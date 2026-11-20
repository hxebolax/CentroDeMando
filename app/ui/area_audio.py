"""Área de audio: salidas, volumen general, cada aplicación y los micrófonos.

Controles (en orden de tabulación, cada uno con su etiqueta delante):

- «Dispositivos de salida» (Alt+D): Intro lo pone como predeterminado.
- «Volumen general» (Alt+G) y «Silenciar el sonido general» (Alt+N).
- «Balance» (Alt+B): de -100 (todo a la izquierda) a 100 (todo a la derecha).
- «Aplicaciones con sonido» (Alt+S): volumen y si está silenciada. Más y menos
  (o Control+flechas arriba y abajo) cambian su volumen de 5 en 5; Espacio la silencia.
- «Volumen de la aplicación» (Alt+P) y «Silenciar la aplicación» (Alt+R): los
  de la aplicación seleccionada en la lista, igual que los generales.
- «Micrófonos» (Alt+F): Intro lo pone como predeterminado.
- «Amplificación del micrófono» (Alt+L): solo en micrófonos que la tienen.
- «Volumen del micrófono» (Alt+M), «Silenciar el micrófono» (Alt+E),
  «Escuchar este dispositivo» (Alt+T) y «Oír el micrófono por» (Alt+O): los del
  micrófono seleccionado. Escuchar lo reproduce por la salida elegida, como la
  pestaña Escuchar del Panel de sonido de Windows.

Se evitan A, C, I, V, H e Y: son las de la barra de menús.
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
# Cada cuánto se releen las aplicaciones y volúmenes mientras el área está a la vista.
INTERVALO_MS = 2000


def _deslizador(padre: wx.Window, etiqueta: str, ayuda: str) -> tuple[wx.StaticText, wx.Slider]:
	"""Etiqueta y deslizador de 0 a 100 (flechas de 1 en 1; RePág y AvPág de 10 en 10)."""
	texto = wx.StaticText(padre, label=etiqueta)
	control = wx.Slider(padre, minValue=0, maxValue=100, style=wx.SL_HORIZONTAL)
	control.SetPageSize(10)
	control.SetHelpText(ayuda)
	return texto, control


class AreaAudio(wx.Panel):
	def __init__(self, padre: wx.Window, controlador: Controlador) -> None:
		super().__init__(padre)
		self.controlador = controlador
		self._dispositivos: list[audio.Dispositivo] = []
		self._sesiones: list[audio.Sesion] = []
		self._entradas: list[audio.Dispositivo] = []
		self._claves_dispositivos: list[str] = []
		self._claves_sesiones: list[str] = []
		self._claves_entradas: list[str] = []
		self._refresco_pendiente: wx.CallLater | None = None
		sizer = wx.BoxSizer(wx.VERTICAL)

		# ── Salidas y volumen general ──
		etiqueta = wx.StaticText(self, label=_("&Dispositivos de salida:"))
		self.dispositivos = listas.crear_lista(
			self, _("Dispositivos de salida"), [(_("Dispositivo"), self.FromDIP(420)), (_("Estado"), self.FromDIP(160))],
			_("Intro pone el dispositivo como salida predeterminada."),
		)
		sizer.Add(etiqueta, 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)
		sizer.Add(self.dispositivos, 1, wx.EXPAND | wx.ALL, 8)
		etiqueta, self.volumen = _deslizador(self, _("Volumen &general:"), _("Volumen general de la salida predeterminada, de 0 a 100."))
		self.silencio_general = wx.CheckBox(self, label=_("Sile&nciar el sonido general"))
		sizer.Add(self._fila(etiqueta, self.volumen, self.silencio_general), 0, wx.EXPAND | wx.ALL, 8)
		etiqueta = wx.StaticText(self, label=_("&Balance (negativo, izquierda; positivo, derecha):"))
		self.balance = wx.Slider(self, value=0, minValue=-100, maxValue=100, style=wx.SL_HORIZONTAL)
		self.balance.SetPageSize(10)
		self.balance.SetHelpText(_("Inclina el sonido hacia un oído sin cambiar el volumen. 0 es centrado."))
		fila = wx.BoxSizer(wx.HORIZONTAL)
		fila.Add(etiqueta, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
		fila.Add(self.balance, 1)
		sizer.Add(fila, 0, wx.EXPAND | wx.ALL, 8)

		# ── Aplicaciones ──
		etiqueta = wx.StaticText(self, label=_("Aplicaciones con &sonido:"))
		self.sesiones = listas.crear_lista(
			self,
			_("Aplicaciones con sonido"),
			[(_("Aplicación"), self.FromDIP(260)), (_("Volumen"), self.FromDIP(90)), (_("Estado"), self.FromDIP(120)), (_("Suena por"), self.FromDIP(260))],
			_("Más y menos, o Control+flechas arriba y abajo, cambian el volumen de la aplicación; Espacio la silencia. "
			"Debajo están su volumen y su silencio, como los generales."),
		)
		sizer.Add(etiqueta, 0, wx.LEFT | wx.RIGHT, 8)
		sizer.Add(self.sesiones, 2, wx.EXPAND | wx.ALL, 8)
		etiqueta, self.volumen_app = _deslizador(
			self, _("Volumen de la a&plicación:"), _("Volumen de la aplicación seleccionada en la lista, de 0 a 100.")
		)
		self.silencio_app = wx.CheckBox(self, label=_("Silencia&r la aplicación"))
		sizer.Add(self._fila(etiqueta, self.volumen_app, self.silencio_app), 0, wx.EXPAND | wx.ALL, 8)

		# ── Micrófonos ──
		etiqueta = wx.StaticText(self, label=_("Micró&fonos:"))
		self.entradas = listas.crear_lista(
			self, _("Micrófonos"), [(_("Micrófono"), self.FromDIP(420)), (_("Estado"), self.FromDIP(160))],
			_("Intro pone el micrófono como predeterminado. Debajo están su volumen, su silencio y Escuchar este dispositivo."),
		)
		sizer.Add(etiqueta, 0, wx.LEFT | wx.RIGHT, 8)
		sizer.Add(self.entradas, 1, wx.EXPAND | wx.ALL, 8)
		etiqueta, self.volumen_micro = _deslizador(
			self, _("Volumen del &micrófono:"), _("Nivel de grabación del micrófono seleccionado, de 0 a 100.")
		)
		self.silencio_micro = wx.CheckBox(self, label=_("Sil&enciar el micrófono"))
		sizer.Add(self._fila(etiqueta, self.volumen_micro, self.silencio_micro), 0, wx.EXPAND | wx.ALL, 8)
		self.escuchar = wx.CheckBox(self, label=_("Escuchar es&te dispositivo"))
		self.escuchar.SetHelpText(
			_("Oye el micrófono por los altavoces o auriculares, como la pestaña Escuchar del Panel de sonido. "
			"Con altavoces puede acoplarse (pitido): mejor con auriculares.")
		)
		etiqueta_por = wx.StaticText(self, label=_("&Oír el micrófono por:"))
		self.escuchar_por = wx.Choice(self)
		self.escuchar_por.SetHelpText(_("Salida por la que se oye el micrófono cuando Escuchar este dispositivo está marcado."))
		fila = wx.BoxSizer(wx.HORIZONTAL)
		fila.Add(self.escuchar, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 16)
		fila.Add(etiqueta_por, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
		fila.Add(self.escuchar_por, 1)
		sizer.Add(fila, 0, wx.EXPAND | wx.ALL, 8)
		etiqueta = wx.StaticText(self, label=_("Amp&lificación del micrófono:"))
		self.amplificacion = wx.Choice(self)
		self.amplificacion.SetHelpText(
			_("Amplificación del micrófono seleccionado en decibelios, como en Niveles del Panel de sonido. "
			"Muchos micrófonos USB y Bluetooth no la tienen: entonces está desactivada.")
		)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		fila.Add(etiqueta, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
		fila.Add(self.amplificacion, 0)
		sizer.Add(fila, 0, wx.ALL, 8)
		self.SetSizer(sizer)
		self._amplificaciones: dict[str, list] = {}
		self._ver_ocultas = False

		self.dispositivos.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: self.predeterminar())
		self.entradas.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: self.predeterminar_micro())
		for lista, sincronizar in ((self.sesiones, self._sincronizar_app), (self.entradas, self._sincronizar_micro)):
			lista.Bind(wx.EVT_LIST_ITEM_SELECTED, lambda _e, s=sincronizar: s())
			lista.Bind(wx.EVT_LIST_ITEM_FOCUSED, lambda _e, s=sincronizar: s())
		self.volumen.Bind(wx.EVT_SLIDER, self._al_mover_volumen)
		self.balance.Bind(wx.EVT_SLIDER, self._al_mover_balance)
		self.silencio_general.Bind(wx.EVT_CHECKBOX, self._al_silencio_general)
		self.volumen_app.Bind(wx.EVT_SLIDER, self._al_mover_volumen_app)
		self.silencio_app.Bind(wx.EVT_CHECKBOX, self._al_silencio_app)
		self.volumen_micro.Bind(wx.EVT_SLIDER, self._al_mover_volumen_micro)
		self.silencio_micro.Bind(wx.EVT_CHECKBOX, self._al_silencio_micro)
		self.escuchar.Bind(wx.EVT_CHECKBOX, self._al_escuchar)
		self.escuchar_por.Bind(wx.EVT_CHOICE, self._al_escuchar)
		self.amplificacion.Bind(wx.EVT_CHOICE, self._al_amplificacion)
		self._temporizador = wx.Timer(self)
		self.Bind(wx.EVT_TIMER, lambda _e: self.refrescar() if self.IsShownOnScreen() else None, self._temporizador)
		self.Bind(wx.EVT_WINDOW_DESTROY, self._al_destruir)

	def _fila(self, etiqueta: wx.StaticText, deslizador: wx.Slider, casilla: wx.CheckBox) -> wx.BoxSizer:
		fila = wx.BoxSizer(wx.HORIZONTAL)
		fila.Add(etiqueta, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
		fila.Add(deslizador, 1, wx.RIGHT, 16)
		fila.Add(casilla, 0, wx.ALIGN_CENTER_VERTICAL)
		return fila

	def _al_destruir(self, evento: wx.WindowDestroyEvent) -> None:
		if evento.GetEventObject() is self and self._temporizador.IsRunning():
			self._temporizador.Stop()
		evento.Skip()

	# ── Lectura ─────────────────────────────────────────────────────────────

	def refrescar(self) -> None:
		if not self:
			return
		try:
			self._dispositivos = audio.dispositivos_salida()
			self._sesiones = self._filtrar_ocultas(audio.sesiones())
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
			[(d.id, (d.nombre, _(d.estado()))) for d in self._dispositivos],
			self._claves_dispositivos,
		)
		self._poner_valor(self.volumen, volumen)
		try:
			balance = audio.balance_general()
		except Exception:  # noqa: BLE001
			balance = None
		self.balance.Enable(balance is not None)
		if balance is not None:
			self._poner_valor(self.balance, balance)
			self.balance.SetHelpText(_("Balance: {b}.").format(b=audio.describir_balance(balance)))
		else:
			self.balance.SetHelpText(_("Esta salida no tiene canal izquierdo y derecho: su balance no se puede cambiar."))
		self._poner_casilla(self.silencio_general, silencio)
		self.volumen.SetHelpText(_("Volumen general: {v} %{s}.").format(v=volumen, s=_(", silenciado") if silencio else ""))
		limites = self.controlador.limites_volumen()
		actualizar_lista(
			self.sesiones,
			[(s.clave, (s.nombre, f"{s.volumen} %", self._estado_sesion(s, limites), nombres.get(s.dispositivo, ""))) for s in self._sesiones],
			self._claves_sesiones,
		)
		self._sincronizar_app()
		try:
			self._entradas = audio.dispositivos_entrada()
		except Exception:  # noqa: BLE001 - sin micrófonos, el resto del área sigue
			log.debug("No se pudieron leer los micrófonos", exc_info=True)
			self._entradas = []
		actualizar_lista(
			self.entradas,
			[(d.id, (d.nombre, _(d.estado()))) for d in self._entradas],
			self._claves_entradas,
		)
		self._rellenar_salidas_escucha()
		self._sincronizar_micro()
		if not self._temporizador.IsRunning():
			self._temporizador.Start(INTERVALO_MS)

	@staticmethod
	def _poner_valor(control: wx.Slider, valor: int) -> None:
		"""Pone el valor salvo si la persona lo está moviendo (tiene el foco)."""
		if control.GetValue() != valor and wx.Window.FindFocus() is not control:
			control.SetValue(valor)

	@staticmethod
	def _poner_casilla(control: wx.CheckBox, valor: bool) -> None:
		if control.GetValue() != valor:
			control.SetValue(valor)

	def _sincronizar_app(self) -> None:
		"""El deslizador y la casilla de la aplicación muestran la seleccionada."""
		sesion = self._sesion()
		for control in (self.volumen_app, self.silencio_app):
			control.Enable(sesion is not None)
		if sesion is None:
			return
		self._poner_valor(self.volumen_app, sesion.volumen)
		self._poner_casilla(self.silencio_app, sesion.silenciada)
		self.volumen_app.SetHelpText(_("Volumen de {a}, de 0 a 100.").format(a=sesion.nombre))

	def _rellenar_salidas_escucha(self) -> None:
		opciones = [_("La salida predeterminada"), *(d.nombre for d in self._dispositivos)]
		if self.escuchar_por.GetItems() != opciones:
			seleccion = self.escuchar_por.GetSelection()
			self.escuchar_por.SetItems(opciones)
			self.escuchar_por.SetSelection(seleccion if 0 <= seleccion < len(opciones) else 0)

	def _sincronizar_micro(self) -> None:
		"""Volumen, silencio y escucha del micrófono seleccionado."""
		micro = self._entrada()
		for control in (self.volumen_micro, self.silencio_micro, self.escuchar, self.escuchar_por):
			control.Enable(micro is not None)
		if micro is None:
			return
		try:
			volumen, silencio = audio.volumen_entrada(micro.id)
			activa, destino = audio.leer_escucha(micro.id)
		except Exception:  # noqa: BLE001 - micrófono desconectado entre medias
			log.debug("No se pudo leer el micrófono %s", micro.nombre, exc_info=True)
			return
		self._poner_valor(self.volumen_micro, volumen)
		self._poner_casilla(self.silencio_micro, silencio)
		self._poner_casilla(self.escuchar, activa)
		if wx.Window.FindFocus() is not self.escuchar_por:
			posicion = next((i + 1 for i, d in enumerate(self._dispositivos) if d.id == destino), 0)
			if self.escuchar_por.GetSelection() != posicion:
				self.escuchar_por.SetSelection(posicion)
		self.volumen_micro.SetHelpText(_("Volumen de {m}, de 0 a 100.").format(m=micro.nombre))
		self._sincronizar_amplificacion(micro)

	# ── Amplificación del micrófono ─────────────────────────────────────────

	def _amplificacion_de(self, micro: audio.Dispositivo):
		"""Primer control de amplificación del micrófono (se busca una vez por micrófono)."""
		from app.services import topologia

		if micro.id not in self._amplificaciones:
			try:
				self._amplificaciones[micro.id] = topologia.buscar_amplificaciones(micro.id)
			except Exception:  # noqa: BLE001
				log.debug("No se pudo leer la topología de %s", micro.nombre, exc_info=True)
				self._amplificaciones[micro.id] = []
		controles = self._amplificaciones[micro.id]
		return controles[0] if controles else None

	def _sincronizar_amplificacion(self, micro: audio.Dispositivo) -> None:
		from app.services import topologia

		control = self._amplificacion_de(micro)
		self.amplificacion.Enable(control is not None)
		if control is None:
			if self.amplificacion.GetItems() != [_("No tiene")]:
				self.amplificacion.SetItems([_("No tiene")])
				self.amplificacion.SetSelection(0)
			return
		try:
			control.nivel = float(control._control.GetLevel(0))
		except Exception:  # noqa: BLE001 - desconectado
			return
		valores = topologia.pasos_validos(control.minimo, control.maximo, control.paso)
		textos = [topologia.formatear_db(v) for v in valores]
		if self.amplificacion.GetItems() != textos:
			self.amplificacion.SetItems(textos)
		if wx.Window.FindFocus() is not self.amplificacion:
			cercano = min(range(len(valores)), key=lambda i: abs(valores[i] - control.nivel))
			if self.amplificacion.GetSelection() != cercano:
				self.amplificacion.SetSelection(cercano)

	def _al_amplificacion(self, _evento: wx.CommandEvent) -> None:
		from app.services import topologia

		micro = self._entrada()
		control = self._amplificacion_de(micro) if micro else None
		if control is None:
			return
		valores = topologia.pasos_validos(control.minimo, control.maximo, control.paso)
		posicion = self.amplificacion.GetSelection()
		if 0 <= posicion < len(valores):
			nivel = self._intentar(topologia.poner_amplificacion, control, valores[posicion])
			if nivel is not None:
				self.controlador.hablar(_("Amplificación {d}").format(d=topologia.formatear_db(nivel)), True)

	# ── Aplicaciones ocultas y volumen máximo ───────────────────────────────

	def _filtrar_ocultas(self, sesiones: list) -> list:
		if self._ver_ocultas:
			return sesiones
		ocultas = audio.lista_programas(self.controlador.config.obtener("audio.apps_ocultas", ""))
		return [s for s in sesiones if audio.nombre_programa(s.nombre) not in ocultas]

	@staticmethod
	def _estado_sesion(sesion, limites: dict[str, int]) -> str:
		partes = []
		if sesion.silenciada:
			partes.append(_("silenciada"))
		maximo = limites.get(audio.nombre_programa(sesion.nombre))
		if maximo is not None:
			partes.append(_("máximo {m} %").format(m=maximo))
		return ", ".join(partes)

	def _limitar(self, sesion, valor: int) -> int:
		"""Un valor pedido para la aplicación, recortado a su volumen máximo si lo tiene."""
		maximo = self.controlador.limites_volumen().get(audio.nombre_programa(sesion.nombre))
		return min(valor, maximo) if maximo is not None else valor

	def ocultar_aplicacion(self) -> None:
		sesion = self._sesion()
		if sesion is None or not sesion.pid:
			return
		config = self.controlador.config
		ocultas = audio.lista_programas(config.obtener("audio.apps_ocultas", ""))
		ocultas.add(audio.nombre_programa(sesion.nombre))
		config.establecer("audio.apps_ocultas", ", ".join(sorted(ocultas)))
		config.guardar()
		self.controlador.hablar(
			_("{a} oculta. Para volver a verla: Ver las aplicaciones ocultas, o en Opciones, Audio.").format(a=sesion.nombre), True
		)
		self.refrescar()

	def alternar_ocultas(self) -> None:
		self._ver_ocultas = not self._ver_ocultas
		self.controlador.hablar(_("Se ven todas las aplicaciones") if self._ver_ocultas else _("Las aplicaciones ocultas no se ven"), True)
		self.refrescar()

	def volumen_maximo(self) -> None:
		from app.ui.accesibilidad.dialogos import pedir_texto

		sesion = self._sesion()
		if sesion is None or not sesion.pid:
			return
		actual = self.controlador.limites_volumen().get(audio.nombre_programa(sesion.nombre), 100)
		texto = pedir_texto(
			self,
			_("Volumen máximo de {a}, de 0 a 100 (100 = sin límite). Si la aplicación lo supera, Centro de Mando se lo baja:").format(
				a=sesion.nombre
			),
			_("Volumen máximo"),
			str(actual),
		)
		if texto is None:
			return
		try:
			maximo = int(texto.strip().rstrip("%").strip())
		except ValueError:
			self.controlador.avisar(_("Escriba un número de 0 a 100."))
			return
		maximo = min(max(maximo, 0), 100)
		self.controlador.poner_limite_volumen(sesion.nombre, maximo)
		if maximo >= 100:
			self.controlador.hablar(_("{a} sin volumen máximo").format(a=sesion.nombre), True)
		else:
			self._intentar(audio.aplicar_limites, self.controlador.limites_volumen())
			self.controlador.hablar(_("{a}: máximo {m} %").format(a=sesion.nombre, m=maximo), True)
		self.refrescar()

	def _refrescar_pronto(self) -> None:
		"""Relee las listas un momento después (tras mover un deslizador, sin hacerlo en cada paso)."""
		if self._refresco_pendiente is not None and self._refresco_pendiente.IsRunning():
			self._refresco_pendiente.Restart(400)
		else:
			self._refresco_pendiente = wx.CallLater(400, self.refrescar)

	def enfocar(self) -> None:
		self.dispositivos.SetFocus()

	def _dispositivo(self) -> audio.Dispositivo | None:
		fila = self.dispositivos.fila_actual()
		return self._dispositivos[fila] if 0 <= fila < len(self._dispositivos) else None

	def _sesion(self) -> audio.Sesion | None:
		fila = self.sesiones.fila_actual()
		return self._sesiones[fila] if 0 <= fila < len(self._sesiones) else None

	def _entrada(self) -> audio.Dispositivo | None:
		fila = self.entradas.fila_actual()
		if 0 <= fila < len(self._entradas):
			return self._entradas[fila]
		# Sin selección: el predeterminado (así los controles nunca quedan vacíos).
		return next((d for d in self._entradas if d.predeterminado), self._entradas[0] if self._entradas else None)

	def _intentar(self, funcion, *argumentos):
		try:
			return funcion(*argumentos)
		except audio.ErrorAudio as error:
			self.controlador.avisar(str(error))
		except Exception:  # noqa: BLE001
			log.exception("Error de audio")
			self.controlador.avisar(_("No se pudo cambiar el audio. Detalles en el registro."))
		return None

	# ── Salidas y general ───────────────────────────────────────────────────

	def predeterminar(self) -> None:
		dispositivo = self._dispositivo()
		if dispositivo is not None and self._intentar(audio.poner_predeterminado, dispositivo) is None:
			self.controlador.hablar(_("Salida: {d}").format(d=dispositivo.nombre), True)
			self.refrescar()

	def _al_mover_volumen(self, _evento: wx.CommandEvent) -> None:
		self._intentar(audio.poner_volumen_general, self.volumen.GetValue())

	def _al_mover_balance(self, _evento: wx.CommandEvent) -> None:
		self._intentar(audio.poner_balance_general, self.balance.GetValue())

	def alternar_mejoras(self) -> None:
		"""Mejoras de audio (efectos del controlador) de la salida seleccionada."""
		dispositivo = self._dispositivo()
		if dispositivo is None:
			return
		actuales = audio.leer_mejoras(dispositivo.id)
		if actuales is None:
			self.controlador.hablar(_("{d} no tiene mejoras de audio.").format(d=dispositivo.nombre), True)
			return
		if self._intentar(audio.poner_mejoras, dispositivo.id, not actuales) is None:
			self.controlador.hablar(
				(_("Mejoras de audio desactivadas en {d}") if actuales else _("Mejoras de audio activadas en {d}")).format(d=dispositivo.nombre),
				True,
			)

	def comunicaciones_salida(self) -> None:
		dispositivo = self._dispositivo()
		if dispositivo is not None and self._intentar(audio.poner_comunicaciones, dispositivo) is None:
			self.controlador.hablar(_("Comunicaciones: {d}").format(d=dispositivo.nombre), True)
			self.refrescar()

	def comunicaciones_micro(self) -> None:
		micro = self._entrada()
		if micro is not None and self._intentar(audio.poner_comunicaciones, micro) is None:
			self.controlador.hablar(_("Micrófono de comunicaciones: {m}").format(m=micro.nombre), True)
			self.refrescar()

	# ── Dispositivos preferidos ─────────────────────────────────────────────

	def preferencias(self, entrada: bool) -> None:
		from app.ui.dialogo_preferencias_audio import DialogoPreferenciasAudio

		sufijo = "entrada" if entrada else "salida"
		config = self.controlador.config
		conocidos = self._intentar(audio.nombres_conocidos, entrada) or []
		guardadas = [n for n in config.obtener(f"audio.preferencias_{sufijo}", []) if isinstance(n, str)]
		with DialogoPreferenciasAudio(
			self, entrada, bool(config.obtener(f"audio.cambio_automatico_{sufijo}", False)), guardadas, conocidos
		) as dialogo:
			if dialogo.ShowModal() != wx.ID_OK:
				return
			activo, orden = dialogo.resultado()
		config.establecer(f"audio.cambio_automatico_{sufijo}", activo)
		config.establecer(f"audio.preferencias_{sufijo}", orden)
		config.guardar()
		if activo:
			self.controlador.aplicar_preferencias_audio()

	# ── Perfiles ────────────────────────────────────────────────────────────

	def guardar_perfil(self) -> None:
		from app.services import perfiles_audio

		perfiles = self.controlador.perfiles_audio()
		with wx.TextEntryDialog(
			self,
			_("Nombre del perfil (por ejemplo «Auriculares» o «Reuniones»). Guarda la salida, el micrófono, "
			"los de comunicaciones y los volúmenes de ahora. Si ya existe uno con ese nombre, se sustituye:"),
			_("Guardar el perfil de audio"),
		) as dialogo:
			if dialogo.ShowModal() != wx.ID_OK:
				return
			nombre = dialogo.GetValue().strip()
		if not nombre:
			return
		perfil = self._intentar(perfiles_audio.capturar, nombre)
		if perfil is None:
			return
		perfiles = [p for p in perfiles if p.nombre.casefold() != nombre.casefold()] + [perfil]
		self.controlador.guardar_perfiles_audio(perfiles)
		self.controlador.hablar(_("Perfil {p} guardado: {d}").format(p=nombre, d=perfil.describir()), True)

	def _elegir_perfil(self, titulo: str):
		perfiles = self.controlador.perfiles_audio()
		if not perfiles:
			self.controlador.hablar(_("No hay perfiles de audio. Use Guardar el audio actual como perfil."), True)
			return None, perfiles
		opciones = [f"{p.nombre}: {p.describir()}" for p in perfiles]
		with wx.SingleChoiceDialog(self, _("Perfiles de audio:"), titulo, opciones) as dialogo:
			if dialogo.ShowModal() != wx.ID_OK:
				return None, perfiles
			return perfiles[dialogo.GetSelection()], perfiles

	def aplicar_perfil(self) -> None:
		perfil, _perfiles = self._elegir_perfil(_("Aplicar un perfil de audio"))
		if perfil is not None:
			self.controlador.aplicar_perfil_audio(perfil)
			self.refrescar()

	def eliminar_perfil(self) -> None:
		perfil, perfiles = self._elegir_perfil(_("Eliminar un perfil de audio"))
		if perfil is not None:
			self.controlador.guardar_perfiles_audio([p for p in perfiles if p is not perfil])
			self.controlador.hablar(_("Perfil {p} eliminado").format(p=perfil.nombre), True)

	def _al_silencio_general(self, _evento: wx.CommandEvent) -> None:
		self._intentar(audio.poner_silencio_general, self.silencio_general.GetValue())

	# ── Aplicación seleccionada ─────────────────────────────────────────────

	def _al_mover_volumen_app(self, _evento: wx.CommandEvent) -> None:
		sesion = self._sesion()
		if sesion is not None and self._intentar(audio.poner_volumen_sesion, sesion.clave, self._limitar(sesion, self.volumen_app.GetValue())) is not None:
			self._refrescar_pronto()

	def _al_silencio_app(self, _evento: wx.CommandEvent) -> None:
		sesion = self._sesion()
		if sesion is not None and self._intentar(audio.poner_silencio_sesion, sesion.clave, self.silencio_app.GetValue()) is not None:
			self._refrescar_pronto()

	def volumen_aplicacion(self, paso: int) -> None:
		sesion = self._sesion()
		if sesion is None:
			return
		nuevo = self._intentar(audio.poner_volumen_sesion, sesion.clave, self._limitar(sesion, sesion.volumen + paso))
		if nuevo is not None:
			self.controlador.hablar(f"{nuevo} %" + (_(", el máximo") if paso > 0 and nuevo < min(sesion.volumen + paso, 100) else ""), True)
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

	# ── Micrófonos ──────────────────────────────────────────────────────────

	def predeterminar_micro(self) -> None:
		micro = self._entrada()
		if micro is not None and self._intentar(audio.poner_predeterminado_entrada, micro) is None:
			self.controlador.hablar(_("Micrófono: {m}").format(m=micro.nombre), True)
			self.refrescar()

	def _al_mover_volumen_micro(self, _evento: wx.CommandEvent) -> None:
		micro = self._entrada()
		if micro is not None and self._intentar(audio.poner_volumen_entrada, self.volumen_micro.GetValue(), micro.id) is not None:
			if micro.predeterminado:
				self.controlador.fijar_volumen_micro_bloqueado(self.volumen_micro.GetValue())

	def _al_silencio_micro(self, _evento: wx.CommandEvent) -> None:
		micro = self._entrada()
		if micro is not None:
			self._intentar(audio.poner_silencio_entrada, self.silencio_micro.GetValue(), micro.id)

	def _al_escuchar(self, _evento: wx.CommandEvent) -> None:
		micro = self._entrada()
		if micro is None:
			return
		posicion = self.escuchar_por.GetSelection()
		destino = self._dispositivos[posicion - 1].id if 0 < posicion <= len(self._dispositivos) else ""
		activar = self.escuchar.GetValue()
		if self._intentar(audio.poner_escucha, micro.id, activar, destino) is None:
			if activar:
				salida = self.escuchar_por.GetString(posicion) if posicion >= 0 else _("La salida predeterminada")
				self.controlador.hablar(_("Se oye {m} por {s}").format(m=micro.nombre, s=salida.lower() if posicion <= 0 else salida), True)
			elif _evento.GetEventObject() is self.escuchar:
				self.controlador.hablar(_("Ya no se oye {m}").format(m=micro.nombre), True)
		else:
			self._sincronizar_micro()

	def alternar_escucha(self) -> None:
		"""Menú Acción: marca o desmarca Escuchar este dispositivo."""
		self.escuchar.SetValue(not self.escuchar.GetValue())
		evento = wx.CommandEvent(wx.wxEVT_CHECKBOX, self.escuchar.GetId())
		evento.SetEventObject(self.escuchar)
		self._al_escuchar(evento)

	# ── Menú Acción y teclas ────────────────────────────────────────────────

	def acciones(self) -> list:
		hay_dispositivo = self._dispositivo() is not None
		hay_sesion = self._sesion() is not None
		hay_micro = self._entrada() is not None
		return [
			(_("Usar como salida &predeterminada (Intro)"), self.predeterminar, hay_dispositivo),
			(_("Pasar a la siguie&nte salida"), self.controlador.siguiente_salida_audio, True),
			None,
			(_("&Subir el volumen de la aplicación (Más)"), lambda: self.volumen_aplicacion(PASO), hay_sesion),
			(_("&Bajar el volumen de la aplicación (Menos)"), lambda: self.volumen_aplicacion(-PASO), hay_sesion),
			(_("Si&lenciar o activar la aplicación (Espacio)"), self.silenciar_aplicacion, hay_sesion),
			(_("Cambiar la sali&da de la aplicación..."), self.cambiar_salida, hay_sesion),
			(_("Solo es&ta aplicación (otra vez: que suenen todas)"), self.solo_esta, hay_sesion),
			(_("Volumen má&ximo de la aplicación..."), self.volumen_maximo, hay_sesion),
			(_("&Ocultar esta aplicación de la lista"), self.ocultar_aplicacion, hay_sesion),
			(_("&Ver las aplicaciones ocultas") if not self._ver_ocultas else _("No &ver las aplicaciones ocultas"), self.alternar_ocultas, True),
			None,
			(_("Usar como salida de &comunicaciones (llamadas)"), self.comunicaciones_salida, hay_dispositivo),
			(_("Activar o desactivar las me&joras de audio de la salida"), self.alternar_mejoras, hay_dispositivo),
			(_("Usar como micrófono pred&eterminado"), self.predeterminar_micro, hay_micro),
			(_("Usar como micrófono de com&unicaciones"), self.comunicaciones_micro, hay_micro),
			(_("Escuc&har este dispositivo (oír el micrófono)"), self.alternar_escucha, hay_micro),
			None,
			(_("Gua&rdar el audio actual como perfil..."), self.guardar_perfil, True),
			(_("Apl&icar un perfil de audio..."), self.aplicar_perfil, True),
			(_("Eliminar un per&fil de audio..."), self.eliminar_perfil, True),
			(_("&Quién usa el micrófono o la cámara"), self.controlador.decir_privacidad, True),
			None,
			(_("Salid&as preferidas al conectar..."), lambda: self.preferencias(False), True),
			(_("&Micrófonos preferidos al conectar..."), lambda: self.preferencias(True), True),
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
