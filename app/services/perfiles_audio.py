"""Perfiles de audio: guardar y aplicar de una vez salidas, micrófonos y volúmenes (sin wx).

Un perfil recuerda:

- la salida predeterminada y la de comunicaciones,
- el micrófono predeterminado y el de comunicaciones,
- el volumen general y el del micrófono.

Se guardan en la configuración (``audio.perfiles``) como diccionarios. Cada
dispositivo se guarda por id y por nombre: si el id cambió (se reinstaló el
controlador, otro puerto USB) se busca por el nombre.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass

from app.services import audio

log = logging.getLogger(__name__)


@dataclass
class PerfilAudio:
	nombre: str
	salida: tuple[str, str] = ("", "")  # (id, nombre)
	salida_llamadas: tuple[str, str] = ("", "")
	entrada: tuple[str, str] = ("", "")
	entrada_llamadas: tuple[str, str] = ("", "")
	volumen: int = -1  # -1 = no cambiarlo
	volumen_micro: int = -1

	def a_dict(self) -> dict:
		datos = asdict(self)
		for campo in ("salida", "salida_llamadas", "entrada", "entrada_llamadas"):
			datos[campo] = list(datos[campo])
		return datos

	@classmethod
	def de_dict(cls, datos: dict) -> PerfilAudio | None:
		if not isinstance(datos, dict) or not str(datos.get("nombre", "")).strip():
			return None

		def par(clave: str) -> tuple[str, str]:
			valor = datos.get(clave)
			if isinstance(valor, (list, tuple)) and len(valor) == 2:
				return str(valor[0] or ""), str(valor[1] or "")
			return "", ""

		def numero(clave: str) -> int:
			valor = datos.get(clave, -1)
			return int(valor) if isinstance(valor, (int, float)) and not isinstance(valor, bool) and -1 <= valor <= 100 else -1

		return cls(
			str(datos["nombre"]).strip(),
			par("salida"),
			par("salida_llamadas"),
			par("entrada"),
			par("entrada_llamadas"),
			numero("volumen"),
			numero("volumen_micro"),
		)

	def describir(self) -> str:
		"""«Auriculares, 40 %; micrófono USB, 80 %» (lo que se anuncia al aplicarlo)."""
		partes = []
		if self.salida[1]:
			partes.append(self.salida[1] + (f", {self.volumen} %" if self.volumen >= 0 else ""))
		if self.entrada[1]:
			partes.append(self.entrada[1] + (f", {self.volumen_micro} %" if self.volumen_micro >= 0 else ""))
		return "; ".join(partes)


def cargar(lista: object) -> list[PerfilAudio]:
	"""Perfiles válidos de la configuración (los dañados se ignoran)."""
	if not isinstance(lista, list):
		return []
	return [p for p in (PerfilAudio.de_dict(d) for d in lista) if p is not None]


def buscar(dispositivos: list[audio.Dispositivo], guardado: tuple[str, str]) -> audio.Dispositivo | None:
	"""El dispositivo guardado: por id y, si no está, por nombre (función pura)."""
	identificador, nombre = guardado
	if not identificador and not nombre:
		return None
	return next((d for d in dispositivos if d.id == identificador), None) or next(
		(d for d in dispositivos if nombre and d.nombre == nombre), None
	)


def capturar(nombre: str) -> PerfilAudio:
	"""Perfil con el estado actual del audio."""
	salidas = audio.dispositivos_salida()
	entradas = audio.dispositivos_entrada()

	def par(lista, condicion) -> tuple[str, str]:
		d = next((x for x in lista if condicion(x)), None)
		return (d.id, d.nombre) if d else ("", "")

	try:
		volumen = audio.volumen_general()[0]
	except audio.ErrorAudio:
		volumen = -1
	try:
		volumen_micro = audio.volumen_entrada()[0]
	except audio.ErrorAudio:
		volumen_micro = -1
	return PerfilAudio(
		nombre.strip(),
		par(salidas, lambda d: d.predeterminado),
		par(salidas, lambda d: d.comunicaciones),
		par(entradas, lambda d: d.predeterminado),
		par(entradas, lambda d: d.comunicaciones),
		volumen,
		volumen_micro,
	)


def aplicar(perfil: PerfilAudio) -> list[str]:
	"""Aplica el perfil; devuelve lo que no se encontró (para avisar)."""
	faltan: list[str] = []
	salidas = audio.dispositivos_salida()
	entradas = audio.dispositivos_entrada()
	for guardado, lista, poner in (
		(perfil.salida, salidas, audio.poner_predeterminado),
		(perfil.salida_llamadas, salidas, audio.poner_comunicaciones),
		(perfil.entrada, entradas, audio.poner_predeterminado_entrada),
		(perfil.entrada_llamadas, entradas, audio.poner_comunicaciones),
	):
		if not guardado[0] and not guardado[1]:
			continue
		dispositivo = buscar(lista, guardado)
		if dispositivo is None:
			if guardado[1] not in faltan:
				faltan.append(guardado[1])
			continue
		poner(dispositivo)
	if perfil.volumen >= 0:
		audio.poner_volumen_general(perfil.volumen)
	if perfil.volumen_micro >= 0 and buscar(entradas, perfil.entrada) is not None:
		audio.poner_volumen_entrada(perfil.volumen_micro)
	log.info("Perfil de audio aplicado: %s", perfil.nombre)
	return faltan


def siguiente(perfiles: list[PerfilAudio], ultimo: str) -> PerfilAudio | None:
	"""El perfil que va después de ``ultimo`` (cíclico; el primero si no hay último)."""
	if not perfiles:
		return None
	nombres = [p.nombre for p in perfiles]
	posicion = nombres.index(ultimo) + 1 if ultimo in nombres else 0
	return perfiles[posicion % len(perfiles)]
