"""Hilo de escritorios: ejecuta todas las operaciones en orden y vigila los cambios (sin wx).

Por qué un hilo propio:

- Las llamadas COM al Explorador son rápidas, pero si el Explorador se cuelga
  o se reinicia pueden tardar segundos. En el hilo de la interfaz eso dejaría
  mudo al lector de pantalla.
- Los gestores COM de pyvda son locales a cada hilo: si todas las operaciones
  pasan por el mismo hilo, nunca se cruzan apartamentos COM.
- Las teclas globales encolan aquí directamente (sin pasar por la interfaz),
  así que cambiar de escritorio es inmediato aunque la ventana esté ocupada.

Además, cuando no hay trabajo, el hilo sondea el escritorio actual cada
``intervalo`` segundos para enterarse de los cambios hechos fuera de la
aplicación (Ctrl+Windows+flechas, Vista de tareas, otros programas) y aplica
las reglas de ventanas a las ventanas nuevas.

Los avisos (``al_cambiar_actual``, ``al_cambiar_lista``, ``al_error``...) se
llaman DESDE ESTE HILO: quien los reciba en la interfaz debe usar
``wx.CallAfter``.
"""

from __future__ import annotations

import builtins
import logging
import os
import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.services import ventanas_win32 as w32
from app.services.escritorios import (
	ErrorEscritorios,
	EstadoEscritorios,
	InfoEscritorio,
	InfoVentana,
	MotorEscritorios,
	calcular_destino,
)
from app.services.reglas import Regla, buscar_regla, destino_de_regla

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


ORIGEN_INTERNO = "interno"
ORIGEN_EXTERNO = "externo"

# Cada cuántos sondeos se relee la lista completa (nombres) aunque no cambie nada.
SONDEOS_POR_LISTA = 8
# Cada cuántos segundos se revisan las ventanas nuevas para las reglas.
INTERVALO_REGLAS = 1.0
# Espera antes de reintentar si el Explorador no responde.
ESPERA_RECONEXION = 3.0


@dataclass
class _Tarea:
	descripcion: str
	trabajo: Callable[[MotorEscritorios], Any]
	al_terminar: Callable[[Any], None] | None = None
	al_fallar: Callable[[str], None] | None = None


@dataclass
class Preferencias:
	"""Opciones que el hilo consulta en cada operación (se leen de la configuración)."""

	ciclico: bool = True
	enfocar_al_cambiar: bool = True
	animacion: bool = False
	seguir_ventana: bool = False
	intervalo_sondeo_ms: int = 250
	aplicar_reglas_al_iniciar: bool = False


