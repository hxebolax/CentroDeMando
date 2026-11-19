"""Teclas globales (funcionan aunque la aplicación no tenga el foco), sin wx.

Dos mecanismos, ambos en un hilo propio con su bucle de mensajes de Windows:

1. ``RegisterHotKey`` para los atajos configurables. Es el método oficial:
   Windows avisa con ``WM_HOTKEY`` y nunca ralentiza el teclado. Si otro
   programa ya usa la combinación, el registro falla y se informa de cuál.
2. Un gancho de teclado de bajo nivel (``WH_KEYBOARD_LL``), OPCIONAL y
   desactivado de serie, que intercepta Ctrl+Windows+Izquierda/Derecha de
   Windows para que también sean cíclicos. ``RegisterHotKey`` no puede con
   ellas porque el Explorador ya las tiene registradas.

Por qué un hilo propio y no ``wx.Window.RegisterHotKey``: las pulsaciones se
atienden aunque la ventana esté ocupada o un diálogo modal esté abierto, y la
acción se encola directamente en el hilo de escritorios: el cambio es
inmediato.

Las combinaciones se escriben en español: «Ctrl+Alt+Win+Derecha».
"""

from __future__ import annotations

import builtins
import ctypes
import logging
import os
import threading
from collections.abc import Callable
from ctypes import wintypes
from dataclasses import dataclass

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

# Orden canónico de los modificadores al escribir una combinación.
MODIFICADORES: list[tuple[int, str, tuple[str, ...]]] = [
	(MOD_CONTROL, "Ctrl", ("ctrl", "control", "ctl")),
	(MOD_ALT, "Alt", ("alt",)),
	(MOD_SHIFT, "Mayús", ("mayús", "mayus", "shift", "mayúsculas", "mayusculas")),
	(MOD_WIN, "Win", ("win", "windows", "super", "meta")),
]


def _tabla_teclas() -> dict[str, int]:
	"""Nombre visible en español → código de tecla virtual (VK)."""
	tabla: dict[str, int] = {}
	for codigo in range(ord("A"), ord("Z") + 1):
		tabla[chr(codigo)] = codigo
	for cifra in range(10):
		tabla[str(cifra)] = 0x30 + cifra
	for numero in range(1, 25):
		tabla[f"F{numero}"] = 0x6F + numero
	tabla.update(
		{
			"Izquierda": 0x25,
			"Arriba": 0x26,
			"Derecha": 0x27,
			"Abajo": 0x28,
			"Inicio": 0x24,
			"Fin": 0x23,
			"RePág": 0x21,
			"AvPág": 0x22,
			"Insertar": 0x2D,
			"Suprimir": 0x2E,
			"Retroceso": 0x08,
			"Intro": 0x0D,
			"Espacio": 0x20,
			"Tabulador": 0x09,
			"Pausa": 0x13,
			"Coma": 0xBC,
			"Punto": 0xBE,
			"Menos": 0xBD,
			"Más": 0xBB,
		}
	)
	for cifra in range(10):
		tabla[f"Num {cifra}"] = 0x60 + cifra
	tabla.update({"Num *": 0x6A, "Num +": 0x6B, "Num -": 0x6D, "Num /": 0x6F, "Num .": 0x6E})
	return tabla


TECLAS: dict[str, int] = _tabla_teclas()
_NOMBRE_DE_VK: dict[int, str] = {vk: nombre for nombre, vk in TECLAS.items()}
_SINONIMOS = {
	"left": "Izquierda",
	"right": "Derecha",
	"up": "Arriba",
	"down": "Abajo",
	"home": "Inicio",
	"end": "Fin",
	"pageup": "RePág",
	"repag": "RePág",
	"pagedown": "AvPág",
	"avpag": "AvPág",
	"insert": "Insertar",
	"ins": "Insertar",
	"delete": "Suprimir",
	"supr": "Suprimir",
	"del": "Suprimir",
	"backspace": "Retroceso",
	"back": "Retroceso",
	"enter": "Intro",
	"return": "Intro",
	"space": "Espacio",
	"tab": "Tabulador",
	"pause": "Pausa",
}
_NOMBRE_NORMALIZADO = {nombre.casefold(): nombre for nombre in TECLAS}
_NOMBRE_NORMALIZADO.update({clave: valor for clave, valor in _SINONIMOS.items()})


@dataclass(frozen=True)
class Combinacion:
	"""Modificadores (``MOD_*``) y tecla virtual."""

	modificadores: int
	vk: int

	def __str__(self) -> str:
		return formatear(self.modificadores, self.vk)

	@property
	def valida(self) -> bool:
		"""Una tecla global sin modificadores robaría la tecla a todos los programas."""
		return bool(self.vk and self.modificadores & (MOD_CONTROL | MOD_ALT | MOD_WIN))


