"""Pruebas de lo nuevo en la versión 1.1.0 (funciones puras, sin wx)."""

from __future__ import annotations

import datetime as dt
import json

import pytest

from app.core import config as modulo_config
from app.core import registro
from app.services import no_molestar
from app.services.audio import FACTOR_PANTALLA, PuntoAudio, cambios_de_conexion, resumir_por_nombre
from app.ui.controlador import (
	ANUNCIO_COMPLETO,
	ANUNCIO_NADA,
	ANUNCIO_SOLO_VENTANAS,
	contar_ventanas,
	decidir_anuncio,
)

# ── Anuncio del cambio de escritorio ────────────────────────────────────────


@pytest.mark.parametrize(
	("modo", "externo", "lector", "ventanas", "esperado"),
	[
		# Con lector, Windows ya lo dice: en automático no se repite.
		("auto", False, True, False, ANUNCIO_NADA),
		("auto", True, True, False, ANUNCIO_NADA),
		("auto", False, True, True, ANUNCIO_SOLO_VENTANAS),
		("auto", True, True, True, ANUNCIO_SOLO_VENTANAS),
		# Sin lector, los cambios propios se dicen con la voz de Windows.
		("auto", False, False, False, ANUNCIO_COMPLETO),
		("auto", True, False, False, ANUNCIO_NADA),
		("propios", False, True, False, ANUNCIO_COMPLETO),
		("propios", True, True, False, ANUNCIO_NADA),
		("todos", True, True, False, ANUNCIO_COMPLETO),
		("nunca", False, False, True, ANUNCIO_NADA),
	],
)
def test_decidir_anuncio(modo, externo, lector, ventanas, esperado):
	assert decidir_anuncio(modo, externo, lector, ventanas) == esperado


def test_contar_ventanas():
	assert contar_ventanas(0) == "Vacío"
	assert contar_ventanas(1) == "1 ventana"
	assert contar_ventanas(4) == "4 ventanas"


# ── Migración de la configuración 1.0.0 ─────────────────────────────────────


@pytest.mark.parametrize(
	("propios", "externos", "esperado"),
	[(True, False, "auto"), (True, True, "todos"), (False, False, "nunca"), (False, True, "nunca")],
)
def test_migrar_anuncios(tmp_path, propios, externos, esperado):
	ruta = tmp_path / "config.json"
	ruta.write_text(
		json.dumps({"anuncios": {"anunciar_cambios": propios, "anunciar_cambios_externos": externos}}),
		encoding="utf-8",
	)
	configuracion = modulo_config.Configuracion(ruta)
	assert configuracion.obtener("anuncios.cambio_escritorio") == esperado
	assert configuracion.obtener("anuncios.anunciar_cambios") is None
	assert configuracion.obtener("anuncios.anunciar_cambios_externos") is None


def test_sin_configuracion_el_anuncio_es_automatico(tmp_path):
	assert modulo_config.Configuracion(tmp_path / "no_existe.json").obtener("anuncios.cambio_escritorio") == "auto"


# ── Avisos de dispositivos de audio ─────────────────────────────────────────


def _monitor(activo_a: bool, activo_b: bool) -> dict[str, PuntoAudio]:
	return {
		"a": PuntoAudio("ASUS VT229", activo_a, pantalla=True),
		"b": PuntoAudio("ASUS VT229", activo_b, pantalla=True),
		"c": PuntoAudio("Auriculares", True),
	}


def test_un_monitor_con_dos_puntos_es_un_solo_dispositivo():
	assert resumir_por_nombre(_monitor(False, True), True) == {"ASUS VT229": True, "Auriculares": True}
	# Windows pasa el sonido de un punto al otro: no ha cambiado nada para la persona.
	assert cambios_de_conexion(resumir_por_nombre(_monitor(False, True), True), resumir_por_nombre(_monitor(True, False), True)) == []


def test_las_pantallas_se_excluyen_si_no_se_piden():
	assert "ASUS VT229" not in resumir_por_nombre(_monitor(True, False), False)
	assert FACTOR_PANTALLA == 9


