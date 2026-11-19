"""Portapapeles de Windows con ctypes (sin wx): leer, escribir y escuchar cambios.

Formatos que se guardan y se restauran:

- Texto Unicode (``CF_UNICODETEXT``).
- HTML (``HTML Format``), junto al texto: al pegar en Word o en un correo se
  conserva el formato.
- Archivos (``CF_HDROP``): copiar archivos en el Explorador y pegarlos luego.
- Imágenes (``CF_DIB``): mapa de bits independiente del dispositivo.

Privacidad: los gestores de contraseñas marcan lo que copian con formatos
especiales para que ningún historial lo guarde. Se respetan los tres que usa
Windows: «ExcludeClipboardContentFromMonitorProcessing», «Clipboard Viewer
Ignore» y «CanIncludeInClipboardHistory» con valor 0.

Escuchar cambios: ``MonitorPortapapeles`` crea una ventana solo de mensajes
(``HWND_MESSAGE``) en su propio hilo y se registra con
``AddClipboardFormatListener``; Windows le avisa con ``WM_CLIPBOARDUPDATE``.
Esa misma ventana es la dueña del portapapeles cuando escribimos (Windows
exige un dueño para que ``SetClipboardData`` funcione tras vaciarlo).
"""

from __future__ import annotations

import ctypes
import hashlib
import logging
import os
import struct
import threading
import time
from collections.abc import Callable
from ctypes import wintypes
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

CF_UNICODETEXT = 13
CF_HDROP = 15
CF_DIB = 8
GMEM_MOVEABLE = 0x0002
WM_CLIPBOARDUPDATE = 0x031D
WM_CLOSE = 0x0010
WM_DESTROY = 0x0002
HWND_MESSAGE = wintypes.HWND(-3)

TIPO_TEXTO = "texto"
TIPO_ARCHIVOS = "archivos"
TIPO_IMAGEN = "imagen"


@dataclass
class Contenido:
	"""Lo que hay (o se quiere poner) en el portapapeles."""

	tipo: str = TIPO_TEXTO
	texto: str = ""
	html: bytes = b""
	archivos: list[str] = field(default_factory=list)
	imagen: bytes = b""  # DIB: BITMAPINFOHEADER + píxeles
	origen: str = ""  # programa que lo copió

	@property
	def vacio(self) -> bool:
		return not (self.texto or self.archivos or self.imagen)

	def huella(self) -> str:
		"""Identificador del contenido para no guardar dos veces lo mismo."""
		resumen = hashlib.sha1()
		resumen.update(self.tipo.encode())
		if self.tipo == TIPO_ARCHIVOS:
			resumen.update("\n".join(self.archivos).encode("utf-8", "surrogatepass"))
		elif self.tipo == TIPO_IMAGEN:
			resumen.update(self.imagen)
		else:
			resumen.update(self.texto.encode("utf-8", "surrogatepass"))
		return resumen.hexdigest()


def dimensiones_dib(datos: bytes) -> tuple[int, int]:
	"""Ancho y alto de una imagen DIB (0, 0 si no se entiende)."""
	if len(datos) < 12:
		return 0, 0
	tamano = struct.unpack_from("<I", datos, 0)[0]
	if tamano == 12:  # BITMAPCOREHEADER
		ancho, alto = struct.unpack_from("<HH", datos, 4)
	else:
		ancho, alto = struct.unpack_from("<ii", datos, 4)
	return abs(int(ancho)), abs(int(alto))


def dib_a_bmp(datos: bytes) -> bytes:
	"""Antepone la cabecera de archivo BMP para poder guardar la imagen como .bmp."""
	tamano_cabecera = struct.unpack_from("<I", datos, 0)[0] if len(datos) >= 4 else 40
	colores = 0
	if tamano_cabecera >= 40 and len(datos) >= 40:
		bits = struct.unpack_from("<H", datos, 14)[0]
		compresion = struct.unpack_from("<I", datos, 16)[0]
		usados = struct.unpack_from("<I", datos, 32)[0]
		if bits <= 8:
			colores = (usados or (1 << bits)) * 4
		elif compresion == 3 and tamano_cabecera == 40:  # BI_BITFIELDS: tres máscaras tras la cabecera
			colores = 12
	desplazamiento = 14 + tamano_cabecera + colores
	return struct.pack("<2sIHHI", b"BM", 14 + len(datos), 0, 0, desplazamiento) + datos


