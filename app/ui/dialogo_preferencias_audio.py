"""Diálogo «Salidas (o micrófonos) preferidos al conectar».

- Casilla «Cambiar solo al preferido al conectar o desconectar» (Alt+O).
- Lista de casillas (Alt+D) con todos los dispositivos que Windows conoce:
  arriba los preferidos, en su orden. Espacio marca o desmarca (marcado =
  entra en el orden de preferencia). Subir (Alt+U) y Bajar (Alt+B), o
  Alt+Mayúsculas+flechas arriba y abajo en la lista, cambian el orden.
- Aceptar guarda; Cancelar no toca nada.
"""

from __future__ import annotations

import builtins

import wx

from app.services.preferencias_audio import filas_para_dialogo, mover
from app.ui.accesibilidad.casillas import CheckListBoxAccesible
from app.ui.accesibilidad.dialogos import crear_botonera, preparar_dialogo


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class DialogoPreferenciasAudio(wx.Dialog):
	def __init__(self, padre: wx.Window, entrada: bool, activo: bool, preferencias: list[str], conocidos: list[str]) -> None:
		titulo = _("Micrófonos preferidos al conectar") if entrada else _("Salidas preferidas al conectar")
		super().__init__(padre, title=titulo, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self._entrada = entrada
		self._filas = filas_para_dialogo(preferencias, conocidos)
		sizer = wx.BoxSizer(wx.VERTICAL)
		self.activo = wx.CheckBox(
			self, label=_("Cambiar s&olo al micrófono preferido al conectar o desconectar") if entrada
			else _("Cambiar s&olo a la salida preferida al conectar o desconectar")
		)
		self.activo.SetValue(activo)
		self.activo.SetHelpText(
			_("Cuando se conecta o desconecta un dispositivo, se pone como predeterminado el primero marcado de la lista "
			"que esté conectado. Al apagar los auriculares, vuelve al siguiente de la lista.")
		)
		sizer.Add(self.activo, 0, wx.ALL, 10)
		etiqueta = wx.StaticText(self, label=_("&Dispositivos en orden de preferencia (marcados = se usan):"))
		self.lista = CheckListBoxAccesible(self, _("Dispositivos en orden de preferencia"), [n for n, _m in self._filas])
		for posicion, (_nombre, marcado) in enumerate(self._filas):
			self.lista.Check(posicion, marcado)
		if self._filas:
			self.lista.SetSelection(0)
		sizer.Add(etiqueta, 0, wx.LEFT | wx.RIGHT, 10)
		sizer.Add(self.lista, 1, wx.EXPAND | wx.ALL, 10)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		self.subir = wx.Button(self, label=_("S&ubir"))
		self.bajar = wx.Button(self, label=_("&Bajar"))
		self.subir.SetHelpText(_("Sube el dispositivo seleccionado en el orden. En la lista: Alt+Mayúsculas+Flecha arriba."))
		self.bajar.SetHelpText(_("Baja el dispositivo seleccionado en el orden. En la lista: Alt+Mayúsculas+Flecha abajo."))
		fila.Add(self.subir, 0, wx.RIGHT, 8)
		fila.Add(self.bajar, 0)
		sizer.Add(fila, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
		sizer.Add(crear_botonera(self, wx.OK | wx.CANCEL), 0, wx.EXPAND | wx.ALL, 10)
		self.SetSizer(sizer)
		self.SetSize(self.FromDIP(wx.Size(560, 460)))
		self.subir.Bind(wx.EVT_BUTTON, lambda _e: self.mover(-1))
		self.bajar.Bind(wx.EVT_BUTTON, lambda _e: self.mover(1))
		self.lista.Bind(wx.EVT_KEY_DOWN, self._al_pulsar)
		preparar_dialogo(self, foco_inicial=self.lista if self._filas else self.activo)
		self.CentreOnParent()

	def _al_pulsar(self, evento: wx.KeyEvent) -> None:
		if evento.GetModifiers() == (wx.MOD_ALT | wx.MOD_SHIFT) and evento.GetKeyCode() in (wx.WXK_UP, wx.WXK_DOWN):
			self.mover(-1 if evento.GetKeyCode() == wx.WXK_UP else 1)
			return
		evento.Skip()

	def _leer_marcas(self) -> None:
		self._filas = [(nombre, self.lista.IsChecked(i)) for i, (nombre, _m) in enumerate(self._filas)]

	def mover(self, desplazamiento: int) -> None:
		posicion = self.lista.GetSelection()
		if posicion == wx.NOT_FOUND:
			return
		self._leer_marcas()
		nueva = mover(self._filas, posicion, desplazamiento)
		if nueva == posicion:
			wx.Bell()
			return
		for indice in (posicion, nueva):
			self.lista.SetString(indice, self._filas[indice][0])
			self.lista.Check(indice, self._filas[indice][1])
		self.lista.SetSelection(nueva)
		self.lista.SetFocus()
		from app.core import voz

		voz.hablar(_("Posición {n}").format(n=nueva + 1), interrumpir=False)

	def resultado(self) -> tuple[bool, list[str]]:
		"""(activado, nombres marcados en orden)."""
		self._leer_marcas()
		return self.activo.GetValue(), [nombre for nombre, marcado in self._filas if marcado]
