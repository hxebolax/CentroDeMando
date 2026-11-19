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

	COLUMNAS_LISTA = "id, tipo, texto, nombre, favorito, origen, creado, usado, veces, ancho, alto, archivos"

	def __init__(self, ruta: Path | None = None) -> None:
		self.ruta = ruta or (paths.ruta_base_datos() / "portapapeles.db")
		self._candado = threading.RLock()
		self._conexion = self._abrir()

	def _abrir(self) -> sqlite3.Connection:
		conexion = None
		try:
			conexion = sqlite3.connect(self.ruta, check_same_thread=False, timeout=5)
			conexion.execute("PRAGMA journal_mode=WAL")
			conexion.execute("PRAGMA synchronous=NORMAL")
			conexion.executescript(ESQUEMA)
			conexion.execute("PRAGMA integrity_check").fetchone()
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
			return conexion

	def cerrar(self) -> None:
		with self._candado:
			try:
				self._conexion.close()
			except sqlite3.Error:
				log.debug("Error al cerrar el historial", exc_info=True)

	@staticmethod
	def _elemento(fila: tuple) -> Elemento:
		id_, tipo, texto, nombre, favorito, origen, creado, usado, veces, ancho, alto, archivos = fila[:12]
		elemento = Elemento(
			id_, tipo, texto, nombre, bool(favorito), origen, creado, usado, veces, ancho, alto, json.loads(archivos) if archivos else []
		)
		if len(fila) > 12:
			elemento.html = fila[12] or b""
			elemento.imagen = fila[13] or b""
		return elemento

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
				cursor = self._conexion.execute(
					"INSERT INTO elementos (huella, tipo, texto, html, archivos, imagen, ancho, alto, origen, creado, usado)"
					" VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
					(
						huella,
						contenido.tipo,
						contenido.texto,
						contenido.html or None,
						json.dumps(contenido.archivos, ensure_ascii=False) if contenido.archivos else "",
						contenido.imagen or None,
						ancho,
						alto,
						contenido.origen,
						ahora,
						ahora,
					),
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

	def listar(self, filtro: str = FILTRO_TODO, buscar: str = "", limite: int = 5000) -> list[Elemento]:
		"""Elementos del más reciente al más antiguo, sin imágenes."""
		condiciones, valores = [], []
		if filtro == FILTRO_FAVORITOS:
			condiciones.append("favorito = 1")
		elif filtro in (TIPO_TEXTO, TIPO_IMAGEN, TIPO_ARCHIVOS):
			condiciones.append("tipo = ?")
			valores.append(filtro)
		for palabra in buscar.split():
			condiciones.append("(texto LIKE ? ESCAPE '\\' OR nombre LIKE ? ESCAPE '\\' OR archivos LIKE ? ESCAPE '\\')")
			patron = "%" + palabra.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
			valores += [patron, patron, patron]
		donde = (" WHERE " + " AND ".join(condiciones)) if condiciones else ""
		consulta = f"SELECT {self.COLUMNAS_LISTA} FROM elementos{donde} ORDER BY usado DESC LIMIT ?"
		with self._candado:
			filas = self._conexion.execute(consulta, (*valores, limite)).fetchall()
		return [self._elemento(f) for f in filas]

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
	guardar_html: bool = True
	guardar_archivos: bool = True
	guardar_imagenes: bool = True
	maximo_imagen_mb: int = 20
	ignorar_privados: bool = True
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
		elemento = self.historial.agregar(contenido, preferencias.maximo)
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

	def pegar(self, identificador: int, hwnd: int) -> bool:
		"""Pega el elemento en ``hwnd`` (llamar desde un hilo: espera y duerme)."""
		from app.services import pegado

		elemento = self.historial.obtener(identificador)
		if elemento is None:
			return False
		preferencias = self._preferencias()
		self.historial.marcar_usado(identificador)
		return pegado.pegar_contenido(
			hwnd,
			elemento.contenido(),
			self.monitor.hwnd,
			self.anotar_propia,
			restaurar=preferencias.restaurar_tras_pegar,
			retraso_restaurar=preferencias.retraso_restaurar_ms / 1000,
			metodo=preferencias.metodo_pegado,
		)

	def copiar_texto(self, texto: str) -> None:
		"""Copia un texto suelto (por ejemplo, un emoticono) sin guardarlo como copia propia."""
		pw.escribir(Contenido(texto=texto), self.monitor.hwnd)
