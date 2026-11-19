"""Pruebas de la lógica sin interfaz: cálculo de destinos, teclas, reglas, acciones y el hilo de escritorios."""

from __future__ import annotations

import threading

import pytest

from app.services import acciones, sistema
from app.services.escritorios import InfoEscritorio, InfoVentana, buscar_por_nombre, calcular_destino
from app.services.reglas import Regla, buscar_regla, cargar_reglas, destino_de_regla
from app.services.teclas import MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, analizar, formatear, normalizar
from app.ui.controlador import componer_anuncio, describir_ventanas

from .conftest import esperar_servicio

# ── Destinos ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
	("actual", "total", "paso", "ciclico", "esperado"),
	[
		(1, 4, 1, True, 2),
		(4, 4, 1, True, 1),  # del último al primero
		(1, 4, -1, True, 4),  # del primero al último
		(4, 4, 1, False, 4),  # sin ciclo se queda en el extremo
		(1, 4, -1, False, 1),
		(2, 5, 7, True, 4),
		(1, 1, 1, True, 1),
		(9, 3, 1, True, 2),  # actual fuera de rango: se toma el 1
		(1, 0, 1, True, 0),
	],
)
def test_calcular_destino(actual, total, paso, ciclico, esperado):
	assert calcular_destino(actual, total, paso, ciclico) == esperado


def test_buscar_por_nombre():
	escritorios = [InfoEscritorio(1, "a"), InfoEscritorio(2, "b", "Correo"), InfoEscritorio(3, "c", "Correo personal")]
	assert buscar_por_nombre(escritorios, "2").numero == 2
	assert buscar_por_nombre(escritorios, "correo").numero == 2, "coincidencia exacta primero"
	assert buscar_por_nombre(escritorios, "personal").numero == 3
	assert buscar_por_nombre(escritorios, "escritorio 1").numero == 1, "el nombre visible por defecto también vale"
	assert buscar_por_nombre(escritorios, "9") is None
	assert buscar_por_nombre(escritorios, "") is None


def test_nombre_visible_y_descripcion():
	assert InfoEscritorio(3, "x").nombre_visible == "Escritorio 3"
	assert InfoEscritorio(3, "x").describir() == "Escritorio 3"
	assert InfoEscritorio(3, "x", "Trabajo").describir() == "3, Trabajo"
	assert InfoEscritorio(3, "x", "Trabajo").describir(con_numero=False) == "Trabajo"


# ── Teclas ──────────────────────────────────────────────────────────────────


def test_formatear_y_analizar_ida_y_vuelta():
	texto = formatear(MOD_CONTROL | MOD_ALT | MOD_WIN, 0x27)
	assert texto == "Ctrl+Alt+Win+Derecha"
	combinacion = analizar(texto)
	assert combinacion.modificadores == MOD_CONTROL | MOD_ALT | MOD_WIN
	assert combinacion.vk == 0x27


@pytest.mark.parametrize(
	("entrada", "canonica"),
	[
		("win+ctrl+alt+right", "Ctrl+Alt+Win+Derecha"),
		("Control+Shift+Windows+1", "Ctrl+Mayús+Win+1"),
		("ctrl+alt+num +", "Ctrl+Alt+Num +"),
		("Ctrl+Alt+Win+repág", "Ctrl+Alt+Win+RePág"),
		("ctrl+alt+supr", "Ctrl+Alt+Suprimir"),
		("Alt+F4", "Alt+F4"),
		("", ""),
		("Ctrl+Patata", ""),
		("Hiper+A", ""),
	],
)
def test_normalizar(entrada, canonica):
	assert normalizar(entrada) == canonica


def test_combinacion_sin_modificador_no_es_valida():
	assert not analizar("A").valida
	assert not analizar("Mayús+A").valida, "Mayúsculas sola no basta"
	assert analizar("Ctrl+Alt+Win+A").valida


