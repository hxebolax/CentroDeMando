"""Fuentes de actualización elegibles: servidor, GitHub, ambos o personalizada."""

from __future__ import annotations

import pytest

from app.services import actualizador as a


def test_urls_de_cada_fuente():
	assert a.urls_de_fuente("servidor") == [a.URL_SERVIDOR]
	assert a.urls_de_fuente("github") == [a.URL_GITHUB]
	assert a.urls_de_fuente("ambos") == [a.URL_SERVIDOR, a.URL_GITHUB]
	assert a.urls_de_fuente("personalizada", " https://mio.example/version.json ") == ["https://mio.example/version.json"]
	assert a.urls_de_fuente("personalizada", "") == [a.URL_SERVIDOR, a.URL_GITHUB], "sin dirección, los dos de siempre"
	assert a.URL_SERVIDOR.startswith("https://") and a.URL_GITHUB.startswith("https://github.com/hxebolax/CentroDeMando/")


def test_si_falla_el_servidor_se_usa_github(tmp_path, monkeypatch):
	config = a.Configuracion(version_actual="1.0.0", carpeta_app=tmp_path, carpeta_datos=tmp_path / "data")
	config.extra["urls"] = a.urls_de_fuente("ambos")
	pedidas = []

	def leer(_config, url):
		pedidas.append(url)
		if url == a.URL_SERVIDOR:
			raise a.ErrorRed("sin conexión")
		return {"version": "1.0.0"}

	monkeypatch.setattr(a, "_leer_manifiesto", leer)
	monkeypatch.setattr(a, "verificar_firma", lambda m, c: None)
	monkeypatch.setattr(
		a, "_info_desde_manifiesto", lambda c, m, u: a.InfoActualizacion("1.0.0", "x.zip", u.replace("version.json", "x.zip"), "0" * 64, 1)
	)
	assert a.comprobar(config) is None, "misma versión: no hay nada nuevo"
	assert pedidas == [a.URL_SERVIDOR, a.URL_GITHUB]


def test_si_fallan_todas_se_informa_del_ultimo_error(tmp_path, monkeypatch):
	config = a.Configuracion(version_actual="1.0.0", carpeta_app=tmp_path, carpeta_datos=tmp_path / "data")
	config.extra["urls"] = a.urls_de_fuente("ambos")
	monkeypatch.setattr(a, "_leer_manifiesto", lambda c, url: (_ for _ in ()).throw(a.ErrorRed(f"falla {url}")))
	with pytest.raises(a.ErrorRed, match="github"):
		a.comprobar(config)
