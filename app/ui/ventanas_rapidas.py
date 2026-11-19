"""Ventanas rápidas de portapapeles y emoticonos, para usar desde cualquier programa.

Se abren con una tecla global. Recuerdan la ventana que estaba delante (el
«destino») y, al elegir algo con Intro, se cierran, le devuelven el foco y
pegan o escriben allí. Escape cierra sin hacer nada y también devuelve el
foco al destino.

Son ventanas independientes (sin padre) y siempre encima, para que aparezcan
delante aunque el gestor esté oculto en la bandeja.
"""

from __future__ import annotations

import builtins
import logging
from typing import TYPE_CHECKING

import wx

from app.services import ventanas_win32 as w32
from app.ui.area_emoticonos import AreaEmoticonos
from app.ui.area_fragmentos import AreaFragmentos
from app.ui.area_lanzador import AreaLanzador
from app.ui.area_notificaciones import AreaNotificaciones
from app.ui.area_portapapeles import AreaPortapapeles

if TYPE_CHECKING:
	from app.ui.controlador import Controlador

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class VentanaRapida(wx.Dialog):
	"""Base: área, botón Cerrar, destino y Escape."""

	def __init__(self, titulo: str, controlador: Controlador, destino: int) -> None:
		super().__init__(None, title=titulo, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.STAY_ON_TOP)
		self.controlador = controlador
		self.destino = destino
		self.area = self._crear_area()
		boton = wx.Button(self, wx.ID_CANCEL, _("C&errar"))
		sizer = wx.BoxSizer(wx.VERTICAL)
		sizer.Add(self.area, 1, wx.EXPAND)
		sizer.Add(boton, 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		self.SetSizer(sizer)
		self.SetSize(self.FromDIP(wx.Size(820, 560)))
		self.CentreOnScreen()
		self.SetEscapeId(wx.ID_CANCEL)
		boton.Bind(wx.EVT_BUTTON, lambda _e: self.cerrar(devolver_foco=True))
		self.Bind(wx.EVT_CLOSE, lambda _e: self.cerrar(devolver_foco=True))
		self.Bind(wx.EVT_CHAR_HOOK, self._al_tecla)

	def _crear_area(self) -> wx.Panel:
		raise NotImplementedError

	def abrir(self) -> None:
		self.Show()
		self.Raise()
		w32.forzar_primer_plano(self.GetHandle())
		self.area.enfocar()

	def cerrar(self, devolver_foco: bool = False) -> None:
		if not self:
			return
		self.Hide()
		if devolver_foco and self.destino:
			w32.forzar_primer_plano(self.destino)
		self.Destroy()

	def _al_tecla(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() == wx.WXK_ESCAPE and not evento.HasAnyModifiers():
			self.cerrar(devolver_foco=True)
			return
		if self.area.manejar_tecla(evento):
			return
		evento.Skip()


class PortapapelesRapido(VentanaRapida):
	"""Historial del portapapeles: Intro pega en la ventana de la que se vino."""

	def __init__(self, controlador: Controlador, destino: int) -> None:
		super().__init__(_("Portapapeles"), controlador, destino)

	def _crear_area(self) -> AreaPortapapeles:
		area = AreaPortapapeles(self, self.controlador, self._pegar)
		area.refrescar()
		return area

	def _pegar(self, identificador: int, transformacion: str | None = None) -> None:
		destino = self.destino
		self.cerrar()
		self.controlador.pegar_elemento(identificador, destino, transformacion)


class EmoticonosRapido(VentanaRapida):
	"""Emoticonos: Intro escribe el emoticono en la ventana de la que se vino."""

	def __init__(self, controlador: Controlador, destino: int) -> None:
		super().__init__(_("Emoticonos"), controlador, destino)

	def _crear_area(self) -> AreaEmoticonos:
		return AreaEmoticonos(self, self.controlador, self._insertar)

	def _insertar(self, texto: str) -> None:
		destino = self.destino
		self.controlador.config.guardar()
		self.cerrar()
		self.controlador.insertar_texto(texto, destino)


class NotificacionesRapido(VentanaRapida):
	"""Historial de notificaciones: Intro abre la aplicación que la envió."""

	def __init__(self, controlador: Controlador, destino: int) -> None:
		super().__init__(_("Notificaciones"), controlador, destino)

	def _crear_area(self) -> AreaNotificaciones:
		area = AreaNotificaciones(self, self.controlador)
		area.refrescar()
		return area


class FragmentosRapido(VentanaRapida):
	"""Fragmentos de texto: Intro (o la abreviatura e Intro) lo escribe donde se estaba."""

	def __init__(self, controlador: Controlador, destino: int) -> None:
		super().__init__(_("Fragmentos de texto"), controlador, destino)

	def _crear_area(self) -> AreaFragmentos:
		return AreaFragmentos(self, self.controlador, self._insertar)

	def _insertar(self, fragmento) -> None:
		destino = self.destino
		self.cerrar()
		self.controlador.insertar_fragmento(fragmento, destino)


class LanzadorRapido(VentanaRapida):
	"""Lanzador y paleta de órdenes: Intro abre el programa, el ajuste o la acción."""

	def __init__(self, controlador: Controlador, destino: int) -> None:
		super().__init__(_("Lanzador"), controlador, destino)

	def _crear_area(self) -> AreaLanzador:
		return AreaLanzador(self, self.controlador, self._elegir)

	def _elegir(self, elemento) -> None:
		destino = self.destino
		# Cálculos y acciones de Centro de Mando actúan sobre la ventana de la que se vino
		# («mover la ventana activa», «pegar»...): primero se le devuelve el foco y se
		# espera un momento a que Windows lo confirme. Programas y ajustes abren algo nuevo.
		volver = elemento.tipo in ("Resultado", "Centro de Mando")
		controlador = self.controlador
		self.cerrar(devolver_foco=volver)
		if volver:
			wx.CallLater(200, controlador.ejecutar_elemento_lanzador, elemento, destino)
		else:
			controlador.ejecutar_elemento_lanzador(elemento, destino)
