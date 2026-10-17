# Work log

A chronological record of what is done in the project. The most recent entry goes on top.
Format: date · what was done · decisions · pending / next steps.

---

## 2026-10-17 — F6 acceptance: the last random matches

**Request**: "it is taking a long time (3 h), you could commit as you go": each result is committed
as soon as it is in, instead of waiting for all of them.

**Results so far** (`gamehub fuzz`, 0 errors and 0 truncated in every run)
- Solitaire, draw one: 50,000 matches in 15,852 s (3/s with 6 processes), 1,001 steps on average
  (with random agents almost every game reaches the 1,000-move cap), average score +6.9 cards on
  the foundations.
- Texas Hold'em, 16,667 matches each (2 processes, in parallel with Solitaire): 2 players in
  117 s (16.5 steps per hand on average), 3 players in 182 s (24.2), 4 players in 296 s (30.0),
  6 players in 451 s (39.6), 8 players in 688 s (47.4), 10 players in 1,115 s (54.6). Hold'em
  is done: 100,002 matches.

**Still running**: Solitaire with draw three and three passes (50,000; slower now: the machine is
shared with the F8 session's builds).

---

## 2026-10-17 — Global action ids brought forward to F8

**Question**: what GameHub and OpenSpiel share and what each can do that the other cannot. One
limit came up: `to_openspiel` numbers the actions by exploring the whole game, so OpenSpiel's
algorithms only reach small games (Kuhn, Leduc, tic-tac-toe), not chess or Hold'em.

**Decision (the user's)**: bring forward to F8 the **global action ids computed from the IR**:
each action's number follows from its parameters' types (e.g. chess: `play` 64 × 64 + `promote`
64 × 64 × 4 + `claim_draw` = 20,481 ids), with no exploration. It was part of F11's
tensorization; F11 reuses it. F8's acceptance adds OpenSpiel's MCTS and MCCFR on the wrapped
chess and Hold'em. The ADR will be written with the design, in F8.

**Progress**: ≈ 66 % (unchanged).

---

## 2026-10-17 — F7 approved and merged into `main`

**Answer received**: "I approve" to question 25: ADR-068 to 074 accepted (Connect Four 7×6 moves
to F8's acceptance) and `f7/teoria-de-juegos` merged into `main` with `--no-ff`. The branch
started from `docs/english`, so the English documentation (ADR-067) reaches `main` with it.
Nothing has been pushed.

**Still open**: question 24 (code comments, CLI messages and commit messages stay in Spanish
until it is answered). F6 acceptance: Solitaire's random matches are still running; their result
and Hold'em's will go to this log.

**Next steps**: F8, the C++ core, bindings and WASM (and Connect Four 7×6).

**Progress**: ≈ 66 % (F0 to F7 in `main`).

---

## 2026-10-17 — Session 10: Phase 7, game theory v1

**Request**: "go with the next step of the roadmap": F7. Worked on `f7/teoria-de-juegos`, which
starts from `docs/english` (the translation, committed by the previous session and still waiting
for approval), so merging F7 brings both.

**Done** (`gamehub.analysis`, everything on the reference engine and in exact arithmetic except CFR)
- **Representations** (ADR-068): the extensive form (`build_tree`) with the engine's information
  sets (perfect-recall keys computed incrementally, the same as `State.information_state`),
  simultaneous nodes played one seat after another, and chance outcomes that lead to the same state
  merged (Leduc: 74,251 nodes and its standard 288 information sets); the state graph
  (`state_graph`): tic-tac-toe has 5,478 positions, 958 terminals and 255,168 games.
- **Linear programming** (ADR-069): an exact two-phase simplex in rationals; HiGHS (`highspy`, the
  new `gamehub[analysis]` extra) for large programs.
- **Normal form and equilibria** (ADR-070): reduced pure strategies (Kuhn 27 × 64), pure
  equilibria, support enumeration, Lemke–Howson (lexicographic), zero-sum LP, iterated dominance
  (strict, weak, by mixed strategies), correlated equilibrium, Pareto, welfare, PoA/PoS.
- **Perfect information**: backward induction (SPE, n players, chance) and alpha-beta with a
  transposition table (expectimax at chance; depth limit with an evaluation function).
- **Imperfect information**: best response, NashConv and exploitability (OpenSpiel's convention),
  CFR and CFR+, and the exact **sequence form** for two-player constant-sum games.
- **CGT** (Grundy with the normal-play check, N/P and L/R/N/P classes), **cooperative games**
  (maximin characteristic function, Shapley, Banzhaf, core and least core, nucleolus, Nash
  bargaining) and **Axelrod tournaments** (11 classic strategies, noise, ecological simulation).
- **Feasibility advisor** (ADR-071): classification + Knuth's estimator (importance sampling at
  chance, merged outcomes, a time budget) + exact counts or a bounded probe + recommendations with
  stable codes. The Studio's size estimate (F5) now uses the same estimator.
- **Interoperability** (ADR-072): `gamehub export --to gambit-efg|gambit-nfg` and `to_openspiel`
  (the new `gamehub[openspiel]` extra).
- **`gamehub analyze`** (ADR-073): one JSON report for the CLI (text or `--json`), notebooks
  (`_repr_html_`: the matrix with best responses and equilibria, the tree, the tournament, the
  advisor) and the Studio's new **Analysis** tab (`gamehub/analyze`: the advisor with a button per
  recommendation, the matrix, equilibria, efficiency, strategies per information set as bars, CFR's
  convergence chart and the ecological simulation, with tooltips and a data table). Analyses that
  do not apply go to `errors`; a quick estimate refuses trees that would not fit. The `repeat`
  combinator tags its games `repeated` (and `best_of`, `best-of`).

**Acceptance** (reference results of game theory §6, `tests/test_analysis_reference.py`): ✅
tic-tac-toe a draw, 5,478 positions, 255,168 games; prisoner's dilemma (D, D) only, Pareto-dominated
by (C, C); rock-paper-scissors and matching pennies uniform with value 0; Kuhn −1/18 exact (sequence
form with exploitability 0, LP over the normal form; CFR+ < 10⁻⁴ in 1,000 iterations); Nim P ⇔
nim-sum 0 for every position with heaps ≤ 3, by search. **Connect Four 7×6 moves to F8**
(ADR-074): the engine solves ~1,600 states/s (5×4 took 7 minutes); checked on small boards against
an independent solver, and 4×4 is a draw (`slow` test).

**External checks**: pygambit 16.7 (built for Python 3.13: there are no 3.14 wheels) reads our Kuhn
`.efg` (27 × 64 strategies, 6 + 6 information sets) and its LP gives −1/18; its equilibria of the
2×2 games coincide with ours. With the wrapped Kuhn, OpenSpiel's `random_sim_test` passes, the
uniform policy's exploitability equals its native `kuhn_poker`'s (11/24), its CFR+ converges to
−1/18 and its alpha-beta gives tic-tac-toe as a draw. Leduc's sequence form with HiGHS gives
−0.0856, the literature's value. The Analysis tab was reviewed in the browser (dark and light).

**Bugs found on the way**: the first version of the advisor tried to enumerate whole decks while
probing (minutes for Skat); support enumeration and Lemke–Howson from every label on Kuhn's
27 × 64 matrix took 25 s (now bounded); tic-tac-toe's normal form ran for 5 minutes before failing
(now refused in half a second).

**Checks**: ruff, pyright, IR, conformance traces, natives, `gamehub fmt/check/test` of the games
and the stdlib, pytest (1,028 passed, 3 skipped, 7 long ones apart), the web's lint, types, 137
tests and build. Two timing-dependent web tests (Parchís played with the generic UI, a room against
a bot) timed out once while the machine was loaded (the F6 Solitaire fuzz, load average 34); they
pass when run again.

**Decisions**: ADR-068 to 074 (proposed). Question 25 opened.

**F6 acceptance, continued**: Solitaire's 50,000 random matches (draw one) are still running from
the previous session; Hold'em's go after them.

**Pending / next steps**: your approval (question 25, and question 24); then F8, the C++ core
(which also brings Connect Four 7×6).

**Progress**: ≈ 66 % (F0 to F7 complete; F7 waiting for approval).

---

## 2026-10-16 — Session 9: the documentation in English

**Request**: once F6 was finished, translate all the documentation into English: the project has
to be professional. Games may keep Spanish as optional information they ship (a platform that
uses the games as an API has to be translatable).

**Done** (branch `docs/english`)
- The whole wiki translated, with English page names: `architecture.md`, `decisions.md`,
  `engine.md`, `formal-model.md`, `game-catalog.md`, `game-theory.md`, `glossary.md`,
  `heuristics-and-ai.md`, `ideas.md`, `language.md`, `open-questions.md`, `protocol.md`,
  `structure-py-analysis.md`, `studio.md`, `web-client.md` (plus `README.md`, `hub.md`, `ir.md`,
  `roadmap.md` and `vision.md`). Links and anchors updated, also in code docstrings that pointed
  to the old pages.
- This log, the root `README.md`, `CLAUDE.md` (talk to the user in Spanish; everything written, in
  English), `LICENSING.md`, `games/LICENSE.md`, `spec/README.md`, `python/README.md`,
  `web/README.md`, the VS Code extension's README and manifest, and the custom UI template's
  README (and the seven UIs' READMEs generated from it; the template now takes the game's English
  title).
- ADR-067 (documentation in English; supersedes ADR-015) and question 24 (how far the switch goes:
  code comments, CLI messages, the default language of games and UIs, commit messages).
- Small fixes found while translating: the architecture's technology table still said "Lark"
  (the parser has been hand-written since F2, ADR-027); stale counts (15 → 22 catalog packages).

**F6 acceptance, continued**: Solitaire's 10⁵ random matches (50,000 with draw one, then 50,000
with draw three and three passes) are still running: with the 1,000-move cap almost every random
match goes the full length, about one match per second per process. Hold'em's (16,667 each with 2,
3, 4, 6, 8 and 10 players, under the new path `games/texas-holdem`) are queued after them.

**Waiting on you**: question 24 and approval to merge `docs/english` into `main`.

**Progress**: ≈ 59 % (the translation does not change the roadmap percentage).

---

## 2026-10-16 — F6 approved and merged into `main`

**Answer received**: "you have my approval" to question 23: ADR-060 to 066 accepted and F6 merged
into `main`. Nothing has been pushed.

**A note on the history**: the F6 commits were made directly on `main` by mistake (the branch was
never created). Since they had not been pushed, what was missing (the documentation) was done on
`f6/catalogo-ola-2` and merged with `--no-ff`; the earlier commits stay linear on `main`
(rewriting `main`'s history to move them was not worth it).

**Next steps**: translate all the documentation into English (the user's request: the project has
to be professional; Spanish remains as an optional translation each game ships); then, F7.

**Progress**: ≈ 59 % (F0 to F6 in `main`).

---

## 2026-10-16 — Session 8: Phase 6, catalog wave 2

**Answer received**: "go on with phase 6". New request: when F6 is finished, translate all the
documentation into English (games may keep shipping Spanish as an optional translation).

**Done (one commit per task)**
- **Engine** (`4503ab7`): memoization of IR functions according to what they depend on
  (*static*: forever; *state*: while the state does not change), integer shortcuts,
  `gamehub perft` and `gamehub fuzz --jobs` (ADR-060, 061). Long tests marked `slow`.
- FIDE **chess** and `std.boards` (`d469338`): legality with check and pin lines, the king in the
  state, castling, en passant, promotion, repetitions, 50/75 moves, insufficient material.
  *perft(5)* = 4,865,609 and those of Kiwipete and positions 3 to 6. *perft(3)* went from 52 s to
  1.2 s.
- **Wizard** and `std.tricktaking`, the Skat and Wizard decks in `std.cards` (`f22021a`, ADR-064).
- ISkO **Skat** (`cf590b1`): bidding, the skat, suit / Grand / Null, Hand, Schneider, Schwarz,
  Ouvert, matadors (hidden until the end: the leak analysis found a real one), overbidding; the
  ISkO examples as tests.
- **Native plugins** in WebAssembly (`f3f3235`, ADR-062): `@native("m.f")` with the body as the
  reference, ABI `gamehub-native/1`, `gamehub natives list|check|build`; `std.poker` with its
  evaluator written in WAT (0 differences from the reference), `std.betting` and no-limit **Texas
  Hold'em** with side pots.
- Spanish **Parchís** (`6d1fd6d`), also in pairs.
- **Generated code** (`958a431`, ADR-063): IR expressions are compiled to Python; ×2 in every game,
  with the same digest at every step as the closures.
- Klondike **Solitaire** (`2999017`), **custom UIs** for chess, Hold'em, Wizard and Parchís
  (`356225a`, reviewed in the browser) and `std.bidding` (`e2d6915`).
- Documentation: ADR-060 to 066, the catalog with wave 2 and analysis sheets, the wiki up to date
  (language, engine, IR, architecture, web client, glossary, roadmap), README and CLAUDE.md.

**Acceptance**: correct *perft(5)*; Skat verified against the ISkO; 10⁵ random matches without
errors of chess (100,000), Skat (50,000 with 3 and with 4), Wizard (25,000 with 3, 4, 5 and 6) and
Parchís (25,000 with 2, 3, 4 and in pairs); Solitaire's and Hold'em's were still running at merge
time (the Hold'em package was renamed to `texas-holdem` and they had to be relaunched); the 22
packages are played to the end with the generic UI against the server.

**Decisions**: ADR-060 to 066 (memoization, perft and fuzz in parallel, native plugins, generated
code, card libraries without generics, wave-2 rules, language adjustments). Questions 9 and 19
answered.

**Pending**: heuristic bots for the new games (F9); custom UIs for Skat and Solitaire.

---

## 2026-10-16 — F5 approved and merged into `main`

**Answer received**: "Yes" to question 22: ADR-052 to 059 accepted (among them **CodeMirror instead
of Monaco**, which changes ADR-012) and `f5/studio` merged into `main` with `--no-ff`. Nothing has
been pushed.

**Next steps**: F6, catalog wave 2 (the 7 requested games) and a mature standard library, on the
`f6/…` branch.

**Progress**: ≈ 51 % (F0 to F5 in `main`).

---

## 2026-10-12 — Session 7: Phase 5, the Studio

**Answers received**: "go on with phase 5", taken as approval of ADR-044 to 051 and of merging F4
(done, `d14ae62`; nothing has been pushed). F5 is worked on in the `f5/studio` branch.

**Done (one commit per task)**
- **Core** (`2cde02a`): the position of each name in the tree, the checker's **symbol index**
  (declarations, resolved uses and the type of each expression), a reference of the built-ins,
  loose fragments with located errors, the **edit engine** (~45 operations on the tree with a
  minimal rewrite of the text, checked by parsing again) and the **document model** for the diagram
  and the forms. Compiling for the editor skips the JSON Schema (it was 90 % of the time).
- **Language server** (`cff47a3`) with pygls: diagnostics, completion with half-written text,
  hover, definition, references, rename with clash checks, formatting, outline, folding,
  signatures and quick fixes; `gamehub lsp` over stdio and the same server over the Studio's
  WebSocket.
- **Studio server** (`8c4277e`): `gamehub studio` (workspace API, layout in `<game>.layout.json`,
  new games from templates, git history), security (local only, token, Host and Origin),
  **simulator** (history with time travel, running until breakpoints, reloading rules, batch runs
  with coverage thanks to the engine's transition trace, tree, counting, size with Knuth's
  estimator) and **templates** (`gamehub new --template`).
- **Tests and invariants in the Studio** and **acceptance** (`7e62df0`): operations to edit them
  and `gamehub/tests` to run them (without them, the empty template stopped compiling as soon as
  its action was touched); acceptance tests against the real server.
- **The web Studio** (`428b6f4`): `@gamehub/nomos` (Nomos for CodeMirror), `@gamehub/studio`
  (diagram with React Flow + ELK, editor and fields with CodeMirror and the LSP, inspector,
  component designer, simulator with the generic UI, batch runs, tree, compare, SVG and PNG
  export) and the app; unit tests, integration tests and tests of the whole app in jsdom.
- **Wheel and CI** (`16d9b6e`): the wheel ships the built Studio; CI builds both apps.
- **Acceptance**: tic-tac-toe is built from the empty template with 24 gestures in the diagram and
  the inspector, passes its tests, is played in the simulator and is the same game as the
  catalog's (same legal moves and payoffs in 40 random matches); Dudo is changed in the diagram (a
  new node, a reconnected arrow —one line of text—, reordered actions, the round put inside a
  phase) without losing a single comment, and what is written in the text, also broken and then
  fixed, reaches the diagram. Reviewed by hand in the built-in browser.
- **Bugs found and fixed while testing in the browser**: saving always reported a conflict (the
  file version was in nanoseconds, which does not fit exactly in a JavaScript number: now in
  microseconds); arrows covered the output handles and another one could not be dragged from a
  node that already had one; ELK put Dudo's bidding node above the start (it broke the cycle at
  the wrong arrow: now by text order); when switching views the diagram fell out of frame; a new
  node ended up out of view; more than 0.65 s passed from the click to the diagram (the editor
  waited half a second to sync the text and the server another 150 ms to parse it: now ~70 ms); in
  batch runs a draw counted as a win for both (69 % + 44 %); "Count" on the tree could take half a
  minute without any feedback (now with a limit and "Counting…"); the dice generator created a
  chance node without a transition; the language and theme selectors took the whole width; "1
  warnings"; node kinds appeared in Spanish with the interface in English; two copies of
  `@lezer/highlight`; the Studio's WebSocket rejected messages over 64 KB (a large `.game` when
  opening it).
