# Open questions

> Decisions that are yours to make. Each one carries my **default recommendation**: if you say
> nothing, work proceeds with it. 🔴 = blocks the indicated phase.

| # | Question | Default recommendation | Affects |
|---|---|---|---|
| 24 | How far does the English switch go beyond the documentation: **code comments and docstrings**, **CLI and terminal messages** (`/listo`, "partidas en … s"), the **default language of the games and UIs** (Spanish today, English as a translation) and **commit messages**? | Everything in English: comments, docstrings, CLI messages and commands, commit messages from now on; games and UIs with English as the default and Spanish as an optional translation they ship | Whole repository |
| 20 | Do you need to play **over the internet** (outside the LAN) before the hub? | Until F10, `gamehub serve` on a reachable machine or a Tailscale-like tunnel; our own relay with the hub (F10) | F4, F10 |
| 3b | Will there be a remote repository on GitHub (or another host)? | Whenever you like; CI is ready | Everything |
| 6 | Who will use the visual editor? Should someone who does not program be able to design a game (Scratch-like blocks for conditions)? | As in Phase 5: conditions and effects written in Nomos in the fields, with completion and the error in place; visual blocks as a later improvement | Studio, after F5 |
| 7 | Are you happy with TypeScript + React for the web? Do you have experience with any framework? | TS + React + React Flow + CodeMirror, as F4 and F5 already use (ADR-044, 054, 055) | Web |
| 8 | Do you want a **Godot** SDK soon to build game UIs there? | After TS and Python, unless you are interested earlier | F4–F6 |
| 9b | **Bullshit** variants: does the rank follow the sequence Ace, Two, Three…, is it chosen by whoever opens the round, or is it free on each play? Can anyone call, or only the next player? Who plays after a call? French or Spanish deck? | Sequence A→K; anyone can call; the next player continues; French 52-card deck. With Nomos, each variant is a few-line `extends` (the Spanish one, with `std.cards`) | Bullshit (whenever you like) |
| 10 | Do you work alone? How many hours per week? A target date for the MVP? | Alone + AI; pace to be defined | Order and size of phases |
| 11 | Continuous real-time games (arcade-like), or are discrete + `race` nodes enough? | Discrete + `race`; continuous out of scope | Model |
| 12 | Platforms: only macOS, or also Linux/Windows? | Development on macOS; CI on Linux. The F3 server and client are portable (no mandatory Unix signals, input in a thread) but **have not been tested on Windows**: add it to CI once there is a remote repository (3b) | F0, F8 |
| 13 | Exact numeric payoffs (rationals) or floating point? | Rationals in the IR and in the reference engine; in the C++ core, **exact 64-bit integers and rationals** (a result that does not fit is a rule error), so that traces are identical (ADR-076; it was `double`) | F1, F8 |
| 14 | Hub hosting (own server, cloud, budget?) | Decide in F10; everything works locally before that | F10 |
| 15 | Store statistics of human matches for balance analytics? (privacy) | Since F3 the server stores replays only locally (SQLite, with player names); using them for analytics: optional and anonymous, enabled by the host | F9 |

## Answered

