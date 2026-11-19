"""Funciones Win32 sobre ventanas (sin wx): título, programa, foco y cierre.

Se usan desde el hilo de escritorios y desde la interfaz. Todas toleran que la
ventana ya no exista (devuelven valores vacíos o ``False``): entre que se
enumera una ventana y se consulta, el usuario puede haberla cerrado.
"""

from __future__ import annotations

import ctypes
import logging
import os
from ctypes import wintypes

log = logging.getLogger(__name__)

_ES_WINDOWS = os.name == "nt"

if _ES_WINDOWS:
	_user32 = ctypes.WinDLL("user32", use_last_error=True)
	_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

	_user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
	_user32.GetWindowTextLengthW.restype = ctypes.c_int
	_user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
	_user32.GetWindowTextW.restype = ctypes.c_int
	_user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
	_user32.GetWindowThreadProcessId.restype = wintypes.DWORD
	_user32.IsWindow.argtypes = [wintypes.HWND]
	_user32.IsWindow.restype = wintypes.BOOL
	_user32.IsIconic.argtypes = [wintypes.HWND]
	_user32.IsIconic.restype = wintypes.BOOL
	_user32.GetForegroundWindow.restype = wintypes.HWND
	_user32.SetForegroundWindow.argtypes = [wintypes.HWND]
	_user32.SetForegroundWindow.restype = wintypes.BOOL
	_user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
	_user32.ShowWindow.restype = wintypes.BOOL
	_user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
	_user32.PostMessageW.restype = wintypes.BOOL
	_user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
	_user32.GetAncestor.restype = wintypes.HWND
	_user32.AllowSetForegroundWindow.argtypes = [wintypes.DWORD]
	_user32.AllowSetForegroundWindow.restype = wintypes.BOOL
	_user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
	_user32.FindWindowW.restype = wintypes.HWND
	_user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
	_user32.GetClassNameW.restype = ctypes.c_int
	_kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
	_kernel32.OpenProcess.restype = wintypes.HANDLE
	_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
	_kernel32.CloseHandle.restype = wintypes.BOOL
	_kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
	_kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
WM_CLOSE = 0x0010
SW_RESTORE = 9
GA_ROOT = 2
ASFW_ANY = 0xFFFFFFFF


def titulo(hwnd: int) -> str:
	"""Título de la ventana o cadena vacía."""
	if not _ES_WINDOWS or not hwnd:
		return ""
	longitud = _user32.GetWindowTextLengthW(hwnd)
	if longitud <= 0:
		return ""
	bufer = ctypes.create_unicode_buffer(longitud + 1)
	_user32.GetWindowTextW(hwnd, bufer, longitud + 1)
	return bufer.value


def clase(hwnd: int) -> str:
	"""Nombre de clase Win32 de la ventana."""
	if not _ES_WINDOWS or not hwnd:
		return ""
	bufer = ctypes.create_unicode_buffer(256)
	_user32.GetClassNameW(hwnd, bufer, 256)
	return bufer.value


def pid(hwnd: int) -> int:
	"""Identificador del proceso dueño de la ventana (0 si no existe)."""
	if not _ES_WINDOWS or not hwnd:
		return 0
	valor = wintypes.DWORD(0)
	_user32.GetWindowThreadProcessId(hwnd, ctypes.byref(valor))
	return int(valor.value)


def ruta_proceso(hwnd: int) -> str:
	"""Ruta completa del ejecutable dueño de la ventana, o cadena vacía.

	Con ``PROCESS_QUERY_LIMITED_INFORMATION`` basta incluso para procesos de
	otro usuario o elevados en la mayoría de los casos; si se deniega, se
	devuelve vacío y la ventana se muestra sin programa.
	"""
	identificador = pid(hwnd)
	if not identificador:
		return ""
	manejador = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, identificador)
	if not manejador:
		return ""
	try:
		tamano = wintypes.DWORD(1024)
		bufer = ctypes.create_unicode_buffer(tamano.value)
		if _kernel32.QueryFullProcessImageNameW(manejador, 0, bufer, ctypes.byref(tamano)):
			return bufer.value
		return ""
	finally:
		_kernel32.CloseHandle(manejador)


def nombre_proceso(hwnd: int) -> str:
	"""Nombre del ejecutable (``notepad.exe``) o cadena vacía."""
	return os.path.basename(ruta_proceso(hwnd))


def existe(hwnd: int) -> bool:
	return bool(_ES_WINDOWS and hwnd and _user32.IsWindow(hwnd))


def ventana_activa() -> int:
	"""La ventana de primer plano, subida hasta su raíz (no un control hijo)."""
	if not _ES_WINDOWS:
		return 0
	hwnd = _user32.GetForegroundWindow() or 0
	if hwnd:
		raiz = _user32.GetAncestor(hwnd, GA_ROOT)
		if raiz:
			hwnd = raiz
	return int(hwnd or 0)


def permitir_primer_plano() -> None:
	"""Deja que cualquier proceso tome el primer plano (lo pide el cambio de escritorio).

	Sin esto, tras cambiar de escritorio el foco a veces se queda en la barra de
	tareas o en una ventana del escritorio anterior.
	"""
	if _ES_WINDOWS:
		_user32.AllowSetForegroundWindow(ASFW_ANY)


def activar(hwnd: int) -> bool:
	"""Trae la ventana al frente y le da el foco (la restaura si está minimizada)."""
	if not existe(hwnd):
		return False
	if _user32.IsIconic(hwnd):
		_user32.ShowWindow(hwnd, SW_RESTORE)
	permitir_primer_plano()
	return bool(_user32.SetForegroundWindow(hwnd))


def cerrar(hwnd: int) -> bool:
	"""Pide a la ventana que se cierre (como Alt+F4; el programa puede preguntar)."""
	if not existe(hwnd):
		return False
	return bool(_user32.PostMessageW(hwnd, WM_CLOSE, 0, 0))


def ventana_del_escritorio() -> int:
	"""La ventana del fondo de escritorio (iconos), para darle el foco si no hay otra."""
	if not _ES_WINDOWS:
		return 0
	return int(_user32.FindWindowW("Progman", None) or 0)


def forzar_primer_plano(hwnd: int) -> bool:
	"""Pone ``hwnd`` delante aunque Windows no quiera (ventanas abiertas desde una tecla global).

	Windows solo deja tomar el primer plano al proceso que recibió la última
	entrada. Si ``SetForegroundWindow`` no basta, se enlaza un momento la cola
	de entrada de nuestro hilo con la del hilo que tiene el primer plano (técnica
	habitual de los lanzadores) y se vuelve a intentar.
	"""
	if not existe(hwnd):
		return False
	activar(hwnd)
	if _user32.GetForegroundWindow() == hwnd:
		return True
	delante = _user32.GetForegroundWindow()
	hilo_delante = _user32.GetWindowThreadProcessId(delante, None) if delante else 0
	propio = _kernel32.GetCurrentThreadId()
	enlazado = bool(hilo_delante and hilo_delante != propio and _user32.AttachThreadInput(propio, hilo_delante, True))
	try:
		_user32.BringWindowToTop(hwnd)
		_user32.SetForegroundWindow(hwnd)
	finally:
		if enlazado:
			_user32.AttachThreadInput(propio, hilo_delante, False)
	return _user32.GetForegroundWindow() == hwnd


if _ES_WINDOWS:
	_user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
	_user32.AttachThreadInput.restype = wintypes.BOOL
	_user32.BringWindowToTop.argtypes = [wintypes.HWND]
	_user32.BringWindowToTop.restype = wintypes.BOOL
	_kernel32.GetCurrentThreadId.restype = wintypes.DWORD
