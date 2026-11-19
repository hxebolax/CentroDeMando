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
from collections.abc import Callable, Sequence
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
from app.ui.accesibilidad.dialogos import confirmar, pedir_texto
from app.ui.accesibilidad.lista import ListaAccesible
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
MENUS: list[tuple[str, list[tuple[str, str, str, int] | None]]] = [
	(
		"&Escritorios",
		[
			("ir", "&Ir al escritorio seleccionado", "Cambia al escritorio seleccionado en la lista (también con Intro).", wx.ITEM_NORMAL),
			None,
			("crear", "&Crear un escritorio\tCtrl+N", "Crea un escritorio nuevo al final.", wx.ITEM_NORMAL),
			(
				"crear_con_nombre",
				"Crear con no&mbre...\tCtrl+Shift+N",
				"Crea un escritorio nuevo y le pone el nombre que escriba.",
				wx.ITEM_NORMAL,
			),
			("renombrar", "Cambiar el &nombre...\tF2", "Cambia el nombre del escritorio seleccionado.", wx.ITEM_NORMAL),
			(
				"eliminar",
				"&Eliminar...",
				"Elimina el escritorio seleccionado (también con Suprimir). Sus ventanas pasan al escritorio vecino.",
				wx.ITEM_NORMAL,
			),
			(
				"eliminar_vacios",
				"Eliminar los escritorios &vacíos...",
				"Elimina los escritorios que no tienen ninguna ventana, salvo el actual.",
				wx.ITEM_NORMAL,
			),
			None,
			(
				"subir",
				"Subir en el &orden\tAlt+Shift+Up",
				"Pasa el escritorio seleccionado una posición hacia el principio.",
				wx.ITEM_NORMAL,
			),
			("bajar", "Bajar en el or&den\tAlt+Shift+Down", "Pasa el escritorio seleccionado una posición hacia el final.", wx.ITEM_NORMAL),
			None,
			("fondo", "&Fondo de pantalla...", "Elige una imagen de fondo para el escritorio seleccionado.", wx.ITEM_NORMAL),
			("fondo_todos", "Fondo para &todos...", "Elige una imagen de fondo para todos los escritorios.", wx.ITEM_NORMAL),
			None,
			("ocultar", "Ocultar en la b&andeja", "Oculta la ventana; el gestor sigue en la bandeja (también con Escape).", wx.ITEM_NORMAL),
			("salir", "&Salir\tCtrl+Q", "Cierra el gestor por completo; las teclas globales dejan de funcionar.", wx.ITEM_NORMAL),
		],
	),
	(
		"Ve&ntanas",
		[
			(
				"activar_ventana_menu",
				"&Activar la ventana",
				"Cambia al escritorio de la ventana seleccionada y la activa (también con Intro).",
				wx.ITEM_NORMAL,
			),
			(
				"mover_ventana",
				"&Mover a otro escritorio...\tCtrl+M",
				"Elige el escritorio al que llevar la ventana seleccionada.",
				wx.ITEM_NORMAL,
			),
			(
				"mover_ventana_siguiente",
				"Mover al escritorio s&iguiente",
				"Lleva la ventana seleccionada al escritorio siguiente.",
				wx.ITEM_NORMAL,
			),
			(
				"mover_ventana_anterior",
				"Mover al escritorio a&nterior",
				"Lleva la ventana seleccionada al escritorio anterior.",
				wx.ITEM_NORMAL,
			),
			None,
			(
				"anclar_ventana",
				"Mostrar en &todos los escritorios",
				"Alterna si la ventana seleccionada aparece en todos los escritorios.",
				wx.ITEM_CHECK,
			),
			(
				"anclar_aplicacion",
				"Mostrar la a&plicación en todos los escritorios",
				"Alterna si todas las ventanas de su aplicación aparecen en todos los escritorios.",
				wx.ITEM_CHECK,
			),
			None,
			("cerrar_ventana", "&Cerrar la ventana", "Pide a la ventana seleccionada que se cierre, como Alt+F4.", wx.ITEM_NORMAL),
			(
				"buscar_ventana",
				"&Buscar una ventana en todos los escritorios...\tCtrl+F",
				"Lista las ventanas de todos los escritorios para ir a una.",
				wx.ITEM_NORMAL,
			),
		],
	),
	(
		"&Ver",
		[
			(
				"ver_todas",
				"Ventanas de &todos los escritorios",
				"La lista de ventanas muestra las de todos los escritorios en lugar de solo las del seleccionado.",
				wx.ITEM_CHECK,
			),
			("barra_estado", "&Barra de estado", "Muestra u oculta la barra de estado.", wx.ITEM_CHECK),
			None,
			("decir_actual", "&Decir el escritorio actual\tCtrl+D", "Anuncia el escritorio en el que está.", wx.ITEM_NORMAL),
			("actualizar", "&Actualizar\tF5", "Vuelve a leer los escritorios y las ventanas.", wx.ITEM_NORMAL),
		],
	),
	(
		"&Herramientas",
		[
			(
				"teclas_globales",
				"&Teclas globales...\tCtrl+T",
				"Ver y cambiar los atajos que funcionan desde cualquier programa.",
				wx.ITEM_NORMAL,
			),
			(
				"reglas",
				"&Reglas de ventanas...\tCtrl+R",
				"Llevar automáticamente las ventanas de ciertos programas a un escritorio.",
				wx.ITEM_NORMAL,
			),
			("opciones", "&Opciones...\tCtrl+,", "Opciones del gestor.", wx.ITEM_NORMAL),
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
			(
				"ayuda_contextual",
				"Ayuda del control &enfocado\tCtrl+H",
				"Explica para qué sirve el control que tiene el foco.",
				wx.ITEM_NORMAL,
			),
			None,
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


def actualizar_lista(lista: wx.ListCtrl, filas: Sequence[tuple[Any, Sequence[str]]], claves: list[Any]) -> None:
	"""Pone ``filas`` (clave, celdas) en la lista tocando solo lo que cambia.

	``claves`` (la lista paralela de claves de la lista) se actualiza en su
	sitio. La selección y el foco se conservan por clave: si el elemento
	seleccionado sigue existiendo, sigue seleccionado aunque cambie de posición.
	"""
	enfocado = lista.GetFocusedItem()
	clave_enfocada = claves[enfocado] if 0 <= enfocado < len(claves) else None
	nuevas = [clave for clave, _celdas in filas]
	if isinstance(lista, ListaAccesible):
		# La lista accesible guarda el texto íntegro de cada celda para leerlo por columnas.
		if nuevas != claves:
			lista.reemplazar_filas([list(celdas) for _clave, celdas in filas], conservar_foco=False)
			claves[:] = nuevas
			if filas:
				destino = nuevas.index(clave_enfocada) if clave_enfocada in nuevas else min(max(enfocado, 0), len(filas) - 1)
				lista.enfocar_fila(destino, anunciar=False)
		else:
			for indice, (_clave, celdas) in enumerate(filas):
				lista.actualizar_fila(indice, list(celdas))
		return
	if nuevas != claves:
		lista.DeleteAllItems()
		for indice, (_clave, celdas) in enumerate(filas):
			lista.InsertItem(indice, celdas[0])
			for columna, texto in enumerate(celdas[1:], 1):
				lista.SetItem(indice, columna, texto)
		claves[:] = nuevas
		if filas:
			destino = nuevas.index(clave_enfocada) if clave_enfocada in nuevas else min(max(enfocado, 0), len(filas) - 1)
			lista.Focus(destino)
			lista.Select(destino)
		return
	for indice, (_clave, celdas) in enumerate(filas):
		for columna, texto in enumerate(celdas):
			if lista.GetItemText(indice, columna) != texto:
				lista.SetItem(indice, columna, texto)
	if filas and lista.GetFocusedItem() < 0:
		lista.Focus(0)
		lista.Select(0)


class VentanaPrincipal(wx.Frame):
	"""Gestor de escritorios: lista de escritorios, sus ventanas, menús y bandeja."""

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
		self.SetStatusText(_("Conectando con los escritorios virtuales..."))
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
		self.SetMenuBar(barra)
		# Al abrir el menú Ventanas, sus casillas reflejan la ventana seleccionada.
		self.Bind(wx.EVT_MENU_OPEN, self._al_abrir_menu)

	def _crear_contenido(self) -> None:
		"""Etiqueta SIEMPRE creada justo antes de su lista: de ella toma el nombre el lector."""
		self.panel = wx.Panel(self)
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
		"""Escape oculta el gestor en la bandeja (no lo cierra)."""
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
		ventana = self.ventana_seleccionada()
		for nombre in (
			"activar_ventana_menu",
			"mover_ventana",
			"mover_ventana_siguiente",
			"mover_ventana_anterior",
			"anclar_ventana",
			"anclar_aplicacion",
			"cerrar_ventana",
		):
			self.elementos_menu[nombre].Enable(ventana is not None)
		self.elementos_menu["anclar_ventana"].Check(bool(ventana and ventana.anclada))
		self.elementos_menu["anclar_aplicacion"].Check(bool(ventana and ventana.app_anclada))
		evento.Skip()

	# ── Manejadores: Escritorios ─────────────────────────────────────────────

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
