"""Integración con Windows: inicio automático y tonos por escritorio (sin wx).

Inicio automático: es la ÚNICA escritura fuera de la carpeta de la aplicación,
y solo si el usuario lo activa en Opciones. Se usa la clave
``HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run`` (por usuario, sin
permisos de administrador). Al desactivarlo se borra el valor.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from pathlib import Path

log = logging.getLogger(__name__)

CLAVE_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
ARGUMENTO_INICIO = "--inicio-windows"


def orden_de_arranque() -> str:
	"""La orden que Windows ejecutará al iniciar sesión.

	Compilada: el ``.exe``. Desde código: ``pythonw.exe main.py`` (sin consola).
	"""
	if getattr(sys, "frozen", False):
		return f'"{sys.executable}" {ARGUMENTO_INICIO}'
	interprete = Path(sys.executable)
	sin_consola = interprete.with_name("pythonw.exe")
	if sin_consola.is_file():
		interprete = sin_consola
	principal = Path(__file__).resolve().parents[2] / "main.py"
	return f'"{interprete}" "{principal}" {ARGUMENTO_INICIO}'


def inicio_automatico_activo(nombre: str) -> bool:
	if os.name != "nt":
		return False
	import winreg

	try:
		with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLAVE_RUN) as clave:
			valor, _tipo = winreg.QueryValueEx(clave, nombre)
			return bool(valor)
	except FileNotFoundError:
		return False
	except OSError:
		log.warning("No se pudo leer el inicio automático", exc_info=True)
		return False


def establecer_inicio_automatico(nombre: str, activar: bool) -> bool:
	"""Crea o borra la entrada de inicio. Devuelve ``True`` si lo consiguió."""
	if os.name != "nt":
		return False
	import winreg

	try:
		with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLAVE_RUN, 0, winreg.KEY_SET_VALUE) as clave:
			if activar:
				winreg.SetValueEx(clave, nombre, 0, winreg.REG_SZ, orden_de_arranque())
				log.info("Inicio automático activado: %s", orden_de_arranque())
			else:
				try:
					winreg.DeleteValue(clave, nombre)
					log.info("Inicio automático desactivado.")
				except FileNotFoundError:
					pass
		return True
	except OSError:
		log.exception("No se pudo cambiar el inicio automático")
		return False


# ── Tonos ────────────────────────────────────────────────────────────────────

FRECUENCIA_BASE = 440
# Semitono a semitono con escala mayor: cada escritorio suena más agudo que el anterior.
_ESCALA = [0, 2, 4, 5, 7, 9, 11]


def frecuencia_de(numero: int) -> int:
	"""Frecuencia del tono del escritorio ``numero`` (escala mayor ascendente desde La 440)."""
	indice = max(numero, 1) - 1
	octava, grado = divmod(indice, len(_ESCALA))
	semitonos = octava * 12 + _ESCALA[grado]
	return int(round(FRECUENCIA_BASE * 2 ** (semitonos / 12)))


def tocar_tono(numero: int, duracion_ms: int = 70) -> None:
	"""Toca el tono del escritorio sin bloquear (``winsound.Beep`` bloquea mientras suena)."""
	if os.name != "nt":
		return

	def sonar() -> None:
		try:
			import winsound

			winsound.Beep(min(frecuencia_de(numero), 8000), duracion_ms)
		except Exception:  # noqa: BLE001 - sin altavoz o sin servicio de sonido
			log.debug("No se pudo tocar el tono", exc_info=True)

	threading.Thread(target=sonar, name="tono", daemon=True).start()


NOMBRES_ANTIGUOS = ("Gestor de Escritorios Virtuales",)


def migrar_inicio_automatico(nombre: str) -> None:
	"""Si el inicio automático se activó con un nombre antiguo del programa, lo pasa al actual."""
	for antiguo in NOMBRES_ANTIGUOS:
		if antiguo != nombre and inicio_automatico_activo(antiguo):
			log.info("Inicio automático: se cambia la entrada «%s» por «%s».", antiguo, nombre)
			if establecer_inicio_automatico(nombre, True):
				establecer_inicio_automatico(antiguo, False)
