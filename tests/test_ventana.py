"""Pruebas de la ventana principal con wx real y escritorios falsos, SIN mostrarla."""

from __future__ import annotations

import pytest
import wx

from app.core.config import Configuracion
from app.core.instancia_unica import ORDEN_MOSTRAR, Orden
from app.core.version import NOMBRE_APLICACION
from app.ui import ventana_principal as vp
from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto

from .conftest import esperar_servicio, procesar_eventos

MENUS_ESPERADOS = ["&Escritorios", "Ve&ntanas", "&Portapapeles", "E&moticonos", "&Ver", "&Herramientas", "Ay&uda"]
ATAJOS_ESPERADOS = {
	"crear": (wx.ACCEL_CTRL, ord("N")),
	"renombrar": (wx.ACCEL_NORMAL, wx.WXK_F2),
	"salir": (wx.ACCEL_CTRL, ord("Q")),
	"actualizar": (wx.ACCEL_NORMAL, wx.WXK_F5),
	"teclas_globales": (wx.ACCEL_CTRL, ord("T")),
	"opciones": (wx.ACCEL_CTRL, ord(",")),
	"manual": (wx.ACCEL_NORMAL, wx.WXK_F1),
	"ayuda_contextual": (wx.ACCEL_CTRL, ord("H")),
}
PALABRAS_EN_INGLES = {
	"file",
	"edit",
	"view",
	"tools",
	"help",
	"open",
	"exit",
	"quit",
	"copy",
	"about",
	"options",
	"refresh",
	"desktop",
	"window",
}


@pytest.fixture
def ventana(controlador_falso, monkeypatch):
	# Sin icono real en la bandeja durante las pruebas.
	monkeypatch.setattr(vp.IconoBandeja, "mostrar", lambda self: True)
	monkeypatch.setattr(vp.IconoBandeja, "IsIconInstalled", lambda self: True)
	marco = vp.VentanaPrincipal(controlador_falso.config, controlador=controlador_falso)
	controlador_falso._notificar_estado(controlador_falso.servicio.estado)
	yield marco
	if marco:
		marco.salir()
		procesar_eventos(lambda: not marco, 2)


def _elementos(menu: wx.Menu):
	for item in menu.GetMenuItems():
		if not item.IsSeparator():
			yield item


def _esperar_pintado(marco, servicio) -> None:
	esperar_servicio(servicio)
	procesar_eventos(segundos=0.2)


def test_arranca_sin_mostrarse_y_pinta_los_escritorios(ventana):
	assert not ventana.IsShown()
	assert ventana.GetTitle().startswith(NOMBRE_APLICACION)
	assert ventana.lista.GetItemCount() == 4
	assert ventana.lista.GetItemText(1, 1) == "Correo"
	assert ventana.lista.GetItemText(0, 3) == "actual"
	assert ventana.lista.GetItemText(2, 1) == "Escritorio 3"


def test_menus_en_espanol_con_teclas_de_acceso(ventana):
	barra = ventana.GetMenuBar()
	assert [barra.GetMenuLabel(i) for i in range(barra.GetMenuCount())] == MENUS_ESPERADOS
	for i in range(barra.GetMenuCount()):
		for item in _elementos(barra.GetMenu(i)):
			palabras = {p.lower().strip(".&") for p in item.GetItemLabelText().split()}
			assert not palabras & PALABRAS_EN_INGLES, f"«{item.GetItemLabel()}» parece estar en inglés"
			assert item.GetHelp(), f"«{item.GetItemLabel()}» no tiene texto de ayuda"


def test_teclado_de_la_ventana_principal(ventana):
	"""Etiquetas, letras de acceso sin repetir ni chocar con los menús y atajos únicos."""
	afirmar_teclado_correcto(ventana, teclas_propias=["Supr", "Escape"])


def test_atajos_de_teclado(ventana):
	for nombre, (modificadores, tecla) in ATAJOS_ESPERADOS.items():
		atajo = ventana.elementos_menu[nombre].GetAccel()
		assert atajo is not None, f"{nombre} no tiene atajo"
		assert (atajo.GetFlags(), atajo.GetKeyCode()) == (modificadores, tecla), nombre


def test_etiquetas_creadas_justo_antes_de_las_listas(ventana):
	hijos = list(ventana.panel.GetChildren())
	for lista, texto in ((ventana.lista, "&Lista de escritorios:"), (ventana.lista_ventanas, "Ven&tanas del escritorio seleccionado:")):
		anterior = hijos[hijos.index(lista) - 1]
		assert isinstance(anterior, wx.StaticText) and anterior.GetLabel() == texto
		assert lista.GetHelpText(), "Ctrl+H necesita la ayuda del control"


