"""Pruebas del historial del portapapeles, del catálogo de emoticonos y de sus áreas (sin tocar el portapapeles real)."""

from __future__ import annotations

import struct
import time

import pytest
import wx

from app.services.emojis import CatalogoEmojis, anotar_reciente, normalizar
from app.services.portapapeles import FILTRO_FAVORITOS, FILTRO_IMAGENES, HistorialPortapapeles, describir_tiempo
from app.services.portapapeles_win32 import TIPO_ARCHIVOS, TIPO_IMAGEN, Contenido, dib_a_bmp, dimensiones_dib
from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto

from .conftest import RAIZ

# ── Historial ───────────────────────────────────────────────────────────────


@pytest.fixture
def historial(tmp_path):
	h = HistorialPortapapeles(tmp_path / "h.db")
	yield h
	h.cerrar()


def test_historial_sin_duplicados_y_con_orden(historial):
	primero = historial.agregar(Contenido(texto="uno", origen="notepad.exe"))
	historial.agregar(Contenido(texto="dos"))
	time.sleep(0.01)
	repetido = historial.agregar(Contenido(texto="uno"))
	assert repetido.id == primero.id, "lo repetido no se duplica"
	assert [e.texto for e in historial.listar()] == ["uno", "dos"], "lo repetido sube arriba"
	assert historial.listar()[0].veces == 2
	assert historial.listar()[0].origen == "notepad.exe", "se conserva el origen si la copia nueva no lo trae"


def test_limite_respeta_favoritos(historial):
	viejo = historial.agregar(Contenido(texto="favorito antiguo"))
	historial.poner_favorito(viejo.id, True)
	for numero in range(5):
		time.sleep(0.002)
		historial.agregar(Contenido(texto=f"texto {numero}"), maximo=3)
	textos = [e.texto for e in historial.listar()]
	assert len(textos) == 3
	assert "favorito antiguo" in textos, "los favoritos no se pierden por el límite"
	assert [e.texto for e in historial.listar(FILTRO_FAVORITOS)] == ["favorito antiguo"]


def test_busqueda_filtros_nombre_y_vaciar(historial):
	historial.agregar(Contenido(texto="Informe de ventas 100%"))
	historial.agregar(Contenido(TIPO_ARCHIVOS, texto="C:\\a.txt", archivos=["C:\\a.txt"]))
	imagen = struct.pack("<IiiHHIIiiII", 40, 640, -480, 1, 32, 0, 0, 0, 0, 0, 0) + b"\0" * 16
	elemento = historial.agregar(Contenido(TIPO_IMAGEN, imagen=imagen))
	assert [e.texto for e in historial.listar(buscar="VENTAS")] == ["Informe de ventas 100%"]
	assert len(historial.listar(buscar="100%")) == 1, "el % se busca literal"
	assert historial.listar(buscar="10_") == [], "el _ también"
	assert [e.id for e in historial.listar(FILTRO_IMAGENES)] == [elemento.id]
	assert historial.listar(FILTRO_IMAGENES)[0].resumen() == "Imagen de 640 por 480"
	assert historial.obtener(elemento.id).imagen == imagen, "la imagen solo viene al pedirla completa"
	assert historial.listar(FILTRO_IMAGENES)[0].imagen == b""
	historial.renombrar(elemento.id, "Captura")
	assert historial.obtener(elemento.id).resumen() == "Captura"
	historial.poner_favorito(elemento.id, True)
	assert historial.vaciar() == 2
	assert historial.contar() == 1


def test_archivos_y_resumenes(historial):
	elemento = historial.agregar(Contenido(TIPO_ARCHIVOS, archivos=["C:\\x\\uno.txt", "C:\\x\\dos.txt"]))
	assert elemento.resumen() == "2 archivos: uno.txt, dos.txt"
	assert elemento.archivos == ["C:\\x\\uno.txt", "C:\\x\\dos.txt"]
	texto = historial.agregar(Contenido(texto="línea 1\nlínea 2"))
	assert texto.descripcion_tipo() == "Texto, 15 caracteres, 2 líneas"


