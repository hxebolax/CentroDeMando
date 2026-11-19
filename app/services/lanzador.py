"""Lanzador y paleta de órdenes (sin wx).

Busca a la vez en:

- Programas instalados (de escritorio y de la Tienda), con ``Get-StartApps``:
  da el nombre visible y el identificador con el que los abre el menú Inicio.
  Tarda menos de un segundo; se lee en un hilo y se guarda en
  ``data/cache/programas.json`` para que la siguiente vez esté al instante.
- Ajustes de Windows (direcciones ``ms-settings:``) con nombres en español.
- Las acciones de Centro de Mando (las mismas de Teclas globales).
- Una calculadora: si lo escrito es una operación, el primer resultado es su
  valor (sin ``eval``: solo números, operadores y unas pocas funciones).

La búsqueda no distingue mayúsculas ni tildes y acepta trozos de palabras e
iniciales («bt» encuentra «Bluetooth»). Lo más usado sube.
"""

from __future__ import annotations

import ast
import json
import logging
import math
import operator
import os
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.core import paths
from app.services.emojis import normalizar

log = logging.getLogger(__name__)

TIPO_PROGRAMA = "Programa"
TIPO_AJUSTE = "Ajuste de Windows"
TIPO_ACCION = "Centro de Mando"
TIPO_RESULTADO = "Resultado"

CADUCIDAD_PROGRAMAS = 600  # segundos


@dataclass(frozen=True)
class Elemento:
	id: str
	nombre: str
	tipo: str
	destino: str = ""
	palabras: str = ""


AJUSTES: list[tuple[str, str, str]] = [
	("Pantalla", "ms-settings:display", "monitor resolución escala brillo"),
	("Sonido", "ms-settings:sound", "audio altavoces micrófono volumen"),
	("Dispositivos de sonido", "ms-settings:sound-devices", "audio salida entrada"),
	("Mezclador de volumen", "ms-settings:apps-volume", "audio aplicaciones volumen"),
	("Notificaciones", "ms-settings:notifications", "avisos no molestar"),
	("No molestar y asistente de concentración", "ms-settings:quiethours", "concentración silencio"),
	("Energía y batería", "ms-settings:powersleep", "suspensión apagado batería"),
	("Almacenamiento", "ms-settings:storagesense", "disco espacio liberar"),
	("Bluetooth y dispositivos", "ms-settings:bluetooth", "bt auriculares emparejar"),
	("Impresoras y escáneres", "ms-settings:printers", "imprimir"),
	("Ratón", "ms-settings:mousetouchpad", "puntero"),
	("Panel táctil", "ms-settings:devices-touchpad", "touchpad"),
	("Escritura y teclado", "ms-settings:typing", "teclado autocorrección"),
	("Red e Internet", "ms-settings:network", "conexión"),
	("Wifi", "ms-settings:network-wifi", "wi-fi inalámbrica red"),
	("Ethernet", "ms-settings:network-ethernet", "cable red"),
	("VPN", "ms-settings:network-vpn", "red privada"),
	("Modo avión", "ms-settings:network-airplanemode", "avión inalámbrico"),
	("Proxy", "ms-settings:network-proxy", "red"),
	("Personalización", "ms-settings:personalization", "tema fondo colores"),
	("Fondo de pantalla", "ms-settings:personalization-background", "escritorio imagen"),
	("Colores y modo oscuro", "ms-settings:colors", "oscuro claro tema"),
	("Barra de tareas", "ms-settings:taskbar", "bandeja iconos"),
	("Aplicaciones instaladas", "ms-settings:appsfeatures", "programas desinstalar"),
	("Aplicaciones predeterminadas", "ms-settings:defaultapps", "abrir con navegador"),
	("Aplicaciones de inicio", "ms-settings:startupapps", "arranque inicio automático"),
	("Cuentas", "ms-settings:yourinfo", "usuario perfil"),
	("Opciones de inicio de sesión", "ms-settings:signinoptions", "contraseña pin hello"),
	("Fecha y hora", "ms-settings:dateandtime", "reloj zona horaria"),
	("Idioma y región", "ms-settings:regionlanguage", "idioma teclado región"),
	("Voz", "ms-settings:speech", "reconocimiento de voz"),
	("Accesibilidad", "ms-settings:easeofaccess", "discapacidad"),
	("Narrador", "ms-settings:easeofaccess-narrator", "lector de pantalla"),
	("Lupa", "ms-settings:easeofaccess-magnifier", "ampliar zoom"),
	("Contraste", "ms-settings:easeofaccess-highcontrast", "alto contraste temas"),
	("Subtítulos", "ms-settings:easeofaccess-closedcaptions", "subtítulos"),
	("Teclado de accesibilidad", "ms-settings:easeofaccess-keyboard", "teclas especiales filtro teclado en pantalla"),
	("Privacidad y seguridad", "ms-settings:privacy", "permisos"),
	("Permiso de notificaciones", "ms-settings:privacy-notifications", "leer notificaciones aplicaciones"),
	("Micrófono, permisos", "ms-settings:privacy-microphone", "privacidad"),
	("Ubicación", "ms-settings:privacy-location", "gps privacidad"),
	("Windows Update", "ms-settings:windowsupdate", "actualizaciones parches"),
	("Seguridad de Windows", "windowsdefender:", "antivirus defender"),
	("Copia de seguridad", "ms-settings:backup", "onedrive respaldo"),
	("Recuperación", "ms-settings:recovery", "restablecer reinstalar"),
	("Información del sistema", "ms-settings:about", "acerca de nombre del equipo versión"),
	("Multitarea y escritorios", "ms-settings:multitasking", "ajustar ventanas escritorios virtuales alt tab"),
	("Juegos", "ms-settings:gaming-gamebar", "xbox game bar"),
	("Zona horaria", "ms-settings:dateandtime", "hora"),
	("Panel de control", "control", "clásico"),
	("Administrador de tareas", "taskmgr", "procesos rendimiento"),
	("Administrador de dispositivos", "devmgmt.msc", "controladores hardware"),
	("Símbolo del sistema", "cmd", "consola terminal"),
	("Explorador de archivos", "explorer", "carpetas"),
]


