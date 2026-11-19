"""Genera ``data/emojis/emojis_es.json`` a partir de los datos oficiales de Unicode.

Se ejecuta en DESARROLLO, no en la aplicación (que solo lee el JSON ya hecho):

    python tools/generar_emojis.py --origen adjuntos/datos_emoji

Entradas (Unicode License V3):

- ``emoji-test.txt`` (unicode.org/Public/emoji/latest): orden, grupos y
  versión de cada emoji; solo se usan los «fully-qualified».
- ``annotations_es.json`` y ``annotationsDerived_es.json`` (cldr-json): nombre
  («tts») y palabras clave («default») en español.

Salida: un JSON compacto con
- ``grupos``: nombres en español, en el orden de Unicode.
- ``emojis``: ``[emoji, nombre, palabras clave separadas por «|», grupo, versión, base]``,
  donde ``base`` es el emoji sin tono de piel (vacío si no es una variante).
- ``simbolos``: caracteres con nombre en CLDR que no son emoji (©, €, →...).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

GRUPOS_ES = {
	"Smileys & Emotion": "Caras y emociones",
	"People & Body": "Personas y cuerpo",
	"Animals & Nature": "Animales y naturaleza",
	"Food & Drink": "Comida y bebida",
	"Travel & Places": "Viajes y lugares",
	"Activities": "Actividades",
	"Objects": "Objetos",
	"Symbols": "Símbolos",
	"Flags": "Banderas",
}
TONOS = "\U0001f3fb\U0001f3fc\U0001f3fd\U0001f3fe\U0001f3ff"
SELECTOR = "️"
LINEA = re.compile(r"^([0-9A-F ]+?)\s*;\s*fully-qualified\s*#\s*\S+\s+E(\d+\.\d+)")


def _anotaciones(ruta: Path, clave: str) -> dict[str, dict]:
	datos = json.loads(ruta.read_text(encoding="utf-8"))
	return datos[clave]["annotations"]


def generar(origen: Path) -> dict:
	nombres: dict[str, dict] = {}
	nombres.update(_anotaciones(origen / "annotations_es.json", "annotations"))
	nombres.update(_anotaciones(origen / "annotationsDerived_es.json", "annotationsDerived"))

	def buscar(emoji: str) -> dict | None:
		return nombres.get(emoji) or nombres.get(emoji.replace(SELECTOR, ""))

	grupos: list[str] = []
	emojis: list[list] = []
	vistos: set[str] = set()
	grupo_actual = -1
	for linea in (origen / "emoji-test.txt").read_text(encoding="utf-8").splitlines():
		if linea.startswith("# group:"):
			nombre = linea.split(":", 1)[1].strip()
			if nombre in GRUPOS_ES:
				grupos.append(GRUPOS_ES[nombre])
				grupo_actual = len(grupos) - 1
			else:
				grupo_actual = -1  # «Component»: tonos sueltos, no se ofrecen
			continue
		coincidencia = LINEA.match(linea)
		if not coincidencia or grupo_actual < 0:
			continue
		emoji = "".join(chr(int(c, 16)) for c in coincidencia.group(1).split())
		anotacion = buscar(emoji)
		if anotacion is None:
			print(f"Aviso: sin nombre en español para {emoji!r}", file=sys.stderr)
			continue
		nombre = anotacion.get("tts", [""])[0]
		claves = "|".join(anotacion.get("default", []))
		base = ""
		if any(t in emoji for t in TONOS):
			sin_tono = "".join(c for c in emoji if c not in TONOS)
			base = sin_tono
		emojis.append([emoji, nombre, claves, grupo_actual, coincidencia.group(2), base])
		vistos.add(emoji)
		vistos.add(emoji.replace(SELECTOR, ""))

	simbolos: list[list] = []
	for caracter, anotacion in _anotaciones(origen / "annotations_es.json", "annotations").items():
		# Fuera los modificadores de tono y de pelo: no son símbolos que se escriban solos.
		if caracter in vistos or caracter in TONOS or "🦰" <= caracter <= "🦳":
			continue
		if len(caracter) != 1 or not caracter.isprintable():
			continue
		simbolos.append([caracter, anotacion.get("tts", [""])[0], "|".join(anotacion.get("default", []))])
	return {"version": "emoji-test.txt + CLDR", "grupos": grupos, "emojis": emojis, "simbolos": simbolos}


def main(argumentos: list[str] | None = None) -> int:
	analizador = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	analizador.add_argument("--origen", type=Path, default=RAIZ / "adjuntos" / "datos_emoji")
	analizador.add_argument("--destino", type=Path, default=RAIZ / "data" / "emojis" / "emojis_es.json")
	opciones = analizador.parse_args(argumentos)
	sys.stdout.reconfigure(encoding="utf-8", errors="replace")
	datos = generar(opciones.origen)
	opciones.destino.parent.mkdir(parents=True, exist_ok=True)
	opciones.destino.write_text(json.dumps(datos, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
	licencia = opciones.origen / "LICENSE_unicode.txt"
	if licencia.is_file():
		(opciones.destino.parent / "LICENCIA_UNICODE.txt").write_text(licencia.read_text(encoding="utf-8"), encoding="utf-8")
	print(f"{len(datos['emojis'])} emojis, {len(datos['simbolos'])} símbolos, {len(datos['grupos'])} grupos → {opciones.destino}")
	return 0


if __name__ == "__main__":
	sys.exit(main())
