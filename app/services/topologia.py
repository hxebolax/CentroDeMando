"""Controles de hardware de un dispositivo de audio: amplificación del micrófono (sin wx).

La «Amplificación de micrófono» (Microphone Boost) del Panel de sonido, pestaña
Niveles, no está en ``IAudioEndpointVolume``: es un control del controlador
(KS) dentro de la *topología* del dispositivo. Se llega así:

1. ``IMMDevice::Activate(IDeviceTopology)`` del micrófono.
2. Su conector 0 → ``GetConnectedTo``: el conector del adaptador (un ``IPart``).
3. Desde ahí se recorren las piezas hacia la fuente de la señal y, en cada
   una, sus interfaces de control. Las ``IAudioVolumeLevel`` cuyo margen en
   decibelios es distinto del volumen del propio micrófono son las de
   amplificación (habitualmente de 0 a +30 dB en pasos de 10).

Referencia: AltMixer (adjuntos/M0LTE_altmixer, src/AltMixer.Core/Audio/Topology.cs)
y la documentación de Microsoft de DeviceTopology. Las interfaces se declaran
aquí con el orden exacto de sus métodos: un orden equivocado tumbaría el proceso.
Muchos micrófonos USB y Bluetooth no tienen amplificación: entonces la lista
sale vacía.
"""

from __future__ import annotations

import ctypes
import logging
from ctypes import HRESULT, POINTER, c_float, c_int, c_uint
from ctypes.wintypes import BOOL, LPWSTR
from dataclasses import dataclass

log = logging.getLogger(__name__)

_interfaces: dict | None = None


