"""Cifrado con la protección de datos de Windows (DPAPI), solo biblioteca estándar.

``CryptProtectData`` cifra con una clave ligada a la cuenta de Windows: solo
la misma persona, en el mismo equipo (o con su perfil itinerante), puede
descifrar. No hay contraseña que guardar ni que perder. Si alguien copia la
base de datos a otro equipo u otro usuario, no puede leerla.

Se añade una «entropía» propia del programa: otro programa de la misma
persona que llame a DPAPI sin ella tampoco puede descifrar estos datos.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

_ENTROPIA = b"CentroDeMando:portapapeles:v1"
_SIN_INTERFAZ = 0x1  # CRYPTPROTECT_UI_FORBIDDEN


class ErrorDpapi(Exception):
	"""No se pudo cifrar o descifrar (otro usuario, datos dañados...)."""


class _Blob(ctypes.Structure):
	_fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(datos: bytes) -> tuple[_Blob, ctypes.Array]:
	memoria = ctypes.create_string_buffer(datos, len(datos))
	return _Blob(len(datos), ctypes.cast(memoria, ctypes.POINTER(ctypes.c_char))), memoria


def _llamar(funcion, datos: bytes) -> bytes:
	entrada, _m1 = _blob(datos)
	entropia, _m2 = _blob(_ENTROPIA)
	salida = _Blob()
	if not funcion(ctypes.byref(entrada), None, ctypes.byref(entropia), None, None, _SIN_INTERFAZ, ctypes.byref(salida)):
		raise ErrorDpapi(f"DPAPI falló (error {ctypes.GetLastError()})")
	try:
		return ctypes.string_at(salida.pbData, salida.cbData)
	finally:
		ctypes.windll.kernel32.LocalFree(salida.pbData)


def cifrar(datos: bytes) -> bytes:
	if not datos:
		return b""
	return _llamar(ctypes.windll.crypt32.CryptProtectData, bytes(datos))


def descifrar(datos: bytes) -> bytes:
	if not datos:
		return b""
	return _llamar(ctypes.windll.crypt32.CryptUnprotectData, bytes(datos))