def test_cambios_de_conexion():
	antes = {"Auriculares": True, "Altavoz": False}
	ahora = {"Auriculares": False, "Altavoz": True, "Nuevo": True}
	assert cambios_de_conexion(antes, ahora) == ["Conectado: Altavoz", "Desconectado: Auriculares", "Conectado: Nuevo"]


# ── No molestar ─────────────────────────────────────────────────────────────


def test_leer_hora():
	assert no_molestar.leer_hora("23:00") == 1380
	assert no_molestar.leer_hora("8.30") == 510
	for malo in ("", "25:00", "10:75", "diez", None):
		assert no_molestar.leer_hora(malo) is None


@pytest.mark.parametrize(
	("hora", "desde", "hasta", "esperado"),
	[
		("23:30", "23:00", "08:00", True),
		("03:00", "23:00", "08:00", True),
		("08:00", "23:00", "08:00", False),
		("12:00", "23:00", "08:00", False),
		("14:00", "13:00", "15:00", True),
		("15:00", "13:00", "15:00", False),
		("10:00", "10:00", "10:00", False),
		("10:00", "mal", "11:00", False),
	],
)
def test_en_franja(hora, desde, hasta, esperado):
	ahora = dt.datetime.strptime(hora, "%H:%M")
	assert no_molestar.en_franja(ahora, desde, hasta) is esperado


def test_activo():
	mediodia = dt.datetime(2026, 11, 19, 12, 0)
	noche = dt.datetime(2026, 11, 19, 23, 30)
	assert no_molestar.activo(True, False, "23:00", "08:00", mediodia)
	assert not no_molestar.activo(False, True, "23:00", "08:00", mediodia)
	assert no_molestar.activo(False, True, "23:00", "08:00", noche)
	assert not no_molestar.activo(False, False, "23:00", "08:00", noche)


def test_debe_anunciar_notificacion():
	anunciar = no_molestar.debe_anunciar_notificacion
	assert anunciar("Correo", "", "", False, "")
	# Solo estas aplicaciones (vale parte del nombre).
	assert anunciar("WhatsApp Beta", "", "whatsapp", False, "")
	assert not anunciar("Correo", "", "whatsapp", False, "")
	# No molestar: solo las permitidas.
	assert not anunciar("Correo", "", "", True, "")
	assert anunciar("WhatsApp Beta", "", "", True, "WhatsApp")
	assert anunciar("App", "Microsoft.Teams", "", True, "microsoft.teams")
	# Un nombre de dos letras no casa por subcadena (evita falsos positivos).
	assert not anunciar("Outlook", "", "ou", False, "")


# ── Volcado de fallos nativos ───────────────────────────────────────────────


def test_resumir_volcado():
	texto = "Windows fatal exception: code 0x8001010d\n\nThread...\nWindows fatal exception: code 0x8001010d\nWindows fatal exception: code 0xc0000005\n"
	assert registro.resumir_volcado(texto) == ["0x8001010d", "0xc0000005"]


def test_volcado_de_una_sesion_que_no_cerro_se_conserva(tmp_path):
	(tmp_path / registro.NOMBRE_FALLO_NATIVO).write_text("Windows fatal exception: code 0xc0000005\n", encoding="utf-8")
	destino = registro._conservar_fallo_anterior(tmp_path)
	assert destino is not None and destino.name.startswith("fallo_nativo_") and destino.is_file()
	assert not (tmp_path / registro.NOMBRE_FALLO_NATIVO).exists()


def test_volcado_vacio_no_se_aparta(tmp_path):
	(tmp_path / registro.NOMBRE_FALLO_NATIVO).write_text("", encoding="utf-8")
	assert registro._conservar_fallo_anterior(tmp_path) is None


# ── Bandeja: nombre guardado por Windows ────────────────────────────────────


def test_corregir_nombre_no_toca_otros_programas():
	from app.ui.bandeja import corregir_nombre_registrado

	assert corregir_nombre_registrado("Centro de Mando", r"C:\no\existe\programa_de_prueba.exe") == 0