def _definir() -> dict:
	"""Declara las interfaces COM la primera vez (importar comtypes es lento)."""
	global _interfaces
	if _interfaces is not None:
		return _interfaces
	from comtypes import COMMETHOD, GUID, IUnknown

	class IPartsList(IUnknown):
		_iid_ = GUID("{6DAA848C-5EB0-45CC-AEA5-998A2CDA1FFB}")

	class IPart(IUnknown):
		_iid_ = GUID("{AE2DE0E4-5BCA-4F2D-AA46-5D13F8FDB3A9}")

	class IConnector(IUnknown):
		_iid_ = GUID("{9c2c4058-23f5-41de-877a-df3af236a09e}")

	class IDeviceTopology(IUnknown):
		_iid_ = GUID("{2A07407E-6497-4A18-9787-32F79BD0D98F}")

	class IControlInterface(IUnknown):
		_iid_ = GUID("{45d37c3f-5140-444a-ae24-400789f3cbf3}")

	class IAudioVolumeLevel(IUnknown):
		_iid_ = GUID("{7FB7B48F-531D-44A2-BCB3-5AD5A134B3DC}")

	class IAudioAutoGainControl(IUnknown):
		_iid_ = GUID("{85401FD4-6DE4-4b9d-9869-2D6753A82F3C}")

	IPartsList._methods_ = [
		COMMETHOD([], HRESULT, "GetCount", (["out"], POINTER(c_uint), "cuenta")),
		COMMETHOD([], HRESULT, "GetPart", (["in"], c_uint, "indice"), (["out"], POINTER(POINTER(IPart)), "pieza")),
	]
	IControlInterface._methods_ = [
		COMMETHOD([], HRESULT, "GetName", (["out"], POINTER(LPWSTR), "nombre")),
		COMMETHOD([], HRESULT, "GetIID", (["out"], POINTER(GUID), "iid")),
	]
	IPart._methods_ = [
		COMMETHOD([], HRESULT, "GetName", (["out"], POINTER(LPWSTR), "nombre")),
		COMMETHOD([], HRESULT, "GetLocalId", (["out"], POINTER(c_uint), "id")),
		COMMETHOD([], HRESULT, "GetGlobalId", (["out"], POINTER(LPWSTR), "id")),
		COMMETHOD([], HRESULT, "GetPartType", (["out"], POINTER(c_int), "tipo")),
		COMMETHOD([], HRESULT, "GetSubType", (["out"], POINTER(GUID), "subtipo")),
		COMMETHOD([], HRESULT, "GetControlInterfaceCount", (["out"], POINTER(c_uint), "cuenta")),
		COMMETHOD([], HRESULT, "GetControlInterface", (["in"], c_uint, "indice"), (["out"], POINTER(POINTER(IControlInterface)), "control")),
		COMMETHOD([], HRESULT, "EnumPartsIncoming", (["out"], POINTER(POINTER(IPartsList)), "piezas")),
		COMMETHOD([], HRESULT, "EnumPartsOutgoing", (["out"], POINTER(POINTER(IPartsList)), "piezas")),
		COMMETHOD([], HRESULT, "GetTopologyObject", (["out"], POINTER(POINTER(IDeviceTopology)), "topologia")),
		COMMETHOD(
			[],
			HRESULT,
			"Activate",
			(["in"], c_uint, "contexto"),
			(["in"], POINTER(GUID), "iid"),
			(["out"], POINTER(POINTER(IUnknown)), "interfaz"),
		),
		COMMETHOD([], HRESULT, "RegisterControlChangeCallback", (["in"], POINTER(GUID), "iid"), (["in"], ctypes.c_void_p, "aviso")),
		COMMETHOD([], HRESULT, "UnregisterControlChangeCallback", (["in"], ctypes.c_void_p, "aviso")),
	]
	IConnector._methods_ = [
		COMMETHOD([], HRESULT, "GetType", (["out"], POINTER(c_int), "tipo")),
		COMMETHOD([], HRESULT, "GetDataFlow", (["out"], POINTER(c_int), "flujo")),
		COMMETHOD([], HRESULT, "ConnectTo", (["in"], POINTER(IConnector), "otro")),
		COMMETHOD([], HRESULT, "Disconnect"),
		COMMETHOD([], HRESULT, "IsConnected", (["out"], POINTER(BOOL), "conectado")),
		COMMETHOD([], HRESULT, "GetConnectedTo", (["out"], POINTER(POINTER(IConnector)), "otro")),
		COMMETHOD([], HRESULT, "GetConnectorIdConnectedTo", (["out"], POINTER(LPWSTR), "id")),
		COMMETHOD([], HRESULT, "GetDeviceIdConnectedTo", (["out"], POINTER(LPWSTR), "id")),
	]
	IDeviceTopology._methods_ = [
		COMMETHOD([], HRESULT, "GetConnectorCount", (["out"], POINTER(c_uint), "cuenta")),
		COMMETHOD([], HRESULT, "GetConnector", (["in"], c_uint, "indice"), (["out"], POINTER(POINTER(IConnector)), "conector")),
		COMMETHOD([], HRESULT, "GetSubunitCount", (["out"], POINTER(c_uint), "cuenta")),
		COMMETHOD([], HRESULT, "GetSubunit", (["in"], c_uint, "indice"), (["out"], POINTER(ctypes.c_void_p), "subunidad")),
		COMMETHOD([], HRESULT, "GetPartById", (["in"], c_uint, "id"), (["out"], POINTER(POINTER(IPart)), "pieza")),
		COMMETHOD([], HRESULT, "GetDeviceId", (["out"], POINTER(LPWSTR), "id")),
		COMMETHOD(
			[],
			HRESULT,
			"GetSignalPath",
			(["in"], POINTER(IPart), "desde"),
			(["in"], POINTER(IPart), "hasta"),
			(["in"], BOOL, "rechazarMezclas"),
			(["out"], POINTER(POINTER(IPartsList)), "piezas"),
		),
	]
	# IAudioVolumeLevel hereda de IPerChannelDbLevel sin añadir métodos.
	IAudioVolumeLevel._methods_ = [
		COMMETHOD([], HRESULT, "GetChannelCount", (["out"], POINTER(c_uint), "cuenta")),
		COMMETHOD(
			[],
			HRESULT,
			"GetLevelRange",
			(["in"], c_uint, "canal"),
			(["out"], POINTER(c_float), "minimo"),
			(["out"], POINTER(c_float), "maximo"),
			(["out"], POINTER(c_float), "paso"),
		),
		COMMETHOD([], HRESULT, "GetLevel", (["in"], c_uint, "canal"), (["out"], POINTER(c_float), "nivel")),
		COMMETHOD([], HRESULT, "SetLevel", (["in"], c_uint, "canal"), (["in"], c_float, "nivel"), (["in"], POINTER(GUID), "contexto")),
		COMMETHOD([], HRESULT, "SetLevelUniform", (["in"], c_float, "nivel"), (["in"], POINTER(GUID), "contexto")),
		COMMETHOD(
			[],
			HRESULT,
			"SetLevelAllChannels",
			(["in"], POINTER(c_float), "niveles"),
			(["in"], c_uint, "cuenta"),
			(["in"], POINTER(GUID), "contexto"),
		),
	]
	IAudioAutoGainControl._methods_ = [
		COMMETHOD([], HRESULT, "GetEnabled", (["out"], POINTER(BOOL), "activo")),
		COMMETHOD([], HRESULT, "SetEnabled", (["in"], BOOL, "activo"), (["in"], POINTER(GUID), "contexto")),
	]
	_interfaces = {
		"IDeviceTopology": IDeviceTopology,
		"IConnector": IConnector,
		"IPart": IPart,
		"IAudioVolumeLevel": IAudioVolumeLevel,
		"IAudioAutoGainControl": IAudioAutoGainControl,
	}
	return _interfaces


