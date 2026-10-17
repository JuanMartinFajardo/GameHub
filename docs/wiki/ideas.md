# Brainstorming: gaps, improvements and ideas

> Outcome of the design session of 2026-10-09. Each idea links to the page where it is developed.

## A. Gaps in the original idea (essential details that were missing)

| # | Gap | Proposal | Where |
|---|---|---|---|
| 1 | **Payoffs and outcomes** | Payoff vector at terminals + ranking + intermediate rewards for RL | [Model §3.8](formal-model.md) |
| 2 | **Chance** | A *nature* pseudo-player; only in `chance` nodes; explicit distributions; enumerable vs. sampleable | [Model §3.3](formal-model.md) |
| 3 | **Fine-grained information** | Visibility per *location* (variable, zone, size, component, event), state-dependent | [Model §3.4](formal-model.md) |
| 4 | **Subtle information leaks** | Opaque handles, re-anonymizing on shuffle, canonical order, a warning when legality depends on hidden data | [Model §3.4](formal-model.md) |
| 5 | **Seat ≠ participant** | Rules talk about seats; humans/bots/spectators occupy them | [Protocol §2](protocol.md) |
| 6 | **Real simultaneity and interruptions** | `simultaneous` and `window` nodes (Bullshit!, UNO!, claiming in Mahjong) | [Model §3.5](formal-model.md) |
| 7 | **Time** | Clocks, deadlines, `on_timeout`; speed games with server timestamps | [Protocol §9](protocol.md) |
| 8 | **Parameters and variants** | `params` with validations; number of players as a range | [Language](language.md) |
| 9 | **Rules that depend on history** | Declared history features (threefold repetition) keeping the state Markovian | [Model §3.7](formal-model.md) |
| 10 | **Reproducibility** | Total determinism, seeds, replays, a universal position notation | [Model §4](formal-model.md) |
| 11 | **Actions with several parameters** | Progressive building (origin → destination → promotion) | [Protocol §6](protocol.md) |
| 12 | **Termination** | Static detection of loops without progress; `max_steps` | [Model §7](formal-model.md) |
| 13 | **Rule tests** | `test` blocks, invariants, fuzzing, golden traces | [Architecture §5](architecture.md) |
| 14 | **Which version of the rules?** | A rules hash on every artifact (bot, replay, analysis, rating) | [IR §5](ir.md) |
| 15 | **Room meta-actions** | Undo, offering a draw, pausing, leaving: outside the rules, in the protocol (leaving, implemented in F3; the rest, pending) | [Protocol §9](protocol.md) |
| 16 | **Security** | Rules = data; pure, sandboxed plugins; authoritative server | [Architecture §6](architecture.md) |
| 17 | **Intellectual property** | Our own rulebooks and art; care with trademarks | [Hub §10](hub.md) |

## B. Proposed improvements

**Game design**
1. **A canonical IR with three front-ends**: `.game` text, the Studio diagram and a Python
   *builder* API (for programmatically generated families: random matrices, parametric boards).
2. **Hierarchical statecharts** instead of a flat diagram (match → round → trick → turn).
3. **Game combinators**: `repeat`, `best_of`, `sum` (CGT sum), `sequence`, `with_params`.
4. **Mods = inheritance + patches** (`extends`, `override`, `remove`): a mod is a small, readable diff.
5. A **standard library** of decks, dice, boards, tricks, auctions and betting.
6. A **generated rulebook** (Markdown/PDF, multilingual) from the IR, with diagrams.

**Verification and analysis**
7. **Information-flow analysis**: an automatic leak detector.
8. **Rule coverage** (like code coverage): rules that never fire.
9. **Feasibility advisor**: classification + estimated size + which computations are possible.
10. **CGT and cooperative-game modules** (Sprague–Grundy, Shapley, core).
11. Axelrod-style **repeated-game tournaments**.
12. **Bridges to OpenSpiel, Gambit, PettingZoo and CGSuite** from the start; importers for
    existing notations (PGN, SGF…).

**Play and interfaces**
13. **Automatic generic UI**: any game is playable without writing an interface.
14. **UI kit** (cards, hands, boards, dice, clocks) + optional rendering hints in the `.game`.
15. **Typed SDKs generated per game** (TS, Python, Godot, Unity).
16. **Provably fair chance** (commit–reveal) in online matches.
17. **Puzzles and positions**: start from any serialized state.
18. **Referee mode** for physical matches (e.g. keeping the score of a real Skat table).
19. **Accessibility**: since everything is structured, the generic UI can be screen-reader
    accessible.

**Collaboration**
20. **Semantic, visual and behavioral diffs** (Balance CI) on change proposals.
21. **Automatic semver** from the interface hash.
22. A **family tree** of games (forks/variants) and **search by mathematical properties**.
23. **GameHub Pages**: hosting for custom UIs.
24. **Classroom mode**: game-theory exercises on real games.

**AI (at the end)**
25. Automatic tensorization from the IR; RL adapters; vectorized environments in C++.
26. LLM agents and assisted design (rules in natural language → a `.game` draft).
27. *Recall* and reaction-time policies for bots (fair play).

## C. Ideas for later

- **Nomic mode**: games whose actions modify the rules themselves (patches to the IR in the
  middle of a match).
- **Evolutionary game design**: (genetic) search over IRs guided by the balance metrics, as
  Cameron Browne's *Ludi* system did (it designed *Yavalath*).
- **Mental poker**: P2P matches without a trusted referee.
- **Real-time collaborative editing** of the diagram (CRDT).

### From Phase 4 (web client)

- **Animations from events**: `move`, `flip` and `reveal` events already say what goes where; the
  generic UI could animate cards and tokens without knowing anything about the game.
- **Hints for more shapes**: tracks (`track`, for Parchís), graphs with coordinates, dice as a way
  to pick an argument (the face in Dudo), grouping variables into panels.
- **Translatable tags in the IR**: today `meta.tags` are English words the app translates with a
  dictionary; a shared tag catalog would also serve the hub.
- **An installable, offline app** (PWA) on top of the engine in the browser (F8 brought local
  matches without a server and `gamehub web export`): a manifest, a service worker and replays.
- **A theme per game**: the kit is already painted with CSS variables; a game could bring its
  palette (felt, wood, seat colors) in its `ui` section.
- **Recording a match as a video or GIF** from the replay viewer, to share it.

## D. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Huge scope | Vertical slices; a playable MVP in Phase 4 (done: any game in the catalog can be played in the browser) and a design MVP in Phase 5; AI at the end |
| Expressiveness vs. analyzability | A pure, total core + pure native plugins as an escape hatch |
| Interpreter speed | Performance ladder: Python → C++ VM → codegen (and, since Phase 6, memoization and Python code generated from the IR) |
| The language changes a lot early on | The versioned IR is the stable boundary; automatic migrations |
| Text ↔ diagram round trip | Authoring IR + idempotence property tests |
| Hidden-information bugs | Opaque handles, leak analysis, view tests |
| Divergence between engines | Differential conformance suite with golden traces |
| An empty community at launch | A catalog of classics + full usefulness locally without a community |
| Malicious bots | Sandboxing with resource limits |
