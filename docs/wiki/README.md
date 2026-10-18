# GameHub wiki

> A platform and a protocol to **design games with mathematical precision**, version them as on
> GitHub, play them from any interface and study them with game theory, heuristics and AI.

## Project status

| | |
|---|---|
| **Last updated** | 2026-10-18 |
| **Current phase** | F0 to F9 in `main` (F9 without the Connect Four 7×6 proof, ADR-089); **F10** (the web hub) done in the `f10/hub` branch, waiting for your approval |
| **Overall progress** | ≈ 90 % (F0 to F9 in `main`, without the 7×6 proof; F10 in its branch) |
| **What works** | Games are designed by writing **Nomos** (`.game`) —a compiler to GameIR with types and clear errors, warnings, classification, tests and invariants, a formatter, modules and a standard library, variants and combinators, packages, diagram, rulebook, semantic diff, presentation hints, declared ranges (`@range`)— or **in the Studio** (`gamehub studio`): diagram and text kept in sync, inspector, language server and simulator. They are **played over the network** (rooms with a code, link and QR code, LAN, spectators, bots, clocks, reconnection, provably fair chance) and **in the browser**. The catalog has the requested games: **chess** (FIDE, exact *perft(5)*), **Skat** (ISkO), no-limit **Texas Hold'em** with side pots, **Wizard**, **Parchís** (also in pairs), Klondike **Solitaire** and Bullshit. Two engines with the same semantics: the Python reference and the **[C++ core](core.md)** (`gamehub-core`), 57–63 times faster, with perft, exact alpha-beta, retrograde analysis, MCTS, CFR and MCCFR; the same core runs **in the browser as WebAssembly** (`@gamehub/engine`): matches on one device without a server, the Studio's playouts, and a static site with every game (`gamehub web export`). **Bots** ([heuristics and AI](heuristics-and-ai.md)): every game has a **heuristic** written in Nomos (features, weights, priority rules and move order; outside the rules hash) and plays against rule-based, alpha-beta, MCTS, ISMCTS and PIMC bots that only use what their seat sees (determinization), in the terminal, the server's rooms and the browser; an **arena** with Elo, Glicko-2, TrueSkill and SPRT per rules hash, bot packages with sandboxing, **balance analytics** with a Balance CI, and weight tuning (CMA-ES, SPSA, Texel). They are **analyzed with game theory** (`gamehub analyze`, notebooks and the Studio's Analysis tab): a feasibility advisor, exact equilibria, alpha-beta and backward induction, CFR+ with exploitability, Grundy, cooperative solutions, Axelrod tournaments, export to Gambit and an **OpenSpiel bridge for every catalog game** (global action ids from the IR: OpenSpiel's MCTS plays chess, its MCCFR runs on Hold'em). They are **shared on the [hub](hub.md)** (`gamehub hub serve`, a "GitHub for games"): git repositories of games and libraries, accounts, organizations and OAuth, versions whose number the hub chooses from the **interface hash** (automatic semver), hub dependencies, forks and **proposals reviewed in four layers** (text, rules, diagram and Balance CI), sandboxed analysis and arena jobs with quotas, hosted rooms of any published version with **matchmaking and human ratings**, search by mathematical properties, family trees, Pages and moderation, with its own website. |
| **Code** | [`spec/`](../../spec/README.md) (IR v0, protocol v1, traces) · [`core/`](../../core) (C++20: VM, values, algorithms, Python bindings) · [`python/`](../../python) (`gamehub`: language, LSP, analysis, engine, native plugins, server, Studio, client, hub, CLI; 1,260+ tests, some long-running) · [`web/`](../../web) (TypeScript SDK, the WASM engine, UI kit, generic UI, play app, Studio, hub website; 190+ tests) · [`stdlib/`](../../stdlib/std) (9 modules) · [`games/`](../../games) (22 packages, 23 games, 7 custom UIs) · [`editors/vscode/nomos`](../../editors/vscode/nomos) |
| **Quality** | F10: the phase's acceptance end to end (publish, fork, variant, proposal with its four diffs, merge, automatic 1.1.0, a match over the network) in tests, also against PostgreSQL, and in the browser; git clone and authenticated push over HTTP; OAuth with a fake provider; CSRF and sandboxed Pages. F9: the heuristics give the same values in both engines; the rule-based bot beats random in every catalog game; the rating systems match their published reference values; round-robin tournaments in 5 games and balance reports for Parchís and Wizard ([`docs/reports`](../reports)). F8: the 16 golden traces reproduced bit for bit by the C++ core, natively and as WebAssembly; a differential sweep of every catalog game, 10,140,000 matches compared step by step, 0 differences; the browser's playouts, plugins and local matches equal to Python's; ×57.7, ×56.8 and ×63.2 in tic-tac-toe, Connect Four and Kuhn. F7: every reference result of [game theory §6](game-theory.md) except Connect Four 7×6 (moved to F9, ADR-081). F6: chess *perft(5)* = 4,865,609; Skat against the ISkO examples; 10⁵ random matches without errors of every second-wave game |
| **Recent decisions** | Proposed for F10, ADR-090 to 097: the hub's backend (Starlette, SQLite or PostgreSQL, object store, our own git service, AGPL); the interface hash and automatic semver; accounts and OAuth; hub dependencies; proposals in four layers; sandboxed jobs and quotas; playing on the hub with matchmaking and human ratings; search, family tree, Pages, moderation and the website. Accepted for F9: ADR-083 to 089 |
| **Waiting on you** | [Question 30](open-questions.md) (approve ADR-090 to 097 and merge F10), question 14 (where to host the hub), question 24 (how far the English switch goes) and the rest of the [open questions](open-questions.md) |
| **Next step** | Your review of F10 (question 30); then F11 (AI) or F12 (hardening and hosting the hub) |

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
- [Hub ("GitHub for games")](hub.md) — implemented (F10): repositories, versions with automatic semver, proposals with four diffs, jobs, hosted play, search, Pages, moderation
- [Game theory](game-theory.md)
- [Heuristics, bots, arena and AI](heuristics-and-ai.md) — heuristic blocks, bots with determinization, arena and ratings, balance analytics, tuning (F9)
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
