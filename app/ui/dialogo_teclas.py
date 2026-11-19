"""Diálogo «Teclas globales»: ver y cambiar el atajo de cada acción.

Diseño accesible:

- Una lista en modo informe con tres columnas: Acción, Atajo y Estado
  («Activa», «Sin atajo» o por qué no se pudo registrar).
- Para cambiar un atajo NO se pide «pulse la combinación»: Windows se queda
  con muchas combinaciones de la tecla Windows antes de que lleguen a la
  aplicación y el propio lector de pantalla captura otras. En su lugar, cuatro
  casillas (Ctrl, Alt, Mayús, Win) y un desplegable con la tecla: todo se
  puede hacer y comprobar con el lector.
- Los cambios se prueban al pulsar Aplicar o Aceptar: se registran en
  Windows y la columna Estado dice cuáles fallaron.
"""

from __future__ import annotations

import builtins
import logging

import wx

from app.core.config import Configuracion
from app.services import acciones as catalogo
from app.services.teclas import MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, TECLAS, analizar, formatear
from app.ui.listas import crear_lista
from app.ui.accesibilidad.dialogos import confirmar, crear_botonera, mostrar_mensaje, preparar_dialogo

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


SIN_TECLA = "(ninguna)"


class DialogoEditarAtajo(wx.Dialog):
	"""Elegir modificadores y tecla para una acción."""

	def __init__(self, padre: wx.Window, nombre_accion: str, atajo: str) -> None:
		super().__init__(padre, title=_("Atajo de «{accion}»").format(accion=nombre_accion))
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		combinacion = analizar(atajo)
		modificadores = combinacion.modificadores if combinacion else MOD_CONTROL | MOD_ALT | MOD_WIN
		self.casillas: dict[int, wx.CheckBox] = {}
		for bandera, etiqueta in (
			(MOD_CONTROL, _("Co&ntrol")),
			(MOD_ALT, _("A&lt")),
			(MOD_SHIFT, _("&Mayúsculas")),
			(MOD_WIN, _("&Windows")),
		):
			casilla = wx.CheckBox(panel, label=etiqueta)
			casilla.SetValue(bool(modificadores & bandera))
			casilla.SetHelpText(_("Marque las teclas que hay que mantener pulsadas. Hace falta al menos Control, Alt o Windows."))
			self.casillas[bandera] = casilla
			sizer.Add(casilla, 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)
		etiqueta_tecla = wx.StaticText(panel, label=_("&Tecla:"))
		self._nombres = [SIN_TECLA, *TECLAS.keys()]
		self.tecla = wx.Choice(panel, choices=[_(SIN_TECLA), *TECLAS.keys()])
		self.tecla.SetHelpText(_("La tecla principal de la combinación. Elija «(ninguna)» para dejar la acción sin atajo."))
		nombre_tecla = next((n for n, vk in TECLAS.items() if combinacion and vk == combinacion.vk), SIN_TECLA)
		self.tecla.SetSelection(self._nombres.index(nombre_tecla))
		sizer.Add(etiqueta_tecla, 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)
		sizer.Add(self.tecla, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
		self.resumen = wx.StaticText(panel, label="")
		sizer.Add(self.resumen, 0, wx.ALL, 8)
		sizer.Add(crear_botonera(panel, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		panel.SetSizer(sizer)
		marco = wx.BoxSizer(wx.VERTICAL)
		marco.Add(panel, 1, wx.EXPAND)
		self.SetSizerAndFit(marco)
		for casilla in self.casillas.values():
			casilla.Bind(wx.EVT_CHECKBOX, self._al_cambiar)
		self.tecla.Bind(wx.EVT_CHOICE, self._al_cambiar)
		self.Bind(wx.EVT_BUTTON, self._al_aceptar, id=wx.ID_OK)
		self._al_cambiar(None)
		preparar_dialogo(self, foco_inicial=self.tecla)
		self.CentreOnParent()

	def atajo(self) -> str:
		"""Combinación elegida en texto, o cadena vacía si no hay tecla."""
		nombre = self._nombres[self.tecla.GetSelection()] if self.tecla.GetSelection() >= 0 else SIN_TECLA
		if nombre == SIN_TECLA:
			return ""
		modificadores = sum(b for b, c in self.casillas.items() if c.GetValue())
		return formatear(modificadores, TECLAS[nombre])

	def _al_cambiar(self, _evento: wx.Event | None) -> None:
		atajo = self.atajo()
		self.resumen.SetLabel(_("Combinación: {a}").format(a=atajo) if atajo else _("Sin atajo"))

	def _al_aceptar(self, evento: wx.CommandEvent) -> None:
		atajo = self.atajo()
		if atajo:
			combinacion = analizar(atajo)
			if combinacion is None or not combinacion.valida:
				mostrar_mensaje(
					self,
					_("Marque al menos Control, Alt o Windows: una tecla sola dejaría de funcionar en todos los programas."),
					_("Atajo no válido"),
					wx.ICON_WARNING,
				)
				return
			if combinacion.modificadores == MOD_WIN and combinacion.vk == TECLAS["L"]:
				mostrar_mensaje(self, _("Windows+L bloquea el equipo y no se puede usar."), _("Atajo no válido"), wx.ICON_WARNING)
				return
		evento.Skip()


class DialogoTeclas(wx.Dialog):
	"""Lista de acciones con su atajo global."""

	def __init__(self, padre: wx.Window, configuracion: Configuracion, controlador) -> None:
		super().__init__(padre, title=_("Teclas globales"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self._config = configuracion
		self._controlador = controlador
		self.atajos = catalogo.atajos_efectivos(configuracion.obtener("teclas", {}))
		self._acciones = list(catalogo.ACCIONES)

		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		etiqueta = wx.StaticText(panel, label=_("&Lista de acciones y sus teclas:"))
		self.lista = crear_lista(
			panel,
			_("Lista de acciones y sus teclas"),
			[
				(_("Acción"), self.FromDIP(380)),
				(_("Atajo"), self.FromDIP(220)),
				(_("Estado"), self.FromDIP(260)),
				(_("Categoría"), self.FromDIP(180)),
			],
			_("Intro o el botón Cambiar edita el atajo de la acción; Suprimir lo quita. Los atajos funcionan desde cualquier programa."),
		)
		sizer.Add(etiqueta, 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)
		sizer.Add(self.lista, 1, wx.EXPAND | wx.ALL, 8)

		etiqueta_descripcion = wx.StaticText(panel, label=_("&Descripción:"))
		self.descripcion = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY, size=self.FromDIP(wx.Size(-1, 50)))
		sizer.Add(etiqueta_descripcion, 0, wx.LEFT | wx.RIGHT, 8)
		sizer.Add(self.descripcion, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

		fila = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_cambiar = wx.Button(panel, label=_("Ca&mbiar..."))
		self.boton_quitar = wx.Button(panel, label=_("&Quitar el atajo"))
		self.boton_fabrica = wx.Button(panel, label=_("&Restablecer este"))
		self.boton_todos = wx.Button(panel, label=_("Restablecer &todos"))
		for boton in (self.boton_cambiar, self.boton_quitar, self.boton_fabrica, self.boton_todos):
			fila.Add(boton, 0, wx.RIGHT, 8)
		sizer.Add(fila, 0, wx.LEFT | wx.RIGHT, 8)
		sizer.Add(crear_botonera(panel, wx.OK | wx.CANCEL | wx.APPLY), 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		panel.SetSizer(sizer)
		marco = wx.BoxSizer(wx.VERTICAL)
		marco.Add(panel, 1, wx.EXPAND)
		self.SetSizer(marco)
		self.SetSize(self.FromDIP(wx.Size(1000, 600)))

		self.boton_cambiar.Bind(wx.EVT_BUTTON, lambda _e: self.cambiar())
		self.boton_quitar.Bind(wx.EVT_BUTTON, lambda _e: self.quitar())
		self.boton_fabrica.Bind(wx.EVT_BUTTON, lambda _e: self.restablecer())
		self.boton_todos.Bind(wx.EVT_BUTTON, lambda _e: self.restablecer_todos())
		self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: self.cambiar())
		self.lista.Bind(wx.EVT_LIST_ITEM_SELECTED, self._al_seleccionar)
		self.lista.Bind(wx.EVT_KEY_DOWN, self._al_tecla)
		self.Bind(wx.EVT_BUTTON, self._al_aplicar, id=wx.ID_APPLY)
		self.Bind(wx.EVT_BUTTON, self._al_aceptar, id=wx.ID_OK)

		self.rellenar()
		preparar_dialogo(self, foco_inicial=self.lista)
		self.CentreOnParent()

	# ── Lista ───────────────────────────────────────────────────────────────

	def _estado(self, accion: str) -> str:
		atajo = self.atajos.get(accion, "")
		if not atajo:
			return _("Sin atajo")
		registro = getattr(self._controlador, "ultimo_registro", None)
		if registro is not None:
			if accion in registro.fallidos:
				return registro.fallidos[accion]
			if registro.registrados.get(accion) == atajo:
				return _("Activa")
		return _("Pendiente de aplicar")

	def rellenar(self) -> None:
		seleccion = max(self.lista.GetFirstSelected(), 0)
		self.lista.DeleteAllItems()
		for indice, accion in enumerate(self._acciones):
			self.lista.InsertItem(indice, _(accion.nombre))
			self.lista.SetItem(indice, 1, self.atajos.get(accion.id, "") or _("Ninguno"))
			self.lista.SetItem(indice, 2, self._estado(accion.id))
			self.lista.SetItem(indice, 3, _(accion.categoria))
		if self._acciones:
			seleccion = min(seleccion, len(self._acciones) - 1)
			self.lista.Select(seleccion)
			self.lista.Focus(seleccion)
			self._mostrar_descripcion(seleccion)

	def _actualizar_fila(self, indice: int) -> None:
		accion = self._acciones[indice]
		self.lista.SetItem(indice, 1, self.atajos.get(accion.id, "") or _("Ninguno"))
		self.lista.SetItem(indice, 2, self._estado(accion.id))

	def _seleccionada(self) -> int:
		return self.lista.GetFirstSelected()

	def _al_seleccionar(self, evento: wx.ListEvent) -> None:
		self._mostrar_descripcion(evento.GetIndex())

	def _mostrar_descripcion(self, indice: int) -> None:
		if 0 <= indice < len(self._acciones):
			accion = self._acciones[indice]
			fabrica = accion.atajo or _("ninguno")
			self.descripcion.SetValue(
				_("{descripcion} Atajo de fábrica: {fabrica}.").format(descripcion=_(accion.descripcion), fabrica=fabrica)
			)

	def _al_tecla(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() in (wx.WXK_DELETE, wx.WXK_NUMPAD_DELETE) and not evento.HasAnyModifiers():
			self.quitar()
			return
		evento.Skip()

	# ── Cambios ─────────────────────────────────────────────────────────────

	def asignar(self, indice: int, atajo: str) -> bool:
		"""Asigna el atajo; si ya lo tenía otra acción, pregunta si se le quita. Devuelve si se asignó."""
		accion = self._acciones[indice]
		if atajo:
			canonico = str(analizar(atajo))
			for otra in self._acciones:
				if otra.id != accion.id and self.atajos.get(otra.id) and str(analizar(self.atajos[otra.id])) == canonico:
					respuesta = confirmar(
						self,
						_("«{atajo}» ya está asignado a «{otra}». ¿Quitárselo y asignarlo a «{esta}»?").format(
							atajo=canonico, otra=_(otra.nombre), esta=_(accion.nombre)
						),
						_("Atajo repetido"),
					)
					if respuesta != wx.ID_YES:
						return False
					self.atajos[otra.id] = ""
					self._actualizar_fila(self._acciones.index(otra))
		self.atajos[accion.id] = atajo
		self._actualizar_fila(indice)
		return True

	def cambiar(self) -> None:
		indice = self._seleccionada()
		if indice < 0:
			return
		accion = self._acciones[indice]
		dialogo = DialogoEditarAtajo(self, _(accion.nombre), self.atajos.get(accion.id, ""))
		try:
			if dialogo.ShowModal() == wx.ID_OK:
				self.asignar(indice, dialogo.atajo())
		finally:
			dialogo.Destroy()
		self.lista.SetFocus()

	def quitar(self) -> None:
		indice = self._seleccionada()
		if indice >= 0:
			self.asignar(indice, "")

	def restablecer(self) -> None:
		indice = self._seleccionada()
		if indice >= 0:
			self.asignar(indice, self._acciones[indice].atajo)

	def restablecer_todos(self) -> None:
		if confirmar(self, _("¿Volver a los atajos de fábrica en todas las acciones?"), _("Restablecer todos")) == wx.ID_YES:
			self.atajos = catalogo.atajos_de_fabrica()
			self.rellenar()

	def guardar(self) -> None:
		"""Guarda solo lo que difiere de fábrica y vuelve a registrar las teclas."""
		fabrica = catalogo.atajos_de_fabrica()
		cambiados = {accion: atajo for accion, atajo in self.atajos.items() if atajo != fabrica.get(accion, "")}
		self._config.establecer("teclas", cambiados)
		self._config.guardar()
		resultado = self._controlador.aplicar_teclas() if self._controlador else None
		for indice in range(len(self._acciones)):
			self._actualizar_fila(indice)
		if resultado is not None and resultado.fallidos:
			nombres = "\n".join(
				f"- {_(catalogo.POR_ID[a].nombre)}: {motivo}" for a, motivo in resultado.fallidos.items() if a in catalogo.POR_ID
			)
			mostrar_mensaje(
				self,
				_("Algunas teclas no se pudieron activar:\n\n{lista}\n\nElija otra combinación para ellas.").format(lista=nombres),
				_("Teclas globales"),
				wx.ICON_WARNING,
			)

	def _al_aplicar(self, _evento: wx.CommandEvent) -> None:
		self.guardar()

	def _al_aceptar(self, evento: wx.CommandEvent) -> None:
		self.guardar()
		evento.Skip()
