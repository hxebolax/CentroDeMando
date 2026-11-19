"""Pruebas de temporizadores y alarmas."""

from __future__ import annotations

import time

import wx

from app.services import temporizadores as t
from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto


def test_textos_y_horas():
	assert t.describir_duracion(3725) == "1 hora, 2 minutos y 5 segundos"
	assert t.describir_duracion(60) == "1 minuto"
	assert t.describir_duracion(0) == "0 segundos"
	assert t.analizar_hora("7:30") == (7, 30)
	assert t.analizar_hora("19.05") == (19, 5)
	assert t.analizar_hora("7") == (7, 0)
	assert t.analizar_hora("25:00") is None and t.analizar_hora("hola") is None
	ahora = time.mktime((2026, 11, 19, 10, 0, 0, 0, 0, -1))
	assert time.localtime(t.proxima_hora(11, 0, ahora)).tm_mday == 19
	assert time.localtime(t.proxima_hora(9, 0, ahora)).tm_mday == 20, "si ya pasó, mañana"


def test_vencer_pausar_posponer_y_diaria(tmp_path):
	servicio = t.ServicioTemporizadores(tmp_path / "t.json")
	temporizador = servicio.nuevo_temporizador(60, "Pan")
	alarma = servicio.nueva_alarma(8, 0, "Pastilla", diaria=True)
	assert servicio.pausar(temporizador.id) is True
	assert servicio.revisar(time.time() + 3600) == [] or all(v.id != temporizador.id for v in servicio.revisar(time.time() + 3600)), "pausado no suena"
	assert servicio.pausar(temporizador.id) is False
	vencidos = servicio.revisar(time.time() + 2 * 86400)
	assert {v.nombre for v in vencidos} == {"Pan", "Pastilla"}
	guardado = {x.id: x for x in t.ServicioTemporizadores(tmp_path / "t.json").todos()}
	assert not guardado[temporizador.id].activo, "el temporizador queda terminado"
	assert guardado[alarma.id].activo and guardado[alarma.id].vence > time.time(), "la diaria se reprograma"
	servicio.posponer(temporizador.id, 5)
	assert servicio.todos()[0].activo
	servicio.eliminar(temporizador.id)
	assert all(x.id != temporizador.id for x in servicio.todos())


def test_area_y_dialogos(controlador_falso, tmp_path):
	from app.ui.area_temporizadores import AreaTemporizadores, DialogoAlarma, DialogoAviso, DialogoTemporizador

	controlador_falso._temporizadores = t.ServicioTemporizadores(tmp_path / "t.json")
	controlador_falso.temporizadores.nuevo_temporizador(90, "Té")
	marco = wx.Frame(None)
	try:
		area = AreaTemporizadores(marco, controlador_falso)
		area.refrescar()
		afirmar_teclado_correcto(marco)
		assert area.lista.texto_celda(0, 0) == "Té"
		assert area.lista.texto_celda(0, 3).startswith("1 minuto y")
		for clase in (DialogoTemporizador, DialogoAlarma):
			dialogo = clase(marco)
			afirmar_teclado_correcto(dialogo)
			dialogo.Destroy()
		aviso = DialogoAviso(controlador_falso, controlador_falso.temporizadores.todos()[0])
		afirmar_teclado_correcto(aviso)
		aviso.cerrar()
	finally:
		area._reloj.Stop()
		marco.Destroy()
