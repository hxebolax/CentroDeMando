"""«No molestar»: cuándo callar los avisos automáticos (sin wx, se prueba aparte).

Qué calla:

- El anuncio por voz de las notificaciones nuevas (siguen guardándose en el
  historial), salvo las de las aplicaciones permitidas.
- Los avisos de dispositivos de audio conectados y desconectados.
- El aviso «Copiado» del portapapeles.

Qué NO calla: las respuestas a una orden de la persona (decir el escritorio,
el volumen...) ni las alarmas y temporizadores, que se ponen a propósito.

Se activa a mano (tecla global, bandeja, lanzador) o cada día en una franja
horaria («23:00» a «08:00» cruza la medianoche y vale igual).
"""

from __future__ import annotations

import datetime as _dt
import re
from collections.abc import Iterable

_HORA = re.compile(r"^\s*(\d{1,2})[:.](\d{2})\s*$")


def leer_hora(texto: str) -> int | None:
	"""«23:00» → minutos desde la medianoche (1380). ``None`` si no es una hora válida."""
	coincidencia = _HORA.match(str(texto or ""))
	if not coincidencia:
		return None
	horas, minutos = int(coincidencia.group(1)), int(coincidencia.group(2))
	if horas > 23 or minutos > 59:
		return None
	return horas * 60 + minutos


def en_franja(ahora: _dt.time | _dt.datetime, desde: str, hasta: str) -> bool:
	"""Indica si ``ahora`` cae en la franja [desde, hasta). Admite cruzar la medianoche.

	Una franja con el mismo inicio y fin, o con una hora no válida, no vale nunca.
	"""
	inicio, fin = leer_hora(desde), leer_hora(hasta)
	if inicio is None or fin is None or inicio == fin:
		return False
	minuto = ahora.hour * 60 + ahora.minute
	if inicio < fin:
		return inicio <= minuto < fin
	return minuto >= inicio or minuto < fin


def activo(manual: bool, programado: bool, desde: str, hasta: str, ahora: _dt.datetime | None = None) -> bool:
	"""«No molestar» está en vigor si se activó a mano o si toca por horario."""
	if manual:
		return True
	return bool(programado) and en_franja(ahora or _dt.datetime.now(), desde, hasta)


def lista_apps(texto: str | Iterable[str]) -> set[str]:
	"""«WhatsApp, Correo» → {"whatsapp", "correo"} (sin mayúsculas ni espacios sobrantes)."""
	partes = texto.split(",") if isinstance(texto, str) else list(texto)
	return {p.strip().casefold() for p in partes if p and p.strip()}


def coincide_app(app: str, aumid: str, apps: set[str]) -> bool:
	"""La notificación es de alguna de ``apps`` (por nombre visible o por identificador).

	Se acepta que el nombre escrito sea parte del nombre real: «whatsapp»
	casa con «WhatsApp Beta».
	"""
	nombre, identificador = (app or "").casefold(), (aumid or "").casefold()
	return any(a == nombre or a == identificador or (len(a) >= 3 and a in nombre) for a in apps)


def debe_anunciar_notificacion(
	app: str,
	aumid: str,
	solo_estas: str,
	no_molestar: bool,
	permitidas: str,
) -> bool:
	"""Decide si se dice en voz alta una notificación nueva (función pura).

	- Si hay lista de «solo estas aplicaciones», las demás no se anuncian.
	- Con «No molestar» en vigor, solo se anuncian las permitidas.
	"""
	seleccion = lista_apps(solo_estas)
	if seleccion and not coincide_app(app, aumid, seleccion):
		return False
	if no_molestar:
		return coincide_app(app, aumid, lista_apps(permitidas))
	return True