def test_base_danada_se_aparta(tmp_path):
	ruta = tmp_path / "h.db"
	ruta.write_bytes(b"esto no es una base de datos" * 100)
	historial = HistorialPortapapeles(ruta)
	try:
		historial.agregar(Contenido(texto="sigue funcionando"))
		assert historial.contar() == 1
		assert list(tmp_path.glob("h.danado-*.db"))
	finally:
		historial.cerrar()


def test_dib_y_tiempos():
	cabecera = struct.pack("<IiiHHIIiiII", 40, 3, -2, 1, 24, 0, 0, 0, 0, 0, 0)
	assert dimensiones_dib(cabecera) == (3, 2)
	assert dib_a_bmp(cabecera)[:2] == b"BM"
	assert describir_tiempo(1000, 1030) == "hace un momento"
	assert describir_tiempo(1000, 1000 + 5 * 60) == "hace 5 minutos"


def test_huella_distingue_tipos():
	assert Contenido(texto="a").huella() == Contenido(texto="a", html=b"<b>a</b>").huella(), "el HTML no cambia lo copiado"
	assert Contenido(texto="a").huella() != Contenido(TIPO_ARCHIVOS, archivos=["a"]).huella()


# ── Emoticonos ──────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def catalogo():
	return CatalogoEmojis(RAIZ / "data" / "emojis" / "emojis_es.json")


def test_catalogo_completo_en_espanol(catalogo):
	assert catalogo.error == ""
	assert catalogo.grupos[0] == "Caras y emociones"
	assert catalogo.grupos[-2:] == ["Símbolos tipográficos", "Kaomoji"]
	assert catalogo.obtener("😀").nombre == "cara sonriendo"
	assert len(catalogo.del_grupo("Caras y emociones")) > 150


def test_busqueda_sin_tildes_y_por_palabras(catalogo):
	assert catalogo.buscar("corazon rojo")[0].caracter == "❤️"
	assert catalogo.buscar("cara sonriendo")[0].caracter == "😀", "primero la coincidencia exacta"
	assert any(e.caracter == "🧑\u200d💻" for e in catalogo.buscar("programador")), "busca en las palabras clave"
	assert catalogo.buscar("   ") == []
	assert not any(e.base for e in catalogo.buscar("mano")), "sin variantes de tono salvo que se pidan"
	assert any(e.grupo == "Kaomoji" for e in catalogo.buscar("encogerse"))
	assert catalogo.buscar("euro")[0].grupo in ("Símbolos tipográficos", "Símbolos")


def test_tonos_de_piel(catalogo):
	assert catalogo.con_tono("👋", 3) == "👋🏽"
	assert catalogo.con_tono("☝️", 1) == "☝🏻", "funciona aunque el emoji base lleve selector de variación"
	assert catalogo.con_tono("😀", 3) == "😀", "sin variante se queda igual"
	assert catalogo.con_tono("👋", 0) == "👋"
	assert catalogo.admite_tono("👍") and not catalogo.admite_tono("😀")


def test_recientes_y_normalizar():
	assert anotar_reciente(["a", "b", "c"], "b", 3) == ["b", "a", "c"]
	assert anotar_reciente(["a", "b", "c"], "d", 3) == ["d", "a", "b"]
	assert normalizar("Corazón ROJO") == "corazon rojo"


def test_datos_incluyen_licencia():
	assert (RAIZ / "data" / "emojis" / "LICENCIA_UNICODE.txt").is_file()


# ── Áreas (interfaz sin mostrar) ────────────────────────────────────────────


def _pulsar(control, tecla: int, mayusculas: bool = False, control_pulsado: bool = False) -> wx.KeyEvent:
	evento = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
	evento.SetKeyCode(tecla)
	evento.SetShiftDown(mayusculas)
	evento.SetControlDown(control_pulsado)
	return evento


