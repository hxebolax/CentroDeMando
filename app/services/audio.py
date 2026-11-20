"""Audio: dispositivos de salida, volumen general, micrófono y volumen por aplicación (sin wx).

Con pycaw (Core Audio de Windows sobre comtypes). Usar desde el hilo de la
interfaz o desde un hilo con COM inicializado: las llamadas son rápidas.

Cambiar el dispositivo predeterminado usa ``IPolicyConfig``, una interfaz no
documentada pero estable desde Windows 7 (la usan EarTrumpet y SoundSwitch).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Dispositivo:
	id: str
	nombre: str
	predeterminado: bool = False
	# Dispositivo de comunicaciones (llamadas: Teams, WhatsApp, Discord...).
	comunicaciones: bool = False

	def estado(self) -> str:
		"""«predeterminado», «comunicaciones», los dos o nada (lo que se ve en la lista)."""
		partes = []
		if self.predeterminado:
			partes.append("predeterminado")
		if self.comunicaciones:
			partes.append("comunicaciones")
		return " y ".join(partes)


@dataclass(frozen=True)
class Sesion:
	"""Una aplicación que tiene sonido abierto."""

	clave: str  # identificador estable de la sesión
	nombre: str
	pid: int
	volumen: int  # 0-100
	silenciada: bool
	dispositivo: str = ""  # id del dispositivo por el que suena


class ErrorAudio(Exception):
	"""Fallo de audio con mensaje para el usuario."""


def _pycaw():
	try:
		from pycaw.pycaw import DEVICE_STATE, AudioUtilities, EDataFlow, ERole
	except Exception as error:  # noqa: BLE001
		raise ErrorAudio(f"El audio no está disponible: {error}") from error
	return AudioUtilities, EDataFlow, ERole, DEVICE_STATE


def _id_predeterminado(flujo: int, comunicaciones: bool) -> str:
	utilidades, _flujos, roles, _estados = _pycaw()
	rol = roles.eCommunications.value if comunicaciones else roles.eMultimedia.value
	try:
		return utilidades.GetDeviceEnumerator().GetDefaultAudioEndpoint(flujo, rol).GetId()
	except Exception:  # noqa: BLE001 - no hay ninguno de ese tipo
		return ""


def _predeterminado(flujo: int):
	utilidades, _flujos, roles, _estados = _pycaw()
	enumerador = utilidades.GetDeviceEnumerator()
	try:
		dispositivo = enumerador.GetDefaultAudioEndpoint(flujo, roles.eMultimedia.value)
	except Exception as error:  # noqa: BLE001 - no hay ningún dispositivo de ese tipo
		raise ErrorAudio("No hay ningún dispositivo de audio de ese tipo.") from error
	return utilidades.CreateDevice(dispositivo)


def dispositivos_salida() -> list[Dispositivo]:
	utilidades, flujos, _roles, estados = _pycaw()
	actual = _id_predeterminado(flujos.eRender.value, False)
	llamadas = _id_predeterminado(flujos.eRender.value, True)
	return [
		Dispositivo(d.id, d.FriendlyName or d.id, d.id == actual, d.id == llamadas)
		for d in utilidades.GetAllDevices(flujos.eRender.value, estados.ACTIVE.value)
	]


def poner_comunicaciones(dispositivo: Dispositivo) -> None:
	"""Dispositivo SOLO para comunicaciones (llamadas); el predeterminado no cambia."""
	utilidades, _flujos, roles, _estados = _pycaw()
	try:
		utilidades.SetDefaultDevice(dispositivo.id, [roles.eCommunications])
	except Exception as error:  # noqa: BLE001
		log.warning("No se pudo cambiar el dispositivo de comunicaciones", exc_info=True)
		raise ErrorAudio("Windows no dejó cambiar el dispositivo de comunicaciones.") from error


def poner_predeterminado(dispositivo: Dispositivo) -> None:
	utilidades, _flujos, roles, _estados = _pycaw()
	try:
		utilidades.SetDefaultDevice(dispositivo.id, [roles.eConsole, roles.eMultimedia, roles.eCommunications])
	except Exception as error:  # noqa: BLE001
		log.warning("No se pudo cambiar el dispositivo predeterminado", exc_info=True)
		raise ErrorAudio("Windows no dejó cambiar el dispositivo de audio.") from error


def siguiente_salida() -> Dispositivo:
	"""Pasa al siguiente dispositivo de salida (cíclico) y lo devuelve."""
	lista = dispositivos_salida()
	if not lista:
		raise ErrorAudio("No hay dispositivos de salida.")
	actual = next((i for i, d in enumerate(lista) if d.predeterminado), -1)
	siguiente = lista[(actual + 1) % len(lista)]
	poner_predeterminado(siguiente)
	return siguiente


def _volumen_salida():
	_u, flujos, _r, _e = _pycaw()
	return _predeterminado(flujos.eRender.value).EndpointVolume


def volumen_general() -> tuple[int, bool]:
	volumen = _volumen_salida()
	return round(volumen.GetMasterVolumeLevelScalar() * 100), bool(volumen.GetMute())


def poner_volumen_general(porcentaje: int) -> int:
	porcentaje = min(max(int(porcentaje), 0), 100)
	_volumen_salida().SetMasterVolumeLevelScalar(porcentaje / 100, None)
	return porcentaje


def cambiar_volumen_general(paso: int) -> int:
	actual, _silencio = volumen_general()
	return poner_volumen_general(actual + paso)


def alternar_silencio_general() -> bool:
	volumen = _volumen_salida()
	nuevo = not bool(volumen.GetMute())
	volumen.SetMute(nuevo, None)
	return nuevo


def alternar_microfono() -> bool:
	"""Silencia o activa el micrófono predeterminado. Devuelve ``True`` si queda silenciado."""
	_u, flujos, _r, _e = _pycaw()
	volumen = _predeterminado(flujos.eCapture.value).EndpointVolume
	nuevo = not bool(volumen.GetMute())
	volumen.SetMute(nuevo, None)
	return nuevo


def _todas_las_sesiones():
	"""(id del dispositivo, AudioSession de pycaw) de todas las salidas activas.

	``AudioUtilities.GetAllSessions`` solo mira el dispositivo predeterminado: una
	aplicación que sonara por otro no aparecería.
	"""
	from comtypes import CLSCTX_ALL
	from pycaw.api.audiopolicy import IAudioSessionControl2, IAudioSessionManager2
	from pycaw.utils import AudioSession

	utilidades, flujos, _roles, estados = _pycaw()
	coleccion = utilidades.GetDeviceEnumerator().EnumAudioEndpoints(flujos.eRender.value, estados.ACTIVE.value)
	for indice in range(coleccion.GetCount()):
		dispositivo = coleccion.Item(indice)
		try:
			gestor = dispositivo.Activate(IAudioSessionManager2._iid_, CLSCTX_ALL, None).QueryInterface(IAudioSessionManager2)
			enumerador = gestor.GetSessionEnumerator()
			identificador = dispositivo.GetId()
		except Exception:  # noqa: BLE001 - dispositivo que se acaba de desconectar
			log.debug("Dispositivo de audio ilegible", exc_info=True)
			continue
		for posicion in range(enumerador.GetCount()):
			control = enumerador.GetSession(posicion)
			if control is not None:
				yield identificador, AudioSession(control.QueryInterface(IAudioSessionControl2))


def _clave(sesion) -> str:
	return str(sesion.InstanceIdentifier or sesion.Identifier or sesion.ProcessId)


def sesiones() -> list[Sesion]:
	"""Aplicaciones con sonido en cualquier salida (sin repetir la misma sesión)."""
	import psutil

	resultado: dict[str, Sesion] = {}
	for dispositivo, sesion in _todas_las_sesiones():
		try:
			proceso = sesion.Process
			nombre = proceso.name() if proceso else "Sonidos del sistema"
			simple = sesion.SimpleAudioVolume
			clave = _clave(sesion)
			resultado.setdefault(
				clave,
				Sesion(clave, nombre, int(sesion.ProcessId or 0), round(simple.GetMasterVolume() * 100), bool(simple.GetMute()), dispositivo),
			)
		except (psutil.Error, OSError, Exception):  # noqa: BLE001 - la aplicación pudo cerrarse
			log.debug("Sesión de audio ilegible", exc_info=True)
	return list(resultado.values())


def _sesion(clave: str):
	for _dispositivo, sesion in _todas_las_sesiones():
		if _clave(sesion) == clave:
			return sesion
	raise ErrorAudio("Esa aplicación ya no tiene sonido.")


def cambiar_volumen_sesion(clave: str, paso: int) -> int:
	simple = _sesion(clave).SimpleAudioVolume
	nuevo = min(max(round(simple.GetMasterVolume() * 100) + paso, 0), 100)
	simple.SetMasterVolume(nuevo / 100, None)
	return nuevo


def poner_volumen_sesion(clave: str, porcentaje: int) -> int:
	"""Pone el volumen de la aplicación (0-100) y lo devuelve."""
	porcentaje = min(max(int(porcentaje), 0), 100)
	_sesion(clave).SimpleAudioVolume.SetMasterVolume(porcentaje / 100, None)
	return porcentaje


def poner_silencio_sesion(clave: str, silenciar: bool) -> bool:
	_sesion(clave).SimpleAudioVolume.SetMute(bool(silenciar), None)
	return bool(silenciar)


def alternar_silencio_sesion(clave: str) -> bool:
	simple = _sesion(clave).SimpleAudioVolume
	nuevo = not bool(simple.GetMute())
	simple.SetMute(nuevo, None)
	return nuevo


# ── La aplicación enfocada ───────────────────────────────────────────────────


# Procesos que reproducen el sonido de la aplicación que los empotra.
AYUDANTES_WEB = {"msedgewebview2.exe", "cefsharp.browsersubprocess.exe", "qtwebengineprocess.exe"}


def _pid_real(hwnd: int) -> int:
	"""PID del programa de la ventana. Las apps de la Tienda se ven a través de
	ApplicationFrameHost: su proceso real es el de la ventana hija que contiene.
	"""
	import ctypes
	from ctypes import wintypes

	from app.services import ventanas_win32 as w32

	pid = w32.pid(hwnd)
	if w32.clase(hwnd) != "ApplicationFrameWindow":
		return pid
	encontrado = [pid]
	tipo = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

	def visitar(hijo, _parametro):
		otro = w32.pid(int(hijo))
		if otro and otro != pid:
			encontrado[0] = otro
			return False
		return True

	ctypes.windll.user32.EnumChildWindows(wintypes.HWND(hwnd), tipo(visitar), 0)
	return encontrado[0]


def sesiones_de_ventana(hwnd: int) -> list[Sesion]:
	"""Sesiones de audio del programa de esa ventana.

	Los navegadores y otros programas suenan desde procesos hijos (Firefox,
	Chrome, Edge...): se aceptan el mismo proceso, cualquier proceso con el
	mismo ejecutable y los descendientes que son motores web empotrados
	(WebView2, CEF, Qt WebEngine). Otros descendientes NO: todo lo que se abre
	desde el escritorio desciende del Explorador, y se le atribuiría su sonido.
	"""
	import psutil

	pid = _pid_real(hwnd)
	if not pid:
		return []
	try:
		proceso = psutil.Process(pid)
		nombre = proceso.name().casefold()
		ayudantes = set()
		for hijo in proceso.children(recursive=True):
			try:
				if hijo.name().casefold() in AYUDANTES_WEB:
					ayudantes.add(hijo.pid)
			except psutil.Error:
				continue
	except (psutil.NoSuchProcess, psutil.AccessDenied):
		return []
	return [s for s in sesiones() if s.pid == pid or s.pid in ayudantes or s.nombre.casefold() == nombre]


def _programa_de(hwnd: int) -> str:
	from app.services import ventanas_win32 as w32

	return w32.nombre_proceso(hwnd).removesuffix(".exe").removesuffix(".EXE") or "La aplicación"


def cambiar_volumen_ventana(hwnd: int, paso: int) -> str:
	"""Sube o baja el volumen de la aplicación de esa ventana; devuelve lo que se anuncia."""
	propias = sesiones_de_ventana(hwnd)
	if not propias:
		raise ErrorAudio(f"{_programa_de(hwnd)} no está reproduciendo sonido.")
	nuevo = 0
	for sesion in propias:
		nuevo = cambiar_volumen_sesion(sesion.clave, paso)
	return f"{_programa_de(hwnd)}: {nuevo} %"


def alternar_silencio_ventana(hwnd: int) -> str:
	propias = sesiones_de_ventana(hwnd)
	if not propias:
		raise ErrorAudio(f"{_programa_de(hwnd)} no está reproduciendo sonido.")
	# Todas sus sesiones quedan iguales: si alguna suena, se silencian todas.
	silenciar = any(not s.silenciada for s in propias)
	for sesion in propias:
		if sesion.silenciada != silenciar:
			alternar_silencio_sesion(sesion.clave)
	return f"{_programa_de(hwnd)} " + ("silenciada" if silenciar else "con sonido")


def siguiente_salida_de_ventana(hwnd: int) -> str:
	"""Pasa la aplicación de la ventana a la siguiente salida (la última vuelta deja la predeterminada)."""
	propias = [s for s in sesiones_de_ventana(hwnd) if s.pid]
	if not propias:
		raise ErrorAudio(f"{_programa_de(hwnd)} no está reproduciendo sonido.")
	salidas = dispositivos_salida()
	politica = _obtener_politica()
	actual = politica.leer(propias[0].pid) or ""
	opciones = ["", *(d.id for d in salidas)]
	siguiente = opciones[(opciones.index(actual) + 1) % len(opciones)] if actual in opciones else ""
	for pid in {s.pid for s in propias}:
		politica.poner(pid, siguiente)
	nombre = next((d.nombre for d in salidas if d.id == siguiente), "la salida predeterminada")
	return f"{_programa_de(hwnd)} suena por {nombre}"


def decir_volumen_ventana(hwnd: int) -> str:
	propias = sesiones_de_ventana(hwnd)
	if not propias:
		return f"{_programa_de(hwnd)} no está reproduciendo sonido."
	sesion = propias[0]
	return f"{_programa_de(hwnd)}: {sesion.volumen} %" + (", silenciada" if sesion.silenciada else "")



# ── Salida por aplicación (como el Mezclador de volumen de Windows) ──────────

_IID_POLITICA = ("ab3d4648-e242-459f-b02f-541c70306324", "2a59116d-6c4f-45e0-a74f-707e3fef9258")
_PREFIJO = "\\\\?\\SWD#MMDEVAPI#"
_SUFIJO_SALIDA = "#{e6327cad-dcec-4949-ae8a-991e976a79d2}"
_SIN_SESION = 0x80070057


class _PoliticaPorAplicacion:
	"""Interfaz no documentada ``IAudioPolicyConfigFactory`` (la usan EarTrumpet y SoundSwitch).

	Se pide con el IID de cada versión de Windows: si ninguno encaja, se
	rechaza con ``ErrorAudio`` en lugar de arriesgarse a llamar a una tabla de
	métodos equivocada (eso tumbaría el proceso). Usar siempre desde el hilo
	principal (COM inicializado por wx).
	"""

	def __init__(self) -> None:
		import ctypes
		import uuid

		self._ctypes = ctypes
		combase = ctypes.windll.combase
		combase.WindowsCreateString.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)]
		combase.WindowsDeleteString.argtypes = [ctypes.c_void_p]
		combase.WindowsGetStringRawBuffer.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
		combase.WindowsGetStringRawBuffer.restype = ctypes.c_wchar_p
		self._combase = combase

		class GUID(ctypes.Structure):
			_fields_ = [("a", ctypes.c_ulong), ("b", ctypes.c_ushort), ("c", ctypes.c_ushort), ("d", ctypes.c_ubyte * 8)]

		combase.RoGetActivationFactory.argtypes = [ctypes.c_void_p, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
		nombre = self._hstring("Windows.Media.Internal.AudioPolicyConfig")
		self._fabrica = ctypes.c_void_p()
		try:
			for iid in _IID_POLITICA:
				u = uuid.UUID(iid)
				guid = GUID(u.time_low, u.time_mid, u.time_hi_version, (ctypes.c_ubyte * 8)(*u.bytes[8:]))
				if combase.RoGetActivationFactory(nombre, ctypes.byref(guid), ctypes.byref(self._fabrica)) == 0:
					break
			else:
				raise ErrorAudio("Esta versión de Windows no permite elegir la salida de cada aplicación.")
		finally:
			combase.WindowsDeleteString(nombre)
		tabla = ctypes.cast(self._fabrica, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
		hresult = ctypes.c_long
		self._poner = ctypes.WINFUNCTYPE(hresult, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_int, ctypes.c_void_p)(tabla[25])
		self._leer = ctypes.WINFUNCTYPE(hresult, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p))(tabla[26])

	def _hstring(self, texto: str):
		manejador = self._ctypes.c_void_p()
		self._combase.WindowsCreateString(texto, len(texto), self._ctypes.byref(manejador))
		return manejador

	def leer(self, pid: int) -> str | None:
		"""Id del dispositivo asignado al proceso; "" = el predeterminado; ``None`` = sin sesión."""
		salida = self._ctypes.c_void_p()
		resultado = self._leer(self._fabrica, pid, 0, 1, self._ctypes.byref(salida)) & 0xFFFFFFFF
		if resultado == _SIN_SESION:
			return None
		if resultado:
			raise ErrorAudio(f"Windows no dio la salida de esa aplicación (código {resultado:#x}).")
		texto = self._combase.WindowsGetStringRawBuffer(salida, None) or ""
		self._combase.WindowsDeleteString(salida)
		return texto.removeprefix(_PREFIJO).removesuffix(_SUFIJO_SALIDA)

	def poner(self, pid: int, dispositivo: str) -> None:
		"""Asigna la salida (multimedia y consola, como EarTrumpet); ``""`` vuelve al predeterminado."""
		manejador = self._hstring(_PREFIJO + dispositivo + _SUFIJO_SALIDA) if dispositivo else None
		try:
			for rol in (1, 0):
				resultado = self._poner(self._fabrica, pid, 0, rol, manejador) & 0xFFFFFFFF
				if resultado == _SIN_SESION:
					raise ErrorAudio("Esa aplicación no tiene el sonido abierto ahora mismo.")
				if resultado:
					raise ErrorAudio(f"Windows no dejó cambiar la salida (código {resultado:#x}).")
		finally:
			if manejador:
				self._combase.WindowsDeleteString(manejador)


_politica: _PoliticaPorAplicacion | None = None


def _obtener_politica() -> _PoliticaPorAplicacion:
	global _politica
	if _politica is None:
		_politica = _PoliticaPorAplicacion()
	return _politica


def salida_de_sesion(sesion: Sesion) -> str:
	"""Nombre de la salida asignada a la aplicación o «predeterminada»."""
	try:
		asignada = _obtener_politica().leer(sesion.pid)
	except ErrorAudio:
		return ""
	if not asignada:
		return "predeterminada"
	return next((d.nombre for d in dispositivos_salida() if d.id == asignada), "otra")


def poner_salida_de_sesion(sesion: Sesion, dispositivo: Dispositivo | None) -> None:
	"""Hace que la aplicación suene por ``dispositivo`` (``None`` = la salida predeterminada)."""
	_obtener_politica().poner(sesion.pid, dispositivo.id if dispositivo else "")


# ── Entrada: micrófonos, su volumen y «Escuchar este dispositivo» ─────────────

# Propiedades de «Escuchar este dispositivo» (pestaña Escuchar de las propiedades
# del micrófono en el Panel de sonido). Comprobadas en Windows 11 26300:
# pid 0 = dispositivo por el que se oye (texto; si falta, el predeterminado),
# pid 1 = activado (sí/no).
_FMTID_ESCUCHA = "{24DBB0FC-9311-4B3D-9CF0-18FF155639D4}"
_PID_ESCUCHA_DESTINO = 0
_PID_ESCUCHA_ACTIVA = 1


def dispositivos_entrada() -> list[Dispositivo]:
	"""Micrófonos y entradas activos; ``predeterminado`` marca el de uso general."""
	utilidades, flujos, _roles, estados = _pycaw()
	actual = _id_predeterminado(flujos.eCapture.value, False)
	llamadas = _id_predeterminado(flujos.eCapture.value, True)
	return [
		Dispositivo(d.id, d.FriendlyName or d.id, d.id == actual, d.id == llamadas)
		for d in utilidades.GetAllDevices(flujos.eCapture.value, estados.ACTIVE.value)
	]


def nombres_conocidos(entrada: bool = False) -> list[str]:
	"""Nombres de todas las salidas (o entradas) que Windows conoce, conectadas o no.

	Primero las conectadas; sin repetir nombres (un monitor HDMI aparece varias veces).
	"""
	utilidades, flujos, _roles, estados = _pycaw()
	flujo = flujos.eCapture.value if entrada else flujos.eRender.value
	activos, resto = [], []
	for dispositivo in utilidades.GetAllDevices(flujo, estados.MASK_ALL.value):
		nombre = dispositivo.FriendlyName or ""
		estado = getattr(dispositivo.state, "value", dispositivo.state)
		(activos if estado == 1 else resto).append(nombre)
	vistos: set[str] = set()
	resultado = []
	for nombre in activos + sorted(resto, key=str.casefold):
		if nombre and nombre.casefold() not in vistos:
			vistos.add(nombre.casefold())
			resultado.append(nombre)
	return resultado


def silenciar_salvo_lectores() -> list[str]:
	"""Silencia todas las aplicaciones con sonido menos los lectores de pantalla.

	Devuelve las claves de las que silenció (las que ya lo estaban no se tocan),
	para devolverles el sonido después con ``quitar_silencio``.
	"""
	silenciadas = []
	for sesion in sesiones():
		if sesion.silenciada or not sesion.pid or sesion.nombre.casefold() in LECTORES:
			continue
		try:
			_sesion(sesion.clave).SimpleAudioVolume.SetMute(True, None)
			silenciadas.append(sesion.clave)
		except ErrorAudio:
			continue
	return silenciadas


def quitar_silencio(claves: list[str]) -> int:
	"""Devuelve el sonido a las aplicaciones de ``claves`` que sigan abiertas."""
	devueltas = 0
	for clave in claves:
		try:
			_sesion(clave).SimpleAudioVolume.SetMute(False, None)
			devueltas += 1
		except ErrorAudio:
			continue
	return devueltas


# ── Quién usa el micrófono o la cámara ───────────────────────────────────────

_CONSENTIMIENTOS = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore"


def nombre_de_consentimiento(subclave: str) -> str:
	"""Nombre legible de una entrada del registro de permisos (función pura).

	«C:#Program Files#Zoom#bin#Zoom.exe» → «Zoom»;
	«MSTeams_8wekyb3d8bbwe» → «MSTeams».
	"""
	if "#" in subclave:
		ultimo = subclave.rsplit("#", 1)[-1]
		return ultimo[:-4] if ultimo.casefold().endswith(".exe") else ultimo
	return subclave.split("_", 1)[0].rsplit(".", 1)[-1]


def apps_usando(capacidad: str = "microphone") -> list[str]:
	"""Aplicaciones que están usando ahora el micrófono (o ``"webcam"``, la cámara).

	Windows apunta en el registro de cada usuario cuándo empezó y terminó cada
	aplicación de usarlo: si terminó vale 0, lo está usando. Es lo mismo que
	enseña el icono de privacidad de la barra de tareas.
	"""
	try:
		import winreg
	except ImportError:
		return []
	resultado: list[str] = []

	def recorrer(ruta: str) -> None:
		try:
			clave = winreg.OpenKey(winreg.HKEY_CURRENT_USER, ruta)
		except OSError:
			return
		with clave:
			indice = 0
			while True:
				try:
					sub = winreg.EnumKey(clave, indice)
				except OSError:
					break
				indice += 1
				if sub == "NonPackaged":
					recorrer(ruta + "\\" + sub)
					continue
				try:
					with winreg.OpenKey(clave, sub) as app:
						inicio, _t = winreg.QueryValueEx(app, "LastUsedTimeStart")
						fin, _t = winreg.QueryValueEx(app, "LastUsedTimeStop")
				except OSError:
					continue
				if inicio and not fin:
					nombre = nombre_de_consentimiento(sub)
					if nombre not in resultado:
						resultado.append(nombre)

	recorrer(_CONSENTIMIENTOS + "\\" + capacidad)
	return resultado


def _volumen_de(identificador: str | None, flujo_si_falta: str = "captura"):
	"""``IAudioEndpointVolume`` del dispositivo con ese id (o del predeterminado)."""
	utilidades, flujos, _r, _e = _pycaw()
	if not identificador:
		flujo = flujos.eCapture.value if flujo_si_falta == "captura" else flujos.eRender.value
		return _predeterminado(flujo).EndpointVolume
	from comtypes import CLSCTX_ALL
	from pycaw.api.endpointvolume import IAudioEndpointVolume

	try:
		dispositivo = utilidades.GetDeviceEnumerator().GetDevice(identificador)
		interfaz = dispositivo.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
		return interfaz.QueryInterface(IAudioEndpointVolume)
	except Exception as error:  # noqa: BLE001 - desconectado entre medias
		raise ErrorAudio("Ese dispositivo ya no está disponible.") from error


def volumen_entrada(identificador: str | None = None) -> tuple[int, bool]:
	"""(volumen 0-100, silenciado) del micrófono ``identificador`` o del predeterminado."""
	volumen = _volumen_de(identificador)
	return round(volumen.GetMasterVolumeLevelScalar() * 100), bool(volumen.GetMute())


def poner_volumen_entrada(porcentaje: int, identificador: str | None = None) -> int:
	porcentaje = min(max(int(porcentaje), 0), 100)
	_volumen_de(identificador).SetMasterVolumeLevelScalar(porcentaje / 100, None)
	return porcentaje


def cambiar_volumen_entrada(paso: int, identificador: str | None = None) -> int:
	actual, _silencio = volumen_entrada(identificador)
	return poner_volumen_entrada(actual + paso, identificador)


def poner_silencio_entrada(silenciar: bool, identificador: str | None = None) -> bool:
	_volumen_de(identificador).SetMute(bool(silenciar), None)
	return bool(silenciar)


def poner_silencio_general(silenciar: bool) -> bool:
	_volumen_salida().SetMute(bool(silenciar), None)
	return bool(silenciar)


def calcular_balance(izquierdo: float, derecho: float) -> int:
	"""Balance de -100 (todo a la izquierda) a 100 (todo a la derecha); 0 = centrado (función pura)."""
	mayor = max(izquierdo, derecho)
	if mayor <= 0:
		return 0
	return round((derecho - izquierdo) / mayor * 100)


def canales_para_balance(balance: int, volumen: float) -> tuple[float, float]:
	"""Niveles (izquierdo, derecho) de 0 a 1 que dan ese balance sin cambiar el volumen (función pura).

	El canal hacia el que se inclina queda al volumen general; el otro baja.
	"""
	balance = min(max(int(balance), -100), 100)
	volumen = min(max(float(volumen), 0.0), 1.0)
	izquierdo = volumen * (1 - balance / 100) if balance > 0 else volumen
	derecho = volumen * (1 + balance / 100) if balance < 0 else volumen
	return izquierdo, derecho


# Canales izquierdo y derecho según el orden estándar de Windows
# (delantero izq., delantero der., centro, graves, trasero izq., trasero der., lateral izq., lateral der.).
CANALES_LADOS = {
	2: ((0,), (1,)),
	4: ((0, 2), (1, 3)),
	6: ((0, 4), (1, 5)),
	8: ((0, 4, 6), (1, 5, 7)),
}


def balance_general() -> int | None:
	"""Balance de la salida predeterminada, o ``None`` si su número de canales no lo permite."""
	volumen = _volumen_salida()
	lados = CANALES_LADOS.get(volumen.GetChannelCount())
	if lados is None:
		return None
	izquierdo = max(volumen.GetChannelVolumeLevelScalar(c) for c in lados[0])
	derecho = max(volumen.GetChannelVolumeLevelScalar(c) for c in lados[1])
	return calcular_balance(izquierdo, derecho)


def poner_balance_general(balance: int) -> int:
	"""Inclina el sonido a la izquierda (negativo) o a la derecha (positivo), como Niveles, Balance de Windows."""
	volumen = _volumen_salida()
	lados = CANALES_LADOS.get(volumen.GetChannelCount())
	if lados is None:
		raise ErrorAudio("Esta salida no tiene canal izquierdo y derecho: su balance no se puede cambiar.")
	izquierdo, derecho = canales_para_balance(balance, volumen.GetMasterVolumeLevelScalar())
	for canal in lados[0]:
		volumen.SetChannelVolumeLevelScalar(canal, izquierdo, None)
	for canal in lados[1]:
		volumen.SetChannelVolumeLevelScalar(canal, derecho, None)
	return min(max(int(balance), -100), 100)


def describir_balance(balance: int) -> str:
	"""«Centrado», «20 a la izquierda», «100 a la derecha» (función pura)."""
	if balance == 0:
		return "Centrado"
	return f"{abs(balance)} a la " + ("izquierda" if balance < 0 else "derecha")


def nombre_entrada_predeterminada() -> str:
	return next((d.nombre for d in dispositivos_entrada() if d.predeterminado), "sin micrófono")


def alternar_escucha_predeterminada() -> str:
	"""Activa o desactiva «Escuchar este dispositivo» del micrófono predeterminado."""
	micro = next((d for d in dispositivos_entrada() if d.predeterminado), None)
	if micro is None:
		raise ErrorAudio("No hay ningún micrófono.")
	activa, _destino = leer_escucha(micro.id)
	poner_escucha(micro.id, not activa)
	return ("Se oye " if not activa else "Ya no se oye ") + micro.nombre


def poner_predeterminado_entrada(dispositivo: Dispositivo) -> None:
	"""Micrófono predeterminado para todo (consola, multimedia y comunicaciones)."""
	poner_predeterminado(dispositivo)


def _politica_clasica():
	"""``IPolicyConfig`` (no documentada, estable desde Windows 7) con la firma completa.

	La que trae pycaw omite el parámetro ``bFxStore`` de Get/SetPropertyValue:
	llamarla así pasaría los argumentos corridos. Aquí se declara bien (los
	ocho primeros métodos no se usan; solo cuentan para el orden de la tabla).
	"""
	import ctypes
	from ctypes import HRESULT, POINTER
	from ctypes.wintypes import BOOL, LPCWSTR

	import comtypes
	from comtypes import COMMETHOD, GUID, IUnknown
	from pycaw.api.mmdeviceapi import PROPERTYKEY
	from pycaw.api.mmdeviceapi.depend import PROPVARIANT

	global _IPolicyConfigCompleta
	if _IPolicyConfigCompleta is None:

		class IPolicyConfigCompleta(IUnknown):
			_case_insensitive_ = True
			_iid_ = GUID("{f8679f50-850a-41cf-9c72-430f290290c8}")
			_methods_ = (
				*(COMMETHOD([], HRESULT, f"SinUso{n}") for n in range(8)),
				COMMETHOD(
					[],
					HRESULT,
					"GetPropertyValue",
					(["in"], LPCWSTR, "dispositivo"),
					(["in"], BOOL, "almacenEfectos"),
					(["in"], POINTER(PROPERTYKEY), "clave"),
					(["in"], POINTER(PROPVARIANT), "valor"),
				),
				COMMETHOD(
					[],
					HRESULT,
					"SetPropertyValue",
					(["in"], LPCWSTR, "dispositivo"),
					(["in"], BOOL, "almacenEfectos"),
					(["in"], POINTER(PROPERTYKEY), "clave"),
					(["in"], POINTER(PROPVARIANT), "valor"),
				),
			)

		_IPolicyConfigCompleta = IPolicyConfigCompleta
	clsid = GUID("{870af99c-171d-4f9e-af0d-e63df40c2bc9}")  # CPolicyConfigClient
	try:
		return comtypes.CoCreateInstance(clsid, _IPolicyConfigCompleta, comtypes.CLSCTX_ALL), ctypes, PROPERTYKEY, PROPVARIANT, GUID
	except Exception as error:  # noqa: BLE001
		raise ErrorAudio("Esta versión de Windows no deja cambiar esa opción del dispositivo.") from error


_IPolicyConfigCompleta = None


def _clave_escucha(PROPERTYKEY, GUID, pid: int):  # noqa: N803 - tipos de pycaw
	clave = PROPERTYKEY()
	clave.fmtid = GUID(_FMTID_ESCUCHA)
	clave.pid = pid
	return clave


def leer_escucha(identificador: str) -> tuple[bool, str]:
	"""(activada, id del dispositivo por el que se oye o "" = el predeterminado)."""
	utilidades, _f, _r, _e = _pycaw()
	try:
		dispositivo = utilidades.CreateDevice(utilidades.GetDeviceEnumerator().GetDevice(identificador))
		propiedades = {str(k).upper(): v for k, v in (dispositivo.properties or {}).items()}
	except Exception as error:  # noqa: BLE001
		raise ErrorAudio("No se pudo leer ese micrófono.") from error
	activa = propiedades.get(f"{_FMTID_ESCUCHA} {_PID_ESCUCHA_ACTIVA}")
	destino = propiedades.get(f"{_FMTID_ESCUCHA} {_PID_ESCUCHA_DESTINO}")
	return activa is True, destino if isinstance(destino, str) else ""


def poner_escucha(identificador: str, activar: bool, destino: str | None = None) -> None:
	"""Activa o desactiva «Escuchar este dispositivo» del micrófono ``identificador``.

	``destino``: id de la salida por la que se oye; ``""`` = la predeterminada;
	``None`` = no cambiarla. Windows aplica el cambio al momento (como al
	pulsar Aplicar en el Panel de sonido) y lo recuerda.
	"""
	from comtypes.automation import VT_BOOL, VT_LPWSTR

	politica, ctypes, PROPERTYKEY, PROPVARIANT, GUID = _politica_clasica()  # noqa: N806
	try:
		if destino is not None:
			valor = PROPVARIANT()
			if destino:
				valor.vt = VT_LPWSTR
				texto = ctypes.create_unicode_buffer(destino)
				valor.union.pwszVal = ctypes.cast(texto, ctypes.c_wchar_p)
			else:
				valor.vt = 0  # VT_EMPTY: vuelve a la salida predeterminada
			politica.SetPropertyValue(identificador, False, ctypes.byref(_clave_escucha(PROPERTYKEY, GUID, _PID_ESCUCHA_DESTINO)), ctypes.byref(valor))
		valor = PROPVARIANT()
		valor.vt = VT_BOOL
		valor.union.boolVal = -1 if activar else 0  # VARIANT_TRUE = -1
		politica.SetPropertyValue(identificador, False, ctypes.byref(_clave_escucha(PROPERTYKEY, GUID, _PID_ESCUCHA_ACTIVA)), ctypes.byref(valor))
	except ErrorAudio:
		raise
	except Exception as error:  # noqa: BLE001
		log.warning("No se pudo cambiar «Escuchar este dispositivo»", exc_info=True)
		if (getattr(error, "hresult", 0) & 0xFFFFFFFF) == 0x80070005:
			raise ErrorAudio("Windows no dio permiso para cambiar «Escuchar este dispositivo».") from error
		raise ErrorAudio("Windows no dejó cambiar «Escuchar este dispositivo».") from error
	# Se comprueba leyendo: algunas versiones aceptan la llamada sin aplicarla.
	if leer_escucha(identificador)[0] != bool(activar):
		raise ErrorAudio("Windows no aplicó «Escuchar este dispositivo».")


# ── Solo esta aplicación ─────────────────────────────────────────────────────

# Nunca se silencian los lectores de pantalla: el usuario se quedaría sin voz.
LECTORES = {"nvda.exe", "nvda_slave.exe", "jfw.exe", "narrator.exe", "zdsrv.exe", "zt.exe", "sapisvr.exe"}
_silenciadas_por_solo: list[str] = []


def solo_esta_aplicacion(hwnd: int) -> str:
	"""Silencia todo salvo el programa de la ventana (y el lector); la segunda vez lo restaura."""
	global _silenciadas_por_solo
	if _silenciadas_por_solo:
		for clave in _silenciadas_por_solo:
			try:
				simple = _sesion(clave).SimpleAudioVolume
				simple.SetMute(False, None)
			except ErrorAudio:
				continue
		_silenciadas_por_solo = []
		return "Vuelven a sonar todas las aplicaciones"
	propias = {s.clave for s in sesiones_de_ventana(hwnd)}
	if not propias:
		raise ErrorAudio(f"{_programa_de(hwnd)} no está reproduciendo sonido.")
	return solo_estas(propias, _programa_de(hwnd))


def solo_estas(propias: set[str], nombre: str) -> str:
	"""Silencia todas las sesiones salvo ``propias`` y los lectores de pantalla."""
	global _silenciadas_por_solo
	if _silenciadas_por_solo:
		return solo_esta_aplicacion(0)
	for sesion in sesiones():
		if sesion.clave in propias or sesion.silenciada or sesion.nombre.casefold() in LECTORES or not sesion.pid:
			continue
		try:
			_sesion(sesion.clave).SimpleAudioVolume.SetMute(True, None)
			_silenciadas_por_solo.append(sesion.clave)
		except ErrorAudio:
			continue
	return f"Solo suena {nombre}. Repita la orden para volver a oír las demás."


# ── Avisos de dispositivos conectados y desconectados ────────────────────────


# Factor de forma de un punto de audio (PKEY_AudioEndpoint_FormFactor).
_CLAVE_FACTOR_FORMA = "{1da5d803-d492-4edd-8c23-e0c0ffee7f0e} 0"
FACTOR_PANTALLA = 9  # DigitalAudioDisplayDevice: el audio de un monitor o televisor por HDMI o DisplayPort
ESTADO_ACTIVO = 1


@dataclass
class PuntoAudio:
	"""Un punto de audio de Windows (una salida o una entrada)."""

	nombre: str
	activo: bool
	pantalla: bool = False


def resumir_por_nombre(puntos: dict[str, PuntoAudio], con_pantallas: bool) -> dict[str, bool]:
	"""{nombre: conectado} agrupando los puntos que comparten nombre (función pura).

	Un monitor ASUS por HDMI aparece como dos o tres puntos con el mismo
	nombre; Windows activa uno y desactiva otro al despertar la pantalla. Para
	la persona es UN dispositivo: está conectado si alguno de sus puntos lo está.
	"""
	resumen: dict[str, bool] = {}
	for punto in puntos.values():
		if not punto.nombre or (punto.pantalla and not con_pantallas):
			continue
		resumen[punto.nombre] = resumen.get(punto.nombre, False) or punto.activo
	return resumen


def cambios_de_conexion(antes: dict[str, bool], ahora: dict[str, bool]) -> list[str]:
	"""Avisos «Conectado: X» / «Desconectado: Y» entre dos resúmenes (función pura)."""
	avisos = []
	for nombre in sorted(set(antes) | set(ahora)):
		previo, actual = antes.get(nombre, False), ahora.get(nombre, False)
		if actual and not previo:
			avisos.append(f"Conectado: {nombre}")
		elif previo and not actual:
			avisos.append(f"Desconectado: {nombre}")
	return avisos


class VigilanteDispositivos:
	"""Avisa con ``al_cambiar(texto)`` al conectar o desconectar un dispositivo de audio.

	- Windows llama desde sus propios hilos: ``al_cambiar`` debe pasar a la
	  interfaz con ``wx.CallAfter``. Los dispositivos Bluetooth llegan como
	  cambios de estado, no como «añadido».
	- Los avisos se agrupan por NOMBRE y se dan cuando los cambios se calman
	  (``espera`` segundos sin novedades): un dispositivo que se desconecta y
	  se vuelve a conectar enseguida no dice nada, y uno con varios puntos
	  (monitores HDMI, cascos con micrófono) avisa una sola vez.
	- Las pantallas (audio por HDMI o DisplayPort) solo avisan si
	  ``con_pantallas()`` lo pide: al reposar y despertar el monitor Windows las
	  desconecta y conecta sin que nadie haya tocado nada.
	"""

	def __init__(self, al_cambiar, con_pantallas=None, espera: float = 2.5, al_estabilizar=None) -> None:
		import threading

		self._al_cambiar = al_cambiar
		# Se llama (desde el hilo del temporizador) cada vez que algo se conectó o
		# desconectó de verdad: para pasar al dispositivo preferido.
		self._al_estabilizar = al_estabilizar
		self._con_pantallas = con_pantallas or (lambda: False)
		self._espera = espera
		self._enumerador = None
		self._cliente = None
		self._puntos: dict[str, PuntoAudio] = {}
		self._anunciado: dict[str, bool] = {}
		self._candado = threading.Lock()
		self._temporizador = None

	def _leer_puntos(self) -> dict[str, PuntoAudio]:
		utilidades, flujos, _roles, estados = _pycaw()
		puntos = {}
		for dispositivo in utilidades.GetAllDevices(flujos.eAll.value, estados.MASK_ALL.value):
			factor = None
			try:
				factor = next((v for k, v in (dispositivo.properties or {}).items() if str(k).lower() == _CLAVE_FACTOR_FORMA), None)
			except Exception:  # noqa: BLE001 - propiedades ilegibles: se trata como dispositivo normal
				factor = None
			estado = getattr(dispositivo.state, "value", dispositivo.state)
			puntos[dispositivo.id] = PuntoAudio(dispositivo.FriendlyName or "", estado == ESTADO_ACTIVO, factor == FACTOR_PANTALLA)
		return puntos

	def iniciar(self) -> None:
		from pycaw.callbacks import MMNotificationClient

		utilidades, _flujos, _roles, _estados = _pycaw()
		self._puntos = self._leer_puntos()
		# Lo que hay al arrancar no se anuncia: es el punto de partida.
		self._anunciado = resumir_por_nombre(self._puntos, True)
		vigilante = self

		class Cliente(MMNotificationClient):
			def on_device_state_changed(self, device_id, new_state, new_state_id):
				vigilante._estado(device_id, new_state_id)

			def on_device_added(self, added_device_id):
				vigilante._estado(added_device_id, None)

			def on_device_removed(self, removed_device_id):
				vigilante._estado(removed_device_id, 0)

		self._cliente = Cliente()
		self._enumerador = utilidades.GetDeviceEnumerator()
		self._enumerador.RegisterEndpointNotificationCallback(self._cliente)

	def _estado(self, identificador: str, estado: int | None) -> None:
		"""Anota el cambio y espera a que se calme antes de avisar."""
		import threading

		log.debug("Audio: el punto %s pasa al estado %s", identificador, estado)
		with self._candado:
			punto = self._puntos.get(identificador)
			if punto is None or estado is None:
				self._pendiente_releer = True
			else:
				punto.activo = estado == ESTADO_ACTIVO
			if self._temporizador is not None:
				self._temporizador.cancel()
			self._temporizador = threading.Timer(self._espera, self._evaluar)
			self._temporizador.daemon = True
			self._temporizador.name = "avisos-audio"
			self._temporizador.start()

	def _evaluar(self) -> None:
		"""Compara con lo último anunciado y avisa de lo que de verdad cambió."""
		try:
			if getattr(self, "_pendiente_releer", False):
				self._pendiente_releer = False
				try:
					puntos = self._leer_puntos()
				except Exception:  # noqa: BLE001
					log.debug("No se pudo releer la lista de dispositivos de audio", exc_info=True)
				else:
					with self._candado:
						self._puntos = puntos
			with self._candado:
				todos = resumir_por_nombre(self._puntos, True)
				pantallas = {p.nombre for p in self._puntos.values() if p.pantalla}
				avisos = cambios_de_conexion(self._anunciado, todos)
				self._anunciado = todos
			if avisos and self._al_estabilizar is not None:
				self._al_estabilizar()
			if not self._con_pantallas():
				avisos = [a for a in avisos if a.split(": ", 1)[1] not in pantallas]
			for aviso in avisos:
				log.info("Audio: %s", aviso)
			if avisos:
				self._al_cambiar(". ".join(avisos))
		except Exception:  # noqa: BLE001
			log.exception("Error al avisar de un cambio de dispositivo")

	def detener(self) -> None:
		if self._temporizador is not None:
			self._temporizador.cancel()
			self._temporizador = None
		if self._enumerador is not None and self._cliente is not None:
			try:
				self._enumerador.UnregisterEndpointNotificationCallback(self._cliente)
			except Exception:  # noqa: BLE001
				log.debug("No se pudo quitar el aviso de dispositivos", exc_info=True)
		self._enumerador = self._cliente = None
