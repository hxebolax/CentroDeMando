"""Pruebas de los diálogos y la bandeja (se crean sin mostrarse; nunca ShowModal)."""

from __future__ import annotations

import sys
import types

import wx

from app.core.config import Configuracion
from app.core.version import APP_VERSION, NOMBRE_APLICACION
from app.ui.acerca_de import texto_acerca_de
from app.ui.bandeja import IconoBandeja
from app.ui.dialogo_opciones import DialogoOpciones
from app.ui import dialogo_texto
from app.ui.dialogo_texto import DialogoTexto
from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto


def _botones(ventana: wx.Window) -> dict[int, str]:
	return {hijo.GetId(): hijo.GetLabel() for hijo in ventana.GetChildren() if isinstance(hijo, wx.Button)}


def test_dialogo_texto_accesible(app_wx):
	dialogo = DialogoTexto(None, "Título", "&Contenido:", "línea 1\nlínea 2", copiable=True)
	try:
		campo = dialogo.campo
		assert campo.IsMultiLine() and not campo.IsEditable(), "texto largo: multilínea de solo lectura"
		hijos = list(dialogo.GetChildren())
		anterior = hijos[hijos.index(campo) - 1]
		assert isinstance(anterior, wx.StaticText) and anterior.GetLabel() == "&Contenido:"
		botones = _botones(dialogo)
		assert botones[wx.ID_CANCEL] == "C&errar"
		assert "Co&piar al portapapeles" in botones.values()
		assert dialogo.GetEscapeId() == wx.ID_CANCEL
		assert campo.GetInsertionPoint() == 0
	finally:
		dialogo.Destroy()


def test_dialogo_opciones_guarda(app_wx, datos_temporales, monkeypatch):
	from app.ui import dialogo_opciones

	monkeypatch.setattr(dialogo_opciones.sistema, "inicio_automatico_activo", lambda nombre: False)
	config = Configuracion()
	avisos = []
	dialogo = DialogoOpciones(None, config, lambda: avisos.append(True))
	try:
		botones = _botones(dialogo)
		assert botones[wx.ID_OK] == "&Aceptar"
		assert botones[wx.ID_CANCEL] == "&Cancelar"
		for control in dialogo.controles.values():
			assert control.GetHelpText()
		afirmar_teclado_correcto(dialogo)
		dialogo.controles["general.minimizar_a_bandeja"].SetValue(False)
		dialogo.controles["anuncios.retraso_ms"].SetValue(300)
		dialogo.aplicar()
	finally:
		dialogo.Destroy()
	guardada = Configuracion()
	assert guardada.obtener("general.minimizar_a_bandeja") is False
	assert guardada.obtener("anuncios.retraso_ms") == 300
	assert avisos == [True], "la aplicación abierta se entera del cambio"


def test_texto_acerca_de():
	texto = texto_acerca_de()
	assert NOMBRE_APLICACION in texto and APP_VERSION in texto
	assert "Carpeta de datos" in texto


def test_menu_de_bandeja_con_escritorios(app_wx):
	from app.services.escritorios import EstadoEscritorios, InfoEscritorio

	llamadas = []
	estado = EstadoEscritorios((InfoEscritorio(1, "a"), InfoEscritorio(2, "b", "Correo & más", actual=True)), actual=2)
	icono = IconoBandeja(
		"Prueba",
		lambda: llamadas.append("restaurar"),
		lambda: llamadas.append("salir"),
		al_accion=llamadas.append,
		obtener_estado=lambda: estado,
	)
	try:
		menu = icono.CreatePopupMenu()
		elementos = [item for item in menu.GetMenuItems() if not item.IsSeparator()]
		etiquetas = [item.GetItemLabel() for item in elementos]
		assert etiquetas[0] == "&Mostrar el gestor"
		assert etiquetas[1:3] == ["&1. Escritorio 1", "&2. Correo && más"], "el & del nombre se dobla"
		assert elementos[2].IsChecked() and not elementos[1].IsChecked(), "el escritorio actual va marcado"
		assert etiquetas[-1] == "&Salir"
		letras = [e[e.index("&") + 1].lower() for e in etiquetas]
		assert len(letras) == len(set(letras)), f"letras repetidas en el menú de la bandeja: {letras}"
		menu.Destroy()
		icono._restaurar()
		assert llamadas == ["restaurar"]
	finally:
		icono.quitar()


def test_dialogo_teclas(app_wx, datos_temporales):
	from app.services import acciones
	from app.services.teclas import ResultadoRegistro
	from app.ui.dialogo_teclas import DialogoEditarAtajo, DialogoTeclas

	class ControladorFalso:
		ultimo_registro = ResultadoRegistro({"siguiente": "Ctrl+Alt+Win+Derecha"}, {"anterior": "Windows u otro programa ya usa «x»."})
		aplicadas = 0

		def aplicar_teclas(self):
			self.aplicadas += 1
			return ResultadoRegistro({}, {})

	controlador = ControladorFalso()
	config = Configuracion()
	dialogo = DialogoTeclas(None, config, controlador)
	try:
		afirmar_teclado_correcto(dialogo, teclas_propias=["Supr"])
		ids = [a.id for a in acciones.ACCIONES]
		assert dialogo.lista.GetItemCount() == len(ids)
		indice = ids.index("siguiente")
		assert dialogo.lista.GetItemText(indice, 2) == "Activa"
		indice_anterior = ids.index("anterior")
		assert "ya usa" in dialogo.lista.GetItemText(indice_anterior, 2)
		assert dialogo.asignar(indice, "Ctrl+Alt+Win+X")
		dialogo.lista.Select(indice_anterior)
		dialogo.quitar()
		dialogo.guardar()
	finally:
		dialogo.Destroy()
	guardadas = Configuracion().obtener("teclas")
	assert guardadas == {"siguiente": "Ctrl+Alt+Win+X", "anterior": ""}, "solo se guarda lo que difiere de fábrica"
	assert controlador.aplicadas == 1

	editor = DialogoEditarAtajo(None, "Prueba", "Ctrl+Alt+Win+Derecha")
	try:
		afirmar_teclado_correcto(editor)
		assert editor.atajo() == "Ctrl+Alt+Win+Derecha"
		editor.casillas[8].SetValue(False)  # sin Win
		assert editor.atajo() == "Ctrl+Alt+Derecha"
		editor.tecla.SetSelection(0)
		assert editor.atajo() == ""
	finally:
		editor.Destroy()


