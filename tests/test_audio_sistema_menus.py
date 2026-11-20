"""Pruebas de las áreas de audio y sistema y del menú Acción (sin tocar el audio real)."""

from __future__ import annotations

import pytest
import wx

from app.services import audio, equipo
from app.ui import ventana_principal as vp
from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto

from .conftest import procesar_eventos


@pytest.fixture
def audio_falso(monkeypatch):
	estado = {"pred": "b", "vol": 40, "sesiones": {"s1": [50, False]}}
	monkeypatch.setattr(
		audio,
		"dispositivos_salida",
		lambda: [audio.Dispositivo(i, n, i == estado["pred"]) for i, n in (("a", "Altavoces"), ("b", "Auriculares"))],
	)
	monkeypatch.setattr(audio, "volumen_general", lambda: (estado["vol"], False))
	monkeypatch.setattr(audio, "poner_predeterminado", lambda d: estado.__setitem__("pred", d.id))
	monkeypatch.setattr(audio, "sesiones", lambda: [audio.Sesion(k, "musica.exe", 1, v, m) for k, (v, m) in estado["sesiones"].items()])

	def cambiar(clave, paso):
		estado["sesiones"][clave][0] += paso
		return estado["sesiones"][clave][0]

	monkeypatch.setattr(audio, "cambiar_volumen_sesion", cambiar)
	monkeypatch.setattr(audio, "poner_volumen_sesion", lambda clave, v: estado["sesiones"][clave].__setitem__(0, v) or v)
	monkeypatch.setattr(audio, "poner_silencio_sesion", lambda clave, s: estado["sesiones"][clave].__setitem__(1, s) or s)
	monkeypatch.setattr(audio, "poner_silencio_general", lambda s: estado.__setitem__("silencio", s) or s)
	estado["micros"] = {"m1": [70, False, False, ""]}
	monkeypatch.setattr(audio, "dispositivos_entrada", lambda: [audio.Dispositivo("m1", "Micrófono USB", True)])
	monkeypatch.setattr(audio, "volumen_entrada", lambda i=None: tuple(estado["micros"][i or "m1"][:2]))
	monkeypatch.setattr(audio, "leer_escucha", lambda i: tuple(estado["micros"][i][2:]))
	monkeypatch.setattr(audio, "poner_volumen_entrada", lambda v, i=None: estado["micros"][i].__setitem__(0, v) or v)
	monkeypatch.setattr(audio, "poner_silencio_entrada", lambda s, i=None: estado["micros"][i].__setitem__(1, s) or s)

	def escuchar(i, activar, destino=None):
		estado["micros"][i][2] = activar
		if destino is not None:
			estado["micros"][i][3] = destino

	monkeypatch.setattr(audio, "poner_escucha", escuchar)
	estado["balance"] = 0
	from app.services import topologia

	class ControlFalso:
		nivel = 0.0

		def GetLevel(self, _canal):
			return self.nivel

		def SetLevelUniform(self, nivel, _contexto):
			self.nivel = float(getattr(nivel, "value", nivel))

	control = ControlFalso()
	estado["amplificacion"] = control
	monkeypatch.setattr(
		topologia, "buscar_amplificaciones", lambda i: [topologia.Amplificacion("Amplificación de micrófono", 0.0, 30.0, 10.0, 0.0, control)]
	)
	monkeypatch.setattr(audio, "balance_general", lambda: estado["balance"])
	monkeypatch.setattr(audio, "poner_balance_general", lambda b: estado.__setitem__("balance", b) or b)
	return estado


