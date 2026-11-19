"""Pruebas de lo nuevo en la versión 1.2.0 (funciones puras, sin tocar el audio real)."""

from __future__ import annotations

import pytest

from app.services import audio, perfiles_audio
from app.services.perfiles_audio import PerfilAudio

# ── Balance ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
	("izquierdo", "derecho", "esperado"),
	[(0.5, 0.5, 0), (0.5, 0.0, -100), (0.0, 0.5, 100), (0.8, 0.4, -50), (0.0, 0.0, 0)],
)
def test_calcular_balance(izquierdo, derecho, esperado):
	assert audio.calcular_balance(izquierdo, derecho) == esperado


def test_canales_para_balance_mantiene_el_volumen():
	assert audio.canales_para_balance(0, 0.6) == (0.6, 0.6)
	izquierdo, derecho = audio.canales_para_balance(-50, 0.6)
	assert izquierdo == 0.6 and derecho == pytest.approx(0.3)
	assert audio.calcular_balance(*audio.canales_para_balance(40, 0.8)) == 40
	assert audio.canales_para_balance(500, 2.0) == (0.0, 1.0)


def test_describir_balance():
	assert audio.describir_balance(0) == "Centrado"
	assert audio.describir_balance(-20) == "20 a la izquierda"
	assert audio.describir_balance(100) == "100 a la derecha"


def test_canales_por_lado():
	assert audio.CANALES_LADOS[2] == ((0,), (1,))
	assert 1 not in audio.CANALES_LADOS  # mono: sin balance


# ── Dispositivos y privacidad ───────────────────────────────────────────────


def test_estado_de_dispositivo():
	assert audio.Dispositivo("a", "A").estado() == ""
	assert audio.Dispositivo("a", "A", True).estado() == "predeterminado"
	assert audio.Dispositivo("a", "A", False, True).estado() == "comunicaciones"
	assert audio.Dispositivo("a", "A", True, True).estado() == "predeterminado y comunicaciones"


@pytest.mark.parametrize(
	("subclave", "esperado"),
	[
		("C:#Program Files#Zoom#bin#Zoom.exe", "Zoom"),
		("C:#Users#ana#AppData#Local#Discord#app-1.0#Discord.EXE", "Discord"),
		("MSTeams_8wekyb3d8bbwe", "MSTeams"),
		("Microsoft.WindowsSoundRecorder_8wekyb3d8bbwe", "WindowsSoundRecorder"),
	],
)
def test_nombre_de_consentimiento(subclave, esperado):
	assert audio.nombre_de_consentimiento(subclave) == esperado


# ── Perfiles de audio ───────────────────────────────────────────────────────


def _perfil() -> PerfilAudio:
	return PerfilAudio("Reuniones", ("s1", "Auriculares"), ("s1", "Auriculares"), ("m1", "Micro USB"), ("m1", "Micro USB"), 40, 80)


def test_perfil_ida_y_vuelta():
	perfil = _perfil()
	assert PerfilAudio.de_dict(perfil.a_dict()) == perfil
	assert perfil.describir() == "Auriculares, 40 %; Micro USB, 80 %"


def test_cargar_ignora_perfiles_danados():
	buenos = perfiles_audio.cargar([_perfil().a_dict(), {"nombre": ""}, "basura", {"nombre": "X", "volumen": 900}])
	assert [p.nombre for p in buenos] == ["Reuniones", "X"]
	assert buenos[1].volumen == -1
	assert perfiles_audio.cargar(None) == []


def test_buscar_por_id_y_por_nombre():
	lista = [audio.Dispositivo("nuevo-id", "Auriculares"), audio.Dispositivo("otro", "Altavoces")]
	assert perfiles_audio.buscar(lista, ("nuevo-id", "x")).nombre == "Auriculares"
	assert perfiles_audio.buscar(lista, ("id-viejo", "Altavoces")).id == "otro"
	assert perfiles_audio.buscar(lista, ("", "")) is None
	assert perfiles_audio.buscar(lista, ("nada", "Nada")) is None


def test_siguiente_perfil_ciclico():
	perfiles = [PerfilAudio("A"), PerfilAudio("B")]
	assert perfiles_audio.siguiente(perfiles, "").nombre == "A"
	assert perfiles_audio.siguiente(perfiles, "A").nombre == "B"
	assert perfiles_audio.siguiente(perfiles, "B").nombre == "A"
	assert perfiles_audio.siguiente([], "A") is None


def test_aplicar_perfil(monkeypatch):
	hechos = []
	monkeypatch.setattr(audio, "dispositivos_salida", lambda: [audio.Dispositivo("s1", "Auriculares")])
	monkeypatch.setattr(audio, "dispositivos_entrada", lambda: [])
	monkeypatch.setattr(audio, "poner_predeterminado", lambda d: hechos.append(("pred", d.id)))
	monkeypatch.setattr(audio, "poner_comunicaciones", lambda d: hechos.append(("com", d.id)))
	monkeypatch.setattr(audio, "poner_predeterminado_entrada", lambda d: hechos.append(("pred_micro", d.id)))
	monkeypatch.setattr(audio, "poner_volumen_general", lambda v: hechos.append(("vol", v)))
	monkeypatch.setattr(audio, "poner_volumen_entrada", lambda v, i=None: hechos.append(("vol_micro", v)))
	faltan = perfiles_audio.aplicar(_perfil())
	assert faltan == ["Micro USB"]
	assert hechos == [("pred", "s1"), ("com", "s1"), ("vol", 40)]