def test_dialogos_de_reglas(app_wx):
	from app.services.reglas import Regla
	from app.ui.dialogo_reglas import DialogoRegla, DialogoReglas

	reglas = [Regla(nombre="Correo", proceso="thunderbird.exe", escritorio="2"), Regla(proceso="x.exe", anclar=True)]
	dialogo = DialogoReglas(None, reglas, ["thunderbird.exe"], ["1", "Correo"])
	try:
		afirmar_teclado_correcto(dialogo, teclas_propias=["Supr"])
		assert dialogo.lista.GetItemCount() == 2
		dialogo.lista.Select(1)
		dialogo.mover(-1)
		assert [r.proceso for r in dialogo.reglas] == ["x.exe", "thunderbird.exe"]
		assert reglas[0].proceso == "thunderbird.exe", "la lista original no se toca hasta Aceptar"
	finally:
		dialogo.Destroy()
	editor = DialogoRegla(None, reglas[0], ["thunderbird.exe"], ["1", "Correo"])
	try:
		afirmar_teclado_correcto(editor)
		assert editor.regla() == reglas[0]
	finally:
		editor.Destroy()


def test_selector_filtra_y_elige(app_wx):
	from app.ui.selector import DialogoSelector, filtrar

	elementos = [("1. Escritorio 1", 1), ("2. Correo", 2), ("3. Correo personal", 3)]
	assert [v for _t, v in filtrar(elementos, "correo per")] == [3]
	assert filtrar(elementos, "") == elementos
	elegidos = []
	selector = DialogoSelector("Ir", "&Escritorios:", elementos, elegidos.append, seleccion_inicial=1)
	afirmar_teclado_correcto(selector)
	assert selector.lista.GetSelection() == 1
	selector.filtro.SetValue("personal")
	assert selector.lista.GetCount() == 1
	selector._al_elegir_evento(None)
	assert elegidos == [3]


def _capturar_message_dialog(monkeypatch) -> list[tuple[str, str, str]]:
	"""Sustituye ``ShowModal`` de ``wx.MessageDialog``: anota título, mensaje y botón."""
	vistos: list[tuple[str, str, str]] = []

	def mostrar(dialogo):
		vistos.append((dialogo.GetTitle(), dialogo.GetMessage(), dialogo.GetOKLabel()))
		return wx.ID_OK

	monkeypatch.setattr(wx.MessageDialog, "ShowModal", mostrar)
	return vistos


def test_mensajes_con_boton_en_espanol(app_wx, monkeypatch):
	"""Los mensajes usan los diálogos accesibles del proyecto, con «Aceptar» en español."""
	from app.ui.accesibilidad import dialogos

	vistos = []

	def mostrar(dialogo):
		botones = {b.GetLabel() for b in _todos(dialogo) if isinstance(b, wx.Button)}
		vistos.append((dialogo.GetTitle(), botones))
		dialogo.Destroy()
		return wx.ID_OK

	monkeypatch.setattr(dialogos, "_mostrar", mostrar)
	dialogo_texto.mostrar_mensaje(None, "Hola", "Ayuda")
	dialogo_texto.mostrar_error(None, "Fallo")
	assert [titulo for titulo, _b in vistos] == ["Ayuda", "Error"]
	assert all("&Aceptar" in botones for _t, botones in vistos)


def _todos(ventana):
	for hijo in ventana.GetChildren():
		yield hijo
		yield from _todos(hijo)


def test_mensajes_usan_los_dialogos_del_proyecto_si_existen(app_wx, monkeypatch):
	recibidos = []
	falso = types.SimpleNamespace(
		mostrar_mensaje=lambda padre, mensaje, titulo, icono=None: recibidos.append(("mensaje", mensaje, titulo)),
		mostrar_error=lambda padre, mensaje, titulo: recibidos.append(("error", mensaje, titulo)),
	)
	paquete = types.ModuleType("app.ui.accesibilidad")
	paquete.dialogos = falso
	monkeypatch.setitem(sys.modules, "app.ui.accesibilidad", paquete)
	monkeypatch.setitem(sys.modules, "app.ui.accesibilidad.dialogos", falso)
	dialogo_texto.mostrar_mensaje(None, "Hola", "Ayuda")
	dialogo_texto.mostrar_error(None, "Fallo", "Abrir")
	assert recibidos == [("mensaje", "Hola", "Ayuda"), ("error", "Fallo", "Abrir")]


def test_documento_inexistente_avisa_en_espanol(app_wx, monkeypatch):
	vistos = []
	monkeypatch.setattr(dialogo_texto, "mostrar_mensaje", lambda padre, mensaje, titulo, *a, **k: vistos.append((titulo, mensaje)))
	assert dialogo_texto.mostrar_documento(None, "no_existe_nunca", "Manual") is False
	assert len(vistos) == 1 and vistos[0][0] == "Manual" and "no_existe_nunca" in vistos[0][1]