def formatear(modificadores: int, vk: int) -> str:
	"""«Ctrl+Alt+Win+Derecha» a partir de modificadores y tecla."""
	partes = [nombre for bandera, nombre, _alias in MODIFICADORES if modificadores & bandera]
	partes.append(_NOMBRE_DE_VK.get(vk, f"VK {vk:#04x}"))
	return "+".join(partes)


def analizar(texto: str) -> Combinacion | None:
	"""Convierte «ctrl+alt+win+derecha» en una ``Combinacion``; ``None`` si no se entiende.

	Acepta los nombres en español o en inglés y cualquier orden y mayúsculas.
	«Num +» y «Más» se distinguen porque el signo de suma suelto no separa.
	"""
	texto = (texto or "").strip()
	if not texto:
		return None
	# «Num +» contiene el separador: se protege antes de partir.
	protegido = texto.replace("Num +", "Num \x00").replace("num +", "Num \x00")
	partes = [p.strip().replace("\x00", "+") for p in protegido.split("+") if p.strip()]
	if not partes:
		return None
	modificadores = 0
	for parte in partes[:-1]:
		bandera = next((b for b, _n, alias in MODIFICADORES if parte.casefold() in alias), None)
		if bandera is None:
			return None
		modificadores |= bandera
	nombre = _NOMBRE_NORMALIZADO.get(partes[-1].casefold())
	if nombre is None:
		return None
	return Combinacion(modificadores, TECLAS[nombre])


def normalizar(texto: str) -> str:
	"""Devuelve la forma canónica o cadena vacía si no es válida."""
	combinacion = analizar(texto)
	return str(combinacion) if combinacion else ""


# ── Hilo de teclas ───────────────────────────────────────────────────────────

WM_HOTKEY = 0x0312
WM_APP = 0x8000
WM_QUIT = 0x0012
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WH_KEYBOARD_LL = 13
LLKHF_INJECTED = 0x10
VK_LEFT, VK_RIGHT = 0x25, 0x27
VK_CONTROL, VK_MENU, VK_SHIFT, VK_LWIN, VK_RWIN = 0x11, 0x12, 0x10, 0x5B, 0x5C
# Tecla sin asignar que se pulsa y suelta para que el menú Inicio no se abra
# al soltar Windows tras una combinación interceptada (truco habitual).
VK_MASCARA = 0xE8
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002

_ORDEN_REGISTRAR = WM_APP + 1
_ORDEN_GANCHO = WM_APP + 2


class _KBDLLHOOKSTRUCT(ctypes.Structure):
	_fields_ = [
		("vkCode", wintypes.DWORD),
		("scanCode", wintypes.DWORD),
		("flags", wintypes.DWORD),
		("time", wintypes.DWORD),
		("dwExtraInfo", ctypes.c_size_t),
	]


class _KEYBDINPUT(ctypes.Structure):
	_fields_ = [
		("wVk", wintypes.WORD),
		("wScan", wintypes.WORD),
		("dwFlags", wintypes.DWORD),
		("time", wintypes.DWORD),
		("dwExtraInfo", ctypes.c_size_t),
	]


class _INPUT(ctypes.Structure):
	class _U(ctypes.Union):
		# El tamaño de la unión debe ser el de MOUSEINPUT (el mayor) o SendInput falla.
		_fields_ = [("ki", _KEYBDINPUT), ("relleno", ctypes.c_byte * 32)]

	_anonymous_ = ("u",)
	_fields_ = [("type", wintypes.DWORD), ("u", _U)]


if os.name == "nt":
	_user32 = ctypes.WinDLL("user32", use_last_error=True)
	_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
	LRESULT = ctypes.c_ssize_t
	_PROC_GANCHO = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
	_user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
	_user32.RegisterHotKey.restype = wintypes.BOOL
	_user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
	_user32.UnregisterHotKey.restype = wintypes.BOOL
	_user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
	_user32.GetMessageW.restype = wintypes.BOOL
	_user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
	_user32.PeekMessageW.restype = wintypes.BOOL
	_user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
	_user32.PostThreadMessageW.restype = wintypes.BOOL
	_user32.SetWindowsHookExW.argtypes = [ctypes.c_int, _PROC_GANCHO, wintypes.HINSTANCE, wintypes.DWORD]
	_user32.SetWindowsHookExW.restype = wintypes.HHOOK
	_user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
	_user32.UnhookWindowsHookEx.restype = wintypes.BOOL
	_user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
	_user32.CallNextHookEx.restype = LRESULT
	_user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
	_user32.GetAsyncKeyState.restype = ctypes.c_short
	_user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int]
	_user32.SendInput.restype = wintypes.UINT
	_kernel32.GetCurrentThreadId.restype = wintypes.DWORD
	_kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
	_kernel32.GetModuleHandleW.restype = wintypes.HMODULE


