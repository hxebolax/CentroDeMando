"""Reglas de ventanas: llevar automáticamente ciertas ventanas a un escritorio (sin wx).

Una regla dice «las ventanas del programa X (o cuyo título contenga Y) van al
escritorio Z» o «se muestran en todos los escritorios». Se guardan en la
configuración como una lista de diccionarios; aquí solo hay datos y la
lógica de coincidencia, que se prueba sin Windows.
"""

from __future__ import annotations

import builtins
from dataclasses import asdict, dataclass
from typing import Any

from app.services.escritorios import InfoEscritorio, InfoVentana, buscar_por_nombre


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


@dataclass
class Regla:
	"""Una regla de colocación de ventanas."""

	nombre: str = ""
	# Nombre del ejecutable («notepad.exe»); vacío = cualquiera.
	proceso: str = ""
	# Texto que debe contener el título; vacío = cualquiera.
	titulo: str = ""
	# Número («3») o nombre («Correo») del escritorio de destino.
	escritorio: str = ""
	# En lugar de moverla, mostrarla en todos los escritorios.
	anclar: bool = False
	activa: bool = True

	def es_valida(self) -> bool:
		"""Debe filtrar por algo y tener un destino (escritorio o anclar)."""
		return bool((self.proceso.strip() or self.titulo.strip()) and (self.escritorio.strip() or self.anclar))

	def coincide(self, ventana: InfoVentana) -> bool:
		if not self.activa or not self.es_valida():
			return False
		if self.proceso.strip() and ventana.proceso.casefold() != _normalizar_proceso(self.proceso):
			return False
		if self.titulo.strip() and self.titulo.strip().casefold() not in ventana.titulo.casefold():
			return False
		return True

	def describir(self) -> str:
		"""Resumen legible para la lista de reglas."""
		partes = []
		if self.proceso.strip():
			partes.append(_("programa {p}").format(p=self.proceso.strip()))
		if self.titulo.strip():
			partes.append(_("título con «{t}»").format(t=self.titulo.strip()))
		condicion = _(" y ").join(partes) or _("sin condición")
		destino = _("en todos los escritorios") if self.anclar else _("al escritorio {e}").format(e=self.escritorio.strip())
		return _("{condicion}: {destino}").format(condicion=condicion, destino=destino)

	def a_dict(self) -> dict[str, Any]:
		return asdict(self)

	@classmethod
	def desde_dict(cls, datos: Any) -> Regla | None:
		"""Crea la regla desde la configuración; ``None`` si los datos no sirven."""
		if not isinstance(datos, dict):
			return None
		valores = {}
		for campo, defecto in asdict(cls()).items():
			valor = datos.get(campo, defecto)
			if isinstance(defecto, bool):
				valor = bool(valor) if isinstance(valor, (bool, int)) else defecto
			else:
				valor = str(valor) if valor is not None else defecto
			valores[campo] = valor
		return cls(**valores)


def _normalizar_proceso(proceso: str) -> str:
	"""«Notepad» y «notepad.exe» valen igual."""
	proceso = proceso.strip().casefold()
	return proceso if proceso.endswith(".exe") else proceso + ".exe"


def cargar_reglas(datos: Any) -> list[Regla]:
	"""Lista de reglas válida a partir de lo guardado (ignora lo que no se entienda)."""
	if not isinstance(datos, list):
		return []
	return [regla for regla in (Regla.desde_dict(d) for d in datos) if regla is not None]


def buscar_regla(reglas: list[Regla], ventana: InfoVentana) -> Regla | None:
	"""La primera regla activa que encaja con la ventana (el orden importa)."""
	for regla in reglas:
		if regla.coincide(ventana):
			return regla
	return None


def destino_de_regla(regla: Regla, escritorios: tuple[InfoEscritorio, ...] | list[InfoEscritorio]) -> int:
	"""Número del escritorio de destino; 0 si no existe."""
	escritorio = buscar_por_nombre(escritorios, regla.escritorio)
	return escritorio.numero if escritorio else 0
