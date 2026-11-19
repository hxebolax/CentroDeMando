"""Pruebas del lanzador (sin abrir programas de verdad)."""

from __future__ import annotations

import pytest
import wx

from app.services import lanzador
from app.services.lanzador import TIPO_ACCION, TIPO_PROGRAMA, CatalogoLanzador, Elemento, calcular, puntuar
from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto


@pytest.mark.parametrize(
	("texto", "esperado"),
	[
		("2+2*3", "8"),
		("15% de 80", "12"),
		("1,5*2", "3"),
		("10 x 3", "30"),
		("7/2", "3,5"),
		("raiz(16)", "4"),
		("=2^3", "8"),
		("42", None),
		("hola", None),
		("1/0", None),
		("2**100000", None),
		("__import__('os').system('x')", None),
		("(1).__class__", None),
	],
)
def test_calculadora_segura(texto, esperado):
	assert calcular(texto) == esperado


def test_puntuacion():
	assert puntuar("bloc de notas", "bloc de notas") == 0
	assert puntuar("bloc", "bloc de notas") == 1
	assert puntuar("not", "bloc de notas") == 2
	assert puntuar("adm disp", "administrador de dispositivos") == 2
	assert puntuar("ad", "administrador de dispositivos") == 1
	assert puntuar("xyz", "bloc de notas") is None
	assert puntuar("altavoz", "sonido", "audio altavoz") == 5


def test_catalogo_busca_y_prioriza_lo_usado(tmp_path):
	programas = [Elemento("programa:a", "Bloc de notas", TIPO_PROGRAMA, "a"), Elemento("programa:b", "Bloquear pantalla", TIPO_PROGRAMA, "b")]
	acciones = [Elemento("accion:crear", "Crear un escritorio", TIPO_ACCION, "crear")]
	catalogo = CatalogoLanzador(acciones, tmp_path / "c.json", lector=lambda: programas)
	catalogo.actualizar_programas(esperar=True)
	assert [e.nombre for e in catalogo.buscar("blo")][:2] == ["Bloc de notas", "Bloquear pantalla"]
	assert catalogo.buscar("blo", {"programa:b": 5})[0].nombre == "Bloquear pantalla", "lo más usado sube"
	assert catalogo.buscar("", {"accion:crear": 2})[0].id == "accion:crear", "sin texto, lo más usado"
	assert catalogo.buscar("wifi")[0].tipo == "Ajuste de Windows"
	assert catalogo.buscar("2+2")[0].destino == "4"
	assert (tmp_path / "c.json").is_file(), "los programas se guardan para la próxima vez"
	assert [e.nombre for e in CatalogoLanzador([], tmp_path / "c.json", lector=list).elementos()][:2] == ["Bloc de notas", "Bloquear pantalla"]


def test_ventana_y_ejecucion(controlador_falso, tmp_path, monkeypatch):
	from app.ui.ventanas_rapidas import LanzadorRapido

	programas = [Elemento("programa:a", "Bloc de notas", TIPO_PROGRAMA, "a")]
	controlador_falso._catalogo_lanzador = None
	catalogo = controlador_falso.catalogo_lanzador
	catalogo._ruta_cache = tmp_path / "c.json"
	catalogo._lector = lambda: programas
	catalogo.actualizar_programas(esperar=True)
	abiertos, ejecutadas = [], []
	monkeypatch.setattr(lanzador, "ejecutar_destino", lambda e: abiertos.append(e.nombre) or True)
	monkeypatch.setattr(controlador_falso, "ejecutar", ejecutadas.append)
	ventana = LanzadorRapido(controlador_falso, 0)
	try:
		afirmar_teclado_correcto(ventana)
		ventana.area.buscar.SetValue("bloc")
		ventana.area._abrir_primero()
	finally:
		if ventana:
			ventana.Destroy()
	assert abiertos == ["Bloc de notas"]
	assert controlador_falso.config.obtener("lanzador.usos") == {"programa:a": 1}
	accion = next(e for e in catalogo.elementos() if e.id == "accion:siguiente")
	controlador_falso.ejecutar_elemento_lanzador(accion)
	assert ejecutadas == ["siguiente"]
	wx.GetApp().ProcessPendingEvents()
