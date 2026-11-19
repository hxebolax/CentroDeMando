"""Diálogos de reglas de ventanas: lista de reglas y edición de una regla.

Una regla lleva automáticamente las ventanas nuevas de un programa (o con un
texto en el título) a un escritorio, o las muestra en todos. El orden importa:
se aplica la primera regla que encaja, por eso hay Subir y Bajar.
"""

from __future__ import annotations

import builtins
from collections.abc import Callable

import wx

from app.services.reglas import Regla
from app.ui.listas import crear_lista
from app.ui.accesibilidad.dialogos import confirmar, crear_botonera, mostrar_mensaje, preparar_dialogo
from app.ui.accesibilidad.nombres import crear_campo


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class DialogoRegla(wx.Dialog):
	"""Crear o modificar una regla."""

	def __init__(self, padre: wx.Window, regla: Regla | None, procesos: list[str], escritorios: list[str]) -> None:
		super().__init__(padre, title=_("Modificar la regla") if regla else _("Nueva regla"))
		regla = regla or Regla()
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		_e, self.nombre = crear_campo(
			panel,
			_("&Nombre de la regla:"),
			wx.TextCtrl,
			value=regla.nombre,
			ayuda=_("Opcional: un nombre para reconocerla en la lista."),
			sizer=sizer,
		)
		_e, self.proceso = crear_campo(
			panel,
			_("&Programa (ejecutable):"),
			wx.ComboBox,
			value=regla.proceso,
			choices=sorted(set(procesos), key=str.casefold),
			ayuda=_(
				"Nombre del ejecutable, por ejemplo thunderbird.exe. La lista trae los programas con ventanas abiertas. Vacío = cualquiera."
			),
			sizer=sizer,
		)
		_e, self.titulo = crear_campo(
			panel,
			_("&Título contiene:"),
			wx.TextCtrl,
			value=regla.titulo,
			ayuda=_("Texto que debe aparecer en el título de la ventana, sin distinguir mayúsculas. Vacío = cualquiera."),
			sizer=sizer,
		)
		_e, self.escritorio = crear_campo(
			panel,
			_("&Escritorio de destino (número o nombre):"),
			wx.ComboBox,
			value=regla.escritorio,
			choices=escritorios,
			ayuda=_("Número del escritorio o su nombre. Si se cambia el orden de los escritorios, usar el nombre mantiene la regla."),
			sizer=sizer,
		)
		self.anclar = wx.CheckBox(panel, label=_("&Mostrar en todos los escritorios en lugar de moverla"))
		self.anclar.SetValue(regla.anclar)
		self.anclar.SetHelpText(_("La ventana no se mueve: aparece en todos los escritorios."))
		sizer.Add(self.anclar, 0, wx.ALL, 8)
		self.activa = wx.CheckBox(panel, label=_("Regla acti&va"))
		self.activa.SetValue(regla.activa)
		self.activa.SetHelpText(_("Desmárquela para conservar la regla sin que se aplique."))
		sizer.Add(self.activa, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
		sizer.Add(crear_botonera(panel, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		panel.SetSizer(sizer)
		marco = wx.BoxSizer(wx.VERTICAL)
		marco.Add(panel, 1, wx.EXPAND)
		self.SetSizerAndFit(marco)
		self.Bind(wx.EVT_BUTTON, self._al_aceptar, id=wx.ID_OK)
		preparar_dialogo(self, foco_inicial=self.nombre)
		self.CentreOnParent()

	def regla(self) -> Regla:
		return Regla(
			nombre=self.nombre.GetValue().strip(),
			proceso=self.proceso.GetValue().strip(),
			titulo=self.titulo.GetValue().strip(),
			escritorio=self.escritorio.GetValue().strip(),
			anclar=self.anclar.GetValue(),
			activa=self.activa.GetValue(),
		)

	def _al_aceptar(self, evento: wx.CommandEvent) -> None:
		regla = self.regla()
		if not (regla.proceso or regla.titulo):
			mostrar_mensaje(self, _("Escriba el programa, un texto del título o ambos."), _("Regla incompleta"), wx.ICON_WARNING)
			self.proceso.SetFocus()
			return
		if not (regla.escritorio or regla.anclar):
			mostrar_mensaje(
				self,
				_("Indique el escritorio de destino o marque «Mostrar en todos los escritorios»."),
				_("Regla incompleta"),
				wx.ICON_WARNING,
			)
			self.escritorio.SetFocus()
			return
		evento.Skip()


class DialogoReglas(wx.Dialog):
	"""Lista de reglas con Nueva, Modificar, Eliminar, Subir, Bajar y Aplicar ahora."""

	def __init__(
		self,
		padre: wx.Window,
		reglas: list[Regla],
		procesos: list[str],
		escritorios: list[str],
		al_aplicar_ahora: Callable[[list[Regla]], None] | None = None,
	) -> None:
		super().__init__(padre, title=_("Reglas de ventanas"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.reglas = [Regla(**r.a_dict()) for r in reglas]
		self._procesos = procesos
		self._escritorios = escritorios
		self._al_aplicar_ahora = al_aplicar_ahora

		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		etiqueta = wx.StaticText(panel, label=_("&Reglas, en orden de prioridad:"))
		self.lista = crear_lista(
			panel,
			_("Reglas, en orden de prioridad"),
			[(_("Nombre"), self.FromDIP(180)), (_("Qué hace"), self.FromDIP(460)), (_("Estado"), self.FromDIP(110))],
			_("Intro modifica la regla; Suprimir la elimina. Se aplica la primera regla que encaja con cada ventana nueva."),
		)
		sizer.Add(etiqueta, 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)
		sizer.Add(self.lista, 1, wx.EXPAND | wx.ALL, 8)

		fila = wx.BoxSizer(wx.HORIZONTAL)
		botones = [
			(_("&Nueva..."), self.nueva),
			(_("&Modificar..."), self.modificar),
			(_("&Eliminar"), self.eliminar),
			(_("S&ubir"), lambda: self.mover(-1)),
			(_("&Bajar"), lambda: self.mover(1)),
			(_("Aplicar a&hora a las ventanas abiertas"), self.aplicar_ahora),
		]
		for etiqueta_boton, funcion in botones:
			boton = wx.Button(panel, label=etiqueta_boton)
			boton.Bind(wx.EVT_BUTTON, lambda _e, f=funcion: f())
			fila.Add(boton, 0, wx.RIGHT, 6)
		sizer.Add(fila, 0, wx.LEFT | wx.RIGHT, 8)
		sizer.Add(crear_botonera(panel, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		panel.SetSizer(sizer)
		marco = wx.BoxSizer(wx.VERTICAL)
		marco.Add(panel, 1, wx.EXPAND)
		self.SetSizer(marco)
		self.SetSize(self.FromDIP(wx.Size(820, 480)))

		self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: self.modificar())
		self.lista.Bind(wx.EVT_KEY_DOWN, self._al_tecla)
		self.rellenar(0)
		preparar_dialogo(self, foco_inicial=self.lista)
		self.CentreOnParent()

	def rellenar(self, seleccion: int = 0) -> None:
		self.lista.DeleteAllItems()
		for indice, regla in enumerate(self.reglas):
			self.lista.InsertItem(indice, regla.nombre or _("Regla {n}").format(n=indice + 1))
			self.lista.SetItem(indice, 1, regla.describir())
			self.lista.SetItem(indice, 2, _("Activa") if regla.activa else _("Desactivada"))
		if self.reglas:
			seleccion = min(max(seleccion, 0), len(self.reglas) - 1)
			self.lista.Select(seleccion)
			self.lista.Focus(seleccion)

	def _seleccionada(self) -> int:
		return self.lista.GetFirstSelected()

	def _editar(self, regla: Regla | None) -> Regla | None:
		dialogo = DialogoRegla(self, regla, self._procesos, self._escritorios)
		try:
			return dialogo.regla() if dialogo.ShowModal() == wx.ID_OK else None
		finally:
			dialogo.Destroy()
			self.lista.SetFocus()

	def nueva(self) -> None:
		regla = self._editar(None)
		if regla is not None:
			self.reglas.append(regla)
			self.rellenar(len(self.reglas) - 1)

	def modificar(self) -> None:
		indice = self._seleccionada()
		if indice < 0:
			return
		regla = self._editar(self.reglas[indice])
		if regla is not None:
			self.reglas[indice] = regla
			self.rellenar(indice)

	def eliminar(self) -> None:
		indice = self._seleccionada()
		if indice < 0:
			return
		if (
			confirmar(self, _("¿Eliminar la regla «{r}»?").format(r=self.reglas[indice].describir()), _("Eliminar regla"), peligroso=True)
			== wx.ID_YES
		):
			del self.reglas[indice]
			self.rellenar(indice)
		self.lista.SetFocus()

	def mover(self, paso: int) -> None:
		indice = self._seleccionada()
		destino = indice + paso
		if indice < 0 or not 0 <= destino < len(self.reglas):
			wx.Bell()
			return
		self.reglas[indice], self.reglas[destino] = self.reglas[destino], self.reglas[indice]
		self.rellenar(destino)
		self.lista.SetFocus()

	def aplicar_ahora(self) -> None:
		if self._al_aplicar_ahora is not None:
			self._al_aplicar_ahora(list(self.reglas))

	def _al_tecla(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() in (wx.WXK_DELETE, wx.WXK_NUMPAD_DELETE) and not evento.HasAnyModifiers():
			self.eliminar()
			return
		evento.Skip()
