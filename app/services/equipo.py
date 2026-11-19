"""Estado del equipo y energía (sin wx).

- Estado: batería, procesador, memoria, disco del sistema, red y tiempo
  encendido, con psutil. Pensado para anunciarse de una vez con una tecla.
- Energía: bloquear, suspender, hibernar, apagar la pantalla, mantener el
  equipo despierto y apagar o reiniciar con cuenta atrás (cancelable). Nada
  necesita permisos de administrador.
"""

from __future__ import annotations

import ctypes
import logging
import os
import subprocess
import time
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Dato:
	nombre: str
	valor: str


def _duracion(segundos: float) -> str:
	segundos = int(segundos)
	dias, resto = divmod(segundos, 86400)
	horas, resto = divmod(resto, 3600)
	minutos = resto // 60
	partes = []
	if dias:
		partes.append(f"{dias} día" + ("s" if dias != 1 else ""))
	if horas:
		partes.append(f"{horas} hora" + ("s" if horas != 1 else ""))
	if minutos or not partes:
		partes.append(f"{minutos} minuto" + ("s" if minutos != 1 else ""))
	return " y ".join([", ".join(partes[:-1]), partes[-1]]) if len(partes) > 1 else partes[0]


def _tamano(octetos: float) -> str:
	for unidad in ("bytes", "KB", "MB", "GB", "TB"):
		if octetos < 1024 or unidad == "TB":
			return f"{octetos:.1f} {unidad}".replace(".", ",") if unidad != "bytes" else f"{int(octetos)} bytes"
		octetos /= 1024
	return ""


def estado() -> list[Dato]:
	"""Datos actuales del equipo, en el orden en que se anuncian."""
	import psutil

	datos: list[Dato] = []
	bateria = psutil.sensors_battery()
	if bateria is not None:
		if bateria.power_plugged:
			texto = f"{round(bateria.percent)} %, cargando" if bateria.percent < 100 else "100 %, conectada"
		else:
			texto = f"{round(bateria.percent)} %"
			if bateria.secsleft not in (psutil.POWER_TIME_UNLIMITED, psutil.POWER_TIME_UNKNOWN) and bateria.secsleft > 0:
				texto += f", quedan {_duracion(bateria.secsleft)}"
		datos.append(Dato("Batería", texto))
	datos.append(Dato("Procesador", f"{round(psutil.cpu_percent(interval=0.2))} % en uso"))
	memoria = psutil.virtual_memory()
	datos.append(Dato("Memoria", f"{round(memoria.percent)} % en uso, libres {_tamano(memoria.available)} de {_tamano(memoria.total)}"))
	unidad = os.environ.get("SystemDrive", "C:") + "\\"
	try:
		disco = psutil.disk_usage(unidad)
		datos.append(Dato(f"Disco {unidad[:2]}", f"libres {_tamano(disco.free)} de {_tamano(disco.total)}"))
	except OSError:
		log.debug("No se pudo leer el disco %s", unidad, exc_info=True)
	conectadas = [nombre for nombre, s in psutil.net_if_stats().items() if s.isup and "loopback" not in nombre.casefold()]
	datos.append(Dato("Red", ", ".join(conectadas) if conectadas else "sin conexión"))
	datos.append(Dato("Encendido desde hace", _duracion(time.time() - psutil.boot_time())))
	return datos


def resumen_para_voz() -> str:
	return ". ".join(f"{d.nombre}: {d.valor}" for d in estado() if d.nombre in ("Batería", "Procesador", "Memoria", "Red"))


# ── Energía ──────────────────────────────────────────────────────────────────

ES_CONTINUO = 0x80000000
ES_SISTEMA = 0x00000001
ES_PANTALLA = 0x00000002


def bloquear() -> bool:
	return bool(ctypes.windll.user32.LockWorkStation())


def suspender(hibernar: bool = False) -> bool:
	"""Suspende (o hiberna). Devuelve False si Windows lo rechaza."""
	return bool(ctypes.windll.powrprof.SetSuspendState(bool(hibernar), False, False))


def apagar_pantalla() -> None:
	hwnd_broadcast, wm_syscommand, sc_monitorpower = 0xFFFF, 0x0112, 0xF170
	ctypes.windll.user32.PostMessageW(hwnd_broadcast, wm_syscommand, sc_monitorpower, 2)


def mantener_despierto(activar: bool) -> None:
	"""Impide que el equipo se suspenda (la pantalla puede apagarse). Afecta al hilo que lo llama."""
	estado_nuevo = ES_CONTINUO | (ES_SISTEMA if activar else 0)
	ctypes.windll.kernel32.SetThreadExecutionState(estado_nuevo)


def programar_apagado(minutos: int, reiniciar: bool = False) -> None:
	"""Apaga o reinicia dentro de ``minutos`` con el aviso de Windows (se cancela con ``cancelar_apagado``)."""
	segundos = max(0, int(minutos) * 60)
	orden = ["shutdown", "/r" if reiniciar else "/s", "/t", str(segundos)]
	subprocess.run(orden, check=True, capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))  # noqa: S603, S607


def cancelar_apagado() -> bool:
	resultado = subprocess.run(
		["shutdown", "/a"], capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False
	)  # noqa: S603, S607
	return resultado.returncode == 0
