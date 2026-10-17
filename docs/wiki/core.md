# The C++ core

> Status: **implemented** (Phase 8, 2026-10-17) in [`core/`](../../core). A second engine with
> exactly the semantics of the [reference engine](engine.md) —the golden
> [conformance traces](../../spec/conformance) and a differential suite of more than ten million
> random matches agree step by step— and 50–60 times faster. Decisions: ADR-075 to 080 in
> [decisions](decisions.md).

## 1. Usage

```python
from gamehub.engine.core import CoreGame, core_game     # pip install 'gamehub[core]'
game = core_game(load_nomos(Path("games/chess/chess.game")))   # or CoreGame(ir)
state = game.new_state(2)
state = state.apply_action(0, state.legal_actions(0)[0])        # the reference API
state.digest() == reference_state.digest()                       # same snapshots, views, events
```

`CoreGame` and `CoreState` have the methods of `Game` and `State` with the same Python values
(`Action`, `EnumValue`, `Fraction`…), so the drivers (`play_match`, `fuzz`, `record`, `replay`)
take either engine. `CoreState.evaluate` compiles an IR expression on the fly; `edited` (the
`set` of Nomos tests) only exists in the reference engine. The module underneath,
`gamehub_core`, speaks JSON (dicts, lists, ints, strings) and holds the algorithms.

```bash
gamehub bench GAME --games 500 --cpp-games 100000   # matches/s, both engines, same matches
gamehub fuzz GAME --engine cpp --jobs 8             # the same matches as fuzz, in C++ threads
gamehub differential GAME --games 100000 --jobs 6   # C++ against the reference, step by step
gamehub perft ../games/chess --depth 5 --engine cpp # 4,865,609 in 18 s
gamehub analyze GAME --solve|--retrograde --engine cpp
gamehub conformance --check                          # the golden traces, with both engines
```

Development: `uv sync` in `python/` builds `gamehub-core` (scikit-build-core + nanobind, without
build isolation) in editable mode; importing it after a change to the C++ rebuilds it
incrementally. `cmake -S core -B core/build-prof -DGAMEHUB_CORE_TOOLS=ON` builds
`gamehub_bench`, which plays random matches of an `.ir.json` without Python (for profiling).

## 2. Values (ADR-076)

A `Value` is 16 bytes: a tag and a payload. The none option, booleans, integers (and seats),
enum values and cells live inline; rationals, texts and containers (tuples, structs, sets, maps,
zones, grids) are **immutable objects with a reference count** (not atomic: a state belongs to
one thread). Writing into a container that is shared with another state copies it first
(**copy-on-write**); one that is already unique is modified in place, so a transaction copies
each container it touches at most once. Sets, bags and maps keep the canonical order, and the
canonical order, equality, JSON and digests are those of Python (an inline cell is the tuple of
its two integers in every respect).

- **Exact arithmetic in 64 bits.** Integers are `int64` and rationals `int64/int64`, normalized.
  A result that does not fit is a `RuleError` ("desbordamiento"), never a different value. This
  replaces the "`double` in the C++ core" default of question 13: traces must be identical.
- **A memory arena.** Containers, states, stores and pending submissions come from per-thread
  free lists by size (`PoolAllocator`); the system allocator, which on this macOS stamps the time
  of every `free`, was 30 % of the time in Kuhn.