@dataclass
class Amplificacion:
	"""Un control de amplificación de un micrófono (en decibelios)."""

	nombre: str
	minimo: float
	maximo: float
	paso: float
	nivel: float
	_control: object = None

	def describir(self) -> str:
		return f"{self.nombre}: {formatear_db(self.nivel)} (de {formatear_db(self.minimo)} a {formatear_db(self.maximo)})"


def formatear_db(valor: float) -> str:
	"""«+20 dB», «0 dB», «-6,5 dB» (función pura)."""
	redondeado = round(valor, 1)
	texto = f"{redondeado:+.1f}".replace(".", ",").replace(",0", "")
	return ("0" if texto in ("+0", "-0") else texto) + " dB"


def pasos_validos(minimo: float, maximo: float, paso: float) -> list[float]:
	"""Valores que admite el control, de menor a mayor (función pura)."""
	if paso <= 0 or maximo <= minimo:
		return [minimo]
	cuenta = int(round((maximo - minimo) / paso))
	return [round(minimo + i * paso, 2) for i in range(min(cuenta, 200) + 1)]


def _piezas(pieza, entrantes: bool) -> list:
	try:
		lista = pieza.EnumPartsIncoming() if entrantes else pieza.EnumPartsOutgoing()
		return [lista.GetPart(i) for i in range(lista.GetCount())]
	except Exception:  # noqa: BLE001 - extremo del recorrido
		return []


def buscar_amplificaciones(identificador: str) -> list[Amplificacion]:
	"""Controles de amplificación del micrófono ``identificador`` (lista vacía si no tiene)."""
	from comtypes import CLSCTX_ALL
	from pycaw.pycaw import AudioUtilities

	interfaces = _definir()
	try:
		dispositivo = AudioUtilities.GetDeviceEnumerator().GetDevice(identificador)
		topologia = dispositivo.Activate(interfaces["IDeviceTopology"]._iid_, CLSCTX_ALL, None).QueryInterface(interfaces["IDeviceTopology"])
		inicio = topologia.GetConnector(0).GetConnectedTo().QueryInterface(interfaces["IPart"])
		volumen = dispositivo.Activate(
			__import__("pycaw.api.endpointvolume", fromlist=["IAudioEndpointVolume"]).IAudioEndpointVolume._iid_, CLSCTX_ALL, None
		)
		from pycaw.api.endpointvolume import IAudioEndpointVolume

		margen = volumen.QueryInterface(IAudioEndpointVolume).GetVolumeRange()
	except Exception:  # noqa: BLE001 - dispositivo sin topología (virtual, Bluetooth...)
		log.debug("Sin topología para %s", identificador, exc_info=True)
		return []
	resultado: list[Amplificacion] = []
	vistas: set[str] = set()
	pendientes = [(inicio, 0)]
	while pendientes:
		pieza, profundidad = pendientes.pop()
		try:
			global_id = pieza.GetGlobalId()
		except Exception:  # noqa: BLE001
			continue
		if global_id in vistas or profundidad > 40:
			continue
		vistas.add(global_id)
		try:
			nombre = pieza.GetName() or ""
			for indice in range(pieza.GetControlInterfaceCount()):
				iid = pieza.GetControlInterface(indice).GetIID()
				if iid != interfaces["IAudioVolumeLevel"]._iid_:
					continue
				control = pieza.Activate(CLSCTX_ALL, iid).QueryInterface(interfaces["IAudioVolumeLevel"])
				minimo, maximo, paso = control.GetLevelRange(0)
				# El volumen del propio micrófono tiene el mismo margen que el del extremo: no es amplificación.
				if abs(minimo - margen[0]) < 0.01 and abs(maximo - margen[1]) < 0.01:
					continue
				if maximo <= 0:
					continue
				resultado.append(Amplificacion(nombre or "Amplificación", minimo, maximo, paso, control.GetLevel(0), control))
		except Exception:  # noqa: BLE001 - una pieza ilegible no detiene el recorrido
			log.debug("Pieza de topología ilegible", exc_info=True)
		# Hacia la fuente de la señal; los dos sentidos por si el controlador los dibuja al revés.
		for siguiente in _piezas(pieza, True) + _piezas(pieza, False):
			pendientes.append((siguiente, profundidad + 1))
	return resultado


def poner_amplificacion(amplificacion: Amplificacion, decibelios: float) -> float:
	"""Pone la amplificación (se ajusta al paso válido más cercano) y devuelve el nivel puesto."""
	from comtypes import GUID

	validos = pasos_validos(amplificacion.minimo, amplificacion.maximo, amplificacion.paso)
	nivel = min(validos, key=lambda v: abs(v - decibelios))
	amplificacion._control.SetLevelUniform(c_float(nivel), ctypes.byref(GUID()))
	amplificacion.nivel = float(amplificacion._control.GetLevel(0))
	return amplificacion.nivel
