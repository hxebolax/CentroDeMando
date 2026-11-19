"""Área de audio: dispositivo de salida, volumen general y volumen de cada aplicación.

Controles:

- «Dispositivos de salida» (Alt+D): Intro lo pone como predeterminado.
- «Volumen general» (Alt+G): deslizador de 0 a 100 (flechas de 1 en 1, RePág y AvPág de 10 en 10).
- «Aplicaciones con sonido» (Alt+S): volumen y si está silenciada. Más y menos
  (o Control+flechas arriba y abajo) cambian su volumen de 5 en 5; Espacio la silencia.
"""

from __future__ import annotations

import builtins
import logging
from typing import TYPE_CHECKING

import wx

from app.services import audio
from app.ui import listas
from app.ui.listas import actualizar_lista

if TYPE_CHECKING:
	from app.ui.controlador import Controlador

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


PASO = 5


class AreaAudio(wx.Panel):
	def __init__(self, padre: wx.Window, controlador: Controlador) -> None:
		super().__init__(padre)
		self.controlador = controlador
		self._dispositivos: list[audio.Dispositivo] = []
		self._sesiones: list[audio.Sesion] = []
		self._claves_dispositivos: list[str] = []
		self._claves_sesiones: list[str] = []
		sizer = wx.BoxSizer(wx.VERTICAL)
		etiqueta = wx.StaticText(self, label=_("&Dispositivos de salida:"))
		self.dispositivos = listas.crear_lista(
			self, _("Dispositivos de salida"), [(_("Dispositivo"), self.FromDIP(420)), (_("Estado"), self.FromDIP(160))],
			_("Intro pone el dispositivo como salida predeterminada."),
		)
		sizer.Add(etiqueta, 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)
		sizer.Add(self.dispositivos, 1, wx.EXPAND | wx.ALL, 8)
		etiqueta = wx.StaticText(self, label=_("Volumen &general:"))
		self.volumen = wx.Slider(self, minValue=0, maxValue=100, style=wx.SL_HORIZONTAL)
		self.volumen.SetHelpText(_("Volumen general de la salida predeterminada, de 0 a 100."))
		fila = wx.BoxSizer(wx.HORIZONTAL)
		fila.Add(etiqueta, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
		fila.Add(self.volumen, 1)
		sizer.Add(fila, 0, wx.EXPAND | wx.ALL, 8)
		etiqueta = wx.StaticText(self, label=_("Aplicaciones con &sonido:"))
		self.sesiones = listas.crear_lista(
			self,
			_("Aplicaciones con sonido"),
			[(_("Aplicación"), self.FromDIP(260)), (_("Volumen"), self.FromDIP(90)), (_("Estado"), self.FromDIP(120)), (_("Suena por"), self.FromDIP(260))],
			_("Más y menos, o Control+flechas arriba y abajo, cambian el volumen de la aplicación; Espacio la silencia."),
		)
		sizer.Add(etiqueta, 0, wx.LEFT | wx.RIGHT, 8)
		sizer.Add(self.sesiones, 2, wx.EXPAND | wx.ALL, 8)
		self.SetSizer(sizer)
		self.dispositivos.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: self.predeterminar())
		self.volumen.Bind(wx.EVT_SLIDER, self._al_mover_volumen)

	def refrescar(self) -> None:
		if not self:
			return
		try:
			self._dispositivos = audio.dispositivos_salida()
			self._sesiones = audio.sesiones()
			volumen, silencio = audio.volumen_general()
		except audio.ErrorAudio as error:
			self.controlador.hablar(str(error), True)
			return
		except Exception:  # noqa: BLE001
			log.exception("No se pudo leer el audio")
			return
		nombres = {d.id: d.nombre for d in self._dispositivos}
		actualizar_lista(
			self.dispositivos,
			[(d.id, (d.nombre, _("predeterminado") if d.predeterminado else "")) for d in self._dispositivos],
			self._claves_dispositivos,
		)
		if self.volumen.GetValue() != volumen:
			self.volumen.SetValue(volumen)
		self.volumen.SetHelpText(_("Volumen general: {v} %{s}.").format(v=volumen, s=_(", silenciado") if silencio else ""))
		actualizar_lista(
			self.sesiones,
			[
				(s.clave, (s.nombre, f"{s.volumen} %", _("silenciada") if s.silenciada else "", nombres.get(s.dispositivo, "")))
				for s in self._sesiones
			],
			self._claves_sesiones,
		)

	def enfocar(self) -> None:
		self.dispositivos.SetFocus()

	def _dispositivo(self) -> audio.Dispositivo | None:
		fila = self.dispositivos.fila_actual()
		return self._dispositivos[fila] if 0 <= fila < len(self._dispositivos) else None

	def _sesion(self) -> audio.Sesion | None:
		fila = self.sesiones.fila_actual()
		return self._sesiones[fila] if 0 <= fila < len(self._sesiones) else None

	def _intentar(self, funcion, *argumentos):
		try:
			return funcion(*argumentos)
		except audio.ErrorAudio as error:
			self.controlador.avisar(str(error))
		except Exception:  # noqa: BLE001
			log.exception("Error de audio")
			self.controlador.avisar(_("No se pudo cambiar el audio. Detalles en el registro."))
		return None

	def predeterminar(self) -> None:
		dispositivo = self._dispositivo()
		if dispositivo is not None and self._intentar(audio.poner_predeterminado, dispositivo) is None:
			self.controlador.hablar(_("Salida: {d}").format(d=dispositivo.nombre), True)
			self.refrescar()

	def _al_mover_volumen(self, _evento: wx.CommandEvent) -> None:
		self._intentar(audio.poner_volumen_general, self.volumen.GetValue())

	def volumen_aplicacion(self, paso: int) -> None:
		sesion = self._sesion()
		if sesion is None:
			return
		nuevo = self._intentar(audio.cambiar_volumen_sesion, sesion.clave, paso)
		if nuevo is not None:
			self.controlador.hablar(f"{nuevo} %", True)
			self.refrescar()

	def silenciar_aplicacion(self) -> None:
		sesion = self._sesion()
		if sesion is None:
			return
		silenciada = self._intentar(audio.alternar_silencio_sesion, sesion.clave)
		if silenciada is not None:
			self.controlador.hablar((_("{a} silenciada") if silenciada else _("{a} con sonido")).format(a=sesion.nombre), True)
			self.refrescar()

	def cambiar_salida(self) -> None:
		sesion = self._sesion()
		if sesion is None or not sesion.pid:
			self.controlador.hablar(_("Elija una aplicación de la lista."), True)
			return
		opciones = [_("La salida predeterminada"), *(d.nombre for d in self._dispositivos)]
		with wx.SingleChoiceDialog(self, _("Salida por la que suena {a}:").format(a=sesion.nombre), _("Salida de la aplicación"), opciones) as dialogo:
			if dialogo.ShowModal() != wx.ID_OK:
				return
			elegido = dialogo.GetSelection()
		dispositivo = self._dispositivos[elegido - 1] if elegido > 0 else None
		if self._intentar(audio.poner_salida_de_sesion, sesion, dispositivo) is None:
			self.controlador.hablar(_("{a} suena por {d}").format(a=sesion.nombre, d=opciones[elegido]), True)
			wx.CallLater(400, self.refrescar)

	def solo_esta(self) -> None:
		sesion = self._sesion()
		if sesion is None:
			return
		mensaje = self._intentar(audio.solo_estas, {s.clave for s in self._sesiones if s.nombre == sesion.nombre}, sesion.nombre)
		if mensaje:
			self.controlador.hablar(mensaje, True)
			self.refrescar()

	def acciones(self) -> list:
		hay_dispositivo = self._dispositivo() is not None
		hay_sesion = self._sesion() is not None
		return [
			(_("Usar como salida &predeterminada (Intro)"), self.predeterminar, hay_dispositivo),
			(_("Pasar a la siguie&nte salida"), self.controlador.siguiente_salida_audio, True),
			None,
			(_("&Subir el volumen de la aplicación (Más)"), lambda: self.volumen_aplicacion(PASO), hay_sesion),
			(_("&Bajar el volumen de la aplicación (Menos)"), lambda: self.volumen_aplicacion(-PASO), hay_sesion),
			(_("Si&lenciar o activar la aplicación (Espacio)"), self.silenciar_aplicacion, hay_sesion),
			(_("Cambiar la sali&da de la aplicación..."), self.cambiar_salida, hay_sesion),
			(_("Solo es&ta aplicación (otra vez: que suenen todas)"), self.solo_esta, hay_sesion),
			None,
			(_("Silenciar o activar el sonido &general"), self.controlador.silenciar_general, True),
			(_("Silenciar o activar el &micrófono"), self.controlador.silenciar_microfono, True),
		]

	def manejar_tecla(self, evento: wx.KeyEvent) -> bool:
		if wx.Window.FindFocus() is not self.sesiones:
			return False
		tecla, modificadores = evento.GetKeyCode(), evento.GetModifiers()
		if (tecla in (ord("+"), wx.WXK_NUMPAD_ADD) and modificadores in (wx.MOD_NONE, wx.MOD_SHIFT)) or (
			tecla == wx.WXK_UP and modificadores == wx.MOD_CONTROL
		):
			self.volumen_aplicacion(PASO)
		elif (tecla in (ord("-"), wx.WXK_NUMPAD_SUBTRACT) and modificadores == wx.MOD_NONE) or (
			tecla == wx.WXK_DOWN and modificadores == wx.MOD_CONTROL
		):
			self.volumen_aplicacion(-PASO)
		elif tecla == wx.WXK_SPACE and modificadores == wx.MOD_NONE:
			self.silenciar_aplicacion()
		else:
			return False
		return True