def test_atajos_de_fabrica_validos_y_sin_repetir():
	fabrica = acciones.atajos_de_fabrica()
	for accion, atajo in fabrica.items():
		if atajo:
			combinacion = analizar(atajo)
			assert combinacion is not None and combinacion.valida, f"{accion}: {atajo}"
			# Nada de Ctrl+Alt+flechas sin Win: las usan los lectores para las tablas.
			assert combinacion.modificadores & MOD_WIN, f"{accion} debería usar Win: {atajo}"
			# Ctrl+Alt+Mayús+Win+letra es la tecla Office.
			if combinacion.modificadores == MOD_CONTROL | MOD_ALT | MOD_SHIFT | MOD_WIN:
				assert not ("A" <= str(combinacion).rsplit("+", 1)[-1] <= "Z" and len(str(combinacion).rsplit("+", 1)[-1]) == 1), atajo
	assert acciones.duplicados(fabrica) == {}


def test_atajos_efectivos_respetan_lo_guardado():
	efectivos = acciones.atajos_efectivos({"siguiente": "Ctrl+Alt+Win+X", "crear": "", "desconocida": "Ctrl+Alt+Q"})
	assert efectivos["siguiente"] == "Ctrl+Alt+Win+X"
	assert efectivos["crear"] == "", "vacío = sin atajo a propósito"
	assert "desconocida" not in efectivos
	assert efectivos["anterior"] == acciones.POR_ID["anterior"].atajo


def test_ids_de_acciones_unicos():
	ids = [a.id for a in acciones.ACCIONES]
	assert len(ids) == len(set(ids))


# ── Reglas ──────────────────────────────────────────────────────────────────


def test_reglas_coinciden_por_proceso_y_titulo():
	ventana = InfoVentana(1, "Bandeja de entrada - Thunderbird", "thunderbird.exe")
	assert Regla(proceso="Thunderbird", escritorio="2").coincide(ventana), "sin .exe y sin mayúsculas también vale"
	assert Regla(titulo="bandeja", escritorio="2").coincide(ventana)
	assert not Regla(proceso="firefox.exe", escritorio="2").coincide(ventana)
	assert not Regla(proceso="thunderbird.exe", titulo="redactar", escritorio="2").coincide(ventana)
	assert not Regla(proceso="thunderbird.exe", escritorio="2", activa=False).coincide(ventana)
	assert not Regla(proceso="thunderbird.exe").coincide(ventana), "sin destino no es válida"
	assert Regla(proceso="thunderbird.exe", anclar=True).coincide(ventana)


def test_reglas_orden_y_destino():
	ventana = InfoVentana(1, "x", "notepad.exe")
	primera = Regla(proceso="notepad.exe", escritorio="Notas")
	segunda = Regla(proceso="notepad.exe", escritorio="3")
	assert buscar_regla([primera, segunda], ventana) is primera
	escritorios = [InfoEscritorio(1, "a"), InfoEscritorio(2, "b", "Notas"), InfoEscritorio(3, "c")]
	assert destino_de_regla(primera, escritorios) == 2
	assert destino_de_regla(segunda, escritorios) == 3
	assert destino_de_regla(Regla(proceso="x", escritorio="Inexistente"), escritorios) == 0


def test_cargar_reglas_tolera_basura():
	reglas = cargar_reglas([{"proceso": "a.exe", "escritorio": 2, "anclar": "si"}, "basura", None, {"titulo": "t"}])
	assert len(reglas) == 2
	assert reglas[0].escritorio == "2" and reglas[0].anclar is False
	assert cargar_reglas("no es una lista") == []
	regla = Regla(nombre="n", proceso="p.exe", escritorio="1")
	assert cargar_reglas([regla.a_dict()]) == [regla]


# ── Anuncios y tonos ────────────────────────────────────────────────────────


