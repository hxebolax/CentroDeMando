"""Pruebas de lo nuevo en la versión 1.4.0: cifrado del historial y gestión de audio."""

from __future__ import annotations

import sqlite3

import pytest

from app.core import dpapi
from app.services import audio, topologia
from app.services.portapapeles import NO_DESCIFRABLE, HistorialPortapapeles
from app.services.portapapeles_win32 import TIPO_ARCHIVOS, Contenido

# ── DPAPI ───────────────────────────────────────────────────────────────────


def test_dpapi_ida_y_vuelta():
	secreto = "Contraseña: ñandú 😀".encode()
	cifrado = dpapi.cifrar(secreto)
	assert cifrado != secreto and secreto not in cifrado
	assert dpapi.descifrar(cifrado) == secreto
	assert dpapi.cifrar(b"") == b"" and dpapi.descifrar(b"") == b""


def test_dpapi_rechaza_datos_ajenos():
	with pytest.raises(dpapi.ErrorDpapi):
		dpapi.descifrar(b"esto no lo cifro DPAPI" * 4)


# ── Historial cifrado ───────────────────────────────────────────────────────


def _crudo(ruta) -> bytes:
	return ruta.read_bytes() + (ruta.with_name(ruta.name + "-wal").read_bytes() if ruta.with_name(ruta.name + "-wal").exists() else b"")


def test_guardar_cifrado_y_leer(tmp_path):
	ruta = tmp_path / "p.db"
	historial = HistorialPortapapeles(ruta)
	historial.cifrar = True
	elemento = historial.agregar(Contenido(texto="clave secreta del banco", html=b"<b>x</b>", origen="notepad.exe"))
	historial.agregar(Contenido(tipo=TIPO_ARCHIVOS, archivos=["C:\\privado\\nominas.pdf"]))
	assert historial.obtener(elemento.id).texto == "clave secreta del banco"
	assert historial.obtener(elemento.id).html == b"<b>x</b>"
	assert historial.contar_cifrados() == 2
	historial.cerrar()
	assert b"clave secreta" not in _crudo(ruta) and b"nominas" not in _crudo(ruta)


def test_buscar_en_lo_cifrado(tmp_path):
	historial = HistorialPortapapeles(tmp_path / "p.db")
	historial.agregar(Contenido(texto="texto normal de prueba"))
	historial.cifrar = True
	historial.agregar(Contenido(texto="receta de tortilla secreta"))
	historial.agregar(Contenido(tipo=TIPO_ARCHIVOS, archivos=["C:\\docs\\tortilla.txt"]))
	encontrados = [e.texto or e.archivos[0] for e in historial.listar(buscar="tortilla")]
	assert encontrados == ["C:\\docs\\tortilla.txt", "receta de tortilla secreta"]
	assert [e.texto for e in historial.listar(buscar="normal")] == ["texto normal de prueba"]
	assert len(historial.listar()) == 3
	historial.cerrar()


def test_cifrar_y_descifrar_lo_guardado(tmp_path):
	ruta = tmp_path / "p.db"
	historial = HistorialPortapapeles(ruta)
	for numero in range(150):  # más de una tanda
		historial.agregar(Contenido(texto=f"elemento privado {numero}"))
	assert historial.cambiar_cifrado(True) == 150
	assert historial.contar_cifrados() == 150
	assert historial.listar(buscar="privado 149")[0].texto == "elemento privado 149"
	historial.cerrar()
	assert b"elemento privado" not in _crudo(ruta)
	historial = HistorialPortapapeles(ruta)
	assert historial.cambiar_cifrado(False) == 150
	assert historial.contar_cifrados() == 0
	historial.cerrar()


def test_cifrado_de_otro_usuario_no_rompe(tmp_path):
	ruta = tmp_path / "p.db"
	historial = HistorialPortapapeles(ruta)
	historial.agregar(Contenido(texto="hola"))
	with sqlite3.connect(ruta) as conexion:
		conexion.execute("UPDATE elementos SET texto = ?, cifrado = 1", (b"basura que no es DPAPI" * 3,))
	assert historial.listar()[0].texto == NO_DESCIFRABLE
	historial.cerrar()


def test_base_antigua_sin_columna_cifrado(tmp_path):
	ruta = tmp_path / "antigua.db"
	with sqlite3.connect(ruta) as conexion:
		conexion.execute(
			"CREATE TABLE elementos (id INTEGER PRIMARY KEY AUTOINCREMENT, huella TEXT NOT NULL UNIQUE, tipo TEXT NOT NULL,"
			" texto TEXT NOT NULL DEFAULT '', html BLOB, archivos TEXT NOT NULL DEFAULT '', imagen BLOB,"
			" ancho INTEGER NOT NULL DEFAULT 0, alto INTEGER NOT NULL DEFAULT 0, nombre TEXT NOT NULL DEFAULT '',"
			" favorito INTEGER NOT NULL DEFAULT 0, origen TEXT NOT NULL DEFAULT '', creado REAL NOT NULL, usado REAL NOT NULL,"
			" veces INTEGER NOT NULL DEFAULT 1)"
		)
		conexion.execute("INSERT INTO elementos (huella, tipo, texto, creado, usado) VALUES ('h', 'texto', 'de antes', 1, 1)")
	historial = HistorialPortapapeles(ruta)
	assert historial.listar()[0].texto == "de antes"
	historial.cerrar()


