# Centro de Mando

Centro de mando accesible para Windows: **escritorios virtuales**, **historial del portapapeles**, **emoticonos** y **notificaciones**, todo desde la bandeja del sistema, con teclas globales configurables y pensado desde la primera línea para personas que usan lector de pantalla (NVDA, JAWS, Narrador).

- Versión: 1.1.0
- Autor: Héctor J. Benítez Corredera
- Licencia: [GPL-3.0](LICENSE)
- Plataforma: Windows 10 y 11 de 64 bits
- Idioma: español

## Para personas usuarias

### Qué encontrará

**Escritorios virtuales**

- Cambio instantáneo con teclas globales: siguiente y anterior **cíclicos** (del último al primero), directo del 1 al 10, primero, último y volver al anterior.
- Opción para que también Control+Windows+flechas de Windows den la vuelta.
- Crear, renombrar, reordenar, eliminar (también todos los vacíos) y fondo por escritorio.
- Mover la ventana activa a otro escritorio o a uno nuevo, mostrarla en todos y buscar cualquier ventana en todos los escritorios.
- Reglas para llevar solas las ventanas de un programa a su escritorio.
- Al cambiar, el foco va a la última ventana usada. Con lector de pantalla el escritorio se oye una sola vez (Windows ya lo anuncia y Centro de Mando no lo repite); sin lector, lo dice Centro de Mando.

**Historial del portapapeles**

- Guarda textos con formato, listas de archivos e imágenes, sin duplicados.
- Control+Alt+Windows+V desde cualquier programa: buscar, elegir e Intro para **pegar donde estaba**; lo que tenía copiado vuelve al portapapeles al terminar.
- Pegar como texto sin formato o transformado (una línea, mayúsculas, minúsculas...), favoritos, nombres, caducidad y límite.
- Privacidad: respeta lo que los gestores de contraseñas marcan como privado y permite excluir programas.

**Emoticonos**

- Casi 4000 emojis con nombre y palabras clave en español (datos oficiales de Unicode), símbolos tipográficos y kaomoji.
- Control+Alt+Windows+E desde cualquier programa: búsqueda sin tildes que dice cuántos resultados hay e Intro para **escribirlo donde está el cursor**, sin tocar el portapapeles.
- Recientes, favoritos, tono de piel y varios emoticonos de una vez.

**Notificaciones**

- Historial propio de las notificaciones de Windows y de las aplicaciones: Windows las borra; Centro de Mando las guarda.
- Control+Alt+Windows+A abre el historial; Control+Alt+Windows+U dice la última y cuántas quedan sin leer.
- Leídas y no leídas, favoritas, búsqueda, filtro por aplicación, abrir la aplicación que la envió, descartar en Windows, ignorar aplicaciones y exportar a CSV.
- **No molestar** (Control+Alt+Windows+Q), a mano o con horario diario: calla los avisos automáticos sin dejar de guardar las notificaciones; algunas aplicaciones pueden anunciarse igualmente.

**Fragmentos de texto**

- Firmas, direcciones o respuestas guardadas que se insertan donde está el cursor (Control+Alt+Windows+T): escriba la abreviatura e Intro.
- Variables de fecha, hora y portapapeles.

**Audio**

- Cambiar la salida predeterminada con una tecla y oír su nombre, volumen general, volumen y silencio por aplicación y micrófono.
- Volumen y silencio **de la aplicación enfocada** con teclas globales, también en navegadores; «solo esta aplicación» sin silenciar nunca el lector.
- **Salida de audio por aplicación** (como el Mezclador de volumen de Windows) y aviso al conectar o desconectar dispositivos, sin vaivenes de monitores HDMI que reposan.

**Sistema**

- Estado del equipo anunciable (batería, procesador, memoria, disco, red) y energía: bloquear, suspender, hibernar, apagar la pantalla, apagado o reinicio programados y mantener despierto.

**Ventanas y procesos**

- Todas las ventanas abiertas y los procesos: activar, minimizar, maximizar, siempre encima (también con Control+Alt+Windows+K), cerrar y finalizar; uso de procesador y memoria.

**Temporizadores y alarmas**

- Temporizadores, alarmas y recordatorios (también diarios) con aviso sonoro, hablado y en pantalla; posponer y detener.

**Lanzador**

- Control+Alt+Windows+Espacio: escriba y abra al momento programas, ajustes de Windows o cualquier acción de Centro de Mando; también calcula («15% de 80»).

**En todo el programa**

- Ventana principal con siete áreas (Alt+1 a Alt+7), una barra de menús fija (Archivo, Acción, Ir, Ver, Herramientas, Ayuda) cuyo menú Acción cambia con el área, y ventanas rápidas para usar desde cualquier sitio.
- Todas las listas se recorren por columnas (flechas izquierda y derecha, Control+1 a 0), con lo que se dice configurable.
- Todas las teclas globales se pueden cambiar con un editor accesible que avisa de las combinaciones ocupadas.
- Portable: todo en la carpeta `data`, junto al programa.

