# Manual de Gestor de Escritorios Virtuales

## Qué es

Gestor de Escritorios Virtuales administra los escritorios virtuales de Windows 10 y 11 desde el teclado y con lector de pantalla: cambiar de escritorio al instante (también de forma cíclica, del último al primero), crearlos, ponerles nombre, ordenarlos, eliminarlos, mover ventanas entre ellos y mostrar ventanas en todos. Vive en la bandeja del sistema y responde a teclas globales que funcionan desde cualquier programa; todas se pueden cambiar.

## Requisitos

- Windows 10 u 11 de 64 bits. Algunas funciones (reordenar escritorios, fondo por escritorio, animación) solo existen en Windows 11.
- Funciona con NVDA, JAWS y Narrador. No necesita instalación: es portable.

## Primeros pasos

1. Descomprima el archivo ZIP en una carpeta donde tenga permiso de escritura (por ejemplo, en Documentos). No la ponga en Archivos de programa.
2. Abra `EscritoriosVirtuales.exe`.
3. El foco empieza en la lista de escritorios, sobre el escritorio actual.
4. Pruebe Control+Alt+Windows+Flecha derecha desde cualquier programa: pasará al escritorio siguiente y oirá su número y su nombre.

## Cambiar de escritorio rápidamente

Las teclas globales funcionan aunque la ventana del gestor esté oculta en la bandeja. Las de fábrica usan Control+Alt+Windows, una combinación que Windows no usa y que no choca con NVDA ni con JAWS.

- Siguiente y anterior: Control+Alt+Windows+Flecha derecha o izquierda. Con la opción **Cambio cíclico** (activada de fábrica), desde el último escritorio se vuelve al primero y al revés.
- Directo a un escritorio: Control+Alt+Windows+1 a 9, y 0 para el décimo.
- Primero y último: Control+Alt+Windows+Inicio o Fin.
- Volver al escritorio anterior: Control+Alt+Windows+Retroceso. Alterna entre los dos últimos escritorios, como Alt+Tab pero con escritorios.
- Elegir de una lista: Control+Alt+Windows+S abre una lista con todos los escritorios. Use las flechas, escriba el número o la primera letra, o escriba parte del nombre en el campo Filtrar (Alt+F). Intro va al escritorio; Escape cierra.

Al llegar a un escritorio, el gestor da el foco a la última ventana que usó en él (si no hay ninguna, al escritorio de Windows) y anuncia el escritorio. Ambas cosas se ajustan en Opciones.

### Hacer cíclicas las teclas de Windows

Windows ya trae Control+Windows+Flecha derecha e izquierda, pero se detienen en el primer y el último escritorio. En Opciones, pestaña Avanzado, la casilla **Hacer cíclicas Ctrl+Windows+Izquierda y Derecha** hace que también den la vuelta. Para ello el gestor vigila el teclado con un gancho; si nota cualquier problema con el teclado, desactívela.

## La ventana principal

Se muestra con Control+Alt+Windows+G, con un clic en el icono de la bandeja o abriendo el programa otra vez.

- **Lista de escritorios** (Alt+L): número, nombre, cuántas ventanas tiene y cuál es el actual.
  - Intro: ir al escritorio.
  - F2: cambiar el nombre. Si deja el nombre vacío, vuelve a llamarse «Escritorio N».
  - Suprimir: eliminar el escritorio. Sus ventanas no se cierran: pasan al escritorio vecino.
  - Alt+Mayúsculas+Flecha arriba o abajo: cambiar su posición.
  - Tecla Aplicaciones: menú contextual.
- **Ventanas del escritorio seleccionado** (Alt+T): título, programa y escritorio de cada ventana. Las que se muestran en todos los escritorios aparecen siempre, con «Todos» en la columna Escritorio.
  - Intro: cambiar al escritorio de la ventana y activarla.
  - Control+M: moverla a otro escritorio.
  - Suprimir: pedirle que se cierre (como Alt+F4; el programa puede preguntar si guarda).
  - Tecla Aplicaciones: todas sus acciones.
- En el menú Ver, **Ventanas de todos los escritorios** muestra en la segunda lista las ventanas de todos.
- **Barra de estado**: muestra lo último que se anunció.

