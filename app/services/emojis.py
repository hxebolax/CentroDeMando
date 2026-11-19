"""Catálogo de emoticonos en español (sin wx).

Datos: ``data/emojis/emojis_es.json``, generado con ``tools/generar_emojis.py``
a partir de emoji-test.txt y CLDR (Unicode License V3). Incluye todos los
emojis completos de Unicode con nombre y palabras clave en español, más los
símbolos tipográficos con nombre en CLDR y una pequeña colección de kaomoji.

La búsqueda no distingue mayúsculas ni tildes, busca en el nombre y en las
palabras clave y exige que aparezcan TODAS las palabras escritas («corazón
rojo» encuentra ❤️). Ordena primero los nombres que empiezan por lo buscado.
"""

from __future__ import annotations

import json
import logging
import threading
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from app.core import paths

log = logging.getLogger(__name__)

TONOS = ("", "\U0001f3fb", "\U0001f3fc", "\U0001f3fd", "\U0001f3fe", "\U0001f3ff")
NOMBRES_TONOS = ("Sin tono (amarillo)", "Claro", "Claro medio", "Medio", "Oscuro medio", "Oscuro")
SELECTOR = "\ufe0f"

GRUPO_RECIENTES = "Usados recientemente"
GRUPO_FAVORITOS = "Favoritos"
GRUPO_SIMBOLOS = "Símbolos tipográficos"
GRUPO_KAOMOJI = "Kaomoji"

# Kaomoji: caras hechas con caracteres, como en el panel de Windows.
KAOMOJI: list[tuple[str, str]] = [
	("(◕‿◕)", "contento"),
	("(＾▽＾)", "alegre"),
	("(≧◡≦)", "encantado"),
	("ヽ(•‿•)ノ", "celebrando"),
	("\\(^o^)/", "hurra"),
	("(｡♥‿♥｡)", "enamorado"),
	("(づ｡◕‿‿◕｡)づ", "abrazo"),
	("(*^3^)/~☆", "beso"),
	("(╥﹏╥)", "llorando"),
	("(ಥ﹏ಥ)", "muy triste"),
	("(._.)", "decaído"),
	("(╯°□°）╯︵ ┻━┻", "tirar la mesa, enfado"),
	("┬─┬ノ( º _ ºノ)", "colocar la mesa, calma"),
	("(ಠ_ಠ)", "mirada de desaprobación"),
	("(¬_¬)", "sospecha"),
	("¯\\_(ツ)_/¯", "encogerse de hombros, ni idea"),
	("(⊙_⊙)", "asombro"),
	("(°o°)", "sorpresa"),
	("(-_-) zzZ", "dormido"),
	("(=^･ω･^=)", "gato"),
	("U・ᴥ・U", "perro"),
	("ʕ•ᴥ•ʔ", "oso"),
	("(っ˘ڡ˘ς)", "comiendo, rico"),
	("( •_•)>⌐■-■", "ponerse gafas de sol"),
	("(⌐■_■)", "con gafas de sol, guay"),
	("(ง'̀-'́)ง", "listo para pelear"),
	("(￣▽￣)ノ", "saludo"),
	("( ˘▽˘)っ♨", "café caliente"),
	("(^_^)b", "pulgar arriba, bien"),
	("m(_ _)m", "reverencia, perdón"),
]


@dataclass(frozen=True)
class Emoji:
	caracter: str
	nombre: str
	claves: tuple[str, ...] = ()
	grupo: str = ""
	version: str = ""
	base: str = ""  # emoji sin tono si este es una variante de tono

	def describir(self) -> str:
		"""«😀 cara sonriendo»: lo que se ve y se oye en las listas."""
		return f"{self.caracter} {self.nombre}"


def normalizar(texto: str) -> str:
	"""Minúsculas y sin tildes, para buscar «corazon» y encontrar «corazón»."""
	descompuesto = unicodedata.normalize("NFD", texto.casefold())
	return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