# ── Calculadora segura ───────────────────────────────────────────────────────

_OPERADORES = {
	ast.Add: operator.add,
	ast.Sub: operator.sub,
	ast.Mult: operator.mul,
	ast.Div: operator.truediv,
	ast.FloorDiv: operator.floordiv,
	ast.Mod: operator.mod,
	ast.Pow: operator.pow,
	ast.USub: operator.neg,
	ast.UAdd: operator.pos,
}
_FUNCIONES = {
	"raiz": math.sqrt,
	"sqrt": math.sqrt,
	"abs": abs,
	"redondear": round,
	"round": round,
	"sen": math.sin,
	"sin": math.sin,
	"cos": math.cos,
	"tan": math.tan,
	"log": math.log10,
	"ln": math.log,
}
_CONSTANTES = {"pi": math.pi, "e": math.e}


def _evaluar(nodo: ast.AST) -> float:
	if isinstance(nodo, ast.Expression):
		return _evaluar(nodo.body)
	if isinstance(nodo, ast.Constant) and isinstance(nodo.value, (int, float)) and not isinstance(nodo.value, bool):
		return nodo.value
	if isinstance(nodo, ast.BinOp) and type(nodo.op) in _OPERADORES:
		izquierda, derecha = _evaluar(nodo.left), _evaluar(nodo.right)
		if isinstance(nodo.op, ast.Pow) and abs(derecha) > 1000:
			raise ValueError("exponente demasiado grande")
		return _OPERADORES[type(nodo.op)](izquierda, derecha)
	if isinstance(nodo, ast.UnaryOp) and type(nodo.op) in _OPERADORES:
		return _OPERADORES[type(nodo.op)](_evaluar(nodo.operand))
	if isinstance(nodo, ast.Name) and nodo.id in _CONSTANTES:
		return _CONSTANTES[nodo.id]
	if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name) and nodo.func.id in _FUNCIONES and not nodo.keywords:
		return _FUNCIONES[nodo.func.id](*(_evaluar(a) for a in nodo.args))
	raise ValueError("no es una operación")