if os.name == "nt":
	_user32 = ctypes.WinDLL("user32", use_last_error=True)
	_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
	_shell32 = ctypes.WinDLL("shell32", use_last_error=True)
	LRESULT = ctypes.c_ssize_t
	_WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

	class _WNDCLASSW(ctypes.Structure):
		_fields_ = [
			("style", wintypes.UINT),
			("lpfnWndProc", _WNDPROC),
			("cbClsExtra", ctypes.c_int),
			("cbWndExtra", ctypes.c_int),
			("hInstance", wintypes.HINSTANCE),
			("hIcon", wintypes.HICON),
			("hCursor", wintypes.HANDLE),
			("hbrBackground", wintypes.HBRUSH),
			("lpszMenuName", wintypes.LPCWSTR),
			("lpszClassName", wintypes.LPCWSTR),
		]

	_firmas = {
		"OpenClipboard": ([wintypes.HWND], wintypes.BOOL),
		"CloseClipboard": ([], wintypes.BOOL),
		"EmptyClipboard": ([], wintypes.BOOL),
		"GetClipboardData": ([wintypes.UINT], wintypes.HANDLE),
		"SetClipboardData": ([wintypes.UINT, wintypes.HANDLE], wintypes.HANDLE),
		"IsClipboardFormatAvailable": ([wintypes.UINT], wintypes.BOOL),
		"RegisterClipboardFormatW": ([wintypes.LPCWSTR], wintypes.UINT),
		"GetClipboardSequenceNumber": ([], wintypes.DWORD),
		"GetClipboardOwner": ([], wintypes.HWND),
		"AddClipboardFormatListener": ([wintypes.HWND], wintypes.BOOL),
		"RemoveClipboardFormatListener": ([wintypes.HWND], wintypes.BOOL),
		"RegisterClassW": ([ctypes.POINTER(_WNDCLASSW)], wintypes.ATOM),
		"CreateWindowExW": (
			[wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
			 wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID],
			wintypes.HWND,
		),
		"DestroyWindow": ([wintypes.HWND], wintypes.BOOL),
		"DefWindowProcW": ([wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM], LRESULT),
		"GetMessageW": ([ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT], wintypes.BOOL),
		"TranslateMessage": ([ctypes.POINTER(wintypes.MSG)], wintypes.BOOL),
		"DispatchMessageW": ([ctypes.POINTER(wintypes.MSG)], LRESULT),
		"PostMessageW": ([wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM], wintypes.BOOL),
		"PostQuitMessage": ([ctypes.c_int], None),
	}
	for _nombre, (_argumentos, _resultado) in _firmas.items():
		_funcion = getattr(_user32, _nombre)
		_funcion.argtypes = _argumentos
		_funcion.restype = _resultado
	_kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
	_kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
	_kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
	_kernel32.GlobalLock.restype = wintypes.LPVOID
	_kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
	_kernel32.GlobalUnlock.restype = wintypes.BOOL
	_kernel32.GlobalSize.argtypes = [wintypes.HGLOBAL]
	_kernel32.GlobalSize.restype = ctypes.c_size_t
	_kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
	_kernel32.GlobalFree.restype = wintypes.HGLOBAL
	_kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
	_kernel32.GetModuleHandleW.restype = wintypes.HMODULE
	_shell32.DragQueryFileW.argtypes = [wintypes.HANDLE, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]
	_shell32.DragQueryFileW.restype = wintypes.UINT

	CF_HTML = _user32.RegisterClipboardFormatW("HTML Format")
	CF_EXCLUIR = _user32.RegisterClipboardFormatW("ExcludeClipboardContentFromMonitorProcessing")
	CF_IGNORAR_VISOR = _user32.RegisterClipboardFormatW("Clipboard Viewer Ignore")
	CF_PERMITIR_HISTORIAL = _user32.RegisterClipboardFormatW("CanIncludeInClipboardHistory")
else:  # pragma: no cover - solo Windows
	CF_HTML = CF_EXCLUIR = CF_IGNORAR_VISOR = CF_PERMITIR_HISTORIAL = 0


class PortapapelesOcupado(Exception):
	"""Otro programa tiene abierto el portapapeles."""


class _Abierto:
	"""``with _Abierto(dueno):`` abre el portapapeles con reintentos y lo cierra siempre."""

	def __init__(self, dueno: int = 0, intentos: int = 10, espera: float = 0.03) -> None:
		self._dueno = dueno
		self._intentos = intentos
		self._espera = espera

	def __enter__(self) -> _Abierto:
		for _intento in range(self._intentos):
			if _user32.OpenClipboard(self._dueno or None):
				return self
			time.sleep(self._espera)
		raise PortapapelesOcupado("Otro programa está usando el portapapeles.")

	def __exit__(self, *_error: object) -> None:
		_user32.CloseClipboard()