class CatalogoEmojis:
	"""Carga perezosa del JSON (unos 0,5 MB) la primera vez que se necesita."""

	def __init__(self, ruta: Path | None = None) -> None:
		self._ruta = ruta
		self._candado = threading.Lock()
		self._cargado = False
		self._grupos: list[str] = []
		self._por_grupo: dict[str, list[Emoji]] = {}
		self._todos: list[Emoji] = []
		self._por_caracter: dict[str, Emoji] = {}
		self._variantes: dict[tuple[str, str], str] = {}
		self._indice: list[tuple[str, str, Emoji]] = []
		self.error = ""

	def _cargar(self) -> None:
		with self._candado:
			if self._cargado:
				return
			self._cargado = True
			ruta = self._ruta or (paths.ruta_emojis() / "emojis_es.json")
			try:
				datos = json.loads(ruta.read_text(encoding="utf-8"))
			except (OSError, ValueError) as error:
				log.exception("No se pudieron cargar los emoticonos de %s", ruta)
				self.error = f"No se encuentran los datos de emoticonos ({ruta.name}): {error}"
				datos = {"grupos": [], "emojis": [], "simbolos": []}
			grupos = list(datos.get("grupos", []))
			for caracter, nombre, claves, grupo, version, base in datos.get("emojis", []):
				emoji = Emoji(caracter, nombre, tuple(c for c in claves.split("|") if c), grupos[grupo], version, base)
				self._agregar(emoji)
				if base:
					tono = next((t for t in TONOS[1:] if t in caracter), "")
					# Solo las variantes de un único tono: «personas con tonos distintos» no se eligen así.
					if tono and sum(caracter.count(t) for t in TONOS[1:]) == 1:
						self._variantes[(base.replace(SELECTOR, ""), tono)] = caracter
			for caracter, nombre, claves in datos.get("simbolos", []):
				self._agregar(Emoji(caracter, nombre, tuple(c for c in claves.split("|") if c), GRUPO_SIMBOLOS))
			for caracter, nombre in KAOMOJI:
				self._agregar(Emoji(caracter, nombre, tuple(nombre.split(", ")), GRUPO_KAOMOJI))
			self._grupos = [*grupos, GRUPO_SIMBOLOS, GRUPO_KAOMOJI]
			log.info("Emoticonos cargados: %d.", len(self._todos))

	@property
	def grupos(self) -> list[str]:
		"""Grupos en el orden de Unicode, más símbolos tipográficos y kaomoji."""
		self._cargar()
		return list(self._grupos)

	def _agregar(self, emoji: Emoji) -> None:
		self._todos.append(emoji)
		self._por_grupo.setdefault(emoji.grupo, []).append(emoji)
		self._por_caracter.setdefault(emoji.caracter, emoji)
		self._indice.append((normalizar(emoji.nombre), normalizar(" ".join(emoji.claves)), emoji))

	# ── Consultas ───────────────────────────────────────────────────────────

	def obtener(self, caracter: str) -> Emoji | None:
		self._cargar()
		return self._por_caracter.get(caracter) or self._por_caracter.get(caracter.replace(SELECTOR, ""))

	def del_grupo(self, grupo: str, con_tonos: bool = False) -> list[Emoji]:
		"""Emojis de un grupo en el orden de Unicode; sin las variantes de tono salvo que se pidan."""
		self._cargar()
		lista = self._por_grupo.get(grupo, [])
		return list(lista) if con_tonos else [e for e in lista if not e.base]

	def buscar(self, texto: str, limite: int = 500, con_tonos: bool = False) -> list[Emoji]:
		"""Emojis cuyo nombre o palabras clave contienen todas las palabras de ``texto``."""
		self._cargar()
		palabras = normalizar(texto).split()
		if not palabras:
			return []
		frase = " ".join(palabras)
		resultados: list[tuple[int, int, Emoji]] = []
		for posicion, (nombre, claves, emoji) in enumerate(self._indice):
			if emoji.base and not con_tonos:
				continue
			if not all(p in nombre or p in claves for p in palabras):
				continue
			if nombre == frase:
				prioridad = 0
			elif nombre.startswith(frase):
				prioridad = 1
			elif all(p in nombre for p in palabras):
				prioridad = 2
			else:
				prioridad = 3
			resultados.append((prioridad, posicion, emoji))
		resultados.sort(key=lambda r: (r[0], r[1]))
		return [r[2] for r in resultados[:limite]]

	def con_tono(self, caracter: str, tono: int) -> str:
		"""Variante con el tono de piel ``tono`` (0 = ninguno) si existe; si no, el mismo carácter."""
		self._cargar()
		if not 0 < tono < len(TONOS):
			return caracter
		return self._variantes.get((caracter.replace(SELECTOR, ""), TONOS[tono]), caracter)

	def admite_tono(self, caracter: str) -> bool:
		self._cargar()
		return (caracter.replace(SELECTOR, ""), TONOS[1]) in self._variantes

	def lista(self, caracteres: list[str]) -> list[Emoji]:
		"""Convierte caracteres guardados (recientes, favoritos) en emojis conocidos."""
		resultado = []
		for caracter in caracteres:
			emoji = self.obtener(caracter)
			if emoji is None:
				base = "".join(c for c in caracter if c not in TONOS[1:])
				conocido = self.obtener(base)
				emoji = Emoji(caracter, conocido.nombre if conocido else caracter, grupo=conocido.grupo if conocido else "")
			resultado.append(emoji)
		return resultado


def anotar_reciente(recientes: list[str], caracter: str, maximo: int = 40) -> list[str]:
	"""Pone ``caracter`` el primero de la lista de recientes, sin repetir."""
	nueva = [caracter, *(c for c in recientes if c != caracter)]
	return nueva[: max(maximo, 1)]


_catalogo: CatalogoEmojis | None = None


def catalogo() -> CatalogoEmojis:
	"""Catálogo compartido por toda la aplicación."""
	global _catalogo
	if _catalogo is None:
		_catalogo = CatalogoEmojis()
	return _catalogo
