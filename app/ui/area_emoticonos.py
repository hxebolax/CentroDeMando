"""Área de emoticonos: buscar, elegir e insertar emojis, símbolos y kaomoji.

Se usa en la pestaña «Emoticonos» de la ventana principal y en la ventana
rápida. Quien la contiene decide qué hace Intro (``al_insertar``): escribir
en la ventana de la que se vino.

Controles, en orden de tabulación:

- «Buscar emoticono» (Alt+B): búsqueda mientras se escribe, sin tildes, en
  el nombre y las palabras clave. Flecha abajo baja a la lista.
- «Grupo» (Alt+G): usados recientemente, favoritos, los grupos de Unicode,
  símbolos tipográficos y kaomoji. Al buscar se busca en todos.
- «Lista de emoticonos» (Alt+L): nombre y grupo de cada uno.
- «Tono de piel» (Alt+T): se aplica a los emojis de personas y manos.
- «Texto para insertar» (Alt+X): Control+Intro va añadiendo aquí emojis para
  insertarlos todos juntos; se puede editar.

Por qué la lista dice el NOMBRE y no el carácter: los lectores de pantalla ya
leen el emoji por su nombre; «😀 cara sonriendo» se oiría dos veces. Una
opción muestra también el carácter para quien lo quiera ver.
"""

from __future__ import annotations

import builtins
from collections.abc import Callable
from typing import TYPE_CHECKING

import wx

from app.services import emojis as servicio_emojis
from app.services.emojis import GRUPO_FAVORITOS, GRUPO_RECIENTES, NOMBRES_TONOS, Emoji, anotar_reciente
from app.ui import listas
from app.ui.listas import actualizar_lista

if TYPE_CHECKING:
	from app.ui.controlador import Controlador


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


RETRASO_BUSQUEDA_MS = 200
LIMITE_RESULTADOS = 400


