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


ANUNCIO_NADA = "nada"
ANUNCIO_COMPLETO = "completo"
ANUNCIO_SOLO_VENTANAS = "solo_ventanas"


def decidir_anuncio(modo: str, externo: bool, hay_lector: bool, decir_ventanas: bool) -> str:
	"""Qué decir al cambiar de escritorio (función pura).

	Con lector de pantalla, Windows ya anuncia el escritorio al que se llega,
	lo cambie quien lo cambie: en modo «auto» no se repite y, como mucho, se
	añade cuántas ventanas tiene.
	"""
	if modo == "nunca":
		return ANUNCIO_NADA
	if modo == "todos" or (modo == "propios" and not externo):
		return ANUNCIO_COMPLETO
	if modo == "auto" and not hay_lector:
		return ANUNCIO_NADA if externo else ANUNCIO_COMPLETO
	if modo == "auto" and decir_ventanas:
		return ANUNCIO_SOLO_VENTANAS
	return ANUNCIO_NADA


def contar_ventanas(cuantas: int) -> str:
	"""«Vacío», «1 ventana», «3 ventanas»."""
	if cuantas == 0:
		return _("Vacío")
	return _("1 ventana") if cuantas == 1 else _("{n} ventanas").format(n=cuantas)


ACCIONES_AUDIO_GENERAL = (
	"audio_siguiente_salida",
	"audio_subir",
	"audio_bajar",
	"audio_silenciar",
	"audio_microfono",
	"decir_audio",
	"audio_micro_subir",
	"audio_micro_bajar",
	"audio_micro_escuchar",
	"audio_micro_decir",
	"audio_balance_izquierda",
	"audio_balance_derecha",
	"audio_balance_centrar",
	"audio_perfil_siguiente",
	"decir_privacidad",
)


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
		self._oyentes_no_molestar: list[Callable[[bool], None]] = []
		self._temporizador_no_molestar = None
		self._temporizador_micro = None
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
		self.temporizadores.al_vencer = lambda t: wx.CallAfter(self._al_vencer_temporizador, t)
		self.temporizadores.al_cambiar = lambda: wx.CallAfter(self._al_cambiar_temporizadores)
		self.temporizadores.iniciar()
		self._iniciar_vigilante_audio()
		wx.CallAfter(self._vigilar_no_molestar)
		wx.CallAfter(self._vigilar_microfono)
		wx.CallLater(1500, self.aplicar_preferencias_audio, False)
		wx.CallLater(30_000, self._copia_automatica)
		wx.CallLater(3000, self.aplicar_cifrado_portapapeles)
		if self.config.obtener("audio.silenciar_micro_al_iniciar", False):
			from app.services import audio

			try:
				audio.poner_silencio_entrada(True)
				log.info("Micrófono silenciado al arrancar (opción).")
			except Exception:  # noqa: BLE001
				log.warning("No se pudo silenciar el micrófono al arrancar", exc_info=True)
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
		for nombre in ("_temporizador_no_molestar", "_temporizador_micro"):
			temporizador = getattr(self, nombre, None)
			if temporizador is not None:
				temporizador.Stop()
				setattr(self, nombre, None)
		if self.teclas is not None:
			self.teclas.detener()
		self.servicio.detener()
		self.portapapeles.detener()
		self.notificaciones.detener()
		if getattr(self, "_temporizadores", None) is not None:
			self._temporizadores.detener()
		if getattr(self, "_vigilante_audio", None) is not None:
			self._vigilante_audio.detener()

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
			cifrar=bool(obtener("portapapeles.cifrar", False)),
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
		if self.config.obtener("anuncios.tono", False):
			sistema.tocar_tono(estado.actual)
		modo = str(self.config.obtener("anuncios.cambio_escritorio", "auto"))
		que = decidir_anuncio(modo, origen == ORIGEN_EXTERNO, voz.hay_lector_de_pantalla(), bool(self.config.obtener("anuncios.decir_ventanas", False)))
		if que == ANUNCIO_COMPLETO:
			self.anunciar_escritorio(estado, retrasar=True)
		elif que == ANUNCIO_SOLO_VENTANAS:
			self._anunciar_solo_ventanas(estado)

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

	def _anunciar_solo_ventanas(self, estado: EstadoEscritorios) -> None:
		"""Tras el anuncio de Windows, añade solo cuántas ventanas hay («2 ventanas»)."""
		escritorio = estado.escritorio_actual()
		if escritorio is None:
			return
		retraso = max(0, int(self.config.obtener("anuncios.retraso_ms", 150))) + 400

		def decir(ventanas: list[InfoVentana]) -> None:
			cuantas = sum(1 for v in ventanas if v.id_escritorio == escritorio.id)
			wx.CallLater(retraso, self.hablar, contar_ventanas(cuantas))

		self.servicio.obtener_ventanas(lambda ventanas: wx.CallAfter(decir, ventanas))

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
		elif accion in ("portapapeles_rapido", "emoticonos_rapido", "portapapeles_favoritos"):
			# La ventana de destino se mira AHORA, antes de que se abra la nuestra.
			destino = w32.ventana_activa()
			if destino and w32.pid(destino) == os.getpid():
				destino = 0
			wx.CallAfter(self._abrir_rapida, accion, destino)
		elif accion.startswith("pegar_reciente_") and accion[15:].isdigit():
			# El destino es la ventana que tiene el foco AHORA.
			destino = w32.ventana_activa()
			wx.CallAfter(self.pegar_reciente, int(accion[15:]), destino)
		elif accion in ACCIONES_AUDIO_GENERAL:
			metodo = {
				"audio_siguiente_salida": self.siguiente_salida_audio,
				"audio_subir": lambda: self.volumen_general(5),
				"audio_bajar": lambda: self.volumen_general(-5),
				"audio_silenciar": self.silenciar_general,
				"audio_microfono": self.silenciar_microfono,
				"decir_audio": self.decir_audio,
				"audio_micro_subir": lambda: self.volumen_microfono(5),
				"audio_micro_bajar": lambda: self.volumen_microfono(-5),
				"audio_micro_escuchar": self.escuchar_microfono,
				"audio_micro_decir": self.decir_microfono,
				"audio_balance_izquierda": lambda: self.mover_balance(-10),
				"audio_balance_derecha": lambda: self.mover_balance(10),
				"audio_balance_centrar": lambda: self.mover_balance(None),
				"audio_perfil_siguiente": self.siguiente_perfil_audio,
				"decir_privacidad": self.decir_privacidad,
			}[accion]
			wx.CallAfter(metodo)
		elif accion in ("audio_app_subir", "audio_app_bajar", "audio_app_silenciar", "audio_app_decir", "audio_solo_app", "audio_app_salida"):
			# La ventana se mira AHORA, en el hilo de las teclas, antes de que cambie el foco.
			wx.CallAfter(self.audio_aplicacion_activa, accion, w32.ventana_activa())
		elif accion == "decir_estado_sistema":
			wx.CallAfter(self.decir_estado_sistema)
		elif accion in ("nuevo_temporizador", "nueva_alarma"):
			wx.CallAfter(self._abrir_desde_lanzador, accion)
		elif accion == "decir_temporizadores":
			wx.CallAfter(self.decir_temporizadores)
		elif accion == "siempre_encima":
			from app.services import procesos

			hwnd = w32.ventana_activa()
			if hwnd:
				encima = not procesos.esta_encima(hwnd)
				procesos.poner_encima(hwnd, encima)
				wx.CallAfter(self.hablar, _("Siempre encima") if encima else _("Ya no está siempre encima"), True)
		elif accion == "bloquear_equipo":
			from app.services import equipo

			equipo.bloquear()
		elif accion == "apagar_pantalla":
			from app.services import equipo

			equipo.apagar_pantalla()
		elif accion == "pausar_portapapeles":
			wx.CallAfter(self.alternar_captura)
		elif accion == "no_molestar":
			wx.CallAfter(self.alternar_no_molestar)
		elif accion == "lanzador":
			destino = w32.ventana_activa()
			if destino and w32.pid(destino) == os.getpid():
				destino = 0
			wx.CallAfter(self._abrir_rapida, accion, destino)
		elif accion.startswith("area:") and accion[5:].isdigit():
			wx.CallAfter(self._mostrar_area, int(accion[5:]))
		elif accion == "fragmentos_rapido":
			destino = w32.ventana_activa()
			if destino and w32.pid(destino) == os.getpid():
				destino = 0
			wx.CallAfter(self._abrir_rapida, accion, destino)
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
		if self.config.obtener("portapapeles.anunciar_copias", False) and not self.no_molestar_activo():
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

	def pegar_reciente(self, posicion: int, destino: int) -> None:
		"""Pega el elemento ``posicion`` del historial (1 = el más reciente) en ``destino``."""
		elementos = self.portapapeles.historial.listar(limite=posicion)
		if len(elementos) < posicion:
			self.avisar(_("El historial no tiene {n} elementos.").format(n=posicion))
			return
		self.pegar_elemento(elementos[posicion - 1].id, destino)

	@property
	def fragmentos(self):
		"""Almacén de fragmentos de texto (se crea la primera vez que se usa)."""
		if getattr(self, "_fragmentos", None) is None:
			from app.services.fragmentos import AlmacenFragmentos

			self._fragmentos = AlmacenFragmentos()
		return self._fragmentos

	def texto_del_portapapeles(self) -> str:
		from app.services import portapapeles_win32 as pw

		contenido = pw.leer(con_html=False, con_archivos=False, con_imagenes=False)
		return contenido.texto if contenido else ""

	def insertar_fragmento(self, fragmento, destino: int) -> None:
		"""Expande las variables del fragmento y lo escribe en ``destino``."""
		from app.services.fragmentos import expandir

		texto, retroceso = expandir(fragmento.texto, portapapeles=self.texto_del_portapapeles)
		self.insertar_texto(texto, destino, retroceso)

	def insertar_texto(self, texto: str, destino: int, retroceso: int = 0) -> None:
		"""Escribe ``texto`` (un emoticono o un fragmento) en la ventana ``destino``."""
		from app.services import pegado

		if not destino:
			self.con_destino_anterior(lambda hwnd: self.insertar_texto(texto, hwnd, retroceso) if hwnd else self.copiar_texto(texto))
			return
		metodo = str(self.config.obtener("emoticonos.metodo", pegado.METODO_ESCRIBIR))
		self._en_hilo(
			"insertar",
			lambda: pegado.insertar_texto(destino, texto, metodo, self.portapapeles.monitor.hwnd, self.portapapeles.anotar_propia, retroceso),
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

	# ── No molestar ─────────────────────────────────────────────────────────

	def no_molestar_activo(self) -> bool:
		"""«No molestar» en vigor: activado a mano o dentro de su horario."""
		from app.services import no_molestar

		obtener = self.config.obtener
		return no_molestar.activo(
			bool(obtener("no_molestar.activo", False)),
			bool(obtener("no_molestar.programado", False)),
			str(obtener("no_molestar.desde", "23:00")),
			str(obtener("no_molestar.hasta", "08:00")),
		)

	def alternar_no_molestar(self) -> None:
		"""Activa o desactiva «No molestar» a mano y lo dice."""
		en_vigor = self.no_molestar_activo()
		manual = bool(self.config.obtener("no_molestar.activo", False))
		if en_vigor and not manual:
			# Está en vigor por horario: desactivarlo a mano no es posible sin
			# quitar el horario; se avisa en lugar de no hacer nada.
			self.hablar(_("No molestar está activo por horario. Cámbielo en Opciones, No molestar."), True)
			return
		self.config.establecer("no_molestar.activo", not manual)
		self.config.guardar()
		self.hablar(_("No molestar activado") if not manual else _("No molestar desactivado"), True)
		self.avisar_no_molestar()

	def suscribir_no_molestar(self, oyente: Callable[[bool], None]) -> None:
		self._oyentes_no_molestar.append(oyente)

	def avisar_no_molestar(self) -> None:
		"""Avisa a la bandeja y a la ventana del estado actual (también al cambiar de franja)."""
		en_vigor = self.no_molestar_activo()
		self._ultimo_no_molestar = en_vigor
		for oyente in list(self._oyentes_no_molestar):
			try:
				oyente(en_vigor)
			except Exception:  # noqa: BLE001
				log.exception("Error al avisar del estado de No molestar")

	def _vigilar_no_molestar(self) -> None:
		"""Cada minuto mira si se entra o se sale de la franja horaria."""
		if self.no_molestar_activo() != getattr(self, "_ultimo_no_molestar", None):
			self.avisar_no_molestar()
		self._temporizador_no_molestar = wx.CallLater(60_000, self._vigilar_no_molestar)

	# ── Notificaciones ──────────────────────────────────────────────────────

	def suscribir_notificaciones(self, oyente: Callable[[bool], None]) -> None:
		"""``oyente(hay_nuevas)``: con ``True`` hay que releer la lista; con ``False`` basta el contador."""
		self._oyentes_notificaciones.append(oyente)

	def notificar_no_leidas(self, hay_nuevas: bool = False) -> None:
		for oyente in list(self._oyentes_notificaciones):
			try:
				oyente(hay_nuevas)
			except Exception:  # noqa: BLE001
				log.exception("Error al refrescar las notificaciones")

	def _al_notificaciones(self, nuevas: list[Notificacion]) -> None:
		self.notificar_no_leidas(hay_nuevas=True)
		if not self.config.obtener("notificaciones.anunciar_nuevas", False):
			return
		from app.services.no_molestar import debe_anunciar_notificacion

		silencio = self.no_molestar_activo()
		solo_estas = str(self.config.obtener("notificaciones.apps_anunciadas", ""))
		permitidas = str(self.config.obtener("no_molestar.apps_permitidas", ""))
		nuevas = [n for n in nuevas if debe_anunciar_notificacion(n.app, n.aumid, solo_estas, silencio, permitidas)]
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

	# ── Audio y sistema ─────────────────────────────────────────────────────

	def _audio(self, funcion: Callable[[], str]) -> None:
		"""Ejecuta una orden de audio en el hilo principal (COM ya iniciado) y dice el resultado."""
		from app.services import audio

		try:
			self.hablar(funcion(), True)
		except audio.ErrorAudio as error:
			self.avisar(str(error))
		except Exception:  # noqa: BLE001
			log.exception("Error de audio")
			self.avisar(_("No se pudo cambiar el audio. Detalles en el registro."))
		if self.ventana and self.ventana.area_actual() is self.ventana.area_audio:
			self.ventana.area_audio.refrescar()

	def siguiente_salida_audio(self) -> None:
		from app.services import audio

		self._audio(lambda: audio.siguiente_salida().nombre)

	def volumen_general(self, paso: int) -> None:
		from app.services import audio

		self._audio(lambda: _("Volumen {v} %").format(v=audio.cambiar_volumen_general(paso)))

	def silenciar_general(self) -> None:
		from app.services import audio

		self._audio(lambda: _("Sonido silenciado") if audio.alternar_silencio_general() else _("Sonido activado"))

	def silenciar_microfono(self) -> None:
		from app.services import audio

		self._audio(lambda: _("Micrófono silenciado") if audio.alternar_microfono() else _("Micrófono activado"))

	def volumen_microfono(self, paso: int) -> None:
		from app.services import audio

		def cambiar() -> str:
			nuevo = audio.cambiar_volumen_entrada(paso)
			self.fijar_volumen_micro_bloqueado(nuevo)
			return _("Micrófono {v} %").format(v=nuevo)

		self._audio(cambiar)

	def fijar_volumen_micro_bloqueado(self, volumen: int) -> None:
		"""Si el micrófono está bloqueado, lo que la persona elige pasa a ser el volumen fijo."""
		if not self.config.obtener("audio.bloquear_micro", False):
			return
		self.config.establecer("audio.volumen_micro_bloqueado", int(volumen))
		pendiente = getattr(self, "_guardado_micro", None)
		if pendiente is not None and pendiente.IsRunning():
			pendiente.Restart(1000)
		else:
			self._guardado_micro = wx.CallLater(1000, self.config.guardar)

	def escuchar_microfono(self) -> None:
		from app.services import audio

		self._audio(audio.alternar_escucha_predeterminada)

	def decir_microfono(self) -> None:
		from app.services import audio

		def texto() -> str:
			micro = next((d for d in audio.dispositivos_entrada() if d.predeterminado), None)
			if micro is None:
				return _("No hay ningún micrófono.")
			volumen, silencio = audio.volumen_entrada(micro.id)
			escucha, _destino = audio.leer_escucha(micro.id)
			return _("{m}, volumen {v} %{s}{e}").format(
				m=micro.nombre, v=volumen, s=_(", silenciado") if silencio else "", e=_(", se está escuchando") if escucha else ""
			)

		self._audio(texto)

	def mover_balance(self, paso: int | None) -> None:
		"""``None`` centra; un número inclina el balance tantos puntos."""
		from app.services import audio

		def cambiar() -> str:
			actual = audio.balance_general()
			if actual is None:
				raise audio.ErrorAudio(_("El balance solo se puede cambiar en salidas estéreo (dos canales)."))
			return _("Balance: {b}").format(b=audio.describir_balance(audio.poner_balance_general(0 if paso is None else actual + paso)))

		self._audio(cambiar)

	# ── Perfiles de audio, privacidad y micrófono fijo ──────────────────────

	def perfiles_audio(self) -> list:
		from app.services import perfiles_audio

		return perfiles_audio.cargar(self.config.obtener("audio.perfiles", []))

	def guardar_perfiles_audio(self, perfiles: list) -> None:
		self.config.establecer("audio.perfiles", [p.a_dict() for p in perfiles])
		self.config.guardar()

	def aplicar_perfil_audio(self, perfil) -> None:
		from app.services import perfiles_audio

		def aplicar() -> str:
			faltan = perfiles_audio.aplicar(perfil)
			self.config.establecer("audio.ultimo_perfil", perfil.nombre)
			self.config.guardar()
			texto = _("Perfil {p}").format(p=perfil.nombre)
			if faltan:
				texto += ". " + _("No está conectado: {f}").format(f=", ".join(faltan))
			return texto

		self._audio(aplicar)

	def siguiente_perfil_audio(self) -> None:
		from app.services import perfiles_audio

		perfil = perfiles_audio.siguiente(self.perfiles_audio(), str(self.config.obtener("audio.ultimo_perfil", "")))
		if perfil is None:
			self.avisar(_("No hay perfiles de audio. Guárdelos en el área de audio, menú Acción."))
			return
		self.aplicar_perfil_audio(perfil)

	def decir_privacidad(self) -> None:
		from app.services import audio

		microfono = audio.apps_usando("microphone")
		camara = audio.apps_usando("webcam")
		partes = [
			_("Micrófono: {a}").format(a=", ".join(microfono)) if microfono else _("Nadie usa el micrófono"),
			_("Cámara: {a}").format(a=", ".join(camara)) if camara else _("nadie usa la cámara"),
		]
		self.hablar(". ".join(partes), True)

	def _al_cambio_escucha(self, identificador: str) -> None:
		"""Alguien cambió «Escuchar este dispositivo» (Panel de sonido u otro programa): se dice."""
		from app.services import audio

		if audio.cambio_de_escucha_propio(identificador):
			return
		try:
			activa, _destino = audio.leer_escucha(identificador)
			nombre = next((d.nombre for d in audio.dispositivos_entrada() if d.id == identificador), _("el micrófono"))
		except Exception:  # noqa: BLE001
			log.debug("No se pudo leer el cambio de escucha", exc_info=True)
			return
		conocidas = self.__dict__.setdefault("_escuchas_conocidas", {})
		if conocidas.get(identificador) == activa:
			return
		conocidas[identificador] = activa
		self.hablar((_("Se oye {m}") if activa else _("Ya no se oye {m}")).format(m=nombre))
		if self.ventana and self.ventana.area_actual() is self.ventana.area_audio:
			self.ventana.area_audio.refrescar()

	def limites_volumen(self) -> dict[str, int]:
		from app.services import audio

		return audio.leer_limites(self.config.obtener("audio.volumen_maximo", {}))

	def poner_limite_volumen(self, programa: str, maximo: int | None) -> None:
		"""``None`` o 100 quita el límite."""
		from app.services import audio

		limites = self.limites_volumen()
		clave = audio.nombre_programa(programa)
		if maximo is None or maximo >= 100:
			limites.pop(clave, None)
		else:
			limites[clave] = max(0, int(maximo))
		self.config.establecer("audio.volumen_maximo", limites)
		self.config.guardar()

	def aplicar_preferencias_audio(self, anunciar: bool = True) -> None:
		"""Pone como predeterminados la salida y el micrófono preferidos que estén conectados."""
		from app.services import audio
		from app.services.preferencias_audio import cambio_necesario

		for entrada in (False, True):
			sufijo = "entrada" if entrada else "salida"
			if not self.config.obtener(f"audio.cambio_automatico_{sufijo}", False):
				continue
			preferencias = [str(n) for n in self.config.obtener(f"audio.preferencias_{sufijo}", []) if isinstance(n, str)]
			try:
				conectados = audio.dispositivos_entrada() if entrada else audio.dispositivos_salida()
				elegido = cambio_necesario(preferencias, conectados)
				if elegido is None:
					continue
				if entrada:
					audio.poner_predeterminado_entrada(elegido)
				else:
					audio.poner_predeterminado(elegido)
			except Exception:  # noqa: BLE001
				log.warning("No se pudo pasar al dispositivo preferido", exc_info=True)
				continue
			log.info("Dispositivo preferido puesto (%s): %s", sufijo, elegido.nombre)
			if anunciar and not self.no_molestar_activo():
				self.hablar((_("Micrófono: {d}") if entrada else _("Salida: {d}")).format(d=elegido.nombre))
		if self.ventana and self.ventana.area_actual() is self.ventana.area_audio:
			self.ventana.area_audio.refrescar()

	def _vigilar_sesion(self) -> None:
		"""Al bloquear el equipo silencia las aplicaciones y el micrófono; al volver, lo devuelve."""
		from app.services import audio, sesion

		bloqueada = sesion.sesion_bloqueada()
		if bloqueada is None or bloqueada == getattr(self, "_sesion_bloqueada", False):
			return
		self._sesion_bloqueada = bloqueada
		if bloqueada:
			if not self.config.obtener("audio.silenciar_al_bloquear", False):
				return
			try:
				self._silenciadas_al_bloquear = audio.silenciar_salvo_lectores()
				self._micro_silenciado_al_bloquear = not audio.volumen_entrada()[1]
				if self._micro_silenciado_al_bloquear:
					audio.poner_silencio_entrada(True)
				log.info("Equipo bloqueado: %d aplicaciones silenciadas.", len(self._silenciadas_al_bloquear))
			except Exception:  # noqa: BLE001
				log.warning("No se pudo silenciar al bloquear", exc_info=True)
			return
		try:
			devueltas = audio.quitar_silencio(getattr(self, "_silenciadas_al_bloquear", []))
			if getattr(self, "_micro_silenciado_al_bloquear", False):
				audio.poner_silencio_entrada(False)
			if devueltas or getattr(self, "_micro_silenciado_al_bloquear", False):
				log.info("Equipo desbloqueado: sonido devuelto a %d aplicaciones.", devueltas)
		except Exception:  # noqa: BLE001
			log.warning("No se pudo devolver el sonido al desbloquear", exc_info=True)
		self._silenciadas_al_bloquear = []
		self._micro_silenciado_al_bloquear = False

	def _vigilar_microfono(self) -> None:
		"""Cada 2 segundos, si está pedido, devuelve el micrófono a su volumen fijo."""
		from app.services import audio

		try:
			self._vigilar_sesion()
		except Exception:  # noqa: BLE001
			log.debug("No se pudo vigilar la sesión", exc_info=True)
		limites = self.limites_volumen()
		if limites:
			try:
				for nombre in audio.aplicar_limites(limites):
					log.info("Volumen de %s bajado a su máximo", nombre)
			except Exception:  # noqa: BLE001
				log.debug("No se pudieron aplicar los volúmenes máximos", exc_info=True)
		if self.config.obtener("audio.bloquear_micro", False):
			objetivo = min(max(int(self.config.obtener("audio.volumen_micro_bloqueado", 80)), 0), 100)
			try:
				actual = audio.volumen_entrada()[0]
				if actual != objetivo:
					audio.poner_volumen_entrada(objetivo)
					log.info("Volumen del micrófono devuelto de %s %% a %s %%", actual, objetivo)
			except Exception:  # noqa: BLE001 - sin micrófono o desconectado
				log.debug("No se pudo vigilar el volumen del micrófono", exc_info=True)
		self._temporizador_micro = wx.CallLater(2000, self._vigilar_microfono)

	def aplicar_cifrado_portapapeles(self) -> None:
		"""Si la opción no coincide con lo guardado, cifra o descifra el historial en segundo plano."""
		cifrar = bool(self.config.obtener("portapapeles.cifrar", False))
		historial = self.portapapeles.historial
		try:
			pendientes = historial.contar_cifrados(not cifrar)
		except Exception:  # noqa: BLE001
			log.debug("No se pudo contar el historial", exc_info=True)
			return
		historial.cifrar = cifrar
		if not pendientes or getattr(self, "_cifrando", False):
			return
		self._cifrando = True

		def trabajo() -> None:
			try:
				cambiados = historial.cambiar_cifrado(cifrar)
				texto = (_("Historial del portapapeles cifrado: {n} elementos") if cifrar else _("Historial del portapapeles descifrado: {n} elementos")).format(
					n=cambiados
				)
				wx.CallAfter(self.hablar, texto)
			except Exception:  # noqa: BLE001
				log.exception("No se pudo cambiar el cifrado del historial")
				wx.CallAfter(self.avisar, _("No se pudo cifrar o descifrar el historial. Detalles en el registro."))
			finally:
				self._cifrando = False

		threading.Thread(target=trabajo, name="cifrado-portapapeles", daemon=True).start()

	def _copia_automatica(self) -> None:
		"""Copia de seguridad diaria, en un hilo para no frenar la interfaz."""
		if not self.config.obtener("copias.automaticas", True):
			return
		from app.core.version import APP_VERSION
		from app.services import copias

		conservar = max(1, int(self.config.obtener("copias.conservar", 7)))
		con_portapapeles = bool(self.config.obtener("copias.incluir_portapapeles", True))
		threading.Thread(
			target=copias.copia_automatica, args=(APP_VERSION, conservar, con_portapapeles), name="copia-seguridad", daemon=True
		).start()

	def decir_audio(self) -> None:
		from app.services import audio

		def texto() -> str:
			salida = next((d.nombre for d in audio.dispositivos_salida() if d.predeterminado), _("sin salida"))
			volumen, silencio = audio.volumen_general()
			return _("{s}, volumen {v} %{m}").format(s=salida, v=volumen, m=_(", silenciado") if silencio else "")

		self._audio(texto)

	def audio_aplicacion_activa(self, accion: str, hwnd: int) -> None:
		"""Volumen solo del programa que tiene el foco."""
		from app.services import audio

		if (not hwnd or w32.pid(hwnd) == os.getpid()) and not (accion == "audio_solo_app" and audio._silenciadas_por_solo):
			self.avisar(_("Ponga el foco en el programa cuyo sonido quiere cambiar."))
			return
		funciones = {
			"audio_app_subir": lambda: audio.cambiar_volumen_ventana(hwnd, 5),
			"audio_app_bajar": lambda: audio.cambiar_volumen_ventana(hwnd, -5),
			"audio_app_silenciar": lambda: audio.alternar_silencio_ventana(hwnd),
			"audio_app_decir": lambda: audio.decir_volumen_ventana(hwnd),
			"audio_solo_app": lambda: audio.solo_esta_aplicacion(hwnd),
			"audio_app_salida": lambda: audio.siguiente_salida_de_ventana(hwnd),
		}
		self._audio(funciones[accion])

	def _iniciar_vigilante_audio(self) -> None:
		"""Avisos de dispositivos de audio conectados y desconectados (se registra en el hilo principal)."""
		from app.services import audio

		def al_cambiar(texto: str) -> None:
			if self.config.obtener("anuncios.dispositivos_audio", True) and not self.no_molestar_activo():
				wx.CallAfter(self.hablar, texto)
			if self.ventana:
				wx.CallAfter(lambda: self.ventana.area_audio.refrescar() if self.ventana.area_actual() is self.ventana.area_audio else None)

		try:
			self._vigilante_audio = audio.VigilanteDispositivos(
				al_cambiar,
				con_pantallas=lambda: bool(self.config.obtener("anuncios.dispositivos_pantallas", False)),
				al_estabilizar=lambda: wx.CallAfter(self.aplicar_preferencias_audio),
				al_cambio_escucha=lambda identificador: wx.CallLater(400, self._al_cambio_escucha, identificador),
			)
			self._vigilante_audio.iniciar()
		except Exception:  # noqa: BLE001 - sin avisos de dispositivos, el resto sigue
			log.warning("No se pudieron vigilar los dispositivos de audio", exc_info=True)
			self._vigilante_audio = None

	def decir_estado_sistema(self) -> None:
		from app.services import equipo

		try:
			self.hablar(equipo.resumen_para_voz(), True)
		except Exception:  # noqa: BLE001
			log.exception("No se pudo leer el estado del equipo")

	def abrir_permiso_notificaciones(self) -> None:
		try:
			os.startfile("ms-settings:privacy-notifications")  # noqa: S606 - página de Configuración de Windows
		except OSError:
			log.exception("No se pudo abrir la configuración de privacidad")
		self.notificaciones.consultar_ya()

	# ── Actualizaciones ─────────────────────────────────────────────────────

	def config_actualizador(self):
		"""Configuración del actualizador con las fuentes elegidas en Opciones (se lee en cada uso)."""
		from app.core.version import APP_VERSION
		from app.services import actualizador

		config = actualizador.configuracion_por_defecto(APP_VERSION)
		config.extra["urls"] = actualizador.urls_de_fuente(
			str(self.config.obtener("actualizaciones.fuente", "ambos")),
			str(self.config.obtener("actualizaciones.url_personalizada", "")),
		)
		return config

	# ── Temporizadores ──────────────────────────────────────────────────────

	@property
	def temporizadores(self):
		if getattr(self, "_temporizadores", None) is None:
			from app.services.temporizadores import ServicioTemporizadores

			self._temporizadores = ServicioTemporizadores()
		return self._temporizadores

	def _al_vencer_temporizador(self, temporizador) -> None:
		from app.ui.area_temporizadores import DialogoAviso

		DialogoAviso(self, temporizador).abrir()
		self._al_cambiar_temporizadores()

	def _al_cambiar_temporizadores(self) -> None:
		if self.ventana and self.ventana.IsShown() and self.ventana.area_actual() is self.ventana.area_temporizadores:
			self.ventana.area_temporizadores.refrescar()

	def decir_temporizadores(self) -> None:
		from app.services.temporizadores import describir_duracion

		activos = [t for t in self.temporizadores.todos() if t.activo]
		if not activos:
			self.hablar(_("No hay temporizadores ni alarmas en marcha."), True)
			return
		self.hablar("; ".join(f"{t.nombre}: {describir_duracion(t.restante())}" for t in activos[:5]), True)

	# ── Lanzador ────────────────────────────────────────────────────────────

	AREAS = (
		"Escritorios",
		"Portapapeles",
		"Fragmentos de texto",
		"Emoticonos",
		"Notificaciones",
		"Audio",
		"Sistema",
		"Ventanas y procesos",
		"Temporizadores y alarmas",
	)

	@property
	def catalogo_lanzador(self):
		"""Programas, ajustes y acciones para el lanzador (se crea la primera vez)."""
		if getattr(self, "_catalogo_lanzador", None) is None:
			from app.services.lanzador import TIPO_ACCION, CatalogoLanzador, Elemento

			acciones = [
				Elemento(f"accion:{a.id}", a.nombre, TIPO_ACCION, a.id, a.descripcion)
				for a in catalogo.ACCIONES
				if a.id != "lanzador"
			]
			acciones += [
				Elemento(f"accion:area:{n}", _("Ver el área de {a}").format(a=nombre.lower()), TIPO_ACCION, f"area:{n}", "ir mostrar pestaña")
				for n, nombre in enumerate(self.AREAS)
			]
			for nombre, accion in (
				(_("Opciones de Centro de Mando"), "interfaz:opciones"),
				(_("Teclas globales de Centro de Mando"), "interfaz:teclas_globales"),
				(_("Reglas de ventanas"), "interfaz:reglas"),
				(_("Manual de Centro de Mando"), "interfaz:manual"),
			):
				acciones.append(Elemento(f"accion:{accion}", nombre, TIPO_ACCION, accion, "configuración ayuda"))
			self._catalogo_lanzador = CatalogoLanzador(acciones)
		return self._catalogo_lanzador

	def ejecutar_elemento_lanzador(self, elemento, destino: int = 0) -> None:
		from app.services.lanzador import TIPO_ACCION, TIPO_RESULTADO, ejecutar_destino

		usos = dict(self.config.obtener("lanzador.usos", {}))
		if elemento.tipo != TIPO_RESULTADO:
			usos[elemento.id] = int(usos.get(elemento.id, 0)) + 1
			self.config.establecer("lanzador.usos", usos)
		if elemento.tipo == TIPO_RESULTADO:
			self.copiar_texto(elemento.destino)
			self.hablar(_("Copiado {r}").format(r=elemento.destino), True)
		elif elemento.tipo == TIPO_ACCION:
			if elemento.destino.startswith("interfaz:"):
				wx.CallAfter(self._abrir_desde_lanzador, elemento.destino[9:])
			else:
				self.ejecutar(elemento.destino)
		elif not ejecutar_destino(elemento):
			self.avisar(_("No se pudo abrir {n}.").format(n=elemento.nombre))

	def _mostrar_area(self, indice: int) -> None:
		if self.ventana:
			self.ventana.restaurar()
			wx.CallAfter(self.ventana.mostrar_area, indice)

	def _abrir_desde_lanzador(self, orden: str) -> None:
		if self.ventana:
			self.ventana.restaurar()
			wx.CallAfter(getattr(self.ventana, f"_al_{orden}"), None)

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
