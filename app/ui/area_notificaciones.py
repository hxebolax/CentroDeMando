"""Área de notificaciones: historial de las notificaciones de Windows y de las aplicaciones.

Se usa en la pestaña «Notificaciones» y en la ventana rápida.

Controles, en orden de tabulación:

- «Buscar en las notificaciones» (Alt+B): filtra mientras se escribe.
- «Mostrar» (Alt+S): todas, no leídas o favoritas.
- «Aplicación» (Alt+C): todas o una aplicación concreta.
- «Lista de notificaciones» (Alt+L): de la más reciente a la más antigua.
  Columnas: aplicación, título, texto, cuándo y estado.
- «Contenido» (Alt+T): título y texto completos, de solo lectura.

Teclas en la lista: Intro abre la aplicación que la envió, Mayúsculas+Intro
copia el texto, Espacio marca como leída o no leída, F4 favorita, Suprimir
la borra del historial y Mayúsculas+Suprimir la descarta también del centro
de notificaciones de Windows.
"""

from __future__ import annotations

import builtins
import logging
from typing import TYPE_CHECKING

import wx

from app.services.notificaciones import FILTRO_FAVORITAS, FILTRO_NO_LEIDAS, FILTRO_TODAS, Notificacion, abrir_aplicacion
from app.services.portapapeles import describir_tiempo
from app.ui import listas
from app.ui.accesibilidad.dialogos import confirmar
from app.ui.listas import actualizar_lista

if TYPE_CHECKING:
	from app.ui.controlador import Controlador

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


FILTROS = [(FILTRO_TODAS, "Todas"), (FILTRO_NO_LEIDAS, "No leídas"), (FILTRO_FAVORITAS, "Favoritas")]
RETRASO_BUSQUEDA_MS = 200
# Tiempo en una notificación antes de darla por leída (pasar por encima con las flechas no cuenta).
RETRASO_LEIDA_MS = 1500


def estado_de(notificacion: Notificacion) -> str:
	partes = [_("leída") if notificacion.leida else _("no leída")]
	if notificacion.favorita:
		partes.append(_("favorita"))
	if not notificacion.en_windows:
		partes.append(_("ya no está en Windows"))
	return ", ".join(partes)


