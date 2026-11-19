"""Icono de la bandeja del sistema con menú accesible de escritorios.

- El icono está siempre (opción «Icono siempre en la bandeja»): el gestor vive
  ahí y las teclas globales funcionan aunque la ventana esté oculta.
- El texto emergente dice solo el escritorio actual («Escritorio 3: Trabajo»):
  Windows ya le antepone el nombre del programa, y es lo que el lector lee al
  llegar al icono.
- El menú se construye en ``CreatePopupMenu`` (wx lo pide en cada apertura),
  así siempre refleja los escritorios de ese momento. Los escritorios van como
  elementos de opción (``ITEM_RADIO``): el lector dice cuál está marcado.
- Desde el teclado: Windows+B lleva a la bandeja, las flechas al icono, Intro
  muestra la ventana y la tecla Aplicaciones abre el menú.
"""

from __future__ import annotations

import builtins
import logging
from collections.abc import Callable

import wx
import wx.adv

from app.core import paths
from app.services.escritorios import EstadoEscritorios

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


# Escritorios que caben como elementos directos en el menú; el resto, en «Más».
MAXIMO_EN_MENU = 20


def texto_emergente(estado: EstadoEscritorios) -> str:
	"""Texto del icono: SOLO el escritorio actual, sin el nombre del programa.

	Windows 11 nombra el botón de la bandeja con la descripción del ejecutable
	seguida de este texto. Si el texto repitiera el nombre del programa, el
	lector diría «Centro de Mando Centro de Mando: Escritorio 4».
	"""
	escritorio = estado.escritorio_actual()
	if escritorio is None:
		return _("Sin conexión con los escritorios virtuales")
	if escritorio.nombre:
		return _("Escritorio {n}: {nombre}").format(n=escritorio.numero, nombre=escritorio.nombre)
	return escritorio.nombre_visible