- **Automatic Zobrist hashing.** Every container caches **two independent structural hashes**
  (positional XOR of its elements' hashes); writing one position updates the first in O(1) and
  invalidates the second. A state's 128-bit key (`state_key`) combines the node, the pending
  submissions, the payoffs and the store: the transposition tables use it.
- **Undo for search.** States are persistent: `apply_action` returns a new state that shares
  everything unchanged with its parent, so going back is keeping the previous state. Searches use
  `ApplyOptions{events=false, history=false, validate=false}` (no events, no parent link, no
  legality check for actions taken from `legal_actions` of the same state).

## 3. The VM (ADR-077)

**Expressions** compile to a stack bytecode, one chunk per site; arguments and locals (`let`,
comprehension and `for` variables) are frame **slots** resolved lexically at load time. The 87
operators reproduce `gamehub.engine.expr` result by result and error by error (a test evaluates
some 150 expressions, wrong ones included, in both engines). **Statements** are trees of C++
nodes whose expressions are bytecode, with the flow of `_Tx`: phases with `on_enter`/`on_exit`
and `$exit`, transitions by groups, decisions, simultaneous nodes, windows, chance, terminals,
the 10,000-arrival limit and the "no legal action" check on arrival.

Optimizations, none of which changes a result:

| Technique | Effect |
|---|---|
| Direct threading (computed goto), stack and instruction pointers in registers | the dispatch |
| Rotated comprehension loops; the step fused with the loop (`ALL_LOOP`, `FILTER_LOOP`…); the first element fused with the initialization, reading a local collection from its slot | Connect Four: 1,056 → 592 instructions per step (tic-tac-toe: 213 → 139) |
| Superinstructions fused at emission when no jump target lies between: `index(var, local)`, `== local`, `== constant` | |
| `cells(g)` and `lines(g, k)` cached by the grid's dimensions | the 69 lines of Connect Four built once |
| Function memo as in Python (`static` for every match, `state` while the store does not change), cleared in O(1) by generation and **adaptive**: a `state` function that hits less than once in 16 lookups stops being memoized | |
| Legal actions enumerated in one frame per action; one-argument actions without an allocation; chance sampled and applied in a single execution | |
| Node paths precomputed; transactions without `shared_ptr` copies | |

## 4. Conformance (ADR-078)

- **Golden traces:** `gamehub conformance --check` replays the 16 traces of
  `spec/conformance` with the reference engine and with the C++ one (bit for bit: the same
  digest after every step).
- **Differential suite:** `gamehub differential` plays each match in both engines at once with
  the same random agents (the seeds of `fuzz`) and compares, at every step, the digest, the
  status, the active seats, the payoffs, the chance outcome drawn from the same generator and the
  legal actions (count and the one chosen); one match in `--deep-every` also compares every
  legal action, the views and events of every seat, of a spectator and the omniscient ones, the
  enumerated chance outcomes with their probabilities and the ranking. A `RuleError` must happen
  in the same step in both engines.
- **The acceptance sweep** (2026-10-17): every catalog game, ≥ 10 million matches in total (a
  million of each 2×2 game and of Kuhn, half a million of Nim and tic-tac-toe, … two thousand of
  chess), **0 differences**. `tests/test_core.py` runs a smaller version in the normal suite.

## 5. Performance

Random matches per second, one thread, the same matches in both engines (`gamehub bench`, Apple
M1, 2026-10-17):

| Game | Reference engine | C++ core | Speed-up |
|---|---:|---:|---:|
| Tic-tac-toe | 2,438 | 140,758 | ×57.7 |
| Connect Four (7×6) | 338 | 19,209 | ×56.8 |
| Kuhn poker | 5,495 | 347,504 | ×63.2 |

Chess *perft(5)* (4,865,609 positions): 18 s on one thread (the reference engine needed 131 s on
six processes). Leduc, 100 iterations of CFR+ including building its 74,251-node tree: 2.1 s
(15.9 s in Python).

## 6. Global action ids and `@range` (ADR-079)

`gamehub.analysis.action_space` numbers every possible action of a match (players and
parameters fixed) **from the IR, without exploring the game**:

- Actions are grouped into **blocks**, one per distinct signature (name and the universes of its
  parameters) in flow order; `pass` of windows is one more block.
- Inside a block the number is the **mixed radix** of its arguments' ranks in finite
  **universes**: `Bool`, enums (or the values the domain lists: chess promotes to 4 of 6 kinds),
  seats, cells (the largest grid of the state), structs and tuples (products), options,
  bounded integers and **subsets** (by size, then the combinatorial number of the chosen ranks).
- Integers are bounded by an **interval abstract interpretation** of their domain: constants, the
  match's parameters, the number of players, IR functions and the state variables, whose bounds
  come from a fixpoint over all their assignments (with widening) or from their **declared
  range**.

Chess has 20,481 ids (`play` 64·64 + `promote` 64·64·4 + `claim_draw`), two-player Hold'em
1,205, Wizard 85; all 21 catalog games have an action space and the C++ encoding
(`gamehub_core.ActionSpace`) agrees with Python's on every legal action of random matches.

**`@range(lo..hi)`** on a state variable (Nomos; `"range": [lo, hi]` in the IR) declares the
range of its numbers (the Int, Seat or Real leaves of per_player, lists, sets, grids and options),
with expressions of parameters and constants. Both engines check it on every write: a value
outside is a `RuleError` (`chips: 9 fuera de su rango 0..8`). Analyses use it as a bound where no
fixpoint can find one: Hold'em declares its chips, bets and minimum raise
(`@range(0..stack * num_players)`), Wizard its round and Solitaire its hidden cards.

**OpenSpiel without exploring** (`to_openspiel(game)`, `numbering="ir"` by default): the ids
above (legal actions sorted), the C++ states (immutable: cloning copies nothing) and exact chance
presented either as the list of distinct outcomes (when they can be enumerated and fit in
`max_chance_outcomes`) or **draw by draw** (shuffling 52 cards: each draw a chance node with its
options). The information state string is a perfect-recall key (chained SHA-256 of each step's
view and events); `max_chance_outcomes`, the game length and the utility bounds come from the
static analysis where possible and otherwise from probe matches. OpenSpiel's **MCTS plays the
wrapped chess** and its **MCCFR** (outcome sampling) runs on the wrapped no-limit Hold'em;
external sampling runs with small stacks (with 200 chips it would explore every bet size at each
of the traverser's decisions).

## 7. Algorithms (ADR-080)

`gamehub.analysis.cpp` (and `gamehub analyze --engine cpp`):

| | |
|---|---|
| `perft` | Python's semantics (chance adds every outcome; `skip`) |
| `alphabeta` | exact (rationals), expectimax at chance, transposition table with 128-bit keys; the same `Solution` as the Python version |
| `retrograde` | deterministic two-player zero-sum games **with cycles or without**: the whole state graph, labelled backwards from the terminals; what stays unlabelled draws by repetition (tic-tac-toe: 5,478 positions, a draw; Nim 3-5-7: 376, a first-player win) |
| `mcts` | UCT with random rollouts, n players, sampled chance |
| `cfr` | the same tree as `build_tree` (preorder, merged chance, information sets by the same SHA-256 keys) and the same CFR/CFR+ operations: the same average strategy |

## 8. Pending in F8

The WASM build for `play` and the Studio without a server (it needs the Emscripten SDK), the
optional IR → C++ code generation for hot games and Connect Four 7×6 (ADR-074).
