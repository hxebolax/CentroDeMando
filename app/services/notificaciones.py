"""Historial de notificaciones de Windows y de las aplicaciones (sin wx).

Fuente: ``UserNotificationListener`` (API oficial de WinRT). Funciona en
aplicaciones no empaquetadas si en Configuración, Privacidad y seguridad,
Notificaciones, está permitido que las aplicaciones accedan a ellas. Da el
identificador, la aplicación (AUMID y nombre legible), la hora y los textos.

Windows no avisa de los cambios a las aplicaciones no empaquetadas (el evento
``NotificationChanged`` falla), así que un hilo consulta la lista cada pocos
segundos y guarda las que no conocía. Así se capturan también las que llegan
con «No molestar» o las que el usuario descarta enseguida (si duran más que
el intervalo). Windows borra sus notificaciones al descartarlas o al
caducar: por eso el historial propio es lo único que no se pierde.

Base de datos: SQLite en ``data/db/notificaciones.db``.
"""

from __future__ import annotations

import asyncio
import csv
import logging
import os
import queue
import sqlite3
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.core import paths

log = logging.getLogger(__name__)

ESQUEMA = """
CREATE TABLE IF NOT EXISTS notificaciones (
	id INTEGER PRIMARY KEY AUTOINCREMENT,
	id_windows INTEGER NOT NULL DEFAULT 0,
	aumid TEXT NOT NULL DEFAULT '',
	app TEXT NOT NULL DEFAULT '',
	titulo TEXT NOT NULL DEFAULT '',
	texto TEXT NOT NULL DEFAULT '',
	creada REAL NOT NULL,
	recibida REAL NOT NULL,
	leida INTEGER NOT NULL DEFAULT 0,
	favorita INTEGER NOT NULL DEFAULT 0,
	en_windows INTEGER NOT NULL DEFAULT 1,
	UNIQUE (aumid, id_windows, creada)
);
CREATE INDEX IF NOT EXISTS indice_creada ON notificaciones (creada DESC);
"""

FILTRO_TODAS = "todas"
FILTRO_NO_LEIDAS = "no_leidas"
FILTRO_FAVORITAS = "favoritas"

ACCESO_PERMITIDO = "permitido"
ACCESO_DENEGADO = "denegado"
ACCESO_SIN_DECIDIR = "sin_decidir"
ACCESO_NO_DISPONIBLE = "no_disponible"


@dataclass
class Notificacion:
	id: int
	id_windows: int
	aumid: str
	app: str
	titulo: str
	texto: str
	creada: float
	recibida: float
	leida: bool = False
	favorita: bool = False
	en_windows: bool = True

	def resumen(self) -> str:
		"""«Correo: Nuevo mensaje de Ana» (lo que se anuncia)."""
		partes = [self.app or self.aumid or "Aplicación desconocida"]
		if self.titulo:
			partes.append(self.titulo)
		return ": ".join(partes)

	def texto_completo(self) -> str:
		lineas = [self.titulo, self.texto] if self.texto else [self.titulo]
		return "\n".join(linea for linea in lineas if linea)


@dataclass(frozen=True)
class Captada:
	"""Una notificación tal como la da Windows (antes de guardarla)."""

	id_windows: int
	aumid: str
	app: str
	titulo: str
	texto: str
	creada: float


# ── Fuente: Windows ──────────────────────────────────────────────────────────