- Docs: the [Studio](docs/wiki/studio.md) page rewritten (implemented), language §4 and §13
  (`gamehub studio`, `gamehub lsp`, templates), architecture, engine (trace), roadmap, licenses
  (elkjs is EPL-2.0), READMEs; ADR-052 to 059. Tests: 798 Python and 113 web.

**Decisions** (proposed): ADR-052 to 059; the most visible one, **CodeMirror instead of Monaco**
(ADR-054, it changes ADR-012): lighter and designed for dozens of fields with its LSP client.

**Limitations**: no collaborative editing; no Scratch-like blocks (question 6); moving an action
from one node to another is done in the text; the VS Code extension does not use the LSP yet; the
Studio needs the local server (without it, with F8's WASM and F10's hub). The built-in browser
panel was small: the desktop layout was checked by measuring the page and with screenshots at that
size, not full screen.

**Waiting on you**: review ADR-052 to 059 and approve merging `f5/studio` into `main` (question
22).

**Next**: F6, catalog wave 2 (the 7 requested games) and a mature standard library.

**Overall progress**: ≈ 51 %.

---

## 2026-10-11 — Phase 4 approved and merged

- "Go on with phase 5": ADR-044 to 051 and the merge are taken as approved. The `f4/cliente-web`
  branch is merged into `main` and Phase 5 (the Studio: a bidirectional visual editor with a
  simulator) starts on the `f5/studio` branch.
