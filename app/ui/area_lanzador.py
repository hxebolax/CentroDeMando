"""Lanzador: buscar y abrir programas, ajustes de Windows y acciones de Centro de Mando.

- «Buscar» (Alt+B): se escribe y la lista se filtra al momento. Intro abre el
  primer resultado; Flecha abajo baja a la lista.
- «Resultados» (Alt+R): nombre y tipo (programa, ajuste de Windows, Centro
  de Mando o resultado de un cálculo). Intro abre el elegido.

Si lo escrito es una operación («15% de 80»), el primer resultado es el
valor: Intro lo copia al portapapeles.
"""

from __future__ import annotations

import builtins
from collections.abc import Callable
from typing import TYPE_CHECKING

import wx

from app.services.lanzador import Elemento
from app.ui import listas
from app.ui.listas import actualizar_lista

if TYPE_CHECKING:
	from app.ui.controlador import Controlador


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


RETRASO_ANUNCIO_MS = 400


class AreaLanzador(wx.Panel):
	def __init__(self, padre: wx.Window, controlador: Controlador, al_elegir: Callable[[Elemento], None]) -> None:
		super().__init__(padre)
		self.controlador = controlador
		self._al_elegir = al_elegir
		self._elementos: list[Elemento] = []
		self._claves: list[str] = []
		self._anuncio: wx.CallLater | None = None
		sizer = wx.BoxSizer(wx.VERTICAL)
		etiqueta = wx.StaticText(self, label=_("&Buscar programa, ajuste u orden:"))
		self.buscar = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
		self.buscar.SetHelpText(
			_("Escriba parte del nombre o sus iniciales. También una operación, como 15% de 80. Intro abre el primero; Flecha abajo baja a la lista.")
		)
		sizer.Add(etiqueta, 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)
		sizer.Add(self.buscar, 0, wx.EXPAND | wx.ALL, 8)
		etiqueta = wx.StaticText(self, label=_("&Resultados:"))
		self.lista = listas.crear_lista(
			self, _("Resultados"), [(_("Nombre"), self.FromDIP(460)), (_("Tipo"), self.FromDIP(200))], _("Intro abre el elemento.")
		)
		sizer.Add(etiqueta, 0, wx.LEFT | wx.RIGHT, 8)
		sizer.Add(self.lista, 1, wx.EXPAND | wx.ALL, 8)
		self.SetSizer(sizer)
		self.buscar.Bind(wx.EVT_TEXT, lambda _e: self._al_escribir())
		self.buscar.Bind(wx.EVT_TEXT_ENTER, lambda _e: self._abrir_primero())
		self.buscar.Bind(wx.EVT_KEY_DOWN, self._al_tecla_buscar)
		self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: self.abrir())
		self.controlador.catalogo_lanzador.actualizar_programas()
		self.refrescar()

	def refrescar(self) -> None:
		if not self:
			return
		self._elementos = self.controlador.catalogo_lanzador.buscar(self.buscar.GetValue(), self.controlador.config.obtener("lanzador.usos", {}))
		actualizar_lista(self.lista, [(e.id, (e.nombre, _(e.tipo))) for e in self._elementos], self._claves)

	def _al_escribir(self) -> None:
		self.refrescar()
		if self._anuncio is not None:
			self._anuncio.Stop()
		self._anuncio = wx.CallLater(RETRASO_ANUNCIO_MS, self._anunciar)

	def _anunciar(self) -> None:
		if not self or not self.buscar.GetValue().strip():
			return
		if not self._elementos:
			self.controlador.hablar(_("Sin resultados"))
		else:
			primero = self._elementos[0]
			self.controlador.hablar(_("{n} resultados. Primero: {p}").format(n=len(self._elementos), p=primero.nombre))

	def enfocar(self) -> None:
		self.buscar.SetFocus()

	def seleccionado(self) -> Elemento | None:
		fila = self.lista.fila_actual()
		return self._elementos[fila] if 0 <= fila < len(self._elementos) else None

	def abrir(self) -> None:
		elemento = self.seleccionado()
		if elemento is not None:
			self._al_elegir(elemento)

	def _abrir_primero(self) -> None:
		self.refrescar()
		if not self._elementos:
			self.controlador.hablar(_("Sin resultados"), True)
			return
		self._al_elegir(self._elementos[0])

	def _al_tecla_buscar(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() in (wx.WXK_DOWN, wx.WXK_NUMPAD_DOWN) and not evento.HasAnyModifiers():
			if self.lista.numero_filas():
				self.lista.SetFocus()
				if self.lista.GetFocusedItem() < 0:
					self.lista.enfocar_fila(0, anunciar=False)
			return
		evento.Skip()

	def manejar_tecla(self, _evento: wx.KeyEvent) -> bool:
		return False