class ServicioEscritorios:
	"""Cola de operaciones sobre escritorios con un único hilo trabajador."""

	def __init__(
		self,
		preferencias: Callable[[], Preferencias] | None = None,
		fabrica_motor: Callable[[], MotorEscritorios] = MotorEscritorios,
		excluir_propias: bool = True,
	) -> None:
		self._preferencias = preferencias or Preferencias
		self._fabrica_motor = fabrica_motor
		# Las ventanas del propio gestor no cuentan como ventanas del escritorio.
		self._pid_propio = os.getpid() if excluir_propias else 0
		self._cola: queue.Queue[_Tarea | None] = queue.Queue()
		self._detener = threading.Event()
		self._hilo: threading.Thread | None = None
		self._candado = threading.Lock()
		self._estado = EstadoEscritorios()
		self._id_actual = ""
		self._id_anterior = ""
		self._reglas: list[Regla] = []
		self._ventanas_conocidas: set[int] | None = None
		self._ultima_revision_reglas = 0.0
		self.disponible = False
		self.error_conexion = ""
		# Avisos (se llaman desde el hilo de escritorios).
		self.al_cambiar_actual: Callable[[EstadoEscritorios, str], None] | None = None
		self.al_cambiar_lista: Callable[[EstadoEscritorios], None] | None = None
		self.al_error: Callable[[str], None] | None = None
		self.al_aplicar_regla: Callable[[InfoVentana, Regla, int], None] | None = None
		self.al_conectar: Callable[[bool, str], None] | None = None

	# ── Ciclo de vida ───────────────────────────────────────────────────────

	def iniciar(self) -> None:
		if self._hilo and self._hilo.is_alive():
			return
		self._detener.clear()
		self._hilo = threading.Thread(target=self._bucle, name="escritorios", daemon=True)
		self._hilo.start()

	def detener(self, espera: float = 3.0) -> None:
		self._detener.set()
		self._cola.put(None)
		if self._hilo is not None:
			self._hilo.join(timeout=espera)
			if self._hilo.is_alive():
				log.warning("El hilo de escritorios no terminó a tiempo.")
		self._hilo = None

	@property
	def estado(self) -> EstadoEscritorios:
		"""Copia del último estado conocido (se puede leer desde cualquier hilo)."""
		with self._candado:
			return EstadoEscritorios(self._estado.escritorios, self._estado.actual, self._estado.anterior)

	def establecer_reglas(self, reglas: list[Regla]) -> None:
		with self._candado:
			self._reglas = list(reglas)

	# ── Cola ────────────────────────────────────────────────────────────────

	def encolar(
		self,
		descripcion: str,
		trabajo: Callable[[MotorEscritorios], Any],
		al_terminar: Callable[[Any], None] | None = None,
		al_fallar: Callable[[str], None] | None = None,
	) -> None:
		"""Pone una operación en la cola. ``trabajo(motor)`` corre en el hilo de escritorios."""
		self._cola.put(_Tarea(descripcion, trabajo, al_terminar, al_fallar))

	def _bucle(self) -> None:
		motor: MotorEscritorios | None = None
		sondeos = 0
		while not self._detener.is_set():
			if motor is None:
				motor = self._conectar()
				if motor is None:
					self._detener.wait(ESPERA_RECONEXION)
					self._descartar_tareas(self.error_conexion)
					continue
			intervalo = max(50, int(self._preferencias().intervalo_sondeo_ms)) / 1000
			try:
				tarea = self._cola.get(timeout=intervalo)
			except queue.Empty:
				tarea = None
			if self._detener.is_set():
				break
			if tarea is not None:
				motor = self._ejecutar(motor, tarea)
				continue
			sondeos += 1
			try:
				self._sondear(motor, completo=sondeos % SONDEOS_POR_LISTA == 0)
				self._revisar_reglas(motor)
			except Exception:  # noqa: BLE001 - casi siempre, el Explorador se ha reiniciado
				log.warning("Falló el sondeo de escritorios; se reconecta.", exc_info=True)
				motor = self._reconectar(motor)
		log.info("Hilo de escritorios terminado.")

	def _conectar(self) -> MotorEscritorios | None:
		try:
			motor = self._fabrica_motor()
			self._sincronizar(motor, ORIGEN_EXTERNO, avisar_actual=False)
		except Exception as error:  # noqa: BLE001 - ErrorEscritorios o COMError
			mensaje = str(error) if isinstance(error, ErrorEscritorios) else _("El Explorador de Windows no responde.")
			if self.disponible or not self.error_conexion:
				log.warning("No hay acceso a los escritorios virtuales: %s", error, exc_info=True)
				self.disponible = False
				self.error_conexion = mensaje
				self._avisar(self.al_conectar, False, mensaje)
			return None
		if not self.disponible:
			self.disponible = True
			self.error_conexion = ""
			log.info("Conectado con los escritorios virtuales (%d escritorios).", self._estado.total)
			self._avisar(self.al_conectar, True, "")
		return motor

	def _reconectar(self, motor: MotorEscritorios) -> MotorEscritorios | None:
		try:
			motor.reconectar()
			self._sincronizar(motor, ORIGEN_EXTERNO)
			return motor
		except Exception:  # noqa: BLE001 - se vuelve a crear el motor más tarde
			log.debug("La reconexión rápida falló", exc_info=True)
			self.disponible = True  # para que _conectar avise de la pérdida
			self.error_conexion = ""
			return None

	def _descartar_tareas(self, mensaje: str) -> None:
		"""Sin conexión, las tareas pendientes fallan enseguida en vez de acumularse."""
		while True:
			try:
				tarea = self._cola.get_nowait()
			except queue.Empty:
				return
			if tarea is not None:
				self._fallo(tarea, mensaje)

	def _ejecutar(self, motor: MotorEscritorios, tarea: _Tarea) -> MotorEscritorios | None:
		"""Ejecuta una tarea; si falla por COM, reconecta y la reintenta una vez."""
		for intento in (1, 2):
			try:
				resultado = tarea.trabajo(motor)
			except ErrorEscritorios as error:
				self._fallo(tarea, str(error))
				return motor
			except Exception:  # noqa: BLE001 - COMError: el Explorador se reinició
				if intento == 1:
					log.warning("Falló «%s»; se reconecta y se reintenta.", tarea.descripcion, exc_info=True)
					nuevo = self._reconectar(motor)
					if nuevo is None:
						self._fallo(tarea, _("El Explorador de Windows no responde."))
						return None
					motor = nuevo
					continue
				log.exception("Falló «%s» tras reconectar.", tarea.descripcion)
				self._fallo(tarea, _("No se pudo completar «{tarea}». Detalles en el registro.").format(tarea=tarea.descripcion))
				return motor
			if tarea.al_terminar is not None:
				self._avisar(tarea.al_terminar, resultado)
			return motor
		return motor

	def _fallo(self, tarea: _Tarea, mensaje: str) -> None:
		log.info("No se pudo «%s»: %s", tarea.descripcion, mensaje)
		self._avisar(tarea.al_fallar or self.al_error, mensaje)

	@staticmethod
	def _avisar(funcion: Callable[..., None] | None, *argumentos: Any) -> None:
		if funcion is None:
			return
		try:
			funcion(*argumentos)
		except Exception:  # noqa: BLE001 - un aviso roto no debe parar el hilo
			log.exception("Error en un aviso del servicio de escritorios")

	# ── Estado y sondeo ─────────────────────────────────────────────────────

	def _sondear(self, motor: MotorEscritorios, completo: bool) -> None:
		"""Comprobación barata: escritorio actual y cantidad; la lista entera solo si cambian."""
		if not completo and motor.id_actual() == self._id_actual and motor.total() == self._estado.total:
			return
		self._sincronizar(motor, ORIGEN_EXTERNO)

	def _sincronizar(self, motor: MotorEscritorios, origen: str, avisar_actual: bool = True) -> EstadoEscritorios:
		"""Relee la lista y avisa de lo que haya cambiado."""
		escritorios = tuple(motor.listar())
		id_actual = next((e.id for e in escritorios if e.actual), "")
		with self._candado:
			lista_cambiada = [(e.id, e.nombre) for e in escritorios] != [(e.id, e.nombre) for e in self._estado.escritorios]
			actual_cambiado = id_actual != self._id_actual
			if actual_cambiado:
				if self._id_actual:
					self._id_anterior = self._id_actual
				self._id_actual = id_actual
			numero = lambda identificador: next((e.numero for e in escritorios if e.id == identificador), 0)  # noqa: E731
			self._estado = EstadoEscritorios(escritorios, numero(id_actual), numero(self._id_anterior))
			estado = EstadoEscritorios(escritorios, self._estado.actual, self._estado.anterior)
		if lista_cambiada:
			self._avisar(self.al_cambiar_lista, estado)
		if actual_cambiado and avisar_actual:
			self._avisar(self.al_cambiar_actual, estado, origen)
		return estado

	def _revisar_reglas(self, motor: MotorEscritorios, forzar: bool = False) -> int:
		"""Aplica las reglas a las ventanas nuevas. Devuelve cuántas se movieron."""
		with self._candado:
			reglas = [r for r in self._reglas if r.activa and r.es_valida()]
		if not reglas and not forzar:
			self._ventanas_conocidas = None
			return 0
		ahora = time.monotonic()
		if not forzar and ahora - self._ultima_revision_reglas < INTERVALO_REGLAS:
			return 0
		self._ultima_revision_reglas = ahora
		ventanas = motor.ventanas(self._pid_propio)
		hwnds = {v.hwnd for v in ventanas}
		if self._ventanas_conocidas is None and not forzar and not self._preferencias().aplicar_reglas_al_iniciar:
			# Primera vuelta: lo que ya estaba abierto se respeta.
			self._ventanas_conocidas = hwnds
			return 0
		conocidas = set() if forzar else (self._ventanas_conocidas or set())
		aplicadas = 0
		for ventana in ventanas:
			if ventana.hwnd in conocidas:
				continue
			regla = buscar_regla(reglas, ventana)
			if regla is None:
				continue
			try:
				aplicadas += self._aplicar_regla(motor, ventana, regla)
			except Exception:  # noqa: BLE001 - una ventana especial no debe parar las demás
				log.warning("No se pudo aplicar la regla «%s» a %s", regla.describir(), ventana.describir(), exc_info=True)
		self._ventanas_conocidas = hwnds
		return aplicadas

	def _aplicar_regla(self, motor: MotorEscritorios, ventana: InfoVentana, regla: Regla) -> int:
		if regla.anclar:
			if ventana.anclada:
				return 0
			motor.anclar_ventana(ventana.hwnd, True)
			destino = 0
		else:
			destino = destino_de_regla(regla, self.estado.escritorios)
			if not destino or destino == ventana.escritorio:
				return 0
			motor.mover_ventana(ventana.hwnd, destino)
		log.info("Regla «%s» aplicada a %s", regla.describir(), ventana.describir())
		self._avisar(self.al_aplicar_regla, ventana, regla, destino)
		return 1

	# ── Operaciones de alto nivel ───────────────────────────────────────────
	# Todas encolan; el resultado llega por los avisos o por ``al_terminar``.

	def _leer(self, motor: MotorEscritorios) -> EstadoEscritorios:
		"""Relee el estado antes de una operación sin anunciar el escritorio actual.

		Si el usuario cambió de escritorio por fuera justo antes de pulsar la
		tecla, se anunciaría ese cambio y enseguida el nuestro: dos avisos seguidos.
		"""
		return self._sincronizar(motor, ORIGEN_EXTERNO, avisar_actual=False)

	def _cambiar(self, motor: MotorEscritorios, numero: int) -> EstadoEscritorios:
		"""Cambia al escritorio y, si se pide, da el foco a su última ventana."""
		preferencias = self._preferencias()
		if motor.id_actual() != (self.estado.escritorio(numero).id if self.estado.escritorio(numero) else ""):
			motor.ir_a(numero, preferencias.animacion)
			if preferencias.animacion:
				time.sleep(0.25)
		if preferencias.enfocar_al_cambiar:
			motor.enfocar_ventana_superior(self._pid_propio)
		return self._sincronizar(motor, ORIGEN_INTERNO)

	def ir_a(self, numero: int, al_terminar: Callable[[Any], None] | None = None) -> None:
		def trabajo(motor: MotorEscritorios) -> EstadoEscritorios:
			total = motor.total()
			if not 1 <= numero <= total:
				raise ErrorEscritorios(_("No existe el escritorio {n}; hay {total}.").format(n=numero, total=total))
			self._leer(motor)
			return self._cambiar(motor, numero)

		self.encolar(_("ir al escritorio {n}").format(n=numero), trabajo, al_terminar)

	def desplazar(self, paso: int, ciclico: bool | None = None) -> None:
		"""Siguiente (``paso`` 1) o anterior (``paso`` -1), cíclico según preferencias."""

		def trabajo(motor: MotorEscritorios) -> EstadoEscritorios:
			estado = self._leer(motor)
			vuelta = self._preferencias().ciclico if ciclico is None else ciclico
			destino = calcular_destino(estado.actual, estado.total, paso, vuelta)
			if destino == estado.actual:
				raise ErrorEscritorios(_("Ya está en el último escritorio.") if paso > 0 else _("Ya está en el primer escritorio."))
			return self._cambiar(motor, destino)

		self.encolar(_("cambiar de escritorio"), trabajo)

	def ir_al_extremo(self, ultimo: bool) -> None:
		def trabajo(motor: MotorEscritorios) -> EstadoEscritorios:
			estado = self._leer(motor)
			return self._cambiar(motor, estado.total if ultimo else 1)

		self.encolar(_("ir al último escritorio") if ultimo else _("ir al primer escritorio"), trabajo)

	def alternar(self) -> None:
		"""Vuelve al escritorio en el que se estaba antes (como Alt+Tab, pero de escritorios)."""

		def trabajo(motor: MotorEscritorios) -> EstadoEscritorios:
			estado = self._leer(motor)
			if not estado.anterior or estado.anterior == estado.actual:
				raise ErrorEscritorios(_("Todavía no hay un escritorio anterior al que volver."))
			return self._cambiar(motor, estado.anterior)

		self.encolar(_("volver al escritorio anterior"), trabajo)

	def crear(self, nombre: str = "", ir: bool = False, al_terminar: Callable[[Any], None] | None = None) -> None:
		def trabajo(motor: MotorEscritorios) -> int:
			numero = motor.crear(nombre)
			self._sincronizar(motor, ORIGEN_INTERNO)
			if ir:
				self._cambiar(motor, numero)
			return numero

		self.encolar(_("crear un escritorio"), trabajo, al_terminar)

	def eliminar(self, numero: int | None = None, al_terminar: Callable[[Any], None] | None = None) -> None:
		"""Elimina el escritorio ``numero`` (o el actual); sus ventanas pasan al vecino."""

		def trabajo(motor: MotorEscritorios) -> InfoEscritorio | None:
			estado = self._leer(motor)
			objetivo = numero or estado.actual
			eliminado = estado.escritorio(objetivo)
			motor.eliminar(objetivo)
			if objetivo == estado.actual and self._preferencias().enfocar_al_cambiar:
				motor.enfocar_ventana_superior(self._pid_propio)
			self._sincronizar(motor, ORIGEN_INTERNO)
			return eliminado

		self.encolar(_("eliminar el escritorio"), trabajo, al_terminar)

	def eliminar_vacios(self, al_terminar: Callable[[Any], None] | None = None) -> None:
		"""Elimina los escritorios sin ventanas, salvo el actual."""

		def trabajo(motor: MotorEscritorios) -> int:
			estado = self._leer(motor)
			ocupados = {v.escritorio for v in motor.ventanas(self._pid_propio)}
			vacios = [e.numero for e in estado.escritorios if e.numero not in ocupados and e.numero != estado.actual]
			for numero in sorted(vacios, reverse=True):
				if motor.total() <= 1:
					break
				motor.eliminar(numero)
			self._sincronizar(motor, ORIGEN_INTERNO)
			return len(vacios)

		self.encolar(_("eliminar los escritorios vacíos"), trabajo, al_terminar)

	def renombrar(self, numero: int, nombre: str, al_terminar: Callable[[Any], None] | None = None) -> None:
		def trabajo(motor: MotorEscritorios) -> EstadoEscritorios:
			motor.renombrar(numero, nombre)
			return self._sincronizar(motor, ORIGEN_INTERNO)

		self.encolar(_("cambiar el nombre del escritorio"), trabajo, al_terminar)

	def mover_escritorio(self, numero: int, nueva_posicion: int, al_terminar: Callable[[Any], None] | None = None) -> None:
		def trabajo(motor: MotorEscritorios) -> int:
			total = motor.total()
			destino = min(max(nueva_posicion, 1), total)
			if destino == numero:
				raise ErrorEscritorios(_("El escritorio ya está en esa posición."))
			motor.mover_escritorio(numero, destino)
			self._sincronizar(motor, ORIGEN_INTERNO)
			return destino

		self.encolar(_("mover el escritorio"), trabajo, al_terminar)

	def poner_fondo(self, numero: int | None, ruta: str, al_terminar: Callable[[Any], None] | None = None) -> None:
		"""Fondo de un escritorio, o de todos si ``numero`` es ``None``."""

		def trabajo(motor: MotorEscritorios) -> None:
			if numero is None:
				motor.poner_fondo_todos(ruta)
			else:
				motor.poner_fondo(numero, ruta)

		self.encolar(_("cambiar el fondo"), trabajo, al_terminar)

	def mover_ventana(
		self,
		hwnd: int | None = None,
		destino: int | None = None,
		paso: int | None = None,
		seguir: bool | None = None,
		al_terminar: Callable[[Any], None] | None = None,
	) -> None:
		"""Lleva una ventana (por defecto, la activa) a ``destino`` o a ``paso`` escritorios de distancia.

		``hwnd`` se captura AHORA, no al ejecutar la tarea: si no, otra ventana
		podría haber tomado el primer plano entretanto.
		"""
		ventana = hwnd or w32.ventana_activa()

		def trabajo(motor: MotorEscritorios) -> tuple[int, int]:
			if not ventana:
				raise ErrorEscritorios(_("No hay ninguna ventana activa que mover."))
			estado = self._leer(motor)
			numero = destino
			if numero is None:
				origen = motor.escritorio_de_ventana(ventana) or estado.actual
				numero = calcular_destino(origen, estado.total, paso or 1, self._preferencias().ciclico)
			if not 1 <= numero <= estado.total:
				raise ErrorEscritorios(_("No existe el escritorio {n}.").format(n=numero))
			motor.mover_ventana(ventana, numero)
			if self._preferencias().seguir_ventana if seguir is None else seguir:
				motor.ir_a(numero, self._preferencias().animacion)
				w32.activar(ventana)
				self._sincronizar(motor, ORIGEN_INTERNO)
			elif hwnd is None and self._preferencias().enfocar_al_cambiar:
				# La ventana se fue: el foco pasa a la siguiente de este escritorio.
				motor.enfocar_ventana_superior(self._pid_propio)
			return ventana, numero

		self.encolar(_("mover la ventana"), trabajo, al_terminar)

	def anclar_ventana(
		self,
		hwnd: int | None = None,
		anclar: bool | None = None,
		aplicacion: bool = False,
		al_terminar: Callable[[Any], None] | None = None,
	) -> None:
		"""Muestra la ventana (o toda su aplicación) en todos los escritorios. ``anclar=None`` alterna."""
		ventana = hwnd or w32.ventana_activa()

		def trabajo(motor: MotorEscritorios) -> tuple[int, bool]:
			if not ventana:
				raise ErrorEscritorios(_("No hay ninguna ventana activa."))
			if aplicacion:
				valor = (not motor.app_anclada(ventana)) if anclar is None else anclar
				motor.anclar_app(ventana, valor)
			else:
				valor = (not motor.ventana_anclada(ventana)) if anclar is None else anclar
				motor.anclar_ventana(ventana, valor)
			return ventana, valor

		self.encolar(_("anclar la ventana"), trabajo, al_terminar)

	def ir_a_ventana(self, hwnd: int, al_terminar: Callable[[Any], None] | None = None) -> None:
		"""Cambia al escritorio de la ventana y la activa."""

		def trabajo(motor: MotorEscritorios) -> int:
			numero = motor.escritorio_de_ventana(hwnd)
			if numero and motor.id_actual() != self._id_de(numero):
				motor.ir_a(numero, self._preferencias().animacion)
			if not w32.activar(hwnd):
				try:
					motor._vista(hwnd).set_focus()  # noqa: SLF001 - respaldo de foco del propio motor
				except Exception:  # noqa: BLE001 - la ventana pudo cerrarse
					log.debug("No se pudo enfocar %s", hwnd, exc_info=True)
			self._sincronizar(motor, ORIGEN_INTERNO)
			return numero

		self.encolar(_("ir a la ventana"), trabajo, al_terminar)

	def _id_de(self, numero: int) -> str:
		escritorio = self.estado.escritorio(numero)
		return escritorio.id if escritorio else ""

	def obtener_ventanas(self, al_terminar: Callable[[list[InfoVentana]], None], al_fallar: Callable[[str], None] | None = None) -> None:
		"""Lista de ventanas de todos los escritorios (para la interfaz)."""
		self.encolar(_("leer las ventanas"), lambda motor: motor.ventanas(self._pid_propio), al_terminar, al_fallar)

	def obtener_fondos(self, al_terminar: Callable[[list[InfoEscritorio]], None]) -> None:
		self.encolar(_("leer los fondos"), lambda motor: motor.listar(con_fondo=True), al_terminar)

	def actualizar(self, al_terminar: Callable[[Any], None] | None = None) -> None:
		"""Relee todo y avisa de los cambios."""
		self.encolar(_("actualizar"), lambda motor: self._sincronizar(motor, ORIGEN_EXTERNO), al_terminar)

	def aplicar_reglas_ahora(self, al_terminar: Callable[[Any], None] | None = None) -> None:
		"""Aplica las reglas a TODAS las ventanas abiertas."""
		self.encolar(_("aplicar las reglas"), lambda motor: self._revisar_reglas(motor, forzar=True), al_terminar)
