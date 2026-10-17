# Reference engine (Python)

> Status: **implemented** (Phase 1, 2026-10-09) in [`python/src/gamehub/engine`](../../python/src/gamehub/engine).
> This document fixes the **exact operational semantics**: any other engine (C++, WASM) must
> reproduce the [conformance traces](../../spec/conformance) bit for bit. Since Phase 8 the
> [C++ core](core.md) does, 50–60 times faster, with the same API (`gamehub.engine.core`).

## 1. Usage

```python
from gamehub.engine import load_game, Action, Pcg32

game = load_game("spec/ir/examples/kuhn-poker.ir.json")   # validates and compiles the IR
s = game.new_state(num_players=2, params={})               # initial state (immutable)
s.status                                                   # CHANCE | DECISION | TERMINAL
s.chance_outcomes()                                        # [((2, 1), Fraction(1, 6)), …]
s = s.apply_chance(s.sample_chance(Pcg32(seed=7)))         # or a specific outcome
s.active_seats, s.legal_actions(0)                         # (0,), [check, bet]
s.options(0), s.options(0, "bet", {})                      # progressive building
s = s.apply_action(0, Action.of("bet"))                    # returns a NEW state
s.view(1), s.events(1)                                     # what seat 1 sees
s.view(PUBLIC), s.events(PUBLIC)                           # what a spectator sees (F3)
s.information_state(1)                                     # key of its information set
s.snapshot(), s.digest()                                   # canonical configuration and its digest
s.illegal_reason(1, Action.of("call"))                     # why it is not legal (or None)
s.evaluate(["len", ["var", "moves"]])                      # an IR expression (tests, tools)
s.edited([["assign", ["var", "turn"], ["const", 1]]])      # an edited copy outside the flow (tests' `set`)
s.iter_legal_actions(0)                                    # legal actions one at a time (F3)
s.ranking()                                                # place of each seat at the end (F3)
game.decode_action(s.node, {"name": "bet", "args": {}})    # an action from JSON without the state (F3)
```

`evaluate`, `edited` and `illegal_reason` (Phase 2) serve `gamehub test` and the tools; they are
not part of the rules or of the conformance traces. `PUBLIC`, `iter_legal_actions`, `ranking` and
`Game.decode_action` (Phase 3) are used by the match server and the clients. For the Studio's
simulator (Phase 5), `s.outcome_probability(outcome)` gives the probability of a specific chance
outcome, and each transition knows who it is (`TransitionDef.key`: `("node", "Move", "0")` or
`("action", "Bid", "dudo", "1")`): with a list in `gamehub.engine.state.TRACE` (a `ContextVar`),
the engine records the ones it goes through, which gives the arrows of the last step and rule
coverage. Neither changes the semantics or the conformance traces. A game can also be loaded from
Nomos: `gamehub.lang.compiler.load_nomos(Path("games/nim/nim.game"))`.

```bash
gamehub play  GAME.game|GAME.ir.json --seats human,random [--param k=v] [--save-replay x.ghr.json]
gamehub fuzz  GAME.game|GAME.ir.json --games 100000 [--players n] [--failures DIR] [--jobs 6]
gamehub perft GAME.game --depth 5 [--divide] [--skip claim_draw] [--jobs 6]
gamehub natives list | check [--trials N] | build --check|--write
gamehub replay MATCH.ghr.json [--seat n]                   # also checks the provably fair chance
gamehub conformance --check | --write
```

`fuzz --jobs N` spreads the matches over N processes (seeds `seed + i`, the same report as with
one) and `perft` counts the sequences of legal moves up to a depth: chance points add up those of
all their outcomes, `--skip` leaves out actions such as claiming a draw and `--divide` splits the
count by first move (`gamehub.analysis.perft`, ADR-061).

