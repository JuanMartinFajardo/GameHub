# Registro de decisiones (ADR)

> Cada decisión de arquitectura queda aquí con su contexto. Estados: **Aceptada** (firme),
> **Propuesta** (recomendación, pendiente de tu visto bueno), **Pendiente** (falta información).
> Las aceptadas "sin objeciones" se propusieron y el usuario pidió seguir adelante sobre ellas.

| ADR | Decisión | Estado |
|---|---|---|
| 001 | La GameIR es la única fuente de verdad; texto y diagrama son vistas | Aceptada (2026-10-09, sin objeciones) |
| 002 | Lenguaje de expresiones puro, tipado y total (sin lambdas Python) | Aceptada (2026-10-09, sin objeciones) |
| 003 | Azar solo en nodos `chance`; RNG con semilla; determinismo total | Aceptada (2026-10-09, sin objeciones) |
| 004 | Estados inmutables, sin singletons; el bucle de partida fuera del motor | Aceptada (2026-10-09, sin objeciones) |
| 005 | Visibilidad declarativa por ubicación; vistas derivadas; servidor autoritativo | Aceptada (2026-10-09, sin objeciones) |
| 006 | El flow es un statechart jerárquico con un conjunto cerrado de tipos de nodo | Aceptada (2026-10-09, sin objeciones) |
| 007 | Motor de referencia en Python primero; C++ después, con conformidad diferencial | Aceptada (2026-10-09, sin objeciones) |
| 008 | Git como backend de versiones; GameHub añade la capa semántica | Aceptada (2026-10-09, sin objeciones) |
| 009 | Protocolo WebSocket + JSON, contratos en JSON Schema | Aceptada (2026-10-09, sin objeciones) |
| 010 | Interoperar con OpenSpiel / Gambit / PettingZoo antes de reimplementar | Aceptada (2026-10-09, sin objeciones) |
| 011 | Monorepo (spec, python, core, web, stdlib, games, docs) | Aceptada (2026-10-09, sin objeciones) |
| 012 | Web en TypeScript + React (+ React Flow, Monaco; Monaco → CodeMirror en ADR-054) | Aceptada (2026-10-09, sin objeciones) |
| 013 | Software en Python 3 y C++ (C++ para cálculo pesado) | **Aceptada** (decisión del usuario) |
| 014 | Extensión de archivo `.game` | **Aceptada** (decisión del usuario) |
| 015 | Documentación en español; código e identificadores en inglés | Aceptada (2026-10-09, sin objeciones) |
| 016 | Licencias: Apache-2.0 / AGPL-3.0 (hub) / CC-BY-4.0 (juegos) | **Aceptada** (2026-10-09) |
| 017 | El lenguaje se llama **Nomos** (archivos `.game`) | **Aceptada** (2026-10-09) |
| 018 | Sintaxis con llaves y palabras clave en inglés | **Aceptada** (2026-10-09) |
| 019 | IR v0.1: visibilidad por predicados; zonas ordenadas vs. bolsas; sin identidades ocultas | Aceptada (2026-10-09, sin objeciones) |
| 020 | Catálogo de operadores (`ops.json`) como fuente única; esquemas generados | Aceptada (2026-10-09, sin objeciones) |
| 021 | La Fase 0 especifica solo la IR núcleo (resuelta); la IR de autor llega con el compilador (F2) | Aceptada (2026-10-09, sin objeciones) |
| 022 | PCG32 (implementación de referencia en C) es el RNG normativo de todos los motores | Aceptada (2026-10-09, F1) |
| 023 | Validación con JSON Schema + comprobador propio (sin pydantic); el motor compila la IR a funciones | Aceptada (2026-10-09, F1) |
| 024 | `$exit`: primero `on_exit` de la fase y después sus transiciones | Aceptada (2026-10-09, F1) |
| 025 | El hash de reglas ignora valores por defecto explícitos (listas vacías, visibilidad `all`) | Aceptada (2026-10-09, F1) |
| 026 | Cada fase en su rama (`fN/…`); un commit por tarea; fusión a `main` con visto bueno | Aceptada (2026-10-09, usuario) |
| 027 | Parser de Nomos escrito a mano (descenso recursivo), no con Lark | Aceptada (2026-10-10, usuario) |
| 028 | Ningún nombre local oculta un global del juego, salvo en funciones de módulo | Aceptada (2026-10-10, usuario) |
| 029 | Azúcar guiado por los tipos; comprobación y traducción a la IR en una sola pasada | Aceptada (2026-10-10, usuario) |
| 030 | Tests e invariantes fuera de la IR, con una semántica de ejecución propia | Aceptada (2026-10-10, usuario) |
| 031 | Módulos: declaraciones externas con poda; resolución std → dependencias → relativa | Aceptada (2026-10-10, usuario) |
| 032 | Mods sobre el modelo (AST) y combinadores como transformaciones de la IR | Aceptada (2026-10-10, usuario) |
| 033 | Paquetes con `game.toml` y `game.lock` (commits de git), sin registro central | Aceptada (2026-10-10, usuario) |
| 034 | Análisis estáticos sobre la IR, situados en el texto con un mapa de fuentes | Aceptada (2026-10-10, usuario) |
| 035 | Formato canónico al estilo Prettier; el parser admite continuar tras `=`, `requires`, `when` | Aceptada (2026-10-10, usuario) |
| 036 | Servidor de partidas sobre Starlette + uvicorn (sin FastAPI ni pydantic); contratos en JSON Schema | Aceptada (2026-10-10, usuario) |
| 037 | Núcleo de salas puro (sin E/S ni reloj propio) y transporte fino | Aceptada (2026-10-10, usuario) |
| 038 | Una actualización por entrada, `seq` sin huecos y rechazo por turno vigente | Aceptada (2026-10-10, usuario) |
| 039 | Observador público en el motor: los espectadores no ocupan asiento | Aceptada (2026-10-10, usuario) |
| 040 | Azar verificable `gamehub-fair/1`: compromiso, semillas de los jugadores y semilla de 53 bits | Aceptada (2026-10-10, usuario) |
| 041 | Abandonar = último puesto y un bot juega por el asiento; la partida acaba si queda uno | Aceptada (2026-10-10, usuario) |
| 042 | LAN: puerto 7420, enlace `/r/CÓDIGO` con QR, anuncio mDNS `_gamehub._tcp` y sesiones guardadas | Aceptada (2026-10-10, usuario) |
| 043 | Bots en red con la misma interfaz `Agent` que en proceso | Aceptada (2026-10-10, usuario) |
| 044 | Cliente web: workspace de pnpm en la raíz (web/ y games/*/ui), TypeScript 7, React 19, Vite 8, Biome, Vitest | Aceptada (2026-10-11, usuario) |
| 045 | Tipos TS del protocolo con el mismo generador que los de Python | Aceptada (2026-10-11, usuario) |
| 046 | El servidor de partidas sirve la app web (mismo origen; el enlace y el QR abren la app) | Aceptada (2026-10-11, usuario) |
| 047 | Pistas de presentación `ui { … }`: catálogo cerrado, comprobadas y fuera del hash de reglas | Aceptada (2026-10-11, usuario) |
| 048 | UI genérica guiada por los tipos y los dominios de las acciones; constructor de acciones | Aceptada (2026-10-11, usuario) |
| 049 | Partidas en un mismo dispositivo con una conexión por asiento contra el servidor | Aceptada (2026-10-11, usuario) |
| 050 | UIs propias como paquetes en games/<juego>/ui, registradas solas; plantilla y tipos por juego | Aceptada (2026-10-11, usuario) |
| 051 | Sin dependencias de estado ni de idiomas: reductor puro + useSyncExternalStore, catálogos propios | Aceptada (2026-10-11, usuario) |
| 052 | Studio: el `.game` es lo único que se guarda; diagrama y formularios editan el árbol con operaciones y reescritura mínima comprobada | **Propuesta** (F5) |
| 053 | Servidor de lenguaje con pygls: `gamehub lsp` por stdio y el mismo servidor, con métodos `gamehub/…`, por el WebSocket del Studio | **Propuesta** (F5) |
| 054 | Editor de texto y campos con CodeMirror 6 y su cliente LSP, no Monaco | **Propuesta** (F5) |
| 055 | Diagrama con React Flow + ELK (por capas, ciclos por el orden del texto); disposición en `<juego>.layout.json` | **Propuesta** (F5) |
| 056 | Índice de símbolos del comprobador (posiciones de nombres, usos resueltos, tipos) para el LSP y para renombrar | **Propuesta** (F5) |
| 057 | Seguridad del Studio: solo local, token, Host y Origin comprobados, archivos `.game` del directorio de trabajo | **Propuesta** (F5) |
| 058 | Simulador en el servidor sobre el motor de referencia: historia inmutable, traza de transiciones y estimador de Knuth | **Propuesta** (F5) |
| 059 | Tests e invariantes editables y ejecutables desde el Studio; plantillas compartidas con `gamehub new --template` | **Propuesta** (F5) |

---

### ADR-001 — IR canónica como fuente de verdad
- **Contexto:** se quiere diseñar con texto *y* con diagramas, ejecutar en Python, C++ y navegador,
  y analizar. Con varias "fuentes" habría divergencias.
- **Decisión:** todo produce o consume la GameIR (JSON canónico, versionado, con hash).
- **Alternativas:** el texto como fuente (el diagrama sería de solo lectura); el código Python como
  fuente (no portable).
- **Consecuencias:** hay que mantener un esquema estable y migraciones; a cambio, cualquier
  herramienta nueva solo necesita leer la IR.

### ADR-002 — Expresiones puras, tipadas y totales
- **Contexto:** `structure.py` usaba funciones Python arbitrarias.
- **Decisión:** lenguaje propio sin efectos en expresiones, sin recursión general, bucles solo
  sobre colecciones finitas. Vía de escape: plugins nativos puros con firma declarada.
- **Consecuencias:** portabilidad, seguridad, análisis estático (tipos, fugas, terminación) y
  compilación a C++. Algunos juegos exóticos necesitarán plugins.

### ADR-003 — Azar explícito y determinismo
- **Decisión:** solo los nodos `chance` (y la preparación inicial) introducen aleatoriedad, con
  distribuciones explícitas; la ejecución usa un RNG con semilla.
- **Consecuencias:** replays exactos, tests reproducibles, azar verificable online y algoritmos
  que distinguen nodos de azar enumerables de los muestreables.

### ADR-004 — Estados inmutables
- **Decisión:** `apply(s, a)` devuelve un estado nuevo (con compartición estructural). Nada de
  singletons. El motor no hace E/S.
- **Consecuencias:** búsqueda en árbol, simulación paralela, viaje en el tiempo y servidor
  multi-sala sin trucos. El motor C++ podrá usar *undo* incremental internamente.

### ADR-005 — Visibilidad declarativa
- **Decisión:** se declara quién ve cada ubicación del estado (y cada parámetro de acción y
  evento); las vistas se derivan; el servidor solo envía vistas redactadas; las componentes
  ocultas no exponen identidad (detalle en ADR-019).
- **Consecuencias:** imposible "olvidarse" de ocultar algo en la UI; análisis de fugas posible.

### ADR-006 — Statechart jerárquico
- **Decisión:** tipos de nodo cerrados: `decision`, `simultaneous`, `window`, `chance`, `auto`,
  `phase`, `call`, `terminal`.
- **Alternativas:** diagrama plano (no escala a rondas/bazas); máquinas de estados de BGA/boardgame.io
  (poco formales).
- **Consecuencias:** diagramas legibles y plegables; correspondencia directa con la forma extensiva.

### ADR-007 — Python primero, C++ después
- **Contexto:** prioridad = diseñar y jugar cuanto antes; el rendimiento importa para análisis e IA.
- **Decisión:** motor de referencia en Python (claridad, rapidez de desarrollo); core C++ en la
  Fase 8, verificado contra el de referencia con trazas doradas.
- **Consecuencias:** el MVP llega antes; la IR debe evitar cualquier semántica "solo Python".

### ADR-008 — Git como backend
- **Decisión:** cada juego es un repo git; el hub usa git (Forgejo o similar) y añade diffs
  semánticos, partidas, análisis y arena.
- **Consecuencias:** ramas/forks/merges sin reinventar nada; integración con GitHub/GitLab gratis.

### ADR-009 — WebSocket + JSON + JSON Schema
- **Decisión:** transporte WebSocket con JSON en v1; contratos en JSON Schema con tipos generados.
- **Consecuencias:** cualquier tecnología puede ser cliente; MessagePack/WebRTC quedan como mejoras.

### ADR-010 — Interoperabilidad primero
- **Decisión:** exportar a OpenSpiel y Gambit desde la Fase 7 para disponer de sus algoritmos;
  implementar en C++ propio lo que más se use.

### ADR-011 / 012 / 015 — Organización
- Monorepo; web en TypeScript + React; documentación en español e identificadores en inglés.
  Pendiente de tu confirmación.

### ADR-016 — Licencias (aceptada, 2026-10-09)
- **Decisión:** Apache-2.0 para todo por defecto (motor, Nomos, especificaciones, SDKs,
  herramientas, documentación); AGPL-3.0-or-later para el servidor del hub (evita que alguien
  monte un hub cerrado con este código); CC-BY-4.0 para el contenido de los juegos oficiales.
  Los juegos de terceros llevan la licencia que elija su autor.
- **Consecuencias:** `LICENSE` (texto canónico de Apache-2.0), `LICENSING.md` con el reparto por
  directorios y cabeceras SPDX en el código.

### ADR-017 — Nomos (aceptada, 2026-10-09)
- El lenguaje de descripción de juegos se llama **Nomos** (νόμος, "ley, regla"; guiño al juego
  *Nomic*). La extensión de archivo sigue siendo `.game` (ADR-014).

### ADR-018 — Sintaxis (aceptada, 2026-10-09)
- Bloques con llaves y palabras clave en inglés; textos visibles para jugadores traducibles.
  Por defecto (a falta de objeción): condicional al estilo Python `x if c else y` y pagos exactos
  (racionales) en la IR.

### ADR-019 — Modelo de visibilidad de la IR v0.1
- **Contexto:** el borrador proponía *handles opacos* re-anonimizados al barajar. Analizándolo, un
  handle estable filtra información: si paso un Q♠ a un rival y luego él juega una carta boca
  abajo desde su mano, el handle me diría si es "mi" Q♠ (en la mesa real no lo sabría).
- **Decisión:**
  1. La visibilidad es un **predicado** con `viewer`, `owner` e `item_face_up` ligados (con atajos
     `all`, `none`, `owner`); se evalúa sobre el estado actual.
  2. Dos tipos de zona: **`zone`** (ordenada: mazos, pilas, filas de Memory; las posiciones son
     públicas) y **`bag`** (multiconjunto: manos; el orden no forma parte del estado).
  3. Quien no ve el contenido de una zona ve solo su **tamaño** (si `size_visibility` lo permite) y,
     en zonas ordenadas, **huecos por posición**. En bolsas ocultas, solo el tamaño. Las
     componentes ocultas **no tienen identidad** visible.
  4. `reveal` es un **evento** (muestra valores a ciertos asientos) y no cambia la visibilidad
     persistente; las cartas que quedan boca arriba usan `flip` + `item_face_up`.
  5. La visibilidad de un parámetro de acción se aplica a los **demás** asientos: el actor
     siempre ve su propia acción.
- **Consecuencias:** sin fugas por identificadores ni por orden; el rastreo legítimo (por
  posición pública o por memoria de lo revelado) sigue siendo posible.

### ADR-020 — Catálogo de operadores como fuente única
- **Decisión:** `spec/ir/v0/ops.json` define cada expresión, sentencia y selector (aridad, tipo de
  argumentos, si es aleatoria, documentación). `expr.schema.json` y `stmt.schema.json` se generan
  (`gamehub ir schemas --write`) y un test/CI comprueba que están al día.
- **Consecuencias:** cada motor futuro (Python, C++, WASM) podrá verificar automáticamente que
  implementa todo el catálogo; la documentación de operadores se podrá generar del mismo archivo.

### ADR-021 — IR núcleo primero
- **Decisión:** la Fase 0 fija la **IR resuelta** (la que ejecutan los motores). La IR de autor
  (con azúcar: bucles en fases, `deal`, tablas de pagos, `call` de sub-flows) depende de la
  sintaxis concreta y se especificará junto al compilador en la Fase 2.
- **Consecuencias:** el motor de referencia (F1) puede empezar ya contra un contrato estable.

### ADR-022 — PCG32 como RNG normativo
- **Contexto:** "misma semilla ⇒ misma partida" debe valer entre motores (Python, C++, WASM). El
  `random` de Python (Mersenne Twister con su propio sembrado) no es reproducible fuera de Python.
- **Decisión:** PCG32 (XSH-RR 64/32) exactamente como `pcg32_srandom_r`, `pcg32_random_r` y
  `pcg32_boundedrand_r` de la implementación de referencia en C; flujos por propósito; Fisher–Yates
  desde el final; muestreo ponderado exacto con denominador común. Ver [motor §4](motor.md).
- **Consecuencias:** trazas de conformidad comparables bit a bit; los replays guardan además los
  sorteos, así que no dependen del RNG.

### ADR-023 — Sin capa de modelos pydantic
- **Decisión:** la IR se valida con el JSON Schema y el comprobador de buena formación; el motor la
  compila directamente a funciones Python (closures).
- **Alternativas:** modelos pydantic (duplicarían el esquema y añadirían una dependencia).
- **Consecuencias:** una sola definición del formato (el esquema); los tipos estáticos de Python
  llegan donde aportan (motor), no en el formato.

### ADR-024 — Orden de `$exit`
- **Decisión:** al salir de una fase con `$exit`, primero se ejecuta su `on_exit` y después se
  evalúan sus transiciones.
- **Motivo:** permite "al terminar la ronda, puntuar; si alguien llega a 500, fin; si no, otra
  ronda" sin duplicar cálculos en las guardas.

### ADR-025 — Hash insensible a valores por defecto
- **Decisión:** antes de calcular el hash de reglas se eliminan las listas vacías y las
  visibilidades `all` explícitas (además de `meta`, `doc` y mensajes de restricciones).
- **Consecuencias:** dos IR con la misma semántica escritas de forma distinta (a mano, con el
  builder, desde Nomos o desde Studio) tienen el mismo hash.

### ADR-027 — Parser escrito a mano
- **Contexto:** el roadmap preveía Lark. El lenguaje necesita mensajes de error claros con
  sugerencias, recuperación para informar de todos los errores de un archivo y conservar los
  comentarios para el formateador.
- **Decisión:** analizador léxico y sintáctico propios (descenso recursivo con precedencias); los
  comentarios son *trivia* pegada a los tokens; cada token sabe su profundidad de corchetes y la
  recuperación salta al siguiente elemento de su mismo bloque.
- **Alternativas:** Lark (gramática declarativa, pero errores genéricos y recuperación pobre).
- **Consecuencias:** ~1 500 líneas sin dependencias; errores de calidad (al estilo rustc); la
  gramática vive en el código y en la [referencia](lenguaje-game.md), no en un archivo aparte.

### ADR-028 — Sin ocultar nombres globales
- **Decisión:** un parámetro, un `let` o una variable de comprensión no puede llamarse como una
  variable de estado, una opción, una función, un tipo, un valor de enumerado o un nombre de
  contexto (`seats`, `actor`…) del juego (E204). Excepción: dentro de una función de módulo, el
  estado y las opciones del juego no existen, así que sus nombres quedan libres.
- **Motivo:** en reglas de juego, confundir `turn` (estado) con un `turn` local es un error
  difícil de ver; los módulos, en cambio, se escriben sin conocer los juegos que los usarán.

### ADR-029 — Azúcar guiado por los tipos
- **Decisión:** el comprobador elabora y traduce cada expresión en una sola pasada (devuelve IR y
  tipo). Las formas cómodas se traducen según el tipo: `+`/`-`/`in` en listas (`concat`,
  `difference`, `contains`), `+=`, el selector de `move` (`value` o `values`), `deal`, `match` a
  `case`, valores iniciales por defecto. Las cadenas `a + b + c` se aplanan.
- **Consecuencias:** la IR solo tiene operadores del catálogo y el descompilador puede volver al
  texto exactamente (probado en todos los juegos).

### ADR-030 — Tests e invariantes fuera de la IR
- **Decisión:** `test` e `invariant` se compilan aparte (no cambian el hash de reglas) y los
  ejecuta `gamehub test`: el azar pendiente se resuelve con una semilla antes de cada paso;
  `chance where c` elige con la probabilidad condicionada; tras un `set` dejan de comprobarse los
  invariantes; los invariantes se comprueban también en partidas aleatorias.
- **Consecuencias:** los juegos traen sus propias pruebas sin ensuciar las reglas; cada fallo se
  explica con los valores en juego.

### ADR-031 — Módulos
- **Decisión:** las declaraciones de primer nivel (propias o importadas) son externas: solo
  llegan a la IR si el juego las usa. `import` busca en la biblioteca estándar, después en las
  dependencias del paquete y después junto al archivo; importar un nombre trae lo que necesita.
  La IR no guarda módulos: queda autocontenida.
- **Consecuencias:** las variantes y las bibliotecas no engordan la IR; un motor no necesita saber
  nada de módulos.

### ADR-032 — Mods y combinadores
- **Decisión:** `extends` mezcla modelos (AST) antes de comprobar: la variante se compila como un
  juego completo y la base no cambia. `repeat` y `best_of` transforman la IR de la base (fase por
  ronda, terminales que apuntan el resultado). Para extender un combinador se descompila su IR.
- **Consecuencias:** las variantes tienen errores situados en su texto; los combinadores valen
  para cualquier juego, también uno escrito en IR.

### ADR-033 — Paquetes
- **Decisión:** cada juego es un directorio con `game.toml` (nombre, versión, archivo principal,
  dependencias por `path` o `git` + `rev`) y `game.lock` (commit exacto de cada dependencia git),
  con una caché local. `gamehub new`, `fetch`, `clone` y `fork` (que anota `forked_from`).
- **Alternativas:** un registro central (llega con el hub, F10); versiones semánticas resueltas
  (por ahora, revisiones de git).
- **Consecuencias:** coherente con git como backend (ADR-008); compilaciones reproducibles.

### ADR-034 — Análisis estáticos sobre la IR
- **Decisión:** los avisos de `gamehub check` (alcanzabilidad, exhaustividad, terminación, bucles
  sin progreso, fugas de información, declaraciones sin usar) y la clasificación se calculan sobre
  la IR, recorrida de forma genérica con el catálogo de operadores; el compilador los sitúa en el
  texto con un mapa de fuentes.
- **Consecuencias:** valen igual para Nomos, IR escrita a mano o el futuro editor visual. El
  análisis de fugas v1 es conservador (puede avisar de más), entiende el tamaño visible, la parte
  propia de una variable `@visible(owner)` y `reveal … to all`.

### ADR-035 — Formato canónico
- **Decisión:** `gamehub fmt` usa un álgebra de documentos al estilo Wadler/Prettier (100
  columnas, sangría 2): las cadenas aritméticas rellenan líneas, las de `and`/`or` van una por
  línea, un valor que empieza por un corchete se abre junto al `=` si no cabe en la línea
  siguiente. El parser admite que un valor empiece en la línea siguiente tras `=`, `requires`,
  `when` y `clave:`, de modo que todo lo que escribe el formateador se vuelve a leer igual
  (probado formateando todos los juegos a anchos de 24 a 100 columnas).

### ADR-036 — Servidor sobre Starlette + uvicorn
- **Contexto:** el roadmap y la arquitectura proponían FastAPI. Su valor añadido es validar con
  pydantic y documentar con OpenAPI, pero los contratos del proyecto ya son JSON Schema (ADR-009,
  ADR-023) y casi todo el protocolo va por WebSocket, que OpenAPI no describe.
- **Decisión:** Starlette (la base de FastAPI) sobre uvicorn, con `websockets` como implementación
  y como cliente. Los mensajes se validan con el esquema `spec/protocol/v1` y los tipos de Python
  (`TypedDict`) se generan de él.
- **Alternativas:** FastAPI (duplicaría los contratos en modelos pydantic), aiohttp (servidor y
  cliente en uno, menos extendido).
- **Consecuencias:** tres dependencias ligeras; una sola definición de cada mensaje para Python,
  TypeScript (F4) y la documentación. El hub (F10) puede usar FastAPI si lo necesita.

### ADR-037 — Núcleo de salas puro
- **Decisión:** `Room`/`Match` no abren conexiones ni leen la hora: cada operación recibe `now`,
  deja los mensajes en un buzón de salida (con su instante de entrega, para el retardo de los
  espectadores) e indica cuándo hay que volver a llamarla (`next_wakeup`: bots, plazos). La capa
  de transporte solo valida, entrega y programa temporizadores; todo corre en el bucle de eventos,
  sin cerrojos.
- **Consecuencias:** toda la semántica (turnos, relojes, bots, espectadores, abandonos,
  reconexión) se prueba sin red y con un reloj simulado; el mismo núcleo servirá al simulador
  del Studio y a los torneos.

### ADR-038 — Actualizaciones y turnos
- **Decisión:** cada entrada (acción, bot o plazo vencido) produce **una** actualización con la
  acción y el azar que la sigue; `seq` numera las actualizaciones sin huecos. Un `act` se rechaza
  por `stale_seq` solo si su `seq` es anterior al comienzo del **turno vigente** del asiento: el
  turno sigue mientras el asiento pueda actuar, no haya actuado y no se llegue a ningún nodo.
- **Alternativas:** rechazar cualquier `act` con un `seq` que no sea el último (rechazos
  espurios en nodos simultáneos y ventanas, donde los envíos de otros no cambian tu decisión).
- **Consecuencias:** la protección contra jugadas decididas con un estado viejo no molesta en
  los nodos simultáneos; los huecos en `seq` delatan mensajes perdidos.

### ADR-039 — Observador público
- **Decisión:** el motor ofrece la vista y los eventos de un espectador (`PUBLIC`), que no ocupa
  ningún asiento: las políticas se evalúan con un `viewer` que no coincide con ningún `owner`, y un
  predicado que no se puede evaluar sin asiento cuenta como falso. De los eventos ve lo público y
  lo que se revela a todos los asientos.
- **Alternativas:** la intersección de lo que ven todos los asientos (no es lo mismo: lo que cada
  uno ve por separado no es público).
- **Consecuencias:** espectadores sin trampas; `@visible(viewer != owner)` (Hanabi) se ve desde
  fuera, como en la mesa. No cambia las trazas de conformidad.

### ADR-040 — Azar verificable
- **Decisión:** esquema `gamehub-fair/1`: compromiso SHA-256 de la semilla del servidor publicado
  en el lobby; semillas opcionales de los jugadores al declararse listos; semilla de la partida =
  SHA-256 del JSON canónico de todo, recortada a 53 bits (exacta en JSON y JavaScript); revelación
  al terminar; el replay lleva todo para verificarlo. El azar del servidor que no es de las reglas
  (jugada al vencer un plazo, bots del servidor) sale de otros flujos de PCG32 de la misma semilla.
- **Consecuencias:** nadie (ni el servidor ni un jugador) puede elegir el azar; cualquiera
  comprueba una partida con `gamehub replay`.

### ADR-041 — Abandonos
- **Decisión:** quien abandona (rendirse, salir en partida o plazo vencido con `forfeit`) queda el
  último y un bot juega por su asiento hasta el final; si solo queda un asiento sin abandonar, la
  partida termina sin pagos (`reason: forfeit`).
- **Alternativas:** terminar siempre la partida (injusto con los demás en juegos de 3 o más);
  pausarla (bloquea a todos).
- **Consecuencias:** las partidas de varios jugadores sobreviven a que alguien se vaya; el puesto
  final refleja el abandono.

### ADR-042 — Jugar en la LAN
- **Decisión:** `gamehub host` levanta el servidor en el puerto 7420 de todas las interfaces y
  comparte la sala de tres formas: el código (6 caracteres), el enlace
  `http://IP:7420/r/CÓDIGO` (página de la sala) y su QR en la terminal; además la anuncia por mDNS
  (`_gamehub._tcp`, con `zeroconf`) para que `gamehub join CÓDIGO` la encuentre sin escribir IPs.
  mDNS es opcional: si la red no lo permite, el enlace basta. El cliente guarda el token de cada
  sala para volver a ella tras cerrar la terminal.
- **Alternativas:** solo IP y puerto (incómodo); un servidor central (no hace falta en casa).
- **Consecuencias:** dos dependencias pequeñas (`zeroconf`, `segno` para el QR). Las pruebas de
  mDNS dependen de la red: se ejecutan con `GAMEHUB_LAN_TESTS=1`.

### ADR-043 — Bots en red con la interfaz de siempre
- **Decisión:** un bot remoto implementa el mismo `Agent` que en proceso (`act(observation,
  legal)`), con una observación de los mismos nombres (`seat`, `view`, `events`, más `clock` y
  `game`) y las acciones ya decodificadas con los tipos del juego (`Action`), perezosamente. El
  SDK resuelve la red: reconexión, acciones progresivas, `act` en un hilo para no bloquear.
- **Consecuencias:** el mismo agente juega en la arena, en `play_match` y contra personas por la
  red sin cambiar una línea; `gamehub bot run` carga un archivo `.py` con `make_agent`, una clase
  `Agent` o una función `act`.

### ADR-044 — Cliente web: pila y workspace
- **Contexto:** la Fase 4 crea la parte de JavaScript del monorepo: paquetes de la web y UIs
  propias que viven dentro de cada paquete de juego (`games/<juego>/ui`, como prevé la
  [arquitectura](arquitectura.md)).
- **Decisión:** un workspace de **pnpm en la raíz del repositorio** con `web/packages/*`,
  `web/apps/*` y `games/*/ui`, Node 22, **TypeScript 7** estricto (el compilador nativo),
  **React 19**, **Vite 8**, **Biome** para lint y formato (el equivalente de ruff) y **Vitest**.
  Versiones exactas en un catálogo de `pnpm-workspace.yaml`; los paquetes internos exportan su
  código TypeScript, sin paso de compilación.
- **Alternativas:** el workspace dentro de `web/` (pnpm no lo encuentra al trabajar dentro de
  `games/<juego>/ui`, que no cuelga de `web/`); ESLint + Prettier (dos herramientas y más
  configuración); TypeScript 6 (más lento, mismo resultado).
- **Consecuencias:** `pnpm install`, `test`, `lint`, `typecheck` y `build` desde la raíz;
  `pnpm dev` funciona dentro de cada UI. La raíz gana `package.json`, `pnpm-workspace.yaml`,
  `pnpm-lock.yaml`, `biome.json` y `.nvmrc`.

### ADR-045 — Tipos del protocolo generados una sola vez
- **Decisión:** `gamehub protocol types` genera desde `spec/protocol/v1` tanto los `TypedDict`
  de Python como las `interface` de TypeScript (`@gamehub/protocol`), con el formato de cada
  ecosistema; `--check` comprueba los dos en el CI. Para no chocar con globales de JavaScript,
  `Number`, `Event` y `Error` pasan a llamarse `ExactNumber`, `GameEvent` y `ErrorInfo` en el
  esquema (los mensajes en la red no cambian).
- **Alternativas:** `json-schema-to-typescript` (otra herramienta, otro estilo de salida).
- **Consecuencias:** un único origen de verdad para los mensajes en todos los clientes.

### ADR-046 — El servidor sirve la app web
- **Decisión:** `gamehub serve` y `gamehub host` sirven la app compilada (la del repositorio, la
  que viaja en la rueda o `GAMEHUB_WEB_DIR`); las rutas de la app devuelven su `index.html` y
  `/r/CÓDIGO` sigue dando la sala en JSON a quien la pide así. Endpoints nuevos: QR de la sala en
  SVG y replays estado a estado (`/frames?seat=`).
- **Alternativas:** la app en otro servidor (CORS, dos direcciones que recordar).
- **Consecuencias:** mismo origen, sin CORS; el enlace y el QR de una sala abren la app, también
  en el móvil; nada que instalar para jugar en el navegador.

### ADR-047 — Pistas de presentación `ui { … }`
- **Decisión:** una sección de Nomos con entradas `destino: pista, pista…` (variables, opciones,
  tipos, acciones y sus parámetros, nodos, asientos) y un **catálogo cerrado** de pistas
  (cómo dibujar, dónde, nombres traducidos, símbolos, colores, cartas, cómo elegir un argumento,
  colores y nombres de los asientos), comprobadas por el compilador (E701–E704). Llegan a la IR
  en una clave `ui` opcional que **no cuenta para el hash de reglas**; en las variantes, cada
  pista sustituye a la del mismo hueco. Sin cambiar `ir_version`, porque es opcional.
- **Alternativas:** pistas libres en `meta` (sin comprobar: los errores se verían en la
  pantalla); una hoja de estilo aparte (otro archivo que mantener sincronizado con las reglas).
- **Consecuencias:** cambiar la presentación no cambia las reglas ni sus replays; las pistas
  mal escritas fallan al compilar, con sugerencias.

### ADR-048 — UI genérica guiada por tipos y dominios
- **Decisión:** el aspecto de cada variable sale de su tipo y de sus pistas, y cómo se elige
  cada argumento, de la forma de su **dominio** en la IR (`cells(G)` → pulsar casillas;
  `subsets(items(Z), a, b)` → marcar elementos de Z; `items(Z)` → elegir uno) o de una pista.
  Un **constructor de acciones** elige los argumentos en orden con los valores que dan las
  acciones legales (enumeradas o con `query_actions`), calculados una vez por actualización; para
  marcar varios con acciones progresivas valida el tamaño en vez de pedir todos los
  subconjuntos. La web enumera hasta 500 acciones legales por defecto.
- **Consecuencias:** los 15 juegos del catálogo se juegan sin escribir interfaz (lo comprueba un
  test que juega cada uno solo con la UI); un juego nuevo es jugable en cuanto compila.

### ADR-049 — Partidas en un mismo dispositivo
- **Decisión:** el modo local crea una sala en el servidor que sirve la app y abre una conexión
  por asiento humano en la misma pestaña; enseña la UI de quien tiene el turno y, si el juego
  esconde información, tapa la pantalla entre turnos.
- **Alternativas:** un motor en el navegador (no lo hay hasta el core en WASM, F8; Pyodide pesa
  decenas de megas).
- **Consecuencias:** el mismo protocolo y las mismas reglas que en red; sin servidor no hay modo
  local hasta F8.

### ADR-050 — UIs propias
- **Decisión:** una UI propia es un paquete en `games/<juego>/ui` que exporta `defineGameUi`
  (un componente que recibe la vista, las acciones legales tipadas y `act`); la app la registra
  sola (`import.meta.glob`) y deja cambiar a la genérica. `gamehub ui new` la crea desde una
  plantilla que ya funciona (tipos del juego con `gamehub sdk ts`, tablero inicial, test y
  servidor de desarrollo con la app solo para ese juego).
- **Alternativas:** UIs dentro de `web/` (separadas de las reglas a las que pertenecen).
- **Consecuencias:** cada juego lleva sus reglas y su interfaz juntas; si cambian las reglas,
  TypeScript señala lo que hay que tocar (y un test, si los tipos no se regeneraron).

### ADR-051 — Sin librerías de estado ni de idiomas
- **Decisión:** el estado de cada conexión lo lleva el SDK con un reductor puro e inmutable, y
  React lo lee con `useSyncExternalStore`; los textos, con catálogos es/en propios que
  TypeScript comprueba (las mismas claves en los dos idiomas).
- **Alternativas:** Redux o Zustand; i18next.
- **Consecuencias:** el SDK sirve igual fuera de React (bots en Node, otros frameworks); menos
  dependencias que mantener.

### ADR-052 — Studio: el texto es lo que se guarda; el diagrama edita el árbol
- **Contexto:** el Studio edita el mismo juego como diagrama, con formularios y como texto. El
  `.game` lleva comentarios, formato y orden que importan a quien lo escribe, y es lo que se
  versiona con git (ADR-008).
- **Decisión:** el archivo `.game` es lo único que se guarda; el diagrama y los formularios son
  proyecciones de su árbol sintáctico (la IR de autor, ADR-001/021). Cada gesto es una lista de
  **operaciones** (`addNode`, `addTransition`, `updateAction`…) que el servidor aplica a una
  copia del árbol; el texto se reescribe **solo donde cambió** (lo igual conserva su texto, con
  formato y comentarios; lo nuevo, con el formateador) y el resultado se comprueba volviendo a
  analizarlo (mismo árbol y mismos comentarios); si la reescritura parcial no sabe, se formatea el
  archivo entero. Al editor llegan los cambios mínimos, que se deshacen como cualquier edición.
- **Alternativas:** generar el texto entero desde la IR (perdería comentarios y formato); un
  modelo propio del diagrama sincronizado con el texto (dos fuentes que divergen); editar
  directamente el texto desde el navegador con plantillas (frágil ante cualquier formato).
- **Consecuencias:** los diffs de git de un cambio en el diagrama son de una o pocas líneas;
  tests de propiedad (ediciones al azar en todos los juegos del catálogo conservan los
  comentarios y dejan un texto válido) vigilan la garantía; las operaciones viven en Python
  (`gamehub.studio.edits`) y cualquier cliente puede usarlas.

### ADR-053 — Servidor de lenguaje con pygls, también para el Studio
- **Decisión:** el servidor de lenguaje de Nomos se escribe con **pygls** sobre el compilador de
  referencia: diagnósticos, autocompletado (con los tokens hasta el cursor, funciona con el texto
  a medias), hover, definición, referencias, resaltado, renombrar, formato, esquema, plegado,
  ayuda de firmas y arreglos rápidos. Dos transportes: entrada estándar (`gamehub lsp`, para
  editores) y el WebSocket del Studio, donde los métodos propios (`gamehub/edit`,
  `gamehub/analysis`, `gamehub/sim.*`, `gamehub/tests`…) se atienden antes de pygls. Cada
  documento se analiza en un hilo 150 ms después del último cambio (al momento si el cambio viene
  de una edición del Studio).
- **Alternativas:** un servidor de lenguaje en TypeScript (duplicaría el compilador); un
  protocolo propio para el Studio (otro cliente que mantener; el LSP ya resuelve la
  sincronización de documentos y las versiones).
- **Consecuencias:** un solo compilador para todo; cualquier editor con LSP sirve
  (`gamehub lsp`); el Studio habla un único protocolo por un único WebSocket.

### ADR-054 — CodeMirror 6 en vez de Monaco
- **Contexto:** ADR-012 preveía Monaco. El Studio necesita un editor principal y decenas de
  editores pequeños en los formularios (cada condición, efecto o tipo), con resaltado,
  autocompletado y errores en el sitio.
- **Decisión:** **CodeMirror 6** con `@codemirror/lsp-client` (el cliente LSP oficial) para el
  editor y para los campos; Nomos como lenguaje de CodeMirror en `@gamehub/nomos`.
- **Alternativas:** Monaco (unos 5 MB y trabajadores web; pensado para un editor por página, no
  para decenas de campos; el puente LSP es de terceros).
- **Consecuencias:** una app más ligera (el Studio pesa ~1 MB sin ELK); los campos y el editor
  comparten tema y lenguaje; las versiones van en el catálogo de pnpm, con una sola copia de
  `@codemirror/state`, `@codemirror/view` y `@lezer/highlight` (con dos, el editor se rompe).

### ADR-055 — Diagrama con React Flow + ELK; disposición aparte
- **Decisión:** el lienzo es **React Flow** (`@xyflow/react`): cajas por tipo de nodo, fases como
  contenedores plegables, flechas con orden. La disposición automática la calcula **ELK**
  (`elkjs`, algoritmo por capas, los ciclos se rompen por el orden del texto para que el flujo
  empiece arriba), cargado aparte la primera vez; lo que mueve el usuario se guarda en
  `<juego>.layout.json` junto al juego, con los nodos por nombre.
- **Alternativas:** dagre (sin subgrafos, peor con fases); posiciones dentro del `.game` (mezcla
  presentación con reglas y ensucia los diffs).
- **Consecuencias:** el `.game` y el hash de reglas no cambian al mover cajas; elkjs es
  **EPL-2.0** (se distribuye sin modificar dentro de la app compilada; ver `LICENSING.md`).

### ADR-056 — Índice de símbolos del comprobador
- **Decisión:** el árbol guarda la posición de cada nombre (`name_spans`) y el comprobador, si se
  le pasa un índice, anota cada declaración, cada uso resuelto (estado, opción, local, valor de
  enumerado, campo, nodo, acción y sus parámetros, también en `ui` y en los tests) y el tipo de
  cada expresión. Hover, definición, referencias y **renombrar** salen de ahí; renombrar
  recompila y se rechaza si choca con otro nombre o el juego deja de compilar. Para el editor, el
  compilador se salta el JSON Schema (`schema=False`), que era el 90 % del tiempo.
- **Alternativas:** buscar por texto (falla con locales, campos y nombres repetidos en ámbitos
  distintos).
- **Consecuencias:** renombrar cada símbolo de cada juego del catálogo ida y vuelta deja el archivo
  igual (test); compilar un juego del catálogo para el editor tarda milisegundos.

### ADR-057 — Seguridad del Studio
- **Decisión:** `gamehub studio` escucha solo en 127.0.0.1 por defecto; exige un **token**
  aleatorio (en el enlace; la app lo pasa a una cookie de este origen o a la cabecera
  `x-gamehub-token`); comprueba la cabecera **Host** (contra el *DNS rebinding*) y el **Origin**
  de los WebSocket; solo abre y guarda archivos `.game` dentro del directorio de trabajo, con
  detección de conflictos al guardar. Con `--host` fuera de la máquina, avisa.
- **Alternativas:** sin token en local (cualquier página abierta en el navegador podría escribir
  archivos a través de localhost).
- **Consecuencias:** abrir el Studio es abrir el enlace que imprime; `GAMEHUB_STUDIO_TOKEN` lo fija
  (para el servidor de desarrollo de Vite y los tests).

### ADR-058 — Simulador en el servidor
- **Decisión:** el simulador usa el motor de referencia en el servidor del Studio. La historia
  completa se conserva (estados inmutables, ADR-004): viaje en el tiempo, ramas que recortan la
  historia, recargar las reglas repitiéndola. Cada transición del motor sabe quién es
  (`TransitionDef.key`) y se puede **trazar** (`engine.state.TRACE`), lo que da las flechas del
  último paso y la **cobertura** de las partidas masivas, sin cambiar la semántica (las trazas de
  conformidad no cambian). El tamaño del árbol se estima con el **estimador de Knuth** (paseos al
  azar ponderados por 1/P); el recuento exacto, con límites de estados y de tiempo.
- **Alternativas:** simular en el navegador (no hay motor hasta el WASM de F8).
- **Consecuencias:** las reglas que se simulan son exactamente las que compila el servidor; sin
  servidor, no hay simulador hasta F8.

### ADR-059 — Tests e invariantes en el Studio; plantillas compartidas
- **Decisión:** los tests y los invariantes del juego se editan desde el inspector (operaciones
  `addTest`, `updateTest`, `deleteTest` y las de invariantes) y se ejecutan con
  `gamehub/tests` (tests más invariantes en partidas al azar). Las plantillas de juego (vacío,
  carrera, tablero, cartas, dados, matriz 2×2) viven en el paquete de Python y las usan
  `gamehub new --template` y el Studio; todas compilan sin avisos y pasan sus tests.
- **Contexto:** sin poder tocar los tests desde el diagrama, la plantilla vacía dejaba de compilar
  en cuanto se cambiaba su acción (su test la nombra) y no se podía diseñar un juego solo con el
  diagrama.
- **Consecuencias:** el tres en raya se crea desde cero solo con el diagrama y los formularios,
  con sus tests (test de aceptación).