class FuenteWindows:
	"""Acceso a ``UserNotificationListener``. Usar desde un único hilo (el de sondeo)."""

	def __init__(self) -> None:
		from winrt.windows.ui.notifications import KnownNotificationBindings, NotificationKinds
		from winrt.windows.ui.notifications.management import UserNotificationListener

		self._oyente = UserNotificationListener.current
		self._tipos = NotificationKinds
		self._enlaces = KnownNotificationBindings
		self._bucle = asyncio.new_event_loop()

	def acceso(self) -> str:
		estado = int(self._oyente.get_access_status())
		return {1: ACCESO_PERMITIDO, 2: ACCESO_DENEGADO}.get(estado, ACCESO_SIN_DECIDIR)

	def pedir_acceso(self) -> str:
		async def pedir():
			return await self._oyente.request_access_async()

		estado = int(self._bucle.run_until_complete(asyncio.wait_for(pedir(), 30)))
		return {1: ACCESO_PERMITIDO, 2: ACCESO_DENEGADO}.get(estado, ACCESO_SIN_DECIDIR)

	def leer(self) -> list[Captada]:
		async def obtener():
			return await self._oyente.get_notifications_async(self._tipos.TOAST)

		resultado = []
		for aviso in self._bucle.run_until_complete(obtener()):
			try:
				resultado.append(self._convertir(aviso))
			except Exception:  # noqa: BLE001 - un aviso raro no debe impedir leer los demás
				log.debug("Notificación ilegible", exc_info=True)
		return resultado

	def _convertir(self, aviso) -> Captada:
		aumid = app = ""
		try:
			informacion = aviso.app_info
			if informacion is not None:
				aumid = informacion.app_user_model_id or ""
				app = informacion.display_info.display_name or ""
		except Exception:  # noqa: BLE001 - algunas apps no tienen nombre visible
			log.debug("Sin datos de aplicación", exc_info=True)
		textos: list[str] = []
		visual = aviso.notification.visual
		enlace = visual.get_binding(self._enlaces.toast_generic)
		enlaces = [enlace] if enlace is not None else list(visual.bindings)
		for elemento in enlaces:
			textos += [t.text for t in elemento.get_text_elements() if t.text]
		creada = aviso.creation_time.timestamp() if hasattr(aviso.creation_time, "timestamp") else time.time()
		return Captada(int(aviso.id), aumid, app or aumid, textos[0] if textos else "", "\n".join(textos[1:]), creada)

	def descartar(self, id_windows: int) -> None:
		self._oyente.remove_notification(id_windows)

	def cerrar(self) -> None:
		self._bucle.close()


def abrir_aplicacion(aumid: str) -> bool:
	"""Abre la aplicación que envió la notificación (no el contenido concreto del aviso)."""
	if not aumid or os.name != "nt":
		return False
	try:
		os.startfile("shell:AppsFolder\\" + aumid)  # noqa: S606 - identificador de aplicación del sistema
		return True
	except OSError:
		log.warning("No se pudo abrir la aplicación %s", aumid, exc_info=True)
		return False


# ── Historial ────────────────────────────────────────────────────────────────


