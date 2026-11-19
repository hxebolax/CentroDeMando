"""Catálogo de acciones que se pueden asociar a teclas globales (sin wx).

Cada acción tiene un identificador estable (se guarda en la configuración),
un nombre y una descripción en español, una categoría y su atajo de fábrica.

Atajos de fábrica: casi todos con Ctrl+Alt+Win, una combinación que Windows
no usa y que no choca con los lectores de pantalla. Se evitan a propósito:

- Ctrl+Alt+flechas: NVDA y JAWS las usan para moverse por tablas.
- Ctrl+Win+Izquierda/Derecha/D/F4: ya son de Windows (se pueden hacer
  cíclicas con la opción avanzada de interceptarlas).
- Ctrl+Alt+Mayús+Win+letra: es la «tecla Office» y abre programas.
- Cualquier combinación con Win+L: bloquea el equipo.
"""

from __future__ import annotations

import builtins
from dataclasses import dataclass


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


CATEGORIA_CAMBIAR = "Cambiar de escritorio"
CATEGORIA_GESTIONAR = "Gestionar escritorios"
CATEGORIA_VENTANAS = "Ventanas"
CATEGORIA_INFORMACION = "Información y aplicación"
CATEGORIA_PORTAPAPELES = "Portapapeles y emoticonos"
CATEGORIA_NOTIFICACIONES = "Notificaciones"

# Cuántos escritorios tienen acción directa «Ir al escritorio N» (Ctrl+Alt+Win+1 … 0).
ESCRITORIOS_DIRECTOS = 10


@dataclass(frozen=True)
class Accion:
	id: str
	nombre: str
	descripcion: str
	categoria: str
	atajo: str = ""


def _directas() -> list[Accion]:
	acciones = []
	for numero in range(1, ESCRITORIOS_DIRECTOS + 1):
		tecla = str(numero % 10)
		acciones.append(
			Accion(
				f"ir_{numero}",
				f"Ir al escritorio {numero}",
				f"Cambia directamente al escritorio {numero}.",
				CATEGORIA_CAMBIAR,
				f"Ctrl+Alt+Win+{tecla}",
			)
		)
	for numero in range(1, ESCRITORIOS_DIRECTOS + 1):
		tecla = str(numero % 10)
		acciones.append(
			Accion(
				f"mover_ventana_{numero}",
				f"Mover la ventana activa al escritorio {numero}",
				f"Lleva la ventana que tiene el foco al escritorio {numero}.",
				CATEGORIA_VENTANAS,
				f"Ctrl+Alt+Mayús+Win+{tecla}",
			)
		)
	return acciones