def calcular(texto: str) -> str | None:
	"""Resultado de una operación («2+2*3», «15% de 80», «raiz(2)»); ``None`` si no lo es.

	Acepta la coma decimal española, «x» y «×» para multiplicar, «÷» para dividir
	y «^» para potencias.
	"""
	texto = (texto or "").strip().lstrip("=").strip()
	if not texto or not any(c.isdigit() for c in texto):
		return None
	expresion = texto.casefold().replace("×", "*").replace("÷", "/").replace("^", "**").replace(",", ".")
	if " de " in expresion and "%" in expresion:  # «15% de 80»
		parte, total = expresion.split(" de ", 1)
		expresion = f"({parte.replace('%', '')})/100*({total})"
	expresion = expresion.replace("%", "/100")
	expresion = "".join("*" if c == "x" and i and (expresion[i - 1].isdigit() or expresion[i - 1] in " )") else c for i, c in enumerate(expresion))
	try:
		valor = _evaluar(ast.parse(expresion, mode="eval"))
	except (SyntaxError, ValueError, TypeError, ZeroDivisionError, OverflowError):
		return None
	if isinstance(valor, float):
		if valor.is_integer() and abs(valor) < 1e15:
			valor = int(valor)
		else:
			valor = round(valor, 10)
	resultado = str(valor)
	# Si no había ninguna operación («42»), no es un cálculo.
	if resultado == texto.replace(" ", ""):
		return None
	return resultado.replace(".", ",")


# ── Programas ────────────────────────────────────────────────────────────────


def leer_programas() -> list[Elemento]:
	"""Lista de programas del menú Inicio (unos 0,7 s): llamar desde un hilo."""
	if os.name != "nt":
		return []
	orden = ["powershell", "-NoProfile", "-NonInteractive", "-Command", "[Console]::OutputEncoding = [Text.Encoding]::UTF8; Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress"]
	try:
		salida = subprocess.run(
			orden, capture_output=True, timeout=20, check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
		).stdout  # noqa: S603, S607 - orden fija de Windows
		datos = json.loads(salida.decode("utf-8", "replace") or "[]")
	except (OSError, subprocess.SubprocessError, ValueError):
		log.warning("No se pudo leer la lista de programas", exc_info=True)
		return []
	if isinstance(datos, dict):
		datos = [datos]
	programas = []
	vistos = set()
	for dato in datos:
		nombre, aplicacion = str(dato.get("Name") or ""), str(dato.get("AppID") or "")
		if not nombre or not aplicacion or aplicacion in vistos:
			continue
		vistos.add(aplicacion)
		programas.append(Elemento(f"programa:{aplicacion}", nombre, TIPO_PROGRAMA, aplicacion))
	return programas