### Moverse por las columnas de las listas

En todas las listas del gestor (escritorios, ventanas, teclas globales y reglas):

- Flecha izquierda y derecha: columna anterior y siguiente de la fila en la que está, sin cambiar de fila.
- Control+1 a Control+9: lee directamente esa columna; Control+0, la décima.
- Control+Mayúsculas+Inicio y Fin: primera y última columna.

Qué se dice de cada celda se elige en Opciones, pestaña Listas: el número de fila («Fila 2»), el nombre de la columna («Nombre») y el contenido («Correo»). Con las tres activadas se oye «Fila 2, Nombre, Correo». Si desactiva las tres, se dice igualmente el contenido.

Escape, Alt+F4 o minimizar ocultan la ventana en la bandeja; el gestor sigue funcionando. Para cerrarlo del todo use Escritorios, Salir (Control+Q).

## Gestionar escritorios

En el menú Escritorios o con teclas globales:

- **Crear un escritorio** (Control+N en la ventana; Control+Alt+Windows+N desde cualquier sitio). Control+Mayúsculas+N lo crea pidiendo antes el nombre.
- **Cambiar el nombre** (F2; Control+Alt+Windows+R para el escritorio actual).
- **Eliminar** (Suprimir; Control+Alt+Windows+F4 para el actual). De fábrica se pide confirmación; se puede quitar en Opciones.
- **Eliminar los escritorios vacíos**: borra los que no tienen ventanas, salvo el actual.
- **Subir y bajar en el orden** (Alt+Mayúsculas+Flecha arriba o abajo). Solo en Windows 11.
- **Fondo de pantalla** del escritorio seleccionado o de todos. Solo en Windows 11.

## Mover ventanas entre escritorios

Desde cualquier programa, sobre la ventana que tiene el foco:

- Control+Alt+Mayúsculas+Windows+Flecha derecha o izquierda: al escritorio siguiente o anterior.
- Control+Alt+Mayúsculas+Windows+1 a 9 y 0: a un escritorio concreto.
- Control+Alt+Windows+P: mostrar u ocultar la ventana en todos los escritorios.
- **Mover la ventana activa a un escritorio nuevo** y **Mostrar u ocultar la aplicación activa en todos los escritorios** no tienen tecla de fábrica: asígnesela en Teclas globales si las usa.

De fábrica la ventana se va sola y el foco pasa a la siguiente ventana del escritorio en el que está. Con la opción **Seguir a la ventana al moverla** (pestaña Ventanas) cambiará también al escritorio de destino.

Windows no deja mover ventanas de programas ejecutados como administrador si el gestor no se ejecuta también como administrador.

## Buscar una ventana en todos los escritorios

Control+Alt+Windows+B (o Control+F en la ventana) abre una lista con las ventanas de todos los escritorios: título, programa y escritorio. Filtre escribiendo parte del título y pulse Intro: el gestor cambia al escritorio de esa ventana y la activa.

## Información por voz

- Control+Alt+Windows+I: dice el escritorio actual.
- Control+Alt+Windows+V: dice cuántas ventanas hay en el escritorio actual y sus títulos.

En Opciones, pestaña Anuncios, se elige qué se dice al cambiar de escritorio: el número, el total de escritorios, cuántas ventanas tiene, un tono distinto para cada escritorio (más agudo cuanto mayor es el número) y si se anuncian también los cambios hechos fuera del gestor. El **retraso del anuncio** da tiempo a que el lector diga primero la ventana enfocada; si los anuncios se cortan, súbalo un poco.

Si no hay voz directa, lo anunciado se lee siempre en la barra de estado de la ventana.

## Teclas globales

Herramientas, Teclas globales (Control+T) muestra todas las acciones con su atajo y su estado:

- **Activa**: funciona.
- **Sin atajo**: la acción no tiene tecla.
- Un motivo, si Windows u otro programa ya usa esa combinación.

Para cambiar un atajo, seleccione la acción y pulse Intro (o el botón Cambiar). Marque las teclas que se mantienen pulsadas (Control, Alt, Mayúsculas, Windows) y elija la tecla en la lista. Hace falta al menos Control, Alt o Windows. Suprimir quita el atajo; **Restablecer este** y **Restablecer todos** vuelven a los de fábrica. Si elige una combinación que ya tiene otra acción, se le pregunta si se la quita. Los cambios se activan al pulsar Aplicar o Aceptar.