class AreaEmoticonos(wx.Panel):
	"""Selector de emoticonos. ``al_insertar(texto)`` decide dónde se escribe."""

	def __init__(self, padre: wx.Window, controlador: Controlador, al_insertar: Callable[[str], None]) -> None:
		super().__init__(padre)
		self.controlador = controlador
		self.config = controlador.config
		self.catalogo = servicio_emojis.catalogo()
		self._al_insertar = al_insertar
		self._emojis: list[Emoji] = []
		self._claves: list[str] = []
		self._busqueda_pendiente: wx.CallLater | None = None

		sizer = wx.BoxSizer(wx.VERTICAL)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		etiqueta_buscar = wx.StaticText(self, label=_("&Buscar emoticono:"))
		self.buscar = wx.TextCtrl(self)
		self.buscar.SetHelpText(
			_("Escriba parte del nombre o una palabra clave, sin preocuparse de las tildes. Flecha abajo baja a la lista.")
		)
		etiqueta_grupo = wx.StaticText(self, label=_("&Grupo:"))
		self._grupos = [GRUPO_RECIENTES, GRUPO_FAVORITOS, *self.catalogo.grupos]
		self.grupo = wx.Choice(self, choices=[_(g) for g in self._grupos])
		self.grupo.SetHelpText(_("Qué emoticonos se ven cuando no se está buscando."))
		fila.Add(etiqueta_buscar, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
		fila.Add(self.buscar, 1, wx.RIGHT, 12)
		fila.Add(etiqueta_grupo, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
		fila.Add(self.grupo, 0)
		sizer.Add(fila, 0, wx.EXPAND | wx.ALL, 8)

		etiqueta_lista = wx.StaticText(self, label=_("&Lista de emoticonos:"))
		self.lista = listas.crear_lista(
			self,
			_("Lista de emoticonos"),
			[(_("Nombre"), self.FromDIP(420)), (_("Grupo"), self.FromDIP(220))],
			_(
				"Intro inserta el emoticono en la ventana de la que vino; Mayúsculas+Intro solo lo copia; "
				"Control+Intro lo añade al texto para insertar; F4 lo marca como favorito."
			),
		)
		sizer.Add(etiqueta_lista, 0, wx.LEFT | wx.RIGHT, 8)
		sizer.Add(self.lista, 1, wx.EXPAND | wx.ALL, 8)

		fila = wx.BoxSizer(wx.HORIZONTAL)
		etiqueta_tono = wx.StaticText(self, label=_("&Tono de piel:"))
		self.tono = wx.Choice(self, choices=[_(t) for t in NOMBRES_TONOS])
		self.tono.SetSelection(min(max(int(self.config.obtener("emoticonos.tono", 0)), 0), len(NOMBRES_TONOS) - 1))
		self.tono.SetHelpText(_("Tono de piel de los emoticonos de personas y manos. Se recuerda."))
		etiqueta_texto = wx.StaticText(self, label=_("Te&xto para insertar:"))
		self.texto = wx.TextCtrl(self)
		self.texto.SetHelpText(
			_("Control+Intro en la lista añade aquí el emoticono. Intro en este campo inserta todo el texto en la ventana de la que vino.")
		)
		fila.Add(etiqueta_tono, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
		fila.Add(self.tono, 0, wx.RIGHT, 12)
		fila.Add(etiqueta_texto, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
		fila.Add(self.texto, 1)
		sizer.Add(fila, 0, wx.EXPAND | wx.ALL, 8)
		self.SetSizer(sizer)

		self.grupo.SetSelection(0 if self.config.obtener("emoticonos.recientes", []) else 2)
		self.buscar.Bind(wx.EVT_TEXT, self._al_escribir_busqueda)
		self.buscar.Bind(wx.EVT_KEY_DOWN, self._al_tecla_buscar)
		self.grupo.Bind(wx.EVT_CHOICE, lambda _e: self.refrescar())
		self.tono.Bind(wx.EVT_CHOICE, self._al_cambiar_tono)
		self.texto.Bind(wx.EVT_KEY_DOWN, self._al_tecla_texto)
		self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: self.insertar())
		self.lista.Bind(wx.EVT_CONTEXT_MENU, self._al_menu_contextual)
		self.refrescar()

	# ── Datos ───────────────────────────────────────────────────────────────

	def _con_tono(self, emoji: Emoji) -> str:
		return self.catalogo.con_tono(emoji.caracter, self.tono.GetSelection())

	def refrescar(self) -> None:
		if not self:
			return
		texto = self.buscar.GetValue().strip()
		grupo = self._grupos[max(self.grupo.GetSelection(), 0)]
		if texto:
			self._emojis = self.catalogo.buscar(texto, LIMITE_RESULTADOS)
		elif grupo == GRUPO_RECIENTES:
			self._emojis = self.catalogo.lista(self.config.obtener("emoticonos.recientes", []))
		elif grupo == GRUPO_FAVORITOS:
			self._emojis = self.catalogo.lista(self.config.obtener("emoticonos.favoritos", []))
		else:
			self._emojis = self.catalogo.del_grupo(grupo)
		con_caracter = bool(self.config.obtener("emoticonos.mostrar_caracter", False))
		favoritos = set(self.config.obtener("emoticonos.favoritos", []))
		filas = []
		for emoji in self._emojis:
			nombre = emoji.describir() if con_caracter else emoji.nombre
			if emoji.caracter in favoritos and grupo != GRUPO_FAVORITOS:
				nombre += _(" (favorito)")
			filas.append((emoji.caracter, (nombre, _(emoji.grupo))))
		actualizar_lista(self.lista, filas, self._claves)
		if self.catalogo.error:
			self.controlador.hablar(self.catalogo.error, True)

	def seleccionado(self) -> Emoji | None:
		fila = self.lista.fila_actual()
		return self._emojis[fila] if 0 <= fila < len(self._emojis) else None

	def enfocar(self) -> None:
		if self.lista.numero_filas():
			self.lista.SetFocus()
			if self.lista.GetFocusedItem() < 0:
				self.lista.enfocar_fila(0, anunciar=False)
		else:
			self.buscar.SetFocus()

	# ── Acciones ────────────────────────────────────────────────────────────

	def _anotar_reciente(self, caracter: str) -> None:
		maximo = int(self.config.obtener("emoticonos.maximo_recientes", 40))
		self.config.establecer("emoticonos.recientes", anotar_reciente(self.config.obtener("emoticonos.recientes", []), caracter, maximo))

	def insertar(self) -> None:
		"""Intro: el texto acumulado si lo hay; si no, el emoticono seleccionado."""
		acumulado = self.texto.GetValue()
		if acumulado:
			self.texto.SetValue("")
			self._al_insertar(acumulado)
			return
		emoji = self.seleccionado()
		if emoji is None:
			return
		caracter = self._con_tono(emoji)
		self._anotar_reciente(emoji.caracter)
		self._al_insertar(caracter)

	def copiar(self) -> None:
		emoji = self.seleccionado()
		if emoji is None:
			return
		caracter = self._con_tono(emoji)
		self._anotar_reciente(emoji.caracter)
		self.controlador.copiar_texto(caracter)
		self.controlador.hablar(_("Copiado {nombre}").format(nombre=emoji.nombre), True)

	def acumular(self) -> None:
		emoji = self.seleccionado()
		if emoji is None:
			return
		self.texto.AppendText(self._con_tono(emoji))
		self._anotar_reciente(emoji.caracter)
		self.controlador.hablar(_("Añadido {nombre}").format(nombre=emoji.nombre), True)

	def alternar_favorito(self) -> None:
		emoji = self.seleccionado()
		if emoji is None:
			return
		favoritos = list(self.config.obtener("emoticonos.favoritos", []))
		if emoji.caracter in favoritos:
			favoritos.remove(emoji.caracter)
			mensaje = _("Quitado de favoritos")
		else:
			favoritos.append(emoji.caracter)
			mensaje = _("Añadido a favoritos")
		self.config.establecer("emoticonos.favoritos", favoritos)
		self.config.guardar()
		self.controlador.hablar(mensaje, True)
		self.refrescar()

	def copiar_nombre(self) -> None:
		emoji = self.seleccionado()
		if emoji is not None:
			self.controlador.copiar_texto(emoji.nombre)
			self.controlador.hablar(_("Nombre copiado"), True)

	def copiar_codigo(self) -> None:
		"""«U+1F44B U+1F3FD»: el código Unicode de cada carácter."""
		emoji = self.seleccionado()
		if emoji is not None:
			codigo = " ".join(f"U+{ord(c):04X}" for c in self._con_tono(emoji))
			self.controlador.copiar_texto(codigo)
			self.controlador.hablar(_("Copiado {codigo}").format(codigo=codigo), True)

	def _al_menu_contextual(self, evento: wx.ContextMenuEvent) -> None:
		emoji = self.seleccionado()
		if emoji is None:
			return
		favoritos = self.config.obtener("emoticonos.favoritos", [])
		menu = wx.Menu()
		for etiqueta, funcion in (
			(_("&Insertar en la ventana anterior"), self.insertar),
			(_("&Copiar al portapapeles"), self.copiar),
			(_("&Añadir al texto para insertar"), self.acumular),
			(_("Quitar de &favoritos") if emoji.caracter in favoritos else _("Añadir a &favoritos"), self.alternar_favorito),
			(_("Copiar el &nombre"), self.copiar_nombre),
			(_("Copiar el código &Unicode"), self.copiar_codigo),
		):
			item = menu.Append(wx.ID_ANY, etiqueta)
			menu.Bind(wx.EVT_MENU, lambda _e, f=funcion: f(), item)
		posicion = evento.GetPosition()
		if posicion == wx.DefaultPosition:
			rect = self.lista.GetItemRect(max(self.lista.GetFocusedItem(), 0))
			posicion = wx.Point(rect.x + 20, rect.y + rect.height)
		else:
			posicion = self.lista.ScreenToClient(posicion)
		try:
			self.lista.PopupMenu(menu, posicion)
		finally:
			menu.Destroy()

	def vaciar_recientes(self) -> None:
		self.config.establecer("emoticonos.recientes", [])
		self.config.guardar()
		self.refrescar()

	# ── Teclado ─────────────────────────────────────────────────────────────

	def manejar_tecla(self, evento: wx.KeyEvent) -> bool:
		"""Teclas de la lista, atendidas antes que los atajos de menú."""
		if wx.Window.FindFocus() is not self.lista:
			return False
		tecla, modificadores = evento.GetKeyCode(), evento.GetModifiers()
		intro = tecla in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER)
		if intro and modificadores == wx.MOD_SHIFT:
			self.copiar()
		elif intro and modificadores == wx.MOD_CONTROL:
			self.acumular()
		elif tecla == wx.WXK_F4 and modificadores == wx.MOD_NONE:
			self.alternar_favorito()
		else:
			return False
		return True

	def _al_cambiar_tono(self, _evento: wx.CommandEvent) -> None:
		self.config.establecer("emoticonos.tono", self.tono.GetSelection())

	def _al_escribir_busqueda(self, _evento: wx.CommandEvent) -> None:
		if self._busqueda_pendiente is not None:
			self._busqueda_pendiente.Stop()
		self._busqueda_pendiente = wx.CallLater(RETRASO_BUSQUEDA_MS, self._refrescar_busqueda)

	def _refrescar_busqueda(self) -> None:
		self.refrescar()
		if self.buscar.GetValue().strip():
			cuantos = len(self._emojis)
			self.controlador.hablar(
				_("Sin resultados") if not cuantos else (_("1 resultado") if cuantos == 1 else _("{n} resultados").format(n=cuantos))
			)

	def _al_tecla_buscar(self, evento: wx.KeyEvent) -> None:
		tecla = evento.GetKeyCode()
		if tecla in (wx.WXK_DOWN, wx.WXK_NUMPAD_DOWN, wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and not evento.HasAnyModifiers():
			if self._busqueda_pendiente is not None and self._busqueda_pendiente.IsRunning():
				self._busqueda_pendiente.Stop()
				self.refrescar()
			if not self._emojis:
				self.controlador.hablar(_("No se encontró ningún emoticono"), True)
				return
			if tecla in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
				self.lista.enfocar_fila(0, anunciar=False)
				self.insertar()
				return
			self.enfocar()
			return
		evento.Skip()

	def _al_tecla_texto(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and not evento.HasAnyModifiers():
			if self.texto.GetValue():
				self.insertar()
			return
		evento.Skip()
