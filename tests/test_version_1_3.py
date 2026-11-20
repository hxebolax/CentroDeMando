"""Pruebas de lo nuevo en la versión 1.3.0: copias, dispositivos preferidos y sesión."""

from __future__ import annotations

import json
import os
import sqlite3
import time
import zipfile

import pytest

from app.services import copias, preferencias_audio, sesion
from app.services.audio import Dispositivo

# ── Copias de seguridad ─────────────────────────────────────────────────────


@pytest.fixture
def datos(tmp_path):
	"""Una carpeta data con configuración, un fragmento y dos bases SQLite."""
	carpeta = tmp_path / "data"
	(carpeta / "config").mkdir(parents=True)
	(carpeta / "db").mkdir()
	(carpeta / "config" / "config.json").write_text('{"general": {"anunciar_arranque": false}}', encoding="utf-8")
	(carpeta / "config" / "actualizaciones.json").write_text("{}", encoding="utf-8")
	(carpeta / "db" / "fragmentos.json").write_text("[]", encoding="utf-8")
	for nombre in ("portapapeles.db", "notificaciones.db"):
		conexion = sqlite3.connect(carpeta / "db" / nombre)
		conexion.execute("CREATE TABLE t (v TEXT)")
		conexion.execute("INSERT INTO t VALUES (?)", (nombre,))
		conexion.commit()
		conexion.close()
	return carpeta


def test_crear_y_leer_copia(datos, tmp_path):
	destino = copias.crear_copia(tmp_path / "copia.zip", "1.3.0", True, datos)
	informacion = copias.leer_copia(destino)
	assert informacion.version == "1.3.0"
	assert set(informacion.archivos) == {"config/config.json", "db/fragmentos.json", "db/portapapeles.db", "db/notificaciones.db"}
	# El estado del actualizador de este equipo nunca viaja.
	assert "config/actualizaciones.json" not in informacion.archivos


def test_copia_sin_portapapeles(datos, tmp_path):
	informacion = copias.leer_copia(copias.crear_copia(tmp_path / "c.zip", "1.3.0", False, datos))
	assert "db/portapapeles.db" not in informacion.archivos


def test_rechaza_zip_ajeno_o_con_rutas_raras(tmp_path):
	ajeno = tmp_path / "ajeno.zip"
	with zipfile.ZipFile(ajeno, "w") as paquete:
		paquete.writestr("hola.txt", "x")
	with pytest.raises(copias.ErrorCopia):
		copias.leer_copia(ajeno)
	malo = tmp_path / "malo.zip"
	with zipfile.ZipFile(malo, "w") as paquete:
		paquete.writestr(copias.MANIFIESTO, json.dumps({"app": "CentroDeMando"}))
		paquete.writestr("../../Windows/evil.dll", "x")
	with pytest.raises(copias.ErrorCopia):
		copias.leer_copia(malo)
	roto = tmp_path / "roto.zip"
	roto.write_bytes(b"no soy un zip")
	with pytest.raises(copias.ErrorCopia):
		copias.leer_copia(roto)


@pytest.mark.parametrize(
	("nombre", "valido"),
	[
		("config/config.json", True),
		("db/portapapeles.db", True),
		("db/fragmentos.json", True),
		("config/actualizaciones.json", False),
		("db/../config.json", False),
		("logs/sesion.log", False),
		("db/x.exe", False),
	],
)
def test_nombre_permitido(nombre, valido):
	assert copias.nombre_permitido(nombre) is valido


def test_importar_se_aplica_en_el_arranque(datos, tmp_path):
	copia = copias.crear_copia(tmp_path / "copia.zip", "1.3.0", True, datos)
	# Después de la copia, la configuración cambia...
	(datos / "config" / "config.json").write_text('{"cambiado": true}', encoding="utf-8")
	copias.preparar_importacion(copia, datos)
	assert copias.hay_importacion_pendiente(datos)
	# ...y al arrancar vuelve la de la copia, guardando antes lo que había.
	assert copias.aplicar_importacion_pendiente("1.3.0", datos)
	assert "anunciar_arranque" in (datos / "config" / "config.json").read_text(encoding="utf-8")
	assert not copias.hay_importacion_pendiente(datos)
	assert list((datos / "backups").glob("antes_de_importar_*.zip"))
	conexion = sqlite3.connect(datos / "db" / "notificaciones.db")
	assert conexion.execute("SELECT v FROM t").fetchone()[0] == "notificaciones.db"
	conexion.close()


