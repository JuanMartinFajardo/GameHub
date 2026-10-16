# GameHub Studio — editor visual

> Estado: **implementado** (Fase 5, rama `f5/studio`). Decisiones: [ADR-052 a 059](decisiones.md).

## 1. Qué es

Una aplicación web local donde un juego se diseña **como diagrama**, **como texto** o con los dos
a la vez, y se prueba en el mismo sitio. Las dos vistas son proyecciones del mismo árbol
sintáctico del archivo `.game` (la *IR de autor*): lo que se hace en el diagrama o en un
formulario llega al texto cambiando solo lo necesario —el resto conserva su formato y sus
comentarios— y lo que se escribe en el texto se ve en el diagrama en cuanto se analiza.

```bash
cd python && uv run gamehub studio ../games --open     # o un archivo: …/games/dudo/dudo.game
```

`gamehub studio [RUTA]` abre un servidor local (puerto 7421; `--port 0` para uno libre) con la
app, la API del espacio de trabajo y, por WebSocket, el servidor de lenguaje de Nomos y el
simulador. El enlace que imprime lleva un token; sin él no se puede usar (§9).

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ GameHub Studio  dudo/dudo.game ●  ✓ Compila  1 aviso   [Diagrama|Diagrama y texto|Texto]│
│                                   ↶ ↷  Reordenar  SVG  PNG  ▶ Simular  Guardar  ES ◐   │
├──────────────┬───────────────────────────────┬─────────────────────┬─────────────────┤
│ JUEGOS       │ 👤 decisión 👥 … 🎲 azar 🏁 final│ 1 // SPDX…           │ GAME Dudo       │
│ dudo/dudo    │      ●                          │ 2 import std.dice…   │ Título (es) …   │
│ tictactoe/…  │   ┌─────────────┐               │ …                    │ Jugadores 2..4  │
│ NODOS        │   │ 🎲 AZAR Roll │◄──────┐       │ 56 chance Roll {     │ Estado Opciones │
│ Roll  chance │   └──────┬──────┘       │       │ …                    │ Tipos Funciones │
│ Bid decision │   ┌──────▼──────┐  2.   │       │                      │ Pistas ui Tests │
│ End terminal │   │ 👤 Bid       │───────┘       │                      │ cup: per_player │
│              │   │ bid(q, f) ○──┘ 1. alive()==1 │                      │ …               │
│              │   │ dudo()    ○──────►🏁 End     │                      │                 │
├──────────────┴───────────────────────────────┴─────────────────────┴─────────────────┤
│ Problemas (1) · Simulador · Partidas masivas · Árbol · Comparar                         │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

## 2. El diagrama

| Elemento del modelo | Cómo se ve |
|---|---|
| `decision`, `simultaneous`, `window`, `chance`, `auto`, `terminal` | Una caja por nodo con su icono, su tipo y su color; dentro, un resumen (el actor, el modo de la ventana, los efectos del azar, los pagos) |
| `phase` | Contenedor con sus nodos dentro, su marca de inicio y, si se sale de ella (`-> exit`), su marca de salida; se **pliega** (pasa a ser una caja más y las flechas se reconducen a ella) |
| Acción | Una fila de la caja; si tiene transiciones propias, sus flechas salen de la fila |
| Transición | Flecha con su condición; si un nodo tiene varias, llevan su **número de orden** y la última sin condición dice «si no» |
| Inicio | Marca redonda con su flecha (la del flow y la de cada fase) |
| Estado | Punto de ruptura, error o aviso del nodo, nodo activo del simulador, flechas del último paso, número de veces que se pasó por cada nodo, acción o flecha (cobertura), añadido/cambiado/quitado al comparar |

La disposición se calcula con **ELK** (por capas, de arriba abajo; los ciclos se rompen por el
orden del texto, así que el flujo empieza arriba) y después manda lo que mueva el usuario, que se
guarda en el archivo hermano `<juego>.layout.json`:

```json
{ "version": 1,
  "games": { "Dudo": { "direction": "DOWN", "collapsed": ["Round"],
                       "nodes": { "start": {"x": 0, "y": 0}, "Roll": {"x": 12, "y": 76}, "exit:Round": {"x": 40, "y": 300} } } } }
```

Fuera del `.game`, la disposición no cambia las reglas ni su hash. Un nodo nuevo se coloca cerca
de quien apunta a él; «Reordenar» vuelve a calcularlo todo. Si el lienzo cambia de tamaño y no se
ha movido a mano, se vuelve a encuadrar; lo seleccionado se trae a la vista.

## 3. Diseñar

- **Paleta**: arrastrar un tipo de nodo al diagrama (dentro de una fase si se suelta en ella) o
  pulsarlo para añadirlo al final (o dentro de la fase seleccionada). Con la columna estrecha
  quedan solo los iconos.
- **Flechas**: arrastrar desde la salida de un nodo o de una acción a otro nodo crea una
  transición; arrastrar su punta a otro nodo la reconecta; seleccionarla y pulsar Supr (o
  Retroceso) la borra.
  Arrastrar un nodo dentro o fuera de una fase lo mueve allí (si era el inicio, el inicio pasa a
  ser la fase). Menú contextual de cada nodo: punto de ruptura, ver en el texto, borrar.
- **Inspector**, el formulario de lo seleccionado:
  - *Juego*: título (es/en), versión, jugadores; pestañas de **estado** (tipo, valor inicial y
    visibilidad: todos, nadie, el dueño o una condición), **opciones**, **tipos** (enumerados y
    structs), **funciones**, **pistas de ui** y **tests e invariantes** (con «Ejecutar los
    tests», que también comprueba los invariantes en 100 partidas al azar).
  - *Nodo*: nombre (renombra en todo el archivo), tipo, documentación, miembros (actor, actores,
    elegibles, modo, orden, pagos, puesto), bloques (`on_enter`, `on_exit`, `resolve`, efectos),
    `let` de los finales, inicio de una fase, acciones y transiciones.
  - *Acción*: nombre, parámetros (uno por línea: `c in cells(board)`,
    `@visible(owner) card: Card in hand[actor]`), condición, efectos, visibilidad y sus
    transiciones. *Transición*: destino, condición, efectos y orden.
  - Los campos de Nomos son editores pequeños con resaltado y autocompletado de los nombres del
    juego; se confirman al salir (o con Intro / Ctrl+Intro) y, si el servidor rechaza lo escrito,
    el error se marca en el sitio exacto del campo.
- **Diseñador de componentes**: barajas (la francesa de `std.cards` o una propia de palos ×
  valores), tableros de rejilla y de grafo (casillas y conexiones) y dados (con el nodo de azar
  que los tira y a dónde sigue); genera Nomos y lo inserta.
- **Juego nuevo** desde una plantilla (vacío, carrera, tablero, cartas, dados, matriz 2×2; las
  mismas de `gamehub new --template`).
- Deshacer y rehacer (los del editor de texto: un cambio del diagrama es un paso más), guardar
  (Ctrl/Cmd+S; si el archivo cambió en el disco desde que se abrió, avisa antes de pisarlo) y
  recarga sola si otro editor lo cambia y aquí no hay cambios.

## 4. Texto ↔ diagrama

- **Del diagrama al texto.** Cada gesto es una lista de **operaciones** (`addNode`,
  `addTransition`, `updateAction`, `setMember`, `moveNode`, `addTest`… unas 45, en
  `gamehub.studio.edits`) que el servidor aplica a una copia del árbol. El texto se reescribe solo
  donde cambió: los elementos iguales conservan su texto tal cual (con su formato y comentarios)
  y los nuevos o cambiados se escriben con el formateador, a su sangría. El resultado se comprueba
  siempre volviendo a analizarlo (mismo árbol, mismos comentarios); si la reescritura parcial no
  sabe, se formatea el archivo entero, que también los conserva. Al editor llegan los cambios
  mínimos (en UTF-16) y se aplican como una edición más.
- **Renombrar** no pasa por el árbol: cambia cada aparición según el índice de símbolos del
  comprobador; si chocaría con otro nombre o el juego dejaría de compilar, se rechaza.
- **Del texto al diagrama.** Cada cambio del texto se analiza (en un hilo, 150 ms después del
  último; los que vienen del diagrama, al momento) y llega el modelo del documento: lo que dibujan
  el diagrama y los formularios, con el texto de cada expresión y su posición. Con el texto roto,
  el diagrama sigue enseñando el último modelo (sin dejar editar) hasta que se arregla.
- **Selección sincronizada**: lo seleccionado en el diagrama se resalta en el texto y, al mover
  el cursor en el texto, se selecciona en el diagrama lo que hay debajo.
- Garantías con **tests de propiedad** (Hypothesis) sobre todos los juegos del catálogo:
  ediciones al azar dejan un texto válido y conservan los comentarios, y renombrar cada símbolo
  ida y vuelta deja el archivo igual. Del clic en la paleta al nodo dibujado: unos 70 ms.

## 5. Verificar

- **Problemas** en vivo (errores y avisos del compilador, con su ayuda); pulsar uno lo señala en
  el diagrama y en el texto. El peor de cada nodo se marca en su caja.
- **Clasificación** del juego (información perfecta, azar, simultáneo, suma cero…) y **tamaño
  estimado** del árbol (estimador de Knuth sobre paseos al azar).
- **Tests e invariantes** del juego, desde el inspector (ver §3).

## 6. Simular y depurar

- **Jugar** como cualquier asiento, con la UI genérica de la Fase 4: cada asiento puede ser
  humano, al azar o «primera jugada legal».
- **Vistas lado a lado** de los asientos que se elijan y **vista omnisciente**: se comprueba a
  ojo quién ve qué.
- **Paso a paso y viaje en el tiempo**: la historia completa se conserva (los estados son
  inmutables); volver a un paso y jugar otra cosa la recorta. **Azar**: sorteado o elegido de la
  lista de resultados con su probabilidad.
- **Correr** con los jugadores automáticos hasta el final, hasta que toque a un humano o hasta
  un **punto de ruptura**: llegar a un nodo (desde el diagrama o el inspector) o una condición
  escrita en Nomos (`quantity >= 3`), comprobada al escribirla.
- **Recargar** las reglas tras editar el juego, repitiendo la historia mientras siga siendo legal.
- En el diagrama, el **nodo activo** y las **flechas del último paso**.
- **Partidas masivas**: cientos de partidas al azar con estadísticas (terminadas, cortadas,
  errores de reglas con su partida, longitud, victorias y empates, pago medio por asiento) y la
  **cobertura** en el diagrama: cuántas veces se pasó por cada nodo, acción y flecha (en rojo lo
  que nunca se usó).
- **Árbol** del juego desde el paso actual (juegos pequeños): abrir ramas y contar estados,
  finales y profundidad (con límite de 5 s).

## 7. Comparar y exportar

- **Comparar** con una versión de git del archivo o con otro archivo: nodos y flechas añadidos,
  cambiados y quitados se colorean en el diagrama (los quitados, como fantasmas).
- **Exportar** el diagrama a **SVG** (rectángulos, flechas y texto de verdad) o **PNG**.

## 8. Por dentro

| Parte | Dónde | Qué hace |
|---|---|---|
| Servidor | `gamehub.studio.server` | Starlette: la app, la API (`/api/workspace`, `/api/file`, `/api/layout`, `/api/new`, `/api/git/log`, `/api/git/show`) y el WebSocket `/lsp` |
| Sesión | `gamehub.studio.session` | Por conexión: el servidor de lenguaje (pygls) más `gamehub/analysis` (notificación tras cada análisis), `gamehub/edit`, `gamehub/modelOf`, `gamehub/tests` y `gamehub/sim.*` |
| Ediciones | `gamehub.studio.edits` | Las operaciones sobre el árbol, la reescritura mínima y su comprobación; renombrar |
| Modelo | `gamehub.studio.model` | El modelo del documento (posiciones en UTF-16) |
| Simulador | `gamehub.studio.sim` | Historia, correr, puntos de ruptura, partidas masivas con cobertura, árbol, tamaño |
| Lenguaje | `gamehub.lsp` | Diagnósticos, autocompletado, hover, definición, referencias, renombrar, formato… (también `gamehub lsp` por la entrada estándar, para cualquier editor) |
| Web | `@gamehub/nomos`, `@gamehub/studio`, `web/apps/studio` | Nomos para CodeMirror; la app como librería de React (conexión, estado, diagrama, editores, inspector, simulador, herramientas); la app que sirve `gamehub studio` |

En el navegador: **React Flow** (lienzo) + **ELK** (disposición, cargado aparte la primera vez)
+ **CodeMirror 6** con su cliente LSP (el editor y los campos). La rueda de Python lleva la app
compilada (`gamehub/studioapp`); en desarrollo, `pnpm dev:studio` con `gamehub studio` detrás.

## 9. Seguridad

El Studio lee y escribe archivos: por defecto solo escucha en esta máquina (127.0.0.1), exige un
**token aleatorio** (va en el enlace; la app lo guarda en una cookie solo para este origen, o en
la cabecera `x-gamehub-token`), comprueba la cabecera **Host** (contra el *DNS rebinding*) y el
**Origin** de los WebSocket, y solo abre y guarda archivos `.game` dentro del directorio de
trabajo. Con `--host` fuera de la máquina avisa de que cualquiera con el enlace puede editar.

## 10. Límites y siguientes pasos

- Sin **edición colaborativa** en tiempo real (CRDT): un archivo, una pestaña.
- Las condiciones y efectos se escriben en Nomos (con autocompletado); los **bloques tipo
  Scratch** para quien no programa quedan para después ([pregunta 6](preguntas-abiertas.md)).
- Mover una acción de un nodo a otro arrastrándola no está: se hace en el texto.
- La extensión de VS Code sigue con `gamehub check`/`fmt`; pasarla al LSP (`gamehub lsp`)
  necesita empaquetar un cliente LSP en ella.
- El Studio necesita el servidor local: sin él (en el hub, o sin Python) llegará con el motor en
  WASM (F8) y el hub (F10).