def numero_secuencia() -> int:
	return int(_user32.GetClipboardSequenceNumber()) if os.name == "nt" else 0


def _leer_bloque(formato: int) -> bytes | None:
	"""Bytes del formato pedido (el portapapeles ya debe estar abierto)."""
	if not formato or not _user32.IsClipboardFormatAvailable(formato):
		return None
	manejador = _user32.GetClipboardData(formato)
	if not manejador:
		return None
	puntero = _kernel32.GlobalLock(manejador)
	if not puntero:
		return None
	try:
		return ctypes.string_at(puntero, _kernel32.GlobalSize(manejador))
	finally:
		_kernel32.GlobalUnlock(manejador)


def es_privado() -> bool:
	"""El contenido actual pide no guardarse en historiales (contraseñas, por ejemplo)."""
	if os.name != "nt":
		return False
	if _user32.IsClipboardFormatAvailable(CF_EXCLUIR) or _user32.IsClipboardFormatAvailable(CF_IGNORAR_VISOR):
		return True
	if _user32.IsClipboardFormatAvailable(CF_PERMITIR_HISTORIAL):
		try:
			with _Abierto():
				valor = _leer_bloque(CF_PERMITIR_HISTORIAL)
		except PortapapelesOcupado:
			return False
		if valor and len(valor) >= 4 and struct.unpack_from("<I", valor)[0] == 0:
			return True
	return False


def leer(con_html: bool = True, con_archivos: bool = True, con_imagenes: bool = True, maximo_imagen: int = 0) -> Contenido | None:
	"""Lee el portapapeles. ``None`` si está vacío o solo tiene formatos que no se guardan.

	Prioridad: archivos, luego imagen y luego texto (con su HTML si lo hay),
	como hace el Explorador al pegar.
	"""
	if os.name != "nt":
		return None
	with _Abierto():
		if con_archivos and _user32.IsClipboardFormatAvailable(CF_HDROP):
			manejador = _user32.GetClipboardData(CF_HDROP)
			if manejador:
				cuantos = _shell32.DragQueryFileW(manejador, 0xFFFFFFFF, None, 0)
				archivos = []
				for indice in range(cuantos):
					longitud = _shell32.DragQueryFileW(manejador, indice, None, 0)
					bufer = ctypes.create_unicode_buffer(longitud + 1)
					_shell32.DragQueryFileW(manejador, indice, bufer, longitud + 1)
					archivos.append(bufer.value)
				if archivos:
					return Contenido(TIPO_ARCHIVOS, texto="\n".join(archivos), archivos=archivos)
		bruto = _leer_bloque(CF_UNICODETEXT)
		texto = bruto.decode("utf-16-le", "replace").split("\x00", 1)[0] if bruto else ""
		if con_imagenes and not texto and _user32.IsClipboardFormatAvailable(CF_DIB):
			imagen = _leer_bloque(CF_DIB) or b""
			if imagen and (not maximo_imagen or len(imagen) <= maximo_imagen):
				return Contenido(TIPO_IMAGEN, imagen=imagen)
			if imagen:
				log.info("Imagen de %d bytes descartada por superar el máximo.", len(imagen))
			return None
		if not texto:
			return None
		html = b""
		if con_html:
			html = (_leer_bloque(CF_HTML) or b"").split(b"\x00", 1)[0]
		return Contenido(TIPO_TEXTO, texto=texto, html=html)


def _poner(formato: int, datos: bytes) -> None:
	memoria = _kernel32.GlobalAlloc(GMEM_MOVEABLE, max(len(datos), 1))
	if not memoria:
		raise MemoryError("No hay memoria para el portapapeles")
	puntero = _kernel32.GlobalLock(memoria)
	ctypes.memmove(puntero, datos, len(datos))
	_kernel32.GlobalUnlock(memoria)
	if not _user32.SetClipboardData(formato, memoria):
		_kernel32.GlobalFree(memoria)
		raise OSError(ctypes.get_last_error(), "SetClipboardData falló")
	# Desde aquí la memoria es del sistema: no se libera.


def _dropfiles(archivos: list[str]) -> bytes:
	"""Estructura DROPFILES (20 bytes) + rutas UTF-16 terminadas en doble nulo."""
	cabecera = struct.pack("<IiiII", 20, 0, 0, 0, 1)
	rutas = ("\x00".join(archivos) + "\x00\x00").encode("utf-16-le")
	return cabecera + rutas


