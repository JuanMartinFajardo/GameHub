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
| 012 | Web en TypeScript + React (+ React Flow, Monaco) | Aceptada (2026-10-09, sin objeciones) |
| 013 | Software en Python 3 y C++ (C++ para cálculo pesado) | **Aceptada** (decisión del usuario) |
| 014 | Extensión de archivo `.game` | **Aceptada** (decisión del usuario) |
| 015 | Documentación en español; código e identificadores en inglés | Aceptada (2026-10-09, sin objeciones) |
| 016 | Licencias: Apache-2.0 / AGPL-3.0 (hub) / CC-BY-4.0 (juegos) | **Aceptada** (2026-10-09) |
| 017 | El lenguaje se llama **Nomos** (archivos `.game`) | **Aceptada** (2026-10-09) |
| 018 | Sintaxis con llaves y palabras clave en inglés | **Aceptada** (2026-10-09) |
| 019 | IR v0.1: visibilidad por predicados; zonas ordenadas vs. bolsas; sin identidades ocultas | Aceptada (2026-10-09, sin objeciones) |
| 020 | Catálogo de operadores (`ops.json`) como fuente única; esquemas generados | Aceptada (2026-10-09, sin objeciones) |
| 021 | La Fase 0 especifica solo la IR núcleo (resuelta); la IR de autor llega con el compilador (F2) | Aceptada (2026-10-09, sin objeciones) |

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
