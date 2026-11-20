"""Copias de seguridad, exportar e importar la configuración y los datos (sin wx).

Qué entra en una copia (un ZIP):

- ``config/config.json``: todas las opciones, teclas, reglas, perfiles de audio...
- ``db/*.json``: fragmentos de texto, temporizadores y alarmas.
- ``db/*.db``: historial del portapapeles (si se pide) y de notificaciones.
  Las bases SQLite se copian con su API de copia de seguridad: así la copia
  es coherente aunque el programa las esté usando.
- ``centro_de_mando_copia.json``: qué es, de qué versión y cuándo se hizo.

Qué NO entra: registros, temporales y ``config/actualizaciones.json`` (el
estado del actualizador de ESTE equipo: importarlo podría impedir actualizar).

Importar no pisa nada en caliente: deja los archivos en
``data/importacion_pendiente`` y se colocan en el siguiente arranque, antes de
abrir las bases de datos (``aplicar_importacion_pendiente``), tras guardar una
copia de lo que había.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import sqlite3
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

from app.core import paths

log = logging.getLogger(__name__)

MANIFIESTO = "centro_de_mando_copia.json"
PREFIJO_AUTOMATICA = "copia_automatica_"
CARPETA_PENDIENTE = "importacion_pendiente"
# Lo único que puede venir dentro de una copia (cualquier otra ruta se rechaza).
_PERMITIDOS = re.compile(r"^(config/config\.json|db/[A-Za-z0-9_\-]+\.(db|json))$")
# Límite de lo que se extrae (evita «bombas ZIP»).
TAMANO_MAXIMO = 2 * 1024**3
PORTAPAPELES = "db/portapapeles.db"


class ErrorCopia(Exception):
	"""Fallo con mensaje para la persona."""


@dataclass(frozen=True)
class InfoCopia:
	version: str
	fecha: str
	archivos: tuple[str, ...]


def ruta_copias() -> Path:
	return paths.subcarpeta("backups")


def nombre_permitido(nombre: str) -> bool:
	"""Ruta de un ZIP que se acepta al importar (función pura)."""
	return bool(_PERMITIDOS.match(nombre)) and ".." not in nombre


def _archivos_a_copiar(datos: Path, con_portapapeles: bool) -> list[tuple[Path, str]]:
	resultado: list[tuple[Path, str]] = []
	configuracion = datos / "config" / "config.json"
	if configuracion.is_file():
		resultado.append((configuracion, "config/config.json"))
	carpeta_db = datos / "db"
	if carpeta_db.is_dir():
		for archivo in sorted(carpeta_db.iterdir()):
			nombre = f"db/{archivo.name}"
			if not archivo.is_file() or not nombre_permitido(nombre):
				continue
			if nombre == PORTAPAPELES and not con_portapapeles:
				continue
			resultado.append((archivo, nombre))
	return resultado


def _copiar_sqlite(origen: Path, destino: Path) -> None:
	"""Copia coherente de una base SQLite abierta (API de copia de seguridad)."""
	fuente = sqlite3.connect(f"file:{origen}?mode=ro", uri=True, timeout=10)
	try:
		copia = sqlite3.connect(destino)
		try:
			fuente.backup(copia)
		finally:
			copia.close()
	finally:
		fuente.close()


def crear_copia(destino: Path, version: str, con_portapapeles: bool = True, datos: Path | None = None) -> Path:
	"""Crea el ZIP en ``destino`` y lo devuelve. Escribe en un temporal y lo mueve al final."""
	datos = datos or paths.ruta_datos()
	archivos = _archivos_a_copiar(datos, con_portapapeles)
	if not archivos:
		raise ErrorCopia("No hay configuración ni datos que copiar todavía.")
	destino = Path(destino)
	destino.parent.mkdir(parents=True, exist_ok=True)
	temporal = destino.with_name(destino.name + ".tmp")
	with tempfile.TemporaryDirectory() as carpeta:
		with zipfile.ZipFile(temporal, "w", zipfile.ZIP_DEFLATED) as paquete:
			for origen, nombre in archivos:
				if origen.suffix == ".db":
					copia = Path(carpeta) / origen.name
					try:
						_copiar_sqlite(origen, copia)
					except sqlite3.Error as error:
						log.warning("No se pudo copiar la base %s: %s", origen.name, error)
						continue
					paquete.write(copia, nombre)
				else:
					paquete.write(origen, nombre)
			manifiesto = {
				"app": "CentroDeMando",
				"version": version,
				"fecha": time.strftime("%Y-%m-%d %H:%M:%S"),
				"archivos": [nombre for _o, nombre in archivos],
			}
			paquete.writestr(MANIFIESTO, json.dumps(manifiesto, ensure_ascii=False, indent=2))
	temporal.replace(destino)
	log.info("Copia de seguridad creada: %s", destino)
	return destino


def leer_copia(origen: Path) -> InfoCopia:
	"""Comprueba que el ZIP es una copia válida de Centro de Mando y dice qué trae."""
	try:
		with zipfile.ZipFile(origen) as paquete:
			nombres = paquete.namelist()
			if MANIFIESTO not in nombres:
				raise ErrorCopia("Ese archivo no es una copia de Centro de Mando.")
			manifiesto = json.loads(paquete.read(MANIFIESTO).decode("utf-8"))
			archivos = tuple(n for n in nombres if n != MANIFIESTO)
			raros = [n for n in archivos if not nombre_permitido(n)]
			if raros:
				raise ErrorCopia("La copia trae archivos que no se esperan: " + ", ".join(raros[:3]))
			if sum(paquete.getinfo(n).file_size for n in archivos) > TAMANO_MAXIMO:
				raise ErrorCopia("La copia es demasiado grande.")
	except (zipfile.BadZipFile, OSError, ValueError, KeyError) as error:
		raise ErrorCopia("No se pudo leer la copia: el archivo está dañado o no es un ZIP.") from error
	if not isinstance(manifiesto, dict) or manifiesto.get("app") != "CentroDeMando":
		raise ErrorCopia("Ese archivo no es una copia de Centro de Mando.")
	return InfoCopia(str(manifiesto.get("version", "")), str(manifiesto.get("fecha", "")), archivos)


def preparar_importacion(origen: Path, datos: Path | None = None) -> InfoCopia:
	"""Deja la copia lista para colocarla en el siguiente arranque."""
	datos = datos or paths.ruta_datos()
	informacion = leer_copia(origen)
	pendiente = datos / CARPETA_PENDIENTE
	shutil.rmtree(pendiente, ignore_errors=True)
	pendiente.mkdir(parents=True)
	with zipfile.ZipFile(origen) as paquete:
		for nombre in informacion.archivos:
			destino = pendiente / nombre
			destino.parent.mkdir(parents=True, exist_ok=True)
			with paquete.open(nombre) as entrada, open(destino, "wb") as salida:
				shutil.copyfileobj(entrada, salida)
	log.info("Importación preparada desde %s (%d archivos)", origen, len(informacion.archivos))
	return informacion


def hay_importacion_pendiente(datos: Path | None = None) -> bool:
	return ((datos or paths.ruta_datos()) / CARPETA_PENDIENTE).is_dir()


def aplicar_importacion_pendiente(version: str, datos: Path | None = None) -> bool:
	"""En el arranque, ANTES de cargar la configuración y abrir las bases: coloca lo importado.

	Guarda antes una copia de lo que había en ``data/backups``. Devuelve
	``True`` si se importó algo.
	"""
	datos = datos or paths.ruta_datos()
	pendiente = datos / CARPETA_PENDIENTE
	if not pendiente.is_dir():
		return False
	archivos = [a for a in pendiente.rglob("*") if a.is_file() and nombre_permitido(a.relative_to(pendiente).as_posix())]
	if archivos:
		try:
			crear_copia(datos / "backups" / f"antes_de_importar_{time.strftime('%Y%m%d_%H%M%S')}.zip", version, True, datos)
		except ErrorCopia:
			pass  # no había nada que guardar
		for archivo in archivos:
			relativo = archivo.relative_to(pendiente)
			destino = datos / relativo
			destino.parent.mkdir(parents=True, exist_ok=True)
			# Restos de SQLite de la base anterior: no deben mezclarse con la nueva.
			for resto in (destino.with_name(destino.name + "-wal"), destino.with_name(destino.name + "-shm")):
				resto.unlink(missing_ok=True)
			shutil.move(str(archivo), destino)
	shutil.rmtree(pendiente, ignore_errors=True)
	log.info("Importación aplicada: %d archivos", len(archivos))
	return bool(archivos)


def copias_automaticas(carpeta: Path | None = None) -> list[Path]:
	"""Copias automáticas de la más nueva a la más antigua."""
	carpeta = carpeta or ruta_copias()
	return sorted(carpeta.glob(f"{PREFIJO_AUTOMATICA}*.zip"), reverse=True)


def toca_copia(carpeta: Path, cada_horas: float = 24, ahora: float | None = None) -> bool:
	"""``True`` si la última copia automática tiene más de ``cada_horas`` (o no hay ninguna)."""
	existentes = copias_automaticas(carpeta)
	if not existentes:
		return True
	return (ahora or time.time()) - existentes[0].stat().st_mtime >= cada_horas * 3600


def copia_automatica(version: str, conservar: int = 7, con_portapapeles: bool = True, datos: Path | None = None) -> Path | None:
	"""Hace la copia diaria si toca y borra las automáticas más viejas. Nunca lanza."""
	datos = datos or paths.ruta_datos()
	carpeta = datos / "backups"
	try:
		carpeta.mkdir(parents=True, exist_ok=True)
		if not toca_copia(carpeta):
			return None
		ruta = crear_copia(carpeta / f"{PREFIJO_AUTOMATICA}{time.strftime('%Y%m%d_%H%M%S')}.zip", version, con_portapapeles, datos)
		for vieja in copias_automaticas(carpeta)[max(1, conservar):]:
			vieja.unlink(missing_ok=True)
		return ruta
	except ErrorCopia:
		return None
	except Exception:  # noqa: BLE001 - una copia fallida no debe molestar al usar el programa
		log.warning("No se pudo hacer la copia de seguridad automática", exc_info=True)
		return None