def test_area_emoticonos(controlador_falso, monkeypatch):
	from app.ui.area_emoticonos import AreaEmoticonos

	marco = wx.Frame(None)
	insertados = []
	try:
		area = AreaEmoticonos(marco, controlador_falso, insertados.append)
		afirmar_teclado_correcto(marco)
		area.buscar.SetValue("mano saludando")
		area.refrescar()
		assert area.lista.texto_celda(0, 0) == "mano saludando"
		area.tono.SetSelection(3)
		area.lista.enfocar_fila(0, anunciar=False)
		area.insertar()
		assert insertados == ["👋🏽"]
		assert controlador_falso.config.obtener("emoticonos.recientes")[0] == "👋", "se recuerda el emoji base"
		monkeypatch.setattr(wx.Window, "FindFocus", staticmethod(lambda: area.lista))
		assert area.manejar_tecla(_pulsar(area.lista, wx.WXK_F4))
		assert controlador_falso.config.obtener("emoticonos.favoritos") == ["👋"]
		assert area.manejar_tecla(_pulsar(area.lista, wx.WXK_RETURN, control_pulsado=True))
		assert area.manejar_tecla(_pulsar(area.lista, wx.WXK_RETURN, control_pulsado=True))
		assert area.texto.GetValue() == "👋🏽👋🏽"
		area.insertar()
		assert insertados[-1] == "👋🏽👋🏽", "con texto acumulado, Intro inserta todo"
		assert area.texto.GetValue() == ""
		area.buscar.SetValue("")
		area.grupo.SetSelection(1)  # favoritos
		area.refrescar()
		assert area.lista.numero_filas() == 1
	finally:
		marco.Destroy()


def test_area_portapapeles(controlador_falso, monkeypatch, tmp_path):
	from app.ui.area_portapapeles import AreaPortapapeles

	controlador_falso.portapapeles._historial = HistorialPortapapeles(tmp_path / "p.db")
	historial = controlador_falso.portapapeles.historial
	historial.agregar(Contenido(texto="primero"))
	time.sleep(0.01)
	historial.agregar(Contenido(texto="segundo\ncon dos líneas"))
	marco = wx.Frame(None)
	pegados = []
	try:
		area = AreaPortapapeles(marco, controlador_falso, lambda identificador, transformacion=None: pegados.append(identificador))
		afirmar_teclado_correcto(marco)
		area.refrescar()
		assert area.lista.texto_celda(0, 0) == "segundo con dos líneas"
		area.lista.enfocar_fila(0, anunciar=False)
		area._mostrar_contenido()
		assert area.contenido.GetValue() == "segundo\ncon dos líneas", "la vista previa enseña el texto completo"
		area.pegar()
		assert pegados == [historial.listar()[0].id]
		monkeypatch.setattr(wx.Window, "FindFocus", staticmethod(lambda: area.lista))
		assert area.manejar_tecla(_pulsar(area.lista, wx.WXK_F4))
		assert area.lista.texto_celda(0, 4) == "sí"
		assert area.manejar_tecla(_pulsar(area.lista, wx.WXK_DELETE))
		assert historial.contar() == 1
		area.buscar.SetValue("nada parecido")
		area.refrescar()
		assert area.lista.numero_filas() == 0
	finally:
		marco.Destroy()
		historial.cerrar()


@pytest.mark.parametrize("clase", ["PortapapelesRapido", "EmoticonosRapido"])
def test_ventanas_rapidas_accesibles(controlador_falso, tmp_path, clase):
	from app.ui import ventanas_rapidas

	controlador_falso.portapapeles._historial = HistorialPortapapeles(tmp_path / "p.db")
	ventana = getattr(ventanas_rapidas, clase)(controlador_falso, 0)
	try:
		afirmar_teclado_correcto(ventana)
	finally:
		ventana.Destroy()
		controlador_falso.portapapeles.historial.cerrar()


def test_transformaciones_al_pegar():
	from app.services.portapapeles import TRANSFORMACIONES

	texto = "  hola MUNDO  \n  segunda línea "
	assert TRANSFORMACIONES["una_linea"][1](texto) == "hola MUNDO segunda línea"
	assert TRANSFORMACIONES["recortar"][1](texto) == "hola MUNDO\nsegunda línea"
	assert TRANSFORMACIONES["mayusculas"][1]("año") == "AÑO"
	assert TRANSFORMACIONES["titulo"][1]("el ÁRBOL verde") == "El Árbol Verde"
	assert TRANSFORMACIONES["frase"][1]("HOLA mundo") == "Hola mundo"
	assert TRANSFORMACIONES["sin_formato"][1](texto) == texto
