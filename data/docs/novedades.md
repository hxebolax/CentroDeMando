# Novedades de Centro de Mando

## 1.4.0

Audio:

- **Amplificación del micrófono** (Alt+L en el área de audio), en los micrófonos que la tienen.
- **Volumen máximo por aplicación**: si una aplicación o una web sube su volumen por encima, se le baja.
- **Ocultar aplicaciones** de la lista de aplicaciones con sonido, y verlas de nuevo cuando quiera.
- **Mejoras de audio** de cada salida: activarlas o desactivarlas desde el menú Acción.
- **Qué hace Windows durante las llamadas** con los demás sonidos: silenciarlos, bajarlos o nada (Opciones, Audio). Con lector de pantalla, «No hace nada» evita que la voz baje de golpe.
- Si cambia **Escuchar este dispositivo** desde el Panel de sonido de Windows, Centro de Mando lo dice.

Portapapeles:

- **Cifrar el historial** con la protección de datos de Windows: solo su usuario puede leerlo. Se cifra también lo ya guardado y la búsqueda sigue funcionando.
- Al buscar, **los favoritos salen primero**, y una tecla global nueva abre **solo los favoritos**.

## 1.3.0

- **Cambio automático al dispositivo preferido**: ordene sus salidas y micrófonos favoritos (área de audio, menú Acción) y, al conectar los auriculares, el sonido pasa a ellos; al apagarlos, vuelve al siguiente de la lista. Se recuerdan por nombre, aunque cambien de puerto.
- **Silenciar al bloquear el equipo**: con Windows+L se silencian las aplicaciones y el micrófono, y al volver recuperan el sonido. El lector de pantalla no se silencia nunca (Opciones, Audio).
- **Copias de seguridad automáticas** cada día, con las 7 últimas guardadas (Opciones, Copias de seguridad).
- **Exportar e importar la configuración y los datos** (menú Herramientas): opciones, teclas, reglas, perfiles, fragmentos, alarmas e historiales en un ZIP, para otro equipo o como copia. Al importar se guarda antes lo que había y se aplica al reiniciar, que se puede hacer en ese momento.

## 1.2.0

Audio, mucho más completo:

- **Volumen y silencio de la aplicación seleccionada** en el área de audio, con un deslizador y una casilla como los generales (Alt+P y Alt+R). Y una casilla para **silenciar el sonido general** (Alt+N).
- **Micrófonos**: lista de micrófonos (Intro lo pone como predeterminado), **volumen del micrófono**, silencio y **Escuchar este dispositivo** para oírlo por los auriculares o altavoces, eligiendo por cuál. Funciona sin permisos de administrador.
- **Balance** izquierda y derecha de la salida (Alt+B), también con teclas globales.
- **Dispositivo de comunicaciones** aparte, de salida y de micrófono: la música por un sitio y las llamadas por otro.
- **Perfiles de audio**: guarde salidas, micrófonos y volúmenes con un nombre y aplíquelos de una vez, también con una tecla global que pasa al siguiente.
- **Bloquear el volumen del micrófono** para que Teams, el navegador u otros programas no lo cambien, y **silenciar el micrófono al arrancar** (Opciones, Audio).
- **Quién usa el micrófono o la cámara**, en el menú Acción y con tecla global.
- Nuevas teclas globales, sin tecla de fábrica para no ocupar combinaciones: subir y bajar el micrófono, escucharlo, decir su estado, balance, siguiente perfil y privacidad.
- El área de audio se actualiza sola cada dos segundos mientras está a la vista.

## 1.1.0

Correcciones:

- **El escritorio se oye una sola vez.** Con lector de pantalla, Windows ya dice el escritorio al que se llega aunque el cambio lo haga Centro de Mando, y se oía dos veces. Ahora, en modo automático (el de fábrica), Centro de Mando no lo repite; sin lector de pantalla lo sigue diciendo él. Nueva opción en Opciones, Anuncios, **Anunciar el escritorio al cambiar**: automático, solo los cambios propios, todos o nunca. Quien tenía el anuncio activado pasa a automático.
- **El icono de la bandeja ya no dice «Conectando con los escritorios virtuales».** Windows 11 se quedaba con ese primer texto para siempre; ahora el icono se llama «Centro de Mando» y se corrige solo en las instalaciones anteriores.
- **Avisos de dispositivos de audio sin vaivenes.** Un monitor por HDMI (por ejemplo ASUS) decía «Desconectado», «Conectado», «Desconectado»... al reposar o despertar la pantalla. Ahora los avisos esperan a que el cambio se asiente, un dispositivo con varias entradas avisa una vez y el audio de monitores y televisores no avisa salvo que se active.
- **Actualizaciones automáticas.** La versión compilada no podía comprobar la firma de las actualizaciones (le faltaba una pieza de la biblioteca criptográfica). Corregido; la 1.0.0 debe actualizarse a mano esta vez, descargando el paquete.
- **Registro de fallos más claro.** `fallo_nativo.log` recogía excepciones que Windows gestiona sin cerrar el programa. Ahora se resumen en el registro de la sesión y el archivo solo queda si el programa se cierra de golpe.

Novedades:

- **No molestar** (Control+Alt+Windows+Q, menú de la bandeja o lanzador): calla los avisos automáticos (notificaciones nuevas, dispositivos de audio, copias) sin dejar de guardar las notificaciones ni de sonar las alarmas. Con horario diario opcional y aplicaciones que se anuncian igualmente. La bandeja dice cuándo está activo.
- **Anunciar solo las notificaciones de algunas aplicaciones** (Opciones, Notificaciones).
- Con **Decir cuántas ventanas tiene** y lector de pantalla, tras el anuncio de Windows se dice solo «3 ventanas» o «Vacío».

## 1.0.0

Primera versión pública. Centro de Mando reúne, accesible con lector de pantalla y desde la bandeja del sistema:

- Escritorios virtuales: cambio instantáneo y cíclico con teclas globales, crear, renombrar, ordenar y eliminar, mover ventanas entre escritorios, mostrarlas en todos y reglas para llevar cada programa a su escritorio.
- Historial del portapapeles: textos con formato, archivos e imágenes; buscar, favoritos, pegar en la ventana de origen (también sin formato o transformado) y pegar con una tecla uno de los nueve últimos. Respeta lo que los gestores de contraseñas marcan como privado.
- Fragmentos de texto: firmas y respuestas habituales que se insertan con su abreviatura, con variables de fecha, hora y portapapeles.
- Emoticonos: casi 4000 emojis con nombre en español, símbolos tipográficos y kaomoji, con búsqueda sin tildes, recientes, favoritos y tono de piel.
- Notificaciones: historial de las de Windows y de las aplicaciones, con leídas, favoritas, filtro por aplicación, abrir la aplicación, descartar y exportar.
- Audio: salida predeterminada, volumen general y de cada aplicación, salida por aplicación, micrófono, aviso al conectar dispositivos y control del sonido de la aplicación enfocada, incluido «solo esta aplicación».
- Sistema: estado del equipo y energía (bloquear, suspender, apagado programado, mantener despierto).
- Ventanas y procesos: activar, siempre encima, cerrar y finalizar; procesador y memoria de cada proceso.
- Temporizadores, alarmas y recordatorios con aviso sonoro, hablado y en pantalla.
- Lanzador: programas, ajustes de Windows y cualquier acción de Centro de Mando, más una calculadora.
- Actualizaciones automáticas firmadas desde el servidor del autor, GitHub, los dos o una dirección personalizada.
- Más de cincuenta teclas globales configurables, listas que se recorren por columnas y barra de menús con menú Acción según el área.
