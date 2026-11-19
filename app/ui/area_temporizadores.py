"""Área de temporizadores, alarmas y recordatorios, y el aviso que aparece al vencer.

- «Temporizadores y alarmas» (Alt+L): nombre, tipo, cuándo suena y cuánto
  queda (se actualiza cada segundo sin que el lector lo relea). Espacio dice lo
  que queda; Suprimir lo elimina. Nuevo temporizador, nueva alarma y pausar,
  en el menú Acción y el contextual.
- Al vencer: suena un aviso cada pocos segundos, se anuncia y aparece una
  ventana delante de todo con «Posponer 5 minutos» y «Detener».
"""

from __future__ import annotations

import builtins
import logging
import threading
import time
from typing import TYPE_CHECKING

import wx

from app.services import temporizadores as servicio
from app.services import ventanas_win32 as w32
from app.ui import listas
from app.ui.accesibilidad.dialogos import crear_botonera, mostrar_mensaje, preparar_dialogo
from app.ui.accesibilidad.nombres import crear_campo
from app.ui.listas import actualizar_lista

if TYPE_CHECKING:
	from app.ui.controlador import Controlador

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class DialogoTemporizador(wx.Dialog):
	def __init__(self, padre: wx.Window | None) -> None:
		super().__init__(padre, title=_("Nuevo temporizador"))
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		_e, self.horas = crear_campo(panel, _("&Horas:"), wx.SpinCtrl, min=0, max=99, initial=0, sizer=sizer)
		_e, self.minutos = crear_campo(panel, _("&Minutos:"), wx.SpinCtrl, min=0, max=59, initial=5, sizer=sizer)
		_e, self.segundos = crear_campo(panel, _("&Segundos:"), wx.SpinCtrl, min=0, max=59, initial=0, sizer=sizer)
		_e, self.nombre = crear_campo(panel, _("&Nombre (opcional):"), wx.TextCtrl, ayuda=_("Lo que se dirá al terminar, por ejemplo «Sacar el pan del horno»."), sizer=sizer)
		sizer.Add(crear_botonera(panel, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		panel.SetSizer(sizer)
		marco = wx.BoxSizer(wx.VERTICAL)
		marco.Add(panel, 1, wx.EXPAND)
		self.SetSizerAndFit(marco)
		preparar_dialogo(self, foco_inicial=self.minutos)
		self.CentreOnParent()

	def total(self) -> int:
		return self.horas.GetValue() * 3600 + self.minutos.GetValue() * 60 + self.segundos.GetValue()


class DialogoAlarma(wx.Dialog):
	def __init__(self, padre: wx.Window | None) -> None:
		super().__init__(padre, title=_("Nueva alarma o recordatorio"))
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		_e, self.hora = crear_campo(
			panel, _("&Hora (por ejemplo 7:30 o 19:05):"), wx.TextCtrl, ayuda=_("Si esa hora ya ha pasado hoy, sonará mañana."), sizer=sizer
		)
		_e, self.nombre = crear_campo(
			panel, _("&Texto del recordatorio (opcional):"), wx.TextCtrl, ayuda=_("Lo que se dirá y se mostrará cuando suene."), sizer=sizer
		)
		self.diaria = wx.CheckBox(panel, label=_("&Repetir todos los días"))
		sizer.Add(self.diaria, 0, wx.ALL, 8)
		sizer.Add(crear_botonera(panel, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		panel.SetSizer(sizer)
		marco = wx.BoxSizer(wx.VERTICAL)
		marco.Add(panel, 1, wx.EXPAND)
		self.SetSizerAndFit(marco)
		self.Bind(wx.EVT_BUTTON, self._al_aceptar, id=wx.ID_OK)
		preparar_dialogo(self, foco_inicial=self.hora)
		self.CentreOnParent()

	def _al_aceptar(self, evento: wx.CommandEvent) -> None:
		if servicio.analizar_hora(self.hora.GetValue()) is None:
			mostrar_mensaje(self, _("Escriba una hora válida, por ejemplo 7:30 o 19:05."), _("Hora no válida"), wx.ICON_WARNING)
			self.hora.SetFocus()
			return
		evento.Skip()


class DialogoAviso(wx.Dialog):
	"""Aviso de un temporizador o alarma: delante de todo, con sonido hasta que se atiende."""

	def __init__(self, controlador: Controlador, temporizador: servicio.Temporizador) -> None:
		super().__init__(None, title=_("Aviso de Centro de Mando"), style=wx.DEFAULT_DIALOG_STYLE | wx.STAY_ON_TOP)
		self.controlador = controlador
		self.temporizador = temporizador
		self._sonando = threading.Event()
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		texto = _("{n}. Son las {h}.").format(n=temporizador.nombre, h=time.strftime("%H:%M"))
		etiqueta = wx.StaticText(panel, label=_("&Aviso:"))
		self.mensaje = wx.TextCtrl(panel, value=texto, style=wx.TE_MULTILINE | wx.TE_READONLY, size=self.FromDIP(wx.Size(420, 70)))
		sizer.Add(etiqueta, 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)
		sizer.Add(self.mensaje, 0, wx.EXPAND | wx.ALL, 8)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		self.posponer = wx.Button(panel, label=_("&Posponer 5 minutos"))
		self.detener = wx.Button(panel, wx.ID_CANCEL, _("&Detener"))
		fila.Add(self.posponer, 0, wx.RIGHT, 8)
		fila.Add(self.detener)
		sizer.Add(fila, 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		panel.SetSizer(sizer)
		marco = wx.BoxSizer(wx.VERTICAL)
		marco.Add(panel, 1, wx.EXPAND)
		self.SetSizerAndFit(marco)
		self.SetEscapeId(wx.ID_CANCEL)
		self.posponer.Bind(wx.EVT_BUTTON, self._al_posponer)
		self.detener.Bind(wx.EVT_BUTTON, lambda _e: self.cerrar())
		self.Bind(wx.EVT_CLOSE, lambda _e: self.cerrar())
		self.texto = texto

	def abrir(self) -> None:
		self.CentreOnScreen()
		self.Show()
		self.Raise()
		w32.forzar_primer_plano(self.GetHandle())
		self.detener.SetFocus()
		self.controlador.hablar(self.texto, True)
		self._sonando.set()
		threading.Thread(target=self._sonar, name="aviso", daemon=True).start()

	def _sonar(self) -> None:
		"""Un aviso cada 3 segundos durante 2 minutos o hasta que se atienda."""
		try:
			import winsound
		except ImportError:
			return
		limite = time.monotonic() + 120
		while self._sonando.is_set() and time.monotonic() < limite:
			try:
				winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS | winsound.SND_NODEFAULT)
			except RuntimeError:
				winsound.MessageBeep()
			self._sonando.wait(3)
			if not self._sonando.is_set():
				break

	def _al_posponer(self, _evento: wx.CommandEvent) -> None:
		self.controlador.temporizadores.posponer(self.temporizador.id, 5)
		self.controlador.hablar(_("Pospuesto 5 minutos"), True)
		self.cerrar()

	def cerrar(self) -> None:
		self._sonando.clear()
		if self:
			self.Destroy()


class AreaTemporizadores(wx.Panel):
	def __init__(self, padre: wx.Window, controlador: Controlador) -> None:
		super().__init__(padre)
		self.controlador = controlador
		self._lista: list[servicio.Temporizador] = []
		self._claves: list[str] = []
		sizer = wx.BoxSizer(wx.VERTICAL)
		etiqueta = wx.StaticText(self, label=_("&Lista de temporizadores y alarmas:"))
		self.lista = listas.crear_lista(
			self,
			_("Lista de temporizadores y alarmas"),
			[(_("Nombre"), self.FromDIP(300)), (_("Tipo"), self.FromDIP(140)), (_("Suena"), self.FromDIP(160)), (_("Queda"), self.FromDIP(220))],
			_("Espacio dice lo que queda; Suprimir lo elimina. Nuevo temporizador, nueva alarma y pausar, con la tecla Aplicaciones."),
		)
		sizer.Add(etiqueta, 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)
		sizer.Add(self.lista, 1, wx.EXPAND | wx.ALL, 8)
		self.SetSizer(sizer)
		self.lista.Bind(wx.EVT_CONTEXT_MENU, lambda _e: self.controlador.ventana.mostrar_menu_acciones(self.lista))
		self._reloj = wx.Timer(self)
		self.Bind(wx.EVT_TIMER, lambda _e: self.refrescar() if self.IsShownOnScreen() else None, self._reloj)

	def refrescar(self) -> None:
		if not self:
			return
		self._lista = self.controlador.temporizadores.todos()
		filas = []
		for t in self._lista:
			tipo = _("Temporizador") if t.tipo == servicio.TIPO_TEMPORIZADOR else (_("Alarma diaria") if t.diaria else _("Alarma"))
			if not t.activo:
				queda = _("terminado")
			elif t.pausado:
				queda = _("en pausa, quedan {d}").format(d=servicio.describir_duracion(t.restante()))
			else:
				queda = servicio.describir_duracion(t.restante())
			suena = time.strftime("%d/%m %H:%M:%S", time.localtime(t.vence)) if t.activo and not t.pausado else ""
			filas.append((t.id, (t.nombre, tipo, suena, queda)))
		actualizar_lista(self.lista, filas, self._claves)
		if not self._reloj.IsRunning():
			self._reloj.Start(1000)

	def enfocar(self) -> None:
		self.lista.SetFocus()
		if self.lista.numero_filas() and self.lista.GetFocusedItem() < 0:
			self.lista.enfocar_fila(0, anunciar=False)

	def seleccionado(self) -> servicio.Temporizador | None:
		fila = self.lista.fila_actual()
		return self._lista[fila] if 0 <= fila < len(self._lista) else None

	def nuevo_temporizador(self) -> None:
		dialogo = DialogoTemporizador(self)
		try:
			if dialogo.ShowModal() == wx.ID_OK and dialogo.total() > 0:
				t = self.controlador.temporizadores.nuevo_temporizador(dialogo.total(), dialogo.nombre.GetValue().strip())
				self.controlador.hablar(_("Temporizador de {d} en marcha").format(d=servicio.describir_duracion(t.duracion)), True)
		finally:
			dialogo.Destroy()
		self.refrescar()

	def nueva_alarma(self) -> None:
		dialogo = DialogoAlarma(self)
		try:
			if dialogo.ShowModal() == wx.ID_OK:
				hora, minuto = servicio.analizar_hora(dialogo.hora.GetValue())
				a = self.controlador.temporizadores.nueva_alarma(hora, minuto, dialogo.nombre.GetValue().strip(), dialogo.diaria.GetValue())
				self.controlador.hablar(_("Alarma para dentro de {d}").format(d=servicio.describir_duracion(a.restante())), True)
		finally:
			dialogo.Destroy()
		self.refrescar()

	def decir(self) -> None:
		t = self.seleccionado()
		if t is not None:
			texto = _("terminado") if not t.activo else servicio.describir_duracion(t.restante())
			self.controlador.hablar(f"{t.nombre}: {texto}", True)

	def pausar(self) -> None:
		t = self.seleccionado()
		if t is None:
			return
		pausado = self.controlador.temporizadores.pausar(t.id)
		if pausado is None:
			self.controlador.hablar(_("Solo se pueden pausar los temporizadores en marcha."), True)
		else:
			self.controlador.hablar(_("En pausa") if pausado else _("Reanudado"), True)
		self.refrescar()

	def eliminar(self) -> None:
		t = self.seleccionado()
		if t is not None:
			self.controlador.temporizadores.eliminar(t.id)
			self.controlador.hablar(_("Eliminado"), True)
			self.refrescar()

	def acciones(self) -> list:
		hay = self.seleccionado() is not None
		return [
			(_("&Nuevo temporizador..."), self.nuevo_temporizador, True),
			(_("Nueva &alarma o recordatorio..."), self.nueva_alarma, True),
			None,
			(_("&Decir lo que queda (Espacio)"), self.decir, hay),
			(_("&Pausar o reanudar"), self.pausar, hay),
			(_("&Eliminar (Suprimir)"), self.eliminar, hay),
		]

	def manejar_tecla(self, evento: wx.KeyEvent) -> bool:
		if wx.Window.FindFocus() is not self.lista or evento.HasAnyModifiers():
			return False
		if evento.GetKeyCode() == wx.WXK_SPACE:
			self.decir()
		elif evento.GetKeyCode() in (wx.WXK_DELETE, wx.WXK_NUMPAD_DELETE):
			self.eliminar()
		else:
			return False
		return True
