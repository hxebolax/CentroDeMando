"""Pegar o escribir en la ventana donde estaba el usuario (sin wx).

Flujo al elegir algo en una ventana rápida (portapapeles o emoticonos):

1. La ventana rápida guardó al abrirse la ventana que estaba delante.
2. Se cierra la ventana rápida y se devuelve el primer plano a esa ventana;
   se espera a que Windows lo confirme (hasta medio segundo).
3. Se sueltan los modificadores que sigan pulsados (Control, Alt, Mayúsculas,
   Windows): si no, Control+V podría llegar como Control+Alt+V.
4. Texto corto (emoticonos): se escribe carácter a carácter con
   ``KEYEVENTF_UNICODE``, sin tocar el portapapeles.
   Contenido del historial: se pone en el portapapeles y se manda Control+V
   (en las consolas clásicas, la orden Pegar de su menú, como hace NVDA).
5. Si se pidió, al cabo de un momento se devuelve al portapapeles lo que
   había antes: pegar desde el historial no machaca lo que el usuario tenía.

Todo esto espera y duerme: se llama SIEMPRE desde un hilo, nunca desde el de
la interfaz.
"""

from __future__ import annotations

import ctypes
import logging
import os
import time
from collections.abc import Callable

from app.services import ventanas_win32 as w32
from app.services.portapapeles_win32 import Contenido, PortapapelesOcupado, escribir, leer

log = logging.getLogger(__name__)

VK_CONTROL, VK_MENU, VK_SHIFT, VK_LWIN, VK_RWIN, VK_INSERT = 0x11, 0x12, 0x10, 0x5B, 0x5C, 0x2D
VK_LCONTROL, VK_RCONTROL, VK_LSHIFT, VK_RSHIFT, VK_LMENU, VK_RMENU = 0xA2, 0xA3, 0xA0, 0xA1, 0xA4, 0xA5
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
WM_COMMAND = 0x0111
ORDEN_PEGAR_CONSOLA = 0xFFF1
CLASES_CONSOLA = {"ConsoleWindowClass"}

METODO_CONTROL_V = "control_v"
METODO_MAYUS_INSERT = "mayus_insert"
METODO_ESCRIBIR = "escribir"


def _enviar(eventos: list[tuple[int, int, int]]) -> None:
	"""``eventos``: lista de (vk, unidad_unicode, banderas)."""
	from app.services.teclas import INPUT_KEYBOARD, _INPUT, _KEYBDINPUT, _user32

	if not eventos:
		return
	entradas = (_INPUT * len(eventos))()
	for indice, (vk, escaneo, banderas) in enumerate(eventos):
		entradas[indice].type = INPUT_KEYBOARD
		entradas[indice].ki = _KEYBDINPUT(vk, escaneo, banderas, 0, 0)
	_user32.SendInput(len(eventos), entradas, ctypes.sizeof(_INPUT))


def _pulsada(vk: int) -> bool:
	from app.services.teclas import _user32

	return bool(_user32.GetAsyncKeyState(vk) & 0x8000)


def soltar_modificadores() -> None:
	"""Suelta Control, Alt, Mayúsculas y Windows si siguen pulsadas."""
	from app.services.teclas import VK_MASCARA

	eventos = []
	for vk in (VK_LCONTROL, VK_RCONTROL, VK_LSHIFT, VK_RSHIFT, VK_LMENU, VK_RMENU, VK_LWIN, VK_RWIN):
		if _pulsada(vk):
			if vk in (VK_LWIN, VK_RWIN, VK_LMENU, VK_RMENU):
				# Soltar Windows o Alt «a secas» abriría el menú Inicio o la barra de menús.
				eventos += [(VK_MASCARA, 0, 0), (VK_MASCARA, 0, KEYEVENTF_KEYUP)]
			eventos.append((vk, 0, KEYEVENTF_KEYUP))
	_enviar(eventos)


def escribir_unicode(texto: str) -> None:
	"""Escribe el texto como si se tecleara, sin usar el portapapeles (emojis incluidos)."""
	unidades = texto.encode("utf-16-le", "surrogatepass")
	eventos = []
	for posicion in range(0, len(unidades), 2):
		unidad = int.from_bytes(unidades[posicion : posicion + 2], "little")
		eventos += [(0, unidad, KEYEVENTF_UNICODE), (0, unidad, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)]
	_enviar(eventos)


def _combinacion(modificador: int, tecla: int) -> None:
	_enviar([(modificador, 0, 0), (tecla, 0, 0), (tecla, 0, KEYEVENTF_KEYUP), (modificador, 0, KEYEVENTF_KEYUP)])