### Instalación

1. Descomprima el ZIP en una carpeta con permiso de escritura (por ejemplo, Documentos\CentroDeMando).
2. Abra `CentroDeMando.exe`.
3. Para el historial de notificaciones, permita en Windows que las aplicaciones lean las notificaciones: Configuración, Privacidad y seguridad, Notificaciones (en el área de notificaciones, menú Acción, Permiso de Windows lleva allí).

### Actualizaciones

Ayuda, Buscar actualizaciones (y una comprobación automática que se puede desactivar). En Opciones, Actualizaciones, se elige la fuente: el servidor del autor, las [releases de GitHub](https://github.com/hxebolax/CentroDeMando/releases), las dos o una dirección propia. Cada versión va firmada digitalmente: una manipulada se rechaza. Se actualiza sin tocar la configuración ni los historiales y, si algo sale mal, vuelve sola a la versión anterior.

### Descarga

- Última versión: [releases de GitHub](https://github.com/hxebolax/CentroDeMando/releases/latest) o el servidor del autor.

### Documentación

- Manual completo: F1 dentro del programa, o [data/docs/manual.md](data/docs/manual.md).
- Lista de teclas: Control+F1, o [data/docs/teclas.md](data/docs/teclas.md).
- Novedades: [data/docs/novedades.md](data/docs/novedades.md).

### Teclas globales principales

- Control+Alt+Windows+Flecha derecha o izquierda: escritorio siguiente o anterior.
- Control+Alt+Windows+1 a 0: ir al escritorio 1 a 10.
- Control+Alt+Windows+V: historial del portapapeles.
- Control+Alt+Windows+E: emoticonos.
- Control+Alt+Windows+A: historial de notificaciones.
- Control+Alt+Windows+Q: No molestar.
- Control+Alt+Windows+G: mostrar u ocultar Centro de Mando.

### Si le gusta este trabajo

Puede invitar al autor a un café desde Ayuda, Invítame a un café si te gusta mi trabajo.

## Para programadores

### Tecnología

- Python 3.15 y wxPython 4.3 (Phoenix), compilado con cx_Freeze 8 (incluye los runtimes de Visual C++).
- Escritorios virtuales: [pyvda](https://github.com/mrob95/pyvda) (interfaces COM del Explorador, Windows 10 y 11, incluida la 24H2 y posteriores).
- Portapapeles: ctypes sobre la API Win32 (`AddClipboardFormatListener` en una ventana solo de mensajes) y SQLite.
- Notificaciones: `UserNotificationListener` de WinRT (paquetes `winrt-*`), con sondeo, y SQLite.
- Audio: [pycaw](https://github.com/AndreMiras/pycaw) (Core Audio). Sistema: [psutil](https://github.com/giampaolo/psutil) y la API de Windows.
- Emoticonos: datos de [CLDR](https://github.com/unicode-org/cldr-json) y [emoji-test.txt](https://unicode.org/Public/emoji/latest/emoji-test.txt) (Unicode License V3), preprocesados con `tools/generar_emojis.py`.
- Teclas globales: `RegisterHotKey` en un hilo propio; gancho `WH_KEYBOARD_LL` opcional solo para Control+Windows+flechas.

### Estructura

```
main.py                     Arranque (orden fijo: registro, configuración, wx, idioma, instancia única)
app/core/                   Rutas portables, versión, configuración JSON atómica, registro, voz
app/services/               Lógica sin wx
  escritorios.py            Motor de escritorios (pyvda) y modelos
  servicio.py               Hilo de escritorios: cola de operaciones y sondeo de cambios
  teclas.py                 Teclas globales y gancho de teclado
  acciones.py               Catálogo de acciones con sus atajos de fábrica
  reglas.py                 Reglas de ventanas
  portapapeles_win32.py     Leer, escribir y escuchar el portapapeles (ctypes)
  portapapeles.py           Historial SQLite y servicio de captura
  pegado.py                 Volver a la ventana de origen, pegar o teclear Unicode
  emojis.py                 Catálogo de emoticonos y búsqueda
  fragmentos.py             Fragmentos de texto y variables
  audio.py                  Dispositivos, volumen y sesiones de audio
  equipo.py                 Estado del equipo y energía
  lanzador.py               Lanzador: programas (Get-StartApps), ajustes, acciones y calculadora segura
  procesos.py               Ventanas abiertas y procesos (Win32 directo: rápido también con procesos protegidos)
  temporizadores.py         Temporizadores, alarmas y recordatorios
  notificaciones.py         Fuente WinRT, historial SQLite y servicio de sondeo
  ventanas_win32.py         Utilidades Win32 de ventanas y foco
  sistema.py                Inicio con Windows y tonos
  actualizador.py           Actualizaciones firmadas: varias fuentes, verificación, sustitución y vuelta atrás
app/ui/                     Interfaz wxPython
  ventana_principal.py      Ventana con cuatro áreas, menús y bandeja
  controlador.py            Une servicios, teclas, voz e interfaz
  area_*.py                 Áreas de portapapeles, emoticonos y notificaciones
  ventanas_rapidas.py       Ventanas rápidas globales
  listas.py                 Listas accesibles por columnas
  accesibilidad/            Componentes accesibles reutilizables
data/docs/                  Manual, teclas y novedades (se distribuyen)
data/emojis/                Datos de emoticonos en español (se distribuyen)
tools/generar_emojis.py     Genera data/emojis/emojis_es.json
tools/firmar_version.py     Claves y firma Ed25519 del version.json
tools/publicar.py           Empaqueta, firma y publica en el servidor y en GitHub
tests/                      Pruebas pytest (sin tocar data real ni el portapapeles real)
```

### Principios

- **Accesibilidad primero**: etiqueta creada justo antes de cada control, letras de acceso sin repetir por pantalla (lo comprueba `revisar_teclado` en las pruebas), listas que no se releen al actualizarse, voz solo para lo que el lector no puede saber.
- **La interfaz nunca se bloquea**: escritorios, teclas, portapapeles y notificaciones tienen su propio hilo; los controles solo se tocan con `wx.CallAfter`.
- **Portable**: todo en `data/`. Lo único fuera es la entrada opcional de inicio con Windows.
- **Nada se pierde en silencio**: cada error queda en `data/logs` con archivo, línea, hilo y traza.

### Entorno de desarrollo

Requiere Python 3.15 instalado (lanzador `py`).

```bash
entorno.bat crear
```

```bash
entorno.bat pruebas
```

```bash
entorno.bat ejecutar
```

```bash
entorno.bat compilar
```

`entorno.bat` sin argumentos abre un menú. La compilación deja el programa en `build\CentroDeMando` y comprueba que el `.exe` arranca.

Para regenerar los datos de emoticonos tras descargar versiones nuevas de CLDR y emoji-test.txt:

```bash
python tools/generar_emojis.py --origen adjuntos/datos_emoji
```

### Publicar una versión

1. Suba `APP_VERSION` en `app/core/version.py` (y en `pyproject.toml`) y escriba sus novedades en `data/docs/novedades.md` bajo `## <versión>`.
2. `entorno.bat compilar` (desde cero). `setup_cx.py` sustituye después el `python3t.dll` que copia cx_Freeze por el de `abi3t-compat`: el de la raíz de Python 3.15 reenvía al intérprete sin GIL y sin él `cryptography` (la verificación de firmas) no carga. `tools/publicar.py` se niega a publicar una compilación con el DLL equivocado.
   - Ojo: compilar borra `build/CentroDeMando` entero, incluida su carpeta `data` si se ha usado esa copia para probar.
3. Empaquetar, firmar y publicar:

```bash
.venv\Scripts\python.exe tools\publicar.py --servidor --github
```

`tools/publicar.py` crea `dist/CentroDeMando_v<versión>.zip` (todo dentro de la carpeta `CentroDeMando`) y `dist/version.json` con `app`, `version`, `file`, `sha256`, `size`, `date` y `novedades`, lo firma con Ed25519 (`tools/firmar_version.py`) y comprueba la firma con la clave pública del programa. Con `--servidor` copia primero el ZIP y después `version.json` a la carpeta web del servidor; con `--github` crea la release `v<versión>` con los dos archivos.

La clave privada está en `tools/claves/` y **nunca** se sube al repositorio ni al servidor (`.gitignore` la excluye). Sin ella no se pueden publicar versiones que acepten las instalaciones: guarde una copia fuera del equipo.

El actualizador (`app/services/actualizador.py`, del agente «actualizador») verifica la firma antes de leer nada, rechaza versiones anteriores a la ya confirmada en el equipo, extrae el ZIP con comprobaciones de seguridad y sustituye el programa con un `.bat` que hace copia de seguridad, no toca `data` salvo los recursos (`docs`, `emojis`...) y vuelve atrás si la versión nueva no confirma su arranque.

### Pruebas

```bash
.venv\Scripts\python.exe -m pytest -q
```

Las pruebas usan una carpeta `data` temporal (`APP_DATA_DIR`), un motor de escritorios simulado y una fuente de notificaciones simulada, y no muestran ventanas.

### Licencia

Centro de Mando es software libre bajo la [Licencia Pública General de GNU, versión 3](LICENSE).

### Licencias de terceros

- Datos de emoticonos: Unicode License V3 (`data/emojis/LICENCIA_UNICODE.txt`).
- pyvda (MIT), comtypes (MIT), wxPython (wxWindows Library Licence), winrt (MIT), accessible_output2 (MIT), pycaw (MIT), psutil (BSD), cryptography (Apache 2.0 o BSD).