| Date | # | Question | Answer |
|---|---|---|---|
| 2026-10-09 | 1 | Message cut off at *"I also want to have a…"* | You don't remember it. Closed; it will be reopened if it comes back. |
| 2026-10-09 | 2 | License | Proposal accepted: Apache-2.0 (engine/SDKs), AGPL-3.0 (hub server), CC-BY-4.0 (games). → [ADR-016](decisions.md), [`LICENSING.md`](../../LICENSING.md) |
| 2026-10-09 | 3 (partial) | Should I initialize git? | Yes: repository created on the `main` branch. The commit policy remained pending (question 3). |
| 2026-10-09 | 4 | Name of the language | **Nomos**. → [ADR-017](decisions.md) |
| 2026-10-09 | 5 | Syntax | Braces and English keywords. → [ADR-018](decisions.md) |
| 2026-10-09 | 9 (partial) | What is "Mentiroso"? | **Bullshit**: cards are placed face down in the center while declaring "3 fours"; if you are called and it was a lie, you take the whole pile; if it was true, the caller takes it. → [catalog](game-catalog.md), [`mentiroso.ir.json`](../../spec/ir/examples/mentiroso.ir.json) |
| 2026-10-09 | — | Start Phase 0? | Yes. |
| 2026-10-09 | 3 | Commit policy | **One commit per task.** Phase 0 goes to `main`; each later phase is worked on in its own branch (`f1/…`) and merged with your approval. |
| 2026-10-09 | 16 | Are the proposed ADRs accepted? | No objections: you asked to start Phase 1 on top of them. They are considered accepted (reversible if you change your mind). |
| 2026-10-09 | — | Start Phase 1? | Yes. |
| 2026-10-09 | — | Merge Phase 1 and start Phase 2? | Yes: F1 merged into `main` and F2 on the `f2/compilador-nomos` branch. |
| 2026-10-10 | 17 | Do you approve ADR-027 to 035 of Phase 2 and merge the `f2/compilador-nomos` branch? | Yes: ADR-027 to 035 accepted, F2 merged into `main` and F3 on the `f3/servidor-partidas` branch. |
| 2026-10-10 | 18 | Do you approve ADR-036 to 043 of Phase 3 and merge the `f3/servidor-partidas` branch? | Yes: ADR-036 to 043 accepted, F3 merged into `main` and F4 on the `f4/cliente-web` branch. |
| 2026-10-11 | 21 | Do you approve ADR-044 to 051 of Phase 4 and merge the `f4/cliente-web` branch? | Yes ("go on with phase 5"): ADR-044 to 051 accepted, F4 merged into `main` and F5 on the `f5/studio` branch. |
| 2026-10-16 | 22 | Do you approve ADR-052 to 059 of Phase 5 and merge the `f5/studio` branch? | Yes: ADR-052 to 059 accepted (among them CodeMirror instead of Monaco) and F5 merged into `main`. |
| 2026-10-16 | 9 | Specific rules for Solitaire, Poker, Skat, Parchís and Wizard | The recommended ones: Klondike, no-limit Texas Hold'em, ISkO (without Kontra or Ramsch), Spanish Parchís (pairs as an option) and Amigo's Wizard (*hook* as an option); chess, FIDE. → [ADR-065](decisions.md), [catalog](game-catalog.md) |
| 2026-10-16 | 19 | When do we add each game's own `on_timeout`? | It was not needed in F6: losing on time is the room's `forfeit` option and resigning is up to the server (ADR-065). It will be revisited if a game needs its own default move. |
| 2026-10-16 | 23 | Do you approve ADR-060 to 066 of Phase 6 and merge the `f6/catalogo-ola-2` branch? | Yes: ADR-060 to 066 accepted and F6 merged into `main`. Next: the documentation, in English. |
| 2026-10-16 | — | Language of the project | The documentation (wiki, READMEs, log, CLAUDE.md) moves to **English**: the project must look professional. Games may keep Spanish as an optional translation they ship. → [ADR-067](decisions.md) |
| 2026-10-17 | 25 | Do you approve ADR-068 to 074 of Phase 7 and merge the `f7/teoria-de-juegos` branch (which brings `docs/english`)? | Yes: ADR-068 to 074 accepted (Connect Four 7×6 moves to F8) and F7 merged into `main` together with the English documentation. Next: F8. |
| 2026-10-17 | — | Bring forward global action ids from the IR (for the OpenSpiel bridge on large games)? | Yes, to F8 (they were part of F11's tensorization). → [roadmap](roadmap.md) |
| 2026-10-17 | 26 | Connect Four 7×6: move it to F9 (heuristic move ordering) or write the typed C++ code generation now? | Move it to F9. → [ADR-081](decisions.md) |
| 2026-10-17 | — | Install the Emscripten SDK for the WASM build? | Yes (`~/emsdk`). |
