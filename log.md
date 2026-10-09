# Log de trabajo

Registro cronológico de lo que se hace en el proyecto. La entrada más reciente va arriba.
Formato: fecha · qué se hizo · decisiones · pendientes / siguientes pasos.

---

## 2026-10-09 — Sesión 3: Fase 1, motor de referencia en Python

**Respuestas recibidas**
- Commits: uno por tarea. → Fase 0 en `main` (3 commits); Fase 1 en la rama `f1/motor-referencia`
  (13 commits), pendiente de fusionar con el visto bueno del usuario (ADR-026).
- Arrancar la Fase 1: sí. Las ADR propuestas se consideran aceptadas (sin objeciones).

**Qué se hizo**
- `gamehub.ir.hashing`: hash de reglas (JSON canónico + SHA-256), insensible a `meta`, `doc` y
  valores por defecto (ADR-025). Validación: `pass` reservado en ventanas, sin transiciones por
  acción en nodos simultáneos, fases de las que se sale con `$exit` con transiciones.
- **Motor de referencia** (`gamehub.engine`):
  - valores inmutables con orden canónico; tipos; JSON;
  - **PCG32** idéntico a la implementación de referencia en C (vector de prueba verificado),
    sorteos reproducibles y **enumeración exacta** de resultados de azar (ADR-022);
  - los 87 operadores y las 14 sentencias del catálogo, compilados a funciones;
  - semántica del flow: decisiones, simultáneos, ventanas (priority/collect/race), azar, fases con
    `on_enter`/`on_exit`/`$exit` (ADR-024), avance hasta quiescencia sin recursión;
  - visibilidad: vistas redactadas, eventos resueltos por asiento, estados de información con
    recuerdo perfecto (verificado: en Kuhn el asiento 1 no distingue KQ de JQ);
  - acciones legales, forma canónica y construcción progresiva (`options`);
  - instantánea y huella del estado; replays `.ghr.json` verificados paso a paso.
- Drivers: `play_match`, `RandomAgent`, `fuzz`; **trazas doradas** en `spec/conformance` (6 juegos).
- **API builder** (`gamehub.build`): tres juegos reconstruidos con ella dan el mismo hash de reglas
  que sus JSON escritos a mano.
- **CLI**: `gamehub play` (hot-seat y bots, pantalla de cambio de jugador), `fuzz`, `replay`,
  `conformance`.
- Juegos nuevos: **piedra-papel-tijera** y **Nim** (con variante misère).
- Docs: `docs/wiki/motor.md` (semántica operacional exacta), ADR-022 a 026, roadmap, arquitectura,
  glosario, README.
- 132 tests; `ruff` y `pyright` limpios.
- Perfilado de Mentiroso: la mitad del tiempo era deduplicar subconjuntos ya distintos; corregido (×1,8) sin cambiar las trazas de conformidad.

**Aceptación de la Fase 1**

| Juego | Partidas aleatorias | Errores | Partidas/s | Comprobación |
|---|---:|---:|---:|---|
| Tres en raya | 100 000 | 0 | 1 579 | Pago medio de X +0,294 (teórico +0,297) |
| Dilema del prisionero | 100 000 | 0 | 11 972 | Pago medio 2,249 (exacto 9/4) |
| Piedra, papel o tijera | 100 000 | 0 | 11 790 | Pago medio −0,003 (exacto 0) |
| Nim (3, 5, 7) | 100 000 | 0 | 2 805 | — |
| Póker de Kuhn | 100 000 | 0 | 4 600 | Pago medio +0,133 (exacto 1/8) |
| Mentiroso (3 jugadores) | 1 000 | 0 | 0,4 (≈ 0,9 tras optimizar) | 391 pasos de media; gana un 31,6 / 32,2 / 36,2 % por asiento: el asiento 0 recibe 18 cartas y los demás 17 |

Además: valor exacto del juego aleatorio calculado sobre el árbol completo (Kuhn = 1/8, dilema = 9/4,
PPT = 0); replays idénticos bit a bit; vistas sin fugas; partida completa jugable en la terminal.

**Decisiones**: ADR-022 (PCG32), 023 (sin pydantic), 024 (orden de `$exit`), 025 (hash), 026 (ramas).

**Pendiente / siguientes pasos**
- Del usuario: fusionar `f1/motor-referencia` en `main`; variantes de Mentiroso (pregunta 9b).
- F2: compilador de Nomos (`.game` → IR) con tipos, formateador, stdlib v0 y paquetes.

**Progreso:** ≈ 13 % (F0 y F1 completas).

---

## 2026-10-09 — Sesión 2: respuestas del usuario y Fase 0 completada

**Respuestas recibidas**
- Mensaje cortado ("También quiero tener una…"): no lo recuerda → pregunta cerrada.
- Licencias propuestas: aceptadas (ADR-016).
- Mentiroso = *Bullshit*: cartas boca abajo con un *claim* ("3 cuatros"); si te acusan y era
  mentira, te llevas el montón; si era verdad, se lo lleva quien acusó.
- Nombre **Nomos** y palabras clave en inglés: aceptados (ADR-017, ADR-018).
- Inicializar git y arrancar la Fase 0: sí.

**Qué se hizo**
- `git init -b main` (sin commits: política de commits pendiente). `.gitignore`, `.editorconfig`,
  `LICENSE` (texto canónico de Apache-2.0, md5 verificado), `LICENSING.md`.
