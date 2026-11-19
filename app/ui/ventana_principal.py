"""Ventana principal: escritorios y sus ventanas.

Contenido (en orden de tabulación):

1. «Lista de escritorios» (Alt+L): Número, Nombre, Ventanas y Estado
   («actual»). Intro va al escritorio; F2 le cambia el nombre; Suprimir lo
   elimina; Alt+Mayús+Arriba/Abajo cambian el orden.
2. «Ventanas del escritorio seleccionado» (Alt+T): Título, Programa y
   Escritorio. Intro cambia a esa ventana; la tecla Aplicaciones abre sus
   acciones (mover, mostrar en todos, cerrar).

Decisiones:

- Las listas se actualizan EN SU SITIO (solo las celdas que cambian) y
  conservan el elemento seleccionado por su identificador: el lector no
  vuelve a leer la fila ni el usuario pierde su posición.
- Toda operación sobre escritorios va al hilo de escritorios a través del
  controlador; la ventana solo pinta lo que le llega.
- El gestor vive en la bandeja: cerrar, minimizar o Escape lo ocultan ahí y
  las teclas globales siguen funcionando. Escritorios, Salir cierra de verdad.
"""

from __future__ import annotations

import builtins
import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import wx

from app.core import paths, voz
from app.core.config import Configuracion
from app.core.instancia_unica import ORDEN_ABRIR, ORDEN_MOSTRAR, InstanciaUnica
from app.core.version import NOMBRE_APLICACION
from app.services import ventanas_win32 as w32
from app.services.escritorios import EstadoEscritorios, InfoVentana
from app.ui import listas
from app.ui.listas import actualizar_lista
from app.ui.accesibilidad.dialogos import confirmar, pedir_texto
from app.ui.bandeja import IconoBandeja
from app.ui.controlador import Controlador
from app.ui.dialogo_texto import mostrar_documento, mostrar_error, mostrar_mensaje

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


INTERVALO_BUZON_MS = 500
TAMANO_MINIMO = (400, 300)

# (título, [(nombre, etiqueta, ayuda, tipo) | None]); ``None`` es un separador.
# ``nombre`` es el sufijo del manejador ``_al_<nombre>``.
# Barra de menús FIJA (guías de Windows: pocos menús, los mismos siempre).
# El menú «Acción» va en la segunda posición y se rehace con la pestaña visible:
# así cada área tiene sus órdenes sin llenar la barra de menús de áreas.
# (título, [(nombre, etiqueta, ayuda, tipo) | None]); el manejador es ``_al_<nombre>``.
MENUS: list[tuple[str, list[tuple[str, str, str, int] | None]]] = [
	(
		"&Archivo",
		[
			("lanzador", "&Lanzador...\tCtrl+Shift+P", "Busca y abre programas, ajustes de Windows y acciones de Centro de Mando; también calcula.", wx.ITEM_NORMAL),
			("abrir_rapida", "Abrir la lista &rápida del área\tCtrl+L", "Abre la ventana rápida del área actual, la misma de su tecla global.", wx.ITEM_NORMAL),
			("exportar", "E&xportar...", "Exporta el historial del área actual (portapapeles o notificaciones).", wx.ITEM_NORMAL),
			None,
			("ocultar", "&Ocultar en la bandeja", "Oculta la ventana; Centro de Mando sigue en la bandeja (también con Escape).", wx.ITEM_NORMAL),
			("salir", "&Salir\tCtrl+Q", "Cierra Centro de Mando por completo; las teclas globales dejan de funcionar.", wx.ITEM_NORMAL),
		],
	),
	(
		"&Ir",
		[
			("area_escritorios", "&1 Escritorios\tAlt+1", "Área de escritorios y ventanas.", wx.ITEM_NORMAL),
			("area_portapapeles", "&2 Portapapeles\tAlt+2", "Historial del portapapeles.", wx.ITEM_NORMAL),
			("area_fragmentos", "&3 Fragmentos de texto\tAlt+3", "Textos guardados para insertar.", wx.ITEM_NORMAL),
			("area_emoticonos", "&4 Emoticonos\tAlt+4", "Emojis, símbolos y kaomoji.", wx.ITEM_NORMAL),
			("area_notificaciones", "&5 Notificaciones\tAlt+5", "Historial de notificaciones.", wx.ITEM_NORMAL),
			("area_audio", "&6 Audio\tAlt+6", "Dispositivos de salida y volumen de cada aplicación.", wx.ITEM_NORMAL),
			("area_sistema", "&7 Sistema\tAlt+7", "Estado del equipo y energía.", wx.ITEM_NORMAL),
			("area_procesos", "&8 Ventanas y procesos\tAlt+8", "Ventanas abiertas y procesos: activar, siempre encima, cerrar, finalizar.", wx.ITEM_NORMAL),
			("area_temporizadores", "&9 Temporizadores y alarmas\tAlt+9", "Temporizadores, alarmas y recordatorios.", wx.ITEM_NORMAL),
			None,
			("ir_busqueda", "Al cuadro de &búsqueda\tCtrl+E", "Lleva el foco al buscador del área actual.", wx.ITEM_NORMAL),
		],
	),
	(
		"&Ver",
		[
			(
				"ver_todas",
				"&Ventanas de todos los escritorios",
				"En el área de escritorios, la lista de ventanas muestra las de todos los escritorios.",
				wx.ITEM_CHECK,
			),
			("barra_estado", "&Barra de estado", "Muestra u oculta la barra de estado.", wx.ITEM_CHECK),
			None,
			("decir_estado", "&Decir el estado del área\tCtrl+D", "Anuncia lo más importante del área actual.", wx.ITEM_NORMAL),
			("actualizar", "&Actualizar\tF5", "Vuelve a leer los datos del área actual.", wx.ITEM_NORMAL),
		],
	),
	(
		"&Herramientas",
		[
			("teclas_globales", "&Teclas globales...\tCtrl+T", "Ver y cambiar los atajos que funcionan desde cualquier programa.", wx.ITEM_NORMAL),
			("reglas", "&Reglas de ventanas...\tCtrl+R", "Llevar automáticamente las ventanas de ciertos programas a un escritorio.", wx.ITEM_NORMAL),
			("opciones", "&Opciones...\tCtrl+,", "Opciones de Centro de Mando.", wx.ITEM_NORMAL),
			None,
			("carpeta_datos", "Abrir la carpeta de &datos", "Abre en el Explorador la carpeta data del programa.", wx.ITEM_NORMAL),
			("carpeta_registros", "Abrir la carpeta de re&gistros", "Abre en el Explorador la carpeta de registros.", wx.ITEM_NORMAL),
		],
	),
	(
		"Ay&uda",
		[
			("manual", "&Manual de usuario\tF1", "Abre el manual de usuario.", wx.ITEM_NORMAL),
			("teclas", "&Lista de teclas\tCtrl+F1", "Muestra todos los atajos de teclado.", wx.ITEM_NORMAL),
			("novedades", "&Novedades de la versión", "Muestra los cambios de cada versión.", wx.ITEM_NORMAL),
			("ayuda_contextual", "Ayuda del control &enfocado\tCtrl+H", "Explica para qué sirve el control que tiene el foco.", wx.ITEM_NORMAL),
			None,
			(
				"buscar_actualizaciones",
				"&Buscar actualizaciones...",
				"Comprueba si hay una versión nueva de Centro de Mando y la instala (fuente elegible en Opciones, Actualizaciones).",
				wx.ITEM_NORMAL,
			),
			(
				"invitar_cafe",
				"&Invítame a un café si te gusta mi trabajo",
				"Abre en el navegador la página de donaciones de PayPal del autor.",
				wx.ITEM_NORMAL,
			),
			("acerca_de", "&Acerca de {nombre}...", "Muestra la versión y los datos técnicos del programa.", wx.ITEM_NORMAL),
		],
	),
]
TITULO_ACCION = "A&cción"