def test_ventanas_del_escritorio_seleccionado(ventana, motor_falso, controlador_falso):
	motor_falso.agregar_ventana(10, 1, "Documento", "word.exe")
	motor_falso.agregar_ventana(11, 2, "Bandeja de entrada", "thunderbird.exe")
	motor_falso.agregar_ventana(12, 3, "Reproductor", "musica.exe", anclada=True)
	ventana.refrescar_ventanas()
	_esperar_pintado(ventana, controlador_falso.servicio)
	assert ventana.lista.GetItemText(0, 2) == "1"
	assert ventana.lista.GetItemText(1, 2) == "1"
	titulos = [ventana.lista_ventanas.GetItemText(i, 0) for i in range(ventana.lista_ventanas.GetItemCount())]
	assert titulos == ["Documento", "Reproductor"], "las ancladas se ven en todos"
	assert ventana.lista_ventanas.GetItemText(1, 2) == "Todos"
	ventana.lista.Select(1)
	ventana.lista.Focus(1)
	ventana._pintar_ventanas()
	assert ventana.lista_ventanas.GetItemText(0, 0) == "Bandeja de entrada"


def test_seleccion_se_conserva_al_actualizar(ventana, motor_falso, controlador_falso):
	ventana.lista.Select(2)
	ventana.lista.Focus(2)
	controlador_falso.servicio.renombrar(3, "Música")
	_esperar_pintado(ventana, controlador_falso.servicio)
	assert ventana.lista.GetItemText(2, 1) == "Música"
	assert ventana.lista.GetFocusedItem() == 2
	controlador_falso.servicio.mover_escritorio(3, 1)
	_esperar_pintado(ventana, controlador_falso.servicio)
	assert ventana.lista.GetItemText(0, 1) == "Música"
	assert ventana.lista.GetFocusedItem() == 0, "el foco sigue al escritorio aunque cambie de posición"


def test_intro_cambia_al_escritorio(ventana, motor_falso, controlador_falso):
	ventana.lista.Select(3)
	ventana.lista.Focus(3)
	ventana._al_ir(None)
	_esperar_pintado(ventana, controlador_falso.servicio)
	assert motor_falso.numero_actual() == 4
	assert ventana.lista.GetItemText(3, 3) == "actual"
	assert ventana.lista.GetItemText(0, 3) == ""


def test_eliminar_confirma_y_respeta_el_no(ventana, motor_falso, controlador_falso, monkeypatch):
	respuestas = [wx.ID_NO, wx.ID_YES]
	monkeypatch.setattr(vp, "confirmar", lambda *a, **k: respuestas.pop(0))
	ventana.eliminar(2)
	_esperar_pintado(ventana, controlador_falso.servicio)
	assert motor_falso.total() == 4
	ventana.eliminar(2)
	_esperar_pintado(ventana, controlador_falso.servicio)
	assert motor_falso.total() == 3


def test_renombrar_pide_el_nombre(ventana, motor_falso, controlador_falso, monkeypatch):
	monkeypatch.setattr(vp, "pedir_texto", lambda *a, **k: "  Proyectos  ")
	ventana.renombrar(1)
	_esperar_pintado(ventana, controlador_falso.servicio)
	assert motor_falso.escritorios[0]["nombre"] == "Proyectos"


def test_acciones_globales_desde_el_controlador(ventana, motor_falso, controlador_falso):
	controlador_falso.ejecutar("ultimo")
	controlador_falso.ejecutar("siguiente")  # cíclico: del 4 al 1
	controlador_falso.ejecutar("ir_3")
	controlador_falso.ejecutar("alternar")
	esperar_servicio(controlador_falso.servicio)
	assert motor_falso.cambios == [4, 1, 3, 1]
	controlador_falso.ejecutar("crear")
	esperar_servicio(controlador_falso.servicio)
	assert motor_falso.total() == 5


def test_cerrar_a_bandeja_oculta_y_salir_cierra(ventana, monkeypatch):
	ocultada = []
	monkeypatch.setattr(ventana, "Hide", lambda: ocultada.append(True) or True)
	ventana.Close()  # como Alt+F4: se puede vetar
	procesar_eventos(segundos=0.2)
	assert ventana, "con «cerrar a la bandeja» la ventana sigue viva"
	assert ocultada == [True]
	ventana.salir()
	assert procesar_eventos(lambda: not ventana)


def test_cierre_guarda_la_geometria(controlador_falso, datos_temporales, monkeypatch):
	monkeypatch.setattr(vp.IconoBandeja, "mostrar", lambda self: True)
	config = controlador_falso.config
	marco = vp.VentanaPrincipal(config, controlador=controlador_falso)
	marco.SetSize(wx.Size(640, 480))
	marco._rect_normal = marco.GetRect()
	marco.salir()
	assert procesar_eventos(lambda: not marco), "la ventana debe destruirse"
	guardada = Configuracion()
	assert guardada.obtener("ventana.ancho") == 640
	assert (datos_temporales / "config" / "config.json").is_file()


def test_ordenes_de_otra_instancia(controlador_falso, monkeypatch):
	restauradas = []

	class InstanciaFalsa:
		def recoger_ordenes(self):
			return [Orden(ORDEN_MOSTRAR, [], 1.0)]

	marco = vp.VentanaPrincipal(controlador_falso.config, InstanciaFalsa(), controlador=controlador_falso)
	monkeypatch.setattr(marco, "restaurar", lambda: restauradas.append(True))
	try:
		marco._al_revisar_buzon(None)
		assert restauradas == [True]
	finally:
		marco.salir()
		procesar_eventos(lambda: not marco)