- Question 21 moved to answered.
- Overall progress: ≈ 41 %.

---

## 2026-10-11 — Session 6: Phase 4, playing in the browser

**Answers received**: approve ADR-036 to 043, merge F3 into `main` (done, `0607c1b`) and start F4
on the `f4/cliente-web` branch.

**Done (one commit per task)**
- **JavaScript monorepo** (ADR-044): a pnpm workspace at the root with `web/packages/*`,
  `web/apps/*` and `games/*/ui` (it started inside `web/`; it moved to the root because pnpm did
  not find it when working inside a UI in `games/`). Node 22, strict TypeScript 7, React 19,
  Vite 8, Biome and Vitest, with exact versions in a catalog; a new CI job.
- **`@gamehub/protocol`**: the TypeScript types come from the same generator as the Python ones
  (`gamehub protocol types` writes and checks both, ADR-045). In the schema, `Number`, `Event` and
  `Error` become `ExactNumber`, `GameEvent` and `ErrorInfo` (the wire does not change).
- **`@gamehub/client`**, the TypeScript SDK: connection with reconnection and `resume`, heartbeat,
  unique ids, resync if an update is missing, shutdown if another tab takes over the session;
  immutable state with a pure reducer; enumerated and progressive actions; sessions in
  localStorage; REST API. Tested against the real Python server (two clients, a dropped connection
  and a spectator).