def test_componer_anuncio():
	trabajo = InfoEscritorio(3, "x", "Trabajo")
	assert componer_anuncio(trabajo, 12) == "3, Trabajo"
	assert componer_anuncio(trabajo, 12, decir_numero=False) == "Trabajo"
	assert componer_anuncio(trabajo, 12, decir_total=True) == "3, Trabajo de 12"
	assert componer_anuncio(InfoEscritorio(2, "y"), 4, ventanas=0) == "Escritorio 2, vacío"
	assert componer_anuncio(InfoEscritorio(2, "y"), 4, ventanas=1) == "Escritorio 2, 1 ventana"
	assert componer_anuncio(InfoEscritorio(2, "y"), 4, ventanas=5) == "Escritorio 2, 5 ventanas"
	assert componer_anuncio(None, 4) == ""


def test_describir_ventanas():
	assert describir_ventanas([]) == "No hay ventanas en este escritorio."
	ventanas = [InfoVentana(i, f"V{i}", "p.exe") for i in range(12)]
	texto = describir_ventanas(ventanas, maximo=3)
	assert texto.startswith("12 ventanas: V0; V1; V2") and texto.endswith("y 9 más")


def test_tonos_ascendentes():
	frecuencias = [sistema.frecuencia_de(n) for n in range(1, 15)]
	assert frecuencias[0] == 440
	assert frecuencias == sorted(frecuencias) and len(set(frecuencias)) == len(frecuencias)


# ── Hilo de escritorios con motor falso ─────────────────────────────────────


def test_servicio_conecta_y_publica_estado(servicio_falso):
	estado = servicio_falso.estado
	assert servicio_falso.disponible
	assert estado.total == 4 and estado.actual == 1
	assert estado.escritorio(2).nombre == "Correo"


def test_siguiente_ciclico_y_no_ciclico(servicio_falso, motor_falso):
	cambios = []
	servicio_falso.al_cambiar_actual = lambda estado, origen: cambios.append((estado.actual, origen))
	servicio_falso.ir_a(4)
	servicio_falso.desplazar(1)  # cíclico por defecto: vuelve al 1
	assert esperar_servicio(servicio_falso)
	assert motor_falso.cambios == [4, 1]
	assert cambios == [(4, "interno"), (1, "interno")]
	errores = []
	servicio_falso.al_error = errores.append
	servicio_falso.preferencias_prueba.ciclico = False
	servicio_falso.desplazar(-1)
	assert esperar_servicio(servicio_falso)
	assert motor_falso.numero_actual() == 1
	assert errores == ["Ya está en el primer escritorio."]


def test_cambio_enfoca_la_ventana_si_se_pide(servicio_falso, motor_falso):
	servicio_falso.ir_a(2)
	assert esperar_servicio(servicio_falso)
	assert motor_falso.enfocadas == 1
	servicio_falso.preferencias_prueba.enfocar_al_cambiar = False
	servicio_falso.ir_a(3)
	assert esperar_servicio(servicio_falso)
	assert motor_falso.enfocadas == 1


def test_alternar_vuelve_al_anterior(servicio_falso, motor_falso):
	errores = []
	servicio_falso.al_error = errores.append
	servicio_falso.alternar()
	assert esperar_servicio(servicio_falso)
	assert errores, "sin historial todavía no hay a dónde volver"
	servicio_falso.ir_a(3)
	servicio_falso.alternar()
	servicio_falso.alternar()
	assert esperar_servicio(servicio_falso)
	assert motor_falso.cambios == [3, 1, 3]


def test_detecta_cambios_externos(servicio_falso, motor_falso):
	vistos = []
	llegado = threading.Event()

	def al_cambiar(estado, origen):
		vistos.append((estado.actual, origen))
		llegado.set()

	servicio_falso.al_cambiar_actual = al_cambiar
	motor_falso.actual_id = motor_falso.escritorios[2]["id"]  # «Ctrl+Win+Derecha» por fuera
	assert llegado.wait(2)
	assert vistos == [(3, "externo")]
	assert servicio_falso.estado.anterior == 1


