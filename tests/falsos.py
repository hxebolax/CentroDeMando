"""Motor de escritorios falso: permite probar el servicio y la interfaz sin tocar Windows.

Imita a ``MotorEscritorios``: números desde 1, una lista de escritorios con
identificador y nombre, y ventanas repartidas entre ellos.
"""

from __future__ import annotations

import itertools

from app.services.escritorios import ErrorEscritorios, InfoEscritorio, InfoVentana

_contador = itertools.count(1)


class MotorFalso:
	def __init__(self, nombres: list[str] | None = None, actual: int = 1) -> None:
		nombres = nombres if nombres is not None else ["", "Correo", "", "Trabajo"]
		self.escritorios: list[dict] = [{"id": f"id-{next(_contador)}", "nombre": n, "fondo": ""} for n in nombres]
		self.actual_id = self.escritorios[actual - 1]["id"]
		# hwnd → dict(titulo, proceso, id, anclada, app_anclada)
		self.ventanas_falsas: dict[int, dict] = {}
		self.cambios: list[int] = []
		self.enfocadas = 0
		self.fallar_una_vez = False
		self.reconexiones = 0

	# ── utilidades de prueba ────────────────────────────────────────────────

	def agregar_ventana(self, hwnd: int, numero: int, titulo: str = "Ventana", proceso: str = "prueba.exe", anclada: bool = False) -> None:
		self.ventanas_falsas[hwnd] = {
			"titulo": titulo,
			"proceso": proceso,
			"id": self.escritorios[numero - 1]["id"],
			"anclada": anclada,
			"app_anclada": False,
		}

	def numero_actual(self) -> int:
		return self._numero(self.actual_id)

	def _numero(self, identificador: str) -> int:
		return next((n for n, e in enumerate(self.escritorios, 1) if e["id"] == identificador), 0)

	def _comprobar(self) -> None:
		if self.fallar_una_vez:
			self.fallar_una_vez = False
			raise OSError("COM desconectado (simulado)")

	def _validar(self, numero: int) -> dict:
		if not 1 <= numero <= len(self.escritorios):
			raise ErrorEscritorios(f"No existe el escritorio {numero}")
		return self.escritorios[numero - 1]

	# ── API de MotorEscritorios ─────────────────────────────────────────────

	def reconectar(self) -> None:
		self.reconexiones += 1

	def total(self) -> int:
		return len(self.escritorios)

	def id_actual(self) -> str:
		self._comprobar()
		return self.actual_id

	def listar(self, con_fondo: bool = False) -> list[InfoEscritorio]:
		return [
			InfoEscritorio(n, e["id"], e["nombre"], e["id"] == self.actual_id, e["fondo"] if con_fondo else "")
			for n, e in enumerate(self.escritorios, 1)
		]

	def ventanas(self, excluir_pid: int = 0) -> list[InfoVentana]:
		resultado = []
		for hwnd, datos in self.ventanas_falsas.items():
			en_todos = datos["anclada"] or datos["app_anclada"]
			resultado.append(
				InfoVentana(
					hwnd,
					datos["titulo"],
					datos["proceso"],
					0 if en_todos else self._numero(datos["id"]),
					datos["id"],
					datos["anclada"],
					datos["app_anclada"],
				)
			)
		return resultado

	def ir_a(self, numero: int, animacion: bool = False) -> None:
		self._comprobar()
		self.actual_id = self._validar(numero)["id"]
		self.cambios.append(numero)

	def enfocar_ventana_superior(self, excluir_pid: int = 0) -> int:
		self.enfocadas += 1
		return 0

	def crear(self, nombre: str = "") -> int:
		self.escritorios.append({"id": f"id-{next(_contador)}", "nombre": nombre, "fondo": ""})
		return len(self.escritorios)

	def eliminar(self, numero: int, respaldo: int | None = None) -> None:
		if len(self.escritorios) <= 1:
			raise ErrorEscritorios("No se puede eliminar el único escritorio que queda.")
		eliminado = self._validar(numero)
		respaldo = respaldo or (numero - 1 if numero > 1 else 2)
		destino = self.escritorios[respaldo - 1]["id"]
		for datos in self.ventanas_falsas.values():
			if datos["id"] == eliminado["id"]:
				datos["id"] = destino
		if self.actual_id == eliminado["id"]:
			self.actual_id = destino
		self.escritorios.remove(eliminado)

	def renombrar(self, numero: int, nombre: str) -> None:
		self._validar(numero)["nombre"] = nombre

	def mover_escritorio(self, numero: int, nueva_posicion: int) -> None:
		escritorio = self.escritorios.pop(numero - 1)
		self.escritorios.insert(nueva_posicion - 1, escritorio)

	def poner_fondo(self, numero: int, ruta: str) -> None:
		self._validar(numero)["fondo"] = ruta

	def poner_fondo_todos(self, ruta: str) -> None:
		for escritorio in self.escritorios:
			escritorio["fondo"] = ruta

	def _ventana(self, hwnd: int) -> dict:
		if hwnd not in self.ventanas_falsas:
			raise ErrorEscritorios("La ventana ya no existe.")
		return self.ventanas_falsas[hwnd]

	def mover_ventana(self, hwnd: int, numero: int) -> None:
		self._ventana(hwnd)["id"] = self._validar(numero)["id"]

	def escritorio_de_ventana(self, hwnd: int) -> int:
		datos = self._ventana(hwnd)
		return 0 if datos["anclada"] else self._numero(datos["id"])

	def ventana_anclada(self, hwnd: int) -> bool:
		return self._ventana(hwnd)["anclada"]

	def anclar_ventana(self, hwnd: int, anclar: bool) -> None:
		self._ventana(hwnd)["anclada"] = anclar

	def app_anclada(self, hwnd: int) -> bool:
		return self._ventana(hwnd)["app_anclada"]

	def anclar_app(self, hwnd: int, anclar: bool) -> None:
		self._ventana(hwnd)["app_anclada"] = anclar

	def _vista(self, hwnd: int):  # usado por ir_a_ventana como respaldo
		raise ErrorEscritorios("sin vista")
