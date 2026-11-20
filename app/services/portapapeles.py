"""Historial del portapapeles: base de datos y servicio de captura (sin wx).

Base de datos: SQLite en ``data/db/portapapeles.db`` (portable, nunca se
distribuye). Una sola conexión protegida por un candado: el monitor escribe
desde su hilo y la interfaz lee desde el suyo.

- Sin duplicados: si se copia algo que ya está, sube arriba y conserva su
  nombre y si es favorito.
- Límite de elementos configurable; al pasarse se borran los más antiguos
  que no son favoritos (los favoritos no se pierden nunca por el límite).
- Las listas se piden sin las imágenes (pueden ocupar megas); la imagen se
  lee solo al copiar o pegar ese elemento.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from app.core import paths
from app.services import portapapeles_win32 as pw
from app.services.portapapeles_win32 import TIPO_ARCHIVOS, TIPO_IMAGEN, TIPO_TEXTO, Contenido

log = logging.getLogger(__name__)

ESQUEMA = """
CREATE TABLE IF NOT EXISTS elementos (
	id INTEGER PRIMARY KEY AUTOINCREMENT,
	huella TEXT NOT NULL UNIQUE,
	tipo TEXT NOT NULL,
	texto TEXT NOT NULL DEFAULT '',
	html BLOB,
	archivos TEXT NOT NULL DEFAULT '',
	imagen BLOB,
	ancho INTEGER NOT NULL DEFAULT 0,
	alto INTEGER NOT NULL DEFAULT 0,
	nombre TEXT NOT NULL DEFAULT '',
	favorito INTEGER NOT NULL DEFAULT 0,
	origen TEXT NOT NULL DEFAULT '',
	creado REAL NOT NULL,
	usado REAL NOT NULL,
	veces INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS indice_usado ON elementos (usado DESC);
"""

# Texto que se ve en lugar de un elemento cifrado por otra cuenta de Windows.
NO_DESCIFRABLE = "(cifrado por otro usuario de Windows o en otro equipo: no se puede leer)"


def _cifrar_texto(texto: str) -> bytes:
	from app.core import dpapi

	return dpapi.cifrar(texto.encode("utf-8", "surrogatepass"))


def _descifrar_texto(valor) -> str:
	from app.core import dpapi

	if not valor:
		return ""
	if isinstance(valor, str):  # guardado antes de cifrar (no debería pasar)
		return valor
	return dpapi.descifrar(valor).decode("utf-8", "surrogatepass")


def _cifrar_binario(datos) -> bytes | None:
	from app.core import dpapi

	return dpapi.cifrar(bytes(datos)) if datos else None


def _descifrar_binario(datos) -> bytes:
	from app.core import dpapi

	return dpapi.descifrar(bytes(datos)) if datos else b""


def _tipo_titulo(texto: str) -> str:
	"""Mayúscula al principio de cada palabra, sin tocar el resto (``str.title`` estropea «l'agua»)."""
	return " ".join(p[:1].upper() + p[1:].lower() for p in texto.split(" "))


# Transformaciones al pegar: (nombre en el menú, función). Solo afectan a textos.
TRANSFORMACIONES: dict[str, tuple[str, Callable[[str], str]]] = {
	"sin_formato": ("Como texto sin formato", lambda t: t),
	"una_linea": ("En una sola línea", lambda t: " ".join(t.split())),
	"recortar": ("Sin espacios al principio ni al final de cada línea", lambda t: "\n".join(l.strip() for l in t.splitlines())),
	"mayusculas": ("En MAYÚSCULAS", str.upper),
	"minusculas": ("En minúsculas", str.lower),
	"titulo": ("Con Mayúscula En Cada Palabra", _tipo_titulo),
	"frase": ("Con mayúscula solo al principio", lambda t: t[:1].upper() + t[1:].lower()),
}

FILTRO_TODO = "todo"
FILTRO_FAVORITOS = "favoritos"
FILTRO_TEXTO = TIPO_TEXTO
FILTRO_IMAGENES = TIPO_IMAGEN
FILTRO_ARCHIVOS = TIPO_ARCHIVOS


@dataclass
class Elemento:
	"""Un elemento del historial (sin la imagen, salvo que se pida con ``obtener``)."""

	id: int
	tipo: str
	texto: str = ""
	nombre: str = ""
	favorito: bool = False
	origen: str = ""
	creado: float = 0.0
	usado: float = 0.0
	veces: int = 1
	ancho: int = 0
	alto: int = 0
	archivos: list[str] = field(default_factory=list)
	html: bytes = b""
	imagen: bytes = b""

	def resumen(self, maximo: int = 150) -> str:
		"""Lo que se lee en las listas: el nombre puesto por el usuario o el principio del contenido."""
		if self.nombre:
			return self.nombre
		if self.tipo == TIPO_IMAGEN:
			return f"Imagen de {self.ancho} por {self.alto}"
		if self.tipo == TIPO_ARCHIVOS:
			nombres = [Path(a).name for a in self.archivos]
			if len(nombres) == 1:
				return f"Archivo {nombres[0]}"
			return f"{len(nombres)} archivos: " + ", ".join(nombres[:5]) + ("..." if len(nombres) > 5 else "")
		texto = " ".join(self.texto.split())
		return texto[:maximo] + ("..." if len(texto) > maximo else "") if texto else "(texto en blanco)"

	def descripcion_tipo(self) -> str:
		if self.tipo == TIPO_IMAGEN:
			return "Imagen"
		if self.tipo == TIPO_ARCHIVOS:
			return "Archivos"
		lineas = self.texto.count("\n") + 1
		caracteres = len(self.texto)
		return f"Texto, {caracteres} caracteres" + (f", {lineas} líneas" if lineas > 1 else "")

	def contenido(self) -> Contenido:
		return Contenido(self.tipo, texto=self.texto, html=self.html, archivos=list(self.archivos), imagen=self.imagen)

	def texto_completo(self) -> str:
		"""Para la vista previa: todo el texto o la lista de archivos."""
		if self.tipo == TIPO_ARCHIVOS:
			return "\n".join(self.archivos)
		if self.tipo == TIPO_IMAGEN:
			return f"Imagen de {self.ancho} por {self.alto} píxeles."
		return self.texto


def describir_tiempo(instante: float, ahora: float | None = None) -> str:
	"""«hace 3 minutos», «hoy a las 10:15», «12/11/2026 18:02»."""
	ahora = time.time() if ahora is None else ahora
	diferencia = max(0, ahora - instante)
	if diferencia < 60:
		return "hace un momento"
	if diferencia < 3600:
		minutos = int(diferencia // 60)
		return "hace 1 minuto" if minutos == 1 else f"hace {minutos} minutos"
	local, hoy = time.localtime(instante), time.localtime(ahora)
	if local.tm_yday == hoy.tm_yday and local.tm_year == hoy.tm_year:
		return time.strftime("hoy a las %H:%M", local)
	return time.strftime("%d/%m/%Y %H:%M", local)


class HistorialPortapapeles:
	"""Acceso a la base de datos del historial. Seguro entre hilos."""

	COLUMNAS_LISTA = "id, tipo, texto, nombre, favorito, origen, creado, usado, veces, ancho, alto, archivos, cifrado"

	def __init__(self, ruta: Path | None = None) -> None:
		self.ruta = ruta or (paths.ruta_base_datos() / "portapapeles.db")
		self._candado = threading.RLock()
		self._conexion = self._abrir()
		# Guardar lo nuevo cifrado con DPAPI (opción «Cifrar el historial»).
		self.cifrar = False

	@staticmethod
	def _migrar(conexion: sqlite3.Connection) -> None:
		"""Añade las columnas de versiones nuevas a una base antigua."""
		columnas = {fila[1] for fila in conexion.execute("PRAGMA table_info(elementos)")}
		if "cifrado" not in columnas:
			conexion.execute("ALTER TABLE elementos ADD COLUMN cifrado INTEGER NOT NULL DEFAULT 0")
			conexion.commit()

	def _abrir(self) -> sqlite3.Connection:
		conexion = None
		try:
			conexion = sqlite3.connect(self.ruta, check_same_thread=False, timeout=5)
			conexion.execute("PRAGMA journal_mode=WAL")
			conexion.execute("PRAGMA synchronous=NORMAL")
			conexion.executescript(ESQUEMA)
			conexion.execute("PRAGMA integrity_check").fetchone()
			self._migrar(conexion)
			return conexion
		except sqlite3.DatabaseError:
			# Base dañada: se aparta para estudiarla y se empieza de cero.
			log.exception("El historial %s está dañado; se aparta y se crea uno nuevo.", self.ruta)
			if conexion is not None:
				# Windows no deja renombrar un archivo abierto.
				conexion.close()
			apartado = self.ruta.with_name(f"{self.ruta.stem}.danado-{time.strftime('%Y%m%d-%H%M%S')}.db")
			try:
				self.ruta.replace(apartado)
			except OSError:
				log.exception("No se pudo apartar %s", self.ruta)
			conexion = sqlite3.connect(self.ruta, check_same_thread=False, timeout=5)
			conexion.executescript(ESQUEMA)
			self._migrar(conexion)
			return conexion

	def cerrar(self) -> None:
		with self._candado:
			try:
				self._conexion.close()
			except sqlite3.Error:
				log.debug("Error al cerrar el historial", exc_info=True)

	@staticmethod
	def _elemento(fila: tuple) -> Elemento:
		id_, tipo, texto, nombre, favorito, origen, creado, usado, veces, ancho, alto, archivos, cifrado = fila[:13]
		html, imagen = (fila[13] or b"", fila[14] or b"") if len(fila) > 13 else (b"", b"")
		if cifrado:
			from app.core import dpapi

			try:
				texto = _descifrar_texto(texto)
				archivos = _descifrar_texto(archivos)
				html, imagen = _descifrar_binario(html), _descifrar_binario(imagen)
			except dpapi.ErrorDpapi:
				texto, archivos, html, imagen = NO_DESCIFRABLE, "", b"", b""
		elemento = Elemento(
			id_, tipo, texto, nombre, bool(favorito), origen, creado, usado, veces, ancho, alto, json.loads(archivos) if archivos else []
		)
		if len(fila) > 13:
			elemento.html = html
			elemento.imagen = imagen
		return elemento

	def _valores_guardados(self, texto: str, html, archivos: str, imagen, cifrar: bool) -> tuple:
		"""(texto, html, archivos, imagen, cifrado) tal y como van a la base."""
		if not cifrar:
			return texto, html or None, archivos, imagen or None, 0
		return _cifrar_texto(texto), _cifrar_binario(html), _cifrar_texto(archivos) if archivos else "", _cifrar_binario(imagen), 1

	def agregar(self, contenido: Contenido, maximo: int = 0) -> Elemento:
		"""Guarda el contenido (o sube arriba el que ya estaba) y aplica el límite."""
		ahora = time.time()
		huella = contenido.huella()
		ancho, alto = pw.dimensiones_dib(contenido.imagen) if contenido.tipo == TIPO_IMAGEN else (0, 0)
		with self._candado, self._conexion:
			existe = self._conexion.execute("SELECT id FROM elementos WHERE huella = ?", (huella,)).fetchone()
			if existe:
				self._conexion.execute(
					"UPDATE elementos SET usado = ?, veces = veces + 1, origen = COALESCE(NULLIF(?, ''), origen) WHERE id = ?",
					(ahora, contenido.origen, existe[0]),
				)
				identificador = existe[0]
			else:
				texto, html, archivos, imagen, cifrado = self._valores_guardados(
					contenido.texto,
					contenido.html,
					json.dumps(contenido.archivos, ensure_ascii=False) if contenido.archivos else "",
					contenido.imagen,
					self.cifrar,
				)
				cursor = self._conexion.execute(
					"INSERT INTO elementos (huella, tipo, texto, html, archivos, imagen, ancho, alto, origen, creado, usado, cifrado)"
					" VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
					(huella, contenido.tipo, texto, html, archivos, imagen, ancho, alto, contenido.origen, ahora, ahora, cifrado),
				)
				identificador = cursor.lastrowid
			if maximo > 0:
				self._recortar(maximo)
		return self.obtener(identificador, completo=False)

	def _recortar(self, maximo: int) -> int:
		"""Borra los más antiguos que no son favoritos hasta quedar en ``maximo``."""
		total = self._conexion.execute("SELECT COUNT(*) FROM elementos").fetchone()[0]
		sobran = total - maximo
		if sobran <= 0:
			return 0
		cursor = self._conexion.execute(
			"DELETE FROM elementos WHERE id IN (SELECT id FROM elementos WHERE favorito = 0 ORDER BY usado ASC LIMIT ?)", (sobran,)
		)
		return cursor.rowcount

	def recortar(self, maximo: int) -> int:
		with self._candado, self._conexion:
			return self._recortar(maximo)

	def caducar(self, dias: int) -> int:
		"""Borra lo que no se usa desde hace más de ``dias`` días (nunca los favoritos)."""
		if dias <= 0:
			return 0
		with self._candado, self._conexion:
			return self._conexion.execute("DELETE FROM elementos WHERE favorito = 0 AND usado < ?", (time.time() - dias * 86400,)).rowcount

	def listar(self, filtro: str = FILTRO_TODO, buscar: str = "", limite: int = 5000) -> list[Elemento]:
		"""Elementos del más reciente al más antiguo, sin imágenes."""
		condiciones, valores = [], []
		if filtro == FILTRO_FAVORITOS:
			condiciones.append("favorito = 1")
		elif filtro in (TIPO_TEXTO, TIPO_IMAGEN, TIPO_ARCHIVOS):
			condiciones.append("tipo = ?")
			valores.append(filtro)
		palabras = buscar.split()
		base, valores_base = list(condiciones), list(valores)
		for palabra in palabras:
			condiciones.append("(texto LIKE ? ESCAPE '\\' OR nombre LIKE ? ESCAPE '\\' OR archivos LIKE ? ESCAPE '\\')")
			patron = "%" + palabra.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
			valores += [patron, patron, patron]
		if palabras:
			condiciones.append("cifrado = 0")
		donde = (" WHERE " + " AND ".join(condiciones)) if condiciones else ""
		consulta = f"SELECT {self.COLUMNAS_LISTA} FROM elementos{donde} ORDER BY usado DESC LIMIT ?"
		with self._candado:
			filas = self._conexion.execute(consulta, (*valores, limite)).fetchall()
			cifradas = []
			if palabras:
				# Lo cifrado no se puede buscar con SQL: se descifra y se busca aquí.
				donde_cifradas = " WHERE " + " AND ".join([*base, "cifrado = 1"])
				cifradas = self._conexion.execute(
					f"SELECT {self.COLUMNAS_LISTA} FROM elementos{donde_cifradas} ORDER BY usado DESC", valores_base
				).fetchall()
		elementos = [self._elemento(f) for f in filas]
		if cifradas:
			buscadas = [p.casefold() for p in palabras]
			for fila in cifradas:
				elemento = self._elemento(fila)
				pajar = " ".join([elemento.texto, elemento.nombre, *elemento.archivos]).casefold()
				if all(p in pajar for p in buscadas):
					elementos.append(elemento)
			elementos.sort(key=lambda e: e.usado, reverse=True)
		if palabras:
			# Al buscar, los favoritos primero (sin perder el orden por uso dentro de cada grupo).
			elementos.sort(key=lambda e: not e.favorito)
		return elementos[:limite]

	def contar_cifrados(self, cifrados: bool = True) -> int:
		with self._candado:
			return self._conexion.execute("SELECT COUNT(*) FROM elementos WHERE cifrado = ?", (int(cifrados),)).fetchone()[0]

	def cambiar_cifrado(self, cifrar: bool, al_avanzar=None) -> int:
		"""Cifra (o descifra) todo lo guardado; devuelve cuántos elementos cambió.

		Va por tandas para no bloquear el historial mucho rato. Los que no se
		pueden descifrar (de otra cuenta de Windows) se dejan como están.
		"""
		from app.core import dpapi

		self.cifrar = cifrar
		cambiados = 0
		ultimo = 0
		while True:
			with self._candado:
				filas = self._conexion.execute(
					"SELECT id, texto, html, archivos, imagen FROM elementos WHERE cifrado = ? AND id > ? ORDER BY id LIMIT 100",
					(int(not cifrar), ultimo),
				).fetchall()
				if not filas:
					break
				with self._conexion:
					for id_, texto, html, archivos, imagen in filas:
						ultimo = id_
						try:
							if not cifrar:
								texto, archivos = _descifrar_texto(texto), _descifrar_texto(archivos)
								html, imagen = _descifrar_binario(html), _descifrar_binario(imagen)
							nuevos = self._valores_guardados(texto, html, archivos, imagen, cifrar)
						except dpapi.ErrorDpapi:
							continue
						self._conexion.execute(
							"UPDATE elementos SET texto = ?, html = ?, archivos = ?, imagen = ?, cifrado = ? WHERE id = ?", (*nuevos, id_)
						)
						cambiados += 1
			if al_avanzar is not None:
				al_avanzar(cambiados)
		if cambiados:
			with self._candado:
				# Que no queden restos del texto sin cifrar en las páginas libres del archivo.
				self._conexion.execute("VACUUM")
		log.info("Historial del portapapeles %s: %d elementos.", "cifrado" if cifrar else "descifrado", cambiados)
		return cambiados

	def obtener(self, identificador: int, completo: bool = True) -> Elemento | None:
		columnas = self.COLUMNAS_LISTA + (", html, imagen" if completo else "")
		with self._candado:
			fila = self._conexion.execute(f"SELECT {columnas} FROM elementos WHERE id = ?", (identificador,)).fetchone()
		return self._elemento(fila) if fila else None

	def contar(self) -> int:
		with self._candado:
			return self._conexion.execute("SELECT COUNT(*) FROM elementos").fetchone()[0]

	def marcar_usado(self, identificador: int) -> None:
		with self._candado, self._conexion:
			self._conexion.execute("UPDATE elementos SET usado = ?, veces = veces + 1 WHERE id = ?", (time.time(), identificador))

	def poner_favorito(self, identificador: int, favorito: bool) -> None:
		with self._candado, self._conexion:
			self._conexion.execute("UPDATE elementos SET favorito = ? WHERE id = ?", (int(favorito), identificador))

	def renombrar(self, identificador: int, nombre: str) -> None:
		with self._candado, self._conexion:
			self._conexion.execute("UPDATE elementos SET nombre = ? WHERE id = ?", (nombre.strip(), identificador))

	def eliminar(self, identificadores: list[int]) -> int:
		with self._candado, self._conexion:
			cursor = self._conexion.executemany("DELETE FROM elementos WHERE id = ?", [(i,) for i in identificadores])
			return cursor.rowcount

	def vaciar(self, incluir_favoritos: bool = False) -> int:
		with self._candado, self._conexion:
			cursor = self._conexion.execute("DELETE FROM elementos" + ("" if incluir_favoritos else " WHERE favorito = 0"))
			borrados = cursor.rowcount
		with self._candado:
			self._conexion.execute("VACUUM")
		return borrados

	def exportar_texto(self, ruta: Path) -> int:
		"""Escribe los textos del historial en un archivo de texto, separados por una línea."""
		elementos = [e for e in self.listar(limite=1_000_000) if e.tipo == TIPO_TEXTO]
		separador = "\n" + "-" * 40 + "\n"
		ruta.write_text(separador.join(e.texto for e in elementos), encoding="utf-8")
		return len(elementos)


@dataclass
class PreferenciasPortapapeles:
	activo: bool = True
	maximo: int = 500
	dias: int = 0
	guardar_html: bool = True
	guardar_archivos: bool = True
	guardar_imagenes: bool = True
	maximo_imagen_mb: int = 20
	ignorar_privados: bool = True
	cifrar: bool = False
	programas_excluidos: tuple[str, ...] = ()
	restaurar_tras_pegar: bool = True
	retraso_restaurar_ms: int = 500
	metodo_pegado: str = "control_v"


class ServicioPortapapeles:
	"""Monitor + historial: guarda lo que se copia y avisa a la interfaz."""

	def __init__(
		self,
		preferencias: Callable[[], PreferenciasPortapapeles] | None = None,
		historial: HistorialPortapapeles | None = None,
	) -> None:
		self._preferencias = preferencias or PreferenciasPortapapeles
		self._historial = historial
		self.monitor = pw.MonitorPortapapeles(self._al_cambiar)
		self._propias: set[int] = set()
		self._candado = threading.Lock()
		self.pausado = False
		# Avisos (desde el hilo del monitor): la interfaz usa wx.CallAfter.
		self.al_agregar: Callable[[Elemento], None] | None = None

	@property
	def historial(self) -> HistorialPortapapeles:
		if self._historial is None:
			self._historial = HistorialPortapapeles()
		return self._historial

	def iniciar(self) -> None:
		_ = self.historial
		self.monitor.iniciar()

	def detener(self) -> None:
		self.monitor.detener()
		if self._historial is not None:
			self._historial.cerrar()

	def anotar_propia(self, secuencia: int) -> None:
		"""Una escritura nuestra en el portapapeles: el monitor no debe guardarla otra vez."""
		with self._candado:
			self._propias.add(secuencia)
			if len(self._propias) > 50:
				self._propias = set(sorted(self._propias)[-20:])

	def _es_propia(self) -> bool:
		with self._candado:
			return pw.numero_secuencia() in self._propias

	def _al_cambiar(self) -> None:
		"""Hilo del monitor: lee y guarda lo copiado si procede."""
		preferencias = self._preferencias()
		if not preferencias.activo or self.pausado or self._es_propia():
			return
		if preferencias.ignorar_privados and pw.es_privado():
			log.info("Contenido marcado como privado: no se guarda en el historial.")
			return
		origen = pw.nombre_programa_dueno()
		if origen and origen.casefold() in {p.strip().casefold() for p in preferencias.programas_excluidos if p.strip()}:
			log.info("Copia de %s ignorada (programa excluido).", origen)
			return
		try:
			contenido = pw.leer(
				con_html=preferencias.guardar_html,
				con_archivos=preferencias.guardar_archivos,
				con_imagenes=preferencias.guardar_imagenes,
				maximo_imagen=preferencias.maximo_imagen_mb * 1024 * 1024,
			)
		except pw.PortapapelesOcupado:
			log.info("El portapapeles estaba ocupado; no se pudo leer la copia.")
			return
		if contenido is None or contenido.vacio:
			return
		contenido.origen = origen
		self.historial.cifrar = preferencias.cifrar
		elemento = self.historial.agregar(contenido, preferencias.maximo)
		self.historial.caducar(preferencias.dias)
		if elemento is not None and self.al_agregar is not None:
			self.al_agregar(elemento)

	def copiar(self, identificador: int) -> Elemento | None:
		"""Pone el elemento en el portapapeles (sin pegarlo) y lo sube arriba."""
		elemento = self.historial.obtener(identificador)
		if elemento is None:
			return None
		self.anotar_propia(pw.escribir(elemento.contenido(), self.monitor.hwnd))
		self.historial.marcar_usado(identificador)
		return elemento

	def pegar(self, identificador: int, hwnd: int, transformacion: str | None = None) -> bool:
		"""Pega el elemento en ``hwnd`` (llamar desde un hilo: espera y duerme).

		:param transformacion: clave de ``TRANSFORMACIONES``: pega solo el texto,
			transformado (sin formato HTML).
		"""
		from app.services import pegado

		elemento = self.historial.obtener(identificador)
		if elemento is None:
			return False
		preferencias = self._preferencias()
		self.historial.marcar_usado(identificador)
		contenido = elemento.contenido()
		if transformacion in TRANSFORMACIONES and elemento.tipo != TIPO_IMAGEN:
			contenido = Contenido(texto=TRANSFORMACIONES[transformacion][1](elemento.texto_completo()))
		return pegado.pegar_contenido(
			hwnd,
			contenido,
			self.monitor.hwnd,
			self.anotar_propia,
			restaurar=preferencias.restaurar_tras_pegar,
			retraso_restaurar=preferencias.retraso_restaurar_ms / 1000,
			metodo=preferencias.metodo_pegado,
		)

	def copiar_texto(self, texto: str) -> None:
		"""Copia un texto suelto (por ejemplo, un emoticono) sin guardarlo como copia propia."""
		pw.escribir(Contenido(texto=texto), self.monitor.hwnd)
