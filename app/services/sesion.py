"""Estado de la sesión de Windows: ¿está bloqueado el equipo? (sin wx).

Se consulta con ``WTSQuerySessionInformationW(WTSSessionInfoEx)``: el campo
``SessionFlags`` vale 0 (bloqueada) o 1 (desbloqueada) desde Windows 8 (en
Windows 7 estaba al revés, pero el programa exige Windows 10 u 11). Se usa
sondeando cada pocos segundos: más sencillo y robusto que recibir el mensaje
``WM_WTSSESSION_CHANGE`` en la ventana.
"""

from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes

log = logging.getLogger(__name__)

_WTS_SESION_ACTUAL = 0xFFFFFFFF
_WTS_INFO_EX = 25
_BLOQUEADA, _DESBLOQUEADA = 0, 1
# WTSINFOEXW: Level (DWORD) y, alineada a 8 bytes, la unión con WTSINFOEX_LEVEL1_W
# (SessionId, SessionState, SessionFlags...).
_DESPLAZAMIENTO_FLAGS = 16


def sesion_bloqueada() -> bool | None:
	"""``True`` si el equipo está bloqueado, ``False`` si no, ``None`` si no se sabe."""
	try:
		wtsapi = ctypes.windll.wtsapi32
	except (AttributeError, OSError):
		return None
	memoria = ctypes.c_void_p()
	tamano = wintypes.DWORD()
	if not wtsapi.WTSQuerySessionInformationW(None, wintypes.DWORD(_WTS_SESION_ACTUAL), _WTS_INFO_EX, ctypes.byref(memoria), ctypes.byref(tamano)):
		return None
	try:
		if tamano.value < _DESPLAZAMIENTO_FLAGS + 4 or ctypes.c_uint32.from_address(memoria.value).value != 1:
			return None
		banderas = ctypes.c_int32.from_address(memoria.value + _DESPLAZAMIENTO_FLAGS).value
	finally:
		wtsapi.WTSFreeMemory(memoria)
	if banderas == _BLOQUEADA:
		return True
	if banderas == _DESBLOQUEADA:
		return False
	return None
