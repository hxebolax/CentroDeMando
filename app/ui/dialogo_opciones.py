"""Diálogo de opciones con pestañas, declarativo.

Patrón:

- Cada página es una lista de ``Opcion`` (clave, etiqueta con ``&``, ayuda de
  Ctrl+H y tipo). Añadir una opción = añadir una línea aquí y su valor por
  defecto en ``config.VALORES_POR_DEFECTO``.
- Casillas con su propia etiqueta; números y listas con su ``StaticText``
  creada JUSTO ANTES del control.
- En cada página ninguna letra de acceso se repite ni choca con Aceptar (A),
  Cancelar (C) o Aplicar (P): lo comprueba una prueba con ``revisar_teclado``.
- Aceptar y Aplicar guardan y avisan (``al_aplicar``) para que el cambio se
  note al momento en la aplicación abierta; Cancelar no toca nada.
"""

from __future__ import annotations

import builtins
from collections.abc import Callable
from dataclasses import dataclass, field

import wx

from app.core.config import Configuracion
from app.core.version import NOMBRE_APLICACION
from app.services import sistema
from app.ui.accesibilidad.dialogos import crear_botonera, mostrar_mensaje, preparar_dialogo


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


CLAVE_INICIO_WINDOWS = "__inicio_windows__"


@dataclass(frozen=True)
class Opcion:
	clave: str
	etiqueta: str
	ayuda: str
	tipo: str = "bool"  # bool | int | elegir | texto | nota (texto explicativo, sin control)
	minimo: int = 0
	maximo: int = 0
	opciones: tuple[str, ...] = field(default_factory=tuple)
	# Valores que se guardan para cada opción de «elegir» (por defecto, el mismo texto).
	valores: tuple = field(default_factory=tuple)

	def valores_elegir(self) -> tuple:
		return self.valores or self.opciones