From Python too: `gamehub.engine.match` (`play_match`, `RandomAgent`, `fuzz`, `fuzz_parallel`),
`gamehub.engine.replay` (`record`, `replay`) and the [`gamehub.build`](#8-builder-api) API.

## 2. Modules

| Module | Responsibility |
|---|---|
| `values` | Immutable values, total canonical order (`sort_key`), IR types, JSON |
| `rng` | PCG32, draws, exact replay and enumeration of chance |
| `expr` | The 87 expression operators (a test requires covering the whole catalog) |
| `stmt` | The 14 statements, lvalues, selectors and events |
| `visibility` | Visibility policies and value redaction |
| `game` | IR → compiled `GameDef`; parameters and initial state; function memoization; `Game` |
| `codegen` | IR expressions and functions → Python source code (F6, ADR-063) |
| `natives` | Native WebAssembly plugins: lookup, loading, ABI and comparison with the reference (F6, ADR-062) |
| `state` | Immutable `State` and the flow semantics (`_Tx`) |
| `match`, `replay`, `conformance` | Drivers, agents, fuzzer, replays and golden traces |

## 3. Values

| IR type | Value | JSON (views, events, actions) |
|---|---|---|
| `Bool`, `Int`, `Seat`, `Text` | bool, int, int, str | native |
| `Real` | an integer or an exact `Fraction` | integer, or `"n/d"` |
| `Cell`, `tuple`, `list`, `per_player` | tuple | array |
| enum | `EnumValue` | its name |
| struct | `StructValue` (fields in declaration order) | object |
| `option` | a value or `None` | a value or `null` |
| `set` / `map` | canonically ordered | array / array of pairs |
| `zone` / `bag` | `Zone(ordered=True/False)`; items with `face_up` | `{"size": n, "items": […]}` |
| `grid` | `Grid` (rows × columns) | array of rows |

**Canonical order** (`sort_key`): `null` < booleans < numbers < texts < enums (by type and
declaration order) < tuples (lexicographic) < structs < sets < maps < zones < grids. Sets, bags and
map keys are **always** traversed in this order, so execution does not depend on Python's hashing.

**Declared ranges** (`"range"` of a state variable, `@range` in Nomos, F8): every write to the
variable —and its initial value— checks that its numbers lie in the range, evaluated with the
match's parameters; otherwise a `RuleError` such as `chips: 9 fuera de su rango 0..8`.

## 4. Chance

- **RNG:** PCG32 (XSH-RR 64/32), identical to `pcg32_srandom_r(seed, stream)` / `pcg32_random_r` /
  `pcg32_boundedrand_r` from the reference C implementation (verified with its test vector).
  Streams: the match's chance = 1; match-server decisions (the random move when a deadline
  expires) = 2; the agent of seat *s* = 1000 + *s*.
- **Draws per statement:** `roll(n)` → `uniform(n) + 1`; `random_choice(xs)` → `uniform(len(xs))`
  over the canonical order; `shuffle` → Fisher–Yates from the end (*i* = n−1 … 1,
  *j* = `uniform(i+1)`); `sample(dist)` → with a common denominator *D* of the probabilities,
  *r* = `uniform(D)` and the first index whose cumulative sum exceeds *r*.
- The **outcome** of a chance point = the tuple of draws consumed by its effects.
  `chance_outcomes` enumerates them by re-execution, in lexicographic order, with exact
  probabilities (default limit: 100,000 outcomes → `NotEnumerable`). Examples: Kuhn = 6 outcomes
  of 1/6; shuffling 52 cards is not enumerable.
- The setup (`flow.setup`) with random statements is the first chance point (`node = None`).

## 5. Flow semantics

1. **Advance to quiescence.** After each step, the engine walks through `auto` nodes, phase
   entries and exits and transitions until it reaches a decision, a chance point or a terminal.
   Jumps are chained in a loop (no recursion); more than **10,000 arrivals** in one step =
   `RuleError` (a loop without progress). Each arrival emits a public `node` event.
2. **Transitions.** They are tried in groups and, within each group, in declaration order; the
   first one whose guard holds (or that has no guard) wins. Groups: after a decision action, first
   the **action's** (with `actor` and arguments) and then the **node's** (with `actor`); in
   windows, the node's without `actor`; elsewhere, the node's. None applicable = `RuleError`.
3. **Phases.** When jumping to a node, the active phases that do not contain it are exited
   (`on_exit`, inside out) and those that do are entered (`on_enter`, outside in); entering a
   phase leads to its `start` (recursively). Jumping to an ancestor phase **restarts** it.
   **`$exit`**: the phase's `on_exit` runs **and then** its transitions are evaluated (so they can
   depend on what was computed on exit, e.g. the round's score).
4. **`decision`.** `actor` is evaluated on arrival. No legal action at all = `RuleError`.
5. **`simultaneous`.** Actors (no repeats, by seat) evaluated on arrival. Submissions stay hidden
   (public `submitted` event); once complete, the effects are applied **in seat order**, then
   `resolve`, then the node's transitions. No per-action transitions.
6. **`window`.** `order` = the eligible seats in the given order, followed by the remaining
   eligible ones. Passing (`pass`) is implicit and reserved.
   - `priority`: only the first one who has not answered can act; the first non-pass is applied.
   - `collect`: everyone answers in secret (`responded` event); once complete, a `responses`
     event with what each one chose, and the first non-pass according to `order` is applied.
   - `race`: everyone can act; the first non-pass to arrive is applied immediately.
   - If everyone passes, the node's transitions. With no eligible seats, the window closes on
     arrival.
7. **`terminal`.** The payoff must have exactly one numeric value per seat.

## 6. Actions

