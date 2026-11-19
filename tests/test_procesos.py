"""Pruebas del área de ventanas y procesos (sin tocar ventanas ni procesos reales)."""

from __future__ import annotations

import wx

from app.services import procesos
from app.ui import area_procesos as ap
from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto


def test_estado_de_ventana():
	assert procesos.Ventana(1, "t", "p.exe", 1, minimizada=True).estado() == "minimizada"
	assert procesos.Ventana(1, "t", "p.exe", 1, maximizada=True, encima=True, no_responde=True).estado() == "maximizada, siempre encima, no responde"


def test_monitor_lee_procesos_reales_rapido():
	import time

	monitor = procesos.MonitorProcesos()
	inicio = time.perf_counter()
	lista = monitor.leer()
	assert lista and all(p.pid not in (0, 4) for p in lista)
	assert time.perf_counter() - inicio < 1.5, "leer los procesos debe ser rápido"


def test_area(controlador_falso, monkeypatch):
	ventanas = [procesos.Ventana(10, "Documento - Bloc de notas", "notepad.exe", 100), procesos.Ventana(11, "Firefox", "firefox.exe", 200, encima=True)]
	monkeypatch.setattr(procesos, "ventanas", lambda excluir_pid=0: ventanas)
	llamadas = []
	monkeypatch.setattr(procesos, "poner_encima", lambda hwnd, encima: llamadas.append(("encima", hwnd, encima)))
	monkeypatch.setattr(procesos, "esta_encima", lambda hwnd: False)
	monkeypatch.setattr(procesos, "finalizar", lambda pid: llamadas.append(("finalizar", pid)) or True)
	monkeypatch.setattr(ap, "confirmar", lambda *a, **k: wx.ID_YES)
	marco = wx.Frame(None)
	area = ap.AreaProcesos(marco, controlador_falso)
	monkeypatch.setattr(area.monitor, "leer", lambda: [procesos.Proceso(100, "notepad.exe", 1.0, 20.0), procesos.Proceso(200, "firefox.exe", 9.5, 500.0)])
	try:
		area.refrescar()
		afirmar_teclado_correcto(marco)
		assert area.lista_procesos.texto_celda(0, 0) == "firefox.exe", "primero el que más procesador usa"
		assert area.lista_procesos.texto_celda(0, 2) == "9,5 %"
		assert area.lista.texto_celda(1, 2) == "normal, siempre encima"
		area.buscar.SetValue("bloc")
		assert area.lista.numero_filas() == 1
		area.lista.enfocar_fila(0, anunciar=False)
		area.alternar_encima()
		assert llamadas == [("encima", 10, True)]
		monkeypatch.setattr(wx.Window, "FindFocus", staticmethod(lambda: area.lista))
		area.finalizar()
		assert llamadas[-1] == ("finalizar", 100), "desde la lista de ventanas se finaliza su proceso"
	finally:
		area._temporizador.Stop()
		marco.Destroy()