class CatalogoLanzador:
	"""Reúne las fuentes y busca. La lista de programas se refresca en segundo plano."""

	def __init__(self, acciones: list[Elemento], ruta_cache: Path | None = None, lector: Callable[[], list[Elemento]] = leer_programas) -> None:
		self._acciones = acciones
		self._ruta_cache = ruta_cache or (paths.subcarpeta("cache") / "programas.json")
		self._lector = lector
		self._candado = threading.Lock()
		self._programas: list[Elemento] = self._leer_cache()
		self._leidos = 0.0
		self._leyendo = False
		self._ajustes = [Elemento(f"ajuste:{uri}:{nombre}", nombre, TIPO_AJUSTE, uri, palabras) for nombre, uri, palabras in AJUSTES]

	def _leer_cache(self) -> list[Elemento]:
		try:
			return [Elemento(**d) for d in json.loads(self._ruta_cache.read_text(encoding="utf-8"))]
		except (OSError, ValueError, TypeError):
			return []

	def actualizar_programas(self, esperar: bool = False) -> None:
		"""Relee los programas en un hilo si la lista tiene más de 10 minutos."""
		with self._candado:
			if self._leyendo or time.monotonic() - self._leidos < CADUCIDAD_PROGRAMAS and self._leidos:
				return
			self._leyendo = True

		def trabajo() -> None:
			try:
				programas = self._lector()
				if programas:
					with self._candado:
						self._programas = programas
					try:
						self._ruta_cache.write_text(json.dumps([vars(p) for p in programas], ensure_ascii=False), encoding="utf-8")
					except OSError:
						log.debug("No se pudo guardar la caché de programas", exc_info=True)
			finally:
				with self._candado:
					self._leidos = time.monotonic()
					self._leyendo = False

		hilo = threading.Thread(target=trabajo, name="programas", daemon=True)
		hilo.start()
		if esperar:
			hilo.join(30)

	def elementos(self) -> list[Elemento]:
		with self._candado:
			programas = list(self._programas)
		return programas + self._ajustes + self._acciones

	def buscar(self, texto: str, usos: dict[str, int] | None = None, limite: int = 60) -> list[Elemento]:
		usos = usos or {}
		resultado: list[Elemento] = []
		calculo = calcular(texto)
		if calculo is not None:
			resultado.append(Elemento("resultado", f"= {calculo}", TIPO_RESULTADO, calculo))
		consulta = normalizar(texto).strip()
		if not consulta:
			# Sin texto: lo más usado.
			usados = sorted((e for e in self.elementos() if usos.get(e.id)), key=lambda e: -usos[e.id])
			return usados[:limite]
		puntuados = []
		for elemento in self.elementos():
			puntos = puntuar(consulta, normalizar(elemento.nombre), normalizar(elemento.palabras))
			if puntos is not None:
				puntuados.append((puntos - min(usos.get(elemento.id, 0), 20) * 0.5, elemento.nombre.casefold(), elemento))
		puntuados.sort(key=lambda p: (p[0], p[1]))
		return resultado + [p[2] for p in puntuados[:limite]]


def puntuar(consulta: str, nombre: str, palabras: str = "") -> float | None:
	"""Menos es mejor; ``None`` si no encaja.

	0 nombre exacto, 1 empieza igual, 2 alguna palabra empieza igual, 3 lo
	contiene, 4 las iniciales («bt» → «Bluetooth y dispositivos» no; «ae» →
	«Administrador de dispositivos»... sí), 5 en las palabras clave.
	"""
	if nombre == consulta:
		return 0
	if nombre.startswith(consulta):
		return 1
	terminos = consulta.split()
	palabras_nombre = nombre.replace("-", " ").split()
	if all(any(p.startswith(t) for p in palabras_nombre) for t in terminos):
		return 2
	if all(t in nombre for t in terminos):
		return 3
	iniciales = "".join(p[0] for p in palabras_nombre if p)
	if len(consulta) >= 2 and " " not in consulta and iniciales.startswith(consulta):
		return 4
	if palabras and all(t in palabras or t in nombre for t in terminos):
		return 5
	return None


def ejecutar_destino(elemento: Elemento) -> bool:
	"""Abre un programa o un ajuste. Las acciones y resultados los ejecuta la interfaz."""
	if os.name != "nt":
		return False
	if elemento.tipo == TIPO_PROGRAMA:
		destino = "shell:AppsFolder\\" + elemento.destino
	elif elemento.tipo == TIPO_AJUSTE:
		destino = elemento.destino
	else:
		return False
	try:
		os.startfile(destino)  # noqa: S606 - programa del menú Inicio o ajuste de Windows elegido por el usuario
		return True
	except OSError:
		log.info("os.startfile no abrió %s; se prueba con el Explorador", destino, exc_info=True)
	try:
		subprocess.Popen(["explorer.exe", destino], close_fds=True)  # noqa: S603, S607
		return True
	except OSError:
		log.warning("No se pudo abrir %s", destino, exc_info=True)
		return False
