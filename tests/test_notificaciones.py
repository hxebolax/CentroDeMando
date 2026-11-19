"""Pruebas del historial de notificaciones con una fuente de Windows simulada."""

from __future__ import annotations

import threading
import time

import pytest
import wx

from app.services.notificaciones import (
	ACCESO_PERMITIDO,
	FILTRO_FAVORITAS,
	FILTRO_NO_LEIDAS,
	Captada,
	HistorialNotificaciones,
	PreferenciasNotificaciones,
	ServicioNotificaciones,
)
from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto


class FuenteFalsa:
	def __init__(self) -> None:
		self.avisos: list[Captada] = []
		self.descartadas: list[int] = []

	def acceso(self) -> str:
		return ACCESO_PERMITIDO

	def leer(self) -> list[Captada]:
		return list(self.avisos)

	def descartar(self, id_windows: int) -> None:
		self.descartadas.append(id_windows)
		self.avisos = [a for a in self.avisos if a.id_windows != id_windows]

	def cerrar(self) -> None:
		pass


# Hora fija para toda la prueba: dos avisos con el mismo número son la misma notificación.
BASE = time.time()


def _aviso(numero: int, app: str = "Correo", titulo: str = "Mensaje", texto: str = "Hola") -> Captada:
	return Captada(numero, f"{app}!App", app, f"{titulo} {numero}", texto, BASE - 1000 + numero)


@pytest.fixture
def historial(tmp_path):
	h = HistorialNotificaciones(tmp_path / "n.db")
	yield h
	h.cerrar()


def test_historial_sin_duplicados_filtros_y_estado(historial):
	assert historial.agregar(_aviso(1)) is not None
	assert historial.agregar(_aviso(1)) is None, "la misma notificación no se guarda dos veces"
	historial.agregar(_aviso(2, app="Teams", texto="Reunión a las 10"))
	assert [n.app for n in historial.listar()] == ["Teams", "Correo"], "la más reciente primero"
	assert historial.aplicaciones() == ["Correo", "Teams"]
	assert [n.app for n in historial.listar(app="Correo")] == ["Correo"]
	assert [n.texto for n in historial.listar(buscar="reunión")] == ["Reunión a las 10"]
	assert historial.no_leidas() == 2
	primera = historial.listar(app="Correo")[0]
	historial.marcar_leida([primera.id])
	historial.poner_favorita(primera.id, True)
	assert [n.app for n in historial.listar(FILTRO_NO_LEIDAS)] == ["Teams"]
	assert [n.app for n in historial.listar(FILTRO_FAVORITAS)] == ["Correo"]
	assert historial.marcar_todas_leidas() == 1
	assert historial.vaciar() == 1, "las favoritas se conservan"


def test_recortar_por_dias_y_maximo(historial):
	ahora = time.time()
	for numero in range(5):
		historial.agregar(Captada(numero, "a", "A", "t", "", ahora - numero * 86400 * 10))
	viejo = historial.listar()[-1]
	historial.poner_favorita(viejo.id, True)
	assert historial.recortar(dias=25) == 1, "se borra la de hace 30 días, no la favorita de hace 40"
	assert historial.recortar(maximo=2) == 2, "quedan 4: se borran las 2 más antiguas que no son favoritas"
	assert historial.contar() == 2


def test_exportar_csv_protege_formulas(historial, tmp_path):
	historial.agregar(_aviso(1, texto='=HYPERLINK("x")'))
	ruta = tmp_path / "n.csv"
	assert historial.exportar(ruta, historial.listar()) == 1
	contenido = ruta.read_text(encoding="utf-8-sig")
	assert "'=HYPERLINK" in contenido
	historial.exportar(tmp_path / "n.txt", historial.listar())
	assert "Mensaje 1" in (tmp_path / "n.txt").read_text(encoding="utf-8")


def test_servicio_guarda_avisa_ignora_y_descarta(historial):
	fuente = FuenteFalsa()
	fuente.avisos = [_aviso(1)]
	preferencias = PreferenciasNotificaciones(intervalo_s=1, apps_ignoradas=("Juegos",))
	servicio = ServicioNotificaciones(lambda: preferencias, historial, fabrica_fuente=lambda: fuente)
	nuevas = []
	llegada = threading.Event()
	servicio.al_nuevas = lambda lista: (nuevas.extend(lista), llegada.set())
	servicio.iniciar()
	try:
		limite = time.time() + 3
		while historial.contar() < 1 and time.time() < limite:
			time.sleep(0.05)
		assert historial.contar() == 1 and nuevas == [], "lo que ya estaba al arrancar se guarda sin anunciarse"
		fuente.avisos.append(Captada(99, "Viejo!App", "Viejo", "t", "", time.time() - 400 * 86400))
		fuente.avisos.append(_aviso(2, app="Juegos"))
		fuente.avisos.append(_aviso(3, app="Teams"))
		servicio.consultar_ya()
		assert llegada.wait(3)
		assert [n.app for n in nuevas] == ["Teams"], "ni las aplicaciones ignoradas ni las más antiguas que el plazo"
		teams = historial.listar(app="Teams")[0]
		hecho = threading.Event()
		servicio.descartar_en_windows(teams, lambda ok: hecho.set())
		assert hecho.wait(3) and fuente.descartadas == [3]
		servicio.consultar_ya()
		limite = time.time() + 3
		while historial.obtener(teams.id).en_windows and time.time() < limite:
			time.sleep(0.05)
		assert not historial.obtener(teams.id).en_windows, "se sabe que ya no está en Windows"
	finally:
		servicio._historial = None  # el historial lo cierra la prueba
		servicio.detener()


def test_area_y_ventana_rapida(controlador_falso, tmp_path, monkeypatch):
	from app.ui import area_notificaciones
	from app.ui.ventanas_rapidas import NotificacionesRapido

	controlador_falso.notificaciones._historial = HistorialNotificaciones(tmp_path / "n.db")
	historial = controlador_falso.notificaciones.historial
	historial.agregar(_aviso(1, texto="Primer aviso"))
	historial.agregar(_aviso(2, app="Teams", texto="Segundo aviso"))
	ventana = NotificacionesRapido(controlador_falso, 0)
	try:
		afirmar_teclado_correcto(ventana)
		area = ventana.area
		assert area.lista.numero_filas() == 2
		assert area.lista.texto_celda(0, 0) == "Teams"
		assert area.lista.texto_celda(0, 4) == "no leída"
		area.lista.enfocar_fila(0, anunciar=False)
		area._mostrar_contenido()
		assert area.contenido.GetValue() == "Teams\nMensaje 2\nSegundo aviso"
		abiertas = []
		monkeypatch.setattr(area_notificaciones, "abrir_aplicacion", lambda aumid: abiertas.append(aumid) or True)
		area.abrir_app()
		assert abiertas == ["Teams!App"]
		area.refrescar()
		assert area.lista.texto_celda(0, 4) == "leída", "abrirla la marca como leída"
		monkeypatch.setattr(wx.Window, "FindFocus", staticmethod(lambda: area.lista))
		evento = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
		evento.SetKeyCode(wx.WXK_F4)
		assert area.manejar_tecla(evento)
		assert "favorita" in area.lista.texto_celda(0, 4)
		area.app.SetSelection(area.app.GetItems().index("Correo"))
		area.refrescar()
		assert area.lista.numero_filas() == 1
	finally:
		ventana.Destroy()
		historial.cerrar()
