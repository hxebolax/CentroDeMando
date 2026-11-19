"""Listas de la aplicación: ``ListaAccesible`` con las preferencias de lectura de Opciones.

Todas las listas multicolumna del gestor se crean con ``crear_lista``. Así
todas se recorren igual (Izquierda y Derecha por las columnas, Control+1 a 9
y 0 para leer una columna, Control+Mayúsculas+Inicio y Fin para la primera y
la última) y todas leen las mismas preferencias de Opciones, pestaña Listas:
decir el número de fila, el nombre de la columna y el contenido.

Las preferencias se leen EN CADA ANUNCIO: al pulsar Aceptar en Opciones, las
listas ya abiertas cambian sin reiniciar.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import wx

from app.core.config import Configuracion
from app.ui.accesibilidad.composicion import PreferenciasLectura
from app.ui.accesibilidad.lista import ListaAccesible

_configuracion: Configuracion | None = None


def configurar(configuracion: Configuracion) -> None:
	"""La ventana principal registra aquí la configuración al crearse."""
	global _configuracion
	_configuracion = configuracion


def preferencias_lectura() -> PreferenciasLectura:
	"""Lo que se dice al moverse por las columnas, según Opciones."""
	if _configuracion is None:
		return PreferenciasLectura()
	obtener = _configuracion.obtener
	return PreferenciasLectura(
		numero_fila=bool(obtener("listas.decir_numero_fila", True)),
		cabecera=bool(obtener("listas.decir_cabecera", True)),
		contenido=bool(obtener("listas.decir_contenido", True)),
	)


def crear_lista(padre: wx.Window, nombre: str, columnas: Sequence[tuple[str, int]], ayuda: str = "") -> ListaAccesible:
	"""Crea una lista accesible de selección única. Cree ANTES su ``StaticText``."""
	lista = ListaAccesible(padre, nombre, columnas, leer_preferencias=preferencias_lectura)
	if ayuda:
		lista.SetHelpText(ayuda + " " + AYUDA_COLUMNAS)
	return lista


AYUDA_COLUMNAS = (
	"Izquierda y Derecha recorren las columnas; Control más un número del 1 al 0 lee esa columna; "
	"Control+Mayúsculas+Inicio o Fin, la primera o la última."
)


def actualizar_lista(lista: wx.ListCtrl, filas: Sequence[tuple[Any, Sequence[str]]], claves: list[Any]) -> None:
	"""Pone ``filas`` (clave, celdas) en la lista tocando solo lo que cambia.

	``claves`` (la lista paralela de claves de la lista) se actualiza en su
	sitio. La selección y el foco se conservan por clave: si el elemento
	seleccionado sigue existiendo, sigue seleccionado aunque cambie de posición.
	"""
	enfocado = lista.GetFocusedItem()
	clave_enfocada = claves[enfocado] if 0 <= enfocado < len(claves) else None
	nuevas = [clave for clave, _celdas in filas]
	if isinstance(lista, ListaAccesible):
		# La lista accesible guarda el texto íntegro de cada celda para leerlo por columnas.
		if nuevas != claves:
			lista.reemplazar_filas([list(celdas) for _clave, celdas in filas], conservar_foco=False)
			claves[:] = nuevas
			if filas:
				destino = nuevas.index(clave_enfocada) if clave_enfocada in nuevas else min(max(enfocado, 0), len(filas) - 1)
				lista.enfocar_fila(destino, anunciar=False)
		else:
			for indice, (_clave, celdas) in enumerate(filas):
				lista.actualizar_fila(indice, list(celdas))
		return
	if nuevas != claves:
		lista.DeleteAllItems()
		for indice, (_clave, celdas) in enumerate(filas):
			lista.InsertItem(indice, celdas[0])
			for columna, texto in enumerate(celdas[1:], 1):
				lista.SetItem(indice, columna, texto)
		claves[:] = nuevas
		if filas:
			destino = nuevas.index(clave_enfocada) if clave_enfocada in nuevas else min(max(enfocado, 0), len(filas) - 1)
			lista.Focus(destino)
			lista.Select(destino)
		return
	for indice, (_clave, celdas) in enumerate(filas):
		for columna, texto in enumerate(celdas):
			if lista.GetItemText(indice, columna) != texto:
				lista.SetItem(indice, columna, texto)
	if filas and lista.GetFocusedItem() < 0:
		lista.Focus(0)
		lista.Select(0)
