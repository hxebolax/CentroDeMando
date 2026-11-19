"""Área de fragmentos de texto: buscar, insertar, crear y editar.

Controles, en orden de tabulación:

- «Buscar fragmento» (Alt+B): por abreviatura, nombre, categoría o texto.
  Intro en el buscador inserta el primero (escribir la abreviatura y pulsar
  Intro es lo más rápido).
- «Categoría» (Alt+C).
- «Lista de fragmentos» (Alt+L): nombre, abreviatura, categoría, texto y usos.
- «Contenido» (Alt+T): el texto completo, de solo lectura.

Teclas en la lista: Intro inserta en la ventana de la que se vino,
Mayúsculas+Intro copia, Insert crea uno nuevo, F2 lo modifica y Suprimir lo
elimina.
"""

from __future__ import annotations

import builtins
from collections.abc import Callable
from typing import TYPE_CHECKING

import wx

from app.services.fragmentos import VARIABLES, AlmacenFragmentos, Fragmento
from app.ui import listas
from app.ui.accesibilidad.dialogos import confirmar, crear_botonera, mostrar_mensaje, preparar_dialogo
from app.ui.accesibilidad.nombres import crear_campo
from app.ui.listas import actualizar_lista

if TYPE_CHECKING:
	from app.ui.controlador import Controlador


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class DialogoFragmento(wx.Dialog):
	"""Crear o modificar un fragmento."""

	def __init__(self, padre: wx.Window | None, fragmento: Fragmento | None, categorias: list[str]) -> None:
		super().__init__(padre, title=_("Modificar el fragmento") if fragmento else _("Nuevo fragmento"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self._original = fragmento
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		_e, self.nombre = crear_campo(panel, _("&Nombre:"), wx.TextCtrl, value=fragmento.nombre if fragmento else "", ayuda=_("Cómo se verá en la lista."), sizer=sizer)
		_e, self.abreviatura = crear_campo(
			panel,
			_("A&breviatura (opcional):"),
			wx.TextCtrl,
			value=fragmento.abreviatura if fragmento else "",
			ayuda=_("Una palabra corta para encontrarlo al momento: escríbala en el buscador y pulse Intro."),
			sizer=sizer,
		)
		_e, self.categoria = crear_campo(
			panel, _("Ca&tegoría:"), wx.ComboBox, value=fragmento.categoria if fragmento else "", choices=categorias, ayuda=_("Para agruparlos."), sizer=sizer
		)
		_e, self.texto = crear_campo(
			panel,
			_("Te&xto:"),
			wx.TextCtrl,
			value=fragmento.texto if fragmento else "",
			style=wx.TE_MULTILINE,
			size=self.FromDIP(wx.Size(520, 200)),
			ayuda=_("Variables que se sustituyen al insertar: {variables}.").format(variables=", ".join(VARIABLES)),
			sizer=sizer,
		)
		sizer.Add(crear_botonera(panel, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		panel.SetSizer(sizer)
		marco = wx.BoxSizer(wx.VERTICAL)
		marco.Add(panel, 1, wx.EXPAND)
		self.SetSizerAndFit(marco)
		self.Bind(wx.EVT_BUTTON, self._al_aceptar, id=wx.ID_OK)
		preparar_dialogo(self, foco_inicial=self.nombre)
		self.CentreOnParent()

	def fragmento(self) -> Fragmento:
		datos = {
			"nombre": self.nombre.GetValue().strip(),
			"texto": self.texto.GetValue(),
			"categoria": self.categoria.GetValue().strip(),
			"abreviatura": self.abreviatura.GetValue().strip(),
		}
		if self._original is not None:
			return Fragmento(**datos, id=self._original.id, usos=self._original.usos, ultimo_uso=self._original.ultimo_uso)
		return Fragmento(**datos)

	def _al_aceptar(self, evento: wx.CommandEvent) -> None:
		if not self.texto.GetValue():
			mostrar_mensaje(self, _("El fragmento necesita un texto."), _("Fragmento incompleto"), wx.ICON_WARNING)
			self.texto.SetFocus()
			return
		if not self.nombre.GetValue().strip():
			self.nombre.SetValue(" ".join(self.texto.GetValue().split())[:40])
		evento.Skip()


class AreaFragmentos(wx.Panel):
	"""Lista de fragmentos. ``al_insertar(fragmento)`` decide dónde se escribe."""

	def __init__(self, padre: wx.Window, controlador: Controlador, al_insertar: Callable[[Fragmento], None]) -> None:
		super().__init__(padre)
		self.controlador = controlador
		self._al_insertar = al_insertar
		self._fragmentos: list[Fragmento] = []
		self._claves: list[str] = []

		sizer = wx.BoxSizer(wx.VERTICAL)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		etiqueta = wx.StaticText(self, label=_("&Buscar fragmento:"))
		self.buscar = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
		self.buscar.SetHelpText(_("Escriba la abreviatura o parte del nombre o del texto. Intro inserta el primero; Flecha abajo baja a la lista."))
		fila.Add(etiqueta, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
		fila.Add(self.buscar, 1, wx.RIGHT, 12)
		etiqueta = wx.StaticText(self, label=_("Cate&goría:"))
		self.categoria = wx.Choice(self, choices=[_("Todas")])
		self.categoria.SetSelection(0)
		self.categoria.SetHelpText(_("Ver solo los fragmentos de una categoría."))
		fila.Add(etiqueta, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
		fila.Add(self.categoria, 0)
		sizer.Add(fila, 0, wx.EXPAND | wx.ALL, 8)
		etiqueta = wx.StaticText(self, label=_("&Lista de fragmentos:"))
		self.lista = listas.crear_lista(
			self,
			_("Lista de fragmentos"),
			[
				(_("Nombre"), self.FromDIP(220)),
				(_("Abreviatura"), self.FromDIP(110)),
				(_("Categoría"), self.FromDIP(140)),
				(_("Texto"), self.FromDIP(360)),
				(_("Usos"), self.FromDIP(60)),
			],
			_("Intro inserta el fragmento; Mayúsculas+Intro lo copia; Insert crea uno nuevo; F2 lo modifica; Suprimir lo elimina."),
		)
		sizer.Add(etiqueta, 0, wx.LEFT | wx.RIGHT, 8)
		sizer.Add(self.lista, 3, wx.EXPAND | wx.ALL, 8)
		etiqueta = wx.StaticText(self, label=_("Con&tenido:"))
		self.contenido = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2)
		self.contenido.SetHelpText(_("Texto completo del fragmento seleccionado."))
		sizer.Add(etiqueta, 0, wx.LEFT | wx.RIGHT, 8)
		sizer.Add(self.contenido, 1, wx.EXPAND | wx.ALL, 8)
		self.SetSizer(sizer)

		self.buscar.Bind(wx.EVT_TEXT, lambda _e: self.refrescar())
		self.buscar.Bind(wx.EVT_TEXT_ENTER, self._al_intro_buscar)
		self.buscar.Bind(wx.EVT_KEY_DOWN, self._al_tecla_buscar)
		self.categoria.Bind(wx.EVT_CHOICE, lambda _e: self.refrescar())
		self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: self.insertar())
		self.lista.Bind(wx.EVT_LIST_ITEM_SELECTED, lambda _e: self._mostrar_contenido())
		self.lista.Bind(wx.EVT_CONTEXT_MENU, self._al_menu_contextual)
		self.refrescar()

	@property
	def almacen(self) -> AlmacenFragmentos:
		return self.controlador.fragmentos

	def refrescar(self) -> None:
		if not self:
			return
		categorias = [_("Todas"), *self.almacen.categorias()]
		elegida = self.categoria.GetStringSelection()
		if self.categoria.GetItems() != categorias:
			self.categoria.Set(categorias)
			self.categoria.SetSelection(categorias.index(elegida) if elegida in categorias else 0)
		categoria = self.categoria.GetStringSelection() if self.categoria.GetSelection() > 0 else ""
		self._fragmentos = self.almacen.buscar(self.buscar.GetValue(), categoria)
		filas = [(f.id, (f.nombre, f.abreviatura, f.categoria, f.resumen(), str(f.usos))) for f in self._fragmentos]
		actualizar_lista(self.lista, filas, self._claves)
		self._mostrar_contenido()

	def seleccionado(self) -> Fragmento | None:
		fila = self.lista.fila_actual()
		return self._fragmentos[fila] if 0 <= fila < len(self._fragmentos) else None

	def _mostrar_contenido(self) -> None:
		fragmento = self.seleccionado()
		texto = fragmento.texto if fragmento else ""
		if self.contenido.GetValue() != texto:
			self.contenido.SetValue(texto)

	def enfocar(self) -> None:
		self.buscar.SetFocus()

	# ── Acciones ────────────────────────────────────────────────────────────

	def insertar(self) -> None:
		fragmento = self.seleccionado()
		if fragmento is not None:
			self.almacen.anotar_uso(fragmento.id)
			self._al_insertar(fragmento)

	def copiar(self) -> None:
		from app.services.fragmentos import expandir

		fragmento = self.seleccionado()
		if fragmento is not None:
			texto, _retroceso = expandir(fragmento.texto, portapapeles=self.controlador.texto_del_portapapeles)
			self.controlador.copiar_texto(texto)
			self.controlador.hablar(_("Fragmento copiado"), True)

	def nuevo(self) -> None:
		dialogo = DialogoFragmento(self, None, self.almacen.categorias())
		try:
			if dialogo.ShowModal() == wx.ID_OK:
				self.almacen.agregar(dialogo.fragmento())
				self.refrescar()
		finally:
			dialogo.Destroy()
		self.lista.SetFocus()

	def modificar(self) -> None:
		fragmento = self.seleccionado()
		if fragmento is None:
			return
		dialogo = DialogoFragmento(self, fragmento, self.almacen.categorias())
		try:
			if dialogo.ShowModal() == wx.ID_OK:
				self.almacen.reemplazar(dialogo.fragmento())
				self.refrescar()
		finally:
			dialogo.Destroy()
		self.lista.SetFocus()

	def eliminar(self) -> None:
		fragmento = self.seleccionado()
		if fragmento is None:
			return
		if confirmar(self, _("¿Eliminar el fragmento «{n}»?").format(n=fragmento.nombre), _("Eliminar fragmento"), peligroso=True) == wx.ID_YES:
			self.almacen.eliminar(fragmento.id)
			self.refrescar()
		self.lista.SetFocus()

	def acciones(self) -> list:
		hay = self.seleccionado() is not None
		return [
			(_("&Insertar en la ventana anterior (Intro)"), self.insertar, hay),
			(_("&Copiar al portapapeles (Mayúsculas+Intro)"), self.copiar, hay),
			(_("&Nuevo fragmento... (Insert)"), self.nuevo, True),
			(_("&Modificar...\tF2"), self.modificar, hay),
			(_("&Eliminar (Suprimir)"), self.eliminar, hay),
		]

	# ── Teclado ─────────────────────────────────────────────────────────────

	def manejar_tecla(self, evento: wx.KeyEvent) -> bool:
		if wx.Window.FindFocus() is not self.lista:
			return False
		tecla, modificadores = evento.GetKeyCode(), evento.GetModifiers()
		if tecla in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and modificadores == wx.MOD_SHIFT:
			self.copiar()
		elif tecla in (wx.WXK_INSERT, wx.WXK_NUMPAD_INSERT) and modificadores == wx.MOD_NONE:
			self.nuevo()
		elif tecla == wx.WXK_F2 and modificadores == wx.MOD_NONE:
			self.modificar()
		elif tecla in (wx.WXK_DELETE, wx.WXK_NUMPAD_DELETE) and modificadores == wx.MOD_NONE:
			self.eliminar()
		else:
			return False
		return True

	def _al_intro_buscar(self, _evento: wx.CommandEvent) -> None:
		self.refrescar()
		if not self._fragmentos:
			self.controlador.hablar(_("Ningún fragmento coincide"), True)
			return
		self.lista.enfocar_fila(0, anunciar=False)
		self.insertar()

	def _al_tecla_buscar(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() in (wx.WXK_DOWN, wx.WXK_NUMPAD_DOWN) and not evento.HasAnyModifiers():
			if self.lista.numero_filas():
				self.lista.SetFocus()
				if self.lista.GetFocusedItem() < 0:
					self.lista.enfocar_fila(0, anunciar=False)
			return
		evento.Skip()

	def _al_menu_contextual(self, evento: wx.ContextMenuEvent) -> None:
		menu = wx.Menu()
		hay = self.seleccionado() is not None
		for etiqueta, funcion, activo in (
			(_("&Insertar en la ventana anterior"), self.insertar, hay),
			(_("&Copiar al portapapeles"), self.copiar, hay),
			(_("&Nuevo fragmento..."), self.nuevo, True),
			(_("&Modificar..."), self.modificar, hay),
			(_("&Eliminar"), self.eliminar, hay),
		):
			item = menu.Append(wx.ID_ANY, etiqueta)
			item.Enable(activo)
			menu.Bind(wx.EVT_MENU, lambda _e, f=funcion: f(), item)
		posicion = evento.GetPosition()
		if posicion == wx.DefaultPosition:
			rect = self.lista.GetItemRect(max(self.lista.GetFocusedItem(), 0)) if self.lista.numero_filas() else wx.Rect(0, 0, 0, 0)
			posicion = wx.Point(rect.x + 20, rect.y + rect.height)
		else:
			posicion = self.lista.ScreenToClient(posicion)
		try:
			self.lista.PopupMenu(menu, posicion)
		finally:
			menu.Destroy()