def test_area_audio(controlador_falso, audio_falso, monkeypatch):
	from app.ui.area_audio import AreaAudio

	marco = wx.Frame(None)
	try:
		area = AreaAudio(marco, controlador_falso)
		area.refrescar()
		afirmar_teclado_correcto(marco)
		assert area.dispositivos.texto_celda(1, 1) == "predeterminado"
		assert area.volumen.GetValue() == 40
		area.dispositivos.enfocar_fila(0, anunciar=False)
		area.predeterminar()
		assert audio_falso["pred"] == "a"
		area.sesiones.enfocar_fila(0, anunciar=False)
		monkeypatch.setattr(wx.Window, "FindFocus", staticmethod(lambda: area.sesiones))
		evento = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
		evento.SetKeyCode(wx.WXK_NUMPAD_ADD)
		assert area.manejar_tecla(evento)
		assert audio_falso["sesiones"]["s1"][0] == 55
		assert area.acciones()[0][2] is True
		# Deslizador y casilla de la aplicación seleccionada.
		area.refrescar()
		assert area.volumen_app.IsEnabled() and area.volumen_app.GetValue() == 55
		area.volumen_app.SetValue(20)
		area._al_mover_volumen_app(wx.CommandEvent())
		assert audio_falso["sesiones"]["s1"][0] == 20
		area.silencio_app.SetValue(True)
		area._al_silencio_app(wx.CommandEvent())
		assert audio_falso["sesiones"]["s1"][1] is True
		area.silencio_general.SetValue(True)
		area._al_silencio_general(wx.CommandEvent())
		assert audio_falso["silencio"] is True
		# Micrófono: volumen, silencio y escuchar por la segunda salida.
		assert area.volumen_micro.GetValue() == 70
		area.volumen_micro.SetValue(35)
		area._al_mover_volumen_micro(wx.CommandEvent())
		area.silencio_micro.SetValue(True)
		area._al_silencio_micro(wx.CommandEvent())
		area.escuchar_por.SetSelection(2)
		area.escuchar.SetValue(True)
		evento = wx.CommandEvent(wx.wxEVT_CHECKBOX, area.escuchar.GetId())
		evento.SetEventObject(area.escuchar)
		area._al_escuchar(evento)
		assert audio_falso["micros"]["m1"] == [35, True, True, "b"]
		area.alternar_escucha()
		assert audio_falso["micros"]["m1"][2] is False
		# Balance.
		assert area.balance.IsEnabled()
		area.balance.SetValue(-30)
		area._al_mover_balance(wx.CommandEvent())
		assert audio_falso["balance"] == -30
		etiquetas = [e[0] for e in area.acciones() if e]
		limpias = [e.replace("&", "") for e in etiquetas]
		assert any("perfil" in e for e in limpias) and any("comunicaciones" in e for e in limpias)
		letras = [e[e.index("&") + 1].lower() for e in etiquetas if "&" in e]
		assert len(letras) == len(set(letras)), letras
		assert all("&" in e for e in etiquetas), etiquetas
		# Amplificación del micrófono: 0, +10, +20 y +30 dB.
		area.refrescar()
		assert area.amplificacion.IsEnabled() and area.amplificacion.GetCount() == 4
		area.amplificacion.SetSelection(2)
		area._al_amplificacion(wx.CommandEvent())
		assert audio_falso["amplificacion"].nivel == 20.0
		# Volumen máximo: el deslizador no pasa del límite.
		controlador_falso.poner_limite_volumen("musica.exe", 30)
		area.refrescar()
		assert "máximo 30 %" in area.sesiones.texto_celda(0, 2)
		area.volumen_app.SetValue(90)
		area._al_mover_volumen_app(wx.CommandEvent())
		assert audio_falso["sesiones"]["s1"][0] == 30
		controlador_falso.poner_limite_volumen("musica.exe", None)
		# Ocultar la aplicación y volver a verla.
		area.sesiones.enfocar_fila(0, anunciar=False)
		area.ocultar_aplicacion()
		assert area.sesiones.numero_filas() == 0
		area.alternar_ocultas()
		assert area.sesiones.numero_filas() == 1
	finally:
		area._temporizador.Stop()
		marco.Destroy()


def test_area_sistema(controlador_falso, monkeypatch):
	from app.ui.area_sistema import AreaSistema

	monkeypatch.setattr(equipo, "estado", lambda: [equipo.Dato("Batería", "80 %"), equipo.Dato("Procesador", "5 % en uso")])
	marco = wx.Frame(None)
	try:
		area = AreaSistema(marco, controlador_falso)
		area.refrescar()
		afirmar_teclado_correcto(marco)
		assert area.lista.texto_celda(0, 1) == "80 %"
		assert any(e and e[0].startswith("&Bloquear") for e in area.acciones())
	finally:
		area._temporizador.Stop()
		marco.Destroy()


def test_duraciones_y_tamanos():
	assert equipo._duracion(59) == "0 minutos"
	assert equipo._duracion(90061) == "1 día, 1 hora y 1 minuto"
	assert equipo._tamano(1536) == "1,5 KB"


