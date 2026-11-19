"""Acceso a los escritorios virtuales de Windows (sin wx).

Contiene:

- Los modelos de datos (``InfoEscritorio``, ``InfoVentana``) que viajan del
  hilo de escritorios a la interfaz: inmutables, para poder compartirlos entre
  hilos sin candados.
- Funciones puras (``calcular_destino``) que se prueban sin Windows.
- ``MotorEscritorios``: la única pieza que habla con Windows, a través de
  ``pyvda`` (interfaces COM no documentadas del Explorador).

Por qué ``pyvda``: es Python puro (comtypes), sigue los cambios de GUID de
cada versión de Windows 10 y 11 (incluida la 24H2 y posteriores) y sus
gestores COM son locales a cada hilo, lo que permite aislar todo el trabajo
en un hilo propio (``servicio.py``) sin bloquear la interfaz.

IMPORTANTE: un ``MotorEscritorios`` solo debe usarse desde el hilo que lo
creó (los objetos COM pertenecen a su apartamento).
"""

from __future__ import annotations

import builtins
import logging
from dataclasses import dataclass, field

from app.services import ventanas_win32 as w32

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class ErrorEscritorios(Exception):
	"""Fallo al hablar con el sistema de escritorios virtuales (mensaje para el usuario)."""


class FuncionNoDisponible(ErrorEscritorios):
	"""La versión de Windows no ofrece esta función."""


@dataclass(frozen=True)
class InfoEscritorio:
	"""Un escritorio virtual tal y como se ve en la Vista de tareas."""

	numero: int
	id: str
	nombre: str = ""
	actual: bool = False
	fondo: str = ""

	@property
	def nombre_visible(self) -> str:
		"""El nombre que enseña Windows: el propio o «Escritorio N» si no tiene."""
		return self.nombre or _("Escritorio {n}").format(n=self.numero)

	def describir(self, con_numero: bool = True) -> str:
		"""Texto para anunciar: «Escritorio 3» o «3, Trabajo»."""
		if not self.nombre:
			return self.nombre_visible
		if con_numero:
			return _("{n}, {nombre}").format(n=self.numero, nombre=self.nombre)
		return self.nombre


@dataclass(frozen=True)
class InfoVentana:
	"""Una ventana de las que aparecen en Alt+Tab."""

	hwnd: int
	titulo: str
	proceso: str = ""
	escritorio: int = 0  # 0 = en todos (anclada) o desconocido
	id_escritorio: str = ""
	anclada: bool = False
	app_anclada: bool = False

	@property
	def en_todos(self) -> bool:
		return self.anclada or self.app_anclada

	def describir(self) -> str:
		titulo = self.titulo or _("(sin título)")
		return f"{titulo} ({self.proceso})" if self.proceso else titulo


@dataclass
class EstadoEscritorios:
	"""Instantánea del estado conocido: lo que la interfaz pinta."""

	escritorios: tuple[InfoEscritorio, ...] = field(default_factory=tuple)
	actual: int = 0
	anterior: int = 0

	@property
	def total(self) -> int:
		return len(self.escritorios)

	def escritorio(self, numero: int) -> InfoEscritorio | None:
		if 1 <= numero <= len(self.escritorios):
			return self.escritorios[numero - 1]
		return None

	def escritorio_actual(self) -> InfoEscritorio | None:
		return self.escritorio(self.actual)


def calcular_destino(actual: int, total: int, paso: int, ciclico: bool) -> int:
	"""Número de escritorio al que lleva moverse ``paso`` posiciones desde ``actual``.

	Con ``ciclico`` se da la vuelta (del último al primero y al revés); sin él,
	se queda en el extremo. Devuelve ``actual`` si no hay a dónde ir.

	>>> calcular_destino(4, 4, 1, True)
	1
	>>> calcular_destino(1, 4, -1, False)
	1
	"""
	if total <= 0:
		return 0
	if not 1 <= actual <= total:
		actual = 1
	if ciclico:
		return (actual - 1 + paso) % total + 1
	return min(max(actual + paso, 1), total)


