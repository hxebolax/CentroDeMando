"""Área del portapapeles: historial con búsqueda, filtro y vista previa.

La misma área se usa en la pestaña «Portapapeles» de la ventana principal y
en la ventana rápida que abre la tecla global. Quien la contiene decide qué
hace Intro (``al_pegar``): pegar en la ventana de la que se vino.

Controles, en orden de tabulación (la etiqueta SIEMPRE justo antes):

- «Buscar en el historial» (Alt+B): filtra mientras se escribe; Flecha abajo
  baja a la lista.
- «Mostrar» (Alt+S): todo, favoritos, textos, imágenes o archivos.
- «Elementos copiados» (Alt+C): del más reciente al más antiguo. Columnas:
  contenido, tipo, programa de origen, cuándo y favorito.
- «Contenido» (Alt+T): el texto completo del elemento, de solo lectura.

Teclas en la lista: Intro pega, Mayúsculas+Intro solo copia, F2 cambia el
nombre, F4 marca o quita de favoritos, Suprimir elimina.
"""

from __future__ import annotations

import builtins
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

import wx

from app.services.portapapeles import (
	TRANSFORMACIONES,
	FILTRO_ARCHIVOS,
	FILTRO_FAVORITOS,
	FILTRO_IMAGENES,
	FILTRO_TEXTO,
	FILTRO_TODO,
	Elemento,
	describir_tiempo,
)
from app.ui import listas
from app.ui.accesibilidad.dialogos import confirmar, pedir_texto
from app.ui.listas import actualizar_lista

if TYPE_CHECKING:
	from app.ui.controlador import Controlador

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


FILTROS = [
	(FILTRO_TODO, "Todo"),
	(FILTRO_FAVORITOS, "Favoritos"),
	(FILTRO_TEXTO, "Textos"),
	(FILTRO_IMAGENES, "Imágenes"),
	(FILTRO_ARCHIVOS, "Archivos"),
]
RETRASO_BUSQUEDA_MS = 200


