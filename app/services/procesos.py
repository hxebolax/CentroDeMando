"""Ventanas abiertas y procesos (sin wx).

- Ventanas: las de primer nivel visibles y con título (las de Alt+Tab, más o
  menos), de todos los escritorios. Estado: minimizada, maximizada, siempre
  encima y si «no responde» (``IsHungAppWindow``).
- Acciones: activar, minimizar, maximizar, restaurar, siempre encima, cerrar
  (como Alt+F4) y finalizar el programa.
- Procesos: nombre, PID, procesador y memoria con psutil. El uso de procesador
  se calcula entre dos lecturas: la primera vez sale 0.
"""

from __future__ import annotations

import ctypes
import logging
import os
import subprocess
import threading
from ctypes import wintypes
from dataclasses import dataclass

from app.services import ventanas_win32 as w32

log = logging.getLogger(__name__)

GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x0001, 0x0002, 0x0010
SW_MINIMIZE, SW_MAXIMIZE, SW_RESTORE = 6, 3, 9
GW_OWNER = 4

if os.name == "nt":
	_user32 = ctypes.WinDLL("user32", use_last_error=True)
	_PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
	_user32.EnumWindows.argtypes = [_PROC, wintypes.LPARAM]
	_user32.IsWindowVisible.argtypes = [wintypes.HWND]
	_user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
	_user32.GetWindowLongW.restype = ctypes.c_long
	_user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
	_user32.GetWindow.restype = wintypes.HWND
	_user32.IsHungAppWindow.argtypes = [wintypes.HWND]
	_user32.IsIconic.argtypes = [wintypes.HWND]
	_user32.IsZoomed.argtypes = [wintypes.HWND]
	_user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
	_user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]


@dataclass(frozen=True)
class Ventana:
	hwnd: int
	titulo: str
	proceso: str
	pid: int
	minimizada: bool = False
	maximizada: bool = False
	encima: bool = False
	no_responde: bool = False

	def estado(self) -> str:
		partes = ["minimizada" if self.minimizada else "maximizada" if self.maximizada else "normal"]
		if self.encima:
			partes.append("siempre encima")
		if self.no_responde:
			partes.append("no responde")
		return ", ".join(partes)


@dataclass(frozen=True)
class Proceso:
	pid: int
	nombre: str
	cpu: float
	memoria_mb: float
	ruta: str = ""


def ventanas(excluir_pid: int = 0, incluir_encubiertas: bool = True) -> list[Ventana]:
	"""Ventanas de primer nivel visibles, con título y sin dueño (las que se ven en Alt+Tab)."""
	if os.name != "nt":
		return []
	resultado: list[Ventana] = []

	def visitar(hwnd, _parametro) -> bool:
		try:
			if not _user32.IsWindowVisible(hwnd) or _user32.GetWindow(hwnd, GW_OWNER):
				return True
			estilo = _user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
			if estilo & WS_EX_TOOLWINDOW:
				return True
			titulo = w32.titulo(hwnd)
			if not titulo or w32.clase(hwnd) in ("Progman", "Shell_TrayWnd", "Windows.UI.Core.CoreWindow"):
				return True
			pid = w32.pid(hwnd)
			if excluir_pid and pid == excluir_pid:
				return True
			resultado.append(
				Ventana(
					int(hwnd),
					titulo,
					w32.nombre_proceso(hwnd),
					pid,
					bool(_user32.IsIconic(hwnd)),
					bool(_user32.IsZoomed(hwnd)),
					bool(estilo & WS_EX_TOPMOST),
					bool(_user32.IsHungAppWindow(hwnd)),
				)
			)
		except Exception:  # noqa: BLE001 - una ventana cerrándose no debe cortar la enumeración
			log.debug("Ventana ilegible", exc_info=True)
		return True

	_user32.EnumWindows(_PROC(visitar), 0)
	return resultado


def minimizar(hwnd: int) -> None:
	_user32.ShowWindow(hwnd, SW_MINIMIZE)


def maximizar(hwnd: int) -> None:
	_user32.ShowWindow(hwnd, SW_MAXIMIZE)


def restaurar(hwnd: int) -> None:
	_user32.ShowWindow(hwnd, SW_RESTORE)


