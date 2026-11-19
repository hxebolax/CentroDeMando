# Manual de Centro de Mando

## Qué es

Centro de Mando reúne en un solo programa, accesible con lector de pantalla y manejable por completo con el teclado, estas herramientas para Windows 10 y 11:

- **Escritorios virtuales**: cambiar de escritorio al instante (también de forma cíclica), crearlos, ponerles nombre, ordenarlos, eliminarlos y mover ventanas entre ellos.
- **Historial del portapapeles**: todo lo que copia (textos, textos con formato, archivos e imágenes) queda guardado para pegarlo después donde esté.
- **Emoticonos**: casi 4000 emojis con nombre en español, símbolos tipográficos y kaomoji, que se escriben directamente en el programa en el que esté.
- **Notificaciones**: un historial de las notificaciones de Windows y de las aplicaciones, para que no se le pase ninguna.
- **Fragmentos de texto**: firmas, direcciones o respuestas habituales que se insertan al instante.
- **Audio**: dispositivo de salida, volumen general, volumen de cada aplicación y micrófono.
- **Sistema**: estado del equipo y energía (bloquear, suspender, apagar con cuenta atrás...).
- **Lanzador**: abrir al momento programas, ajustes de Windows y cualquier acción de Centro de Mando, y hacer cálculos.
- **Ventanas y procesos**: todas las ventanas abiertas y los procesos, para activarlos, ponerlos siempre encima, cerrarlos o finalizarlos.
- **Temporizadores y alarmas**: cuentas atrás, alarmas y recordatorios con aviso sonoro y hablado.

Vive en la bandeja del sistema y responde a teclas globales que funcionan desde cualquier programa. Todas se pueden cambiar.

## Requisitos

- Windows 10 u 11 de 64 bits. Algunas funciones de escritorios (reordenarlos, fondo por escritorio, animación) solo existen en Windows 11.
- Funciona con NVDA, JAWS y Narrador. No necesita instalación: es portable.

## Primeros pasos

1. Descomprima el archivo ZIP en una carpeta con permiso de escritura (por ejemplo, en Documentos). No la ponga en Archivos de programa.
2. Abra `CentroDeMando.exe`. La ventana principal muestra nueve pestañas: Escritorios, Portapapeles, Fragmentos, Emoticonos, Notificaciones, Audio, Sistema, Ventanas y procesos, y Temporizadores.
3. Pruebe desde cualquier programa:
   - Control+Alt+Windows+Flecha derecha: escritorio siguiente.
   - Control+Alt+Windows+V: historial del portapapeles.
   - Control+Alt+Windows+E: emoticonos.
   - Control+Alt+Windows+A: historial de notificaciones.

## La ventana principal

Tiene nueve áreas en pestañas. Para cambiar de área:

- Control+Tabulador y Control+Mayúsculas+Tabulador.
- Menú Ir: Alt+1 Escritorios, Alt+2 Portapapeles, Alt+3 Fragmentos, Alt+4 Emoticonos, Alt+5 Notificaciones, Alt+6 Audio, Alt+7 Sistema, Alt+8 Ventanas y procesos y Alt+9 Temporizadores. Control+E lleva al buscador del área.

### La barra de menús

La barra es siempre la misma:

- **Archivo**: lanzador (Control+Mayúsculas+P), abrir la lista rápida del área (Control+L), exportar, ocultar en la bandeja y salir (Control+Q).
- **Acción**: las órdenes del área en la que está. Cambia al cambiar de pestaña y es igual que el menú contextual (tecla Aplicaciones). Las órdenes que dependen del elemento seleccionado solo están activas si hay uno.
- **Ir**: las nueve áreas y el buscador.
- **Ver**: ventanas de todos los escritorios, barra de estado, decir el estado del área (Control+D) y actualizar (F5).
- **Herramientas**: teclas globales (Control+T), reglas de ventanas (Control+R), opciones (Control+coma) y las carpetas de datos y registros.
- **Ayuda**: manual (F1), lista de teclas (Control+F1), novedades, ayuda del control (Control+H), invitar a un café y Acerca de.