- **Enumeration** (`legal_actions`): actions in declaration order; parameters in order; values in
  the order of the domain (which may depend on the previous parameters); filtered by `requires`.
  In windows, `pass` is added at the end.
- **Legality and canonical form** (`apply_action`): each argument must belong to its domain and
  `requires` must hold. The `subsets`, `range` and `enum_values` domains are checked without
  enumerating them; `subsets` arguments are reordered canonically (playing {6♦, 6♥} or {6♥, 6♦}
  is the same action).
- **Progressive building** (`options`): the available names, or the values of the next parameter
  that admit at least one complete legal action.

## 7. Information

- **Views** (`view(seat)`): `{node, status, active, state, responded?, payoffs?}` with each
  variable redacted according to its policy (ADR-019): hidden = `{"$hidden": true}`; ordered
  zones with a gap per position; bags with only the visible items and the size. `view(None)` is
  omniscient.
- **Events** of the last step (`events(seat)`), resolved per seat when emitted:

| Type | Contents | Who sees it |
|---|---|---|
| `node` | the node reached | everyone |
| `action` | seat, name, arguments | the actor in full; the others according to the visibility of the action and of each parameter (hidden, or only `{"size"}`) |
| `submitted` / `responded` | seat that has already chosen | everyone |
| `responses` | each seat's answer in a `collect` window | everyone |
| `move` | origin, destination, count, values | each value, if it was visible in the origin **before** or in the destination **after**; the event, if the size of either zone is visible |
| `flip`, `shuffle` | zone | everyone |
| `reveal` | value and label | the given seats |
| `emit` | name and fields | according to its visibility (`owner` = actor) |
| `reward` | seat and amount | everyone |
| `end` | payoffs | everyone |

- **Public observer** (`PUBLIC`, Phase 3): what a spectator, who holds no seat, sees. Policies are
  evaluated with a `viewer` that matches no `owner`: `owner` never lets it see, `all` does, and a
  predicate that cannot be evaluated without a seat (`team[viewer] == …`) counts as false. So
  `@visible(viewer != owner)` (Hanabi) does show it the cards. Of the events, it sees the public
  ones, what is revealed **to all** seats, actions according to their visibility for someone who
  is not the actor, and moves according to the visibility of the zones.
- **Final place** (`ranking`): 1 = first and ties share a place; it comes from the terminal node's
  `rank` if it declares one and, otherwise, from the payoffs (higher payoff, better place).
- **Information state** (`information_state`): SHA-256 of the sequence of (view, events) of that
  seat in every state since the start: perfect recall. Two histories are indistinguishable for a
  seat if and only if their keys match (verified on Kuhn).

## 8. Builder API

`gamehub.build` builds the IR from Python (`Expr` with operators, `GameBuilder`, `T.*`,
statements). Three games rebuilt with it give **the same rules hash** as their hand-written JSON
(`tests/test_build.py`).

## 9. Formats

- **Snapshot** (`snapshot`): canonical JSON with `node`, `store` (zones as `{items, face_up}`),
  `pending` and `payoffs`. **Digest** (`digest`) = SHA-256 of the snapshot.
