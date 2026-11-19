"""Temporizadores, alarmas y recordatorios (sin wx).

- Temporizador: cuenta atrás de una duración; se puede pausar y reanudar.
- Alarma: a una hora (hoy o mañana si ya pasó), una vez o todos los días.
  Con texto, hace de recordatorio.

Un hilo comprueba cada medio segundo qué ha vencido y avisa con
``al_vencer`` (desde ese hilo: la interfaz usa ``wx.CallAfter``). Se guardan
en ``data/db/temporizadores.json``: una alarma sigue programada aunque se
cierre el programa (si vence con el programa cerrado, se avisa al abrirlo).
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

log = logging.getLogger(__name__)

TIPO_TEMPORIZADOR = "temporizador"
TIPO_ALARMA = "alarma"


@dataclass
class Temporizador:
	nombre: str
	tipo: str = TIPO_TEMPORIZADOR
	vence: float = 0.0  # instante (time.time()) en que suena
	duracion: float = 0.0  # segundos (temporizadores)
	restante_pausa: float = 0.0  # segundos que quedaban al pausar (0 = no está pausado)
	diaria: bool = False
	activo: bool = True
	id: str = field(default_factory=lambda: uuid.uuid4().hex)

	@property
	def pausado(self) -> bool:
		return self.restante_pausa > 0

	def restante(self, ahora: float | None = None) -> float:
		if self.pausado:
			return self.restante_pausa
		return max(0.0, self.vence - (time.time() if ahora is None else ahora))


def describir_duracion(segundos: float) -> str:
	"""«1 hora, 5 minutos y 3 segundos», para leer en voz alta."""
	segundos = int(round(segundos))
	horas, resto = divmod(segundos, 3600)
	minutos, segundos = divmod(resto, 60)
	partes = []
	if horas:
		partes.append(f"{horas} hora" + ("s" if horas != 1 else ""))
	if minutos:
		partes.append(f"{minutos} minuto" + ("s" if minutos != 1 else ""))
	if segundos or not partes:
		partes.append(f"{segundos} segundo" + ("s" if segundos != 1 else ""))
	return partes[0] if len(partes) == 1 else ", ".join(partes[:-1]) + " y " + partes[-1]


def proxima_hora(hora: int, minuto: int, ahora: float | None = None) -> float:
	"""Instante de la próxima vez que el reloj marque ``hora:minuto`` (hoy o mañana)."""
	ahora = time.time() if ahora is None else ahora
	local = time.localtime(ahora)
	objetivo = time.mktime((local.tm_year, local.tm_mon, local.tm_mday, hora, minuto, 0, 0, 0, -1))
	if objetivo <= ahora:
		local = time.localtime(ahora + 86400)
		objetivo = time.mktime((local.tm_year, local.tm_mon, local.tm_mday, hora, minuto, 0, 0, 0, -1))
	return objetivo


def analizar_hora(texto: str) -> tuple[int, int] | None:
	"""«7:30», «07.30», «19 30», «7» → (hora, minuto); ``None`` si no es una hora."""
	partes = texto.strip().replace(".", ":").replace(" ", ":").replace("h", ":").split(":")
	partes = [p for p in partes if p != ""]
	try:
		hora = int(partes[0])
		minuto = int(partes[1]) if len(partes) > 1 else 0
	except (ValueError, IndexError):
		return None
	if 0 <= hora <= 23 and 0 <= minuto <= 59:
		return hora, minuto
	return None


class ServicioTemporizadores:
	def __init__(self, ruta: Path | None = None) -> None:
		self.ruta = ruta or (paths.ruta_base_datos() / "temporizadores.json")
		self._candado = threading.RLock()
		self._lista: list[Temporizador] = self._cargar()
		self._hilo: threading.Thread | None = None
		self._detener = threading.Event()
		self.al_vencer: Callable[[Temporizador], None] | None = None
		self.al_cambiar: Callable[[], None] | None = None

	def _cargar(self) -> list[Temporizador]:
		try:
			datos = json.loads(self.ruta.read_text(encoding="utf-8"))
			campos = set(Temporizador.__dataclass_fields__)
			return [Temporizador(**{k: v for k, v in d.items() if k in campos}) for d in datos]
		except FileNotFoundError:
			return []
		except (OSError, ValueError, TypeError):
			log.exception("Temporizadores ilegibles en %s; se empieza sin ninguno", self.ruta)
			return []

	def guardar(self) -> None:
		with self._candado:
			texto = json.dumps([asdict(t) for t in self._lista], ensure_ascii=False, indent="\t")
		temporal = self.ruta.with_name(self.ruta.name + ".tmp")
		try:
			self.ruta.parent.mkdir(parents=True, exist_ok=True)
			temporal.write_text(texto, encoding="utf-8")
			os.replace(temporal, self.ruta)
		except OSError:
			log.exception("No se pudieron guardar los temporizadores")

	def todos(self) -> list[Temporizador]:
		with self._candado:
			return sorted(self._lista, key=lambda t: (not t.activo, t.pausado, t.vence))

	def _cambio(self) -> None:
		self.guardar()
		if self.al_cambiar:
			self.al_cambiar()

	def nuevo_temporizador(self, segundos: float, nombre: str = "") -> Temporizador:
		temporizador = Temporizador(nombre or f"Temporizador de {describir_duracion(segundos)}", TIPO_TEMPORIZADOR, time.time() + segundos, segundos)
		with self._candado:
			self._lista.append(temporizador)
		self._cambio()
		return temporizador

	def nueva_alarma(self, hora: int, minuto: int, nombre: str = "", diaria: bool = False) -> Temporizador:
		alarma = Temporizador(nombre or f"Alarma de las {hora:02d}:{minuto:02d}", TIPO_ALARMA, proxima_hora(hora, minuto), diaria=diaria)
		with self._candado:
			self._lista.append(alarma)
		self._cambio()
		return alarma

	def eliminar(self, identificador: str) -> None:
		with self._candado:
			self._lista = [t for t in self._lista if t.id != identificador]
		self._cambio()

	def pausar(self, identificador: str) -> bool | None:
		"""Pausa o reanuda un temporizador. Devuelve si queda pausado (``None`` si no se puede)."""
		with self._candado:
			temporizador = next((t for t in self._lista if t.id == identificador), None)
			if temporizador is None or temporizador.tipo != TIPO_TEMPORIZADOR or not temporizador.activo:
				return None
			if temporizador.pausado:
				temporizador.vence = time.time() + temporizador.restante_pausa
				temporizador.restante_pausa = 0.0
			else:
				temporizador.restante_pausa = max(1.0, temporizador.vence - time.time())
			pausado = temporizador.pausado
		self._cambio()
		return pausado

	def posponer(self, identificador: str, minutos: int = 5) -> None:
		with self._candado:
			temporizador = next((t for t in self._lista if t.id == identificador), None)
			if temporizador is None:
				return
			temporizador.vence = time.time() + minutos * 60
			temporizador.activo = True
			temporizador.restante_pausa = 0.0
		self._cambio()

	def revisar(self, ahora: float | None = None) -> list[Temporizador]:
		"""Marca y devuelve los que han vencido. Las alarmas diarias se reprograman para mañana."""
		ahora = time.time() if ahora is None else ahora
		vencidos = []
		with self._candado:
			for temporizador in self._lista:
				if temporizador.activo and not temporizador.pausado and temporizador.vence <= ahora:
					vencidos.append(Temporizador(**asdict(temporizador)))
					if temporizador.tipo == TIPO_ALARMA and temporizador.diaria:
						local = time.localtime(temporizador.vence)
						temporizador.vence = proxima_hora(local.tm_hour, local.tm_min, max(ahora, temporizador.vence))
					else:
						temporizador.activo = False
		if vencidos:
			self._cambio()
		return vencidos

	def iniciar(self) -> None:
		if self._hilo and self._hilo.is_alive():
			return
		self._detener.clear()
		self._hilo = threading.Thread(target=self._bucle, name="temporizadores", daemon=True)
		self._hilo.start()

	def detener(self) -> None:
		self._detener.set()
		if self._hilo:
			self._hilo.join(timeout=2)

	def _bucle(self) -> None:
		while not self._detener.wait(0.5):
			try:
				for vencido in self.revisar():
					if self.al_vencer:
						self.al_vencer(vencido)
			except Exception:  # noqa: BLE001 - el reloj no debe pararse por un fallo
				log.exception("Error al revisar los temporizadores")
