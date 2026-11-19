# Novedades de Centro de Mando

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
