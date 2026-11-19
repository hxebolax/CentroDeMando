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
