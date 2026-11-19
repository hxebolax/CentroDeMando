"""Pruebas de los fragmentos de texto."""

from __future__ import annotations

import time

import wx

from app.services.fragmentos import AlmacenFragmentos, Fragmento, expandir
from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto


def test_expandir_variables():
	ahora = time.strptime("2026-11-19 10:05", "%Y-%m-%d %H:%M")
	texto, _retroceso = expandir("Hoy es {fecha_larga} ({fecha}, {hora}). {cursor}Fin", ahora)
	assert texto == "Hoy es jueves, 19 de noviembre de 2026 (19/11/2026, 10:05). Fin", "{cursor} ya no se usa: se quita"
	texto, _r = expandir("Copiado: {portapapeles}", ahora, portapapeles=lambda: "hola")
	assert texto == "Copiado: hola"
	assert expandir("sin variables")[0] == "sin variables"


def test_almacen_busqueda_y_persistencia(tmp_path):
	ruta = tmp_path / "f.json"
	almacen = AlmacenFragmentos(ruta)
	assert [f.abreviatura for f in almacen.todos()] == ["fecha", "firma"], "trae ejemplos la primera vez"
	almacen.agregar(Fragmento("Dirección de casa", "Calle Mayor 1", "Personal", "dir"))
	almacen.agregar(Fragmento("Directorio", "Otra cosa", "Trabajo", ""))
	assert almacen.buscar("dir")[0].abreviatura == "dir", "la abreviatura exacta va primero"
	assert [f.nombre for f in almacen.buscar("", "Trabajo")] == ["Directorio"]
	assert [f.nombre for f in almacen.buscar("direccion")] == ["Dirección de casa"], "sin tildes"
	assert almacen.categorias() == ["Ejemplos", "Personal", "Trabajo"]
	recargado = AlmacenFragmentos(ruta)
	assert len(recargado.todos()) == 4
	recargado.anotar_uso(recargado.buscar("dir")[0].id)
	assert AlmacenFragmentos(ruta).buscar("dir")[0].usos == 1


def test_archivo_danado_se_aparta(tmp_path):
	ruta = tmp_path / "f.json"
	ruta.write_text("{esto no es json", encoding="utf-8")
	almacen = AlmacenFragmentos(ruta)
	assert almacen.todos() == []
	assert list(tmp_path.glob("fragmentos.danado-*.json"))


def test_area_y_ventana_rapida(controlador_falso, tmp_path, monkeypatch):
	from app.ui.ventanas_rapidas import FragmentosRapido

	controlador_falso._fragmentos = AlmacenFragmentos(tmp_path / "f.json")
	ventana = FragmentosRapido(controlador_falso, 0)
	insertados = []
	monkeypatch.setattr(controlador_falso, "insertar_fragmento", lambda f, destino: insertados.append(f.abreviatura))
	try:
		afirmar_teclado_correcto(ventana)
		area = ventana.area
		area.buscar.SetValue("firma")
		area._al_intro_buscar(None)
		assert insertados == ["firma"]
	finally:
		if ventana:
			ventana.Destroy()
	wx.GetApp().ProcessPendingEvents()