class VentanaPrincipal(wx.Frame):
	"""Ventana principal de Centro de Mando: áreas en pestañas, menús y bandeja."""

	def __init__(
		self, configuracion: Configuracion, instancia: InstanciaUnica | None = None, controlador: Controlador | None = None
	) -> None:
		super().__init__(None, title=NOMBRE_APLICACION)
		self._config = configuracion
		self._instancia = instancia
		# Las listas leen sus preferencias de lectura de esta configuración.
		listas.configurar(configuracion)
		self.controlador = controlador or Controlador(configuracion)
		self.controlador.ventana = self
		self._bandeja: IconoBandeja | None = None
		self._saliendo = False
		self._forzar_salida = False
		self._rect_normal: wx.Rect | None = None
		self._estado = EstadoEscritorios()
		self._ventanas: list[InfoVentana] = []
		self._claves_escritorios: list[str] = []
		self._claves_ventanas: list[int] = []
		self._selector = None
		self.elementos_menu: dict[str, wx.MenuItem] = {}

		self._crear_menus()
		self._crear_contenido()
		self.CreateStatusBar()
		self.SetStatusText(_("Cargando los escritorios virtuales..."))
		self._aplicar_barra_estado(bool(self._config.obtener("ventana.barra_estado", True)))
		self.elementos_menu["ver_todas"].Check(bool(self._config.obtener("ventana.ver_todas", False)))
		self._aplicar_icono()
		self._restaurar_geometria()

		self.Bind(wx.EVT_CLOSE, self._al_cerrar)
		self.Bind(wx.EVT_ICONIZE, self._al_minimizar)
		self.Bind(wx.EVT_SIZE, self._al_cambiar_geometria)
		self.Bind(wx.EVT_MOVE, self._al_cambiar_geometria)
		self.Bind(wx.EVT_ACTIVATE, self._al_activar_ventana)
		self.Bind(wx.EVT_CHAR_HOOK, self._al_tecla_ventana)

		self.controlador.suscribir(self._al_cambiar_estado)
		self.controlador.suscribir_no_molestar(lambda activo: self._bandeja.poner_no_molestar(activo) if self._bandeja is not None else None)
		self.reconstruir_menu_accion()

		self._temporizador_buzon = wx.Timer(self)
		self.Bind(wx.EVT_TIMER, self._al_revisar_buzon, self._temporizador_buzon)
		if self._instancia is not None:
			self._temporizador_buzon.Start(INTERVALO_BUZON_MS)

	# ── Construcción ─────────────────────────────────────────────────────────

	def _crear_menus(self) -> None:
		barra = wx.MenuBar()
		for titulo, elementos in MENUS:
			menu = wx.Menu()
			for elemento in elementos:
				if elemento is None:
					menu.AppendSeparator()
					continue
				nombre, etiqueta, ayuda, tipo = elemento
				item = menu.Append(wx.ID_ANY, _(etiqueta).format(nombre=NOMBRE_APLICACION), _(ayuda), tipo)
				self.Bind(wx.EVT_MENU, getattr(self, f"_al_{nombre}"), item)
				self.elementos_menu[nombre] = item
			barra.Append(menu, _(titulo))
		self._menu_accion = wx.Menu()
		self._ids_accion: list[int] = []
		barra.Insert(1, self._menu_accion, _(TITULO_ACCION))
		self.SetMenuBar(barra)
		# Al abrir el menú Acción se activan solo las órdenes que se pueden usar ahora.
		self.Bind(wx.EVT_MENU_OPEN, self._al_abrir_menu)
		self.Bind(wx.EVT_MENU_CLOSE, self._al_cerrar_menu)

	def _crear_contenido(self) -> None:
		"""Etiqueta SIEMPRE creada justo antes de su lista: de ella toma el nombre el lector."""
		# Tres áreas en pestañas (Control+Tabulador o Alt+1, 2 y 3 para cambiar).
		self.libro = wx.Notebook(self)
		self.panel = wx.Panel(self.libro)
		etiqueta = wx.StaticText(self.panel, label=_("&Lista de escritorios:"))
		self.lista = listas.crear_lista(
			self.panel,
			_("Lista de escritorios"),
			[
				(_("Número"), self.FromDIP(70)),
				(_("Nombre"), self.FromDIP(300)),
				(_("Ventanas"), self.FromDIP(90)),
				(_("Estado"), self.FromDIP(100)),
			],
			_(
				"Escritorios virtuales. Intro va al escritorio, F2 le cambia el nombre, Suprimir lo elimina, "
				"Alt+Mayúsculas+flechas arriba o abajo cambian su orden y la tecla Aplicaciones abre el menú contextual."
			),
		)
		etiqueta_ventanas = wx.StaticText(self.panel, label=_("Ven&tanas del escritorio seleccionado:"))
		self.lista_ventanas = listas.crear_lista(
			self.panel,
			_("Ventanas del escritorio seleccionado"),
			[(_("Título"), self.FromDIP(380)), (_("Programa"), self.FromDIP(160)), (_("Escritorio"), self.FromDIP(200))],
			_(
				"Ventanas del escritorio seleccionado (o de todos, según el menú Ver). Intro cambia a la ventana, "
				"Control+M la mueve a otro escritorio y la tecla Aplicaciones abre sus acciones."
			),
		)

		self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: self._al_ir(None))
		self.lista.Bind(wx.EVT_LIST_ITEM_SELECTED, lambda _e: self._pintar_ventanas())
		self.lista.Bind(wx.EVT_KEY_DOWN, self._al_tecla_lista)
		self.lista.Bind(wx.EVT_CONTEXT_MENU, self._al_menu_contextual_escritorios)
		self.lista_ventanas.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: self._al_activar_ventana_lista(None))
		self.lista_ventanas.Bind(wx.EVT_KEY_DOWN, self._al_tecla_lista_ventanas)
		self.lista_ventanas.Bind(wx.EVT_CONTEXT_MENU, self._al_menu_contextual_ventanas)

		sizer = wx.BoxSizer(wx.VERTICAL)
		sizer.Add(etiqueta, 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)
		sizer.Add(self.lista, 1, wx.EXPAND | wx.ALL, 8)
		sizer.Add(etiqueta_ventanas, 0, wx.LEFT | wx.RIGHT, 8)
		sizer.Add(self.lista_ventanas, 1, wx.EXPAND | wx.ALL, 8)
		self.panel.SetSizer(sizer)
		self.libro.AddPage(self.panel, _("Escritorios"))

		from app.ui.area_emoticonos import AreaEmoticonos
		from app.ui.area_portapapeles import AreaPortapapeles

		self.area_portapapeles = AreaPortapapeles(
			self.libro,
			self.controlador,
			lambda identificador, transformacion=None: self.controlador.pegar_elemento(identificador, 0, transformacion),
		)
		self.libro.AddPage(self.area_portapapeles, _("Portapapeles"))
		from app.ui.area_fragmentos import AreaFragmentos

		self.area_fragmentos = AreaFragmentos(self.libro, self.controlador, lambda f: self.controlador.insertar_fragmento(f, 0))
		self.libro.AddPage(self.area_fragmentos, _("Fragmentos"))
		self.area_emoticonos = AreaEmoticonos(self.libro, self.controlador, lambda texto: self.controlador.insertar_texto(texto, 0))
		self.libro.AddPage(self.area_emoticonos, _("Emoticonos"))
		from app.ui.area_notificaciones import AreaNotificaciones

		self.area_notificaciones = AreaNotificaciones(self.libro, self.controlador)
		self.libro.AddPage(self.area_notificaciones, _("Notificaciones"))
		from app.ui.area_audio import AreaAudio
		from app.ui.area_sistema import AreaSistema

		self.area_audio = AreaAudio(self.libro, self.controlador)
		self.libro.AddPage(self.area_audio, _("Audio"))
		self.area_sistema = AreaSistema(self.libro, self.controlador)
		self.libro.AddPage(self.area_sistema, _("Sistema"))
		from app.ui.area_procesos import AreaProcesos

		self.area_procesos = AreaProcesos(self.libro, self.controlador)
		self.libro.AddPage(self.area_procesos, _("Ventanas y procesos"))
		from app.ui.area_temporizadores import AreaTemporizadores

		self.area_temporizadores = AreaTemporizadores(self.libro, self.controlador)
		self.libro.AddPage(self.area_temporizadores, _("Temporizadores"))
		self.areas = [
			self.panel,
			self.area_portapapeles,
			self.area_fragmentos,
			self.area_emoticonos,
			self.area_notificaciones,
			self.area_audio,
			self.area_sistema,
			self.area_procesos,
			self.area_temporizadores,
		]
		self.controlador.suscribir_notificaciones(self._al_cambiar_notificaciones)
		marco = wx.BoxSizer(wx.VERTICAL)
		marco.Add(self.libro, 1, wx.EXPAND)
		self.SetSizer(marco)
		self.libro.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self._al_cambiar_area)
		self.controlador.suscribir_portapapeles(self._al_cambiar_historial)

	def _aplicar_icono(self) -> None:
		ruta = paths.ruta_iconos() / "app.ico"
		if ruta.is_file():
			icono = wx.Icon(str(ruta), wx.BITMAP_TYPE_ICO)
			if icono.IsOk():
				self.SetIcon(icono)

	def poner_estado(self, texto: str) -> None:
		"""Escribe en la barra de estado (lo que se anunció queda consultable)."""
		if self and self.GetStatusBar():
			self.SetStatusText(texto)

	# ── Estado de los escritorios ────────────────────────────────────────────

	def _al_cambiar_estado(self, estado: EstadoEscritorios) -> None:
		"""Llega en el hilo principal cada vez que cambian los escritorios o el actual."""
		if not self or self._saliendo:
			return
		self._estado = estado
		if self._bandeja is not None:
			self._bandeja.actualizar(estado)
		actual = estado.escritorio_actual()
		titulo = f"{NOMBRE_APLICACION} - {actual.describir()}" if actual else NOMBRE_APLICACION
		if self.GetTitle() != titulo:
			self.SetTitle(titulo)
		self._pintar_escritorios()
		if self.IsShown():
			self.refrescar_ventanas()

	def _pintar_escritorios(self) -> None:
		conteo: dict[str, int] = {}
		for ventana in self._ventanas:
			if not ventana.en_todos:
				conteo[ventana.id_escritorio] = conteo.get(ventana.id_escritorio, 0) + 1
		filas = [
			(
				e.id,
				(
					str(e.numero),
					e.nombre_visible,
					str(conteo.get(e.id, 0)) if self._ventanas or not e.actual else "",
					_("actual") if e.actual else "",
				),
			)
			for e in self._estado.escritorios
		]
		actualizar_lista(self.lista, filas, self._claves_escritorios)
		self._pintar_ventanas()

	def refrescar_ventanas(self) -> None:
		"""Pide la lista de ventanas al hilo de escritorios (asíncrono)."""
		self.controlador.servicio.obtener_ventanas(lambda ventanas: wx.CallAfter(self._al_recibir_ventanas, ventanas))

	def _al_recibir_ventanas(self, ventanas: list[InfoVentana]) -> None:
		if not self or self._saliendo:
			return
		self._ventanas = ventanas
		self._pintar_escritorios()

	def escritorio_seleccionado(self) -> int:
		"""Número del escritorio seleccionado en la lista (0 si ninguno)."""
		indice = self.lista.GetFirstSelected()
		if indice < 0:
			indice = self.lista.GetFocusedItem()
		if 0 <= indice < len(self._claves_escritorios):
			identificador = self._claves_escritorios[indice]
			return next((e.numero for e in self._estado.escritorios if e.id == identificador), 0)
		return 0

	def _pintar_ventanas(self) -> None:
		todas = self.elementos_menu["ver_todas"].IsChecked()
		seleccionado = self._estado.escritorio(self.escritorio_seleccionado())
		visibles = [v for v in self._ventanas if todas or (seleccionado is not None and (v.id_escritorio == seleccionado.id or v.en_todos))]
		nombres = {e.id: e.describir() for e in self._estado.escritorios}
		filas = [
			(
				v.hwnd,
				(
					v.titulo or _("(sin título)"),
					v.proceso,
					_("Todos") if v.en_todos else nombres.get(v.id_escritorio, _("desconocido")),
				),
			)
			for v in visibles
		]
		actualizar_lista(self.lista_ventanas, filas, self._claves_ventanas)

	def ventana_seleccionada(self) -> InfoVentana | None:
		indice = self.lista_ventanas.GetFirstSelected()
		if indice < 0:
			indice = self.lista_ventanas.GetFocusedItem()
		if 0 <= indice < len(self._claves_ventanas):
			hwnd = self._claves_ventanas[indice]
			return next((v for v in self._ventanas if v.hwnd == hwnd), None)
		return None

	# ── Mostrar, ocultar, bandeja ────────────────────────────────────────────

	def mostrar(self) -> None:
		self.Show()
		self.Raise()
		self._aplicar_bandeja()
		wx.CallAfter(self._enfocar_lista)

	def _enfocar_lista(self) -> None:
		"""Foco en la lista de escritorios, sobre el actual."""
		if not self:
			return
		self.lista.SetFocus()
		if self.lista.GetItemCount():
			actual = self._estado.escritorio_actual()
			indice = self._claves_escritorios.index(actual.id) if actual and actual.id in self._claves_escritorios else 0
			self.lista.Focus(indice)
			self.lista.Select(indice)

	def _crear_bandeja(self) -> bool:
		if self._bandeja is None:
			self._bandeja = IconoBandeja(
				NOMBRE_APLICACION,
				self.restaurar,
				self.salir,
				al_accion=self.controlador.ejecutar,
				obtener_estado=lambda: self._estado,
				al_menu=self._al_menu_bandeja,
			)
			self._bandeja.actualizar(self._estado)
			self._bandeja.poner_no_molestar(self.controlador.no_molestar_activo())
		if not self._bandeja.IsIconInstalled() and not self._bandeja.mostrar():
			log.warning("No se pudo poner el icono en la bandeja.")
			self._quitar_bandeja()
			return False
		return True

	def _aplicar_bandeja(self) -> None:
		"""Pone o quita el icono según «Icono siempre en la bandeja» y la visibilidad."""
		if self._config.obtener("general.icono_siempre", True) or not self.IsShown():
			self._crear_bandeja()
		else:
			self._quitar_bandeja()

	def ocultar_en_bandeja(self, avisar: bool = True) -> bool:
		"""Oculta la ventana dejando el icono. Si no se pudo poner el icono, NO se oculta."""
		if not self._crear_bandeja():
			return False
		self.Hide()
		if avisar:
			voz.hablar(_("{nombre} sigue en la bandeja del sistema.").format(nombre=NOMBRE_APLICACION))
		return True

	def _quitar_bandeja(self) -> None:
		if self._bandeja is not None:
			self._bandeja.quitar()
			self._bandeja = None

	def restaurar(self) -> None:
		"""Muestra la ventana desde la bandeja, minimizada o detrás de otras."""
		if not self:
			return
		self.Show()
		if self.IsIconized():
			self.Iconize(False)
		self.Raise()
		wx.CallAfter(self._aplicar_bandeja)
		self.refrescar_ventanas()
		dialogo = next((v for v in wx.GetTopLevelWindows() if isinstance(v, wx.Dialog) and v.IsShown() and v.IsEnabled()), None)
		if dialogo is not None:
			dialogo.Raise()
			dialogo.SetFocus()
		else:
			wx.CallAfter(self._enfocar_lista)
		if not w32.forzar_primer_plano(self.GetHandle()):
			self.RequestUserAttention()

	def salir(self) -> None:
		self._forzar_salida = True
		self.Close()

	def _al_menu_bandeja(self, orden: str) -> None:
		if orden.startswith("ir:"):
			self.controlador.servicio.ir_a(int(orden[3:]))
		elif orden == "teclas_globales":
			self.restaurar()
			wx.CallAfter(self._al_teclas_globales, None)
		elif orden == "opciones":
			self.restaurar()
			wx.CallAfter(self._al_opciones, None)

	# ── Acciones de interfaz pedidas por las teclas globales ─────────────────

	def ejecutar_accion_de_interfaz(self, accion: str) -> None:
		if accion == "mostrar_gestor":
			if self.IsShown() and self.IsActive():
				self.ocultar_en_bandeja()
			else:
				self.restaurar()
		elif accion == "selector":
			self.abrir_selector_escritorios()
		elif accion == "buscar_ventana":
			self.abrir_buscador_ventanas()
		elif accion == "renombrar_actual":
			self.renombrar(self._estado.actual)
		elif accion == "eliminar_actual":
			self.eliminar(self._estado.actual)

	def _padre_dialogos(self) -> wx.Window | None:
		"""Los diálogos pedidos desde una tecla global con la ventana oculta van sin padre."""
		return self if self.IsShown() else None

	def _traer_dialogo_al_frente(self) -> None:
		"""Un diálogo abierto desde una tecla global debe quedar delante de la aplicación activa."""
		for ventana in wx.GetTopLevelWindows():
			if isinstance(ventana, wx.Dialog) and ventana.IsShown():
				w32.forzar_primer_plano(ventana.GetHandle())

	def _preparar_modal(self) -> None:
		wx.CallLater(120, self._traer_dialogo_al_frente)

	# ── Áreas y ventanas rápidas ─────────────────────────────────────────────

	def area_actual(self) -> wx.Window:
		return self.areas[max(self.libro.GetSelection(), 0)]

	def mostrar_area(self, indice: int) -> None:
		self.libro.SetSelection(indice)
		area = self.areas[indice]
		if area is self.panel:
			self._enfocar_lista()
		else:
			if area is not self.area_emoticonos:
				area.refrescar()
			area.enfocar()

	def _al_cambiar_area(self, evento: wx.BookCtrlEvent) -> None:
		area = self.areas[evento.GetSelection()] if 0 <= evento.GetSelection() < len(self.areas) else None
		if area is not None and area not in (self.panel, self.area_emoticonos):
			area.refrescar()
		if area is self.area_notificaciones:
			self.controlador.notificaciones.consultar_ya()
		wx.CallAfter(self.reconstruir_menu_accion)
		evento.Skip()

	# ── Menú Acción ─────────────────────────────────────────────────────────

	def _acciones_escritorios(self) -> list:
		hay = bool(self.escritorio_seleccionado())
		ventana = self.ventana_seleccionada()
		con_ventana = ventana is not None
		llamar = lambda funcion: lambda: funcion(None)  # noqa: E731
		return [
			(_("&Ir al escritorio seleccionado (Intro)"), llamar(self._al_ir), hay),
			(_("&Crear un escritorio\tCtrl+N"), llamar(self._al_crear), True),
			(_("Crear con no&mbre...\tCtrl+Shift+N"), llamar(self._al_crear_con_nombre), True),
			(_("Cambiar el &nombre...\tF2"), llamar(self._al_renombrar), hay),
			(_("&Eliminar... (Suprimir)"), llamar(self._al_eliminar), hay),
			(_("Eliminar los escritorios &vacíos..."), llamar(self._al_eliminar_vacios), True),
			None,
			(_("Subir en el &orden\tAlt+Shift+Up"), llamar(self._al_subir), hay),
			(_("Bajar en el or&den\tAlt+Shift+Down"), llamar(self._al_bajar), hay),
			(_("&Fondo de pantalla..."), llamar(self._al_fondo), hay),
			(_("Fondo para &todos..."), llamar(self._al_fondo_todos), True),
			None,
			(
				"submenu",
				_("Ventana &seleccionada"),
				[
					(_("&Activar la ventana (Intro)"), llamar(self._al_activar_ventana_menu), con_ventana),
					(_("&Mover a otro escritorio...\tCtrl+M"), llamar(self._al_mover_ventana), con_ventana),
					(_("Mover al escritorio s&iguiente"), llamar(self._al_mover_ventana_siguiente), con_ventana),
					(_("Mover al escritorio a&nterior"), llamar(self._al_mover_ventana_anterior), con_ventana),
					(_("Mostrar en &todos los escritorios"), llamar(self._al_anclar_ventana), con_ventana, bool(ventana and ventana.anclada)),
					(_("Mostrar la a&plicación en todos"), llamar(self._al_anclar_aplicacion), con_ventana, bool(ventana and ventana.app_anclada)),
					(_("&Cerrar la ventana (Suprimir)"), llamar(self._al_cerrar_ventana), con_ventana),
				],
			),
			(_("&Buscar una ventana en todos los escritorios...\tCtrl+F"), llamar(self._al_buscar_ventana), True),
		]

	def acciones_area_actual(self) -> list:
		area = self.area_actual()
		return self._acciones_escritorios() if area is self.panel else area.acciones()

	def _llenar_menu(self, menu: wx.Menu, entradas: list, activar_todo: bool) -> None:
		for entrada in entradas:
			if entrada is None:
				menu.AppendSeparator()
				continue
			if entrada[0] == "submenu":
				submenu = wx.Menu()
				self._llenar_menu(submenu, entrada[2], activar_todo)
				menu.AppendSubMenu(submenu, entrada[1], entrada[1].replace("&", ""))
				continue
			etiqueta, funcion, activo, *casilla = entrada
			ayuda = etiqueta.split("\t", 1)[0].replace("&", "")
			item = menu.Append(wx.ID_ANY, etiqueta, ayuda, wx.ITEM_CHECK if casilla else wx.ITEM_NORMAL)
			if casilla:
				item.Check(bool(casilla[0]))
			# Con el menú cerrado todo queda activo para que sus atajos (F2, F4...) funcionen;
			# la propia acción comprueba si hay algo seleccionado.
			item.Enable(bool(activo) or activar_todo)
			self.Bind(wx.EVT_MENU, lambda _e, f=funcion: f(), item)
			self._ids_accion.append(item.GetId())

	def reconstruir_menu_accion(self, activar_todo: bool = True) -> None:
		"""Rehace el menú Acción con las órdenes del área visible."""
		if not self:
			return
		for identificador in self._ids_accion:
			self.Unbind(wx.EVT_MENU, id=identificador)
		self._ids_accion = []
		for item in list(self._menu_accion.GetMenuItems()):
			self._menu_accion.DestroyItem(item)
		try:
			self._llenar_menu(self._menu_accion, self.acciones_area_actual(), activar_todo)
		except Exception:  # noqa: BLE001 - un área rota no debe dejar la barra sin menú
			log.exception("No se pudo construir el menú Acción")

	def mostrar_menu_acciones(self, control: wx.Window) -> None:
		"""El mismo contenido del menú Acción como menú contextual, junto al elemento enfocado."""
		menu = wx.Menu()
		ids_previos = self._ids_accion
		self._ids_accion = []
		try:
			self._llenar_menu(menu, self.acciones_area_actual(), activar_todo=False)
			posicion = wx.Point(20, 20)
			if isinstance(control, wx.ListCtrl) and control.GetItemCount():
				rect = control.GetItemRect(max(control.GetFocusedItem(), 0))
				posicion = wx.Point(rect.x + 20, rect.y + rect.height)
			control.PopupMenu(menu, posicion)
		finally:
			for identificador in self._ids_accion:
				self.Unbind(wx.EVT_MENU, id=identificador)
			self._ids_accion = ids_previos
			menu.Destroy()

	def _al_cerrar_menu(self, evento: wx.MenuEvent) -> None:
		if evento.GetMenu() is self._menu_accion:
			wx.CallAfter(self.reconstruir_menu_accion)
		evento.Skip()

	def _al_area_fragmentos(self, _evento: wx.CommandEvent | None) -> None:
		self.mostrar_area(2)

	def _al_area_audio(self, _evento: wx.CommandEvent | None) -> None:
		self.mostrar_area(5)

	def _al_area_sistema(self, _evento: wx.CommandEvent | None) -> None:
		self.mostrar_area(6)

	def _al_area_procesos(self, _evento: wx.CommandEvent | None) -> None:
		self.mostrar_area(7)

	def _al_area_temporizadores(self, _evento: wx.CommandEvent | None) -> None:
		self.mostrar_area(8)

	def _al_nuevo_temporizador(self, _evento: wx.CommandEvent | None) -> None:
		self.mostrar_area(8)
		self.area_temporizadores.nuevo_temporizador()

	def _al_nueva_alarma(self, _evento: wx.CommandEvent | None) -> None:
		self.mostrar_area(8)
		self.area_temporizadores.nueva_alarma()

	def _al_ir_busqueda(self, _evento: wx.CommandEvent | None) -> None:
		area = self.area_actual()
		buscador = getattr(area, "buscar", None)
		if buscador is not None:
			buscador.SetFocus()
			buscador.SelectAll()
		else:
			self.controlador.hablar(_("Esta área no tiene buscador."), True)

	def _al_lanzador(self, _evento: wx.CommandEvent | None) -> None:
		self.abrir_ventana_rapida("lanzador", 0)

	def _al_abrir_rapida(self, _evento: wx.CommandEvent | None) -> None:
		area = self.area_actual()
		rapidas = {
			id(self.area_portapapeles): "portapapeles_rapido",
			id(self.area_fragmentos): "fragmentos_rapido",
			id(self.area_emoticonos): "emoticonos_rapido",
			id(self.area_notificaciones): "notificaciones_rapido",
		}
		if area is self.panel:
			self.abrir_selector_escritorios()
		elif id(area) in rapidas:
			self.abrir_ventana_rapida(rapidas[id(area)], 0)
		else:
			self.controlador.hablar(_("Esta área no tiene lista rápida."), True)

	def _al_exportar(self, _evento: wx.CommandEvent | None) -> None:
		area = self.area_actual()
		if area is self.area_portapapeles:
			self._al_exportar_historial(None)
		elif area is self.area_notificaciones:
			self._al_exportar_notificaciones(None)
		else:
			self.controlador.hablar(_("Esta área no tiene nada que exportar."), True)

	def _al_decir_estado(self, _evento: wx.CommandEvent | None) -> None:
		area = self.area_actual()
		if area is self.panel:
			self.controlador.anunciar_escritorio()
		elif area is self.area_notificaciones:
			self.controlador.leer_ultima_notificacion()
		elif area is self.area_audio:
			self.controlador.decir_audio()
		elif area is self.area_sistema:
			self.controlador.decir_estado_sistema()
		elif area is self.area_portapapeles:
			self.controlador.hablar(_("{n} elementos en el historial").format(n=self.controlador.portapapeles.historial.contar()), True)
		else:
			self.controlador.hablar(_("{n} en la lista").format(n=area.lista.numero_filas()), True)

	def _al_cambiar_historial(self) -> None:
		if self and self.IsShown() and self.area_actual() is self.area_portapapeles:
			self.area_portapapeles.refrescar()

	def _al_cambiar_notificaciones(self, hay_nuevas: bool = False) -> None:
		if not self:
			return
		if hay_nuevas and self.IsShown() and self.area_actual() is self.area_notificaciones:
			self.area_notificaciones.refrescar()
		if self._bandeja is not None:
			self._bandeja.poner_no_leidas(self.controlador.notificaciones.historial.no_leidas())

	def _al_area_notificaciones(self, _evento: wx.CommandEvent | None) -> None:
		self.mostrar_area(3)

	def _al_abrir_app_notificacion(self, _evento: wx.CommandEvent | None) -> None:
		self.area_notificaciones.abrir_app()

	def _al_copiar_notificacion(self, _evento: wx.CommandEvent | None) -> None:
		self.area_notificaciones.copiar()

	def _al_leida_notificacion(self, _evento: wx.CommandEvent | None) -> None:
		self.area_notificaciones.alternar_leida()

	def _al_favorita_notificacion(self, _evento: wx.CommandEvent | None) -> None:
		self.area_notificaciones.alternar_favorita()

	def _al_descartar_notificacion(self, _evento: wx.CommandEvent | None) -> None:
		self.area_notificaciones.descartar()

	def _al_eliminar_notificacion(self, _evento: wx.CommandEvent | None) -> None:
		self.area_notificaciones.eliminar()

	def _al_ignorar_app_notificacion(self, _evento: wx.CommandEvent | None) -> None:
		self.area_notificaciones.ignorar_app()

	def _al_todas_leidas(self, _evento: wx.CommandEvent | None) -> None:
		self.area_notificaciones.marcar_todas_leidas()

	def _al_vaciar_notificaciones(self, _evento: wx.CommandEvent | None) -> None:
		self.area_notificaciones.vaciar()

	def _al_exportar_notificaciones(self, _evento: wx.CommandEvent | None) -> None:
		with wx.FileDialog(
			self,
			_("Exportar las notificaciones"),
			defaultFile="notificaciones.csv",
			wildcard=_("Hoja de cálculo CSV (*.csv)|*.csv|Texto (*.txt)|*.txt"),
			style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
		) as dialogo:
			if dialogo.ShowModal() != wx.ID_OK:
				return
			ruta = Path(dialogo.GetPath())
		try:
			cuantas = self.controlador.notificaciones.historial.exportar(ruta, list(self.area_notificaciones._notificaciones))
		except OSError:
			log.exception("No se pudo exportar a %s", ruta)
			mostrar_error(self, _("No se pudo escribir {ruta}.").format(ruta=ruta), _("Exportar"))
			return
		self.controlador.hablar(_("Exportadas {n} notificaciones").format(n=cuantas), True)

	def _al_pausar_notificaciones(self, evento: wx.CommandEvent) -> None:
		if bool(evento.IsChecked()) != self.controlador.notificaciones.pausado:
			self.controlador.alternar_notificaciones()

	def _al_permiso_notificaciones(self, _evento: wx.CommandEvent | None) -> None:
		try:
			os.startfile("ms-settings:privacy-notifications")  # noqa: S606 - página de Configuración de Windows
		except OSError:
			log.exception("No se pudo abrir la configuración de privacidad")
		self.controlador.notificaciones.consultar_ya()

	def _al_notificaciones_rapido(self, _evento: wx.CommandEvent | None) -> None:
		self.abrir_ventana_rapida("notificaciones_rapido", 0)

	def abrir_ventana_rapida(self, accion: str, destino: int) -> None:
		"""Abre la ventana rápida de portapapeles o de emoticonos para la ventana ``destino``."""
		from app.ui.ventanas_rapidas import EmoticonosRapido, FragmentosRapido, LanzadorRapido, NotificacionesRapido, PortapapelesRapido

		self._cerrar_selector()
		clase = {
			"portapapeles_rapido": PortapapelesRapido,
			"notificaciones_rapido": NotificacionesRapido,
			"fragmentos_rapido": FragmentosRapido,
			"lanzador": LanzadorRapido,
		}.get(accion, EmoticonosRapido)
		self._selector = clase(self.controlador, destino)
		self._selector.abrir()

	def _al_area_escritorios(self, _evento: wx.CommandEvent | None) -> None:
		self.mostrar_area(0)

	def _al_area_portapapeles(self, _evento: wx.CommandEvent | None) -> None:
		self.mostrar_area(1)

	def _al_area_emoticonos(self, _evento: wx.CommandEvent | None) -> None:
		self.mostrar_area(2)

	def _al_pegar_elemento(self, _evento: wx.CommandEvent | None) -> None:
		self.area_portapapeles.pegar()

	def _al_pegar_sin_formato(self, _evento: wx.CommandEvent | None) -> None:
		self.area_portapapeles.pegar("sin_formato")

	def _al_copiar_elemento(self, _evento: wx.CommandEvent | None) -> None:
		self.area_portapapeles.copiar()

	def _al_favorito_elemento(self, _evento: wx.CommandEvent | None) -> None:
		self.area_portapapeles.alternar_favorito()

	def _al_renombrar_elemento(self, _evento: wx.CommandEvent | None) -> None:
		self.area_portapapeles.renombrar()

	def _al_eliminar_elemento(self, _evento: wx.CommandEvent | None) -> None:
		self.area_portapapeles.eliminar()

	def _al_vaciar_historial(self, _evento: wx.CommandEvent | None) -> None:
		self.area_portapapeles.vaciar()

	def _al_exportar_historial(self, _evento: wx.CommandEvent | None) -> None:
		with wx.FileDialog(
			self,
			_("Exportar los textos del historial"),
			defaultFile="portapapeles.txt",
			wildcard=_("Texto (*.txt)|*.txt"),
			style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
		) as dialogo:
			if dialogo.ShowModal() != wx.ID_OK:
				return
			ruta = Path(dialogo.GetPath())
		try:
			cuantos = self.controlador.portapapeles.historial.exportar_texto(ruta)
		except OSError:
			log.exception("No se pudo exportar el historial a %s", ruta)
			mostrar_error(self, _("No se pudo escribir {ruta}.").format(ruta=ruta), _("Exportar"))
			return
		self.controlador.hablar(_("Exportados {n} textos").format(n=cuantos), True)

	def _al_pausar_captura(self, evento: wx.CommandEvent) -> None:
		if bool(evento.IsChecked()) != self.controlador.portapapeles.pausado:
			self.controlador.alternar_captura()

	def _al_portapapeles_rapido(self, _evento: wx.CommandEvent | None) -> None:
		self.abrir_ventana_rapida("portapapeles_rapido", 0)

	def _al_insertar_emoticono(self, _evento: wx.CommandEvent | None) -> None:
		self.area_emoticonos.insertar()

	def _al_copiar_emoticono(self, _evento: wx.CommandEvent | None) -> None:
		self.area_emoticonos.copiar()

	def _al_acumular_emoticono(self, _evento: wx.CommandEvent | None) -> None:
		self.area_emoticonos.acumular()

	def _al_favorito_emoticono(self, _evento: wx.CommandEvent | None) -> None:
		self.area_emoticonos.alternar_favorito()

	def _al_vaciar_recientes(self, _evento: wx.CommandEvent | None) -> None:
		self.area_emoticonos.vaciar_recientes()
		self.controlador.hablar(_("Recientes vaciados"), True)

	def _al_emoticonos_rapido(self, _evento: wx.CommandEvent | None) -> None:
		self.abrir_ventana_rapida("emoticonos_rapido", 0)

	def _cerrar_selector(self) -> None:
		if self._selector:
			self._selector.cerrar()
		self._selector = None

	def abrir_selector_escritorios(self) -> None:
		from app.ui.selector import DialogoSelector

		self._cerrar_selector()
		estado = self._estado
		if not estado.escritorios:
			self.controlador.avisar(self.controlador.servicio.error_conexion or _("No hay escritorios que mostrar."))
			return
		elementos = [(f"{e.numero}. {e.nombre_visible}" + (_(" (actual)") if e.actual else ""), e.numero) for e in estado.escritorios]
		self._selector = DialogoSelector(
			_("Ir a un escritorio"),
			_("&Escritorios:"),
			elementos,
			lambda numero: self.controlador.servicio.ir_a(numero),
			seleccion_inicial=max(estado.actual - 1, 0),
		)
		self._selector.abrir()

	def abrir_buscador_ventanas(self) -> None:
		def abrir(ventanas: list[InfoVentana]) -> None:
			from app.ui.selector import DialogoSelector

			self._cerrar_selector()
			if not ventanas:
				self.controlador.avisar(_("No hay ventanas abiertas."))
				return
			nombres = {e.id: e.describir() for e in self._estado.escritorios}
			elementos = []
			for v in ventanas:
				donde = _("todos los escritorios") if v.en_todos else nombres.get(v.id_escritorio, _("escritorio desconocido"))
				elementos.append((f"{v.titulo or _('(sin título)')} - {v.proceso}, {donde}", v.hwnd))
			self._selector = DialogoSelector(
				_("Buscar una ventana"),
				_("&Ventanas de todos los escritorios:"),
				elementos,
				lambda hwnd: self.controlador.servicio.ir_a_ventana(hwnd),
			)
			self._selector.abrir()

		self.controlador.servicio.obtener_ventanas(lambda ventanas: wx.CallAfter(abrir, ventanas))

	def renombrar(self, numero: int) -> None:
		escritorio = self._estado.escritorio(numero)
		if escritorio is None:
			return
		self._preparar_modal()
		nombre = pedir_texto(
			self._padre_dialogos(),
			_("&Nombre del escritorio {n}:").format(n=numero),
			_("Cambiar el nombre"),
			escritorio.nombre,
			max_caracteres=100,
			ayuda=_("Deje el campo vacío para volver al nombre «Escritorio {n}».").format(n=numero),
		)
		if nombre is None:
			return
		self.controlador.servicio.renombrar(
			numero, nombre.strip(), lambda _estado: wx.CallAfter(self.controlador.hablar, _("Nombre cambiado"), True)
		)

	def eliminar(self, numero: int) -> None:
		escritorio = self._estado.escritorio(numero)
		if escritorio is None:
			return
		if self._estado.total <= 1:
			self.controlador.avisar(_("No se puede eliminar el único escritorio que queda."))
			return
		if self._config.obtener("general.confirmar_eliminar", True):
			self._preparar_modal()
			respuesta = confirmar(
				self._padre_dialogos(),
				_("¿Eliminar el escritorio «{e}»? Sus ventanas no se cierran: pasan al escritorio vecino.").format(
					e=escritorio.describir()
				),
				_("Eliminar escritorio"),
				peligroso=True,
			)
			if respuesta != wx.ID_YES:
				return
		self.controlador.servicio.eliminar(
			numero,
			lambda eliminado: wx.CallAfter(
				self.controlador.hablar, _("Eliminado {e}").format(e=eliminado.describir() if eliminado else numero), True
			),
		)

	# ── Geometría ────────────────────────────────────────────────────────────

	def _restaurar_geometria(self) -> None:
		ancho = int(self._config.obtener("ventana.ancho", 800))
		alto = int(self._config.obtener("ventana.alto", 600))
		if ancho < TAMANO_MINIMO[0] or alto < TAMANO_MINIMO[1]:
			ancho, alto = 800, 600
		self.SetSize(wx.Size(ancho, alto))
		x = int(self._config.obtener("ventana.x", -1))
		y = int(self._config.obtener("ventana.y", -1))
		if x >= -50 and y >= -50 and wx.Display.GetFromPoint(wx.Point(x + 60, y + 15)) != wx.NOT_FOUND:
			self.SetPosition(wx.Point(x, y))
		else:
			self.Centre()
		if self._config.obtener("ventana.maximizada", False):
			self.Maximize(True)

	def _al_cambiar_geometria(self, evento: wx.Event) -> None:
		if self.IsShown() and not self.IsMaximized() and not self.IsIconized():
			self._rect_normal = self.GetRect()
		evento.Skip()

	def _guardar_geometria(self) -> None:
		rect = self._rect_normal or self.GetRect()
		self._config.establecer("ventana.x", rect.x)
		self._config.establecer("ventana.y", rect.y)
		self._config.establecer("ventana.ancho", rect.width)
		self._config.establecer("ventana.alto", rect.height)
		self._config.establecer("ventana.maximizada", bool(self.IsMaximized()))

	# ── Cierre ───────────────────────────────────────────────────────────────

	def _al_minimizar(self, evento: wx.IconizeEvent) -> None:
		if evento.IsIconized() and self._config.obtener("general.minimizar_a_bandeja", True):
			wx.CallAfter(self.ocultar_en_bandeja)
		evento.Skip()

	def _al_cerrar(self, evento: wx.CloseEvent) -> None:
		if (
			not self._forzar_salida
			and evento.CanVeto()
			and self._config.obtener("general.cerrar_a_bandeja", True)
			and self.ocultar_en_bandeja()
		):
			evento.Veto()
			return
		self._saliendo = True
		self._temporizador_buzon.Stop()
		self._cerrar_selector()
		self.controlador.detener()
		self._guardar_geometria()
		self._config.guardar()
		self._quitar_bandeja()
		log.info("Ventana principal cerrada.")
		self.Destroy()

	def _al_activar_ventana(self, evento: wx.ActivateEvent) -> None:
		"""Al volver a la ventana, las ventanas abiertas pueden haber cambiado: se releen."""
		if evento.GetActive() and not self._saliendo:
			self.refrescar_ventanas()
		evento.Skip()

	def _al_tecla_ventana(self, evento: wx.KeyEvent) -> None:
		"""Teclas de las listas de portapapeles y emoticonos; Escape oculta el gestor en la bandeja.

		``EVT_CHAR_HOOK`` llega ANTES que los atajos de menú: así F2 en la lista
		del portapapeles cambia el nombre del elemento y no el del escritorio.
		"""
		area = self.area_actual()
		if hasattr(area, "manejar_tecla") and area.manejar_tecla(evento):
			return
		if evento.GetKeyCode() == wx.WXK_ESCAPE and not evento.HasAnyModifiers():
			self.ocultar_en_bandeja()
			return
		evento.Skip()

	# ── Segunda instancia ────────────────────────────────────────────────────

	def _al_revisar_buzon(self, _evento: wx.TimerEvent) -> None:
		try:
			ordenes = self._instancia.recoger_ordenes() if self._instancia else []
			for orden in ordenes:
				if orden.orden in (ORDEN_MOSTRAR, ORDEN_ABRIR):
					self.restaurar()
		except Exception:  # noqa: BLE001 - el temporizador late toda la sesión; no debe romperla
			log.exception("Error al atender las órdenes de otra instancia")

	# ── Teclado de las listas y menús contextuales ──────────────────────────

	def _al_tecla_lista(self, evento: wx.KeyEvent) -> None:
		# Suprimir y F2 se atienden aquí: como atajo de menú robarían la tecla a los campos de texto.
		codigo = evento.GetKeyCode()
		if codigo in (wx.WXK_DELETE, wx.WXK_NUMPAD_DELETE) and not evento.HasAnyModifiers():
			self._al_eliminar(None)
			return
		evento.Skip()

	def _al_tecla_lista_ventanas(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() in (wx.WXK_DELETE, wx.WXK_NUMPAD_DELETE) and not evento.HasAnyModifiers():
			self._al_cerrar_ventana(None)
			return
		evento.Skip()

	def _menu_emergente(self, control: wx.ListCtrl, evento: wx.ContextMenuEvent, opciones: list[tuple[str | None, str | None]]) -> None:
		"""Menú contextual junto al elemento enfocado cuando se abre desde el teclado."""
		menu = wx.Menu()
		for nombre, etiqueta in opciones:
			if nombre is None:
				menu.AppendSeparator()
				continue
			item = menu.Append(wx.ID_ANY, etiqueta)
			menu.Bind(wx.EVT_MENU, getattr(self, f"_al_{nombre}"), item)
		posicion = evento.GetPosition()
		if posicion == wx.DefaultPosition:
			enfocado = max(control.GetFocusedItem(), 0)
			rect = control.GetItemRect(enfocado) if control.GetItemCount() else wx.Rect(0, 0, 0, 0)
			posicion = wx.Point(rect.x + 20, rect.y + rect.height)
		else:
			posicion = control.ScreenToClient(posicion)
		try:
			control.PopupMenu(menu, posicion)
		finally:
			menu.Destroy()

	def _al_menu_contextual_escritorios(self, evento: wx.ContextMenuEvent) -> None:
		self._menu_emergente(
			self.lista,
			evento,
			[
				("ir", _("&Ir a este escritorio")),
				("renombrar", _("Cambiar el &nombre...")),
				("eliminar", _("&Eliminar...")),
				(None, None),
				("subir", _("Subir en el &orden")),
				("bajar", _("Bajar en el or&den")),
				("fondo", _("&Fondo de pantalla...")),
				(None, None),
				("crear", _("&Crear un escritorio")),
			],
		)

	def _al_menu_contextual_ventanas(self, evento: wx.ContextMenuEvent) -> None:
		ventana = self.ventana_seleccionada()
		if ventana is None:
			return
		self._menu_emergente(
			self.lista_ventanas,
			evento,
			[
				("activar_ventana_menu", _("&Activar la ventana")),
				("mover_ventana", _("&Mover a otro escritorio...")),
				("mover_ventana_siguiente", _("Mover al escritorio s&iguiente")),
				("mover_ventana_anterior", _("Mover al escritorio a&nterior")),
				(None, None),
				(
					"anclar_ventana",
					_("Mostrar solo en su &escritorio") if ventana.anclada else _("Mostrar en &todos los escritorios"),
				),
				(
					"anclar_aplicacion",
					_("Mostrar la a&plicación solo en su escritorio")
					if ventana.app_anclada
					else _("Mostrar la a&plicación en todos los escritorios"),
				),
				(None, None),
				("cerrar_ventana", _("&Cerrar la ventana")),
			],
		)

	def _al_abrir_menu(self, evento: wx.MenuEvent) -> None:
		if evento.GetMenu() is self._menu_accion:
			self.reconstruir_menu_accion(activar_todo=False)
		evento.Skip()

	def _al_ir(self, _evento: wx.CommandEvent | None) -> None:
		numero = self.escritorio_seleccionado()
		if numero:
			self.controlador.servicio.ir_a(numero)

	def _al_crear(self, _evento: wx.CommandEvent | None) -> None:
		self.controlador.ejecutar("crear")

	def _al_crear_con_nombre(self, _evento: wx.CommandEvent | None) -> None:
		nombre = pedir_texto(self, _("&Nombre del escritorio nuevo:"), _("Crear un escritorio"), max_caracteres=100)
		if nombre is None:
			return
		self.controlador.servicio.crear(
			nombre.strip(),
			al_terminar=lambda numero: wx.CallAfter(self.controlador.hablar, _("Creado el escritorio {n}").format(n=numero), True),
		)

	def _al_renombrar(self, _evento: wx.CommandEvent | None) -> None:
		self.renombrar(self.escritorio_seleccionado())

	def _al_eliminar(self, _evento: wx.CommandEvent | None) -> None:
		self.eliminar(self.escritorio_seleccionado())

	def _al_eliminar_vacios(self, _evento: wx.CommandEvent | None) -> None:
		if (
			confirmar(
				self,
				_("¿Eliminar todos los escritorios que no tienen ventanas (salvo el actual)?"),
				_("Eliminar escritorios vacíos"),
				peligroso=True,
			)
			!= wx.ID_YES
		):
			return

		def al_terminar(cuantos: int) -> None:
			texto = _("No había escritorios vacíos") if not cuantos else _("Eliminados {n} escritorios vacíos").format(n=cuantos)
			wx.CallAfter(self.controlador.hablar, texto, True)

		self.controlador.servicio.eliminar_vacios(al_terminar)

	def _mover_escritorio(self, paso: int) -> None:
		numero = self.escritorio_seleccionado()
		if not numero:
			return
		destino = numero + paso
		if not 1 <= destino <= self._estado.total:
			wx.Bell()
			return
		self.controlador.servicio.mover_escritorio(
			numero, destino, lambda posicion: wx.CallAfter(self.controlador.hablar, _("Posición {n}").format(n=posicion), True)
		)

	def _al_subir(self, _evento: wx.CommandEvent | None) -> None:
		self._mover_escritorio(-1)

	def _al_bajar(self, _evento: wx.CommandEvent | None) -> None:
		self._mover_escritorio(1)

	def _elegir_imagen(self, titulo: str) -> str | None:
		with wx.FileDialog(
			self,
			titulo,
			wildcard=_("Imágenes (*.jpg;*.jpeg;*.png;*.bmp;*.gif)|*.jpg;*.jpeg;*.png;*.bmp;*.gif|Todos los archivos (*.*)|*.*"),
			style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
		) as dialogo:
			if dialogo.ShowModal() != wx.ID_OK:
				return None
			return dialogo.GetPath()

	def _al_fondo(self, _evento: wx.CommandEvent | None) -> None:
		numero = self.escritorio_seleccionado()
		if not numero:
			return
		ruta = self._elegir_imagen(_("Fondo del escritorio {n}").format(n=numero))
		if ruta:
			self.controlador.servicio.poner_fondo(numero, ruta, lambda _r: wx.CallAfter(self.controlador.hablar, _("Fondo cambiado"), True))

	def _al_fondo_todos(self, _evento: wx.CommandEvent | None) -> None:
		ruta = self._elegir_imagen(_("Fondo para todos los escritorios"))
		if ruta:
			self.controlador.servicio.poner_fondo(
				None, ruta, lambda _r: wx.CallAfter(self.controlador.hablar, _("Fondo cambiado en todos los escritorios"), True)
			)

	def _al_ocultar(self, _evento: wx.CommandEvent | None) -> None:
		self.ocultar_en_bandeja()

	def _al_salir(self, _evento: wx.CommandEvent | None) -> None:
		self.salir()

	# ── Manejadores: Ventanas ────────────────────────────────────────────────

	def _con_ventana(self, funcion: Callable[[InfoVentana], None]) -> None:
		ventana = self.ventana_seleccionada()
		if ventana is None:
			self.controlador.hablar(_("No hay ninguna ventana seleccionada."), True)
			return
		funcion(ventana)

	def _tras_operacion_ventana(self, texto: str) -> Callable[[Any], None]:
		def al_terminar(_resultado: Any) -> None:
			wx.CallAfter(self.controlador.hablar, texto, True)
			wx.CallAfter(self.refrescar_ventanas)

		return al_terminar

	def _al_activar_ventana_lista(self, _evento: wx.CommandEvent | None) -> None:
		self._con_ventana(lambda v: self.controlador.servicio.ir_a_ventana(v.hwnd))

	def _al_activar_ventana_menu(self, _evento: wx.CommandEvent | None) -> None:
		self._al_activar_ventana_lista(None)

	def _al_mover_ventana(self, _evento: wx.CommandEvent | None) -> None:
		ventana = self.ventana_seleccionada()
		if ventana is None:
			return
		opciones = [e.describir() for e in self._estado.escritorios]
		with wx.SingleChoiceDialog(
			self, _("Escritorio de destino para «{v}»:").format(v=ventana.titulo), _("Mover la ventana"), opciones
		) as dialogo:
			if ventana.escritorio:
				dialogo.SetSelection(ventana.escritorio - 1)
			if dialogo.ShowModal() != wx.ID_OK:
				return
			destino = dialogo.GetSelection() + 1
		self.controlador.servicio.mover_ventana(
			ventana.hwnd,
			destino=destino,
			seguir=False,
			al_terminar=self._tras_operacion_ventana(_("Ventana movida al escritorio {n}").format(n=destino)),
		)

	def _al_mover_ventana_siguiente(self, _evento: wx.CommandEvent | None) -> None:
		self._con_ventana(
			lambda v: self.controlador.servicio.mover_ventana(
				v.hwnd, paso=1, seguir=False, al_terminar=self._tras_operacion_ventana(_("Ventana movida"))
			)
		)

	def _al_mover_ventana_anterior(self, _evento: wx.CommandEvent | None) -> None:
		self._con_ventana(
			lambda v: self.controlador.servicio.mover_ventana(
				v.hwnd, paso=-1, seguir=False, al_terminar=self._tras_operacion_ventana(_("Ventana movida"))
			)
		)

	def _al_anclar_ventana(self, _evento: wx.CommandEvent | None) -> None:
		def anclar(v: InfoVentana) -> None:
			texto = _("La ventana se muestra solo en su escritorio") if v.anclada else _("La ventana se muestra en todos los escritorios")
			self.controlador.servicio.anclar_ventana(v.hwnd, not v.anclada, al_terminar=self._tras_operacion_ventana(texto))

		self._con_ventana(anclar)

	def _al_anclar_aplicacion(self, _evento: wx.CommandEvent | None) -> None:
		def anclar(v: InfoVentana) -> None:
			texto = (
				_("La aplicación se muestra solo en su escritorio")
				if v.app_anclada
				else _("La aplicación se muestra en todos los escritorios")
			)
			self.controlador.servicio.anclar_ventana(
				v.hwnd, not v.app_anclada, aplicacion=True, al_terminar=self._tras_operacion_ventana(texto)
			)

		self._con_ventana(anclar)

	def _al_cerrar_ventana(self, _evento: wx.CommandEvent | None) -> None:
		def cerrar(v: InfoVentana) -> None:
			if w32.cerrar(v.hwnd):
				self.controlador.hablar(_("Cierre pedido a {v}").format(v=v.titulo or v.proceso), True)
				wx.CallLater(700, self.refrescar_ventanas)

		self._con_ventana(cerrar)

	def _al_buscar_ventana(self, _evento: wx.CommandEvent | None) -> None:
		self.abrir_buscador_ventanas()

	# ── Manejadores: Ver ─────────────────────────────────────────────────────

	def _al_ver_todas(self, evento: wx.CommandEvent) -> None:
		self._config.establecer("ventana.ver_todas", evento.IsChecked())
		self._pintar_ventanas()

	def _al_barra_estado(self, evento: wx.CommandEvent) -> None:
		visible = evento.IsChecked()
		self._aplicar_barra_estado(visible)
		self._config.establecer("ventana.barra_estado", visible)

	def _aplicar_barra_estado(self, visible: bool) -> None:
		self.GetStatusBar().Show(visible)
		self.elementos_menu["barra_estado"].Check(visible)
		self.SendSizeEvent()

	def _al_decir_actual(self, _evento: wx.CommandEvent | None) -> None:
		self.controlador.anunciar_escritorio()

	def _al_actualizar(self, _evento: wx.CommandEvent | None) -> None:
		area = self.area_actual()
		if area is not self.panel:
			area.refrescar()
			self.SetStatusText(_("Actualizado"))
			return
		self.controlador.servicio.actualizar()
		self.refrescar_ventanas()
		self.SetStatusText(_("Actualizado"))

	# ── Manejadores: Herramientas ────────────────────────────────────────────

	def _al_teclas_globales(self, _evento: wx.CommandEvent | None) -> None:
		from app.ui.dialogo_teclas import DialogoTeclas

		with DialogoTeclas(self, self._config, self.controlador) as dialogo:
			dialogo.ShowModal()
		self._enfocar_lista()

	def _al_reglas(self, _evento: wx.CommandEvent | None) -> None:
		def abrir(ventanas: list[InfoVentana]) -> None:
			from app.ui.dialogo_reglas import DialogoReglas

			procesos = [v.proceso for v in ventanas if v.proceso]
			escritorios = [e.nombre or str(e.numero) for e in self._estado.escritorios]

			def aplicar_ahora(reglas: list) -> None:
				self.controlador.guardar_reglas(reglas)
				self.controlador.servicio.aplicar_reglas_ahora(
					lambda n: wx.CallAfter(self.controlador.hablar, _("Reglas aplicadas: {n} ventanas movidas").format(n=n), True)
				)

			with DialogoReglas(self, self.controlador.reglas(), procesos, escritorios, aplicar_ahora) as dialogo:
				if dialogo.ShowModal() == wx.ID_OK:
					self.controlador.guardar_reglas(dialogo.reglas)
			self._enfocar_lista()

		self.controlador.servicio.obtener_ventanas(lambda ventanas: wx.CallAfter(abrir, ventanas), lambda _m: wx.CallAfter(abrir, []))

	def _al_opciones(self, _evento: wx.CommandEvent | None) -> None:
		from app.ui.dialogo_opciones import DialogoOpciones

		with DialogoOpciones(self, self._config, self._tras_cambiar_opciones) as dialogo:
			if dialogo.ShowModal() == wx.ID_OK:
				dialogo.aplicar()
		self._enfocar_lista()

	def _tras_cambiar_opciones(self) -> None:
		"""Aplica al momento lo que no se lee en cada uso."""
		self.controlador.aplicar_gancho()
		self._aplicar_bandeja()
		self.controlador.avisar_no_molestar()
		nivel = str(self._config.obtener("registro.nivel", "INFO")).upper()
		if nivel in ("DEBUG", "INFO", "WARNING", "ERROR"):
			logging.getLogger().setLevel(nivel)

	def _abrir_carpeta(self, carpeta: Path) -> None:
		if hasattr(os, "startfile"):
			try:
				os.startfile(carpeta)  # noqa: S606 - carpeta propia de la aplicación
			except OSError:
				log.exception("No se pudo abrir la carpeta %s", carpeta)

	def _al_carpeta_datos(self, _evento: wx.CommandEvent | None) -> None:
		self._abrir_carpeta(paths.ruta_datos())

	def _al_carpeta_registros(self, _evento: wx.CommandEvent | None) -> None:
		self._abrir_carpeta(paths.ruta_registros())

	# ── Manejadores: Ayuda ───────────────────────────────────────────────────

	def _al_manual(self, _evento: wx.CommandEvent | None) -> None:
		mostrar_documento(self, "manual", _("Manual de usuario"))

	def _al_teclas(self, _evento: wx.CommandEvent | None) -> None:
		mostrar_documento(self, "teclas", _("Lista de teclas"))

	def _al_novedades(self, _evento: wx.CommandEvent | None) -> None:
		mostrar_documento(self, "novedades", _("Novedades de la versión"))

	def _al_ayuda_contextual(self, _evento: wx.CommandEvent | None) -> None:
		foco = wx.Window.FindFocus()
		texto = foco.GetHelpText() if foco else ""
		if not texto:
			texto = _("No hay ayuda para este control. Pulse F1 para abrir el manual.")
		mostrar_mensaje(self, texto, _("Ayuda"))

	def _al_buscar_actualizaciones(self, _evento: wx.CommandEvent | None) -> None:
		from app.ui import dialogo_actualizacion

		dialogo_actualizacion.comprobar_manualmente(self, self.controlador.config_actualizador(), anunciar=self.controlador.hablar)

	def iniciar_actualizaciones(self) -> None:
		"""Tras arrancar: confirma la versión (vuelta atrás si una actualización falló) y comprueba de vez en cuando."""
		from app.ui import dialogo_actualizacion

		config = self.controlador.config_actualizador()
		dialogo_actualizacion.al_arrancar(self, config, anunciar=self.controlador.hablar)
		if self._config.obtener("actualizaciones.comprobar_automaticamente", True):
			self._comprobador = dialogo_actualizacion.ComprobadorPeriodico(
				self, config, intervalo_horas=float(self._config.obtener("actualizaciones.intervalo_horas", 24)), anunciar=self.controlador.hablar
			)
			self._comprobador.iniciar()

	def _al_invitar_cafe(self, _evento: wx.CommandEvent | None) -> None:
		import webbrowser

		from app.core.version import URL_DONACIONES

		try:
			webbrowser.open(URL_DONACIONES)
		except Exception:  # noqa: BLE001 - sin navegador configurado
			log.exception("No se pudo abrir la página de donaciones")
			mostrar_error(
				self, _("No se pudo abrir el navegador. La dirección es:\n{url}").format(url=URL_DONACIONES), _("Invítame a un café")
			)
			return
		self.controlador.hablar(_("Gracias. Se ha abierto la página de donaciones en el navegador."), True)

	def _al_acerca_de(self, _evento: wx.CommandEvent | None) -> None:
		from app.ui.acerca_de import mostrar_acerca_de

		mostrar_acerca_de(self)


__all__ = ["VentanaPrincipal", "actualizar_lista", "mostrar_error"]