def poner_encima(hwnd: int, encima: bool) -> bool:
	return bool(
		_user32.SetWindowPos(hwnd, HWND_TOPMOST if encima else HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
	)


def esta_encima(hwnd: int) -> bool:
	return bool(_user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOPMOST)


def finalizar(pid: int, espera: float = 3.0) -> bool:
	"""Pide terminar el proceso; si no termina a tiempo, lo mata. Devuelve si ya no existe."""
	import psutil

	try:
		proceso = psutil.Process(pid)
		proceso.terminate()
		try:
			proceso.wait(espera)
		except psutil.TimeoutExpired:
			proceso.kill()
			proceso.wait(espera)
		return True
	except psutil.NoSuchProcess:
		return True
	except (psutil.AccessDenied, psutil.TimeoutExpired):
		log.warning("No se pudo finalizar el proceso %s", pid, exc_info=True)
		return False


def ruta_de(pid: int) -> str:
	"""Ruta del ejecutable (se pide solo para el proceso elegido: leerla para todos es lento)."""
	import psutil

	try:
		return psutil.Process(pid).exe()
	except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
		return ""


def abrir_ubicacion(ruta: str) -> None:
	"""Abre el Explorador con el ejecutable seleccionado."""
	if ruta:
		subprocess.Popen(["explorer.exe", "/select,", ruta], close_fds=True)  # noqa: S603, S607


class _MEMORIA(ctypes.Structure):
	_fields_ = [
		("cb", wintypes.DWORD),
		("PageFaultCount", wintypes.DWORD),
		("PeakWorkingSetSize", ctypes.c_size_t),
		("WorkingSetSize", ctypes.c_size_t),
		("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
		("QuotaPagedPoolUsage", ctypes.c_size_t),
		("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
		("QuotaNonPagedPoolUsage", ctypes.c_size_t),
		("PagefileUsage", ctypes.c_size_t),
		("PeakPagefileUsage", ctypes.c_size_t),
	]


def _tiempos_y_memoria(pid: int) -> tuple[float, float] | None:
	"""Segundos de procesador usados y MB en memoria, o ``None`` si no hay acceso.

	Directo a la API de Windows: psutil, ante un proceso protegido, recorre
	TODOS los procesos otra vez para cada uno, y la lista tardaba 2 segundos.
	"""
	kernel32 = ctypes.windll.kernel32
	manejador = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
	if not manejador:
		return None
	try:
		creacion, salida, nucleo, usuario = (wintypes.FILETIME() for _i in range(4))
		if not kernel32.GetProcessTimes(manejador, ctypes.byref(creacion), ctypes.byref(salida), ctypes.byref(nucleo), ctypes.byref(usuario)):
			return None
		segundos = sum((t.dwHighDateTime << 32 | t.dwLowDateTime) for t in (nucleo, usuario)) / 1e7
		memoria = _MEMORIA()
		memoria.cb = ctypes.sizeof(memoria)
		mb = memoria.WorkingSetSize / 1048576 if ctypes.windll.psapi.GetProcessMemoryInfo(manejador, ctypes.byref(memoria), memoria.cb) else 0.0
		return segundos, mb
	finally:
		kernel32.CloseHandle(manejador)


class MonitorProcesos:
	"""Lee los procesos y calcula el uso de procesador entre dos lecturas."""

	def __init__(self) -> None:
		self._anterior: dict[int, tuple[str, float]] = {}
		self._instante = 0.0
		self._candado = threading.Lock()
		self._nucleos = os.cpu_count() or 1

	def leer(self) -> list[Proceso]:
		"""Procesos accesibles (los protegidos del sistema se omiten)."""
		import time

		import psutil

		with self._candado:
			ahora = time.monotonic()
			transcurrido = ahora - self._instante if self._instante else 0.0
			actual: dict[int, tuple[str, float]] = {}
			resultado = []
			for proceso in psutil.process_iter(["pid", "name"]):
				pid, nombre = proceso.info["pid"], proceso.info.get("name") or ""
				if pid in (0, 4):
					continue
				datos = _tiempos_y_memoria(pid)
				if datos is None:
					continue
				segundos, mb = datos
				actual[pid] = (nombre, segundos)
				previo = self._anterior.get(pid)
				cpu = 0.0
				if previo and previo[0] == nombre and transcurrido > 0:
					cpu = max(0.0, (segundos - previo[1]) / transcurrido / self._nucleos * 100)
				resultado.append(Proceso(pid, nombre or str(pid), round(cpu, 1), round(mb, 1)))
			self._anterior = actual
			self._instante = ahora
		return resultado
