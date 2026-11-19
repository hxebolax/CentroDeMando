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
	finally:
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
		)
		for indice, esperado in casos:
			marco.libro.SetSelection(indice)
			marco.reconstruir_menu_accion()
			assert etiquetas()[0].startswith(esperado), etiquetas()[0]
			afirmar_teclado_correcto(marco, teclas_propias=["Supr", "Escape"])
	finally:
		marco.area_sistema._temporizador.Stop()
		marco.salir()
		procesar_eventos(lambda: not marco, 2)
