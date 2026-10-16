# Arquitectura

> Estado: **propuesta v0.1** (Fase 0). Las elecciones tecnológicas marcadas como *propuesta* están
> pendientes de confirmación en [decisiones](decisiones.md).

## 1. Vista general

```mermaid
flowchart TB
  subgraph Especificar
    TXT[".game + compilador (Python)"]
    STU["Studio (web: diagrama + texto + simulador)"]
    PYB["API Python builder"]
  end
  IR[(GameIR + hash)]
  TXT --> IR
  STU <--> TXT
  PYB --> IR
  subgraph Ejecutar
    REF["Motor de referencia (Python)"]
    CPP["Core C++ (VM / codegen)"]
    WASM["Core en WASM (navegador)"]
  end
  IR --> REF
  IR --> CPP
  CPP --> WASM
  subgraph Servicios
    SRV["Servidor de partidas (salas, códigos, WebSocket)"]
    HUB["Hub (repos, registro, PRs, páginas)"]
    ARE["Arena (torneos de bots, ratings)"]
    ANA["Workers de análisis"]
  end
  REF --> SRV
  CPP --> SRV
  CPP --> ARE
  CPP --> ANA
  subgraph Clientes
    CLI["CLI gamehub"]
    WEB["Cliente web: UI genérica + UI kit"]
    CUS["UIs propias (React, Godot, Unity…) vía SDK"]
    BOT["Bots / agentes"]
  end
  SRV <--> CLI
  SRV <--> WEB
  SRV <--> CUS
  SRV <--> BOT
  HUB --- SRV
```

## 2. Estructura del monorepo (propuesta)

> **Estado (2026-10-10, Fase 4):** existen `spec/` (IR v0, protocolo v1, trazas de conformidad),
> `python/` (paquete `gamehub`: lenguaje Nomos, validación, análisis, motor, presentaciones,
> paquetes, protocolo, servidor de partidas, SDK cliente, CLI y plantilla de UIs), `web/` (SDK
> TypeScript, UI kit, UI genérica y la app para jugar), `stdlib/`, `games/` (15 paquetes con 16
> juegos; tres con UI propia en `games/<juego>/ui`), `editors/vscode/` y `docs/`. La parte de
> JavaScript es un workspace de pnpm en la raíz (`package.json`, `pnpm-workspace.yaml`,
> `biome.json`). El resto de directorios se crea en la fase que los necesita.