def buscar_por_nombre(escritorios: tuple[InfoEscritorio, ...] | list[InfoEscritorio], texto: str) -> InfoEscritorio | None:
	"""Busca un escritorio por número («3») o por nombre (sin distinguir mayúsculas).

	Primero la coincidencia exacta del nombre y después la que lo contenga.
	"""
	texto = (texto or "").strip()
	if not texto:
		return None
	if texto.isdigit():
		numero = int(texto)
		return escritorios[numero - 1] if 1 <= numero <= len(escritorios) else None
	minusculas = texto.casefold()
	for escritorio in escritorios:
		if escritorio.nombre_visible.casefold() == minusculas:
			return escritorio
	for escritorio in escritorios:
		if minusculas in escritorio.nombre_visible.casefold():
			return escritorio
	return None


class MotorEscritorios:
	"""Operaciones sobre los escritorios con ``pyvda``. Un objeto por hilo.

	Los números de escritorio empiezan en 1, como en la Vista de tareas.
	"""

	def __init__(self) -> None:
		try:
			import pyvda  # noqa: F401 - comprueba la disponibilidad
			from pyvda import pyvda as nucleo
		except Exception as error:  # noqa: BLE001 - NotImplementedError, COMError, ImportError...
			log.exception("No se pudo cargar pyvda")
			raise ErrorEscritorios(
				_("No se puede acceder a los escritorios virtuales de esta versión de Windows: {error}").format(error=error)
			) from error
		self._nucleo = nucleo
		self._pyvda = pyvda

	# ── Conexión ────────────────────────────────────────────────────────────

	def reconectar(self) -> None:
		"""Vuelve a pedir los gestores COM al Explorador (tras reiniciarse explorer.exe).

		Los gestores de pyvda son un ``threading.local``: reinicializarlo desde
		este hilo crea objetos nuevos solo para él.
		"""
		log.info("Reconectando con el gestor de escritorios del Explorador.")
		self._nucleo.managers.__init__()

	@property
	def _gestor(self):
		return self._nucleo.managers.manager_internal

	def _todos(self) -> list:
		from pyvda.com_defns import IVirtualDesktop

		return list(self._gestor.get_all_desktops().iter(IVirtualDesktop))

	def _por_numero(self, numero: int):
		escritorios = self._todos()
		if not 1 <= numero <= len(escritorios):
			raise ErrorEscritorios(_("No existe el escritorio {n}; hay {total}.").format(n=numero, total=len(escritorios)))
		return escritorios[numero - 1]

	@staticmethod
	def _id(escritorio) -> str:
		return str(escritorio.GetID())

	@staticmethod
	def _nombre(escritorio) -> str:
		try:
			return str(escritorio.GetName() or "")
		except Exception:  # noqa: BLE001 - versiones sin nombre
			log.debug("No se pudo leer el nombre del escritorio", exc_info=True)
			return ""

	@staticmethod
	def _fondo(escritorio) -> str:
		try:
			return str(escritorio.GetWallpaperPath() or "")
		except Exception:  # noqa: BLE001 - versiones sin fondo por escritorio
			return ""

	# ── Consultas ───────────────────────────────────────────────────────────

	def total(self) -> int:
		return int(self._gestor.GetCount())

	def id_actual(self) -> str:
		return self._id(self._gestor.get_current_desktop())

	def listar(self, con_fondo: bool = False) -> list[InfoEscritorio]:
		"""Todos los escritorios en el orden de la Vista de tareas."""
		actual = self.id_actual()
		resultado = []
		for numero, escritorio in enumerate(self._todos(), 1):
			identificador = self._id(escritorio)
			resultado.append(
				InfoEscritorio(
					numero=numero,
					id=identificador,
					nombre=self._nombre(escritorio),
					actual=identificador == actual,
					fondo=self._fondo(escritorio) if con_fondo else "",
				)
			)
		return resultado

	def ventanas(self, excluir_pid: int = 0) -> list[InfoVentana]:
		"""Ventanas de Alt+Tab de todos los escritorios, de la más reciente a la más antigua."""
		from pyvda.com_defns import IApplicationView

		numeros = {self._id(e): n for n, e in enumerate(self._todos(), 1)}
		vistas = self._nucleo.managers.view_collection.GetViewsByZOrder()
		resultado = []
		for vista_com in vistas.iter(IApplicationView):
			try:
				vista = self._nucleo.AppView(view=vista_com)
				if not vista.is_shown_in_switchers():
					continue
				hwnd = int(vista.hwnd)
				if excluir_pid and w32.pid(hwnd) == excluir_pid:
					continue
				anclada = bool(vista.is_pinned())
				try:
					app_anclada = bool(vista.is_app_pinned())
				except Exception:  # noqa: BLE001 - ventanas sin identificador de aplicación
					app_anclada = False
				try:
					identificador = str(vista.desktop_id)
				except Exception:  # noqa: BLE001 - algunas vistas no tienen escritorio
					identificador = ""
				resultado.append(
					InfoVentana(
						hwnd=hwnd,
						titulo=w32.titulo(hwnd),
						proceso=w32.nombre_proceso(hwnd),
						escritorio=0 if anclada or app_anclada else numeros.get(identificador, 0),
						id_escritorio=identificador,
						anclada=anclada,
						app_anclada=app_anclada,
					)
				)
			except Exception:  # noqa: BLE001 - una ventana cerrándose no debe tumbar la lista
				log.debug("Se omite una vista que no se pudo leer", exc_info=True)
		return resultado

	# ── Cambiar de escritorio ───────────────────────────────────────────────

	def ir_a(self, numero: int, animacion: bool = False) -> None:
		"""Cambia al escritorio ``numero``."""
		destino = self._por_numero(numero)
		w32.permitir_primer_plano()
		if animacion and hasattr(self._gestor, "SwitchDesktopWithAnimation"):
			try:
				self._gestor.SwitchDesktopWithAnimation(destino)
				return
			except Exception:  # noqa: BLE001 - si falla la animación, cambio normal
				log.debug("SwitchDesktopWithAnimation falló; se usa el cambio normal", exc_info=True)
		self._gestor.switch_desktop(destino)

	def enfocar_ventana_superior(self, excluir_pid: int = 0) -> int:
		"""Da el foco a la ventana más reciente del escritorio actual. Devuelve su hwnd o 0.

		Sin esto, al cambiar de escritorio por programa el foco se queda en la
		barra de tareas o en ninguna parte, y el lector de pantalla calla.
		"""
		actual = self.id_actual()
		for ventana in self.ventanas(excluir_pid):
			if ventana.id_escritorio == actual and not ventana.en_todos:
				if w32.activar(ventana.hwnd):
					return ventana.hwnd
				try:
					self._nucleo.AppView(hwnd=ventana.hwnd).set_focus()
					return ventana.hwnd
				except Exception:  # noqa: BLE001 - se prueba con la siguiente
					log.debug("No se pudo enfocar %s", ventana.hwnd, exc_info=True)
		escritorio = w32.ventana_del_escritorio()
		if escritorio:
			w32.activar(escritorio)
		return 0

	# ── Crear, eliminar, renombrar, ordenar ─────────────────────────────────

	def crear(self, nombre: str = "") -> int:
		"""Crea un escritorio al final y devuelve su número."""
		nuevo = self._gestor.create_desktop()
		if nombre:
			self._poner_nombre(nuevo, nombre)
		return self.total()

	def eliminar(self, numero: int, respaldo: int | None = None) -> None:
		"""Elimina el escritorio; sus ventanas pasan a ``respaldo`` (por defecto, uno vecino)."""
		escritorios = self._todos()
		if len(escritorios) <= 1:
			raise ErrorEscritorios(_("No se puede eliminar el único escritorio que queda."))
		if not 1 <= numero <= len(escritorios):
			raise ErrorEscritorios(_("No existe el escritorio {n}.").format(n=numero))
		if respaldo is None or respaldo == numero or not 1 <= respaldo <= len(escritorios):
			respaldo = numero - 1 if numero > 1 else 2
		self._gestor.RemoveDesktop(escritorios[numero - 1], escritorios[respaldo - 1])

	def renombrar(self, numero: int, nombre: str) -> None:
		self._poner_nombre(self._por_numero(numero), nombre)

	def _poner_nombre(self, escritorio, nombre: str) -> None:
		from pyvda.winstring import HSTRING

		segundo = getattr(self._nucleo.managers, "manager_internal2", None)
		if segundo is not None:
			segundo.SetName(escritorio, HSTRING(nombre))
		elif hasattr(self._gestor, "SetName"):
			self._gestor.SetName(escritorio, HSTRING(nombre))
		else:
			raise FuncionNoDisponible(_("Esta versión de Windows no permite poner nombre a los escritorios."))

	def mover_escritorio(self, numero: int, nueva_posicion: int) -> None:
		"""Cambia el orden: lleva el escritorio ``numero`` a ``nueva_posicion`` (1..total)."""
		escritorios = self._todos()
		if not (1 <= numero <= len(escritorios) and 1 <= nueva_posicion <= len(escritorios)):
			raise ErrorEscritorios(_("Posición no válida."))
		if not hasattr(self._gestor, "MoveDesktop"):
			raise FuncionNoDisponible(_("Esta versión de Windows no permite reordenar los escritorios."))
		try:
			self._gestor.MoveDesktop(escritorios[numero - 1], nueva_posicion - 1)
		except TypeError as error:
			# Las versiones de 2022 piden además un monitor (HWND) como segundo argumento.
			raise FuncionNoDisponible(_("Esta versión de Windows no permite reordenar los escritorios.")) from error

	def poner_fondo(self, numero: int, ruta: str) -> None:
		from pyvda.winstring import HSTRING

		if not hasattr(self._gestor, "SetWallpaper"):
			raise FuncionNoDisponible(_("Esta versión de Windows no permite un fondo por escritorio."))
		self._gestor.SetWallpaper(self._por_numero(numero), HSTRING(ruta))

	def poner_fondo_todos(self, ruta: str) -> None:
		from pyvda.winstring import HSTRING

		if not hasattr(self._gestor, "SetWallpaperForAllDesktops"):
			raise FuncionNoDisponible(_("Esta versión de Windows no permite cambiar el fondo de los escritorios."))
		self._gestor.SetWallpaperForAllDesktops(HSTRING(ruta))

	# ── Ventanas ────────────────────────────────────────────────────────────

	def _vista(self, hwnd: int):
		try:
			return self._nucleo.AppView(hwnd=hwnd)
		except Exception as error:  # noqa: BLE001 - la ventana pudo cerrarse
			raise ErrorEscritorios(_("La ventana ya no existe o no se puede mover.")) from error

	def mover_ventana(self, hwnd: int, numero: int) -> None:
		vista = self._vista(hwnd)
		try:
			vista.move(self._nucleo.VirtualDesktop(desktop=self._por_numero(numero)))
		except ErrorEscritorios:
			raise
		except Exception as error:  # noqa: BLE001 - ventanas elevadas o especiales
			log.warning("No se pudo mover la ventana %s al escritorio %s", hwnd, numero, exc_info=True)
			raise ErrorEscritorios(
				_(
					"Windows no deja mover esta ventana. Si es de un programa ejecutado como administrador, ejecute también Centro de Mando como administrador."
				)
			) from error

	def escritorio_de_ventana(self, hwnd: int) -> int:
		"""Número del escritorio de la ventana; 0 si está en todos o no se sabe."""
		vista = self._vista(hwnd)
		if vista.is_pinned():
			return 0
		identificador = str(vista.desktop_id)
		for numero, escritorio in enumerate(self._todos(), 1):
			if self._id(escritorio) == identificador:
				return numero
		return 0

	def ventana_anclada(self, hwnd: int) -> bool:
		return bool(self._vista(hwnd).is_pinned())

	def anclar_ventana(self, hwnd: int, anclar: bool) -> None:
		vista = self._vista(hwnd)
		if anclar:
			vista.pin()
		else:
			vista.unpin()

	def app_anclada(self, hwnd: int) -> bool:
		return bool(self._vista(hwnd).is_app_pinned())

	def anclar_app(self, hwnd: int, anclar: bool) -> None:
		vista = self._vista(hwnd)
		if vista.app_id is None:
			raise ErrorEscritorios(_("Esta ventana no pertenece a una aplicación que se pueda anclar."))
		if anclar:
			vista.pin_app()
		else:
			vista.unpin_app()