def test_menu_accion_cambia_con_el_area(controlador_falso, audio_falso, monkeypatch):
	monkeypatch.setattr(vp.IconoBandeja, "mostrar", lambda self: True)
	monkeypatch.setattr(equipo, "estado", lambda: [equipo.Dato("Procesador", "5 %")])
	marco = vp.VentanaPrincipal(controlador_falso.config, controlador=controlador_falso)
	try:
		barra = marco.GetMenuBar()
		assert barra.GetMenuLabel(1) == "A&cción"
		etiquetas = lambda: [i.GetItemLabelText() for i in barra.GetMenu(1).GetMenuItems() if not i.IsSeparator()]  # noqa: E731
		assert etiquetas()[0].startswith("Ir al escritorio seleccionado")
		casos = (
			(1, "Pegar en la ventana anterior"),
			(2, "Insertar en la ventana anterior"),
			(3, "Insertar en la ventana anterior"),
			(4, "Abrir la aplicación que la envió"),
			(5, "Usar como salida predeterminada"),
			(6, "Bloquear el equipo"),
			(7, "Activar la ventana"),
			(8, "Nuevo temporizador"),
		)
		for indice, esperado in casos:
			marco.libro.SetSelection(indice)
			marco.reconstruir_menu_accion()
			assert etiquetas()[0].startswith(esperado), etiquetas()[0]
			afirmar_teclado_correcto(marco, teclas_propias=["Supr", "Escape"])
	finally:
		marco.area_sistema._temporizador.Stop()
		marco.area_procesos._temporizador.Stop()
		marco.area_temporizadores._reloj.Stop()
		marco.salir()
		procesar_eventos(lambda: not marco, 2)


def test_sesiones_de_la_ventana_enfocada(monkeypatch):
	"""Firefox suena desde un hijo con su mismo nombre; el Explorador no se queda con el sonido de lo que abrió."""
	import psutil

	sesiones = [
		audio.Sesion("f", "firefox.exe", 501, 80, False),
		audio.Sesion("t", "thunderbird.exe", 900, 100, False),
		audio.Sesion("w", "msedgewebview2.exe", 701, 50, False),
	]
	monkeypatch.setattr(audio, "sesiones", lambda: sesiones)

	class Falso:
		def __init__(self, pid, nombre, hijos=()):
			self.pid, self._nombre, self._hijos = pid, nombre, hijos

		def name(self):
			return self._nombre

		def children(self, recursive=False):
			return list(self._hijos)

	procesos_falsos = {
		500: Falso(500, "firefox.exe", [Falso(501, "firefox.exe")]),
		1: Falso(1, "explorer.exe", [Falso(900, "thunderbird.exe")]),
		700: Falso(700, "ms-teams.exe", [Falso(701, "msedgewebview2.exe")]),
	}
	monkeypatch.setattr(psutil, "Process", lambda pid: procesos_falsos[pid])
	for hwnd, pid, esperado in ((10, 500, ["f"]), (11, 1, []), (12, 700, ["w"])):
		monkeypatch.setattr(audio, "_pid_real", lambda h, p=pid: p)
		assert [s.clave for s in audio.sesiones_de_ventana(hwnd)] == esperado


def test_solo_esta_aplicacion_nunca_silencia_el_lector(monkeypatch):
	silencio: dict[str, bool] = {}

	class Simple:
		def __init__(self, clave):
			self.clave = clave

		def SetMute(self, valor, _contexto):  # noqa: N802 - API de pycaw
			silencio[self.clave] = valor

	class SesionCom:
		def __init__(self, clave):
			self.SimpleAudioVolume = Simple(clave)

	lista = [
		audio.Sesion("f", "firefox.exe", 1, 100, False),
		audio.Sesion("n", "nvda.exe", 2, 100, False),
		audio.Sesion("t", "thunderbird.exe", 3, 100, False),
		audio.Sesion("x", "musica.exe", 4, 100, True),
	]
	monkeypatch.setattr(audio, "sesiones", lambda: lista)
	monkeypatch.setattr(audio, "_sesion", lambda clave: SesionCom(clave))
	monkeypatch.setattr(audio, "_silenciadas_por_solo", [])
	mensaje = audio.solo_estas({"f"}, "firefox")
	assert silencio == {"t": True}, "ni la propia, ni el lector, ni la que ya estaba silenciada"
	assert "firefox" in mensaje
	audio.solo_estas({"f"}, "firefox")
	assert silencio == {"t": False}, "la segunda vez se restaura lo que se silenció"
