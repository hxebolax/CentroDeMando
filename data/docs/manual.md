# Manual de Centro de Mando

## Qué es

Centro de Mando reúne en un solo programa, accesible con lector de pantalla y manejable por completo con el teclado, cuatro herramientas para Windows 10 y 11:

- **Escritorios virtuales**: cambiar de escritorio al instante (también de forma cíclica), crearlos, ponerles nombre, ordenarlos, eliminarlos y mover ventanas entre ellos.
- **Historial del portapapeles**: todo lo que copia (textos, textos con formato, archivos e imágenes) queda guardado para pegarlo después donde esté.
- **Emoticonos**: casi 4000 emojis con nombre en español, símbolos tipográficos y kaomoji, que se escriben directamente en el programa en el que esté.
- **Notificaciones**: un historial de las notificaciones de Windows y de las aplicaciones, para que no se le pase ninguna.

Vive en la bandeja del sistema y responde a teclas globales que funcionan desde cualquier programa. Todas se pueden cambiar.

## Requisitos

- Windows 10 u 11 de 64 bits. Algunas funciones de escritorios (reordenarlos, fondo por escritorio, animación) solo existen en Windows 11.
- Funciona con NVDA, JAWS y Narrador. No necesita instalación: es portable.

## Primeros pasos

1. Descomprima el archivo ZIP en una carpeta con permiso de escritura (por ejemplo, en Documentos). No la ponga en Archivos de programa.
2. Abra `CentroDeMando.exe`. La ventana principal muestra cuatro pestañas: Escritorios, Portapapeles, Emoticonos y Notificaciones.
3. Pruebe desde cualquier programa:
   - Control+Alt+Windows+Flecha derecha: escritorio siguiente.
   - Control+Alt+Windows+V: historial del portapapeles.
   - Control+Alt+Windows+E: emoticonos.
   - Control+Alt+Windows+A: historial de notificaciones.

## La ventana principal

Tiene cuatro áreas en pestañas. Para cambiar de área:

- Control+Tabulador y Control+Mayúsculas+Tabulador.
- Alt+1 Escritorios, Alt+2 Portapapeles, Alt+3 Emoticonos, Alt+4 Notificaciones (también en el menú Ver).

Escape, Alt+F4 o minimizar ocultan la ventana en la bandeja: Centro de Mando sigue funcionando. Para cerrarlo del todo use Escritorios, Salir (Control+Q).

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

En el menú Escritorios también: crear con nombre (Control+Mayúsculas+N), eliminar los escritorios vacíos y fondo de pantalla (Windows 11).

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

Otros controles: **Buscar en el historial** (Alt+B, dice cuántos resultados hay), **Mostrar** (Alt+S: todo, favoritos, textos, imágenes o archivos) y **Contenido** (Alt+T, el texto completo).

Desde la pestaña Portapapeles de la ventana principal, Intro pega en la ventana que usaba antes de abrir Centro de Mando.

### Privacidad

- No se guarda lo que los gestores de contraseñas marcan como privado (KeePass, Bitwarden y otros lo hacen).
- En Opciones, Portapapeles, puede excluir programas por su nombre (por ejemplo, `keepass.exe`).
- Portapapeles, **Detener la captura** deja de guardar hasta que la vuelva a activar.
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

La primera vez, Windows debe permitir que las aplicaciones lean las notificaciones: Configuración, Privacidad y seguridad, Notificaciones. El menú Notificaciones, **Permiso de Windows**, abre esa página. Si no hay permiso, Centro de Mando lo dice.

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

Controles: **Buscar en las notificaciones** (Alt+B), **Mostrar** (Alt+S: todas, no leídas o favoritas), **Aplicación** (Alt+C) y **Contenido** (Alt+T).

En el menú Notificaciones: descartar en Windows, ignorar las de una aplicación, marcar todas como leídas, vaciar, exportar a CSV o texto y detener la captura.

Windows no avisa a los programas de las notificaciones nuevas: Centro de Mando le pregunta cada pocos segundos (Opciones, Notificaciones). Así también se guardan las que llegan con «No molestar».

NVDA ya lee las notificaciones cuando aparecen. Por eso **Anunciar las notificaciones nuevas por voz** viene desactivado; actívelo si quiere oírlas aunque esté con otro programa que no las lea.

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
4. Si no se guardan notificaciones, revise el permiso de Windows (menú Notificaciones, Permiso de Windows).
5. Si un emoticono no aparece en un programa, en Opciones, Emoticonos, elija **Pegar con Control+V**.
