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
CATEGORIA_PORTAPAPELES = "Portapapeles, fragmentos y emoticonos"
CATEGORIA_NOTIFICACIONES = "Notificaciones"
CATEGORIA_AUDIO = "Audio"
CATEGORIA_SISTEMA = "Sistema y energía"

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
	*[
		Accion(
			f"pegar_reciente_{n}",
			f"Pegar el elemento {n} del historial",
			f"Pega directamente el elemento número {n} del historial (1 = el último copiado) donde está el cursor, sin abrir ninguna ventana.",
			CATEGORIA_PORTAPAPELES,
			"",
		)
		for n in range(1, 10)
	],
	Accion(
		"fragmentos_rapido",
		"Fragmentos de texto",
		"Abre la lista de fragmentos desde cualquier programa; escriba la abreviatura e Intro para insertarlo donde estaba.",
		CATEGORIA_PORTAPAPELES,
		"Ctrl+Alt+Win+T",
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
	Accion("audio_siguiente_salida", "Pasar a la siguiente salida de audio", "Cambia el dispositivo de salida predeterminado al siguiente y dice su nombre.", CATEGORIA_AUDIO, "Ctrl+Alt+Win+O"),
	Accion("audio_subir", "Subir el volumen general", "Sube el volumen general de 5 en 5 y dice el nuevo valor.", CATEGORIA_AUDIO, "Ctrl+Alt+Win+Arriba"),
	Accion("audio_bajar", "Bajar el volumen general", "Baja el volumen general de 5 en 5 y dice el nuevo valor.", CATEGORIA_AUDIO, "Ctrl+Alt+Win+Abajo"),
	Accion(
		"audio_app_subir",
		"Subir el volumen de la aplicación activa",
		"Sube de 5 en 5 solo el volumen del programa que tiene el foco (también el de su reproductor interno, como en los navegadores).",
		CATEGORIA_AUDIO,
		"Ctrl+Alt+Mayús+Win+Arriba",
	),
	Accion("audio_app_bajar", "Bajar el volumen de la aplicación activa", "Baja de 5 en 5 solo el volumen del programa que tiene el foco.", CATEGORIA_AUDIO, "Ctrl+Alt+Mayús+Win+Abajo"),
	Accion("audio_app_silenciar", "Silenciar o activar la aplicación activa", "Silencia o vuelve a dar sonido solo al programa que tiene el foco.", CATEGORIA_AUDIO, "Ctrl+Alt+Mayús+Win+Fin"),
	Accion("audio_app_decir", "Decir el volumen de la aplicación activa", "Dice el volumen del programa que tiene el foco.", CATEGORIA_AUDIO, "Ctrl+Alt+Mayús+Win+Inicio"),
	Accion("audio_silenciar", "Silenciar o activar el sonido general", "Alterna el silencio de la salida predeterminada.", CATEGORIA_AUDIO, ""),
	Accion("audio_microfono", "Silenciar o activar el micrófono", "Alterna el silencio del micrófono predeterminado y lo anuncia.", CATEGORIA_AUDIO, "Ctrl+Alt+Win+M"),
	Accion("decir_audio", "Decir el estado del audio", "Dice la salida predeterminada y el volumen general.", CATEGORIA_AUDIO, ""),
	Accion("decir_estado_sistema", "Decir el estado del equipo", "Dice la batería, el procesador, la memoria y la red.", CATEGORIA_SISTEMA, "Ctrl+Alt+Win+F12"),
	Accion(
		"siempre_encima",
		"Poner o quitar la ventana activa siempre encima",
		"La ventana que tiene el foco queda por encima de todas las demás, o deja de estarlo.",
		CATEGORIA_VENTANAS,
		"Ctrl+Alt+Win+K",
	),
	Accion("nuevo_temporizador", "Nuevo temporizador", "Abre el cuadro para poner un temporizador.", CATEGORIA_SISTEMA, ""),
	Accion("nueva_alarma", "Nueva alarma o recordatorio", "Abre el cuadro para poner una alarma o un recordatorio a una hora.", CATEGORIA_SISTEMA, ""),
	Accion("decir_temporizadores", "Decir los temporizadores", "Dice cuánto les queda a los temporizadores y alarmas en marcha.", CATEGORIA_SISTEMA, ""),
	Accion("bloquear_equipo", "Bloquear el equipo", "Bloquea la sesión de Windows.", CATEGORIA_SISTEMA, ""),
	Accion("apagar_pantalla", "Apagar la pantalla", "Apaga el monitor; se enciende al tocar el teclado o el ratón.", CATEGORIA_SISTEMA, ""),
	Accion(
		"lanzador",
		"Lanzador",
		"Busca y abre programas, ajustes de Windows y cualquier acción de Centro de Mando; también calcula.",
		CATEGORIA_INFORMACION,
		"Ctrl+Alt+Win+Espacio",
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