Escape, Alt+F4 o minimizar ocultan la ventana en la bandeja: Centro de Mando sigue funcionando. Para cerrarlo del todo use Archivo, Salir (Control+Q).

La barra de estado muestra siempre lo último que se anunció.

### Moverse por las columnas de las listas

En todas las listas:

- Flecha izquierda y derecha: columna anterior y siguiente de la fila, sin cambiar de fila.
- Control+1 a Control+9: lee esa columna; Control+0, la décima.
- Control+Mayúsculas+Inicio y Fin: primera y última columna.

Qué se dice de cada celda se elige en Opciones, pestaña Listas: número de fila, nombre de la columna y contenido. Si desactiva las tres, se dice igualmente el contenido.

## Escritorios virtuales

### Cambiar de escritorio rápidamente

- Siguiente y anterior: Control+Alt+Windows+Flecha derecha o izquierda. Con **Cambio cíclico** (activado de fábrica), desde el último se vuelve al primero y al revés.
- Directo a un escritorio: Control+Alt+Windows+1 a 9, y 0 para el décimo.
- Primero y último: Control+Alt+Windows+Inicio o Fin.
- Volver al escritorio anterior: Control+Alt+Windows+Retroceso (alterna entre los dos últimos).
- Elegir de una lista: Control+Alt+Windows+S. Escriba el número, la primera letra o parte del nombre en Filtrar (Alt+F), e Intro.

Al llegar a un escritorio, Centro de Mando da el foco a la última ventana que usó en él y anuncia el escritorio.

Las teclas de Windows Control+Windows+Flecha derecha e izquierda se detienen en los extremos. En Opciones, Avanzado, **Hacer cíclicas Ctrl+Windows+Izquierda y Derecha** hace que también den la vuelta.

NVDA ya anuncia el escritorio cuando se cambia con las teclas de Windows. Por eso, de fábrica, Centro de Mando no repite el anuncio de los cambios hechos fuera de él (Opciones, Anuncios, **Anunciar también los cambios hechos fuera de Centro de Mando**). Si con sus propias teclas oye el escritorio dos veces, desactive **Anunciar el escritorio al cambiar**.

### Área de escritorios

- **Lista de escritorios** (Alt+L): número, nombre, ventanas y cuál es el actual. Intro va al escritorio; F2 cambia el nombre; Suprimir lo elimina (sus ventanas pasan al vecino); Alt+Mayúsculas+Flecha arriba o abajo cambia su orden.
- **Ventanas del escritorio seleccionado** (Alt+T): Intro va a la ventana; Control+M la mueve a otro escritorio; Suprimir le pide que se cierre. En Ver, **Ventanas de todos los escritorios** las muestra todas.

En el menú Acción también: crear con nombre (Control+Mayúsculas+N), eliminar los escritorios vacíos, fondo de pantalla (Windows 11) y, en el submenú Ventana seleccionada, todas las acciones de la ventana elegida.

### Mover ventanas entre escritorios

Desde cualquier programa, sobre la ventana con el foco:

- Control+Alt+Mayúsculas+Windows+Flecha derecha o izquierda: al escritorio siguiente o anterior.
- Control+Alt+Mayúsculas+Windows+1 a 0: a un escritorio concreto.
- Control+Alt+Windows+P: mostrarla u ocultarla en todos los escritorios.
- Control+Alt+Windows+B: buscar una ventana en todos los escritorios e ir a ella.

Con **Seguir a la ventana al moverla** (Opciones, Ventanas) cambia también al escritorio de destino.

### Reglas de ventanas

Herramientas, Reglas de ventanas (Control+R): llevar solas las ventanas nuevas de un programa (o con un texto en el título) a un escritorio, o mostrarlas en todos. Se aplica la primera regla que encaja; Subir y Bajar cambian el orden; **Aplicar ahora a las ventanas abiertas** las aplica a todo.

## Historial del portapapeles