# ── Audio: escucha, atenuación, límites ─────────────────────────────────────


def test_es_propiedad_escucha():
	assert audio.es_propiedad_escucha("{24dbb0fc-9311-4b3d-9cf0-18ff155639d4}", 1)
	assert audio.es_propiedad_escucha("{24DBB0FC-9311-4B3D-9CF0-18FF155639D4}", 0)
	assert not audio.es_propiedad_escucha("{24DBB0FC-9311-4B3D-9CF0-18FF155639D4}", 2)
	assert not audio.es_propiedad_escucha("{1da5d803-d492-4edd-8c23-e0c0ffee7f0e}", 0)


def test_cambio_de_escucha_propio(monkeypatch):
	monkeypatch.setattr(audio, "_escucha_propia", {"m1": __import__("time").monotonic()})
	assert audio.cambio_de_escucha_propio("m1")
	assert not audio.cambio_de_escucha_propio("m2")


def test_atenuacion_valida():
	assert audio.leer_atenuacion() in (0, 1, 2, 3)
	with pytest.raises(audio.ErrorAudio):
		audio.poner_atenuacion(7)


def test_nombres_de_programa_y_limites():
	assert audio.nombre_programa(" Chrome.EXE ") == "chrome"
	assert audio.lista_programas("chrome, Spotify.exe ,, nvda") == {"chrome", "spotify", "nvda"}
	assert audio.leer_limites({"Chrome.exe": 50, "malo": "x", "tope": 100, "otro": True, "spotify": 30.0}) == {"chrome": 50, "spotify": 30}
	assert audio.leer_limites(None) == {}


def test_aplicar_limites(monkeypatch):
	puestos = {}
	monkeypatch.setattr(
		audio,
		"sesiones",
		lambda: [audio.Sesion("a", "chrome.exe", 1, 90, False), audio.Sesion("b", "spotify.exe", 2, 20, False), audio.Sesion("c", "nvda.exe", 3, 100, False)],
	)
	monkeypatch.setattr(audio, "poner_volumen_sesion", lambda clave, v: puestos.__setitem__(clave, v) or v)
	assert audio.aplicar_limites({"chrome": 40, "spotify": 50}) == ["chrome.exe"]
	assert puestos == {"a": 40}
	assert audio.aplicar_limites({}) == []


# ── Amplificación del micrófono ─────────────────────────────────────────────


def test_formatear_db():
	assert topologia.formatear_db(0) == "0 dB"
	assert topologia.formatear_db(20) == "+20 dB"
	assert topologia.formatear_db(-6.5) == "-6,5 dB"
	assert topologia.formatear_db(10.04) == "+10 dB"


def test_pasos_validos():
	assert topologia.pasos_validos(0, 30, 10) == [0, 10, 20, 30]
	assert topologia.pasos_validos(0, 0, 10) == [0]
	assert topologia.pasos_validos(0, 30, 0) == [0]
	assert len(topologia.pasos_validos(-100, 100, 0.01)) == 201


def test_buscar_amplificaciones_de_un_id_inexistente():
	assert topologia.buscar_amplificaciones("{0.0.1.00000000}.{no-existe}") == []


# ── Mejoras de audio y favoritos ────────────────────────────────────────────


def test_mejoras_de_un_dispositivo_inexistente():
	assert audio.leer_mejoras("{0.0.0.00000000}.{no-existe}") is None
	with pytest.raises(audio.ErrorAudio):
		audio.poner_mejoras("{0.0.0.00000000}.{no-existe}", False)


def test_favoritos_primero_al_buscar(tmp_path):
	historial = HistorialPortapapeles(tmp_path / "p.db")
	viejo = historial.agregar(Contenido(texto="pan antiguo favorito"))
	historial.agregar(Contenido(texto="pan reciente"))
	historial.poner_favorito(viejo.id, True)
	assert [e.texto for e in historial.listar(buscar="pan")] == ["pan antiguo favorito", "pan reciente"]
	# Sin buscar se mantiene el orden por uso.
	assert [e.texto for e in historial.listar()] == ["pan reciente", "pan antiguo favorito"]
	historial.cerrar()


def test_ventana_rapida_de_favoritos(controlador_falso):
	from app.services.portapapeles import FILTRO_FAVORITOS
	from app.ui.area_portapapeles import FILTROS
	from app.ui.ventanas_rapidas import PortapapelesRapido

	ventana = PortapapelesRapido(controlador_falso, 0, solo_favoritos=True)
	try:
		area = ventana._crear_area()
		assert FILTROS[area.filtro.GetSelection()][0] == FILTRO_FAVORITOS
	finally:
		ventana.Destroy()