def test_ayuda_contextual_sin_ayuda(ventana, monkeypatch):
	mensajes = []
	monkeypatch.setattr(vp, "mostrar_mensaje", lambda padre, texto, *a, **k: mensajes.append(texto))
	monkeypatch.setattr(wx.Window, "FindFocus", staticmethod(lambda: None))
	ventana._al_ayuda_contextual(None)
	assert mensajes and "F1" in mensajes[0]


def test_actualizar_lista_toca_solo_lo_que_cambia(app_wx):
	marco = wx.Frame(None)
	try:
		lista = wx.ListCtrl(marco, style=wx.LC_REPORT)
		lista.InsertColumn(0, "A")
		lista.InsertColumn(1, "B")
		claves: list = []
		vp.actualizar_lista(lista, [("x", ("1", "uno")), ("y", ("2", "dos"))], claves)
		assert claves == ["x", "y"] and lista.GetItemCount() == 2
		lista.Focus(1)
		lista.Select(1)
		vp.actualizar_lista(lista, [("y", ("2", "DOS")), ("x", ("1", "uno")), ("z", ("3", "tres"))], claves)
		assert lista.GetItemText(0, 1) == "DOS"
		assert lista.GetFocusedItem() == 0, "el elemento enfocado («y») conserva el foco"
		vp.actualizar_lista(lista, [], claves)
		assert lista.GetItemCount() == 0
	finally:
		marco.Destroy()


def _pulsar(lista, tecla: int, control: bool = False, mayusculas: bool = False) -> None:
	evento = wx.KeyEvent(wx.wxEVT_KEY_DOWN)
	evento.SetKeyCode(tecla)
	evento.SetControlDown(control)
	evento.SetShiftDown(mayusculas)
	lista._al_pulsar(evento)


def test_columnas_con_flechas_y_control_numero(ventana):
	from app.ui.accesibilidad import voz as voz_listas

	dichos = voz_listas.dichos_en_prueba
	ventana.lista.enfocar_fila(1, anunciar=False)
	_pulsar(ventana.lista, wx.WXK_RIGHT)
	assert dichos[-1] == "Fila 2, Nombre, Correo"
	_pulsar(ventana.lista, ord("4"), control=True)
	assert dichos[-1] == "Fila 2, Estado, Sin datos"
	_pulsar(ventana.lista, wx.WXK_HOME, control=True, mayusculas=True)
	assert dichos[-1] == "Fila 2, Número, 2"
	# Las preferencias de Opciones se aplican al momento, sin reiniciar.
	ventana._config.establecer("listas.decir_numero_fila", False)
	ventana._config.establecer("listas.decir_cabecera", False)
	_pulsar(ventana.lista, wx.WXK_RIGHT)
	assert dichos[-1] == "Correo"
	ventana._config.establecer("listas.decir_contenido", False)
	_pulsar(ventana.lista, wx.WXK_LEFT)
	assert dichos[-1] == "2", "con las tres desactivadas se dice igualmente el contenido"


def test_texto_de_la_bandeja_sin_repetir_el_nombre():
	from app.services.escritorios import EstadoEscritorios, InfoEscritorio
	from app.ui.bandeja import texto_emergente

	estado = EstadoEscritorios((InfoEscritorio(1, "a"), InfoEscritorio(2, "b", "Trabajo", actual=True)), actual=2)
	assert texto_emergente(estado) == "Escritorio 2: Trabajo"
	estado = EstadoEscritorios((InfoEscritorio(1, "a", actual=True),), actual=1)
	assert texto_emergente(estado) == "Escritorio 1"
	assert NOMBRE_APLICACION not in texto_emergente(estado), "Windows ya antepone el nombre del programa"


def test_cafe_encima_de_acerca_de_y_autor(ventana, monkeypatch):
	from app.ui.acerca_de import texto_acerca_de

	barra = ventana.GetMenuBar()
	ayuda = barra.GetMenu(barra.GetMenuCount() - 1)
	elementos = [i for i in ayuda.GetMenuItems() if not i.IsSeparator()]
	textos = [i.GetItemLabelText() for i in elementos]
	assert textos[-2] == "Invítame a un café si te gusta mi trabajo"
	assert textos[-1].startswith("Acerca de")
	abiertas = []
	import webbrowser

	monkeypatch.setattr(webbrowser, "open", abiertas.append)
	ventana._al_invitar_cafe(None)
	assert abiertas and "paypal.me/hjbcdonaciones" in abiertas[0].replace("paypalme", "paypal.me")
	texto = texto_acerca_de()
	assert "Autor: Héctor J. Benítez Corredera" in texto
	assert "Copyright (C) 2026 Héctor J. Benítez Corredera" in texto