- **Replay** `gamehub-replay/0.1` (`.ghr.json`): game (id, version, rules hash), players,
  parameters, seed, steps (`{"chance": [draws]}` or `{"seat", "action"}`), the digest after each
  step and the result. Re-simulation checks the hash and the digests. Optional fields from the
  match server (F3): `players` (name and kind of each seat), `fairness` (provably fair chance)
  and, in `result`, `ranking`, `reason` (`terminal`, `forfeit`, `aborted`) and `forfeited`; a match
  that does not reach a terminal has no `payoffs`. `replay.frames(game, data, seat)` gives each
  state of the match with its view and the events that led to it as a seat, a spectator or
  someone seeing everything saw them (the web app's replay viewer, F4).
- **Provably fair chance** (`gamehub.engine.fairness`, scheme `gamehub-fair/1`): the server
  publishes `SHA-256("gamehub-fair/1:commit:" + server_seed)` before the match; the match seed is
  the SHA-256 of the canonical JSON `{scheme, server_seed, client_seeds}` (first 8 bytes, 53
  bits); at the end `server_seed` is revealed. `gamehub replay` checks the commitment, the seed and
  that each chance outcome is the one PCG32 gives with it.
- **Conformance traces**: replays with fixed seeds in `spec/conformance/<game>/`.

## 10. Performance (Python, Apple Silicon)

None of these techniques changes the semantics: the conformance traces are the same, and a test
checks that, for every game in the catalog, random matches give the same digest at every step
with and without them.

### Function memoization

`GameDef` classifies each IR function by what it reads (a transitive static analysis,
`_memo_kinds`, ADR-060):

- **static** (only its arguments: no state, options, seats or context): its result is kept for
  every match of the game (`GameDef.static_memo`, up to 200,000 entries). This way chess's tables
  (rays, knight jumps) or the value of a poker hand are computed once.
- **state** (state and options, but not the current node or the context seats): kept in
  `State.memo`; every write to the store in a transaction empties it, so there is no invalidation
  to forget.
- No memo: functions that depend on the context (`actor`, `owner`, `viewer`…) and those without
  loops or calls (storing them would cost more than computing them).

### Generated code

`gamehub.engine.codegen` writes each IR expression and function as Python source code (one `def`
per function with its arguments and locals as variables; `let` and comprehensions as lambdas) and
compiles it with `exec` (ADR-063). It calls the same per-operator functions as `expr`'s closures,
so it gives the same results and the same errors; integers have shortcuts (`add`, `lt`, `cell`…)
that skip rationals. The closures remain the reference: they are used if something cannot be
generated, with `GAMEHUB_CODEGEN=0` or with `Game(ir, codegen=False)`. A test requires the
generator to cover the whole operator catalog.

### Native plugins

A function with `"native": "module.function"` ([IR](ir.md), `@native` in
[Nomos](language.md#native-plugins)) can be replaced by a plugin that gives exactly the same
result; **its body is the reference implementation** (ADR-062). Plugins are **WebAssembly
modules without imports** (the same binary will work in the browser and in the C++ core), with a
computation limit per call (50 million units of `wasmtime` fuel). ABI `gamehub-native/1`:

- The module exports `memory`, `gh_buffer() -> i32` (a buffer of at least 64 KiB) and one
  function per native function: `(in: i32, len: i32, out: i32) -> i32`.
- Arguments go into the buffer as i32 words, in order: `Bool` 0/1, `Int` and `Seat` as is, `Cell`
  as row and column, an enum by its ordinal, a struct field by field, a tuple element by element,
  a list as its length followed by its elements, an option as 0, or as 1 followed by the value. The
  function writes the result, encoded the same way, starting at `out` and returns how many words
  it wrote (negative = error).
- The plugin of module `a.b` is `a.b.wasm` (or its source `a.b.wat`) in a directory of
  `GAMEHUB_NATIVE_PATH` or in `stdlib/std/native/`. `natives.register(id, impl)` registers a
  Python implementation (for tests or trusted programs).
- In Python it needs `wasmtime` (the `gamehub[wasm]` extra); without it, with
  `GAMEHUB_NATIVES=0` or if an integer does not fit in an i32, the reference is used.
  `gamehub natives check` compares plugin and reference on random inputs (0 differences in
  `std.poker.hand_value`) and `natives build --check` (in CI) checks that each `.wasm` is its
  compiled `.wat`.

### Figures

Random matches per second with one process (before Phase 6):

| Game | Random matches/s | Average steps |
|---|---:|---:|
| Prisoner's dilemma / RPS | ≈ 12,000 | 2 |
| Kuhn poker | ≈ 4,600 | 3.3 |
| Nim (3, 5, 7) | ≈ 2,800 | 6.7 |
| Tic-tac-toe | ≈ 1,600 | 7.6 |
| Bullshit (3 players) | ≈ 0.9 (2.9 ms per step) | ≈ 390 |

Bullshit's bottleneck is enumerating the subsets of the hand (up to 4,047 actions per turn) so
that the random agent picks uniformly. A profile showed that half the time went into
deduplicating subsets that were already distinct; fixed (×1.8).

The Phase 6 games, in the acceptance run of 10⁵ matches (`fuzz --jobs 6`, 8 cores):

| Game | Matches/s | Average steps |
|---|---:|---:|
| Chess | 11 | 346 |
| Skat (3 / 4 players) | 117 / 83 | 120 / 160 |
| Wizard (3 / 6 players) | 20 / 38 | 711 / 401 |
| Parchís (2 / 4 players) | 57 / 25 | 351 / 665 |

Chess *perft*: memoization and the rewrite of the rules (check and pin lines, the king in the
state, `std.boards`'s tables) brought *perft(3)* down from 52 s to 1.2 s, and *perft(5)*
(4,865,609 positions) took 131 s with 6 processes; generated code came afterwards (×2). The
[C++ core](core.md#5-performance) (Phase 8) does it in 18 s on one thread and plays random
matches 57–63 times faster (tic-tac-toe, Connect Four, Kuhn).

## 11. Known limitations

- Hand-written IR is not **type** checked (Nomos is, since Phase 2): its type errors show up at
  run time as `RuleError`.
- No history features or time in the IR (v0.2): chess keeps the positions for repetitions in its
  state, and deadlines are set by the room.
- A call to a WebAssembly plugin costs ~25 µs in Python: it only pays off for expensive functions
  (the poker evaluator gains ×3).
- `information_state` walks through the whole history (quadratic cost if called at every step).