def escribir(contenido: Contenido, dueno: int) -> int:
	"""Pone el contenido en el portapapeles. Devuelve el número de secuencia resultante.

	El número sirve para que el monitor reconozca esta copia como propia.
	"""
	if os.name != "nt":
		return 0
	with _Abierto(dueno):
		_user32.EmptyClipboard()
		if contenido.tipo == TIPO_ARCHIVOS and contenido.archivos:
			_poner(CF_HDROP, _dropfiles(contenido.archivos))
		elif contenido.tipo == TIPO_IMAGEN and contenido.imagen:
			_poner(CF_DIB, contenido.imagen)
		else:
			_poner(CF_UNICODETEXT, (contenido.texto + "\x00").encode("utf-16-le", "surrogatepass"))
			if contenido.html:
				_poner(CF_HTML, contenido.html + b"\x00")
	return numero_secuencia()


def nombre_programa_dueno() -> str:
	"""Programa que puso el contenido actual (el dueño del portapapeles)."""
	if os.name != "nt":
		return ""
	from app.services import ventanas_win32 as w32

	dueno = _user32.GetClipboardOwner()
	return w32.nombre_proceso(int(dueno)) if dueno else ""


class MonitorPortapapeles:
	"""Hilo con una ventana solo de mensajes que recibe ``WM_CLIPBOARDUPDATE``.

	``al_cambiar()`` se llama desde ESTE hilo en cada cambio; debe ser rápido o
	encolar el trabajo.
	"""

	CLASE = "CentroDeMandoPortapapeles"

	def __init__(self, al_cambiar: Callable[[], None]) -> None:
		self._al_cambiar = al_cambiar
		self._hilo: threading.Thread | None = None
		self._listo = threading.Event()
		self.hwnd = 0
		self._proc = None

	def iniciar(self) -> None:
		if os.name != "nt" or (self._hilo and self._hilo.is_alive()):
			return
		self._listo.clear()
		self._hilo = threading.Thread(target=self._bucle, name="portapapeles", daemon=True)
		self._hilo.start()
		self._listo.wait(3)

	def detener(self) -> None:
		if self.hwnd:
			_user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
		if self._hilo:
			self._hilo.join(timeout=3)
		self._hilo = None

	def _procedimiento(self, hwnd: int, mensaje: int, wparam: int, lparam: int) -> int:
		if mensaje == WM_CLIPBOARDUPDATE:
			try:
				self._al_cambiar()
			except Exception:  # noqa: BLE001 - un fallo no debe parar el monitor
				log.exception("Error al atender un cambio del portapapeles")
			return 0
		if mensaje == WM_CLOSE:
			_user32.RemoveClipboardFormatListener(hwnd)
			_user32.DestroyWindow(hwnd)
			return 0
		if mensaje == WM_DESTROY:
			_user32.PostQuitMessage(0)
			return 0
		return _user32.DefWindowProcW(hwnd, mensaje, wparam, lparam)

	def _bucle(self) -> None:
		instancia = _kernel32.GetModuleHandleW(None)
		self._proc = _WNDPROC(self._procedimiento)
		clase = _WNDCLASSW()
		clase.lpfnWndProc = self._proc
		clase.hInstance = instancia
		clase.lpszClassName = f"{self.CLASE}{id(self)}"
		if not _user32.RegisterClassW(ctypes.byref(clase)):
			log.error("No se pudo registrar la clase de ventana del portapapeles (error %s).", ctypes.get_last_error())
			self._listo.set()
			return
		self.hwnd = int(_user32.CreateWindowExW(0, clase.lpszClassName, "Portapapeles", 0, 0, 0, 0, 0, HWND_MESSAGE, None, instancia, None) or 0)
		if not self.hwnd or not _user32.AddClipboardFormatListener(self.hwnd):
			log.error("No se pudo escuchar el portapapeles (error %s).", ctypes.get_last_error())
			self._listo.set()
			return
		log.info("Escuchando los cambios del portapapeles.")
		self._listo.set()
		mensaje = wintypes.MSG()
		while _user32.GetMessageW(ctypes.byref(mensaje), None, 0, 0) > 0:
			_user32.TranslateMessage(ctypes.byref(mensaje))
			_user32.DispatchMessageW(ctypes.byref(mensaje))
		self.hwnd = 0
		log.info("Monitor del portapapeles detenido.")
