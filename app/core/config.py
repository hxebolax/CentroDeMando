"""Configuración persistente mínima: JSON legible en ``data/config/config.json``.

Decisiones:

- Los valores por defecto viven EN EL CÓDIGO (``VALORES_POR_DEFECTO``), no en
  un archivo distribuido. Si falta ``config.json`` se usan estos valores; si
  una versión nueva añade claves, una configuración antigua sigue valiendo
  porque se fusiona sobre ellos.
- Escritura atómica: temporal + ``fsync`` + ``os.replace``. Un corte de luz
  nunca deja un ``config.json`` a medias: o queda el viejo o el nuevo.
- Un archivo dañado NO impide arrancar: se aparta con otro nombre (para poder
  estudiarlo), se avisa en el registro y se sigue con los valores por defecto.
- Un valor de tipo equivocado (``"ancho": "grande"``) se ignora y se usa el
  predeterminado: más vale una ventana de tamaño estándar que una excepción.
- Acceso seguro entre hilos con un ``RLock``.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

from app.core import paths

log = logging.getLogger(__name__)

NOMBRE_ARCHIVO = "config.json"

# Todas las claves que la aplicación conoce, con su valor inicial.
VALORES_POR_DEFECTO: dict[str, Any] = {
	"general": {
		# Voz al arrancar (solo si hay lector de pantalla o SAPI disponibles).
		"anunciar_arranque": True,
		# El gestor vive en la bandeja: el icono está siempre y cerrar o
		# minimizar lo deja ahí (las teclas globales siguen funcionando). Si la
		# bandeja oculta el icono, Ctrl+Alt+Win+G vuelve a mostrar la ventana.
		"icono_siempre": True,
		"minimizar_a_bandeja": True,
		"cerrar_a_bandeja": True,
		"iniciar_en_bandeja": False,
		# Al arrancar con Windows, empezar oculto en la bandeja.
		"bandeja_al_iniciar_con_windows": True,
		"confirmar_eliminar": True,
	},
	"escritorios": {
		# Del último escritorio se pasa al primero y al revés.
		"ciclico": True,
		# Tras cambiar, dar el foco a la última ventana usada del escritorio.
		"enfocar_al_cambiar": True,
		"animacion": False,
		# Cada cuánto se comprueba si el escritorio cambió fuera del gestor.
		"intervalo_sondeo_ms": 250,
		# Hacer cíclicas también Ctrl+Win+Izquierda/Derecha de Windows (gancho de teclado).
		"interceptar_flechas_nativas": False,
	},
	"anuncios": {
		"anunciar_cambios": True,
		# NVDA ya anuncia el escritorio al cambiar con Control+Windows+flechas: de fábrica no se repite.
		"anunciar_cambios_externos": False,
		"decir_numero": True,
		"decir_total": False,
		"decir_ventanas": False,
		"tono": False,
		# Espera antes de hablar: así el lector anuncia primero la ventana enfocada
		# y nuestro aviso no queda cortado por el cambio de foco.
		"retraso_ms": 150,
	},
	"listas": {
		# Qué se dice al recorrer las columnas de una lista (Izquierda/Derecha, Ctrl+1…0).
		# Si las tres están desactivadas, se dice igualmente el contenido.
		"decir_numero_fila": True,
		"decir_cabecera": True,
		"decir_contenido": True,
	},
	"portapapeles": {
		"activo": True,
		# Elementos que se guardan como máximo (0 = sin límite). Los favoritos no cuentan para borrar.
		"maximo": 500,
		# Borrar lo que no se usa desde hace estos días (0 = nunca). Los favoritos no caducan.
		"dias": 0,
		"guardar_html": True,
		"guardar_archivos": True,
		"guardar_imagenes": True,
		"maximo_imagen_mb": 20,
		# No guardar lo que los gestores de contraseñas marcan como privado.
		"ignorar_privados": True,
		# Programas cuyas copias no se guardan, separados por comas («keepass.exe, bitwarden.exe»).
		"programas_excluidos": "",
		# Tras pegar desde el historial, devolver al portapapeles lo que había antes.
		"restaurar_tras_pegar": True,
		"retraso_restaurar_ms": 500,
		# control_v | mayus_insert
		"metodo_pegado": "control_v",
		"anunciar_copias": False,
	},
	"emoticonos": {
		# 0 = sin tono; 1-5 = de claro a oscuro.
		"tono": 0,
		# escribir (teclear el carácter, sin tocar el portapapeles) | control_v | mayus_insert
		"metodo": "escribir",
		# Mostrar el carácter junto al nombre en las listas (el lector lo leería dos veces).
		"mostrar_caracter": False,
		"maximo_recientes": 40,
		"recientes": [],
		"favoritos": [],
	},
	"notificaciones": {
		"activo": True,
		# Cada cuántos segundos se consulta a Windows (no avisa por sí solo de las nuevas).
		"intervalo_s": 3,
		"anunciar_nuevas": False,
		"anunciar_texto": True,
		"marcar_leida_al_ver": True,
		# Aplicaciones cuyas notificaciones no se guardan, separadas por comas.
		"apps_ignoradas": "",
		# 0 = sin límite. Las favoritas no se borran nunca solas.
		"maximo": 5000,
		"dias": 90,
	},
	"ventanas": {
		# Al mover la ventana activa a otro escritorio, ir con ella.
		"seguir_ventana": False,
		"aplicar_reglas_al_iniciar": False,
	},
	# Atajos cambiados por el usuario: {accion: "Ctrl+Alt+Win+X"}; "" = sin atajo.
	"teclas": {},
	# Reglas de ventanas (lista de diccionarios, ver app/services/reglas.py).
	"reglas": [],
	"ventana": {
		# -1 = sin posición guardada: se centra en la pantalla.
		"x": -1,
		"y": -1,
		"ancho": 800,
		"alto": 600,
		"maximizada": False,
		"barra_estado": True,
	},
	"registro": {
		"nivel": "INFO",
	},
}


def _tipo_compatible(valor: Any, referencia: Any) -> bool:
	"""Indica si ``valor`` tiene un tipo aceptable para la clave de ``referencia``.

	``bool`` es subclase de ``int`` en Python; se trata aparte para que
	``"maximizada": 1`` no cuele como booleano ni ``True`` como tamaño.
	"""
	if referencia is None:
		return True
	if isinstance(referencia, bool):
		return isinstance(valor, bool)
	if isinstance(referencia, (int, float)):
		return isinstance(valor, (int, float)) and not isinstance(valor, bool)
	return isinstance(valor, type(referencia))


class Configuracion:
	"""Almacén de configuración con claves en notación de puntos (``"ventana.ancho"``)."""

	def __init__(self, ruta: Path | None = None) -> None:
		"""Carga la configuración del disco o, si no existe, los valores por defecto.

		:param ruta: archivo alternativo (pruebas); por defecto ``data/config/config.json``.
		"""
		self._candado = threading.RLock()
		self._ruta = ruta or (paths.ruta_configuracion() / NOMBRE_ARCHIVO)
		self._datos: dict[str, Any] = copy.deepcopy(VALORES_POR_DEFECTO)
		self._cargar()

	@property
	def ruta(self) -> Path:
		"""Archivo donde se guarda la configuración."""
		return self._ruta

	def _cargar(self) -> None:
		"""Lee el JSON y lo fusiona sobre los valores por defecto."""
		if not self._ruta.is_file():
			log.info("No hay configuración guardada; se usan los valores por defecto.")
			return
		try:
			guardado = json.loads(self._ruta.read_text(encoding="utf-8"))
		except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
			self._apartar_danado(f"{type(error).__name__}: {error}")
			return
		if not isinstance(guardado, dict):
			self._apartar_danado("el contenido no es un objeto JSON")
			return
		self._fusionar(self._datos, guardado, VALORES_POR_DEFECTO, "")

	def _apartar_danado(self, motivo: str) -> None:
		"""Renombra un archivo ilegible y sigue con los valores por defecto."""
		copia = self._ruta.with_name(f"{self._ruta.stem}.danado-{time.strftime('%Y%m%d-%H%M%S')}.json")
		log.warning(
			"La configuración %s está dañada (%s); se aparta como %s y se usan los valores por defecto.",
			self._ruta,
			motivo,
			copia.name,
		)
		try:
			os.replace(self._ruta, copia)
		except OSError:
			log.exception("No se pudo apartar la configuración dañada %s", self._ruta)

	def _fusionar(self, destino: dict[str, Any], origen: dict[str, Any], referencia: dict[str, Any], prefijo: str) -> None:
		"""Copia ``origen`` sobre ``destino`` validando el tipo de las claves conocidas.

		Las claves desconocidas se conservan (pueden ser de una versión más nueva
		o de un complemento); las conocidas con un tipo erróneo se descartan.
		"""
		for clave, valor in origen.items():
			ruta_clave = f"{prefijo}{clave}"
			if clave not in referencia:
				destino[clave] = valor
				continue
			esperado = referencia[clave]
			if isinstance(esperado, dict):
				if isinstance(valor, dict):
					self._fusionar(destino[clave], valor, esperado, ruta_clave + ".")
				else:
					log.warning("Configuración: «%s» debería ser una sección; se ignora el valor guardado.", ruta_clave)
			elif _tipo_compatible(valor, esperado):
				destino[clave] = valor
			else:
				log.warning("Configuración: «%s» tiene un valor no válido (%r); se usa %r.", ruta_clave, valor, esperado)

	def obtener(self, clave: str, defecto: Any = None) -> Any:
		"""Devuelve una COPIA del valor de ``clave`` o ``defecto`` si no existe.

		Se devuelve una copia para que nadie modifique la configuración en
		memoria sin pasar por ``establecer`` (y sin candado).
		"""
		with self._candado:
			actual: Any = self._datos
			for parte in clave.split("."):
				if not isinstance(actual, dict) or parte not in actual:
					return defecto
				actual = actual[parte]
			return copy.deepcopy(actual)

	def establecer(self, clave: str, valor: Any) -> None:
		"""Asigna ``valor`` a ``clave`` en memoria (se escribe al llamar a ``guardar``)."""
		partes = clave.split(".")
		with self._candado:
			actual = self._datos
			for parte in partes[:-1]:
				siguiente = actual.get(parte)
				if not isinstance(siguiente, dict):
					siguiente = {}
					actual[parte] = siguiente
				actual = siguiente
			actual[partes[-1]] = copy.deepcopy(valor)

	def guardar(self) -> bool:
		"""Escribe la configuración de forma atómica. Devuelve ``True`` si lo consiguió.

		No lanza excepciones: se llama al cerrar la aplicación y un disco lleno
		no debe impedir que la ventana se cierre. El fallo queda en el registro.
		"""
		with self._candado:
			texto = json.dumps(self._datos, ensure_ascii=False, indent="\t")
			temporal = self._ruta.with_name(self._ruta.name + ".tmp")
			try:
				self._ruta.parent.mkdir(parents=True, exist_ok=True)
				with open(temporal, "w", encoding="utf-8", newline="\n") as archivo:
					archivo.write(texto)
					archivo.flush()
					os.fsync(archivo.fileno())
				os.replace(temporal, self._ruta)
			except OSError:
				log.exception("No se pudo guardar la configuración en %s", self._ruta)
				try:
					temporal.unlink(missing_ok=True)
				except OSError:
					log.debug("No se pudo borrar el temporal %s", temporal, exc_info=True)
				return False
		log.debug("Configuración guardada en %s", self._ruta)
		return True
