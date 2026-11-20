"""Dispositivo preferido: pasar solo a él cuando se conecta (sin wx, funciones puras).

La persona ordena por nombre los dispositivos que prefiere («Auriculares
Bluetooth» antes que «Altavoces»). Cuando se conecta o desconecta alguno,
se pone como predeterminado el primero de la lista que esté conectado. Así,
al encender los auriculares el sonido pasa a ellos y, al apagarlos, vuelve
al siguiente de la lista (lo que se suele pedir como «volver al anterior»).

Se guarda por nombre y no por identificador: Windows da otro identificador
al mismo aparato si cambia de puerto USB o se vuelve a emparejar.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from app.services.audio import Dispositivo


def elegir_preferido(preferencias: Sequence[str], conectados: Iterable[Dispositivo]) -> Dispositivo | None:
	"""El primer dispositivo de ``preferencias`` que esté conectado (o ``None``)."""
	por_nombre: dict[str, Dispositivo] = {}
	for dispositivo in conectados:
		por_nombre.setdefault(dispositivo.nombre.casefold(), dispositivo)
	for nombre in preferencias:
		elegido = por_nombre.get(str(nombre).casefold())
		if elegido is not None:
			return elegido
	return None


def cambio_necesario(preferencias: Sequence[str], conectados: Sequence[Dispositivo]) -> Dispositivo | None:
	"""El preferido, solo si NO es ya el predeterminado (si no, ``None``: no hay que hacer nada)."""
	elegido = elegir_preferido(preferencias, conectados)
	if elegido is None or elegido.predeterminado:
		return None
	return elegido


def filas_para_dialogo(preferencias: Sequence[str], conocidos: Iterable[str]) -> list[tuple[str, bool]]:
	"""(nombre, marcado) para la lista del diálogo: primero los preferidos en su orden
	(marcados) y después el resto de dispositivos conocidos (sin marcar), sin repetir."""
	filas: list[tuple[str, bool]] = []
	vistos: set[str] = set()
	for nombre in preferencias:
		clave = str(nombre).casefold()
		if nombre and clave not in vistos:
			filas.append((str(nombre), True))
			vistos.add(clave)
	for nombre in conocidos:
		clave = nombre.casefold()
		if nombre and clave not in vistos:
			filas.append((nombre, False))
			vistos.add(clave)
	return filas


def mover(filas: list, posicion: int, desplazamiento: int) -> int:
	"""Mueve la fila ``posicion`` arriba (-1) o abajo (+1); devuelve su nueva posición."""
	destino = posicion + desplazamiento
	if not (0 <= posicion < len(filas)) or not (0 <= destino < len(filas)):
		return posicion
	filas[posicion], filas[destino] = filas[destino], filas[posicion]
	return destino