PAGINAS: list[tuple[str, list[Opcion]]] = [
	(
		"General",
		[
			Opcion(
				CLAVE_INICIO_WINDOWS,
				"&Iniciar con Windows",
				"Arranca Centro de Mando al iniciar sesión en Windows. Es lo único que se guarda fuera de la carpeta del programa (en el registro de su usuario).",
			),
			Opcion(
				"general.bandeja_al_iniciar_con_windows",
				"Al iniciar con Windows, quedarse &oculto en la bandeja",
				"Cuando arranca con Windows no muestra la ventana: queda en la bandeja con las teclas globales activas.",
			),
			Opcion(
				"general.iniciar_en_bandeja",
				"Arrancar siempre oc&ulto en la bandeja",
				"También al abrirlo a mano, Centro de Mando arranca sin mostrar la ventana.",
			),
			Opcion(
				"general.icono_siempre",
				"Icono siempre en la &bandeja",
				"Mantiene el icono en la bandeja del sistema aunque la ventana esté a la vista. Windows+B lleva a la bandeja.",
			),
			Opcion("general.minimizar_a_bandeja", "&Minimizar a la bandeja", "Al minimizar, la ventana se oculta y queda en la bandeja."),
			Opcion(
				"general.cerrar_a_bandeja",
				"Cerrar a la ba&ndeja",
				"Alt+F4 oculta la ventana en lugar de salir; las teclas globales siguen activas. Para salir de verdad, Escritorios, Salir.",
			),
			Opcion("general.anunciar_arranque", "Anunciar el arranque por &voz", "Dice el nombre del programa al abrirlo."),
			Opcion(
				"general.confirmar_eliminar",
				"Confirmar antes de &eliminar un escritorio",
				"Pregunta antes de eliminar un escritorio. Sus ventanas no se cierran: pasan al escritorio vecino.",
			),
		],
	),
	(
		"Cambio de escritorio",
		[
			Opcion(
				"escritorios.ciclico",
				"Cambio cícl&ico",
				"Siguiente desde el último escritorio lleva al primero, y anterior desde el primero lleva al último.",
			),
			Opcion(
				"escritorios.enfocar_al_cambiar",
				"Dar el &foco a la última ventana del escritorio al cambiar",
				"Tras cambiar de escritorio, activa la ventana que se usó por última vez en él. Si no hay ninguna, el foco va al escritorio de Windows.",
			),
			Opcion(
				"escritorios.animacion",
				"Usar la a&nimación de Windows",
				"Muestra la animación de deslizamiento al cambiar. Sin ella el cambio es instantáneo.",
			),
		],
	),
	(
		"Anuncios",
		[
			Opcion(
				"anuncios.cambio_escritorio",
				"Anunciar el escritorio al ca&mbiar:",
				"Automático: con un lector de pantalla (NVDA, JAWS, Narrador) Windows ya dice el escritorio al que se llega, "
				"así que Centro de Mando no lo repite; sin lector, lo dice con la voz de Windows. "
				"Las demás opciones lo dicen siempre en los cambios hechos con Centro de Mando, en todos o en ninguno.",
				"elegir",
				opciones=(
					"Automático (no repetir lo que ya dice Windows)",
					"Solo los cambios hechos con Centro de Mando",
					"Todos, también con las teclas de Windows",
					"Nunca",
				),
				valores=("auto", "propios", "todos", "nunca"),
			),
			Opcion("anuncios.decir_numero", "Decir el &número del escritorio", "Incluye el número aunque el escritorio tenga nombre."),
			Opcion("anuncios.decir_total", "Decir el &total de escritorios", "Añade «de 12» al anuncio."),
			Opcion(
				"anuncios.decir_ventanas",
				"Decir cuántas &ventanas tiene",
				"Añade cuántas ventanas hay en el escritorio al que se llega. En modo automático con lector de pantalla, se dice solo esto tras el anuncio de Windows.",
			),
			Opcion(
				"anuncios.dispositivos_audio",
				"Avisar al conectar o desconectar dispositivos de au&dio",
				"Dice «Conectado» o «Desconectado» y el nombre del dispositivo (auriculares, altavoces Bluetooth...). "
				"Espera unos segundos a que el cambio se asiente: si se desconecta y vuelve a conectarse enseguida, no dice nada.",
			),
			Opcion(
				"anuncios.dispositivos_pantallas",
				"Avisar también del audio de monitores y televisores (&HDMI, DisplayPort)",
				"Windows desconecta y vuelve a conectar el audio de la pantalla cada vez que esta reposa o despierta. "
				"Desactivado de fábrica para no avisar sin motivo.",
			),
			Opcion("anuncios.tono", "T&ono distinto para cada escritorio", "Un pitido más agudo cuanto mayor es el número del escritorio."),
			Opcion(
				"anuncios.retraso_ms",
				"&Retraso del anuncio en milisegundos:",
				"Espera antes de hablar para que el lector diga primero la ventana enfocada y no corte el anuncio.",
				"int",
				0,
				2000,
			),
		],
	),
	(
		"Listas",
		[
			Opcion(
				"",
				"Al moverse por las columnas de las listas (flechas Izquierda y Derecha, o Control+1 a 9 y 0), "
				"elija qué se dice de cada celda:",
				"",
				"nota",
			),
			Opcion(
				"listas.decir_numero_fila",
				"Decir el número de &fila («Fila 1»)",
				"Antes de la celda dice en qué fila está.",
			),
			Opcion(
				"listas.decir_cabecera",
				"Decir el nombre de la co&lumna («Nombre», «Ventanas»...)",
				"Dice el título de la columna antes de su contenido.",
			),
			Opcion(
				"listas.decir_contenido",
				"Decir el con&tenido de la celda",
				"Dice el texto de la celda.",
			),
			Opcion("", "Si desactiva las tres, se dirá igualmente el contenido de la celda.", "", "nota"),
		],
	),
	(
		"Portapapeles",
		[
			Opcion(
				"portapapeles.activo",
				"Guardar lo que se copia en el &historial",
				"Si se desmarca, el historial deja de crecer; lo guardado se conserva.",
			),
			Opcion(
				"portapapeles.maximo",
				"Número &máximo de elementos (0 = sin límite):",
				"Al pasarse, se borran los más antiguos que no son favoritos. Los favoritos no se borran nunca por el límite.",
				"int",
				0,
				100000,
			),
			Opcion(
				"portapapeles.dias",
				"&Borrar lo que no se use en estos días (0 = nunca):",
				"Los elementos que no se copian ni se pegan en ese tiempo se borran solos. Los favoritos no caducan.",
				"int",
				0,
				3650,
			),
			Opcion(
				"portapapeles.guardar_html",
				"Guardar también el &formato (HTML)",
				"Al pegar en un procesador de textos o en un correo se conserva el formato.",
			),
			Opcion(
				"portapapeles.guardar_archivos",
				"Guardar las copias de a&rchivos",
				"Archivos y carpetas copiados en el Explorador, para pegarlos más tarde.",
			),
			Opcion("portapapeles.guardar_imagenes", "Guardar las &imágenes", "Imágenes copiadas (capturas de pantalla, por ejemplo)."),
			Opcion(
				"portapapeles.maximo_imagen_mb",
				"Tamaño máximo de ca&da imagen en megas:",
				"Las imágenes más grandes no se guardan.",
				"int",
				1,
				500,
			),
			Opcion(
				"portapapeles.ignorar_privados",
				"No guardar el contenido marcado como pri&vado (contraseñas)",
				"Los gestores de contraseñas marcan lo que copian para que ningún historial lo guarde. Se recomienda dejarlo marcado.",
			),
			Opcion(
				"portapapeles.programas_excluidos",
				"Programas &excluidos, separados por comas:",
				"Lo que copien estos programas no se guarda. Por ejemplo: keepass.exe, bitwarden.exe",
				"texto",
			),
			Opcion(
				"portapapeles.restaurar_tras_pegar",
				"Devolver al portapapeles lo que había &tras pegar",
				"Al pegar desde el historial, lo que tenía copiado vuelve al portapapeles al terminar.",
			),
			Opcion(
				"portapapeles.metodo_pegado",
				"Forma de pe&gar:",
				"Casi todos los programas pegan con Control+V; algunos terminales solo con Mayúsculas+Insertar.",
				"elegir",
				opciones=("Control+V", "Mayúsculas+Insertar"),
				valores=("control_v", "mayus_insert"),
			),
			Opcion("portapapeles.anunciar_copias", "A&nunciar cada copia por voz", "Dice el principio de lo que se acaba de copiar."),
		],
	),
	(
		"Emoticonos",
		[
			Opcion(
				"emoticonos.metodo",
				"&Forma de insertar:",
				"Escribir el carácter no toca el portapapeles y funciona en casi todos los programas; si alguno no lo acepta, elija pegar.",
				"elegir",
				opciones=("Escribir el carácter (recomendado)", "Pegar con Control+V", "Pegar con Mayúsculas+Insertar"),
				valores=("escribir", "control_v", "mayus_insert"),
			),
			Opcion(
				"emoticonos.tono",
				"&Tono de piel predeterminado:",
				"Se aplica a los emoticonos de personas y manos. También se cambia desde el área de emoticonos.",
				"elegir",
				opciones=("Sin tono (amarillo)", "Claro", "Claro medio", "Medio", "Oscuro medio", "Oscuro"),
				valores=(0, 1, 2, 3, 4, 5),
			),
			Opcion(
				"emoticonos.mostrar_caracter",
				"&Mostrar el emoticono junto a su nombre en las listas",
				"Útil para verlo en pantalla. Con lector de pantalla se oiría dos veces, porque el lector ya lee el emoticono por su nombre.",
			),
			Opcion(
				"emoticonos.maximo_recientes",
				"Número de usados &recientemente que se recuerdan:",
				"Cuántos emoticonos guarda el grupo «Usados recientemente».",
				"int",
				5,
				200,
			),
		],
	),
	(
		"Notificaciones",
		[
			Opcion(
				"",
				"Para guardar las notificaciones, Windows debe permitirlo en Configuración, Privacidad y seguridad, Notificaciones.",
				"",
				"nota",
			),
			Opcion(
				"notificaciones.activo",
				"Guardar las notificaciones en el &historial",
				"Si se desmarca, las nuevas no se guardan; lo guardado se conserva.",
			),
			Opcion(
				"notificaciones.intervalo_s",
				"Comprobar cada estos &segundos:",
				"Windows no avisa de las notificaciones nuevas: se le pregunta cada pocos segundos. Menos es más rápido.",
				"int",
				1,
				60,
			),
			Opcion(
				"notificaciones.anunciar_nuevas",
				"A&nunciar las notificaciones nuevas por voz",
				"Dice la aplicación y el título de cada notificación nueva.",
			),
			Opcion("notificaciones.anunciar_texto", "Decir también el &texto", "Al anunciar una notificación, lee también su texto."),
			Opcion(
				"notificaciones.marcar_leida_al_ver",
				"Marcar como &leída al detenerse en ella",
				"Una notificación se da por leída tras un momento seleccionada en la lista. Espacio la marca o desmarca a mano.",
			),
			Opcion(
				"notificaciones.apps_anunciadas",
				"Anunciar solo las de estas aplicacion&es, separadas por comas (vacío = todas):",
				"Si escribe aplicaciones aquí, solo se dicen en voz alta sus notificaciones; las demás se guardan en silencio. "
				"Basta con parte del nombre: «whatsapp» vale para «WhatsApp Beta».",
				"texto",
			),
			Opcion(
				"notificaciones.apps_ignoradas",
				"Aplicaciones &ignoradas, separadas por comas:",
				"Las notificaciones de estas aplicaciones no se guardan. También se añade desde el menú Notificaciones.",
				"texto",
			),
			Opcion(
				"notificaciones.maximo",
				"Número &máximo de notificaciones (0 = sin límite):",
				"Al pasarse se borran las más antiguas que no son favoritas.",
				"int",
				0,
				100000,
			),
			Opcion(
				"notificaciones.dias",
				"Borrar las de más de estos &días (0 = nunca):",
				"Las favoritas no se borran nunca solas.",
				"int",
				0,
				3650,
			),
		],
	),
	(
		"Audio",
		[
			Opcion(
				"audio.bloquear_micro",
				"&Bloquear el volumen del micrófono",
				"Si otro programa (Teams, el navegador, un controlador) cambia el volumen del micrófono predeterminado, "
				"Centro de Mando lo devuelve al de abajo en un par de segundos.",
			),
			Opcion(
				"audio.volumen_micro_bloqueado",
				"&Volumen fijo del micrófono:",
				"Volumen al que se devuelve el micrófono cuando está bloqueado.",
				"int",
				0,
				100,
			),
			Opcion(
				"audio.silenciar_micro_al_iniciar",
				"&Silenciar el micrófono al arrancar",
				"Al abrir Centro de Mando (por ejemplo al iniciar Windows) el micrófono predeterminado queda silenciado. Control+Alt+Windows+M lo activa.",
			),
			Opcion(
				"",
				"Los perfiles de audio se guardan y se aplican en el área de audio, menú Acción; la tecla global «Aplicar el siguiente perfil de audio» se asigna en Teclas globales.",
				"",
				"nota",
			),
		],
	),
	(
		"No molestar",
		[
			Opcion(
				"",
				"No molestar calla los avisos automáticos: notificaciones nuevas, dispositivos de audio y copias del portapapeles. "
				"Las notificaciones se siguen guardando y las alarmas siguen sonando. Se activa también con Control+Alt+Windows+Q.",
				"",
				"nota",
			),
			Opcion("no_molestar.activo", "No &molestar activado ahora", "Lo activa o desactiva a mano hasta que se vuelva a cambiar."),
			Opcion(
				"no_molestar.programado",
				"Activarlo cada día en un &horario",
				"Se activa solo entre las dos horas de abajo. Si la de fin es anterior a la de inicio, cruza la medianoche.",
			),
			Opcion("no_molestar.desde", "&Desde (hora:minutos, por ejemplo 23:00):", "Hora a la que empieza cada día.", "texto"),
			Opcion("no_molestar.hasta", "Ha&sta (hora:minutos, por ejemplo 08:00):", "Hora a la que termina.", "texto"),
			Opcion(
				"no_molestar.apps_permitidas",
				"Aplicaciones que se anuncian &igualmente, separadas por comas:",
				"Las notificaciones de estas aplicaciones se dicen aunque No molestar esté activo.",
				"texto",
			),
		],
	),
	(
		"Ventanas",
		[
			Opcion(
				"ventanas.seguir_ventana",
				"&Seguir a la ventana al moverla a otro escritorio",
				"Al mover la ventana activa, cambia también al escritorio de destino.",
			),
			Opcion(
				"ventanas.aplicar_reglas_al_iniciar",
				"Aplicar las &reglas también a las ventanas abiertas al iniciar",
				"Si está desactivado, las reglas solo mueven las ventanas que se abren después de arrancar Centro de Mando.",
			),
		],
	),
	(
		"Actualizaciones",
		[
			Opcion(
				"actualizaciones.fuente",
				"&Buscar actualizaciones en:",
				"El servidor del autor, las publicaciones de GitHub, los dos (primero el servidor y, si no responde, GitHub) o una dirección propia. "
				"Venga de donde venga, la versión se comprueba con su firma digital antes de instalarla.",
				"elegir",
				opciones=("Los dos: servidor del autor y GitHub", "Solo el servidor del autor", "Solo GitHub", "Una dirección personalizada"),
				valores=("ambos", "servidor", "github", "personalizada"),
			),
			Opcion(
				"actualizaciones.url_personalizada",
				"&Dirección personalizada del version.json (https):",
				"Solo con «Una dirección personalizada». Debe publicar un version.json firmado por el autor; si no, se rechaza.",
				"texto",
			),
			Opcion(
				"actualizaciones.comprobar_automaticamente",
				"Comprobar au&tomáticamente si hay versiones nuevas",
				"Al poco de arrancar y después cada cierto tiempo. Siempre pregunta antes de instalar nada.",
			),
			Opcion(
				"actualizaciones.intervalo_horas",
				"Comprobar cada estas &horas:",
				"Cada cuánto se comprueba mientras el programa sigue abierto.",
				"int",
				1,
				168,
			),
		],
	),
	(
		"Avanzado",
		[
			Opcion(
				"escritorios.interceptar_flechas_nativas",
				"&Hacer cíclicas Ctrl+Windows+Izquierda y Derecha",
				"Intercepta esas teclas de Windows con un gancho de teclado para que también den la vuelta. Desactívelo si nota algún problema con el teclado.",
			),
			Opcion(
				"escritorios.intervalo_sondeo_ms",
				"Intervalo de &sondeo en milisegundos:",
				"Cada cuánto se comprueba si se cambió de escritorio fuera de Centro de Mando. Menos es más rápido; más gasta menos.",
				"int",
				50,
				5000,
			),
			Opcion(
				"registro.nivel",
				"Nivel de re&gistro:",
				"Cuánto detalle se escribe en los registros. DEBUG solo para buscar un fallo.",
				"elegir",
				opciones=("DEBUG", "INFO", "WARNING", "ERROR"),
			),
		],
	),
]


