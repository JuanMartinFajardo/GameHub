# GameHub wiki

> A platform and a protocol to **design games with mathematical precision**, version them as on
> GitHub, play them from any interface and study them with game theory, heuristics and AI.

## Project status

| | |
|---|---|
| **Last updated** | 2026-10-16 |
| **Current phase** | F0 to F6 complete and in `main` (F6, the second catalog wave, merged on 2026-10-16); the documentation, translated into English on the `docs/english` branch → next: F7 |
| **Overall progress** | ≈ 59 % (F0 to F6 complete) |
| **What works** | Games are designed by writing **Nomos** (`.game`) —a compiler to GameIR with types and clear errors, warnings, classification, tests and invariants, a formatter, modules and a standard library, variants and combinators, packages, diagram, rulebook, semantic diff, presentation hints— or **in the Studio** (`gamehub studio`): diagram and text kept in sync, inspector, language server and simulator. They are **played over the network** (rooms with a code, link and QR code, LAN, spectators, bots, clocks, reconnection, provably fair chance) and **in the browser**. The catalog already has the requested games: **chess** (FIDE, exact *perft(5)*), **Skat** (ISkO), no-limit **Texas Hold'em** with side pots, **Wizard**, **Parchís** (also in pairs), Klondike **Solitaire** and Bullshit. The engine memoizes pure functions and compiles the IR to Python code; expensive functions can have a **native plugin** in WebAssembly (the poker evaluator), with the Nomos body as the reference. |
| **Code** | [`spec/`](../../spec/README.md) (IR v0, protocol v1, traces) · [`python/`](../../python) (`gamehub`: language, LSP, analysis, engine, native plugins, server, Studio, client, CLI; 966 tests, 6 of them long-running) · [`web/`](../../web) (TypeScript SDK, UI kit, generic UI, play app, Studio; 136 tests including the custom UIs') · [`stdlib/`](../../stdlib/std) (9 modules) · [`games/`](../../games) (22 packages, 23 games, 7 custom UIs) · [`editors/vscode/nomos`](../../editors/vscode/nomos) |
| **Quality** | F6 acceptance: chess *perft(5)* = 4,865,609 and the reference *perft* counts of five other positions; Skat game values match the ISkO examples; 10⁵ random matches without a single error of chess, Skat, Wizard and Parchís (Solitaire's and Hold'em's still running); the 22 catalog packages are played to the end with the generic UI against the server. The native poker evaluator gives the same results as the reference on thousands of random hands, and the generated code the same as the closures in every game |
| **Recent decisions** | ADR-067: the documentation in English, Spanish only as an optional translation shipped by each game. Accepted (2026-10-16) the F6 ones, ADR-060 to 066: memoization of IR functions; `perft` and `fuzz --jobs`; **native WebAssembly plugins** with a mandatory reference; Python code generated from the IR; card-game libraries without generics; the rules of the second wave; language adjustments |
| **Waiting on you** | [Question 24](open-questions.md) (how far the English switch goes: code comments, CLI messages, games' default language, commit messages) and approval to merge `docs/english`; the rest of the [open questions](open-questions.md) |
| **Next step** | F7: game theory v1 |

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
