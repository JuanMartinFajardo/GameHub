# GameHub wiki

> A platform and a protocol to **design games with mathematical precision**, version them as on
> GitHub, play them from any interface and study them with game theory, heuristics and AI.

## Project status

| | |
|---|---|
| **Last updated** | 2026-10-17 |
| **Current phase** | F0 to F7 in `main` (F7, game theory v1, and the documentation in English approved on 2026-10-17) → next: F8, the C++ core |
| **Overall progress** | ≈ 66 % (F0 to F7 complete and in `main`) |
| **What works** | Games are designed by writing **Nomos** (`.game`) —a compiler to GameIR with types and clear errors, warnings, classification, tests and invariants, a formatter, modules and a standard library, variants and combinators, packages, diagram, rulebook, semantic diff, presentation hints— or **in the Studio** (`gamehub studio`): diagram and text kept in sync, inspector, language server and simulator. They are **played over the network** (rooms with a code, link and QR code, LAN, spectators, bots, clocks, reconnection, provably fair chance) and **in the browser**. The catalog already has the requested games: **chess** (FIDE, exact *perft(5)*), **Skat** (ISkO), no-limit **Texas Hold'em** with side pots, **Wizard**, **Parchís** (also in pairs), Klondike **Solitaire** and Bullshit. The engine memoizes pure functions and compiles the IR to Python code; expensive functions can have a **native plugin** in WebAssembly (the poker evaluator), with the Nomos body as the reference. They are **analyzed with game theory** (`gamehub analyze`, notebooks and the Studio's Analysis tab): a feasibility advisor, exact equilibria (Nash, zero-sum, correlated, sequence form), alpha-beta and backward induction, CFR+ with exploitability, Grundy, cooperative solutions, Axelrod tournaments, export to Gambit and an OpenSpiel wrapper. |
| **Code** | [`spec/`](../../spec/README.md) (IR v0, protocol v1, traces) · [`python/`](../../python) (`gamehub`: language, LSP, analysis, engine, native plugins, server, Studio, client, CLI; 1,038 tests, 7 of them long-running) · [`web/`](../../web) (TypeScript SDK, UI kit, generic UI, play app, Studio; 137 tests including the custom UIs') · [`stdlib/`](../../stdlib/std) (9 modules) · [`games/`](../../games) (22 packages, 23 games, 7 custom UIs) · [`editors/vscode/nomos`](../../editors/vscode/nomos) |
| **Quality** | F7 acceptance: every reference result of [game theory §6](game-theory.md) reproduced exactly (tic-tac-toe a draw with its 5,478 positions and 255,168 games; the prisoner's dilemma, rock-paper-scissors and matching pennies equilibria; Kuhn's −1/18 with exploitability 0; Nim's P-positions) except Connect Four 7×6, which needs the C++ core (F8; checked on small boards). Gambit and OpenSpiel confirm our exports. F6: chess *perft(5)* = 4,865,609; Skat against the ISkO examples; 10⁵ random matches without errors of chess, Skat, Wizard and Parchís |
| **Recent decisions** | Accepted for F7, ADR-068 to 074: game theory on the reference engine in exact arithmetic (extensive form with the engine's information sets, state graph); an exact rational simplex with HiGHS for large programs; the solution concepts per class; the feasibility advisor; Gambit and OpenSpiel; `gamehub analyze` and the Studio's Analysis tab; Connect Four 7×6 moves to F8. ADR-067: the documentation in English |
| **Waiting on you** | [Question 24](open-questions.md) (how far the English switch goes: code comments, CLI messages, commit messages) and the rest of the [open questions](open-questions.md) |
| **Next step** | F8: the C++ core, bindings and WASM (×50 speed; Connect Four 7×6; global action ids from the IR, so the OpenSpiel bridge works on every game) |

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