def devolver_foco(hwnd: int, espera: float = 0.6) -> bool:
	"""Pone ``hwnd`` en primer plano y espera a que Windows lo confirme."""
	if not hwnd or not w32.existe(hwnd):
		return False
	w32.forzar_primer_plano(hwnd)
	limite = time.monotonic() + espera
	while time.monotonic() < limite:
		if w32.ventana_activa() == hwnd:
			return True
		time.sleep(0.02)
		w32.forzar_primer_plano(hwnd)
	log.info("La ventana %s no recuperó el primer plano a tiempo.", hwnd)
	return w32.ventana_activa() == hwnd


def pulsar_pegar(hwnd: int, metodo: str = METODO_CONTROL_V) -> None:
	"""Envía la orden de pegar adecuada a la ventana."""
	if w32.clase(hwnd) in CLASES_CONSOLA:
		from app.services.ventanas_win32 import _user32 as user32

		user32.PostMessageW(hwnd, WM_COMMAND, ORDEN_PEGAR_CONSOLA, 0)
		return
	if metodo == METODO_MAYUS_INSERT:
		_combinacion(VK_SHIFT, VK_INSERT)
	else:
		_combinacion(VK_CONTROL, ord("V"))


def pegar_contenido(
	hwnd: int,
	contenido: Contenido,
	dueno: int,
	al_escribir: Callable[[int], None] | None = None,
	restaurar: bool = True,
	retraso_restaurar: float = 0.5,
	metodo: str = METODO_CONTROL_V,
) -> bool:
	"""Pone ``contenido`` en el portapapeles y lo pega en ``hwnd``.

	:param dueno: ventana dueña del portapapeles (la del monitor).
	:param al_escribir: recibe el número de secuencia de cada escritura propia
		(para que el historial no la vuelva a guardar).
	:return: ``True`` si la ventana recuperó el primer plano y se mandó pegar.
	"""
	if os.name != "nt":
		return False
	anterior = None
	if restaurar:
		try:
			anterior = leer()
		except PortapapelesOcupado:
			log.info("No se pudo guardar el portapapeles anterior para restaurarlo.")
	secuencia = escribir(contenido, dueno)
	if al_escribir:
		al_escribir(secuencia)
	if not devolver_foco(hwnd):
		return False
	soltar_modificadores()
	time.sleep(0.03)
	pulsar_pegar(hwnd, metodo)
	if anterior is not None and not anterior.vacio:
		# El programa de destino lee el portapapeles al procesar Control+V: hay que esperarle.
		time.sleep(max(0.1, retraso_restaurar))
		try:
			secuencia = escribir(anterior, dueno)
			if al_escribir:
				al_escribir(secuencia)
		except PortapapelesOcupado, OSError, MemoryError:
			log.warning("No se pudo restaurar el portapapeles anterior.", exc_info=True)
	return True


VK_LEFT = 0x25


def mover_cursor_izquierda(veces: int) -> None:
	"""Retrocede el cursor ``veces`` caracteres (para dejarlo donde marca ``{cursor}``)."""
	if veces > 0:
		# Las flechas son teclas «extendidas»: sin la marca, Windows las toma por el 4 del teclado numérico.
		extendida = 0x0001
		_enviar([e for _i in range(veces) for e in ((VK_LEFT, 0x4B, extendida), (VK_LEFT, 0x4B, extendida | KEYEVENTF_KEYUP))])


def insertar_texto(
	hwnd: int, texto: str, metodo: str, dueno: int, al_escribir: Callable[[int], None] | None = None, retroceso: int = 0
) -> bool:
	"""Escribe ``texto`` en ``hwnd``: tecleándolo (``METODO_ESCRIBIR``) o pegándolo.

	Un texto de varias líneas se pega siempre: teclear el salto de línea como
	carácter no equivale a pulsar Intro en todos los programas.
	"""
	if metodo != METODO_ESCRIBIR or "\n" in texto:
		correcto = pegar_contenido(
			hwnd, Contenido(texto=texto), dueno, al_escribir, restaurar=True, metodo=metodo if metodo != METODO_ESCRIBIR else METODO_CONTROL_V
		)
	else:
		correcto = devolver_foco(hwnd)
		if correcto:
			soltar_modificadores()
			time.sleep(0.03)
			escribir_unicode(texto)
	if correcto and retroceso:
		time.sleep(0.05)
		mover_cursor_izquierda(retroceso)
	return correcto
