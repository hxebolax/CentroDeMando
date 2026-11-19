"""Área de ventanas y procesos.

- «Buscar» (Alt+B): filtra las dos listas por título, programa o nombre.
- «Ventanas abiertas» (Alt+L): título, programa y estado (minimizada,
  maximizada, siempre encima, no responde). Intro la activa; Suprimir la cierra.
- «Procesos» (Alt+P): nombre, PID, procesador y memoria, de mayor a menor uso
  de procesador. Suprimir lo finaliza (con confirmación).

Se actualiza sola cada pocos segundos mientras se ve, sin mover al usuario
de su elemento. El resto de órdenes, en el menú Acción y el contextual.
"""

from __future__ import annotations

import builtins
import logging
import os
from typing import TYPE_CHECKING

import wx

from app.services import procesos
from app.services import ventanas_win32 as w32
from app.services.emojis import normalizar
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


class AreaProcesos(wx.Panel):
	def __init__(self, padre: wx.Window, controlador: Controlador) -> None:
		super().__init__(padre)
		self.controlador = controlador
		self.monitor = procesos.MonitorProcesos()
		self._ventanas: list[procesos.Ventana] = []
		self._procesos: list[procesos.Proceso] = []
		self._claves_ventanas: list[int] = []
		self._claves_procesos: list[int] = []
		sizer = wx.BoxSizer(wx.VERTICAL)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		etiqueta = wx.StaticText(self, label=_("&Buscar:"))
		self.buscar = wx.TextCtrl(self)
		self.buscar.SetHelpText(_("Filtra las ventanas y los procesos por su nombre."))
		fila.Add(etiqueta, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
		fila.Add(self.buscar, 1)
		sizer.Add(fila, 0, wx.EXPAND | wx.ALL, 8)
		etiqueta = wx.StaticText(self, label=_("&Lista de ventanas abiertas:"))
		self.lista = listas.crear_lista(
			self,
			_("Lista de ventanas abiertas"),
			[(_("Título"), self.FromDIP(380)), (_("Programa"), self.FromDIP(160)), (_("Estado"), self.FromDIP(200))],
			_("Intro activa la ventana; Suprimir la cierra. El resto de órdenes, con la tecla Aplicaciones."),
		)
		sizer.Add(etiqueta, 0, wx.LEFT | wx.RIGHT, 8)
		sizer.Add(self.lista, 1, wx.EXPAND | wx.ALL, 8)
		etiqueta = wx.StaticText(self, label=_("&Procesos:"))
		self.lista_procesos = listas.crear_lista(
			self,
			_("Procesos"),
			[(_("Nombre"), self.FromDIP(240)), (_("PID"), self.FromDIP(80)), (_("Procesador"), self.FromDIP(110)), (_("Memoria"), self.FromDIP(120))],
			_("Ordenados por uso de procesador. Suprimir finaliza el proceso; la tecla Aplicaciones abre sus órdenes."),
		)
		sizer.Add(etiqueta, 0, wx.LEFT | wx.RIGHT, 8)
		sizer.Add(self.lista_procesos, 1, wx.EXPAND | wx.ALL, 8)
		self.SetSizer(sizer)
		self.buscar.Bind(wx.EVT_TEXT, lambda _e: self.refrescar())
		self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: self.activar())
		self.lista.Bind(wx.EVT_CONTEXT_MENU, lambda _e: self.controlador.ventana.mostrar_menu_acciones(self.lista))
		self.lista_procesos.Bind(wx.EVT_CONTEXT_MENU, lambda _e: self.controlador.ventana.mostrar_menu_acciones(self.lista_procesos))
		self._temporizador = wx.Timer(self)
		self.Bind(wx.EVT_TIMER, lambda _e: self.refrescar() if self.IsShownOnScreen() else None, self._temporizador)

	def refrescar(self) -> None:
		if not self:
			return
		filtro = normalizar(self.buscar.GetValue()).split()
		encaja = lambda texto: all(p in normalizar(texto) for p in filtro)  # noqa: E731
		try:
			self._ventanas = [v for v in procesos.ventanas(os.getpid()) if encaja(f"{v.titulo} {v.proceso}")]
			self._procesos = sorted(
				(p for p in self.monitor.leer() if encaja(p.nombre)), key=lambda p: (-p.cpu, -p.memoria_mb)
			)
		except Exception:  # noqa: BLE001
			log.exception("No se pudieron leer las ventanas o los procesos")
			return
		actualizar_lista(self.lista, [(v.hwnd, (v.titulo, v.proceso, _(v.estado()))) for v in self._ventanas], self._claves_ventanas)
		actualizar_lista(
			self.lista_procesos,
			[
				(p.pid, (p.nombre, str(p.pid), f"{p.cpu:.1f} %".replace(".", ","), f"{p.memoria_mb:.0f} MB"))
				for p in self._procesos
			],
			self._claves_procesos,
		)
		if not self._temporizador.IsRunning():
			self._temporizador.Start(INTERVALO_MS)

	def enfocar(self) -> None:
		self.lista.SetFocus()
		if self.lista.numero_filas() and self.lista.GetFocusedItem() < 0:
			self.lista.enfocar_fila(0, anunciar=False)

	def ventana(self) -> procesos.Ventana | None:
		fila = self.lista.fila_actual()
		return self._ventanas[fila] if 0 <= fila < len(self._ventanas) else None

	def proceso(self) -> procesos.Proceso | None:
		"""El proceso de la lista de procesos o, si el foco está en las ventanas, el de la ventana."""
		if wx.Window.FindFocus() is self.lista:
			ventana = self.ventana()
			return next((p for p in self._procesos if ventana and p.pid == ventana.pid), None) or (
				procesos.Proceso(ventana.pid, ventana.proceso, 0, 0) if ventana else None
			)
		fila = self.lista_procesos.fila_actual()
		return self._procesos[fila] if 0 <= fila < len(self._procesos) else None

	# ── Acciones ────────────────────────────────────────────────────────────

	def _con_ventana(self, funcion, mensaje: str) -> None:
		ventana = self.ventana()
		if ventana is None:
			return
		funcion(ventana.hwnd)
		self.controlador.hablar(mensaje, True)
		wx.CallLater(300, self.refrescar)

	def activar(self) -> None:
		ventana = self.ventana()
		if ventana is not None:
			if ventana.minimizada:
				procesos.restaurar(ventana.hwnd)
			self.controlador.servicio.ir_a_ventana(ventana.hwnd)

	def minimizar(self) -> None:
		self._con_ventana(procesos.minimizar, _("Minimizada"))

	def maximizar(self) -> None:
		self._con_ventana(procesos.maximizar, _("Maximizada"))

	def restaurar(self) -> None:
		self._con_ventana(procesos.restaurar, _("Restaurada"))

	def alternar_encima(self) -> None:
		ventana = self.ventana()
		if ventana is None:
			return
		encima = not procesos.esta_encima(ventana.hwnd)
		procesos.poner_encima(ventana.hwnd, encima)
		self.controlador.hablar(_("Siempre encima") if encima else _("Ya no está siempre encima"), True)
		wx.CallLater(300, self.refrescar)

	def cerrar(self) -> None:
		self._con_ventana(w32.cerrar, _("Cierre pedido"))

	def finalizar(self) -> None:
		proceso = self.proceso()
		if proceso is None:
			return
		pregunta = _("¿Finalizar {n} (PID {p})? Se perderá lo que no se haya guardado.").format(n=proceso.nombre, p=proceso.pid)
		if confirmar(self, pregunta, _("Finalizar el proceso"), peligroso=True) != wx.ID_YES:
			return
		if procesos.finalizar(proceso.pid):
			self.controlador.hablar(_("{n} finalizado").format(n=proceso.nombre), True)
		else:
			self.controlador.avisar(_("Windows no deja finalizar {n}. Puede que haga falta ejecutar Centro de Mando como administrador.").format(n=proceso.nombre))
		wx.CallLater(300, self.refrescar)

	def abrir_ubicacion(self) -> None:
		proceso = self.proceso()
		ruta = procesos.ruta_de(proceso.pid) if proceso else ""
		if ruta:
			procesos.abrir_ubicacion(ruta)
		else:
			self.controlador.avisar(_("No se puede saber dónde está ese programa."))

	def copiar_ruta(self) -> None:
		proceso = self.proceso()
		ruta = procesos.ruta_de(proceso.pid) if proceso else ""
		if ruta:
			self.controlador.copiar_texto(ruta)
			self.controlador.hablar(_("Ruta copiada"), True)

	def acciones(self) -> list:
		hay_ventana = self.ventana() is not None
		hay_proceso = self.proceso() is not None
		ventana = self.ventana()
		return [
			(_("&Activar la ventana (Intro)"), self.activar, hay_ventana),
			(_("&Minimizar"), self.minimizar, hay_ventana),
			(_("Ma&ximizar"), self.maximizar, hay_ventana),
			(_("&Restaurar"), self.restaurar, hay_ventana),
			(_("&Siempre encima"), self.alternar_encima, hay_ventana, bool(ventana and ventana.encima)),
			(_("C&errar la ventana (Suprimir)"), self.cerrar, hay_ventana),
			None,
			(_("&Finalizar el proceso..."), self.finalizar, hay_proceso),
			(_("Abrir la &ubicación del programa"), self.abrir_ubicacion, hay_proceso),
			(_("&Copiar la ruta del programa"), self.copiar_ruta, hay_proceso),
		]

	def manejar_tecla(self, evento: wx.KeyEvent) -> bool:
		foco = wx.Window.FindFocus()
		if evento.GetKeyCode() not in (wx.WXK_DELETE, wx.WXK_NUMPAD_DELETE) or evento.HasAnyModifiers():
			return False
		if foco is self.lista:
			self.cerrar()
			return True
		if foco is self.lista_procesos:
			self.finalizar()
			return True
		return False
