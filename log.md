# Log de trabajo

Registro cronológico de lo que se hace en el proyecto. La entrada más reciente va arriba.
Formato: fecha · qué se hizo · decisiones · pendientes / siguientes pasos.

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