class HistorialNotificaciones:
	"""Base de datos del historial. Segura entre hilos."""

	COLUMNAS = "id, id_windows, aumid, app, titulo, texto, creada, recibida, leida, favorita, en_windows"

	def __init__(self, ruta: Path | None = None) -> None:
		self.ruta = ruta or (paths.ruta_base_datos() / "notificaciones.db")
		self._candado = threading.RLock()
		self._conexion = self._abrir()

	def _abrir(self) -> sqlite3.Connection:
		conexion = None
		try:
			conexion = sqlite3.connect(self.ruta, check_same_thread=False, timeout=5)
			conexion.execute("PRAGMA journal_mode=WAL")
			conexion.executescript(ESQUEMA)
			conexion.execute("PRAGMA integrity_check").fetchone()
			return conexion
		except sqlite3.DatabaseError:
			log.exception("El historial de notificaciones %s está dañado; se aparta.", self.ruta)
			if conexion is not None:
				conexion.close()
			try:
				self.ruta.replace(self.ruta.with_name(f"{self.ruta.stem}.danado-{time.strftime('%Y%m%d-%H%M%S')}.db"))
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
				log.debug("Error al cerrar", exc_info=True)

	@staticmethod
	def _fila(fila: tuple) -> Notificacion:
		id_, id_windows, aumid, app, titulo, texto, creada, recibida, leida, favorita, en_windows = fila
		return Notificacion(id_, id_windows, aumid, app, titulo, texto, creada, recibida, bool(leida), bool(favorita), bool(en_windows))

	def agregar(self, captada: Captada, leida: bool = False) -> Notificacion | None:
		"""Guarda la notificación. ``None`` si ya estaba."""
		with self._candado, self._conexion:
			cursor = self._conexion.execute(
				"INSERT OR IGNORE INTO notificaciones (id_windows, aumid, app, titulo, texto, creada, recibida, leida)"
				" VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
				(captada.id_windows, captada.aumid, captada.app, captada.titulo, captada.texto, captada.creada, time.time(), int(leida)),
			)
			if not cursor.rowcount:
				return None
			identificador = cursor.lastrowid
		return self.obtener(identificador)

	def obtener(self, identificador: int) -> Notificacion | None:
		with self._candado:
			fila = self._conexion.execute(f"SELECT {self.COLUMNAS} FROM notificaciones WHERE id = ?", (identificador,)).fetchone()
		return self._fila(fila) if fila else None

	def listar(self, filtro: str = FILTRO_TODAS, app: str = "", buscar: str = "", limite: int = 5000) -> list[Notificacion]:
		condiciones, valores = [], []
		if filtro == FILTRO_NO_LEIDAS:
			condiciones.append("leida = 0")
		elif filtro == FILTRO_FAVORITAS:
			condiciones.append("favorita = 1")
		if app:
			condiciones.append("app = ?")
			valores.append(app)
		for palabra in buscar.split():
			patron = "%" + palabra.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
			condiciones.append("(titulo LIKE ? ESCAPE '\\' OR texto LIKE ? ESCAPE '\\' OR app LIKE ? ESCAPE '\\')")
			valores += [patron, patron, patron]
		donde = (" WHERE " + " AND ".join(condiciones)) if condiciones else ""
		with self._candado:
			filas = self._conexion.execute(
				f"SELECT {self.COLUMNAS} FROM notificaciones{donde} ORDER BY creada DESC, id DESC LIMIT ?", (*valores, limite)
			).fetchall()
		return [self._fila(f) for f in filas]

	def aplicaciones(self) -> list[str]:
		with self._candado:
			return [
				f[0] for f in self._conexion.execute("SELECT DISTINCT app FROM notificaciones WHERE app <> '' ORDER BY app COLLATE NOCASE")
			]

	def no_leidas(self) -> int:
		with self._candado:
			return self._conexion.execute("SELECT COUNT(*) FROM notificaciones WHERE leida = 0").fetchone()[0]

	def contar(self) -> int:
		with self._candado:
			return self._conexion.execute("SELECT COUNT(*) FROM notificaciones").fetchone()[0]

	def ultima(self) -> Notificacion | None:
		lista = self.listar(limite=1)
		return lista[0] if lista else None

	def marcar_leida(self, identificadores: list[int], leida: bool = True) -> None:
		with self._candado, self._conexion:
			self._conexion.executemany("UPDATE notificaciones SET leida = ? WHERE id = ?", [(int(leida), i) for i in identificadores])

	def marcar_todas_leidas(self) -> int:
		with self._candado, self._conexion:
			return self._conexion.execute("UPDATE notificaciones SET leida = 1 WHERE leida = 0").rowcount

	def poner_favorita(self, identificador: int, favorita: bool) -> None:
		with self._candado, self._conexion:
			self._conexion.execute("UPDATE notificaciones SET favorita = ? WHERE id = ?", (int(favorita), identificador))

	def eliminar(self, identificadores: list[int]) -> None:
		with self._candado, self._conexion:
			self._conexion.executemany("DELETE FROM notificaciones WHERE id = ?", [(i,) for i in identificadores])

	def vaciar(self, incluir_favoritas: bool = False) -> int:
		with self._candado, self._conexion:
			borradas = self._conexion.execute("DELETE FROM notificaciones" + ("" if incluir_favoritas else " WHERE favorita = 0")).rowcount
		with self._candado:
			self._conexion.execute("VACUUM")
		return borradas

	def recortar(self, maximo: int = 0, dias: int = 0) -> int:
		"""Borra las antiguas (por número y por días), nunca las favoritas."""
		borradas = 0
		with self._candado, self._conexion:
			if dias > 0:
				limite = time.time() - dias * 86400
				borradas += self._conexion.execute("DELETE FROM notificaciones WHERE favorita = 0 AND creada < ?", (limite,)).rowcount
			if maximo > 0:
				total = self._conexion.execute("SELECT COUNT(*) FROM notificaciones").fetchone()[0]
				if total > maximo:
					borradas += self._conexion.execute(
						"DELETE FROM notificaciones WHERE id IN (SELECT id FROM notificaciones WHERE favorita = 0 ORDER BY creada ASC LIMIT ?)",
						(total - maximo,),
					).rowcount
		return borradas

	def sincronizar_presentes(self, presentes: set[tuple[str, int]]) -> None:
		"""Marca cuáles siguen en el centro de notificaciones de Windows (para poder descartarlas)."""
		with self._candado, self._conexion:
			filas = self._conexion.execute("SELECT id, aumid, id_windows FROM notificaciones WHERE en_windows = 1").fetchall()
			desaparecidas = [(i,) for i, aumid, id_windows in filas if (aumid, id_windows) not in presentes]
			self._conexion.executemany("UPDATE notificaciones SET en_windows = 0 WHERE id = ?", desaparecidas)

	def exportar(self, ruta: Path, notificaciones: list[Notificacion]) -> int:
		"""CSV (con BOM para Excel) o texto, según la extensión."""
		if ruta.suffix.lower() == ".csv":
			with open(ruta, "w", encoding="utf-8-sig", newline="") as archivo:
				escritor = csv.writer(archivo, delimiter=";")
				escritor.writerow(["Fecha", "Aplicación", "Título", "Texto", "Leída", "Favorita"])
				for n in notificaciones:
					fila = [
						time.strftime("%d/%m/%Y %H:%M:%S", time.localtime(n.creada)),
						n.app,
						n.titulo,
						n.texto,
						"sí" if n.leida else "no",
						"sí" if n.favorita else "no",
					]
					# Una celda que empieza por = + - @ se ejecutaría como fórmula en una hoja de cálculo.
					escritor.writerow(["'" + c if c[:1] in ("=", "+", "-", "@") else c for c in fila])
		else:
			bloques = [
				f"{time.strftime('%d/%m/%Y %H:%M:%S', time.localtime(n.creada))} - {n.app}\n{n.texto_completo()}" for n in notificaciones
			]
			ruta.write_text(("\n\n" + "-" * 40 + "\n\n").join(bloques), encoding="utf-8")
		return len(notificaciones)


