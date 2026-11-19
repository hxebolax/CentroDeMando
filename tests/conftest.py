"""Preparación común de las pruebas.

- Cada prueba trabaja con su propia carpeta ``data`` temporal (``APP_DATA_DIR``):
  nunca se toca la configuración ni los registros reales.
- La voz se desactiva: con un lector de pantalla abierto, las pruebas no
  deben ponerse a hablar.
- Una única ``wx.App`` para toda la sesión, con el proveedor de ayuda y el
  idioma español, como en ``main.py``. Las ventanas se crean SIN mostrarse.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
	sys.path.insert(0, str(RAIZ))


@pytest.fixture(autouse=True)
def datos_temporales(tmp_path, monkeypatch):
	"""Redirige ``data`` a una carpeta temporal y silencia la voz."""
	carpeta = tmp_path / "data"
	monkeypatch.setenv("APP_DATA_DIR", str(carpeta))
	monkeypatch.delenv("APP_DEPURACION", raising=False)
	from app.core import voz

	monkeypatch.setattr(voz, "hablar", lambda texto, interrumpir=False: False)
	from app.ui.accesibilidad import voz as voz_listas

	# La voz de las listas se anota en lugar de hablar: las pruebas la comprueban.
	dichos: list[str] = []
	monkeypatch.setattr(voz_listas, "hablar", lambda texto, *a, **k: dichos.append(texto))
	monkeypatch.setattr(voz_listas, "dichos_en_prueba", dichos, raising=False)
	return carpeta


@pytest.fixture(scope="session")
def app_wx():
	"""``wx.App`` compartida por todas las pruebas de interfaz."""
	wx = pytest.importorskip("wx")
	aplicacion = wx.App.Get() or wx.App(False)
	wx.HelpProvider.Set(wx.SimpleHelpProvider())
	idioma = wx.Locale(wx.LANGUAGE_SPANISH)
	yield aplicacion
	del idioma


@pytest.fixture(autouse=True)
def _sin_modales_reales(request, monkeypatch):
	"""Un ``ShowModal`` o ``wx.MessageBox`` real se vería en pantalla y colgaría las pruebas.

	Falla al momento con el título del cuadro. Las pruebas que lo necesitan
	sustituyen antes la función que lo abre (``monkeypatch.setattr``), o el
	propio ``ShowModal``. Las marcadas ``interfaz`` quedan fuera.
	"""
	if request.node.get_closest_marker("interfaz"):
		return
	try:
		import wx
	except ImportError:
		return

	def prohibido(dialogo, *args, **kwargs):
		raise RuntimeError(f"ShowModal real durante las pruebas: «{dialogo.GetTitle()}» ({request.node.nodeid})")

	def caja_prohibida(mensaje, titulo="", *args, **kwargs):
		raise RuntimeError(f"wx.MessageBox real durante las pruebas: «{titulo}» ({request.node.nodeid})")

	for nombre in ("Dialog", "MessageDialog", "FileDialog", "DirDialog", "TextEntryDialog", "SingleChoiceDialog"):
		clase = getattr(wx, nombre, None)
		if clase is not None and "ShowModal" in vars(clase):
			monkeypatch.setattr(clase, "ShowModal", prohibido)
	monkeypatch.setattr(wx, "MessageBox", caja_prohibida)


def procesar_eventos(condicion=lambda: False, segundos: float = 3.0) -> bool:
	"""Procesa eventos de wx hasta que se cumple ``condicion`` o pasa el tiempo.

	Sin ``MainLoop`` hay que activar un bucle de eventos a mano: ``wx.CallAfter``
	se atiende en ``ProcessPendingEvents`` y la destrucción diferida de las
	ventanas (``Destroy``) en ``ProcessIdle``.
	"""
	import wx

	bucle = wx.GUIEventLoop()
	activo = wx.EventLoopActivator(bucle)
	try:
		limite = time.monotonic() + segundos
		while time.monotonic() < limite:
			while bucle.Pending():
				bucle.Dispatch()
			wx.GetApp().ProcessPendingEvents()
			bucle.ProcessIdle()
			if condicion():
				return True
			time.sleep(0.01)
		return condicion()
	finally:
		del activo


# ── Escritorios falsos ───────────────────────────────────────────────────────


def esperar_servicio(servicio, segundos: float = 3.0) -> bool:
	"""Espera a que el hilo de escritorios haya atendido todo lo encolado hasta ahora."""
	import threading

	hecho = threading.Event()
	servicio.encolar("marca de prueba", lambda motor: None, lambda _r: hecho.set(), lambda _m: hecho.set())
	return hecho.wait(segundos)


@pytest.fixture
def motor_falso():
	from tests.falsos import MotorFalso

	return MotorFalso()


@pytest.fixture
def servicio_falso(motor_falso):
	"""Servicio con hilo real y motor falso; sondeo rápido para las pruebas."""
	from app.services.servicio import Preferencias, ServicioEscritorios

	preferencias = Preferencias(intervalo_sondeo_ms=50)
	servicio = ServicioEscritorios(lambda: preferencias, fabrica_motor=lambda: motor_falso, excluir_propias=False)
	servicio.preferencias_prueba = preferencias
	servicio.iniciar()
	assert esperar_servicio(servicio)
	yield servicio
	servicio.detener()


@pytest.fixture
def controlador_falso(app_wx, servicio_falso):
	"""Controlador sin teclas globales reales y con el servicio falso."""
	from app.core.config import Configuracion
	from app.ui.controlador import Controlador

	controlador = Controlador(Configuracion(), servicio_falso, con_teclas=False)
	return controlador
