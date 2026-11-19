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


@dataclass(frozen=True)
class Sesion:
	"""Una aplicación que tiene sonido abierto."""

	clave: str  # identificador estable de la sesión
	nombre: str
	pid: int
	volumen: int  # 0-100
	silenciada: bool


class ErrorAudio(Exception):
	"""Fallo de audio con mensaje para el usuario."""


def _pycaw():
	try:
		from pycaw.pycaw import DEVICE_STATE, AudioUtilities, EDataFlow, ERole
	except Exception as error:  # noqa: BLE001
		raise ErrorAudio(f"El audio no está disponible: {error}") from error
	return AudioUtilities, EDataFlow, ERole, DEVICE_STATE


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
	try:
		actual = _predeterminado(flujos.eRender.value).id
	except ErrorAudio:
		actual = ""
	return [
		Dispositivo(d.id, d.FriendlyName or d.id, d.id == actual)
		for d in utilidades.GetAllDevices(flujos.eRender.value, estados.ACTIVE.value)
	]


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


def sesiones() -> list[Sesion]:
	utilidades, _f, _r, _e = _pycaw()
	resultado = []
	for sesion in utilidades.GetAllSessions():
		try:
			proceso = sesion.Process
			nombre = proceso.name() if proceso else "Sonidos del sistema"
			simple = sesion.SimpleAudioVolume
			resultado.append(
				Sesion(
					clave=str(sesion.InstanceIdentifier or sesion.Identifier or sesion.ProcessId),
					nombre=nombre,
					pid=int(sesion.ProcessId or 0),
					volumen=round(simple.GetMasterVolume() * 100),
					silenciada=bool(simple.GetMute()),
				)
			)
		except Exception:  # noqa: BLE001 - la aplicación pudo cerrarse
			log.debug("Sesión de audio ilegible", exc_info=True)
	return resultado


def _sesion(clave: str):
	utilidades, _f, _r, _e = _pycaw()
	for sesion in utilidades.GetAllSessions():
		if str(sesion.InstanceIdentifier or sesion.Identifier or sesion.ProcessId) == clave:
			return sesion
	raise ErrorAudio("Esa aplicación ya no tiene sonido.")


def cambiar_volumen_sesion(clave: str, paso: int) -> int:
	simple = _sesion(clave).SimpleAudioVolume
	nuevo = min(max(round(simple.GetMasterVolume() * 100) + paso, 0), 100)
	simple.SetMasterVolume(nuevo / 100, None)
	return nuevo


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


def decir_volumen_ventana(hwnd: int) -> str:
	propias = sesiones_de_ventana(hwnd)
	if not propias:
		return f"{_programa_de(hwnd)} no está reproduciendo sonido."
	sesion = propias[0]
	return f"{_programa_de(hwnd)}: {sesion.volumen} %" + (", silenciada" if sesion.silenciada else "")