```
GameHub/
├── spec/                  # Fuente de verdad de los contratos
│   ├── ir/                # JSON Schema de la GameIR
│   ├── protocol/          # JSON Schema de los mensajes del protocolo
│   └── conformance/       # Trazas doradas que todo motor debe reproducir
├── python/src/gamehub/    # Paquete Python (pip install gamehub)
│   ├── lang/              # Nomos: lexer, parser, AST, tipos y traducción, módulos, mods,
│   │                      #   combinadores, formateador, descompilador, ejecutor de tests
│   ├── ir/                # esquema, catálogo de operadores, validación, hash canónico
│   ├── build.py           # API Python builder → IR
│   ├── engine/            # motor de referencia (intérprete de la IR)
│   ├── analysis/          # avisos estáticos y clasificación (F2); viabilidad, árbol, solvers…
│   ├── render/            # diagrama del flow, reglamento y diff semántico (F2)
│   ├── packages.py        # game.toml, game.lock, dependencias, new/clone/fork (F2)
│   ├── agents/            # interfaz Agent, aleatorio, minimax, MCTS, heurísticas
│   ├── protocol/          # protocolo v1: validación de mensajes y tipos generados (F3)
│   ├── server/            # salas (núcleo puro), transporte Starlette, LAN/mDNS, SQLite (F3)
│   ├── client/            # SDK cliente Python, bots en red, cliente de terminal (F3)
│   ├── lsp/               # servidor de lenguaje de Nomos (pygls): gamehub lsp y el del Studio (F5)
│   ├── studio/            # el Studio: servidor, sesión, ediciones sobre el árbol, modelo,
│   │                      #   simulador, espacio de trabajo (F5)
│   ├── templates/games/   # plantillas de juego (gamehub new --template y el Studio)
│   ├── interop/           # OpenSpiel, Gambit, PettingZoo, PGN…
│   └── cli.py             # gamehub check|fmt|test|viz|rules|diff|new|play|serve|host|join|rooms|bot|studio|lsp|…
├── core/                  # C++20: VM, estado compacto, algoritmos, bindings, WASM
├── web/                   # TypeScript (workspace de pnpm en la raíz, F4)
│   ├── packages/protocol  # tipos generados desde spec/protocol
│   ├── packages/client    # SDK cliente TS (conexión, estado, REST)
│   ├── packages/i18n      # español e inglés
│   ├── packages/react     # hooks de React sobre el SDK
│   ├── packages/ui-kit    # cartas, manos, mazos, tableros, dados, fichas, relojes
│   ├── packages/auto-ui   # UI genérica a partir de la IR
│   ├── packages/shell     # la experiencia de jugar como librería (salas, lobby, replays…)
│   ├── packages/nomos     # Nomos para CodeMirror (resaltado, sangría, plegado, tema)
│   ├── packages/studio    # el Studio como librería (diagrama, editores, inspector, simulador)
│   ├── apps/play          # la app web (la sirve gamehub serve)
│   ├── apps/studio        # la app del Studio (la sirve gamehub studio, F5)
│   └── apps/hub           # web del hub (más tarde)
├── stdlib/std/            # Módulos .game: std.cards, std.dice, std.grid, std.graph (después: std.tricktaking…)
├── games/                 # Catálogo oficial: un paquete por juego (game.toml, .game con sus tests,
│                          #   ui/ = UI propia de React, opcional)
├── editors/vscode/nomos/  # Extensión de VS Code (resaltado, diagnósticos, formato)
├── docs/wiki/             # Esta wiki
└── log.md
```

**Paquete de juego** (lo que se clona/publica):

```
wizard/
├── game.toml          # nombre, versión, autores, licencia, dependencias (std >= 0.3)
├── wizard.game        # reglas (puede repartirse en varios archivos/módulos)
├── wizard.layout.json # posiciones del diagrama (opcional)
├── tests/             # escenarios .game y trazas doradas
├── heuristics/        # heurísticas y bots (opcional)
├── ui/                # interfaces propias (opcional)
└── README.md          # + reglamento autogenerado
```

## 3. El contrato de motor (Game API)

Todos los motores (Python, C++, WASM) implementan **la misma interfaz**, verificada por las
[trazas de conformidad](../../spec/conformance). Es deliberadamente parecida a OpenSpiel para que el
puente sea trivial. Implementada en el motor de referencia (Fase 1, detalle en [motor](motor.md)):

```python
class Game:
    id, version, title, rules_hash, players            # (mín, máx)
    def new_state(self, num_players=None, params=None) -> State: ...

class State:                                           # INMUTABLE: cada paso devuelve otro estado
    status: Status                                     # CHANCE | DECISION | TERMINAL
    active_seats: tuple[int, ...]
    payoffs: tuple | None
    def legal_actions(self, seat) -> list[Action]
    def options(self, seat, name=None, args=None) -> list   # construcción progresiva
    def apply_action(self, seat, action) -> State
    def chance_outcomes(self, limit=100_000) -> list[tuple[Outcome, Fraction]]
    def sample_chance(self, rng: Pcg32) -> Outcome
    def apply_chance(self, outcome) -> State
    def view(self, seat | None) -> dict                # None = omnisciente
    def events(self, seat | None) -> list[dict]        # eventos del último paso
    def information_state(self, seat) -> str           # clave del conjunto de información
    def snapshot(self) -> dict;  def digest(self) -> str
    def history(self) -> list[Step];  def decode_action(self, seat, json) -> Action
```

