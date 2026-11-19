"""Fragmentos de texto: textos guardados para insertarlos al instante (sin wx).

Como los expansores de texto (Beeftext, PhraseExpress): firmas, direcciones,
respuestas habituales... Cada fragmento tiene un nombre, una categoría, una
abreviatura opcional (para encontrarlo escribiéndola en el buscador) y el
texto, que admite variables:

- ``{fecha}`` 19/11/2026, ``{fecha_larga}`` jueves, 19 de noviembre de 2026
- ``{hora}`` 10:15, ``{dia}``, ``{mes}``, ``{anio}``
- ``{portapapeles}`` el texto copiado ahora mismo

Se guardan en ``data/db/fragmentos.json`` con escritura atómica.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app.core import paths
from app.services.emojis import normalizar

log = logging.getLogger(__name__)

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
VARIABLES = ("{fecha}", "{fecha_larga}", "{hora}", "{dia}", "{mes}", "{anio}", "{portapapeles}")


@dataclass
class Fragmento:
	nombre: str
	texto: str
	categoria: str = ""
	abreviatura: str = ""
	id: str = field(default_factory=lambda: uuid.uuid4().hex)
	usos: int = 0
	ultimo_uso: float = 0.0

	def resumen(self, maximo: int = 80) -> str:
		texto = " ".join(self.texto.split())
		return texto[:maximo] + ("..." if len(texto) > maximo else "")


def expandir(texto: str, ahora: time.struct_time | None = None, portapapeles: Callable[[], str] | None = None) -> tuple[str, int]:
	"""Sustituye las variables. Devuelve el texto y 0 (compatibilidad: antes se devolvía un retroceso del cursor)."""
	ahora = ahora or time.localtime()
	valores = {
		"{fecha}": time.strftime("%d/%m/%Y", ahora),
		"{fecha_larga}": f"{DIAS[ahora.tm_wday]}, {ahora.tm_mday} de {MESES[ahora.tm_mon - 1]} de {ahora.tm_year}",
		"{hora}": time.strftime("%H:%M", ahora),
		"{dia}": str(ahora.tm_mday),
		"{mes}": MESES[ahora.tm_mon - 1],
		"{anio}": str(ahora.tm_year),
	}
	for variable, valor in valores.items():
		texto = texto.replace(variable, valor)
	if "{portapapeles}" in texto:
		copiado = ""
		if portapapeles is not None:
			try:
				copiado = portapapeles()
			except Exception:  # noqa: BLE001 - portapapeles ocupado: se deja vacío
				log.debug("No se pudo leer el portapapeles para el fragmento", exc_info=True)
		texto = texto.replace("{portapapeles}", copiado)
	# Colocar el cursor con flechas simuladas no es fiable en todos los programas:
	# no se ofrece. Si un fragmento antiguo lo trae, se quita sin más.
	return texto.replace("{cursor}", ""), 0


class AlmacenFragmentos:
	"""Lista de fragmentos en JSON. Segura entre hilos."""

	def __init__(self, ruta: Path | None = None) -> None:
		self.ruta = ruta or (paths.ruta_base_datos() / "fragmentos.json")
		self._candado = threading.RLock()
		self._fragmentos: list[Fragmento] = []
		self._cargar()

	def _cargar(self) -> None:
		if not self.ruta.is_file():
			self._fragmentos = [
				Fragmento("Fecha de hoy", "{fecha_larga}", "Ejemplos", "fecha"),
				Fragmento("Firma", "Un saludo,\n\n(escriba aquí su nombre)", "Ejemplos", "firma"),
			]
			return
		try:
			datos = json.loads(self.ruta.read_text(encoding="utf-8"))
			campos = set(Fragmento.__dataclass_fields__)
			self._fragmentos = [Fragmento(**{k: v for k, v in d.items() if k in campos}) for d in datos if isinstance(d, dict)]
		except (OSError, ValueError, TypeError):
			apartado = self.ruta.with_name(f"fragmentos.danado-{time.strftime('%Y%m%d-%H%M%S')}.json")
			log.exception("Fragmentos dañados; se apartan como %s", apartado.name)
			try:
				os.replace(self.ruta, apartado)
			except OSError:
				log.exception("No se pudo apartar %s", self.ruta)
			self._fragmentos = []

	def guardar(self) -> bool:
		with self._candado:
			texto = json.dumps([asdict(f) for f in self._fragmentos], ensure_ascii=False, indent="\t")
			temporal = self.ruta.with_name(self.ruta.name + ".tmp")
			try:
				self.ruta.parent.mkdir(parents=True, exist_ok=True)
				with open(temporal, "w", encoding="utf-8", newline="\n") as archivo:
					archivo.write(texto)
					archivo.flush()
					os.fsync(archivo.fileno())
				os.replace(temporal, self.ruta)
				return True
			except OSError:
				log.exception("No se pudieron guardar los fragmentos")
				return False

	def todos(self) -> list[Fragmento]:
		with self._candado:
			return list(self._fragmentos)

	def categorias(self) -> list[str]:
		return sorted({f.categoria for f in self.todos() if f.categoria}, key=str.casefold)

	def buscar(self, texto: str = "", categoria: str = "") -> list[Fragmento]:
		"""Por abreviatura exacta primero; después por nombre, texto o categoría (sin tildes)."""
		palabras = normalizar(texto).split()
		resultado = []
		for fragmento in self.todos():
			if categoria and fragmento.categoria != categoria:
				continue
			if palabras:
				buscable = normalizar(f"{fragmento.abreviatura} {fragmento.nombre} {fragmento.categoria} {fragmento.texto}")
				if not all(p in buscable for p in palabras):
					continue
			resultado.append(fragmento)
		exacta = normalizar(texto.strip())
		resultado.sort(key=lambda f: (normalizar(f.abreviatura) != exacta or not exacta, -f.usos, f.nombre.casefold()))
		return resultado

	def agregar(self, fragmento: Fragmento) -> None:
		with self._candado:
			self._fragmentos.append(fragmento)
		self.guardar()

	def reemplazar(self, fragmento: Fragmento) -> None:
		with self._candado:
			self._fragmentos = [fragmento if f.id == fragmento.id else f for f in self._fragmentos]
		self.guardar()

	def eliminar(self, identificador: str) -> None:
		with self._candado:
			self._fragmentos = [f for f in self._fragmentos if f.id != identificador]
		self.guardar()

	def anotar_uso(self, identificador: str) -> None:
		with self._candado:
			for fragmento in self._fragmentos:
				if fragmento.id == identificador:
					fragmento.usos += 1
					fragmento.ultimo_uso = time.time()
		self.guardar()