Todo lo que copia se guarda: textos (con su formato HTML), listas de archivos copiadas en el Explorador e imágenes. Lo repetido no se duplica: sube arriba.

### Pegar desde cualquier programa

1. En el programa donde quiere pegar, pulse Control+Alt+Windows+V.
2. Escriba para buscar, o baje con las flechas por la lista.
3. Pulse Intro: la ventana se cierra, vuelve al programa y el elemento se pega donde estaba el cursor.

Después de pegar, lo que tenía copiado vuelve al portapapeles (se puede desactivar en Opciones).

### Teclas en la lista

- Intro: pegar en la ventana de la que vino.
- Control+Mayúsculas+Intro: pegar como texto sin formato.
- Mayúsculas+Intro: solo copiar al portapapeles.
- F2: ponerle un nombre para reconocerlo (al pegar se pega el contenido real).
- F4: añadir o quitar de favoritos. Los favoritos no se borran nunca solos.
- Suprimir: eliminarlo.
- Tecla Aplicaciones: todas las acciones, incluido **Pegar transformado** (en una sola línea, sin espacios sobrantes, en mayúsculas, en minúsculas, con mayúscula en cada palabra o solo al principio).

Otros controles: **Buscar en el historial** (Alt+B, dice cuántos resultados hay), **Mostrar** (Alt+S: todo, favoritos, textos, imágenes o archivos), la lista **Elementos copiados** (Alt+D) y **Contenido** (Alt+T, el texto completo).

### Pegar los últimos sin abrir nada

En Teclas globales hay nueve acciones, «Pegar el elemento 1 del historial» a «Pegar el elemento 9», sin tecla de fábrica. Asígneles una tecla y pegarán ese elemento directamente donde esté el cursor (1 es el último copiado).

Desde la pestaña Portapapeles de la ventana principal, Intro pega en la ventana que usaba antes de abrir Centro de Mando.

### Privacidad

- No se guarda lo que los gestores de contraseñas marcan como privado (KeePass, Bitwarden y otros lo hacen).
- En Opciones, Portapapeles, puede excluir programas por su nombre (por ejemplo, `keepass.exe`).
- En el área de portapapeles, menú Acción, **Detener la captura** deja de guardar hasta que la vuelva a activar.
- El historial está en `data\db\portapapeles.db`, dentro de la carpeta del programa.

## Emoticonos

### Insertar desde cualquier programa

1. Pulse Control+Alt+Windows+E en el programa donde está escribiendo.
2. Escriba lo que busca: «corazon», «risa», «pulgar»... No hace falta poner tildes; busca en el nombre y en las palabras clave. Se anuncia cuántos resultados hay.
3. Flecha abajo baja a la lista; Intro escribe el emoticono donde estaba el cursor.

### Teclas en la lista

- Intro: insertar.
- Mayúsculas+Intro: solo copiar.
- Control+Intro: añadirlo al **Texto para insertar** (Alt+X) para insertar varios de una vez; Intro en ese campo los inserta todos.
- F4: favorito.
- Tecla Aplicaciones: también copiar el nombre o el código Unicode.

Controles: **Buscar emoticono** (Alt+B), **Grupo** (Alt+G: usados recientemente, favoritos, caras, personas, animales, comida, viajes, actividades, objetos, símbolos, banderas, símbolos tipográficos y kaomoji) y **Tono de piel** (Alt+T), que se recuerda.

La lista dice solo el nombre porque el lector de pantalla ya lee el emoticono por su nombre; en Opciones, Emoticonos, puede mostrar también el carácter.

De fábrica el emoticono se «teclea» sin tocar el portapapeles. Si algún programa no lo acepta, en Opciones, Emoticonos, elija pegarlo.

## Notificaciones

Centro de Mando guarda las notificaciones de Windows y de las aplicaciones (correo, mensajería, calendario...). Windows las borra al descartarlas o al cabo de unos días; el historial de Centro de Mando las conserva.

### Permiso de Windows

