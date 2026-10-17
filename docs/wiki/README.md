# GameHub wiki

> A platform and a protocol to **design games with mathematical precision**, version them as on
> GitHub, play them from any interface and study them with game theory, heuristics and AI.

## Project status

| | |
|---|---|
| **Last updated** | 2026-10-17 |
| **Current phase** | F0 to F7 in `main`; **F8, the C++ core**, on the `f8/nucleo-cpp` branch: complete except the optional code generation, waiting for your approval to merge |
| **Overall progress** | ≈ 75 % (F0 to F8 complete; F8's optional code generation left) |
| **What works** | Games are designed by writing **Nomos** (`.game`) —a compiler to GameIR with types and clear errors, warnings, classification, tests and invariants, a formatter, modules and a standard library, variants and combinators, packages, diagram, rulebook, semantic diff, presentation hints, declared ranges (`@range`)— or **in the Studio** (`gamehub studio`): diagram and text kept in sync, inspector, language server and simulator. They are **played over the network** (rooms with a code, link and QR code, LAN, spectators, bots, clocks, reconnection, provably fair chance) and **in the browser**. The catalog has the requested games: **chess** (FIDE, exact *perft(5)*), **Skat** (ISkO), no-limit **Texas Hold'em** with side pots, **Wizard**, **Parchís** (also in pairs), Klondike **Solitaire** and Bullshit. Two engines with the same semantics: the Python reference and the **[C++ core](core.md)** (`gamehub-core`), 57–63 times faster, with perft, exact alpha-beta, retrograde analysis, MCTS, CFR and MCCFR; the same core runs **in the browser as WebAssembly** (`@gamehub/engine`): matches on one device without a server (bots at random or MCTS), the Studio's playouts, and a static site with every game (`gamehub web export`). They are **analyzed with game theory** (`gamehub analyze`, notebooks and the Studio's Analysis tab): a feasibility advisor, exact equilibria, alpha-beta and backward induction, CFR+ with exploitability, Grundy, cooperative solutions, Axelrod tournaments, export to Gambit and an **OpenSpiel bridge for every catalog game** (global action ids from the IR: OpenSpiel's MCTS plays chess, its MCCFR runs on Hold'em). |
| **Code** | [`spec/`](../../spec/README.md) (IR v0, protocol v1, traces) · [`core/`](../../core) (C++20: VM, values, algorithms, Python bindings) · [`python/`](../../python) (`gamehub`: language, LSP, analysis, engine, native plugins, server, Studio, client, CLI; 1,150+ tests, some long-running) · [`web/`](../../web) (TypeScript SDK, the WASM engine, UI kit, generic UI, play app, Studio; 190+ tests) · [`stdlib/`](../../stdlib/std) (9 modules) · [`games/`](../../games) (22 packages, 23 games, 7 custom UIs) · [`editors/vscode/nomos`](../../editors/vscode/nomos) |
| **Quality** | F8: the 16 golden traces reproduced bit for bit by the C++ core, natively and as WebAssembly; a differential sweep of every catalog game, 10,140,000 matches compared step by step, 0 differences; the browser's playouts, plugins and local matches equal to Python's; ×57.7, ×56.8 and ×63.2 in tic-tac-toe, Connect Four and Kuhn. F7: every reference result of [game theory §6](game-theory.md) except Connect Four 7×6 (moved to F9, ADR-081). F6: chess *perft(5)* = 4,865,609; Skat against the ISkO examples; 10⁵ random matches without errors of every second-wave game |
| **Recent decisions** | Proposed for F8, ADR-075 to 080 and 082: the C++ core and its package; values, arena and automatic Zobrist hashing with exact 64-bit numbers; the bytecode VM; differential conformance; global action ids, `@range` and OpenSpiel without exploring; the algorithms in C++; the core in the browser. Accepted for F7: ADR-068 to 074 |
| **Waiting on you** | [Question 24](open-questions.md) and the rest of the [open questions](open-questions.md); approving F8's ADR-075 to 080 and 082 and merging F8 into `main` |
| **Next step** | Your approval of F8 (ADR-075 to 080, 082) and its merge; then F9: heuristics, bots and Connect Four 7×6 |

Detailed history: [`log.md`](../../log.md). Original prototype: [`structure.py`](../../structure.py) ([analysis](structure-py-analysis.md)).

## Wiki map

**Vision and design**
- [Vision](vision.md) — what GameHub is, principles, non-goals, prior art
- [Brainstorming: gaps, improvements and ideas](ideas.md)
- [Analysis of `structure.py`](structure-py-analysis.md) — what is kept and what changes

**Specifications**
- [Formal model](formal-model.md) — the semantics: nodes, actions, chance, information, time, payoffs
- [Nomos, the `.game` language](language.md) — reference v0.1: syntax, types, flow, tests, modules, mods, tools, diagnostics
- [GameIR](ir.md) — canonical intermediate representation, hashes, versioning, validation ([`spec/`](../../spec/README.md))
- [Reference engine](engine.md) — exact operational semantics, chance, events, formats, performance
- [The C++ core](core.md) — the second engine: values, VM, conformance, performance, action ids, algorithms (F8)
- [Match protocol](protocol.md) — v1 implemented: rooms, messages, turns, spectators, clocks, LAN, provably fair chance, performance
- [Web client](web-client.md) — playing in the browser: the app, the generic UI, the kit, custom UIs and their template

**Components**
- [Architecture](architecture.md) — monorepo, engine contract, technology stack, quality, security
- [Studio (visual editor)](studio.md) — design with diagram and text at once, inspector, simulator and tools (F5)
- [Hub ("GitHub for games")](hub.md)
- [Game theory](game-theory.md)
- [Heuristics, bots, arena and AI](heuristics-and-ai.md)
- [Game catalog](game-catalog.md)

**Planning and reference**
- [Roadmap 0 → 100 %](roadmap.md)
- [Decision record (ADR)](decisions.md)
- [Open questions](open-questions.md)
- [Glossary](glossary.md)

## How this wiki is maintained

- Every work session adds an entry to `log.md` and updates the **Project status**.
- The [roadmap](roadmap.md) checkboxes are the source of the progress percentage.
- Every architecture decision is recorded in [decisions](decisions.md).
- When an open question is answered, it moves to "Answered" with its date.
- Design pages carry their status in the header (draft → stable → implemented).
- The documentation is written in English; games may ship a Spanish translation of their texts
  (titles, descriptions, UI labels) as optional data.
