# GameHub Studio — visual editor

> Status: **implemented** (Phase 5). Decisions: [ADR-052 to 059](decisions.md).

## 1. What it is

A local web application where a game is designed **as a diagram**, **as text** or both at once,
and tested in the same place. Both views are projections of the same syntax tree of the `.game`
file (the *authoring IR*): whatever is done in the diagram or in a form reaches the text changing
only what is needed —the rest keeps its formatting and comments— and whatever is written in the
text shows up in the diagram as soon as it is parsed.

```bash
cd python && uv run gamehub studio ../games --open     # or a file: …/games/dudo/dudo.game
```

`gamehub studio [PATH]` opens a local server (port 7421; `--port 0` for a free one) with the app,
the workspace API and, over WebSocket, the Nomos language server and the simulator. The link it
prints carries a token; without it, the Studio cannot be used (§9).

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ GameHub Studio  dudo/dudo.game ●  ✓ Compiles  1 warning  [Diagram|Diagram and text|Text]│
│                                   ↶ ↷  Re-layout  SVG  PNG  ▶ Simulate  Save  EN ◐     │
├──────────────┬───────────────────────────────┬─────────────────────┬─────────────────┤
│ GAMES        │ 👤 decision 👥 … 🎲 chance 🏁 end│ 1 // SPDX…           │ GAME Dudo       │
│ dudo/dudo    │      ●                          │ 2 import std.dice…   │ Title (en) …    │
│ tictactoe/…  │   ┌───────────────┐             │ …                    │ Players 2..4    │
│ NODES        │   │ 🎲 CHANCE Roll │◄──────┐     │ 56 chance Roll {     │ State Options   │
│ Roll  chance │   └──────┬────────┘       │     │ …                    │ Types Functions │
│ Bid decision │   ┌──────▼──────┐  2.     │     │                      │ ui hints Tests  │
│ End terminal │   │ 👤 Bid       │─────────┘     │                      │ cup: per_player │
│              │   │ bid(q, f) ○──┘ 1. alive()==1 │                      │ …               │
│              │   │ dudo()    ○──────►🏁 End     │                      │                 │
├──────────────┴───────────────────────────────┴─────────────────────┴─────────────────┤
│ Problems (1) · Simulator · Batch runs · Tree · Analysis · Compare                       │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

## 2. The diagram

| Model element | How it looks |
|---|---|
| `decision`, `simultaneous`, `window`, `chance`, `auto`, `terminal` | One box per node with its icon, kind and color; inside, a summary (the actor, the window mode, the chance effects, the payoffs) |
| `phase` | A container with its nodes inside, its start mark and, if it can be left (`-> exit`), its exit mark; it **collapses** (it becomes one more box and the arrows are rerouted to it) |
| Action | A row of the box; if it has its own transitions, their arrows leave from the row |
| Transition | An arrow with its condition; if a node has several, they carry their **order number** and the last one without a condition says "otherwise" |
| Start | A round mark with its arrow (the flow's and each phase's) |
| Status | Breakpoint, node error or warning, the simulator's active node, arrows of the last step, how many times each node, action or arrow was visited (coverage), added/changed/removed when comparing |

The layout is computed with **ELK** (layered, top to bottom; cycles are broken by the order in the
text, so the flow starts at the top) and then whatever the user moves takes over, stored in the
sibling file `<game>.layout.json`:

```json
{ "version": 1,
  "games": { "Dudo": { "direction": "DOWN", "collapsed": ["Round"],
                       "nodes": { "start": {"x": 0, "y": 0}, "Roll": {"x": 12, "y": 76}, "exit:Round": {"x": 40, "y": 300} } } } }
```

Being outside the `.game`, the layout changes neither the rules nor their hash. A new node is
placed near whoever points to it; "Re-layout" recomputes everything. If the canvas changes size
and nothing was moved by hand, it is re-fitted; the selection is brought into view.

## 3. Designing

- **Palette**: drag a node kind onto the diagram (inside a phase if dropped on it) or click it to
  add it at the end (or inside the selected phase). With a narrow column only the icons remain.
- **Arrows**: dragging from the output of a node or an action to another node creates a
  transition; dragging its tip to another node reconnects it; selecting it and pressing Delete (or
  Backspace) removes it. Dragging a node into or out of a phase moves it there (if it was the
  start, the phase becomes the start). Each node's context menu: breakpoint, show in the text,
  delete.
- **Inspector**, the form for the selection:
  - *Game*: title (es/en), version, players; tabs for **state** (type, initial value and
    visibility: everyone, nobody, the owner or a condition), **options**, **types** (enums and
    structs), **functions**, **ui hints** and **tests and invariants** (with "Run the tests",
    which also checks the invariants on 100 random matches).
  - *Node*: name (renames across the whole file), kind, documentation, members (actor, actors,
    eligible, mode, order, payoffs, rank), blocks (`on_enter`, `on_exit`, `resolve`, effects),
    terminals' `let`s, a phase's start, actions and transitions.
  - *Action*: name, parameters (one per line: `c in cells(board)`,
    `@visible(owner) card: Card in hand[actor]`), condition, effects, visibility and its
    transitions. *Transition*: target, condition, effects and order.
  - Nomos fields are small editors with highlighting and completion of the game's names; they are
    committed on blur (or with Enter / Ctrl+Enter) and, if the server rejects what was written,
    the error is marked at the exact spot in the field.
- **Component designer**: decks (the French one from `std.cards` or a custom suits × ranks one),
  grid and graph boards (squares and connections) and dice (with the chance node that rolls them
  and where it goes next); it generates Nomos and inserts it.
- **New game** from a template (empty, race, board, cards, dice, 2×2 matrix; the same as
  `gamehub new --template`).
- Undo and redo (the text editor's: a diagram change is one more step), save (Ctrl/Cmd+S; if the
  file changed on disk since it was opened, it warns before overwriting it) and automatic reload
  if another editor changes it and there are no changes here.

## 4. Text ↔ diagram

- **From the diagram to the text.** Each gesture is a list of **operations** (`addNode`,
  `addTransition`, `updateAction`, `setMember`, `moveNode`, `addTest`… about 45, in
  `gamehub.studio.edits`) that the server applies to a copy of the tree. The text is rewritten only
  where it changed: unchanged elements keep their text as is (with their formatting and comments)
  and new or changed ones are written with the formatter, at their indentation. The result is
  always checked by parsing it again (same tree, same comments); if the partial rewrite cannot
  cope, the whole file is formatted, which also preserves them. The editor receives the minimal
  changes (in UTF-16) and applies them as one more edit.
- **Renaming** does not go through the tree: it changes each occurrence according to the checker's
  symbol index; if it would clash with another name or the game would stop compiling, it is
  rejected.
- **From the text to the diagram.** Each text change is parsed (in a thread, 150 ms after the last
  one; those coming from the diagram, immediately) and the document model arrives: what the
  diagram and the forms draw, with the text of each expression and its position. With broken
  text, the diagram keeps showing the last model (without allowing edits) until it is fixed.
- **Synchronized selection**: what is selected in the diagram is highlighted in the text and,
  when the cursor moves in the text, whatever is under it is selected in the diagram.
- Guarantees through **property tests** (Hypothesis) over every game in the catalog: random edits
  leave valid text and preserve comments, and renaming every symbol there and back leaves the file
  unchanged. From the click on the palette to the drawn node: about 70 ms.

## 5. Verifying

- Live **problems** (compiler errors and warnings, with their help); clicking one points to it in
  the diagram and in the text. The worst one of each node is marked on its box.
- **Classification** of the game (perfect information, chance, simultaneous, zero-sum…) and the
  **estimated size** of the tree (Knuth's estimator over random walks, the same as the feasibility
  advisor's since F7).
- The game's **tests and invariants**, from the inspector (see §3).

## 6. Simulating and debugging

- **Play** as any seat, with the generic UI from Phase 4: each seat can be human, random or "first
  legal move".
- **Side-by-side views** of the chosen seats and an **omniscient view**: who sees what can be
  checked at a glance.
- **Step by step and time travel**: the whole history is kept (states are immutable); going back
  to a step and playing something else truncates it. **Chance**: drawn at random or picked from
  the list of outcomes with their probability.
- **Run** with the automatic players to the end, until a human's turn or until a **breakpoint**:
  reaching a node (from the diagram or the inspector) or a condition written in Nomos
  (`quantity >= 3`), checked as it is typed.
- **Reload** the rules after editing the game, replaying the history while it stays legal.
- In the diagram, the **active node** and the **arrows of the last step**.
- **Batch runs**: hundreds of random matches with statistics (finished, cut off, rule errors with
  their match, length, wins and draws, average payoff per seat) and **coverage** on the diagram:
  how many times each node, action and arrow was visited (in red, what was never used). Since
  F8 they run **in the browser** with the C++ core in WebAssembly (the same matches and numbers
  as the server, ≈ 25,000 tic-tac-toe matches per second; the panel says so), falling back to the
  server's `gamehub/sim.playouts` when the engine cannot load.
- The game's **tree** from the current step (small games): open branches and count states,
  terminals and depth (with a 5 s limit).

## 7. Analyzing (game theory, F7)

The **Analysis** tab runs [game theory](game-theory.md) on the text being edited (the same report
as `gamehub analyze`, through `gamehub/analyze`):

- **Analyze**: the feasibility advisor (classification, Knuth's estimate, exact counts if the game
  is small) and whatever it recommends that takes seconds; each recommendation has a button, and
  those that need a later phase say which one.
- One button per analysis: feasibility, **solve** (value, optimal moves, an optimal game,
  positions and games), **normal form and Nash** (the payoff matrix with best responses underlined
  and pure equilibria boxed, mixed equilibria, dominance, correlated equilibrium, Pareto, price of
  anarchy), **sequence form** (exact equilibrium of two-player zero-sum games), **CFR+** (with
  its convergence chart and the strategy of each information set as bars), **Grundy**,
  **cooperative** (characteristic function, Shapley, core, nucleolus, Nash bargaining) and the
  **Axelrod tournament** (ranking and ecological simulation). Iterations and rounds can be chosen.
- Results accumulate per game; an analysis that does not apply shows its reason without hiding the
  rest. Before building a large tree, a quick estimate refuses what would not fit.

## 8. Comparing and exporting

- **Compare** with a git version of the file or with another file: added, changed and removed
  nodes and arrows are colored on the diagram (the removed ones, as ghosts).
- **Export** the diagram to **SVG** (real rectangles, arrows and text) or **PNG**.

## 9. Inside

| Part | Where | What it does |
|---|---|---|
| Server | `gamehub.studio.server` | Starlette: the app, the API (`/api/workspace`, `/api/file`, `/api/layout`, `/api/new`, `/api/git/log`, `/api/git/show`) and the `/lsp` WebSocket |
| Session | `gamehub.studio.session` | Per connection: the language server (pygls) plus `gamehub/analysis` (a notification after each analysis), `gamehub/edit`, `gamehub/modelOf`, `gamehub/tests`, `gamehub/sim.*` and `gamehub/analyze` (F7) |
| Edits | `gamehub.studio.edits` | Operations on the tree, the minimal rewrite and its check; renaming |
| Model | `gamehub.studio.model` | The document model (positions in UTF-16) |
| Simulator | `gamehub.studio.sim` | History, running, breakpoints, batch runs with coverage, tree, size (the advisor's Knuth estimator) |
| Analysis | `gamehub.analysis.report` | The game-theory report of the "Analysis" tab |
| Language | `gamehub.lsp` | Diagnostics, completion, hover, definition, references, rename, formatting… (also `gamehub lsp` over standard input, for any editor) |
| Web | `@gamehub/nomos`, `@gamehub/studio`, `web/apps/studio` | Nomos for CodeMirror; the app as a React library (connection, state, diagram, editors, inspector, simulator, tools); the app served by `gamehub studio` |

In the browser: **React Flow** (canvas) + **ELK** (layout, loaded separately the first time) +
**CodeMirror 6** with its LSP client (the editor and the fields). The Python wheel ships the built
app (`gamehub/studioapp`); in development, `pnpm dev:studio` with `gamehub studio` behind it.

## 10. Security

The Studio reads and writes files: by default it only listens on this machine (127.0.0.1),
requires a **random token** (it travels in the link; the app keeps it in a cookie for this origin
only, or in the `x-gamehub-token` header), checks the **Host** header (against DNS rebinding) and
the **Origin** of WebSockets, and only opens and saves `.game` files inside the working directory.
With `--host` reachable from outside the machine, it warns that anyone with the link can edit.

## 11. Limits and next steps

- No real-time **collaborative editing** (CRDT): one file, one tab.
- Conditions and effects are written in Nomos (with completion); **Scratch-like blocks** for
  non-programmers are left for later ([question 6](open-questions.md)).
- Moving an action from one node to another by dragging it is not supported: it is done in the
  text.
- The VS Code extension still uses `gamehub check`/`fmt`; moving it to the LSP (`gamehub lsp`)
  requires bundling an LSP client in it.
- The Studio needs the local server to compile Nomos, simulate and analyze; its playouts already
  run in the browser with the WASM core (F8, ADR-082). Running entirely without it (on the hub,
  without Python) needs a compiler in the browser and comes with the hub (F10).