- **Nomos's `ui { … }` section** (ADR-047): presentation hints with a target (variables, options,
  types, actions and their parameters, nodes, seats) and a closed catalog (how and where to draw,
  translated names, symbols, colors, cards, how to pick an argument), checked (E701–E704), with
  formatting, decompiler and merging in variants. In the IR, an optional `ui` key that does not
  count for the hash: the conformance traces do not change.
- **`@gamehub/ui-kit`** (accessible grid, SVG cards with French and Spanish suits, fanned hand,
  pile, deck, dice, tokens, track, graph, player, scoreboard, clock, action bar; CSS variables with
  light and dark themes) and **`@gamehub/i18n`** (es/en).
- **`@gamehub/auto-ui`, the generic UI** (ADR-048): the look of each variable comes from its type
  and its hints; how each argument is picked, from its domain (`cells(G)` → squares,
  `subsets(items(Z))` → mark cards) or from a hint; an action builder with the values given by
  the legal actions, computed once per update. An event log in sentences and the result. And
  **`@gamehub/react`** (hooks on top of the SDK).
- **The server serves the app** (ADR-046): `gamehub serve`/`host` (`--open`, `--no-web`); each
  room's link and QR code open the app; QR as SVG and state-by-state replays (`/frames?seat=`). The
  Python wheel ships the built app (tested by installing it in a clean environment).
- **The play app** (`@gamehub/shell` and `web/apps/play`): home (code, create room, open rooms,
  recent matches), create room (game options, clock, spectators, bots), room (player or
  spectator, session kept on reload, lobby with code, link and QR code, seats, bots, settings,
  ready, chat, rematch), match with the generic UI or a custom one, step-by-step replays from any
  perspective, **matches on a single device** with a privacy screen (ADR-049) and the kit gallery
  at `/kit`. Spanish and English, light or dark theme, phones.