La primera vez, Windows debe permitir que las aplicaciones lean las notificaciones: Configuración, Privacidad y seguridad, Notificaciones. En el área de notificaciones, menú Acción, **Permiso de Windows** abre esa página. Si no hay permiso, Centro de Mando lo dice.

### Consultar el historial

- Control+Alt+Windows+A abre el historial desde cualquier programa.
- Control+Alt+Windows+U dice la última notificación y cuántas quedan sin leer.
- El icono de la bandeja dice cuántas hay sin leer.

### Teclas en la lista

- Intro: abrir la aplicación que la envió.
- Mayúsculas+Intro: copiar el título y el texto.
- Espacio: marcar como leída o no leída (también se marca sola al detenerse en ella un momento).
- F4: favorita. Las favoritas no se borran nunca solas.
- Suprimir: borrarla del historial. Mayúsculas+Suprimir: además, descartarla del centro de notificaciones de Windows.

Controles: **Buscar en las notificaciones** (Alt+B), **Mostrar** (Alt+S: todas, no leídas o favoritas), **Aplicación** (Alt+N), la lista (Alt+L) y **Contenido** (Alt+T).

Con «No leídas», las que va leyendo se quedan en la lista hasta que cambie de filtro, para no perder el sitio.

En el menú Acción y en el menú contextual (tecla Aplicaciones): abrir la aplicación, copiar, leída o no leída, favorita, descartar en Windows, eliminar, ignorar las de una aplicación, ver solo las de esa aplicación, marcar todas como leídas, vaciar, detener la captura y el permiso de Windows. Archivo, Exportar, las guarda en CSV o texto.

Windows no avisa a los programas de las notificaciones nuevas: Centro de Mando le pregunta cada pocos segundos (Opciones, Notificaciones). Así también se guardan las que llegan con «No molestar».

NVDA ya lee las notificaciones cuando aparecen. Por eso **Anunciar las notificaciones nuevas por voz** viene desactivado; actívelo si quiere oírlas aunque esté con otro programa que no las lea.

## Fragmentos de texto

Textos que usa a menudo (firmas, direcciones, respuestas) para insertarlos al instante donde está el cursor.

1. Pulse Control+Alt+Windows+T en el programa donde escribe.
2. Escriba la abreviatura del fragmento (por ejemplo «firma») y pulse Intro: se inserta el primero que coincide. O baje a la lista y elija con las flechas.

En la lista: Intro inserta, Mayúsculas+Intro copia, Insert crea uno nuevo, F2 lo modifica y Suprimir lo elimina. Controles: **Buscar fragmento** (Alt+B), **Categoría** (Alt+G), la lista (Alt+L) y **Contenido** (Alt+T).

Cada fragmento tiene nombre, abreviatura (opcional), categoría y texto. El texto admite variables que se sustituyen al insertar: `{fecha}`, `{fecha_larga}`, `{hora}`, `{dia}`, `{mes}`, `{anio}` y `{portapapeles}` (lo que tenga copiado). Los textos de varias líneas se pegan (y su portapapeles vuelve a quedar como estaba); los de una línea se teclean. Se guardan en `data\db\fragmentos.json`.

## Audio

- **Dispositivos de salida** (Alt+D): Intro pone el elegido como salida predeterminada.
- **Volumen general** (Alt+G): deslizador de 0 a 100.
- **Aplicaciones con sonido** (Alt+S): Más y Menos (o Control+flechas arriba y abajo) cambian su volumen de 5 en 5; Espacio la silencia.

Teclas globales: Control+Alt+Windows+O pasa a la siguiente salida y dice su nombre; Control+Alt+Windows+Flecha arriba y abajo suben y bajan el volumen general; Control+Alt+Windows+M silencia o activa el micrófono. En Teclas globales hay además, sin tecla de fábrica, silenciar el sonido general y decir el estado del audio.

### El sonido de la aplicación que tiene delante

Sin abrir nada, desde el programa que está usando:

- Control+Alt+Mayúsculas+Windows+Flecha arriba y abajo: subir y bajar de 5 en 5 solo su volumen.
- Control+Alt+Mayúsculas+Windows+Fin: silenciarlo o devolverle el sonido.
- Control+Alt+Mayúsculas+Windows+Inicio: decir su volumen.

Los navegadores (Firefox, Chrome, Edge) y muchas aplicaciones suenan desde procesos internos: Centro de Mando los reconoce como parte del mismo programa. Si el programa no está sonando, lo dice.

## Sistema

**Estado del equipo** (Alt+E): batería (si la hay), procesador, memoria, disco del sistema, red y tiempo encendido. Se actualiza solo. Control+Alt+Windows+F12 lo dice desde cualquier programa.

En el menú Acción y en el contextual: bloquear, suspender, hibernar, apagar la pantalla, apagar o reiniciar dentro de los minutos que elija (con el aviso de Windows), cancelar el apagado y mantener el equipo despierto. Bloquear y apagar la pantalla también tienen acción en Teclas globales, sin tecla de fábrica.

## Ventanas y procesos

- **Buscar** (Alt+B): filtra las dos listas.
- **Lista de ventanas abiertas** (Alt+L): título, programa y estado (minimizada, maximizada, siempre encima, no responde), de todos los escritorios. Intro activa la ventana (y cambia a su escritorio); Suprimir le pide que se cierre.
- **Procesos** (Alt+P): nombre, PID, procesador y memoria, de mayor a menor uso de procesador. Suprimir lo finaliza, tras confirmarlo. Los procesos protegidos del sistema no aparecen.

En el menú Acción y en el contextual: activar, minimizar, maximizar, restaurar, siempre encima, cerrar, finalizar el proceso, abrir la ubicación del programa y copiar su ruta. Las listas se actualizan solas cada pocos segundos sin moverle de su sitio.

Control+Alt+Windows+K pone (o quita) siempre encima la ventana que tiene el foco, desde cualquier programa.

## Temporizadores y alarmas

En el menú Acción (o con la tecla Aplicaciones en la lista):

- **Nuevo temporizador**: horas, minutos, segundos y un nombre opcional («Sacar el pan del horno»).
- **Nueva alarma o recordatorio**: una hora (7:30, 19:05...) y un texto opcional; si la hora ya pasó, suena mañana. Puede repetirse todos los días.
- Pausar o reanudar un temporizador, decir lo que queda (Espacio) y eliminar (Suprimir).

La lista (Alt+L) dice el nombre, el tipo, cuándo suena y cuánto queda. Al vencer, suena un aviso cada pocos segundos durante dos minutos, se anuncia el texto y aparece una ventana delante de todo con **Posponer 5 minutos** y **Detener**. Se guardan en `data\db\temporizadores.json`: si una alarma vence con el programa cerrado, avisa al abrirlo.

En Teclas globales hay, sin tecla de fábrica, nuevo temporizador, nueva alarma y decir los temporizadores; también se encuentran en el lanzador.

## Lanzador

Control+Alt+Windows+Espacio, desde cualquier programa (o Archivo, Lanzador, Control+Mayúsculas+P), abre una ventana para encontrar y abrir cualquier cosa escribiendo:

- **Programas** instalados, de escritorio y de la Tienda: «bloc», «firefox», «config».
- **Ajustes de Windows**: «wifi», «bluetooth», «sonido», «notificaciones», «actualizaciones», «administrador de dispositivos»...
- **Acciones de Centro de Mando**: «crear escritorio», «micrófono», «emoticonos», «ver el área de audio», «opciones»... Así se pueden usar aunque no tengan tecla, y aprender las que sí la tienen.
- **Cálculos**: «2+2*3», «15% de 80», «1,5*4», «raiz(2)», «7/2». El primer resultado es el valor; Intro lo copia al portapapeles.