El **bucle de partida no está en el motor**: lo ponen los *drivers* (`play_match`, `fuzz`, la CLI,
el servidor, el simulador del Studio, el entrenador RL, los torneos).

## 4. Pila tecnológica (propuesta)

| Área | Propuesta | Motivo | Alternativas |
|---|---|---|---|
| Python | 3.12+, `uv`, `ruff`, `pyright`, `pytest`, `hypothesis` | Moderno y rápido de iterar | poetry |
| Parser | **Lark** (v0) → **tree-sitter** (para editores) | Iteración rápida; luego multi-lenguaje | ANTLR, recursivo descendente a mano |
| Contratos | JSON Schema → `TypedDict` (Py) y `interface` (TS), generados ([ADR-045](decisiones.md)) | Una sola definición | protobuf |
| Servidor | **Starlette + uvicorn + websockets** (F3, [ADR-036](decisiones.md)) | Async y ligero; contratos en JSON Schema | FastAPI, aiohttp |
| Persistencia local | SQLite | Cero configuración | — |
| C++ | C++20, CMake, **nanobind**, Catch2 | Velocidad + bindings ligeros | pybind11 |
| Navegador | Emscripten (core C++ → WASM) | Mismo motor en todas partes | Pyodide (provisional) |
| Web | TypeScript 7, React 19, Vite 8, pnpm, Biome, Vitest (F4, [ADR-044](decisiones.md)) | Ecosistema; Biome es el ruff de JS | Svelte; ESLint + Prettier |
| Diagramas | React Flow (`@xyflow/react`) + ELK.js (F5, [ADR-055](decisiones.md)) | Estándar de editores de nodos + auto-layout | Rete.js, JointJS, dagre |
| Editor de texto | **CodeMirror 6** + LSP (`pygls`) (F5, [ADR-053](decisiones.md), [054](decisiones.md)) | Ligero, decenas de campos por página, cliente LSP oficial | Monaco |
| Análisis | NumPy, SciPy (HiGHS), `pygambit`, OpenSpiel | No reinventar solvers | — |
| RL | PyTorch, Gymnasium, PettingZoo | Estándar | JAX |
| Hub | FastAPI + PostgreSQL + S3/MinIO + **Forgejo** (git) | No reinventar git | Gitea, git propio |

## 5. Estrategia de calidad

| Nivel | Qué | Herramienta |
|---|---|---|
| Unitario | Lenguaje, expresiones, efectos, visibilidad | pytest / Catch2 / vitest |
| Escenarios de reglas | Bloques `test` dentro de cada juego | `gamehub test` |
| Propiedades | Invariantes (`invariant total_cards == 52`), playouts aleatorios sin errores | hypothesis + fuzzer propio |
| Trazas doradas | Misma semilla + acciones ⇒ mismos eventos, vistas y pagos | `spec/conformance/` |
| Diferencial | Python vs C++ vs WASM sobre millones de playouts | runner de conformidad |
| Referencias externas | *perft* de ajedrez, valor de Kuhn (−1/18), tres en raya = tablas | tests de análisis |
| Fugas de información | Ninguna vista contiene datos no visibles | análisis estático + test de vistas |

## 6. Seguridad

- Las reglas son **datos**: ejecutar un juego desconocido en el servidor es seguro por diseño
  (límites de pasos y memoria contra abusos).
- **Plugins nativos** (p. ej. evaluador de manos de póker): puros, con firma declarada y
  preferentemente en **WASM** (sandbox en servidor, navegador y C++), siempre con una
  implementación de referencia en el lenguaje para verificarlos.
- **Servidor autoritativo:** el cliente solo recibe su vista redactada; nunca el estado completo.
- **Studio local** ([ADR-057](decisiones.md)): solo en 127.0.0.1 por defecto, token aleatorio,
  Host y Origin comprobados (contra el *DNS rebinding* y otras páginas del navegador), y solo
  archivos `.game` del directorio de trabajo.
- Bots de terceros: en proceso separado / contenedor / WASM, con límites de CPU, memoria y tiempo.
