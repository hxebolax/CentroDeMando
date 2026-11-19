"""Controlador: une el servicio de escritorios, las teclas globales, la voz y la interfaz.

- Recibe las acciones (de las teclas globales, de los menús o de la bandeja)
  y las reparte: las de escritorios van directas a la cola del servicio (sin
  pasar por el hilo de la interfaz, para que sean instantáneas); las que abren
  ventanas se envían a la interfaz con ``wx.CallAfter``.
- Recibe los avisos del servicio (desde su hilo) y los lleva al hilo
  principal: anuncios por voz, tonos, refresco de la ventana y de la bandeja.
- Lee las preferencias de la configuración en el momento de usarlas: un cambio
  en Opciones se aplica al instante, sin reiniciar.
"""

from __future__ import annotations

import builtins
import logging
import os
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import wx

from app.core import voz
from app.core.config import Configuracion
from app.services import acciones as catalogo
from app.services import sistema
from app.services.escritorios import EstadoEscritorios, InfoEscritorio, InfoVentana
from app.services.reglas import Regla, cargar_reglas
from app.services import ventanas_win32 as w32
from app.services.notificaciones import ACCESO_DENEGADO, Notificacion, PreferenciasNotificaciones, ServicioNotificaciones
from app.services.portapapeles import Elemento, PreferenciasPortapapeles, ServicioPortapapeles
from app.services.servicio import ORIGEN_EXTERNO, Preferencias, ServicioEscritorios
from app.services.teclas import GestorTeclasGlobales, ResultadoRegistro

if TYPE_CHECKING:
	from app.ui.ventana_principal import VentanaPrincipal

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def componer_anuncio(
	escritorio: InfoEscritorio | None,
	total: int,
	decir_numero: bool = True,
	decir_total: bool = False,
	ventanas: int | None = None,
) -> str:
	"""Texto que se anuncia al cambiar de escritorio (función pura, se prueba sin wx).

	- Sin nombre propio: «Escritorio 3» (el número es lo único que hay).
	- Con nombre: «3, Trabajo» o solo «Trabajo» si no se quiere el número.
	- Opcionalmente «de 12» y «2 ventanas».
	"""
	if escritorio is None:
		return ""
	texto = escritorio.describir(con_numero=decir_numero)
	if decir_total and total:
		texto += _(" de {total}").format(total=total)
	if ventanas is not None:
		if ventanas == 0:
			texto += _(", vacío")
		elif ventanas == 1:
			texto += _(", 1 ventana")
		else:
			texto += _(", {n} ventanas").format(n=ventanas)
	return texto


def describir_ventanas(ventanas: list[InfoVentana], maximo: int = 10) -> str:
	"""«3 ventanas: Correo, Documento, Navegador» (función pura)."""
	if not ventanas:
		return _("No hay ventanas en este escritorio.")
	titulos = [v.titulo or v.proceso or _("sin título") for v in ventanas[:maximo]]
	cabecera = _("1 ventana") if len(ventanas) == 1 else _("{n} ventanas").format(n=len(ventanas))
	resto = len(ventanas) - maximo
	texto = cabecera + ": " + "; ".join(titulos)
	if resto > 0:
		texto += _("; y {n} más").format(n=resto)
	return texto