def test_crear_renombrar_mover_y_eliminar(servicio_falso, motor_falso):
	resultados = {}
	servicio_falso.crear("Nuevo", al_terminar=lambda n: resultados.setdefault("creado", n))
	assert esperar_servicio(servicio_falso)
	assert resultados["creado"] == 5 and servicio_falso.estado.escritorio(5).nombre == "Nuevo"
	servicio_falso.renombrar(1, "Inicio")
	servicio_falso.mover_escritorio(5, 1)
	assert esperar_servicio(servicio_falso)
	assert [e.nombre for e in servicio_falso.estado.escritorios] == ["Nuevo", "Inicio", "Correo", "", "Trabajo"]
	servicio_falso.eliminar(1)
	assert esperar_servicio(servicio_falso)
	assert servicio_falso.estado.total == 4


def test_eliminar_vacios_respeta_el_actual(servicio_falso, motor_falso):
	motor_falso.agregar_ventana(10, 2)
	resultado = {}
	servicio_falso.eliminar_vacios(lambda n: resultado.setdefault("n", n))
	assert esperar_servicio(servicio_falso)
	assert resultado["n"] == 2, "el 3 y el 4 estaban vacíos; el 1 es el actual"
	assert [e.nombre for e in servicio_falso.estado.escritorios] == ["", "Correo"]


def test_mover_y_anclar_ventana(servicio_falso, motor_falso):
	motor_falso.agregar_ventana(10, 1, "Notas", "notepad.exe")
	servicio_falso.mover_ventana(10, paso=1, seguir=False)
	assert esperar_servicio(servicio_falso)
	assert motor_falso.escritorio_de_ventana(10) == 2
	servicio_falso.mover_ventana(10, destino=4, seguir=True)
	assert esperar_servicio(servicio_falso)
	assert motor_falso.escritorio_de_ventana(10) == 4
	assert motor_falso.numero_actual() == 4, "con «seguir» se cambia al destino"
	resultado = {}
	servicio_falso.anclar_ventana(10, al_terminar=lambda r: resultado.setdefault("anclada", r[1]))
	assert esperar_servicio(servicio_falso)
	assert resultado["anclada"] is True and motor_falso.ventana_anclada(10)


def test_reglas_mueven_solo_ventanas_nuevas(servicio_falso, motor_falso):
	motor_falso.agregar_ventana(1, 1, "Ya abierta", "thunderbird.exe")
	aplicadas = []
	llegado = threading.Event()
	servicio_falso.al_aplicar_regla = lambda ventana, regla, destino: (aplicadas.append((ventana.hwnd, destino)), llegado.set())
	servicio_falso.establecer_reglas([Regla(proceso="thunderbird.exe", escritorio="Correo")])
	threading.Event().wait(1.3)  # primera revisión: lo abierto se respeta
	motor_falso.agregar_ventana(2, 1, "Nueva", "thunderbird.exe")
	assert llegado.wait(3)
	assert aplicadas == [(2, 2)]
	assert motor_falso.escritorio_de_ventana(1) == 1
	resultado = {}
	servicio_falso.aplicar_reglas_ahora(lambda n: resultado.setdefault("n", n))
	assert esperar_servicio(servicio_falso)
	assert resultado["n"] == 1 and motor_falso.escritorio_de_ventana(1) == 2


def test_fallo_com_reconecta_y_reintenta(servicio_falso, motor_falso):
	motor_falso.fallar_una_vez = True
	servicio_falso.ir_a(2)
	assert esperar_servicio(servicio_falso)
	assert motor_falso.reconexiones >= 1
	assert motor_falso.numero_actual() == 2


def test_operacion_imposible_avisa_sin_romper_el_hilo(servicio_falso):
	errores = []
	servicio_falso.al_error = errores.append
	servicio_falso.ir_a(99)
	servicio_falso.ir_a(2)
	assert esperar_servicio(servicio_falso)
	assert len(errores) == 1 and "99" in errores[0]
	assert servicio_falso.estado.actual == 2
