# Novedades de Centro de Mando

## 2.2.0

- **Lanzador** (Control+Alt+Windows+Espacio, o Archivo, Lanzador, Control+Mayúsculas+P): escriba y abra al momento cualquier programa instalado (de escritorio o de la Tienda), un ajuste de Windows o cualquier acción de Centro de Mando. Busca por trozos de palabras o iniciales, sin tildes, y lo más usado sube.
- El lanzador también **calcula**: «15% de 80», «2+2*3», «raiz(2)»... Intro copia el resultado.

## 2.1.0

- **Barra de menús nueva**, más corta y siempre igual: Archivo, Acción, Ir, Ver, Herramientas y Ayuda. El menú **Acción** cambia con el área en la que está y tiene las mismas órdenes que el menú contextual.
- Las áreas se recorren con **Alt+1 a Alt+7** (menú Ir): Escritorios, Portapapeles, Fragmentos, Emoticonos, Notificaciones, Audio y Sistema. Control+E lleva al buscador del área.
- **Fragmentos de texto** (Control+Alt+Windows+T): textos guardados que se insertan al instante, con abreviatura, categoría y variables (fecha, hora, portapapeles).
- **Audio**: cambiar la salida predeterminada (Control+Alt+Windows+O), volumen general (Control+Alt+Windows+Flecha arriba y abajo), volumen y silencio de cada aplicación, y silenciar el micrófono (Control+Alt+Windows+M).
- **Sistema**: estado del equipo (Control+Alt+Windows+F12 lo dice), bloquear, suspender, hibernar, apagar la pantalla, apagar o reiniciar con cuenta atrás y mantener el equipo despierto.
- Portapapeles: nuevas teclas globales (sin asignar de fábrica) para pegar directamente uno de los 9 últimos elementos.
- Notificaciones, correcciones:
  - La versión compilada no guardaba la aplicación de cada notificación; ahora sí, y las ya guardadas se completan solas.
  - Con «No leídas», las que se van leyendo ya no desaparecen de la lista hasta cambiar de filtro.
  - Menú contextual con todas las acciones.
- Cambian algunas letras: en Portapapeles la lista es Alt+D; en Notificaciones, Aplicación es Alt+N.

## 2.0.0

- El programa pasa a llamarse **Centro de Mando** y organiza la ventana principal en cuatro áreas: escritorios, portapapeles, emoticonos y notificaciones (Alt+1 a Alt+4).
- **Historial del portapapeles**: textos con formato, archivos e imágenes; búsqueda, favoritos, nombres, pegar en la ventana de la que se vino (Control+Alt+Windows+V), pegar sin formato o transformado, y lo que había copiado vuelve al portapapeles al terminar. Respeta lo que los gestores de contraseñas marcan como privado.
- **Emoticonos**: casi 4000 emojis con nombre en español, símbolos tipográficos y kaomoji; búsqueda sin tildes, recientes, favoritos y tono de piel; se escriben directamente donde está el cursor (Control+Alt+Windows+E).
- **Notificaciones**: historial de las notificaciones de Windows y de las aplicaciones, con leídas, favoritas, filtro por aplicación, abrir la aplicación, descartar en Windows, exportar y aviso de las no leídas en la bandeja (Control+Alt+Windows+A y Control+Alt+Windows+U).
- Al buscar en las listas se anuncia cuántos resultados hay.
- «Decir las ventanas del escritorio actual» pasa a Control+Alt+Windows+W.
- De fábrica ya no se repite el anuncio de los cambios de escritorio hechos con las teclas de Windows, porque NVDA ya los dice.
- Si tenía activado «Iniciar con Windows» con el nombre anterior, se cambia solo al nuevo.


## 1.1.0 (Gestor de Escritorios Virtuales)

- Requiere Python 3.15 (la versión compilada lo lleva incluido).
- En todas las listas: flechas izquierda y derecha para recorrer las columnas, Control+1 a 0 para leer una columna y Control+Mayúsculas+Inicio o Fin para la primera o la última.
- Nueva pestaña Listas en Opciones: elegir si se dice el número de fila, el nombre de la columna y el contenido de la celda.
- El icono de la bandeja ya no repite el nombre del programa: dice solo el escritorio actual.
- Nuevo en Ayuda: Invítame a un café si te gusta mi trabajo.
- Acerca de muestra el autor.
- La versión compilada ocupa unos 30 MB menos.

## 1.0.0

- Primera versión.
- Cambio de escritorio instantáneo con teclas globales: siguiente y anterior cíclicos, directo del 1 al 10, primero, último, volver al anterior y lista rápida con filtro.
- Opción para hacer cíclicas también Control+Windows+Flecha derecha e izquierda de Windows.
- Crear, cambiar el nombre, ordenar, eliminar (también los vacíos) y poner fondo a los escritorios.
- Mover la ventana activa a otro escritorio o a uno nuevo, mostrarla en todos y buscar ventanas en todos los escritorios.
- Reglas para llevar automáticamente las ventanas de un programa a un escritorio.
- Anuncios configurables al cambiar de escritorio, con tono opcional por escritorio.
- Teclas globales cambiables con un editor accesible que avisa de las combinaciones ocupadas.
- Icono permanente en la bandeja con menú de escritorios e inicio con Windows opcional.