ACCIONES: list[Accion] = [
	Accion(
		"siguiente",
		"Escritorio siguiente",
		"Va al escritorio de la derecha. Si la opción cíclica está activada, desde el último vuelve al primero.",
		CATEGORIA_CAMBIAR,
		"Ctrl+Alt+Win+Derecha",
	),
	Accion(
		"anterior",
		"Escritorio anterior",
		"Va al escritorio de la izquierda. Si la opción cíclica está activada, desde el primero salta al último.",
		CATEGORIA_CAMBIAR,
		"Ctrl+Alt+Win+Izquierda",
	),
	Accion("primero", "Primer escritorio", "Va al primer escritorio.", CATEGORIA_CAMBIAR, "Ctrl+Alt+Win+Inicio"),
	Accion("ultimo", "Último escritorio", "Va al último escritorio.", CATEGORIA_CAMBIAR, "Ctrl+Alt+Win+Fin"),
	Accion(
		"alternar",
		"Volver al escritorio anterior",
		"Alterna entre el escritorio actual y el último en el que estuvo, como Alt+Tab pero con escritorios.",
		CATEGORIA_CAMBIAR,
		"Ctrl+Alt+Win+Retroceso",
	),
	Accion(
		"selector",
		"Elegir escritorio de una lista",
		"Abre una lista rápida de escritorios: escriba el número o parte del nombre y pulse Intro.",
		CATEGORIA_CAMBIAR,
		"Ctrl+Alt+Win+S",
	),
	*[a for a in _directas() if a.id.startswith("ir_")],
	Accion("crear", "Crear un escritorio", "Crea un escritorio nuevo al final, sin cambiar a él.", CATEGORIA_GESTIONAR, "Ctrl+Alt+Win+N"),
	Accion("crear_e_ir", "Crear un escritorio e ir a él", "Crea un escritorio nuevo y cambia a él.", CATEGORIA_GESTIONAR, ""),
	Accion(
		"eliminar_actual",
		"Eliminar el escritorio actual",
		"Elimina el escritorio actual; sus ventanas pasan al escritorio vecino.",
		CATEGORIA_GESTIONAR,
		"Ctrl+Alt+Win+F4",
	),
	Accion(
		"renombrar_actual",
		"Cambiar el nombre del escritorio actual",
		"Abre un cuadro para escribir el nombre del escritorio actual.",
		CATEGORIA_GESTIONAR,
		"Ctrl+Alt+Win+R",
	),
	Accion(
		"mover_escritorio_izquierda",
		"Mover el escritorio actual a la izquierda",
		"Cambia el orden de los escritorios: el actual pasa una posición a la izquierda.",
		CATEGORIA_GESTIONAR,
		"",
	),
	Accion(
		"mover_escritorio_derecha",
		"Mover el escritorio actual a la derecha",
		"Cambia el orden de los escritorios: el actual pasa una posición a la derecha.",
		CATEGORIA_GESTIONAR,
		"",
	),
	Accion(
		"mover_ventana_siguiente",
		"Mover la ventana activa al escritorio siguiente",
		"Lleva la ventana que tiene el foco al escritorio de la derecha (cíclico si está activado).",
		CATEGORIA_VENTANAS,
		"Ctrl+Alt+Mayús+Win+Derecha",
	),
	Accion(
		"mover_ventana_anterior",
		"Mover la ventana activa al escritorio anterior",
		"Lleva la ventana que tiene el foco al escritorio de la izquierda (cíclico si está activado).",
		CATEGORIA_VENTANAS,
		"Ctrl+Alt+Mayús+Win+Izquierda",
	),
	Accion(
		"mover_ventana_nuevo",
		"Mover la ventana activa a un escritorio nuevo",
		"Crea un escritorio y lleva allí la ventana que tiene el foco.",
		CATEGORIA_VENTANAS,
		"",
	),
	*[a for a in _directas() if a.id.startswith("mover_ventana_")],
	Accion(
		"anclar_ventana",
		"Mostrar u ocultar la ventana activa en todos los escritorios",
		"Alterna si la ventana que tiene el foco aparece en todos los escritorios.",
		CATEGORIA_VENTANAS,
		"Ctrl+Alt+Win+P",
	),
	Accion(
		"anclar_aplicacion",
		"Mostrar u ocultar la aplicación activa en todos los escritorios",
		"Alterna si todas las ventanas de la aplicación activa aparecen en todos los escritorios.",
		CATEGORIA_VENTANAS,
		"",
	),
	Accion(
		"buscar_ventana",
		"Buscar una ventana en todos los escritorios",
		"Abre una lista con las ventanas de todos los escritorios; Intro cambia a su escritorio y la activa.",
		CATEGORIA_VENTANAS,
		"Ctrl+Alt+Win+B",
	),
	Accion(
		"portapapeles_rapido",
		"Historial del portapapeles",
		"Abre el historial del portapapeles desde cualquier programa; Intro pega el elemento elegido donde estaba.",
		CATEGORIA_PORTAPAPELES,
		"Ctrl+Alt+Win+V",
	),
	Accion(
		"emoticonos_rapido",
		"Emoticonos",
		"Abre la lista de emoticonos desde cualquier programa; Intro escribe el elegido donde estaba.",
		CATEGORIA_PORTAPAPELES,
		"Ctrl+Alt+Win+E",
	),
	Accion(
		"pausar_portapapeles",
		"Detener o reanudar la captura del portapapeles",
		"Mientras está detenida, lo que se copia no se guarda en el historial.",
		CATEGORIA_PORTAPAPELES,
		"",
	),
	Accion(
		"notificaciones_rapido",
		"Historial de notificaciones",
		"Abre el historial de notificaciones desde cualquier programa.",
		CATEGORIA_NOTIFICACIONES,
		"Ctrl+Alt+Win+A",
	),
	Accion(
		"leer_ultima_notificacion",
		"Decir la última notificación",
		"Lee la notificación más reciente y cuántas quedan sin leer.",
		CATEGORIA_NOTIFICACIONES,
		"Ctrl+Alt+Win+U",
	),
	Accion(
		"pausar_notificaciones",
		"Detener o reanudar la captura de notificaciones",
		"Mientras está detenida, las notificaciones nuevas no se guardan.",
		CATEGORIA_NOTIFICACIONES,
		"",
	),
	Accion(
		"anunciar_actual",
		"Decir el escritorio actual",
		"Anuncia el número y el nombre del escritorio actual y cuántos hay.",
		CATEGORIA_INFORMACION,
		"Ctrl+Alt+Win+I",
	),
	Accion(
		"anunciar_ventanas",
		"Decir las ventanas del escritorio actual",
		"Anuncia cuántas ventanas hay en el escritorio actual y sus títulos.",
		CATEGORIA_INFORMACION,
		"Ctrl+Alt+Win+W",
	),
	Accion(
		"mostrar_gestor",
		"Mostrar u ocultar Centro de Mando",
		"Muestra la ventana principal; si ya está delante, la oculta en la bandeja.",
		CATEGORIA_INFORMACION,
		"Ctrl+Alt+Win+G",
	),
]

POR_ID: dict[str, Accion] = {accion.id: accion for accion in ACCIONES}

# Acciones internas del gancho de Ctrl+Win+flechas (no configurables).
NATIVAS = {"nativa_siguiente": "siguiente", "nativa_anterior": "anterior"}


def atajos_de_fabrica() -> dict[str, str]:
	return {accion.id: accion.atajo for accion in ACCIONES}


def atajos_efectivos(guardados: dict[str, str] | None) -> dict[str, str]:
	"""Fusiona lo guardado sobre los de fábrica (una acción nueva recibe su atajo de fábrica).

	Un atajo guardado como cadena vacía significa «sin atajo» a propósito.
	"""
	resultado = atajos_de_fabrica()
	for accion, atajo in (guardados or {}).items():
		if accion in resultado and isinstance(atajo, str):
			resultado[accion] = atajo
	return resultado


def duplicados(atajos: dict[str, str]) -> dict[str, list[str]]:
	"""Combinaciones asignadas a más de una acción: ``{combinacion: [acciones]}``."""
	from app.services.teclas import normalizar

	vistos: dict[str, list[str]] = {}
	for accion, atajo in atajos.items():
		canonica = normalizar(atajo)
		if canonica:
			vistos.setdefault(canonica, []).append(accion)
	return {combinacion: acciones for combinacion, acciones in vistos.items() if len(acciones) > 1}