class DialogoOpciones(wx.Dialog):
	"""Opciones del gestor en pestañas."""

	def __init__(self, padre: wx.Window | None, configuracion: Configuracion, al_aplicar: Callable[[], None] | None = None) -> None:
		super().__init__(padre, title=_("Opciones"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self._config = configuracion
		self._al_aplicar = al_aplicar
		self.controles: dict[str, wx.Window] = {}

		self.libro = wx.Notebook(self)
		for titulo, opciones in PAGINAS:
			pagina = wx.Panel(self.libro)
			sizer = wx.BoxSizer(wx.VERTICAL)
			for opcion in opciones:
				if opcion.tipo == "nota":
					sizer.Add(wx.StaticText(pagina, label=_(opcion.etiqueta)), 0, wx.ALL, 6)
					continue
				self.controles[opcion.clave] = self._crear_control(pagina, opcion, sizer)
			pagina.SetSizer(sizer)
			self.libro.AddPage(pagina, _(titulo))

		principal = wx.BoxSizer(wx.VERTICAL)
		principal.Add(self.libro, 1, wx.EXPAND | wx.ALL, 8)
		principal.Add(crear_botonera(self, wx.OK | wx.CANCEL | wx.APPLY), 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		self.SetSizerAndFit(principal)
		self.Bind(wx.EVT_BUTTON, self._al_boton_aplicar, id=wx.ID_APPLY)
		preparar_dialogo(self, foco_inicial=self.libro)
		self.CentreOnParent()

	def _valor(self, clave: str):
		if clave == CLAVE_INICIO_WINDOWS:
			return sistema.inicio_automatico_activo(NOMBRE_APLICACION)
		return self._config.obtener(clave)

	def _crear_control(self, pagina: wx.Window, opcion: Opcion, sizer: wx.Sizer) -> wx.Window:
		valor = self._valor(opcion.clave)
		if opcion.tipo == "bool":
			control = wx.CheckBox(pagina, label=_(opcion.etiqueta))
			control.SetValue(bool(valor))
			sizer.Add(control, 0, wx.ALL, 6)
		else:
			# Etiqueta JUSTO ANTES del control: de ella toma el nombre el lector.
			etiqueta = wx.StaticText(pagina, label=_(opcion.etiqueta))
			if opcion.tipo == "int":
				control = wx.SpinCtrl(pagina, min=opcion.minimo, max=opcion.maximo, initial=int(valor or opcion.minimo))
			elif opcion.tipo == "texto":
				control = wx.TextCtrl(pagina, value=str(valor or ""), size=self.FromDIP(wx.Size(320, -1)))
			else:
				control = wx.Choice(pagina, choices=[_(o) for o in opcion.opciones])
				valores = opcion.valores_elegir()
				control.SetSelection(valores.index(valor) if valor in valores else 0)
			fila = wx.BoxSizer(wx.HORIZONTAL)
			fila.Add(etiqueta, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
			fila.Add(control)
			sizer.Add(fila, 0, wx.ALL, 6)
		control.SetHelpText(_(opcion.ayuda))
		return control

	def aplicar(self) -> None:
		"""Copia los controles a la configuración, la guarda y avisa a la aplicación."""
		for _titulo, opciones in PAGINAS:
			for opcion in opciones:
				if opcion.tipo == "nota":
					continue
				control = self.controles[opcion.clave]
				if opcion.tipo == "bool":
					valor = control.GetValue()
				elif opcion.tipo == "int":
					valor = int(control.GetValue())
				elif opcion.tipo == "texto":
					valor = control.GetValue().strip()
				else:
					valor = opcion.valores_elegir()[max(control.GetSelection(), 0)]
				if opcion.clave == CLAVE_INICIO_WINDOWS:
					if bool(valor) != sistema.inicio_automatico_activo(NOMBRE_APLICACION):
						if not sistema.establecer_inicio_automatico(NOMBRE_APLICACION, bool(valor)):
							mostrar_mensaje(
								self,
								_("No se pudo cambiar el inicio con Windows. Detalles en el registro."),
								_("Opciones"),
								wx.ICON_WARNING,
							)
					continue
				self._config.establecer(opcion.clave, valor)
		self._config.guardar()
		if self._al_aplicar is not None:
			self._al_aplicar()

	def _al_boton_aplicar(self, _evento: wx.CommandEvent) -> None:
		self.aplicar()