- **Especificación de la IR núcleo v0.1** en `spec/ir/v0/`:
  - `ops.json`: catálogo de 87 expresiones, 14 sentencias y 6 selectores (aridad, tipos de
    argumento, aleatoriedad, documentación). Fuente única de verdad (ADR-020).
  - `ir.schema.json`, `common.schema.json`, `type.schema.json` (a mano) y `expr.schema.json`,
    `stmt.schema.json` (generados desde el catálogo).
- **Juegos de validación** en `spec/ir/examples/`: tres en raya, dilema del prisionero (con
  restricciones T > R > P > S), póker de Kuhn y **Mentiroso** (adelantado desde la ola 2).
- **Paquete Python `gamehub`** (`python/`, gestionado con `uv`): validación por JSON Schema +
  comprobador de buena formación (referencias, contextos, azar confinado, sin recursión,
  salidas de nodos), CLI `gamehub ir check` y `gamehub ir schemas --check|--write`.
- 35 tests (20 casos de error deliberados); `ruff`, `pyright` (0 errores) y formato en verde.
- CI de GitHub Actions y hooks de `pre-commit` locales.
- Mejora del modelo de información (ADR-019): se descartan los *handles* opacos (filtraban qué
  carta jugaba un rival) en favor de zonas ordenadas con posiciones públicas y **bolsas** sin
  orden; las componentes ocultas no exponen identidad; `reveal` es un evento.
- Wiki actualizada: preguntas, decisiones (ADR-016 a 021), modelo formal, Nomos (Mentiroso
  completo), IR (validación), protocolo, catálogo, roadmap, glosario, arquitectura, estado.

**Decisiones**
- Aceptadas: ADR-016 (licencias), 017 (Nomos), 018 (sintaxis).
- Propuestas e implementadas: ADR-019 (visibilidad), 020 (catálogo), 021 (IR de autor en F2).

**Pendiente / siguientes pasos**
- Del usuario: política de commits, variantes de Mentiroso (pregunta 9b), visto bueno a las ADR.
- F1: intérprete de la IR en Python (expresiones, efectos, flow, azar con semilla, vistas
  redactadas, replays) hasta jugar las 4 IR en terminal.

**Progreso:** ≈ 4 % (F0: 9/9).

---

## 2026-10-09 — Sesión 1: brainstorming, diseño y roadmap

**Contexto de partida**
- El repo solo contenía `structure.py` (prototipo de mayo 2026: `GameState` singleton, `Node`,
  `Action`, `Flowchart`, permisos por variable). Sin git.

**Qué se hizo**
- Análisis de `structure.py`: intuiciones que se conservan, 6 errores que impiden ejecutarlo y
  7 problemas de diseño → [`docs/wiki/analisis-structure-py.md`](docs/wiki/analisis-structure-py.md).
- Brainstorming completo: 17 huecos de la idea original, 27 mejoras, ideas futuras y riesgos →
  [`ideas-y-mejoras.md`](docs/wiki/ideas-y-mejoras.md).
- Diseño (borradores v0.1):
  - [Visión](docs/wiki/vision.md): principios, no-objetivos, posicionamiento frente a OpenSpiel,
    Ludii, GDL, Gambit, boardgame.io, BGA, PettingZoo.
  - [Modelo formal](docs/wiki/modelo-formal.md): forma extensiva + FOSG + statecharts; 8 tipos de
    nodo; acciones con dominios; azar explícito; visibilidad por ubicación con handles opacos;
    simultaneidad, ventanas de reacción y carreras; tiempo; historial; propiedades derivadas.
  - [Lenguaje `.game`](docs/wiki/lenguaje-game.md): sintaxis con ejemplos (tres en raya, dilema del
    prisionero, Kuhn, fragmento de Mentiroso), módulos, mods con `extends`, combinadores.
  - [GameIR](docs/wiki/ir.md): IR de autor vs. resuelta, S-expresiones en JSON, hash de reglas y
    hash de interfaz, layout en sidecar.
  - [Arquitectura](docs/wiki/arquitectura.md), [protocolo](docs/wiki/protocolo.md),
    [Studio](docs/wiki/studio-editor-visual.md), [hub](docs/wiki/hub.md),
    [teoría de juegos](docs/wiki/teoria-de-juegos.md),
    [heurísticas e IA](docs/wiki/heuristicas-e-ia.md), [catálogo](docs/wiki/catalogo-de-juegos.md).
- [Roadmap](docs/wiki/roadmap.md) en 13 fases (F0–F12) con pesos, entregables, criterios de
  aceptación y dependencias. MVP jugable al 41 %, MVP de diseño al 51 %, IA al final.
- [Registro de decisiones](docs/wiki/decisiones.md) (16 ADR) y
  [preguntas abiertas](docs/wiki/preguntas-abiertas.md) (15, dos bloqueantes).
- `README.md` raíz, índice de la wiki con estado, `CLAUDE.md` con las normas de mantenimiento.

**Decisiones**
- Aceptadas (por el usuario): Python 3 + C++; extensión `.game`.
- Propuestas (pendientes de visto bueno): ADR 001–012 y 015 (IR canónica, expresiones puras,
  azar explícito, estados inmutables, visibilidad declarativa, statecharts, Python primero,
  git como backend, WebSocket+JSON, interoperabilidad, monorepo, TS+React).

**Pendiente / siguientes pasos**
- Respuestas a las preguntas 🔴 (mensaje cortado en "También quiero tener una…", licencia).
- Cerrar F0: `git init`, monorepo y herramientas, JSON Schema de la IR, 3 IR de validación.

**Progreso:** ≈ 0,5 % (F0: 1/8).