- **`ui` hints in the 15 catalog packages** (es/en names, symbols, colors, cards, dice, Connect
  Four's column…).
- **Custom UIs** (ADR-050): `gamehub sdk ts` (a game's types, with Biome's formatting and
  `--check`) and `gamehub ui new` (a template that works on the first try: types, a starting
  board, a test, a development server with the app only for that game). With it, the UIs of
  **tic-tac-toe** (drawn marks, winning line), **Connect Four** (falling discs, highlighted column)
  and **Dudo** (the bid on the felt, the round's history, cups, the last challenge, a bid selector
  with dice); the app registers them by itself.
- **Acceptance**: the 15 catalog games are played to the end against the server only by clicking
  the generic UI (integration test, at random with a seed); **Ana in the app against Luis with
  `gamehub join` in a real terminal**, until the end; a room with the app against a bot, and
  spectator mode. Reviewed by hand in the built-in browser, also at phone size.
- **Bugs found and fixed**: the QR code came out broken (`svg_inline` has no `xmlns` and an
  `<img>` does not draw it); replay players came by position rather than by seat; the log printed
  double parentheses and what was revealed before the move; Bullshit took 170 s in the acceptance
  test (the builder recomputed thousands of subsets on every click: now 35 s); the server's
  catalog included the iterated PD's test game (now, its main file from each package); in jsdom,
  the simulated browser's WebSocket (undici) clashes with its `Event` class: the tests use `ws`.
- Docs: a new [web client](docs/wiki/web-client.md) page, language §12 (`ui`), IR, protocol,
  architecture, glossary, ideas, READMEs (the root one was still at Phase 1); ADR-044 to 051.
  Tests: 673 Python and 85 web (including the custom UIs').

**Decisions** (proposed): ADR-044 to 051.

**Limitations**: without an engine in the browser, local mode needs the server that serves the app
(until F8's WASM); there are no animations; "a custom UI in less than an hour" rests on the
template and the three example UIs, not on a measurement with another person; Windows is still
untested.

**Waiting on you**: review ADR-044 to 051 and approve merging `f4/cliente-web` into `main`
(question 21).

**Next**: F5, the Studio: a bidirectional visual editor (diagram ↔ text) with a simulator, the
**design MVP**.

**Overall progress**: ≈ 41 %.

---

## 2026-10-10 — Phase 3 approved and merged

- You approve ADR-036 to 043 and the merge: the `f3/servidor-partidas` branch is merged into
  `main` and Phase 4 (web client: TypeScript SDK, generic UI, UI kit, play app) starts on the
  `f4/cliente-web` branch.
- Question 18 moved to answered.
- Overall progress: ≈ 32 %.

---

## 2026-10-10 — Session 5: Phase 3, the match server and network play

**Answers received**: approve ADR-027 to 035, merge F2 into `main` (done, `a178967`) and start F3
on the `f3/servidor-partidas` branch.

**Done (one commit per task)**
- **Engine**: the view and events of a **spectator** (`PUBLIC`, holds no seat; a predicate that
  cannot be evaluated without a seat counts as false), **final place** (`ranking`, from the
  terminal's `rank` or from the payoffs), lazy legal actions and stateless decoding. **Provably
  fair chance** `gamehub-fair/1` (commitment, players' seeds, 53-bit seed, reveal) and
  `gamehub replay` checking it. The conformance traces do not change.
- **Protocol v1** in JSON Schema (`spec/protocol/v1`): 15 client messages, 11 server messages and
  the REST API; generated Python types (`gamehub protocol types`, in CI).
- **Match server** (Starlette + uvicorn + websockets, ADR-036): a **pure** room core, with no
  network or clock of its own (ADR-037), tested with a simulated clock. Rooms with a code, seats
  `open/reserved/human/bot`, host, settings; one update per input with `seq` without gaps and
  rejection by **current turn** (no spurious rejections in simultaneous nodes, ADR-038); enumerated
  or progressive actions; reconnection with token and `resume`; spectators with a public or
  omniscient view and a delay; server bots; `move`/`match` clocks with `on_timeout`; **forfeits**
  (last place and a bot finishes for the seat, ADR-041); rematch; aborting if the rules fail;
  limits (rate, sizes, rooms, connections) and cleanup of empty rooms.
- **Persistence** in SQLite: each step as it is played; after a crash, unfinished matches are
  closed as aborted with their verifiable replay. `gamehub serve`.
- **Python client SDK** (automatic reconnection, requests with replies) and **network bots with
  the same `Agent` interface** as in process (ADR-043); `gamehub bot run agent.py --room CODE`.
- **LAN play** (ADR-042): `gamehub host game` (code, `/r/CODE` link, QR code in the terminal,
  mDNS announcement), `gamehub join CODE|link` (it looks for the room on the LAN; it stores the
  session to go back after closing the terminal), `gamehub rooms`; a terminal client with a lobby,
  commands (`/listo`, `/chat`, `/bot`…), move menus, clocks, result and rematch.
- **Performance**: profiling Bullshit over the network, `to_json` dispatches on the exact type and
  action enumeration reuses each card's conversion (server ×3.7) and the client decodes actions
  only when the agent looks at them: a match of 3 bots from 52 s to ~5 s. **Load test**
  (`gamehub loadtest`): 100 simultaneous rooms, Dudo with 4 (400 connections) ≈ 890 moves/s and
  Nim ≈ 1,300/s, without failures.
- **Acceptance** with real processes on the local network (`tests/test_acceptance_f3.py`,
  `GAMEHUB_LAN_TESTS=1`): four `gamehub join`s acting as four computers play Dudo in a
  `gamehub host` room (two find it over mDNS, two through the link); one of them loses their
  terminal on their turn and comes back; in the rematch a bot joins by code. Five out of five.
- **Bugs found and fixed**: the client's message ids repeated across processes and the server
  discarded as retries the moves of whoever resumed the session from another terminal (found by
  the acceptance test); when resuming with nothing pending no update arrived and the client did
  not know it was its turn; a long name left `hello` unanswered; `gamehub host`'s output to a pipe
  stayed in the buffer; the tests wrote sessions in `~/.local/share/gamehub` (now, a temporary
  directory).
- Docs: `protocol.md` rewritten (v1 implemented, performance), `engine.md`, `architecture.md`,
  `heuristics-and-ai.md` (the `Agent` interface), glossary, ADR-036 to 043; 604 tests.

**Decisions** (proposed): ADR-036 to 043.

**Waiting on you**: review ADR-036 to 043 and approve merging `f3/servidor-partidas` into `main`
(question 18); new questions 19 (per-game `on_timeout`) and 20 (playing over the internet before
the hub).

**Next**: F4, the web client (a TypeScript SDK with types generated from the same schema, a generic
UI from the IR, UI kit, lobby): the **playable MVP**.

**Overall progress**: ≈ 32 %.

---

## 2026-10-10 — Phase 2 approved and merged

- You approve ADR-027 to 035 and the merge: the `f2/compilador-nomos` branch is merged into `main`
  and Phase 3 (match server and protocol) starts on the `f3/servidor-partidas` branch.
- Question 17 moved to answered. A count in the wiki corrected: there are 15 game packages with 16
  games (the iterated PD package also ships its test game).
- Overall progress: ≈ 24 %.

---

## 2026-10-09 — Session 4: Phase 2, the Nomos language and its tools

**Answers received**: merge F1 into `main` (done, `bc6b203`) and start F2 on the
`f2/compilador-nomos` branch.

**Done (one commit per task)**
- A hand-written Nomos parser (recursive descent + precedences) with error recovery, rustc-style
  diagnostics and comments kept as trivia.
- The canonical formatter `gamehub fmt` (idempotent, keeps comments); in CI and pre-commit.
- Type checker and translation to GameIR (`gamehub compile`, `gamehub check`); `play`, `fuzz` and
  `replay` accept `.game`. **The six F1 games written in Nomos (`games/`) compile to the same rules
  hash as their hand-written IR.**
- An IR → Nomos decompiler (`gamehub decompile`): an exact round trip on the 6 examples and on a
  "kitchen sink" game that uses every construct (`python/tests/fixtures/kitchen-sink.game`).
- Fixed a bug in the F1 validator: `at(Node)` in state visibility or in functions was reported as
  an unknown node.
- Formatter, second pass: long arithmetic chains fill lines and `and`/`or` chains go one per line;
  a value that does not fit after `=` moves to the next line, or opens next to the `=` if it starts
  with a bracket and does not fit there either; blank lines around comments are kept. A latent bug
  fixed: the formatter could break after `=`, `requires`, `when` or `key:` and the parser did not
  accept it. `fmt --diff` no longer writes. Stress test: every game, formatted at widths from 24 to
  80 columns, goes back to the same syntax tree.
- **`gamehub test`**: runs the `test` blocks (chance resolved with the test's seed, `chance where`
  conditioned on the probability, `play` with an implicit seat if only one can act, `expect`,
  `expect legal/illegal`, `set`) and checks the invariants in each state of the test and on random
  matches (`--playouts`, 20 by default). Failures are explained rustc-style with the values
  involved (`payoff == [1, -1]` is false: `payoff` is [2, -2]) and the legal moves. New errors:
  E601/E602 (test configuration) and E610–E614 (failures). Engine: `State.evaluate`,
  `State.edited` and `illegal_reason`. The games' 19 tests and 4 invariants pass; in CI.
- **`gamehub check` analyses** (the `gamehub.analysis` package, on the IR, so they also work for
  hand-written IR or the future visual editor): unreachable nodes (W401), transitions that may not
  cover every case (W402, it recognizes pairs `c`/`not c`, `a < b`/`a >= b` and complete enums),
  nodes without a path to an end (W403), loops of `auto` nodes without effects (W404),
  **information leaks v1** (W405: hidden data reaching public state or events, also through an
  `if`; who plays or which node follows depending on hidden data; legal moves that depend on what
  the actor cannot see), unused declarations (W406; uses in tests count) and shadowed transitions
  in hand-written IR (W407). Static **classification** (players, chance, information,
  simultaneity, zero-sum when it can be guaranteed). Warnings are placed in the text through a
  source map. The six games give no warnings; the kitchen sink gives the expected ones.
  `gamehub test` always plays the random matches and reports whether payoffs add up to a constant.
- **Modules and `import`** (`import a.b.{X, Y}`, `import a.b.*`): `std.…` in the standard library
  and the rest relative to the file; importing a name brings what it needs, and only what the game
  uses reaches the IR. Errors: module not found (E503), nonexistent name (E201, with a suggestion),
  circular import (E504), name clashes (E202). A file without games is a module and
  `gamehub check` checks it. Cells can be indexed (`c[0]` row, `c[1]` column).
- **Standard library v0** (`stdlib/std/`): `std.cards` (the French 52-card deck and the Spanish
  40/48-card deck, `rank_value`, `is_red`…), `std.dice` (faces, counts with wildcards,
  straights…), `std.grid` (directions, rays, distances) and `std.graph` (graphs as edge lists,
  cycles, neighbors). Tested with tests written in Nomos (`tests/fixtures/stdlib.game`).
- **Mods**: `game V extends Base { … }` (the base can be from the file, imported or a combinator)
  with new declarations, `override` (fn, types, nodes —also inside phases—, params, state; an
  `override params` with `assert`s replaces the constraints), `remove` and `extend node` (actions
  at the end, transitions before). Meta merged without `id`/`version`; tests and invariants are not
  inherited; the base does not change. Errors E505.
- **Combinators**: `game G = repeat(Base, rounds: n, payoff: sum|mean)` and
  `best_of(Base, rounds: n)`, as IR transformations (a round phase, terminals that record the
  result, a "Next" node, a final terminal; `rounds` becomes a parameter; new names without
  clashes). Errors E506. A combinator can be extended (it is decompiled), e.g. to add tests to it.
  Tested: iterated PD (9/9 cooperating, average 3 and 4/3), best of 3 (zero-sum), tic-tac-toe
  variants (misère, with a pass, 4×4).
- In an `import`, `prisoners_dilemma` also finds `prisoners-dilemma.game`.
- **Packages** (`gamehub.packages`): `game.toml` (name, version, main file, license, authors,
  `forked_from`, `[dependencies]` by `path` or `git` + `rev`), `game.lock` with the commit of each
  git dependency (also the transitive ones) and a cache in `~/.cache/gamehub/git`. `import`s look
  in `std`, then in the package's dependencies and then next to the file. Commands: `gamehub new`
  (a package with a minimal game that compiles and passes its test: a race to the finish line),
  `fetch [--update]`, `clone` and `fork` (it records `forked_from` with the commit and keeps the
  original remote as `upstream`). The six games in `games/` are now packages. Tested with local git
  repositories (no network).
- **`gamehub viz`** (Mermaid or Graphviz): each node with its shape according to its kind, who
  plays, its actions and the payoff; arrows with the action and the condition in Nomos; phases as
  subgraphs with entry and exit marks. Checked by rendering the diagrams with Mermaid in the
  browser.
- **`gamehub rules`**: a Markdown rulebook generated from the IR (classification, options,
  components, what is on the table and who sees it, the diagram, each node with its actions,
  conditions and effects in Nomos, definitions), in the requested language.
- **`gamehub diff A B`** or **`gamehub diff REV1..REV2 file`**: a semantic diff by element (not by
  line), as text or JSON, saying whether the rules or only the texts change.
- **VS Code extension** (`editors/vscode/nomos`, JavaScript without a build step): a TextMate
  grammar, language configuration, diagnostics from `gamehub check --format json` on open and save
  (also in imported modules) and formatting with `gamehub fmt --stdin` (new). A test checks that
  the grammar covers every reserved word and function of the language. Fixed: a game without a
  `flow` gave an error without a position (now a single one, on the game).
- **New games in Nomos**, each a package with tests (64 checks in total, all green, no warnings):
  - **Connect Four** (parameterizable board and line; invariant: discs do not float);
  - the **2×2 family**: the base `two-by-two` (two payoff tables as options) and the variants
    **stag hunt**, **chicken**, **matching pennies** and **battle of the sexes** with `extends`
    (`override enum` to rename the choices, `override params` for the payoffs);
  - the **iterated prisoner's dilemma** with `repeat(PrisonersDilemma, rounds: 10)` and a
    `tests.game` that extends it;
  - **Leduc poker** (two rounds, a raise limit, a community card);
  - **Dudo** for 2 to 4 players, using `std.dice`.
- Improvements that came out of writing them: the leak analysis understands `reveal … to all`;
  module functions have their own scope (their parameters may be named like things in the game);
  the parser's error recovery respects nested brackets (an error inside a text no longer closes the
  block and drags everything along); translatable texts accept line breaks between languages.

- **Documentation**: `language.md` rewritten as the Nomos v0.1 reference (lexical structure,
  modules and packages, types, visibility, expressions, effects and flow, tests, mods, tools,
  translation to the IR, diagnostics, formatting and differences from the RFC); ADR-027 to 035;
  status, architecture, IR, engine, glossary, catalog and open questions up to date.
- `spec/` and `stdlib/` travel inside the Python wheel: tested by installing it in an isolated
  environment, outside the repository (Dudo, which imports `std.dice`, compiles and passes its
  tests).

**Decisions (proposed, ADR-027 to 035)**: a hand-written parser instead of Lark; no local shadows
a global except in module functions; type-directed sugar with single-pass translation; tests and
invariants outside the IR; modules with pruning and resolution std → dependencies → relative; mods
on the model and combinators on the IR; packages with `game.toml` and `game.lock`; static analyses
on the IR; Prettier-style canonical formatting.

**Phase 2 acceptance** ✅
- The 16 wave-1 games are in `.game` and pass their tests: `gamehub test ../games` gives 64 green
  checks (tests, invariants and random matches) and `gamehub check`, no warnings. The 6 F1 games
  compile to the same rules hash as their hand-written IR.
- `fmt` idempotent and stable at any width (every game, from 24 to 100 columns).
- `text → IR → text` stable: an exact round trip with the decompiler.
- `viz`: one box per node and one arrow per transition in every game (test).
- 500 Python tests; `ruff`, `pyright`, `gamehub ir check` and the conformance traces green.

**Waiting on you**: review ADR-027 to 035 and approve merging `f2/compilador-nomos` into `main`
(question 17); Bullshit variants (9b).

**Next steps**: Phase 3, the match server (rooms with a code, a WebSocket + JSON protocol with JSON
Schema, per-seat projection, reconnection, LAN) to play over the network from the terminal.

**Progress:** ≈ 24 % (F0, F1 and F2 complete).

---

## 2026-10-09 — Session 3: Phase 1, the reference engine in Python

**Answers received**
- Commits: one per task. → Phase 0 on `main` (3 commits); Phase 1 on the `f1/motor-referencia`
  branch (one commit per task), to be merged with the user's approval (ADR-026).
- Start Phase 1: yes. The proposed ADRs are considered accepted (no objections).

**What was done**
- `gamehub.ir.hashing`: the rules hash (canonical JSON + SHA-256), insensitive to `meta`, `doc`
  and default values (ADR-025). Validation: `pass` reserved in windows, no per-action transitions
  in simultaneous nodes, phases left with `$exit` have transitions.
- **Reference engine** (`gamehub.engine`):
  - immutable values with a canonical order; types; JSON;
  - **PCG32** identical to the reference C implementation (test vector verified), reproducible
    draws and **exact enumeration** of chance outcomes (ADR-022);
  - the catalog's 87 operators and 14 statements, compiled into functions;
  - flow semantics: decisions, simultaneous nodes, windows (priority/collect/race), chance, phases
    with `on_enter`/`on_exit`/`$exit` (ADR-024), advancing to quiescence without recursion;
  - visibility: redacted views, events resolved per seat, information states with perfect recall
    (verified: in Kuhn, seat 1 cannot tell KQ from JQ);
  - legal actions, canonical form and progressive building (`options`);
  - state snapshot and digest; `.ghr.json` replays verified step by step.
- Drivers: `play_match`, `RandomAgent`, `fuzz`; **golden traces** in `spec/conformance` (6 games).
- **Builder API** (`gamehub.build`): three games rebuilt with it give the same rules hash as their
  hand-written JSON.
- **CLI**: `gamehub play` (hot-seat and bots, a player-change screen), `fuzz`, `replay`,
  `conformance`.
- New games: **rock-paper-scissors** and **Nim** (with a misère variant).
- Docs: `docs/wiki/engine.md` (exact operational semantics), ADR-022 to 026, roadmap,
  architecture, glossary, README.
- 132 tests; `ruff` and `pyright` clean.
- Profiling Bullshit: half the time went into deduplicating subsets that were already distinct;
  fixed (×1.8) without changing the conformance traces.

**Phase 1 acceptance**

| Game | Random matches | Errors | Matches/s | Check |
|---|---:|---:|---:|---|
| Tic-tac-toe | 100,000 | 0 | 1,579 | X's average payoff +0.294 (theoretical +0.297) |
| Prisoner's dilemma | 100,000 | 0 | 11,972 | Average payoff 2.249 (exactly 9/4) |
| Rock-paper-scissors | 100,000 | 0 | 11,790 | Average payoff −0.003 (exactly 0) |
| Nim (3, 5, 7) | 100,000 | 0 | 2,805 | — |
| Kuhn poker | 100,000 | 0 | 4,600 | Average payoff +0.133 (exactly 1/8) |
| Bullshit (3 players) | 1,000 | 0 | 0.4 (≈ 0.9 after optimizing) | 391 steps on average; wins 31.6 / 32.2 / 36.2 % per seat: seat 0 gets 18 cards and the others 17 |

Also: the exact value of the random game computed over the full tree (Kuhn = 1/8, dilemma = 9/4,
RPS = 0); replays identical bit for bit; views without leaks; a full match playable in the
terminal.

**Decisions**: ADR-022 (PCG32), 023 (no pydantic), 024 (order of `$exit`), 025 (hash), 026
(branches).

**Pending / next steps**
- From the user: merge `f1/motor-referencia` into `main`; Bullshit variants (question 9b).
- F2: the Nomos compiler (`.game` → IR) with types, formatter, stdlib v0 and packages.

**Progress:** ≈ 13 % (F0 and F1 complete).

---

## 2026-10-09 — Session 2: the user's answers and Phase 0 completed

**Answers received**
- Cut-off message ("I also want to have a…"): the user does not remember it → question closed.
- Proposed licenses: accepted (ADR-016).
- Mentiroso = *Bullshit*: cards face down with a *claim* ("3 fours"); if you are called and it was
  a lie, you take the pile; if it was true, the caller takes it.
- The name **Nomos** and English keywords: accepted (ADR-017, ADR-018).
- Initialize git and start Phase 0: yes.

**What was done**
- `git init -b main` (no commits: commit policy pending). `.gitignore`, `.editorconfig`,
  `LICENSE` (the canonical Apache-2.0 text, md5 verified), `LICENSING.md`.
- **Core IR v0.1 specification** in `spec/ir/v0/`:
  - `ops.json`: a catalog of 87 expressions, 14 statements and 6 selectors (arity, argument types,
    randomness, documentation). The single source of truth (ADR-020).
  - `ir.schema.json`, `common.schema.json`, `type.schema.json` (by hand) and `expr.schema.json`,
    `stmt.schema.json` (generated from the catalog).
- **Validation games** in `spec/ir/examples/`: tic-tac-toe, prisoner's dilemma (with the
  constraints T > R > P > S), Kuhn poker and **Bullshit** (brought forward from wave 2).
- **The `gamehub` Python package** (`python/`, managed with `uv`): validation by JSON Schema + a
  well-formedness checker (references, contexts, confined chance, no recursion, node exits), the
  `gamehub ir check` and `gamehub ir schemas --check|--write` CLI.
- 35 tests (20 deliberate error cases); `ruff`, `pyright` (0 errors) and formatting green.
- GitHub Actions CI and local `pre-commit` hooks.
- An improvement to the information model (ADR-019): opaque *handles* are discarded (they leaked
  which card an opponent played) in favor of ordered zones with public positions and unordered
  **bags**; hidden components expose no identity; `reveal` is an event.
- Wiki updated: questions, decisions (ADR-016 to 021), formal model, Nomos (full Bullshit), IR
  (validation), protocol, catalog, roadmap, glossary, architecture, status.

**Decisions**
- Accepted: ADR-016 (licenses), 017 (Nomos), 018 (syntax).
- Proposed and implemented: ADR-019 (visibility), 020 (catalog), 021 (authoring IR in F2).

**Pending / next steps**
- From the user: commit policy, Bullshit variants (question 9b), approval of the ADRs.
- F1: an IR interpreter in Python (expressions, effects, flow, seeded chance, redacted views,
  replays) until the 4 IRs can be played in the terminal.

**Progress:** ≈ 4 % (F0: 9/9).

---

## 2026-10-09 — Session 1: brainstorming, design and roadmap

**Starting point**
- The repository only contained `structure.py` (the May 2026 prototype: a `GameState` singleton,
  `Node`, `Action`, `Flowchart`, per-variable permissions). No git.

**What was done**
- Analysis of `structure.py`: intuitions that are kept, 6 bugs that prevent running it and 7
  design problems → [`docs/wiki/structure-py-analysis.md`](docs/wiki/structure-py-analysis.md).
- Full brainstorming: 17 gaps in the original idea, 27 improvements, future ideas and risks →
  [`ideas.md`](docs/wiki/ideas.md).
- Design (v0.1 drafts):
  - [Vision](docs/wiki/vision.md): principles, non-goals, positioning against OpenSpiel, Ludii,
    GDL, Gambit, boardgame.io, BGA, PettingZoo.
  - [Formal model](docs/wiki/formal-model.md): extensive form + FOSG + statecharts; 8 node kinds;
    actions with domains; explicit chance; visibility per location with opaque handles;
    simultaneity, reaction windows and races; time; history; derived properties.
  - [The `.game` language](docs/wiki/language.md): syntax with examples (tic-tac-toe, prisoner's
    dilemma, Kuhn, a Bullshit fragment), modules, mods with `extends`, combinators.
  - [GameIR](docs/wiki/ir.md): authoring vs. resolved IR, S-expressions in JSON, rules hash and
    interface hash, layout in a sidecar.
  - [Architecture](docs/wiki/architecture.md), [protocol](docs/wiki/protocol.md),
    [Studio](docs/wiki/studio.md), [hub](docs/wiki/hub.md),
    [game theory](docs/wiki/game-theory.md),
    [heuristics and AI](docs/wiki/heuristics-and-ai.md), [catalog](docs/wiki/game-catalog.md).
- A [roadmap](docs/wiki/roadmap.md) in 13 phases (F0–F12) with weights, deliverables, acceptance
  criteria and dependencies. Playable MVP at 41 %, design MVP at 51 %, AI at the end.
- A [decision record](docs/wiki/decisions.md) (16 ADRs) and
  [open questions](docs/wiki/open-questions.md) (15, two of them blocking).
- The root `README.md`, the wiki index with the status, `CLAUDE.md` with the maintenance rules.

**Decisions**
- Accepted (by the user): Python 3 + C++; the `.game` extension.
- Proposed (waiting for approval): ADR 001–012 and 015 (canonical IR, pure expressions, explicit
  chance, immutable states, declarative visibility, statecharts, Python first, git as the backend,
  WebSocket+JSON, interoperability, monorepo, TS+React).

**Pending / next steps**
- Answers to the 🔴 questions (message cut off at "I also want to have a…", license).
- Close F0: `git init`, monorepo and tools, the IR's JSON Schema, 3 validation IRs.

**Progress:** ≈ 0.5 % (F0: 1/8).
