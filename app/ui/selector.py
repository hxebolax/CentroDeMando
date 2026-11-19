"""Selector rápido: una lista filtrable para elegir un escritorio o una ventana.

Se abre con una tecla global desde cualquier programa, así que:

- Es una ventana independiente (sin padre) y siempre encima, y se trae al
  frente con las técnicas de ``instancia_unica.traer_al_frente``.
- El foco empieza en la lista, en el elemento actual: con las flechas o
  escribiendo la primera letra o cifra se llega al destino, e Intro lo elige.
- El campo «Filtrar» (Alt+F) reduce la lista mientras se escribe; Intro en
  él elige el primer resultado y Flecha abajo baja a la lista.
- Escape cierra sin hacer nada y el foco vuelve a donde estaba (Windows lo
  devuelve a la ventana anterior al cerrarse la nuestra).
"""

from __future__ import annotations

import builtins
import logging
from collections.abc import Callable, Sequence
from typing import Any

import wx

from app.services.ventanas_win32 import forzar_primer_plano as traer_al_frente

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def filtrar(elementos: Sequence[tuple[str, Any]], texto: str) -> list[tuple[str, Any]]:
	"""Elementos cuyo texto contiene TODAS las palabras del filtro (sin distinguir mayúsculas)."""
	palabras = (texto or "").casefold().split()
	if not palabras:
		return list(elementos)
	return [e for e in elementos if all(p in e[0].casefold() for p in palabras)]


class DialogoSelector(wx.Dialog):
	"""Lista con filtro. Llama a ``al_elegir(valor)`` y se cierra."""

	def __init__(
		self,
		titulo: str,
		etiqueta_lista: str,
		elementos: Sequence[tuple[str, Any]],
		al_elegir: Callable[[Any], None],
		seleccion_inicial: int = 0,
		padre: wx.Window | None = None,
	) -> None:
		super().__init__(padre, title=titulo, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.STAY_ON_TOP)
		self._elementos = list(elementos)
		self._visibles = list(elementos)
		self._al_elegir = al_elegir

		panel = wx.Panel(self)
		etiqueta = wx.StaticText(panel, label=etiqueta_lista)
		self.lista = wx.ListBox(panel, choices=[t for t, _v in self._visibles], style=wx.LB_SINGLE)
		self.lista.SetHelpText(_("Flechas o la primera letra para elegir; Intro para ir; Escape para cerrar."))
		etiqueta_filtro = wx.StaticText(panel, label=_("&Filtrar:"))
		self.filtro = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER)
		self.filtro.SetHelpText(_("Escriba parte del nombre o el número para reducir la lista. Intro elige el primero."))
		boton_ir = wx.Button(panel, wx.ID_OK, _("&Ir"))
		boton_cerrar = wx.Button(panel, wx.ID_CANCEL, _("&Cerrar"))
		boton_ir.SetDefault()

		sizer = wx.BoxSizer(wx.VERTICAL)
		sizer.Add(etiqueta, 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)
		sizer.Add(self.lista, 1, wx.EXPAND | wx.ALL, 8)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		fila.Add(etiqueta_filtro, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
		fila.Add(self.filtro, 1, wx.EXPAND)
		sizer.Add(fila, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
		botones = wx.BoxSizer(wx.HORIZONTAL)
		botones.Add(boton_ir, 0, wx.RIGHT, 8)
		botones.Add(boton_cerrar)
		sizer.Add(botones, 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		panel.SetSizer(sizer)
		marco = wx.BoxSizer(wx.VERTICAL)
		marco.Add(panel, 1, wx.EXPAND)
		self.SetSizer(marco)
		self.SetSize(self.FromDIP(wx.Size(520, 420)))
		self.CentreOnScreen()
		self.SetEscapeId(wx.ID_CANCEL)

		self.lista.Bind(wx.EVT_LISTBOX_DCLICK, self._al_elegir_evento)
		self.filtro.Bind(wx.EVT_TEXT, self._al_filtrar)
		self.filtro.Bind(wx.EVT_TEXT_ENTER, self._al_elegir_evento)
		self.filtro.Bind(wx.EVT_KEY_DOWN, self._al_tecla_filtro)
		boton_ir.Bind(wx.EVT_BUTTON, self._al_elegir_evento)
		boton_cerrar.Bind(wx.EVT_BUTTON, lambda _e: self.cerrar())
		self.Bind(wx.EVT_CLOSE, lambda _e: self.cerrar())

		if self._visibles:
			indice = min(max(seleccion_inicial, 0), len(self._visibles) - 1)
			self.lista.SetSelection(indice)

	def abrir(self) -> None:
		"""Muestra el selector delante de todo con el foco en la lista."""
		self.Show()
		self.Raise()
		traer_al_frente(self.GetHandle())
		self.lista.SetFocus()

	def cerrar(self) -> None:
		if self:
			self.Destroy()

	def _al_filtrar(self, _evento: wx.CommandEvent) -> None:
		self._visibles = filtrar(self._elementos, self.filtro.GetValue())
		self.lista.Set([t for t, _v in self._visibles])
		if self._visibles:
			self.lista.SetSelection(0)

	def _al_tecla_filtro(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() in (wx.WXK_DOWN, wx.WXK_NUMPAD_DOWN) and not evento.HasAnyModifiers():
			self.lista.SetFocus()
			return
		evento.Skip()

	def _al_elegir_evento(self, _evento: wx.Event) -> None:
		indice = self.lista.GetSelection()
		if indice == wx.NOT_FOUND and self._visibles:
			indice = 0
		if indice == wx.NOT_FOUND or indice >= len(self._visibles):
			wx.Bell()
			return
		valor = self._visibles[indice][1]
		# Primero se cierra: así el foco no vuelve a esta ventana tras el cambio.
		self.cerrar()
		try:
			self._al_elegir(valor)
		except Exception:  # noqa: BLE001 - se registra; el selector ya está cerrado
			log.exception("Error al elegir en el selector")