class IconoBandeja(wx.adv.TaskBarIcon):
	"""Icono de bandeja; las acciones se inyectan desde la ventana principal."""

	def __init__(
		self,
		texto: str,
		al_restaurar: Callable[[], None],
		al_salir: Callable[[], None],
		al_accion: Callable[[str], None] | None = None,
		obtener_estado: Callable[[], EstadoEscritorios] | None = None,
		al_menu: Callable[[str], None] | None = None,
	) -> None:
		super().__init__()
		self._texto = texto
		self._al_restaurar = al_restaurar
		self._al_salir = al_salir
		self._al_accion = al_accion or (lambda _accion: None)
		self._obtener_estado = obtener_estado or EstadoEscritorios
		self._al_menu = al_menu or (lambda _nombre: None)
		self._texto_actual = _("Conectando con los escritorios virtuales")
		# Un clic o un doble clic restauran: la acción más frecuente, a un gesto.
		self.Bind(wx.adv.EVT_TASKBAR_LEFT_UP, self._restaurar)
		self.Bind(wx.adv.EVT_TASKBAR_LEFT_DCLICK, self._restaurar)

	def mostrar(self) -> bool:
		"""Pone el icono en la bandeja. El texto emergente es lo que lee el lector."""
		return bool(self.SetIcon(_icono_aplicacion(), self._texto_actual))

	def actualizar(self, estado: EstadoEscritorios) -> None:
		"""Pone en el texto emergente el escritorio actual."""
		if not estado.escritorios:
			# Aún sin conectar: se queda «Conectando...».
			return
		self._estado = estado
		self._poner_texto()

	def poner_no_leidas(self, cuantas: int) -> None:
		"""Añade al texto del icono cuántas notificaciones quedan sin leer."""
		self._no_leidas = cuantas
		self._poner_texto()

	def _poner_texto(self) -> None:
		estado = getattr(self, "_estado", None)
		if estado is None or not estado.escritorios:
			return
		texto = texto_emergente(estado)
		cuantas = getattr(self, "_no_leidas", 0)
		if cuantas:
			texto += ". " + (_("1 notificación sin leer") if cuantas == 1 else _("{n} notificaciones sin leer").format(n=cuantas))
		# El texto emergente de Windows admite 127 caracteres.
		texto = texto[:127]
		if texto != self._texto_actual:
			self._texto_actual = texto
			if self.IsIconInstalled():
				self.SetIcon(_icono_aplicacion(), texto)

	def quitar(self) -> None:
		"""Quita el icono y destruye el objeto (hay que llamarlo siempre al cerrar)."""
		if self.IsIconInstalled():
			self.RemoveIcon()
		self.Destroy()

	def CreatePopupMenu(self) -> wx.Menu:  # noqa: N802 - nombre impuesto por wx
		"""Menú contextual del icono, con los escritorios de este momento."""
		menu = wx.Menu()
		self._agregar(menu, _("&Mostrar Centro de Mando"), self._restaurar)
		menu.AppendSeparator()

		estado = self._obtener_estado()
		destino = menu
		for escritorio in estado.escritorios:
			if escritorio.numero == MAXIMO_EN_MENU + 1:
				destino = wx.Menu()
				menu.AppendSubMenu(destino, _("Más escritorios"))
			# Las cifras 1-9 sirven de letra de acceso para los nueve primeros.
			prefijo = f"&{escritorio.numero}" if escritorio.numero <= 9 else str(escritorio.numero)
			# Un «&» del nombre se dobla para que no se tome como letra de acceso.
			etiqueta = f"{prefijo}. " + escritorio.nombre_visible.replace("&", "&&")
			item = destino.AppendRadioItem(wx.ID_ANY, etiqueta)
			item.Check(escritorio.actual)
			destino.Bind(
				wx.EVT_MENU, lambda _e, n=escritorio.numero: self._al_accion(f"ir_{n}") if n <= 10 else self._al_menu(f"ir:{n}"), item
			)
		if estado.escritorios:
			menu.AppendSeparator()

		self._agregar(menu, _("Escritorio si&guiente"), lambda _e: self._al_accion("siguiente"))
		self._agregar(menu, _("Escritorio &anterior"), lambda _e: self._al_accion("anterior"))
		self._agregar(menu, _("&Volver al escritorio anterior"), lambda _e: self._al_accion("alternar"))
		menu.AppendSeparator()
		self._agregar(menu, _("&Crear un escritorio"), lambda _e: self._al_accion("crear"))
		self._agregar(menu, _("Crear un escritorio e &ir a él"), lambda _e: self._al_accion("crear_e_ir"))
		self._agregar(menu, _("Cambiar el &nombre del escritorio actual..."), lambda _e: self._al_accion("renombrar_actual"))
		self._agregar(menu, _("&Eliminar el escritorio actual..."), lambda _e: self._al_accion("eliminar_actual"))
		menu.AppendSeparator()
		self._agregar(menu, _("&Lanzador..."), lambda _e: self._al_accion("lanzador"))
		self._agregar(menu, _("&Buscar una ventana..."), lambda _e: self._al_accion("buscar_ventana"))
		self._agregar(menu, _("Historial del &portapapeles..."), lambda _e: self._al_accion("portapapeles_rapido"))
		self._agregar(menu, _("Insertar un emo&ji..."), lambda _e: self._al_accion("emoticonos_rapido"))
		self._agregar(menu, _("&Historial de notificaciones..."), lambda _e: self._al_accion("notificaciones_rapido"))
		self._agregar(menu, _("&Teclas globales..."), lambda _e: self._al_menu("teclas_globales"))
		self._agregar(menu, _("&Opciones..."), lambda _e: self._al_menu("opciones"))
		menu.AppendSeparator()
		item = menu.Append(wx.ID_EXIT, _("&Salir"))
		menu.Bind(wx.EVT_MENU, lambda _evento: self._al_salir(), item)
		return menu

	@staticmethod
	def _agregar(menu: wx.Menu, etiqueta: str, manejador: Callable[[wx.CommandEvent], None]) -> None:
		item = menu.Append(wx.ID_ANY, etiqueta)
		menu.Bind(wx.EVT_MENU, manejador, item)

	def _restaurar(self, _evento: wx.Event | None = None) -> None:
		self._al_restaurar()


def _icono_aplicacion() -> wx.Icon:
	"""``data/icons/app.ico`` si existe; si no, un icono genérico de wx."""
	ruta = paths.ruta_iconos() / "app.ico"
	if ruta.is_file():
		icono = wx.Icon(str(ruta), wx.BITMAP_TYPE_ICO)
		if icono.IsOk():
			return icono
		log.warning("El icono %s no es válido; se usa el genérico", ruta)
	icono = wx.Icon()
	icono.CopyFromBitmap(wx.ArtProvider.GetBitmap(wx.ART_INFORMATION, wx.ART_OTHER, (16, 16)))
	return icono
