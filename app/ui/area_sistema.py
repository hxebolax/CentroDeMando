"""Área de sistema: estado del equipo y energía.

- «Estado del equipo» (Alt+E): batería, procesador, memoria, disco, red y
  tiempo encendido. Se actualiza cada pocos segundos mientras se ve.
- Las órdenes de energía están en el menú Acción y en el menú contextual:
  bloquear, suspender, hibernar, apagar la pantalla, apagar o reiniciar con
  cuenta atrás, cancelar el apagado y mantener el equipo despierto.
"""

from __future__ import annotations

import builtins
import logging
from typing import TYPE_CHECKING

import wx

from app.services import equipo
from app.ui import listas
from app.ui.accesibilidad.dialogos import confirmar
from app.ui.listas import actualizar_lista

if TYPE_CHECKING:
	from app.ui.controlador import Controlador

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


INTERVALO_MS = 3000


class AreaSistema(wx.Panel):
	def __init__(self, padre: wx.Window, controlador: Controlador) -> None:
		super().__init__(padre)
		self.controlador = controlador
		self._claves: list[str] = []
		self.despierto = False
		sizer = wx.BoxSizer(wx.VERTICAL)
		etiqueta = wx.StaticText(self, label=_("&Estado del equipo:"))
		self.lista = listas.crear_lista(
			self, _("Estado del equipo"), [(_("Dato"), self.FromDIP(200)), (_("Valor"), self.FromDIP(480))],
			_("Estado actual del equipo. La tecla Aplicaciones abre las órdenes de energía."),
		)
		sizer.Add(etiqueta, 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)
		sizer.Add(self.lista, 1, wx.EXPAND | wx.ALL, 8)
		self.SetSizer(sizer)
		self.lista.Bind(wx.EVT_CONTEXT_MENU, self._al_menu_contextual)
		self._temporizador = wx.Timer(self)
		self.Bind(wx.EVT_TIMER, lambda _e: self.refrescar() if self.IsShownOnScreen() else None, self._temporizador)

	def refrescar(self) -> None:
		if not self:
			return
		try:
			datos = equipo.estado()
		except Exception:  # noqa: BLE001
			log.exception("No se pudo leer el estado del equipo")
			return
		actualizar_lista(self.lista, [(d.nombre, (d.nombre, d.valor)) for d in datos], self._claves)
		if not self._temporizador.IsRunning():
			self._temporizador.Start(INTERVALO_MS)

	def enfocar(self) -> None:
		self.lista.SetFocus()
		if self.lista.numero_filas() and self.lista.GetFocusedItem() < 0:
			self.lista.enfocar_fila(0, anunciar=False)

	# ── Energía ─────────────────────────────────────────────────────────────

	def _confirmar(self, pregunta: str) -> bool:
		return confirmar(self, pregunta, _("Energía"), peligroso=True) == wx.ID_YES

	def bloquear(self) -> None:
		equipo.bloquear()

	def suspender(self) -> None:
		if self._confirmar(_("¿Suspender el equipo ahora?")) and not equipo.suspender():
			self.controlador.avisar(_("Windows no dejó suspender el equipo."))

	def hibernar(self) -> None:
		if self._confirmar(_("¿Hibernar el equipo ahora?")) and not equipo.suspender(hibernar=True):
			self.controlador.avisar(_("Windows no dejó hibernar el equipo. Puede que la hibernación esté desactivada."))

	def apagar_pantalla(self) -> None:
		equipo.apagar_pantalla()

	def programar(self, reiniciar: bool = False) -> None:
		accion = _("reiniciar") if reiniciar else _("apagar")
		dialogo = wx.NumberEntryDialog(self, _("Minutos hasta {a} el equipo:").format(a=accion), _("&Minutos:"), _("Programar"), 30, 0, 1440)
		try:
			if dialogo.ShowModal() != wx.ID_OK:
				return
			minutos = dialogo.GetValue()
		finally:
			dialogo.Destroy()
		try:
			equipo.programar_apagado(minutos, reiniciar)
		except Exception:  # noqa: BLE001 - p. ej. ya había otro apagado programado
			log.warning("No se pudo programar", exc_info=True)
			self.controlador.avisar(_("No se pudo programar. Si ya hay uno programado, cancélelo primero."))
			return
		self.controlador.hablar(_("El equipo se va a {a} dentro de {m} minutos. Puede cancelarlo desde aquí.").format(a=accion, m=minutos), True)

	def cancelar(self) -> None:
		self.controlador.hablar(_("Apagado cancelado") if equipo.cancelar_apagado() else _("No había ningún apagado programado"), True)

	def alternar_despierto(self) -> None:
		self.despierto = not self.despierto
		equipo.mantener_despierto(self.despierto)
		self.controlador.hablar(_("El equipo no se suspenderá") if self.despierto else _("El equipo vuelve a suspenderse normalmente"), True)

	def acciones(self) -> list:
		return [
			(_("&Bloquear el equipo"), self.bloquear, True),
			(_("&Suspender..."), self.suspender, True),
			(_("&Hibernar..."), self.hibernar, True),
			(_("Apagar la &pantalla"), self.apagar_pantalla, True),
			None,
			(_("&Apagar dentro de..."), lambda: self.programar(False), True),
			(_("&Reiniciar dentro de..."), lambda: self.programar(True), True),
			(_("&Cancelar el apagado programado"), self.cancelar, True),
			None,
			(_("&Mantener el equipo despierto"), self.alternar_despierto, True, self.despierto),
			(_("&Decir el estado"), lambda: self.controlador.hablar(equipo.resumen_para_voz(), True), True),
		]

	def manejar_tecla(self, _evento: wx.KeyEvent) -> bool:
		return False

	def _al_menu_contextual(self, _evento: wx.ContextMenuEvent) -> None:
		self.controlador.ventana.mostrar_menu_acciones(self.lista)