Se busca por trozos de palabras o por iniciales («adm disp» encuentra Administrador de dispositivos) y sin tildes. Al escribir se anuncia cuántos resultados hay y cuál es el primero. Intro en el buscador abre el primero; Flecha abajo baja a la lista **Resultados** (Alt+R), donde Intro abre el elegido. Lo que más usa aparece antes, y sin escribir nada se ven sus elementos más usados.

Las acciones de Centro de Mando se ejecutan sobre la ventana en la que estaba (por ejemplo, «Mover la ventana activa al escritorio siguiente»).

## Teclas globales

Herramientas, Teclas globales (Control+T) muestra todas las acciones con su atajo y su estado (Activa, Sin atajo o por qué no se pudo activar). Intro cambia un atajo: marque Control, Alt, Mayúsculas y Windows y elija la tecla. Suprimir lo quita; **Restablecer este** y **Restablecer todos** vuelven a los de fábrica.

Conviene evitar Control+Alt+flechas (las usan NVDA y JAWS en las tablas), Control+Alt+Mayúsculas+Windows con una letra (tecla Office) y cualquier combinación con Windows+L.

Algunas acciones no traen tecla de fábrica: crear un escritorio e ir a él, mover el escritorio, mover la ventana a un escritorio nuevo, anclar la aplicación y detener la captura del portapapeles o de las notificaciones.

## Opciones

Herramientas, Opciones (Control+coma), con pestañas:

- **General**: iniciar con Windows, arrancar oculto, icono en la bandeja, minimizar y cerrar a la bandeja, voz al arrancar y confirmar al eliminar escritorios.
- **Cambio de escritorio**: cíclico, foco a la última ventana y animación.
- **Anuncios**: qué se dice al cambiar de escritorio y con cuánto retraso.
- **Listas**: qué se dice al moverse por las columnas.
- **Portapapeles**: guardar o no, máximo de elementos, caducidad en días, formatos que se guardan, tamaño de imagen, privacidad, programas excluidos, restaurar tras pegar, forma de pegar y anunciar cada copia.
- **Emoticonos**: forma de insertar, tono de piel, mostrar el carácter y cuántos recientes se recuerdan.
- **Notificaciones**: guardar o no, cada cuánto se consulta, anunciar las nuevas, marcar como leídas, aplicaciones ignoradas, máximo y días.
- **Ventanas**: seguir a la ventana al moverla y aplicar las reglas al iniciar.
- **Avanzado**: hacer cíclicas las teclas de Windows, sondeo de escritorios y nivel de registro.

Los cambios se aplican al momento.

## La bandeja del sistema

Windows+B lleva a la bandeja. El lector dice el nombre del programa, el escritorio actual y, si las hay, las notificaciones sin leer. Intro muestra la ventana; la tecla Aplicaciones abre un menú con los escritorios, el historial del portapapeles, los emoticonos, el historial de notificaciones, las teclas globales, las opciones y Salir.

Si la bandeja oculta el icono, Control+Alt+Windows+G muestra la ventana.

## Acerca de e invitar a un café

- Ayuda, **Invítame a un café si te gusta mi trabajo** abre la página de donaciones de PayPal del autor.
- Ayuda, **Acerca de** muestra la versión, el autor y los datos técnicos, que se pueden copiar.

## Dónde guarda sus datos

Todo queda en la carpeta `data` junto al programa: configuración, historiales (`data\db`) y registros. Para hacer una copia de seguridad, copie la carpeta. Para desinstalarlo, desactive **Iniciar con Windows** y borre la carpeta.

Fuera de la carpeta solo se guarda la entrada de **Iniciar con Windows**, si la activa.

## Si algo falla

1. Herramientas, Abrir la carpeta de registros, y envíe a soporte el `sesion_*.log` más reciente.
2. Si el Explorador de Windows se reinicia, Centro de Mando se reconecta solo.
3. Si una tecla global no funciona, mire su estado en Teclas globales.
4. Si no se guardan notificaciones, revise el permiso de Windows (área de notificaciones, menú Acción, Permiso de Windows).
5. Si un emoticono no aparece en un programa, en Opciones, Emoticonos, elija **Pegar con Control+V**.