class AreaNotificaciones(wx.Panel):
	"""Historial de notificaciones."""

	def __init__(self, padre: wx.Window, controlador: Controlador) -> None:
		super().__init__(padre)
		self.controlador = controlador
		self._notificaciones: list[Notificacion] = []
		self._claves: list[int] = []
		self._busqueda_pendiente: wx.CallLater | None = None
		self._leida_pendiente: wx.CallLater | None = None
		# Con el filtro «No leídas», las que se leen durante la consulta siguen en la
		# lista hasta cambiar de filtro: si desaparecieran, el usuario perdería su sitio.
		self._retenidas: set[int] = set()

		sizer = wx.BoxSizer(wx.VERTICAL)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		etiqueta = wx.StaticText(self, label=_("&Buscar en las notificaciones:"))
		self.buscar = wx.TextCtrl(self)
		self.buscar.SetHelpText(_("Escriba para filtrar por aplicación, título o texto. Flecha abajo baja a la lista."))
		fila.Add(etiqueta, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
		fila.Add(self.buscar, 1, wx.RIGHT, 12)
		etiqueta = wx.StaticText(self, label=_("Mo&strar:"))
		self.filtro = wx.Choice(self, choices=[_(n) for _c, n in FILTROS])
		self.filtro.SetSelection(0)
		self.filtro.SetHelpText(_("Todas, solo las no leídas o solo las favoritas."))
		fila.Add(etiqueta, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
		fila.Add(self.filtro, 0, wx.RIGHT, 12)
		etiqueta = wx.StaticText(self, label=_("Aplicació&n:"))
		self.app = wx.Choice(self, choices=[_("Todas las aplicaciones")])
		self.app.SetSelection(0)
		self.app.SetHelpText(_("Ver solo las notificaciones de una aplicación."))
		fila.Add(etiqueta, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
		fila.Add(self.app, 0)
		sizer.Add(fila, 0, wx.EXPAND | wx.ALL, 8)

		etiqueta = wx.StaticText(self, label=_("&Lista de notificaciones:"))
		self.lista = listas.crear_lista(
			self,
			_("Lista de notificaciones"),
			[
				(_("Aplicación"), self.FromDIP(160)),
				(_("Título"), self.FromDIP(260)),
				(_("Texto"), self.FromDIP(320)),
				(_("Recibida"), self.FromDIP(140)),
				(_("Estado"), self.FromDIP(160)),
			],
			_(
				"Intro abre la aplicación que la envió; Mayúsculas+Intro copia el texto; Espacio la marca como leída o no leída; "
				"F4 favorita; Suprimir la borra del historial; Mayúsculas+Suprimir la descarta también de Windows."
			),
		)
		sizer.Add(etiqueta, 0, wx.LEFT | wx.RIGHT, 8)
		sizer.Add(self.lista, 3, wx.EXPAND | wx.ALL, 8)
		etiqueta = wx.StaticText(self, label=_("Con&tenido:"))
		self.contenido = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2)
		self.contenido.SetHelpText(_("Título y texto completos de la notificación seleccionada."))
		sizer.Add(etiqueta, 0, wx.LEFT | wx.RIGHT, 8)
		sizer.Add(self.contenido, 1, wx.EXPAND | wx.ALL, 8)
		self.SetSizer(sizer)

		self.buscar.Bind(wx.EVT_TEXT, self._al_escribir)
		self.buscar.Bind(wx.EVT_KEY_DOWN, self._al_tecla_buscar)
		self.filtro.Bind(wx.EVT_CHOICE, self._al_cambiar_filtro)
		self.app.Bind(wx.EVT_CHOICE, self._al_cambiar_filtro)
		self.lista.Bind(wx.EVT_CONTEXT_MENU, self._al_menu_contextual)
		self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: self.abrir_app())
		self.lista.Bind(wx.EVT_LIST_ITEM_SELECTED, self._al_seleccionar)

	@property
	def historial(self):
		return self.controlador.notificaciones.historial

	# ── Datos ───────────────────────────────────────────────────────────────

	def refrescar(self) -> None:
		if not self:
			return
		try:
			apps = self.historial.aplicaciones()
			elegida = self.app.GetStringSelection() if self.app.GetSelection() > 0 else ""
			opciones = [_("Todas las aplicaciones"), *apps]
			if self.app.GetItems() != opciones:
				self.app.Set(opciones)
				self.app.SetSelection(opciones.index(elegida) if elegida in opciones else 0)
			app = self.app.GetStringSelection() if self.app.GetSelection() > 0 else ""
			filtro = FILTROS[max(self.filtro.GetSelection(), 0)][0]
			self._notificaciones = self.historial.listar(filtro, app, self.buscar.GetValue())
			if filtro == FILTRO_NO_LEIDAS and self._retenidas:
				presentes = {n.id for n in self._notificaciones}
				for identificador in self._retenidas - presentes:
					retenida = self.historial.obtener(identificador)
					if retenida is not None and (not app or retenida.app == app):
						self._notificaciones.append(retenida)
				self._notificaciones.sort(key=lambda n: (n.creada, n.id), reverse=True)
		except Exception:  # noqa: BLE001
			log.exception("No se pudo leer el historial de notificaciones")
			self._notificaciones = []
		filas = [
			(n.id, (n.app, n.titulo, " ".join(n.texto.split()), describir_tiempo(n.creada), estado_de(n))) for n in self._notificaciones
		]
		actualizar_lista(self.lista, filas, self._claves)
		self._mostrar_contenido()

	def seleccionada(self) -> Notificacion | None:
		fila = self.lista.fila_actual()
		if 0 <= fila < len(self._claves):
			return next((n for n in self._notificaciones if n.id == self._claves[fila]), None)
		return None

	def _mostrar_contenido(self) -> None:
		n = self.seleccionada()
		texto = f"{n.app}\n{n.texto_completo()}" if n else ""
		if self.contenido.GetValue() != texto:
			self.contenido.SetValue(texto)

	def enfocar(self) -> None:
		if self.lista.numero_filas():
			self.lista.SetFocus()
			if self.lista.GetFocusedItem() < 0:
				self.lista.enfocar_fila(0, anunciar=False)
		else:
			self.buscar.SetFocus()

	def _al_seleccionar(self, evento: wx.ListEvent) -> None:
		self._mostrar_contenido()
		if self._leida_pendiente is not None:
			self._leida_pendiente.Stop()
		if self.controlador.config.obtener("notificaciones.marcar_leida_al_ver", True):
			self._leida_pendiente = wx.CallLater(RETRASO_LEIDA_MS, self._marcar_vista)
		evento.Skip()

	def _al_cambiar_filtro(self, _evento: wx.CommandEvent) -> None:
		self._retenidas.clear()
		self.refrescar()

	def _marcar_vista(self) -> None:
		n = self.seleccionada()
		if self and n is not None and not n.leida:
			self.historial.marcar_leida([n.id], True)
			self._retenidas.add(n.id)
			n.leida = True
			fila = self.lista.fila_actual()
			self.lista.actualizar_celda(fila, 4, estado_de(n))
			self.controlador.notificar_no_leidas()

	# ── Acciones ────────────────────────────────────────────────────────────

	def abrir_app(self) -> None:
		n = self.seleccionada()
		if n is None:
			return
		if abrir_aplicacion(n.aumid):
			self.historial.marcar_leida([n.id], True)
			self.controlador.hablar(_("Abriendo {app}").format(app=n.app), True)
		else:
			self.controlador.avisar(_("No se pudo abrir la aplicación de esta notificación."))

	def copiar(self) -> None:
		n = self.seleccionada()
		if n is not None:
			self.controlador.copiar_texto(n.texto_completo())
			self.controlador.hablar(_("Texto copiado"), True)

	def alternar_leida(self) -> None:
		n = self.seleccionada()
		if n is None:
			return
		self.historial.marcar_leida([n.id], not n.leida)
		self._retenidas.add(n.id)
		self.controlador.hablar(_("Marcada como no leída") if n.leida else _("Marcada como leída"), True)
		self.refrescar()
		self.controlador.notificar_no_leidas()

	def alternar_favorita(self) -> None:
		n = self.seleccionada()
		if n is None:
			return
		self.historial.poner_favorita(n.id, not n.favorita)
		self.controlador.hablar(_("Quitada de favoritas") if n.favorita else _("Añadida a favoritas"), True)
		self.refrescar()

	def eliminar(self, tambien_en_windows: bool = False) -> None:
		n = self.seleccionada()
		if n is None:
			return
		if tambien_en_windows and n.en_windows:
			self.controlador.notificaciones.descartar_en_windows(n)
		self.historial.eliminar([n.id])
		self.controlador.hablar(_("Descartada y eliminada") if tambien_en_windows else _("Eliminada del historial"), True)
		self.refrescar()
		self.controlador.notificar_no_leidas()

	def descartar(self) -> None:
		n = self.seleccionada()
		if n is None:
			return
		if not n.en_windows:
			self.controlador.hablar(_("Esta notificación ya no está en el centro de notificaciones de Windows."), True)
			return

		def al_terminar(correcto: bool) -> None:
			wx.CallAfter(self.controlador.hablar, _("Descartada en Windows") if correcto else _("Windows ya no la tenía"), True)
			wx.CallAfter(self.refrescar)

		self.controlador.notificaciones.descartar_en_windows(n, al_terminar)

	def marcar_todas_leidas(self) -> None:
		cuantas = self.historial.marcar_todas_leidas()
		self.controlador.hablar(_("{n} marcadas como leídas").format(n=cuantas), True)
		self.refrescar()
		self.controlador.notificar_no_leidas()

	def vaciar(self) -> None:
		if (
			confirmar(
				self, _("¿Vaciar el historial de notificaciones? Las favoritas se conservan."), _("Vaciar el historial"), peligroso=True
			)
			== wx.ID_YES
		):
			cuantas = self.historial.vaciar()
			self.controlador.hablar(_("Eliminadas {n} notificaciones").format(n=cuantas), True)
			self.refrescar()
			self.controlador.notificar_no_leidas()

	def ignorar_app(self) -> None:
		n = self.seleccionada()
		if n is None or not n.app:
			return
		config = self.controlador.config
		actuales = [a.strip() for a in str(config.obtener("notificaciones.apps_ignoradas", "")).split(",") if a.strip()]
		if n.app.casefold() not in {a.casefold() for a in actuales}:
			actuales.append(n.app)
			config.establecer("notificaciones.apps_ignoradas", ", ".join(actuales))
			config.guardar()
		self.controlador.hablar(_("Las notificaciones de {app} ya no se guardarán").format(app=n.app), True)

	def acciones(self) -> list:
		n = self.seleccionada()
		hay = n is not None
		return [
			(_("&Abrir la aplicación que la envió (Intro)"), self.abrir_app, hay),
			(_("&Copiar el texto (Mayúsculas+Intro)"), self.copiar, hay),
			(_("Marcar como &leída o no leída (Espacio)"), self.alternar_leida, hay),
			(_("Añadir o quitar de &favoritas\tF4"), self.alternar_favorita, hay),
			(_("&Descartar en Windows"), self.descartar, hay),
			(_("&Eliminar del historial (Suprimir)"), self.eliminar, hay),
			(_("&Ignorar las de esta aplicación"), self.ignorar_app, hay),
			None,
			(_("Marcar &todas como leídas"), self.marcar_todas_leidas, True),
			(_("&Vaciar el historial..."), self.vaciar, True),
			(_("Detener la ca&ptura"), self.controlador.alternar_notificaciones, True, self.controlador.notificaciones.pausado),
			(_("Per&miso de Windows..."), self.controlador.abrir_permiso_notificaciones, True),
		]

	# ── Teclado ─────────────────────────────────────────────────────────────

	def manejar_tecla(self, evento: wx.KeyEvent) -> bool:
		if wx.Window.FindFocus() is not self.lista:
			return False
		tecla, modificadores = evento.GetKeyCode(), evento.GetModifiers()
		if tecla in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and modificadores == wx.MOD_SHIFT:
			self.copiar()
		elif tecla == wx.WXK_SPACE and modificadores == wx.MOD_NONE:
			self.alternar_leida()
		elif tecla == wx.WXK_F4 and modificadores == wx.MOD_NONE:
			self.alternar_favorita()
		elif tecla in (wx.WXK_DELETE, wx.WXK_NUMPAD_DELETE) and modificadores in (wx.MOD_NONE, wx.MOD_SHIFT):
			self.eliminar(tambien_en_windows=modificadores == wx.MOD_SHIFT)
		else:
			return False
		return True

	def _al_menu_contextual(self, evento: wx.ContextMenuEvent) -> None:
		n = self.seleccionada()
		if n is None:
			return
		menu = wx.Menu()
		opciones = [
			(_("&Abrir la aplicación que la envió"), self.abrir_app),
			(_("&Copiar el texto"), self.copiar),
			(_("Marcar como no &leída") if n.leida else _("Marcar como &leída"), self.alternar_leida),
			(_("Quitar de &favoritas") if n.favorita else _("Añadir a &favoritas"), self.alternar_favorita),
			None,
			(_("&Descartar en Windows"), self.descartar),
			(_("&Eliminar del historial"), self.eliminar),
			(_("Eliminar y descartar en &Windows"), lambda: self.eliminar(tambien_en_windows=True)),
			None,
			(_("&Ignorar las de {app}").format(app=n.app or _("esta aplicación")), self.ignorar_app),
			(_("Ver solo las de {app}").format(app=n.app) if n.app else None, self.solo_esta_app),
			(_("Marcar &todas como leídas"), self.marcar_todas_leidas),
		]
		for opcion in opciones:
			if opcion is None:
				menu.AppendSeparator()
				continue
			etiqueta, funcion = opcion
			if etiqueta is None:
				continue
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

	def solo_esta_app(self) -> None:
		n = self.seleccionada()
		if n is None or not n.app:
			return
		self.refrescar()
		elementos = self.app.GetItems()
		if n.app in elementos:
			self.app.SetSelection(elementos.index(n.app))
			self._retenidas.clear()
			self.refrescar()
			self.controlador.hablar(_("Solo las de {app}: {n}").format(app=n.app, n=len(self._notificaciones)), True)

	def _al_escribir(self, _evento: wx.CommandEvent) -> None:
		if self._busqueda_pendiente is not None:
			self._busqueda_pendiente.Stop()
		self._busqueda_pendiente = wx.CallLater(RETRASO_BUSQUEDA_MS, self._refrescar_busqueda)

	def _refrescar_busqueda(self) -> None:
		self.refrescar()
		if self.buscar.GetValue().strip():
			cuantas = len(self._notificaciones)
			self.controlador.hablar(
				_("Sin resultados") if not cuantas else (_("1 resultado") if cuantas == 1 else _("{n} resultados").format(n=cuantas))
			)

	def _al_tecla_buscar(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() in (wx.WXK_DOWN, wx.WXK_NUMPAD_DOWN) and not evento.HasAnyModifiers():
			if self._busqueda_pendiente is not None and self._busqueda_pendiente.IsRunning():
				self._busqueda_pendiente.Stop()
				self.refrescar()
			self.enfocar()
			return
		evento.Skip()