class Controlador:
	"""Coordina servicio, teclas e interfaz. Se crea en el hilo principal."""

	def __init__(
		self,
		configuracion: Configuracion,
		servicio: ServicioEscritorios | None = None,
		con_teclas: bool = True,
		portapapeles: ServicioPortapapeles | None = None,
		notificaciones: ServicioNotificaciones | None = None,
	) -> None:
		self.config = configuracion
		self.servicio = servicio or ServicioEscritorios(self.preferencias)
		self.portapapeles = portapapeles or ServicioPortapapeles(self.preferencias_portapapeles)
		self._oyentes_portapapeles: list[Callable[[], None]] = []
		self.portapapeles.al_agregar = lambda elemento: wx.CallAfter(self._al_copiar, elemento)
		self.notificaciones = notificaciones or ServicioNotificaciones(self.preferencias_notificaciones)
		self._oyentes_notificaciones: list[Callable[[], None]] = []
		self.notificaciones.al_nuevas = lambda nuevas: wx.CallAfter(self._al_notificaciones, nuevas)
		self.notificaciones.al_cambiar_acceso = lambda acceso: wx.CallAfter(self._al_cambiar_acceso, acceso)
		self.teclas = GestorTeclasGlobales(self.ejecutar) if con_teclas else None
		self.ventana: VentanaPrincipal | None = None
		self._oyentes_estado: list[Callable[[EstadoEscritorios], None]] = []
		self.ultimo_registro = ResultadoRegistro({}, {})

		self.servicio.al_cambiar_actual = lambda estado, origen: wx.CallAfter(self._al_cambiar_actual, estado, origen)
		self.servicio.al_cambiar_lista = lambda estado: wx.CallAfter(self._notificar_estado, estado)
		self.servicio.al_error = lambda mensaje: wx.CallAfter(self.avisar, mensaje)
		self.servicio.al_conectar = lambda ok, mensaje: wx.CallAfter(self._al_conectar, ok, mensaje)
		self.servicio.al_aplicar_regla = lambda ventana, regla, destino: wx.CallAfter(self._al_aplicar_regla, ventana, regla, destino)
		if self.teclas is not None:
			self.teclas.al_cambiar_registro = lambda resultado: wx.CallAfter(self._al_registrar_teclas, resultado)

	# ── Arranque y cierre ───────────────────────────────────────────────────

	def iniciar(self) -> None:
		self.servicio.establecer_reglas(self.reglas())
		self.servicio.iniciar()
		try:
			self.notificaciones.iniciar()
		except Exception:  # noqa: BLE001 - sin notificaciones, el resto sigue funcionando
			log.exception("No se pudo iniciar el historial de notificaciones")
		try:
			self.portapapeles.iniciar()
		except Exception:  # noqa: BLE001 - sin historial, el resto del programa sigue funcionando
			log.exception("No se pudo iniciar el historial del portapapeles")
		if self.teclas is not None:
			self.teclas.iniciar()
			self.aplicar_teclas()
			self.teclas.interceptar_flechas_nativas(bool(self.config.obtener("escritorios.interceptar_flechas_nativas", False)))

	def detener(self) -> None:
		if self.teclas is not None:
			self.teclas.detener()
		self.servicio.detener()
		self.portapapeles.detener()
		self.notificaciones.detener()

	# ── Preferencias ────────────────────────────────────────────────────────

	def preferencias(self) -> Preferencias:
		"""Se llama desde el hilo de escritorios en cada operación (la configuración es segura entre hilos)."""
		obtener = self.config.obtener
		return Preferencias(
			ciclico=bool(obtener("escritorios.ciclico", True)),
			enfocar_al_cambiar=bool(obtener("escritorios.enfocar_al_cambiar", True)),
			animacion=bool(obtener("escritorios.animacion", False)),
			seguir_ventana=bool(obtener("ventanas.seguir_ventana", False)),
			intervalo_sondeo_ms=int(obtener("escritorios.intervalo_sondeo_ms", 250)),
			aplicar_reglas_al_iniciar=bool(obtener("ventanas.aplicar_reglas_al_iniciar", False)),
		)

	def preferencias_portapapeles(self) -> PreferenciasPortapapeles:
		"""Se llama desde el hilo del monitor en cada copia."""
		obtener = self.config.obtener
		excluidos = str(obtener("portapapeles.programas_excluidos", ""))
		return PreferenciasPortapapeles(
			activo=bool(obtener("portapapeles.activo", True)),
			maximo=int(obtener("portapapeles.maximo", 500)),
			dias=int(obtener("portapapeles.dias", 0)),
			guardar_html=bool(obtener("portapapeles.guardar_html", True)),
			guardar_archivos=bool(obtener("portapapeles.guardar_archivos", True)),
			guardar_imagenes=bool(obtener("portapapeles.guardar_imagenes", True)),
			maximo_imagen_mb=int(obtener("portapapeles.maximo_imagen_mb", 20)),
			ignorar_privados=bool(obtener("portapapeles.ignorar_privados", True)),
			programas_excluidos=tuple(p.strip() for p in excluidos.replace(";", ",").split(",") if p.strip()),
			restaurar_tras_pegar=bool(obtener("portapapeles.restaurar_tras_pegar", True)),
			retraso_restaurar_ms=int(obtener("portapapeles.retraso_restaurar_ms", 500)),
			metodo_pegado=str(obtener("portapapeles.metodo_pegado", "control_v")),
		)

	def preferencias_notificaciones(self) -> PreferenciasNotificaciones:
		obtener = self.config.obtener
		ignoradas = str(obtener("notificaciones.apps_ignoradas", ""))
		return PreferenciasNotificaciones(
			activo=bool(obtener("notificaciones.activo", True)),
			intervalo_s=float(obtener("notificaciones.intervalo_s", 3)),
			apps_ignoradas=tuple(a.strip() for a in ignoradas.replace(";", ",").split(",") if a.strip()),
			maximo=int(obtener("notificaciones.maximo", 5000)),
			dias=int(obtener("notificaciones.dias", 90)),
		)

	def atajos(self) -> dict[str, str]:
		return catalogo.atajos_efectivos(self.config.obtener("teclas", {}))

	def aplicar_teclas(self) -> ResultadoRegistro:
		"""Vuelve a registrar las teclas globales con la configuración actual."""
		if self.teclas is None:
			return ResultadoRegistro({}, {})
		self.ultimo_registro = self.teclas.registrar(self.atajos())
		return self.ultimo_registro

	def aplicar_gancho(self) -> None:
		if self.teclas is not None:
			self.teclas.interceptar_flechas_nativas(bool(self.config.obtener("escritorios.interceptar_flechas_nativas", False)))

	def reglas(self) -> list[Regla]:
		return cargar_reglas(self.config.obtener("reglas", []))

	def guardar_reglas(self, reglas: list[Regla]) -> None:
		self.config.establecer("reglas", [r.a_dict() for r in reglas])
		self.config.guardar()
		self.servicio.establecer_reglas(reglas)

	# ── Oyentes de estado (ventana, bandeja) ────────────────────────────────

	def suscribir(self, oyente: Callable[[EstadoEscritorios], None]) -> None:
		self._oyentes_estado.append(oyente)

	def _notificar_estado(self, estado: EstadoEscritorios) -> None:
		for oyente in list(self._oyentes_estado):
			try:
				oyente(estado)
			except Exception:  # noqa: BLE001 - un oyente roto no debe impedir los demás
				log.exception("Error al refrescar con el nuevo estado")

	def _al_cambiar_actual(self, estado: EstadoEscritorios, origen: str) -> None:
		self._notificar_estado(estado)
		if not self.config.obtener("anuncios.anunciar_cambios", True):
			return
		if origen == ORIGEN_EXTERNO and not self.config.obtener("anuncios.anunciar_cambios_externos", True):
			return
		if self.config.obtener("anuncios.tono", False):
			sistema.tocar_tono(estado.actual)
		self.anunciar_escritorio(estado, retrasar=True)

	def anunciar_escritorio(self, estado: EstadoEscritorios | None = None, retrasar: bool = False) -> None:
		"""Dice el escritorio actual (y sus ventanas si así está configurado)."""
		estado = estado or self.servicio.estado
		escritorio = estado.escritorio_actual()
		if escritorio is None:
			self.hablar(self.servicio.error_conexion or _("No se conoce el escritorio actual."))
			return
		obtener = self.config.obtener

		def decir(ventanas: int | None) -> None:
			texto = componer_anuncio(
				escritorio,
				estado.total,
				bool(obtener("anuncios.decir_numero", True)),
				bool(obtener("anuncios.decir_total", False)),
				ventanas,
			)
			if retrasar:
				wx.CallLater(max(0, int(obtener("anuncios.retraso_ms", 150))) or 1, self.hablar, texto)
			else:
				self.hablar(texto, interrumpir=True)

		if obtener("anuncios.decir_ventanas", False):
			self.servicio.obtener_ventanas(
				lambda ventanas: wx.CallAfter(decir, sum(1 for v in ventanas if v.id_escritorio == escritorio.id)),
				lambda _mensaje: wx.CallAfter(decir, None),
			)
		else:
			decir(None)

	def anunciar_ventanas(self) -> None:
		estado = self.servicio.estado
		escritorio = estado.escritorio_actual()

		def decir(ventanas: list[InfoVentana]) -> None:
			propias = [v for v in ventanas if escritorio and v.id_escritorio == escritorio.id and not v.en_todos]
			self.hablar(describir_ventanas(propias), interrumpir=True)

		self.servicio.obtener_ventanas(lambda ventanas: wx.CallAfter(decir, ventanas))

	# ── Mensajes ────────────────────────────────────────────────────────────

	def hablar(self, texto: str, interrumpir: bool = False) -> None:
		"""Voz + barra de estado (lo dicho también queda escrito, consultable)."""
		if not texto:
			return
		voz.hablar(texto, interrumpir=interrumpir)
		if self.ventana:
			self.ventana.poner_estado(texto)

	def avisar(self, mensaje: str) -> None:
		"""Fallo de una operación: se dice y se escribe, sin diálogo (puede venir de una tecla global)."""
		log.info("Aviso al usuario: %s", mensaje)
		self.hablar(mensaje, interrumpir=True)

	def _al_conectar(self, ok: bool, mensaje: str) -> None:
		if ok:
			self._notificar_estado(self.servicio.estado)
		else:
			self.avisar(mensaje)

	def _al_aplicar_regla(self, ventana: InfoVentana, regla: Regla, destino: int) -> None:
		if destino:
			texto = _("{ventana} movida al escritorio {n}").format(ventana=ventana.titulo or ventana.proceso, n=destino)
		else:
			texto = _("{ventana} se muestra en todos los escritorios").format(ventana=ventana.titulo or ventana.proceso)
		if self.ventana:
			self.ventana.poner_estado(texto)

	def _al_registrar_teclas(self, resultado: ResultadoRegistro) -> None:
		self.ultimo_registro = resultado
		if resultado.fallidos:
			log.warning("Teclas globales no disponibles: %s", resultado.fallidos)

	# ── Acciones ────────────────────────────────────────────────────────────

	def ejecutar(self, accion: str) -> None:
		"""Ejecuta una acción del catálogo. Se puede llamar desde CUALQUIER hilo.

		Las acciones de escritorio solo encolan (rápido). Las que necesitan la
		interfaz se envían al hilo principal.
		"""
		log.debug("Acción: %s", accion)
		servicio = self.servicio
		if accion in catalogo.NATIVAS:
			# Ctrl+Win+flechas interceptadas: siempre cíclicas (para eso se interceptan).
			servicio.desplazar(1 if catalogo.NATIVAS[accion] == "siguiente" else -1, ciclico=True)
		elif accion == "siguiente":
			servicio.desplazar(1)
		elif accion == "anterior":
			servicio.desplazar(-1)
		elif accion == "primero":
			servicio.ir_al_extremo(ultimo=False)
		elif accion == "ultimo":
			servicio.ir_al_extremo(ultimo=True)
		elif accion == "alternar":
			servicio.alternar()
		elif accion.startswith("ir_") and accion[3:].isdigit():
			servicio.ir_a(int(accion[3:]))
		elif accion.startswith("mover_ventana_") and accion[14:].isdigit():
			servicio.mover_ventana(destino=int(accion[14:]), al_terminar=self._tras_mover_ventana)
		elif accion == "mover_ventana_siguiente":
			servicio.mover_ventana(paso=1, al_terminar=self._tras_mover_ventana)
		elif accion == "mover_ventana_anterior":
			servicio.mover_ventana(paso=-1, al_terminar=self._tras_mover_ventana)
		elif accion == "mover_ventana_nuevo":
			self._mover_ventana_a_nuevo()
		elif accion == "crear":
			servicio.crear(al_terminar=lambda numero: wx.CallAfter(self.hablar, _("Creado el escritorio {n}").format(n=numero), True))
		elif accion == "crear_e_ir":
			servicio.crear(ir=True)
		elif accion in ("mover_escritorio_izquierda", "mover_escritorio_derecha"):
			actual = servicio.estado.actual
			paso = -1 if accion.endswith("izquierda") else 1
			servicio.mover_escritorio(
				actual,
				actual + paso,
				al_terminar=lambda posicion: wx.CallAfter(self.hablar, _("Escritorio en la posición {n}").format(n=posicion), True),
			)
		elif accion in ("anclar_ventana", "anclar_aplicacion"):
			aplicacion = accion == "anclar_aplicacion"
			servicio.anclar_ventana(aplicacion=aplicacion, al_terminar=lambda r: wx.CallAfter(self._tras_anclar, r[1], aplicacion))
		elif accion == "anunciar_actual":
			wx.CallAfter(self.anunciar_escritorio)
		elif accion == "anunciar_ventanas":
			wx.CallAfter(self.anunciar_ventanas)
		elif accion in ("portapapeles_rapido", "emoticonos_rapido"):
			# La ventana de destino se mira AHORA, antes de que se abra la nuestra.
			destino = w32.ventana_activa()
			if destino and w32.pid(destino) == os.getpid():
				destino = 0
			wx.CallAfter(self._abrir_rapida, accion, destino)
		elif accion == "pausar_portapapeles":
			wx.CallAfter(self.alternar_captura)
		elif accion == "notificaciones_rapido":
			wx.CallAfter(self._abrir_rapida, accion, 0)
		elif accion == "leer_ultima_notificacion":
			wx.CallAfter(self.leer_ultima_notificacion)
		elif accion == "pausar_notificaciones":
			wx.CallAfter(self.alternar_notificaciones)
		elif accion in ("eliminar_actual", "renombrar_actual", "selector", "buscar_ventana", "mostrar_gestor"):
			wx.CallAfter(self._accion_de_interfaz, accion)
		else:
			log.warning("Acción desconocida: %s", accion)

	# ── Portapapeles y emoticonos ───────────────────────────────────────────

	def suscribir_portapapeles(self, oyente: Callable[[], None]) -> None:
		self._oyentes_portapapeles.append(oyente)

	def _al_copiar(self, elemento: Elemento) -> None:
		"""Hilo principal: algo nuevo en el historial."""
		for oyente in list(self._oyentes_portapapeles):
			try:
				oyente()
			except Exception:  # noqa: BLE001
				log.exception("Error al refrescar el historial")
		if self.config.obtener("portapapeles.anunciar_copias", False):
			self.hablar(_("Copiado: {resumen}").format(resumen=elemento.resumen(80)))

	def copiar_elemento(self, identificador: int) -> None:
		try:
			elemento = self.portapapeles.copiar(identificador)
		except Exception:  # noqa: BLE001 - portapapeles ocupado por otro programa
			log.warning("No se pudo copiar el elemento %s", identificador, exc_info=True)
			self.avisar(_("No se pudo copiar: otro programa está usando el portapapeles."))
			return
		if elemento is not None:
			self.hablar(_("Copiado al portapapeles"), True)
			self._al_copiar_interno()

	def _al_copiar_interno(self) -> None:
		for oyente in list(self._oyentes_portapapeles):
			oyente()

	def copiar_texto(self, texto: str) -> None:
		try:
			self.portapapeles.copiar_texto(texto)
		except Exception:  # noqa: BLE001
			log.warning("No se pudo copiar el texto", exc_info=True)
			self.avisar(_("No se pudo copiar: otro programa está usando el portapapeles."))

	def _en_hilo(self, nombre: str, trabajo: Callable[[], bool], mensaje_fallo: str) -> None:
		"""Pegar y escribir esperan al foco y duermen: nunca en el hilo de la interfaz."""

		def envoltorio() -> None:
			try:
				correcto = trabajo()
			except Exception:  # noqa: BLE001
				log.exception("Falló «%s»", nombre)
				correcto = False
			if not correcto:
				wx.CallAfter(self.avisar, mensaje_fallo)

		threading.Thread(target=envoltorio, name=nombre, daemon=True).start()

	def pegar_elemento(self, identificador: int, destino: int, transformacion: str | None = None) -> None:
		"""Pega un elemento del historial en la ventana ``destino`` (o en la anterior si no se sabe)."""
		if not destino:
			self.con_destino_anterior(
				lambda hwnd: self.pegar_elemento(identificador, hwnd, transformacion) if hwnd else self.copiar_elemento(identificador)
			)
			return
		self._en_hilo(
			"pegar",
			lambda: self.portapapeles.pegar(identificador, destino, transformacion),
			_("No se pudo volver a la ventana para pegar. El elemento queda copiado en el portapapeles."),
		)

	def insertar_texto(self, texto: str, destino: int) -> None:
		"""Escribe ``texto`` (un emoticono) en la ventana ``destino``."""
		from app.services import pegado

		if not destino:
			self.con_destino_anterior(lambda hwnd: self.insertar_texto(texto, hwnd) if hwnd else self.copiar_texto(texto))
			return
		metodo = str(self.config.obtener("emoticonos.metodo", pegado.METODO_ESCRIBIR))
		self._en_hilo(
			"insertar",
			lambda: pegado.insertar_texto(destino, texto, metodo, self.portapapeles.monitor.hwnd, self.portapapeles.anotar_propia),
			_("No se pudo volver a la ventana para insertar el texto."),
		)

	def con_destino_anterior(self, al_obtener: Callable[[int], None]) -> None:
		"""Busca la ventana usada antes del gestor (la más reciente del escritorio actual que no es nuestra)."""

		def trabajo(motor) -> int:
			actual = motor.id_actual()
			for ventana in motor.ventanas(os.getpid()):
				if ventana.id_escritorio == actual or ventana.en_todos:
					return ventana.hwnd
			return 0

		self.servicio.encolar(
			_("buscar la ventana anterior"), trabajo, lambda hwnd: wx.CallAfter(al_obtener, hwnd), lambda _m: wx.CallAfter(al_obtener, 0)
		)

	def alternar_captura(self) -> None:
		self.portapapeles.pausado = not self.portapapeles.pausado
		self.hablar(_("Captura del portapapeles detenida") if self.portapapeles.pausado else _("Captura del portapapeles reanudada"), True)

	# ── Notificaciones ──────────────────────────────────────────────────────

	def suscribir_notificaciones(self, oyente: Callable[[], None]) -> None:
		self._oyentes_notificaciones.append(oyente)

	def notificar_no_leidas(self) -> None:
		for oyente in list(self._oyentes_notificaciones):
			try:
				oyente()
			except Exception:  # noqa: BLE001
				log.exception("Error al refrescar las notificaciones")

	def _al_notificaciones(self, nuevas: list[Notificacion]) -> None:
		self.notificar_no_leidas()
		if not self.config.obtener("notificaciones.anunciar_nuevas", False):
			return
		con_texto = self.config.obtener("notificaciones.anunciar_texto", True)
		for notificacion in nuevas[-3:]:
			texto = notificacion.resumen()
			if con_texto and notificacion.texto:
				texto += ". " + " ".join(notificacion.texto.split())[:300]
			self.hablar(texto)

	def _al_cambiar_acceso(self, acceso: str) -> None:
		self.notificar_no_leidas()
		if acceso == ACCESO_DENEGADO:
			self.avisar(
				_(
					"Windows no deja leer las notificaciones. Actívelo en Configuración, Privacidad y seguridad, Notificaciones, "
					"o desde el menú Notificaciones, Permiso de Windows."
				)
			)

	def leer_ultima_notificacion(self) -> None:
		ultima = self.notificaciones.historial.ultima()
		if ultima is None:
			self.hablar(_("No hay notificaciones en el historial."), True)
			return
		pendientes = self.notificaciones.historial.no_leidas()
		from app.services.portapapeles import describir_tiempo

		texto = f"{ultima.resumen()}. {' '.join(ultima.texto.split())} {describir_tiempo(ultima.creada)}."
		if pendientes:
			texto += " " + (_("1 sin leer.") if pendientes == 1 else _("{n} sin leer.").format(n=pendientes))
		self.hablar(texto, True)

	def alternar_notificaciones(self) -> None:
		self.notificaciones.pausado = not self.notificaciones.pausado
		self.hablar(
			_("Captura de notificaciones detenida") if self.notificaciones.pausado else _("Captura de notificaciones reanudada"), True
		)

	def _abrir_rapida(self, accion: str, destino: int) -> None:
		if self.ventana:
			self.ventana.abrir_ventana_rapida(accion, destino)

	def _accion_de_interfaz(self, accion: str) -> None:
		if self.ventana:
			self.ventana.ejecutar_accion_de_interfaz(accion)

	def _tras_mover_ventana(self, resultado: tuple[int, int]) -> None:
		_hwnd, numero = resultado
		wx.CallAfter(self.hablar, _("Ventana movida al escritorio {n}").format(n=numero), False)

	def _tras_anclar(self, anclada: bool, aplicacion: bool) -> None:
		if aplicacion:
			texto = (
				_("La aplicación se muestra en todos los escritorios") if anclada else _("La aplicación se muestra solo en su escritorio")
			)
		else:
			texto = _("La ventana se muestra en todos los escritorios") if anclada else _("La ventana se muestra solo en este escritorio")
		self.hablar(texto, interrumpir=True)

	def _mover_ventana_a_nuevo(self) -> None:
		from app.services import ventanas_win32 as w32

		hwnd = w32.ventana_activa()
		if not hwnd:
			self.avisar(_("No hay ninguna ventana activa que mover."))
			return

		def trabajo(motor: Any) -> int:
			numero = motor.crear()
			motor.mover_ventana(hwnd, numero)
			return numero

		def al_terminar(numero: int) -> None:
			self.servicio.actualizar()
			wx.CallAfter(self.hablar, _("Ventana movida al nuevo escritorio {n}").format(n=numero), False)

		self.servicio.encolar(_("mover la ventana a un escritorio nuevo"), trabajo, al_terminar)