@dataclass(frozen=True)
class ResultadoRegistro:
	"""Qué atajos se registraron y cuáles no (y por qué)."""

	registrados: dict[str, str]
	fallidos: dict[str, str]


class GestorTeclasGlobales:
	"""Registra atajos globales y llama a ``al_pulsar(accion)`` desde su propio hilo.

	``al_pulsar`` debe ser rápido (encolar y volver): mientras se ejecuta, el
	hilo no atiende otras teclas.
	"""

	def __init__(self, al_pulsar: Callable[[str], None]) -> None:
		self._al_pulsar = al_pulsar
		self._hilo: threading.Thread | None = None
		self._id_hilo = 0
		self._listo = threading.Event()
		self._candado = threading.Lock()
		self._pendiente: dict[str, str] = {}
		self._resultado = ResultadoRegistro({}, {})
		self._resultado_listo = threading.Event()
		self._por_id: dict[int, str] = {}
		self._gancho = None
		self._proc_gancho = None
		self._gancho_pedido = False
		self._interceptadas: set[int] = set()
		self.al_cambiar_registro: Callable[[ResultadoRegistro], None] | None = None

	# ── API pública (cualquier hilo) ────────────────────────────────────────

	def iniciar(self) -> None:
		if os.name != "nt" or (self._hilo and self._hilo.is_alive()):
			return
		self._listo.clear()
		self._hilo = threading.Thread(target=self._bucle, name="teclas-globales", daemon=True)
		self._hilo.start()
		self._listo.wait(3)

	def detener(self) -> None:
		if self._hilo and self._hilo.is_alive() and self._id_hilo:
			_user32.PostThreadMessageW(self._id_hilo, WM_QUIT, 0, 0)
			self._hilo.join(timeout=3)
		self._hilo = None

	def registrar(self, atajos: dict[str, str], esperar: float = 2.0) -> ResultadoRegistro:
		"""Sustituye todos los atajos por ``{accion: "Ctrl+Alt+Win+X"}`` y devuelve el resultado.

		Las acciones sin atajo (texto vacío) se omiten. El registro ocurre en el
		hilo de teclas (Windows asocia cada atajo al hilo que lo registra).
		"""
		with self._candado:
			self._pendiente = {accion: texto for accion, texto in atajos.items() if texto}
		self._resultado_listo.clear()
		if not self._enviar(_ORDEN_REGISTRAR):
			return ResultadoRegistro({}, dict.fromkeys(self._pendiente, _("El sistema de teclas globales no está activo.")))
		self._resultado_listo.wait(esperar)
		return self._resultado

	def suspender(self) -> None:
		"""Quita todos los atajos (p. ej. mientras se edita uno en el diálogo de teclas)."""
		self.registrar({})

	def interceptar_flechas_nativas(self, activar: bool) -> None:
		"""Activa o desactiva el gancho que hace cíclicas Ctrl+Win+Izquierda/Derecha."""
		self._gancho_pedido = activar
		self._enviar(_ORDEN_GANCHO)

	@property
	def resultado(self) -> ResultadoRegistro:
		return self._resultado

	@property
	def gancho_activo(self) -> bool:
		return self._gancho is not None

	def _enviar(self, orden: int) -> bool:
		if not self._id_hilo or not (self._hilo and self._hilo.is_alive()):
			return False
		return bool(_user32.PostThreadMessageW(self._id_hilo, orden, 0, 0))

	# ── Hilo ────────────────────────────────────────────────────────────────

	def _bucle(self) -> None:
		self._id_hilo = _kernel32.GetCurrentThreadId()
		mensaje = wintypes.MSG()
		# Crea la cola de mensajes del hilo antes de que nadie le envíe nada.
		_user32.PeekMessageW(ctypes.byref(mensaje), None, 0, 0, 0)
		self._listo.set()
		log.info("Hilo de teclas globales en marcha.")
		try:
			while _user32.GetMessageW(ctypes.byref(mensaje), None, 0, 0) > 0:
				if mensaje.message == WM_HOTKEY:
					accion = self._por_id.get(int(mensaje.wParam))
					if accion:
						self._lanzar(accion)
				elif mensaje.message == _ORDEN_REGISTRAR:
					self._aplicar_registro()
				elif mensaje.message == _ORDEN_GANCHO:
					self._aplicar_gancho()
		finally:
			self._quitar_todos()
			self._quitar_gancho()
			self._id_hilo = 0
			log.info("Hilo de teclas globales terminado.")

	def _lanzar(self, accion: str) -> None:
		try:
			self._al_pulsar(accion)
		except Exception:  # noqa: BLE001 - una acción rota no debe matar las teclas
			log.exception("Error al ejecutar la acción «%s» de una tecla global", accion)

	def _quitar_todos(self) -> None:
		for identificador in list(self._por_id):
			_user32.UnregisterHotKey(None, identificador)
		self._por_id.clear()

	def _aplicar_registro(self) -> None:
		self._quitar_todos()
		with self._candado:
			pendiente = dict(self._pendiente)
		registrados: dict[str, str] = {}
		fallidos: dict[str, str] = {}
		usadas: dict[Combinacion, str] = {}
		for identificador, (accion, texto) in enumerate(sorted(pendiente.items()), 1):
			combinacion = analizar(texto)
			if combinacion is None or not combinacion.valida:
				fallidos[accion] = _("La combinación «{t}» no es válida: necesita Ctrl, Alt o Win y una tecla.").format(t=texto)
				continue
			if combinacion in usadas:
				fallidos[accion] = _("«{t}» ya está asignada a otra acción.").format(t=combinacion)
				continue
			if _user32.RegisterHotKey(None, identificador, combinacion.modificadores | MOD_NOREPEAT, combinacion.vk):
				self._por_id[identificador] = accion
				usadas[combinacion] = accion
				registrados[accion] = str(combinacion)
			else:
				error = ctypes.get_last_error()
				log.warning("No se pudo registrar %s para «%s» (error %s).", combinacion, accion, error)
				fallidos[accion] = _("Windows u otro programa ya usa «{t}».").format(t=combinacion)
		self._resultado = ResultadoRegistro(registrados, fallidos)
		log.info("Teclas globales: %d registradas, %d fallidas.", len(registrados), len(fallidos))
		self._resultado_listo.set()
		if self.al_cambiar_registro is not None:
			try:
				self.al_cambiar_registro(self._resultado)
			except Exception:  # noqa: BLE001
				log.exception("Error en el aviso de registro de teclas")

	# ── Gancho de Ctrl+Win+flechas ──────────────────────────────────────────

	def _aplicar_gancho(self) -> None:
		if self._gancho_pedido and self._gancho is None:
			self._proc_gancho = _PROC_GANCHO(self._procesar_tecla)
			self._gancho = _user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc_gancho, _kernel32.GetModuleHandleW(None), 0)
			if not self._gancho:
				log.warning("No se pudo instalar el gancho de teclado (error %s).", ctypes.get_last_error())
				self._gancho = None
			else:
				log.info("Gancho de Ctrl+Win+flechas instalado.")
		elif not self._gancho_pedido:
			self._quitar_gancho()

	def _quitar_gancho(self) -> None:
		if self._gancho is not None:
			_user32.UnhookWindowsHookEx(self._gancho)
			self._gancho = None
			log.info("Gancho de Ctrl+Win+flechas quitado.")

	@staticmethod
	def _pulsada(vk: int) -> bool:
		return bool(_user32.GetAsyncKeyState(vk) & 0x8000)

	def _procesar_tecla(self, codigo: int, wparam: int, lparam: int) -> int:
		"""Debe ser MUY rápido: Windows quita el gancho si tarda demasiado."""
		try:
			if codigo == 0:
				datos = _KBDLLHOOKSTRUCT.from_address(lparam)
				vk = int(datos.vkCode)
				if vk in (VK_LEFT, VK_RIGHT) and not datos.flags & LLKHF_INJECTED:
					if wparam in (WM_KEYDOWN, WM_SYSKEYDOWN):
						if (
							self._pulsada(VK_CONTROL)
							and (self._pulsada(VK_LWIN) or self._pulsada(VK_RWIN))
							and not self._pulsada(VK_MENU)
							and not self._pulsada(VK_SHIFT)
						):
							self._interceptadas.add(vk)
							self._enmascarar_windows()
							self._lanzar("nativa_siguiente" if vk == VK_RIGHT else "nativa_anterior")
							return 1
					elif wparam in (WM_KEYUP, WM_SYSKEYUP) and vk in self._interceptadas:
						self._interceptadas.discard(vk)
						return 1
		except Exception:  # noqa: BLE001 - jamás romper el teclado del usuario
			log.debug("Error en el gancho de teclado", exc_info=True)
		return _user32.CallNextHookEx(None, codigo, wparam, lparam)

	@staticmethod
	def _enmascarar_windows() -> None:
		"""Pulsa una tecla neutra para que soltar Windows no abra el menú Inicio."""
		entradas = (_INPUT * 2)()
		for indice, banderas in enumerate((0, KEYEVENTF_KEYUP)):
			entradas[indice].type = INPUT_KEYBOARD
			entradas[indice].ki = _KEYBDINPUT(VK_MASCARA, 0, banderas, 0, 0)
		_user32.SendInput(2, entradas, ctypes.sizeof(_INPUT))