Combinaciones que conviene evitar:

- Control+Alt+flechas: NVDA y JAWS las usan para moverse por tablas.
- Control+Alt+Mayúsculas+Windows con una letra: es la «tecla Office» y abre programas.
- Cualquier combinación con Windows+L: bloquea el equipo.

## Reglas de ventanas

Herramientas, Reglas de ventanas (Control+R) lleva automáticamente las ventanas nuevas de ciertos programas a un escritorio, o las muestra en todos. Por ejemplo: «thunderbird.exe va al escritorio Correo».

Cada regla tiene:

- **Programa**: el ejecutable (la lista trae los programas con ventanas abiertas). Vacío vale para cualquiera.
- **Título contiene**: un texto del título. Vacío vale para cualquiera.
- **Escritorio de destino**: el número o el nombre. Con el nombre, la regla sigue funcionando aunque cambie el orden de los escritorios.
- **Mostrar en todos los escritorios** en lugar de moverla.
- **Regla activa**.

Se aplica la primera regla que encaja, por eso hay Subir y Bajar. De fábrica las reglas solo actúan sobre las ventanas que se abren después de arrancar el gestor; el botón **Aplicar ahora a las ventanas abiertas** las aplica a todas.

## Opciones

Herramientas, Opciones (Control+coma). Pestañas:

- **General**: iniciar con Windows, quedarse oculto en la bandeja al iniciar con Windows, arrancar siempre oculto, icono siempre en la bandeja, minimizar y cerrar a la bandeja, voz al arrancar y confirmar antes de eliminar.
- **Cambio de escritorio**: cambio cíclico, dar el foco a la última ventana del escritorio y animación de Windows.
- **Anuncios**: qué se dice al cambiar y con cuánto retraso.
- **Listas**: qué se dice al moverse por las columnas: número de fila, nombre de la columna y contenido de la celda.
- **Ventanas**: seguir a la ventana al moverla y aplicar las reglas al iniciar.
- **Avanzado**: hacer cíclicas las teclas de Windows, cada cuánto se comprueban los cambios hechos fuera del gestor y el nivel de detalle de los registros.

Los cambios se aplican al momento, sin reiniciar.

## La bandeja del sistema

Windows+B lleva a la bandeja; busque el icono con las flechas. El lector dice el nombre del programa y el escritorio actual, por ejemplo «Gestor de Escritorios Virtuales Escritorio 4: Trabajo». Intro o un clic muestran la ventana. La tecla Aplicaciones abre un menú con todos los escritorios (el actual va marcado; las cifras 1 a 9 llevan directamente a ellos), siguiente, anterior, crear, cambiar el nombre, eliminar, buscar una ventana, teclas globales, opciones y salir.

Si la bandeja oculta el icono, Control+Alt+Windows+G sigue mostrando la ventana.

## Acerca de e invitar a un café

- Ayuda, **Invítame a un café si te gusta mi trabajo** abre en el navegador la página de donaciones de PayPal del autor.
- Ayuda, **Acerca de** muestra la versión, el autor y los datos técnicos, que se pueden copiar al portapapeles para enviarlos a soporte.

## Dónde guarda sus datos

Todo queda en la carpeta `data` junto al programa: configuración (incluidas sus teclas y reglas), registros y documentación. Para hacer una copia de seguridad basta con copiar la carpeta. Para desinstalarlo, desactive antes **Iniciar con Windows** y borre la carpeta.

Lo único que se guarda fuera es la entrada de **Iniciar con Windows**, y solo si la activa: un valor en el registro de su usuario que se borra al desactivarla. Los nombres y el orden de los escritorios los guarda Windows.

## Si algo falla

1. Use Herramientas, Abrir la carpeta de registros.
2. Envíe a soporte el registro más reciente (archivos `sesion_*.log`).
3. Si el Explorador de Windows se reinicia, el gestor se reconecta solo en unos segundos.
4. Si una tecla global no funciona, mire su estado en Teclas globales: probablemente otro programa usa esa combinación.