def test_sin_importacion_pendiente_no_hace_nada(datos):
	assert copias.aplicar_importacion_pendiente("1.3.0", datos) is False


def test_copia_automatica_diaria_y_limpieza(datos):
	primera = copias.copia_automatica("1.3.0", conservar=2, datos=datos)
	assert primera is not None and primera.is_file()
	# El mismo día no se repite.
	assert copias.copia_automatica("1.3.0", conservar=2, datos=datos) is None
	# Si la última es de hace más de un día, toca otra; se conservan solo 2.
	for indice in range(3):
		viejas = copias.copias_automaticas(datos / "backups")
		hace_dos_dias = time.time() - 2 * 86400
		os.utime(viejas[0], (hace_dos_dias, hace_dos_dias))
		time.sleep(1.1)  # nombres con segundos distintos
		assert copias.copia_automatica("1.3.0", conservar=2, datos=datos) is not None, indice
	assert len(copias.copias_automaticas(datos / "backups")) == 2


# ── Dispositivos preferidos ─────────────────────────────────────────────────


def test_elegir_preferido():
	conectados = [Dispositivo("1", "Altavoces", True), Dispositivo("2", "Auriculares BT")]
	assert preferencias_audio.elegir_preferido(["Auriculares BT", "Altavoces"], conectados).id == "2"
	assert preferencias_audio.elegir_preferido(["Cascos USB", "altavoces"], conectados).id == "1"
	assert preferencias_audio.elegir_preferido(["Nada"], conectados) is None
	assert preferencias_audio.elegir_preferido([], conectados) is None


def test_cambio_necesario_solo_si_no_es_ya_el_predeterminado():
	conectados = [Dispositivo("1", "Altavoces", True), Dispositivo("2", "Auriculares BT")]
	assert preferencias_audio.cambio_necesario(["Altavoces"], conectados) is None
	assert preferencias_audio.cambio_necesario(["Auriculares BT", "Altavoces"], conectados).id == "2"
	# Al apagar los auriculares vuelve al siguiente de la lista.
	assert preferencias_audio.cambio_necesario(["Auriculares BT", "Altavoces"], [Dispositivo("1", "Altavoces")]).id == "1"


def test_filas_y_mover():
	filas = preferencias_audio.filas_para_dialogo(["B", "A"], ["A", "C", "b"])
	assert filas == [("B", True), ("A", True), ("C", False)]
	assert preferencias_audio.mover(filas, 2, -1) == 1
	assert filas[1] == ("C", False)
	assert preferencias_audio.mover(filas, 0, -1) == 0  # no sale de la lista


def test_dialogo_preferencias(app_wx):
	import wx

	from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto
	from app.ui.dialogo_preferencias_audio import DialogoPreferenciasAudio

	dialogo = DialogoPreferenciasAudio(None, False, True, ["Auriculares"], ["Altavoces", "Auriculares", "Monitor"])
	try:
		afirmar_teclado_correcto(dialogo)
		assert dialogo.lista.GetCount() == 3 and dialogo.lista.IsChecked(0) and not dialogo.lista.IsChecked(1)
		dialogo.lista.SetSelection(1)
		dialogo.lista.Check(1, True)
		dialogo.mover(-1)
		activo, orden = dialogo.resultado()
		assert activo is True
		assert orden == ["Altavoces", "Auriculares"]
		assert dialogo.lista.GetSelection() == 0
		assert isinstance(dialogo, wx.Dialog)
	finally:
		dialogo.Destroy()


# ── Sesión ──────────────────────────────────────────────────────────────────


def test_sesion_bloqueada_responde():
	# Mientras se pasan las pruebas, el equipo no está bloqueado.
	assert sesion.sesion_bloqueada() in (False, None)