# ── Servicio ─────────────────────────────────────────────────────────────────


@dataclass
class PreferenciasNotificaciones:
	activo: bool = True
	intervalo_s: float = 3.0
	apps_ignoradas: tuple[str, ...] = ()
	maximo: int = 5000
	dias: int = 90


class ServicioNotificaciones:
	"""Hilo que consulta Windows y guarda lo nuevo. Avisos desde ese hilo (usar wx.CallAfter)."""

	def __init__(
		self,
		preferencias: Callable[[], PreferenciasNotificaciones] | None = None,
		historial: HistorialNotificaciones | None = None,
		fabrica_fuente: Callable[[], FuenteWindows] = FuenteWindows,
	) -> None:
		self._preferencias = preferencias or PreferenciasNotificaciones
		self._historial = historial
		self._fabrica_fuente = fabrica_fuente
		self._hilo: threading.Thread | None = None
		self._detener = threading.Event()
		self._despertar = threading.Event()
		self._ordenes: queue.Queue = queue.Queue()
		self.pausado = False
		self.acceso = ACCESO_NO_DISPONIBLE
		self.al_nuevas: Callable[[list[Notificacion]], None] | None = None
		self.al_cambiar_acceso: Callable[[str], None] | None = None

	@property
	def historial(self) -> HistorialNotificaciones:
		if self._historial is None:
			self._historial = HistorialNotificaciones()
		return self._historial

	def iniciar(self) -> None:
		if self._hilo and self._hilo.is_alive():
			return
		_ = self.historial
		self._detener.clear()
		self._hilo = threading.Thread(target=self._bucle, name="notificaciones", daemon=True)
		self._hilo.start()

	def detener(self) -> None:
		self._detener.set()
		self._despertar.set()
		if self._hilo:
			self._hilo.join(timeout=5)
		self._hilo = None
		if self._historial is not None:
			self._historial.cerrar()

	def consultar_ya(self) -> None:
		"""Adelanta la siguiente consulta (por ejemplo, al abrir el historial)."""
		self._despertar.set()

	def descartar_en_windows(self, notificacion: Notificacion, al_terminar: Callable[[bool], None] | None = None) -> None:
		"""Quita la notificación del centro de notificaciones de Windows (no del historial)."""
		self._ordenes.put(("descartar", notificacion, al_terminar))
		self._despertar.set()

	def pedir_acceso(self, al_terminar: Callable[[str], None] | None = None) -> None:
		self._ordenes.put(("acceso", None, al_terminar))
		self._despertar.set()

	@staticmethod
	def _avisar(funcion: Callable | None, *argumentos) -> None:
		if funcion is None:
			return
		try:
			funcion(*argumentos)
		except Exception:  # noqa: BLE001
			log.exception("Error en un aviso de notificaciones")

	def _bucle(self) -> None:
		fuente = None
		primera = True
		ultima_limpieza = 0.0
		while not self._detener.is_set():
			preferencias = self._preferencias()
			if fuente is None:
				try:
					fuente = self._fabrica_fuente()
					self._poner_acceso(fuente.acceso())
				except Exception:  # noqa: BLE001 - sin WinRT (Windows antiguo, paquete ausente)
					log.warning("No se puede acceder a las notificaciones de Windows.", exc_info=True)
					self._poner_acceso(ACCESO_NO_DISPONIBLE)
					self._detener.wait(30)
					continue
			self._atender_ordenes(fuente)
			if preferencias.activo and not self.pausado and self.acceso == ACCESO_PERMITIDO:
				try:
					self._sondear(fuente, preferencias, primera)
					primera = False
				except Exception:  # noqa: BLE001 - se reintenta en el siguiente ciclo
					log.warning("Falló la lectura de notificaciones.", exc_info=True)
					fuente = None
			elif fuente is not None and self.acceso != ACCESO_PERMITIDO:
				self._poner_acceso(fuente.acceso())
			if time.monotonic() - ultima_limpieza > 3600:
				ultima_limpieza = time.monotonic()
				self.historial.recortar(preferencias.maximo, preferencias.dias)
			self._despertar.wait(max(1.0, float(preferencias.intervalo_s)))
			self._despertar.clear()
		if fuente is not None:
			fuente.cerrar()
		log.info("Hilo de notificaciones terminado.")

	def _poner_acceso(self, acceso: str) -> None:
		if acceso != self.acceso:
			log.info("Acceso a las notificaciones de Windows: %s", acceso)
			self.acceso = acceso
			self._avisar(self.al_cambiar_acceso, acceso)

	def _atender_ordenes(self, fuente: FuenteWindows) -> None:
		while True:
			try:
				orden, notificacion, al_terminar = self._ordenes.get_nowait()
			except queue.Empty:
				return
			if orden == "descartar":
				correcto = True
				try:
					fuente.descartar(notificacion.id_windows)
				except Exception:  # noqa: BLE001 - ya no estaba
					log.info("No se pudo descartar la notificación %s", notificacion.id_windows, exc_info=True)
					correcto = False
				self._avisar(al_terminar, correcto)
			elif orden == "acceso":
				try:
					self._poner_acceso(fuente.pedir_acceso())
				except Exception:  # noqa: BLE001
					log.warning("No se pudo pedir el acceso", exc_info=True)
				self._avisar(al_terminar, self.acceso)

	def _sondear(self, fuente: FuenteWindows, preferencias: PreferenciasNotificaciones, primera: bool) -> None:
		captadas = fuente.leer()
		ignoradas = {a.strip().casefold() for a in preferencias.apps_ignoradas if a.strip()}
		nuevas = []
		# Las que superan el plazo de borrado no se guardan: si no, la limpieza las
		# borraría y en la siguiente consulta volverían a entrar como nuevas.
		antiguedad_maxima = time.time() - preferencias.dias * 86400 if preferencias.dias > 0 else 0
		for captada in sorted(captadas, key=lambda c: c.creada):
			if captada.app.casefold() in ignoradas or captada.aumid.casefold() in ignoradas:
				continue
			if captada.creada < antiguedad_maxima:
				continue
			# Las que ya estaban al arrancar se guardan sin anunciarlas.
			guardada = self.historial.agregar(captada)
			if guardada is not None and not primera:
				nuevas.append(guardada)
		self.historial.sincronizar_presentes({(c.aumid, c.id_windows) for c in captadas})
		if nuevas:
			self._avisar(self.al_nuevas, nuevas)