class AreaPortapapeles(wx.Panel):
	"""Historial del portapapeles. ``al_pegar(id)`` decide a dónde se pega."""

	def __init__(self, padre: wx.Window, controlador: Controlador, al_pegar: Callable[..., None]) -> None:
		super().__init__(padre)
		self.controlador = controlador
		self._al_pegar = al_pegar
		self._elementos: list[Elemento] = []
		self._claves: list[int] = []
		self._busqueda_pendiente: wx.CallLater | None = None

		sizer = wx.BoxSizer(wx.VERTICAL)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		etiqueta_buscar = wx.StaticText(self, label=_("&Buscar en el historial:"))
		self.buscar = wx.TextCtrl(self)
		self.buscar.SetHelpText(_("Escriba para filtrar el historial mientras escribe. Flecha abajo baja a la lista."))
		etiqueta_filtro = wx.StaticText(self, label=_("Mo&strar:"))
		self.filtro = wx.Choice(self, choices=[_(nombre) for _clave, nombre in FILTROS])
		self.filtro.SetSelection(0)
		self.filtro.SetHelpText(_("Qué elementos se ven: todos, solo los favoritos, textos, imágenes o archivos."))
		fila.Add(etiqueta_buscar, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
		fila.Add(self.buscar, 1, wx.RIGHT, 12)
		fila.Add(etiqueta_filtro, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
		fila.Add(self.filtro, 0)
		sizer.Add(fila, 0, wx.EXPAND | wx.ALL, 8)

		etiqueta_lista = wx.StaticText(self, label=_("Elementos copia&dos:"))
		self.lista = listas.crear_lista(
			self,
			_("Elementos copiados"),
			[
				(_("Contenido"), self.FromDIP(420)),
				(_("Tipo"), self.FromDIP(170)),
				(_("Origen"), self.FromDIP(130)),
				(_("Copiado"), self.FromDIP(140)),
				(_("Favorito"), self.FromDIP(80)),
			],
			_(
				"Historial del portapapeles. Intro pega el elemento en la ventana de la que vino; Mayúsculas+Intro solo lo copia; "
				"F2 le cambia el nombre; F4 lo marca como favorito; Suprimir lo elimina; la tecla Aplicaciones abre sus acciones."
			),
		)
		sizer.Add(etiqueta_lista, 0, wx.LEFT | wx.RIGHT, 8)
		sizer.Add(self.lista, 3, wx.EXPAND | wx.ALL, 8)
		etiqueta_contenido = wx.StaticText(self, label=_("Con&tenido:"))
		self.contenido = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2)
		self.contenido.SetHelpText(_("Texto completo del elemento seleccionado, de solo lectura."))
		sizer.Add(etiqueta_contenido, 0, wx.LEFT | wx.RIGHT, 8)
		sizer.Add(self.contenido, 1, wx.EXPAND | wx.ALL, 8)
		self.SetSizer(sizer)

		self.buscar.Bind(wx.EVT_TEXT, self._al_escribir_busqueda)
		self.buscar.Bind(wx.EVT_KEY_DOWN, self._al_tecla_buscar)
		self.filtro.Bind(wx.EVT_CHOICE, lambda _e: self.refrescar())
		self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: self.pegar())
		self.lista.Bind(wx.EVT_LIST_ITEM_SELECTED, lambda _e: self._mostrar_contenido())
		self.lista.Bind(wx.EVT_CONTEXT_MENU, self._al_menu_contextual)

	# ── Datos ───────────────────────────────────────────────────────────────

	def mostrar_solo_favoritos(self) -> None:
		"""Pone el filtro «Favoritos» (ventana rápida de favoritos)."""
		claves = [clave for clave, _nombre in FILTROS]
		self.filtro.SetSelection(claves.index(FILTRO_FAVORITOS))

	def refrescar(self) -> None:
		"""Relee el historial con la búsqueda y el filtro actuales."""
		if not self:
			return
		try:
			self._elementos = self.controlador.portapapeles.historial.listar(
				FILTROS[max(self.filtro.GetSelection(), 0)][0], self.buscar.GetValue()
			)
		except Exception:  # noqa: BLE001 - base de datos bloqueada o dañada: se avisa y se sigue
			log.exception("No se pudo leer el historial del portapapeles")
			self._elementos = []
		filas = [
			(
				e.id,
				(e.resumen(), e.descripcion_tipo(), e.origen or _("desconocido"), describir_tiempo(e.usado), _("sí") if e.favorito else ""),
			)
			for e in self._elementos
		]
		actualizar_lista(self.lista, filas, self._claves)
		self._mostrar_contenido()

	def seleccionado(self) -> Elemento | None:
		fila = self.lista.fila_actual()
		if 0 <= fila < len(self._claves):
			identificador = self._claves[fila]
			return next((e for e in self._elementos if e.id == identificador), None)
		return None

	def _mostrar_contenido(self) -> None:
		elemento = self.seleccionado()
		texto = elemento.texto_completo() if elemento else ""
		if self.contenido.GetValue() != texto:
			self.contenido.SetValue(texto)

	def enfocar(self) -> None:
		"""Foco en la lista (o en la búsqueda si está vacía)."""
		if self.lista.numero_filas():
			self.lista.SetFocus()
			if self.lista.GetFocusedItem() < 0:
				self.lista.enfocar_fila(0, anunciar=False)
		else:
			self.buscar.SetFocus()

	# ── Acciones ────────────────────────────────────────────────────────────

	def pegar(self, transformacion: str | None = None) -> None:
		elemento = self.seleccionado()
		if elemento is None:
			return
		if transformacion and elemento.tipo == "imagen":
			self.controlador.hablar(_("Una imagen no se puede transformar."), True)
			return
		self._al_pegar(elemento.id, transformacion)

	def copiar(self) -> None:
		elemento = self.seleccionado()
		if elemento is not None:
			self.controlador.copiar_elemento(elemento.id)

	def alternar_favorito(self) -> None:
		elemento = self.seleccionado()
		if elemento is None:
			return
		self.controlador.portapapeles.historial.poner_favorito(elemento.id, not elemento.favorito)
		self.controlador.hablar(_("Quitado de favoritos") if elemento.favorito else _("Añadido a favoritos"), True)
		self.refrescar()

	def renombrar(self) -> None:
		elemento = self.seleccionado()
		if elemento is None:
			return
		nombre = pedir_texto(
			self,
			_("&Nombre del elemento:"),
			_("Cambiar el nombre"),
			elemento.nombre,
			max_caracteres=200,
			ayuda=_("El nombre solo sirve para reconocerlo en la lista; al pegar se pega el contenido real. Vacío = mostrar el contenido."),
		)
		if nombre is not None:
			self.controlador.portapapeles.historial.renombrar(elemento.id, nombre)
			self.refrescar()

	def eliminar(self) -> None:
		elemento = self.seleccionado()
		if elemento is None:
			return
		self.controlador.portapapeles.historial.eliminar([elemento.id])
		self.controlador.hablar(_("Eliminado"), True)
		self.refrescar()

	def vaciar(self) -> None:
		respuesta = confirmar(
			self,
			_("¿Vaciar el historial del portapapeles? Los favoritos se conservan."),
			_("Vaciar el historial"),
			peligroso=True,
		)
		if respuesta == wx.ID_YES:
			borrados = self.controlador.portapapeles.historial.vaciar(incluir_favoritos=False)
			self.controlador.hablar(_("Eliminados {n} elementos").format(n=borrados), True)
			self.refrescar()

	def acciones(self) -> list:
		"""Órdenes del menú Acción (las del elemento primero; la primera es la de Intro)."""
		elemento = self.seleccionado()
		hay = elemento is not None
		texto = hay and elemento.tipo != "imagen"
		return [
			(_("&Pegar en la ventana anterior (Intro)"), self.pegar, hay),
			(_("Pegar como texto &sin formato (Control+Mayúsculas+Intro)"), lambda: self.pegar("sin_formato"), texto),
			(_("&Copiar al portapapeles (Mayúsculas+Intro)"), self.copiar, hay),
			(_("Añadir o quitar de &favoritos\tF4"), self.alternar_favorito, hay),
			(_("Cambiar el &nombre...\tF2"), self.renombrar, hay),
			(_("&Eliminar (Suprimir)"), self.eliminar, hay),
			None,
			(_("&Vaciar el historial..."), self.vaciar, True),
			(_("&Detener la captura"), self.controlador.alternar_captura, True, self.controlador.portapapeles.pausado),
		]

	# ── Teclado ─────────────────────────────────────────────────────────────

	def manejar_tecla(self, evento: wx.KeyEvent) -> bool:
		"""Teclas propias de la lista. Se llama desde ``EVT_CHAR_HOOK`` del contenedor,
		antes que los atajos de menú (F2 es también «cambiar el nombre del escritorio»).
		"""
		if wx.Window.FindFocus() is not self.lista:
			return False
		tecla, modificadores = evento.GetKeyCode(), evento.GetModifiers()
		if tecla in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and modificadores == wx.MOD_SHIFT:
			self.copiar()
		elif tecla in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and modificadores == wx.MOD_CONTROL | wx.MOD_SHIFT:
			self.pegar("sin_formato")
		elif tecla == wx.WXK_F2 and modificadores == wx.MOD_NONE:
			self.renombrar()
		elif tecla == wx.WXK_F4 and modificadores == wx.MOD_NONE:
			self.alternar_favorito()
		elif tecla in (wx.WXK_DELETE, wx.WXK_NUMPAD_DELETE) and modificadores == wx.MOD_NONE:
			self.eliminar()
		else:
			return False
		return True

	def _al_escribir_busqueda(self, _evento: wx.CommandEvent) -> None:
		# Se espera a que se deje de escribir: releer en cada letra haría hablar a la lista sin parar.
		if self._busqueda_pendiente is not None:
			self._busqueda_pendiente.Stop()
		self._busqueda_pendiente = wx.CallLater(RETRASO_BUSQUEDA_MS, self._refrescar_busqueda)

	def _refrescar_busqueda(self) -> None:
		"""Tras escribir en la búsqueda: relee y dice cuántos resultados hay."""
		self.refrescar()
		if self.buscar.GetValue().strip():
			cuantos = len(self._elementos)
			self.controlador.hablar(
				_("Sin resultados") if not cuantos else (_("1 resultado") if cuantos == 1 else _("{n} resultados").format(n=cuantos))
			)

	def _al_tecla_buscar(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() in (wx.WXK_DOWN, wx.WXK_NUMPAD_DOWN) and not evento.HasAnyModifiers():
			if self._busqueda_pendiente is not None and self._busqueda_pendiente.IsRunning():
				self._busqueda_pendiente.Stop()
				self.refrescar()
			self.enfocar()
			return
		if evento.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and not evento.HasAnyModifiers():
			self.refrescar()
			if self._elementos:
				self.lista.enfocar_fila(0, anunciar=False)
				self.pegar()
			return
		evento.Skip()

	def _al_menu_contextual(self, evento: wx.ContextMenuEvent) -> None:
		elemento = self.seleccionado()
		if elemento is None:
			return
		menu = wx.Menu()
		for etiqueta, funcion in (
			(_("&Pegar en la ventana anterior"), self.pegar),
			(_("Pegar como texto &sin formato"), lambda: self.pegar("sin_formato")),
			(_("&Copiar al portapapeles"), self.copiar),
			(_("Quitar de &favoritos") if elemento.favorito else _("Añadir a &favoritos"), self.alternar_favorito),
			(_("Cambiar el &nombre..."), self.renombrar),
			(_("&Eliminar"), self.eliminar),
		):
			item = menu.Append(wx.ID_ANY, etiqueta)
			menu.Bind(wx.EVT_MENU, lambda _e, f=funcion: f(), item)
		if elemento.tipo != "imagen":
			submenu = wx.Menu()
			for clave, (nombre, _funcion) in TRANSFORMACIONES.items():
				if clave == "sin_formato":
					continue
				item = submenu.Append(wx.ID_ANY, _(nombre))
				submenu.Bind(wx.EVT_MENU, lambda _e, c=clave: self.pegar(c), item)
			menu.AppendSubMenu(submenu, _("Pegar &transformado"))
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
