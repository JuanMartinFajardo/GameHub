# Nomos — the `.game` language (reference v0.1)

> Status: **implemented** (Phase 2; extended in Phases 4 to 6). Compiler in
> [`python/src/gamehub/lang`](../../python/src/gamehub/lang); text is translated into
> [GameIR](ir.md), which the [engine](engine.md) runs. The underlying semantics is in the
> [formal model](formal-model.md). This page is the reference of the language as it works today;
> the differences from the Phase 0 RFC are summarized at the end.

## 1. Design goals

- **Human-readable** and **diffable**: a rule change is a small diff (and `gamehub diff` explains
  it element by element).
- **1:1 correspondence with the diagram**: each node is a box and each `->` an arrow with its
  condition (`gamehub viz` draws exactly that).
- **Pure, typed and total expressions** (no recursion or infinite loops); effects only in effect
  blocks. Chance only in `chance` nodes and in the setup.
- Syntax with braces, English keywords and Python-style expressions (`and`, `or`, `not`, `in`,
  `a if c else b`); the texts players see are translatable.

## 2. At a glance

```game
game TicTacToe {
  meta {
    id: "tictactoe"
    version: "1.0.0"
    title: { en: "Tic-tac-toe", es: "Tres en raya" }
  }
  players 2

  enum Mark { X, O }

  state {
    board: Grid[3, 3] of Mark? = none
    turn: Seat = 0
  }

  fn mark(p: Seat) -> Mark = X if p == 0 else O
  fn wins(m: Mark) -> Bool = any(line in lines(board, 3) : all(c in line : board[c] == m))
  fn full() -> Bool = all(c in cells(board) : not is_none(board[c]))

  flow {
    start -> Move

    decision Move {
      actor: turn
      action place(c in cells(board)) requires is_none(board[c]) { board[c] = mark(turn) }
      -> Win when wins(mark(turn))
      -> Draw when full()
      -> Move { turn = next(turn) }
    }

    terminal Win { payoff: win_loss(turn, 1, -1) }
    terminal Draw { payoff: fill(0) }
  }

  test "X wins on the diagonal" {
    play place((0, 0)), place((0, 1)), place((1, 1)), place((0, 2)), place((2, 2))
    expect at(Win) and payoff == [1, -1]
  }

  /// X moves first: it never has fewer marks than O nor more than one ahead
  invariant {
    let xs = count(c in cells(board) : board[c] == X)
    let os = count(c in cells(board) : board[c] == O)
    xs - os in 0..1
  }
}
```

More complete examples in [`games/`](../../games): Kuhn and Leduc (poker), Bullshit, Dudo,
Connect Four, Nim, the 2×2 family (with `extends`), the iterated prisoner's dilemma (with
`repeat`) and, since Phase 6, chess, Skat, Texas Hold'em, Wizard, Parchís and Solitaire.

## 3. Lexical structure

- **Identifiers**: letters, digits and `_`, not starting with a digit. By convention, types, enum
  values and nodes in `CamelCase`; everything else in `snake_case`.
- **Reserved words**: `action and assert auto case chance deal decision div else emit enum exit
  extend extends fail false flip flow fn for game if import in invariant let match meta move none
  not or override params phase players remove requires reveal reward shuffle simultaneous start
  state struct terminal test true when window`.
- **Contextual words** (keywords only where they apply, so they are valid names): `from to each
  as of top bottom at all face_up face_down face play expect legal illegal set seed where node
  per_player`, the keys of a node's members and of `meta`, and `Grid`.
- **Numbers**: integers (`42`, `1_000`) and exact decimals (`0.5`, which is the rational 1/2;
  payoffs and `Real`s are exact rationals). `div` is integer division and `%` the modulo; `//`
  starts a comment.
- **Texts**: `"…"` with the escapes `\n \t \r \" \\ \0 \u{…}`. A **translatable text** is
  `{ en: "…", es: "…" }` (entries separated by commas or line breaks).
- **Comments**: `// …`, `/* … */` and **documentation** comments `/// …`, which attach to the
  next declaration (and reach the IR as `doc`). For translatable documentation:
  `@doc({ en: "…", es: "…" })`.
- **Line breaks**: they separate elements and statements. Inside `( … )` and `[ … ]` they do not
  count; inside `{ … }`, they do. An expression continues on the next line after a binary
  operator (`+`, `and`…) and after `=`, `+=`…, `requires`, `when` and `key:` (that is how the
  formatter splits lines). `;` also separates.

## 4. Files, modules and packages

A `.game` file contains, in any order: `import`, `enum`, `struct`, top-level `fn`, games
(`game Name { … }`) and games derived with a combinator (`game Name = repeat(…)`). A file without
games is a **module** (`gamehub check` checks its types and functions).

```game
import std.cards.{Card, Rank, french52}    // specific names
import std.dice.*                          // everything the module declares
import prisoners_dilemma.{PrisonersDilemma}
```

- **Resolution** of `a.b`: `std.…` is the [standard library](../../stdlib/std); then, a
  **dependency** `a` of the file's package (`game.toml`); otherwise, the file `a/b.game` next to
  the importing one. In an `import` each part is an identifier: `prisoners_dilemma` also finds
  `prisoners-dilemma.game`. `import dep.{X}` reads the dependency's main file;
  `import dep.sub.{X}`, `sub.game` inside it.
- **What it brings**: an imported name also brings what it needs from the module (its types and
  helper functions). Imported declarations only reach the IR if the game uses them.
- **Module scope**: a module's functions do not see the state or the options of any game (they do
  see `seats` and `num_players`); their parameters may be named like anything in the game.
- A name cannot be imported from two modules or clash with a local declaration (E202); import
  cycles are an error (E504).

**Standard library** (`stdlib/std/`, tested with [Nomos tests](../../python/tests/fixtures/stdlib.game);
the F2 v0 plus what Phase 6 added):

| Module | Contents |
|---|---|
| `std.cards` | The French deck (`Suit`, `Rank` from 2 to ace, `Card`, `french52()`, `rank_value`, `is_red`), the Skat deck (`skat32()`: from seven to ace), the Wizard deck (`WizardRank`, `WizardCard`, `wizard60()`, `is_wizard`, `is_jester`) and the Spanish deck (`SpanishSuit`, `SpanishRank`, `SpanishCard`, `spanish40()`, `spanish48()`, `spanish_number`) |
| `std.dice` | `faces`, `count_face`, `count_with_wild` (wildcards), `sum_face`, `most_repeated`, `all_same`, `is_straight` |
| `std.grid` | Directions (`orthogonal`, `diagonal`, `all_directions`), `shift`, `ray`, `manhattan`, `chebyshev`, `adjacent`, `touching` |
| `std.graph` | Graphs as edge lists: `neighbors_of`, `successors`, `connected`, `degree`, `cycle`, `advance` |
| `std.boards` | Boards: rook, bishop and queen directions, knight jumps (`rook_directions`, `bishop_directions`, `queen_directions`, `knight_jumps`), squares within the board (`within`, `ray_within`, `hops_within`) and circular tracks (`loop_path`, `advance_on`, `passes`) |
| `std.tricktaking` | Tricks from the **effective suit** (an integer; −1 = can always be played) and the **strength** each game gives its cards: `can_play`, `first_suit`, `trick_key`, `trick_winner`, `trick_order` ([ADR-064](decisions.md)) |
| `std.bidding` | Trick bids: `above`, `total_bid`, `all_bid`, `hook_ok` (the last bid cannot make the total add up), `sole_bidder` |
| `std.betting` | Pots from per-seat bets: `pot_levels`, `pots` (main pot and side pots), `pot_share`, `winnings`, `to_call` |
| `std.poker` | Poker hands of 5 to 7 cards: `HandRank`, `hand_rank`, `hand_value` (an integer that orders hands; with a [native plugin](#native-plugins)), and its building blocks (`encode`, `ranks_down`, `straight_high`, `top_ranks`, `flush_value`) |

### Native plugins

A top-level function can be marked as **native** ([ADR-062](decisions.md)):

```game
@native("std.poker.hand_value")
fn hand_value(cards: List<Card>) -> Int { … }   // the body is the reference, and it is mandatory
```

An engine may replace the function with a plugin that gives **exactly** the same result for any
input; if it has none (or with `GAMEHUB_NATIVES=0`), it uses the body. Plugins are WebAssembly
modules without imports: the one for module `a.b` is the file `a.b.wasm` in `stdlib/std/native/`
or in a directory of `GAMEHUB_NATIVE_PATH`. The ABI is in the [engine](engine.md#native-plugins).
The signature may only use `Bool`, `Int`, `Seat`, `Cell`, enums, structs, tuples, lists and
options of them (E211). `gamehub natives list|check|build` lists them, compares them with the
reference on random inputs and compiles them from WAT.

**Packages** ([`gamehub.packages`](../../python/src/gamehub/packages.py)): each game lives in a
directory with its `game.toml`.

```toml
[game]
name = "iterated-pd"             # lowercase and dashes (the game's id)
version = "1.0.0"
entry = "iterated-pd.game"       # optional: <name>.game by default
license = "CC-BY-4.0"
authors = ["GameHub"]
forked_from = "url@commit"       # written by gamehub fork

[dependencies]
prisoners-dilemma = { path = "../prisoners-dilemma" }
cards = { git = "https://…", rev = "v1.0" }    # branch, tag or commit
```

`gamehub fetch` downloads the git dependencies (also those of the dependencies) into the cache
(`~/.cache/gamehub/git`) and writes `game.lock` with the exact commit of each one; with the lock,
compilation is reproducible (`--update` resolves again). `gamehub new` creates a package with a
game that compiles and passes its tests, from a template (`--template`: `vacio` (empty),
`carrera` (race, the default), `tablero` (board), `cartas` (cards), `dados` (dice) or `matriz`
(2×2 matrix); the same ones as the Studio); `gamehub clone` clones and downloads dependencies;
`gamehub fork` copies and records the origin (`forked_from`, and the original remote becomes
`upstream`).

## 5. Inside a game

| Element | Form | Notes |
|---|---|---|
| `meta` | `meta { id: "…", version: "…", title: …, description: …, authors: […], license: "…", tags: […] }` | Default `id`: the name in lowercase with dashes (`TicTacToe` → `tic-tac-toe`); `version`, `"0.1.0"`. Translatable texts in `title` and `description`. |
| `players` | `players 2` · `players 2..4` | Required. |
| `params` | `params { name: Type = value … assert cond, "message" }` | Match options. A default value may only use earlier options. The `assert`s are checked when the match is created. |
| `enum` | `enum Suit { Coins, Cups, Swords, Clubs }` | Ordered by declaration (`ord`, comparisons). |
| `struct` | `struct Card { suit: Suit, rank: Rank }` | Immutable; literal `Card { suit: s, rank: r }`. |
| `state` | `state { [@visible(…)] [@size_visible(…)] [@range(lo..hi)] name: Type [= value] … }` | Without a value: the type's zero (`false`, `0`, `""`, `none`, an empty collection, the enum's first value…). In `per_player`, the value may use `owner`. `@range` (below) declares the range of its numbers. |
| `fn` | `fn name(p: T, …) -> R = expr` · `fn name(…) -> R { let … ; result }` | Pure; they may read state and options; no recursion (E208). Top-level ones may be `@native` (§4). |
| `flow` | `flow { start … nodes … }` | See §9. |
| `test` | `test "name" { steps }` | See §10. They are not part of the IR. |
| `invariant` | `[/// label] invariant cond` | See §10. |
| `ui` | `ui { target: hint, … }` | Presentation hints for interfaces (§12). They are not rules. |

Local names (function and action parameters, `let`, comprehension variables) cannot shadow a
global name of the game (E204): state, options, functions, types, enum values, or `seats`,
`num_players`, `actor`, `viewer`, `owner`, `face_up`.

## 6. Types

| Type | Values | Notes |
|---|---|---|
| `Bool`, `Int`, `Real`, `Text` | | `Real` = exact rational; an `Int` is accepted where a `Real` is expected. |
| `Seat` | `0 … num_players - 1` | Interchangeable with `Int`. `next(s)`, `prev(s)`, `other(s)` (2 players), `seats`, `seats_from(s)`. |
| `Cell` | `(row, column)` | A grid square; `c[0]` row, `c[1]` column; interchangeable with `(Int, Int)`. |
| `T?` | `none` or a `T` | `is_none(x)`, `unwrap(x)`. |
| `List<T>`, `Set<T>`, `Map<K, V>` | `[…]`, `set(…)`, — | |
| `Zone<T>` | an **ordered** collection of items with a face (deck, pile, table) | `top(z)`, `size(z)`, `items(z)`; it can be shuffled, dealt, flipped. |
| `Bag<T>` | an **unordered** multiset (a hand) | Whoever cannot see its contents only sees its size. |
| `(A, B, …)` | tuples | `t[0]`, `t[1]` with a constant index. |
| `per_player T` | one `T` per seat | `x[s]`; the owner of `x[s]` = `s` (for `@visible(owner)`). |
| `Grid[width, height] of T` | grid | Constant dimensions or option names (`Grid[columns, rows] of Disc?`). `cells`, `lines(g, k)`, `neighbors`, `in_bounds`. It can be assigned the list of its rows (`board = [[…], …]`, also in tests' `set`); the dimensions are checked at run time. |

A list is accepted where a zone, a bag, a set or a `per_player` is expected.

## 7. Visibility (hidden information)

Annotations on state variables, action parameters and events:

| Annotation | Who sees |
|---|---|
| `@visible(all)` | everyone (the default) |
| `@visible(none)` | nobody (a deck) |
| `@visible(owner)` | the owner of each `per_player` part (a hand) |
| `@visible(face_up)` | in a zone, whatever is face up (also in a list of zones: zone by zone) |
| `@visible(expr)` | whoever satisfies `expr`, with `viewer`, `owner`, `face_up` and `at(Node)`: `@visible(viewer == owner or at(Showdown))` |
| `@size_visible(…)` | in zones and bags, who sees the size (everyone by default) |

**Declared ranges** (F8, ADR-079): `@range(lo..hi)` (or `lo..<hi`) on a state variable whose
numbers are `Int`, `Seat` or `Real` —also inside `per_player`, lists, sets, grids and options—
declares that every one of them stays in that range, with bounds made of parameters and
constants: `@range(0..stack * num_players) chips: per_player Int = stack`. The engines check it
on every write (`chips: 9 fuera de su rango 0..8` is a rule error) and the analyses use it as a
bound: the global action ids of a bet `amount in 1..chips[actor]` need to know how high `chips`
can go. It is part of the rules (it changes the rules hash).

In actions: `action play(@visible(none) @size_visible(all) cards in …)` hides which cards were
played but not how many. In events: `@visible(owner) emit …`. `reveal x to all` /
`reveal x to s [as "label"]` show a value. The submissions of a `simultaneous` node and the
answers of a `collect` window stay hidden until resolved. `gamehub check` warns about possible
leaks (W405, §15).

## 8. Expressions

**Precedence** (lowest to highest): `a if c else b` · `or` · `and` · `not` · comparisons
(`== != < <= > >= in` `not in`; they do not chain) · ranges (`a..b` inclusive, `a..<b`) · `+ -` ·
`* / div %` · unary `-` · calls, indexing, slices and fields (`f(x)`, `xs[i]`, `xs[a:b]`,
`c.rank`). Parentheses group; `(a, b)` is a tuple.

| Construct | Example |
|---|---|
| Literals | `true`, `none`, `3`, `0.25`, `"text"`, `[1, 2]`, `(r, c)`, `Card { suit: s, rank: r }` |
| Enums | `Rank.Ace` (always) or `Ace` (if not ambiguous, E203); `Rank.values` |
| Conditional | `1 if won else 0` |
| `case` | `case { x > y => 1  x < y => -1  else => 0 }` (one branch per line) |
| `match` | `match (a, b) { (Red, _) => 1 … }` — patterns: values, `_` and tuples; it must be exhaustive (E304) |
| Block with `let` | `{ let xs = …; let os = …; xs - os }` |
| Comprehension | `[c.value for c in hand[s] if c.rank != Ace]`, several `for`s and `if`s |
| Aggregates | `all(x in xs : p)`, `any`, `count`, `sum`, `max`, `min`, `argmax`, `argmin`, `sort_by`, `map`, `filter`, `flat_map`; shortcuts `sum(xs)`, `max(xs)`, `min(xs)` |
| Collections | `xs + ys` (concatenate), `xs - ys` (difference), `x in xs`, `x not in xs` |
| Context | `actor` (actions and transitions of a decision), `seats`, `num_players`, `at(Node)`; in visibility: `viewer`, `owner`, `face_up` |

**Built-in functions**: `len`, `size`, `items`, `top`, `first`, `last`, `only`, `reverse`,
`distinct`, `append`, `concat`, `union`, `intersection`, `difference`, `subsets(xs, min, max)`,
`range(a, b)`, `slice`, `contains`, `set(…)`, `abs`, `min`, `max`, `sum`, `rat(a, b)`, `is_none`,
`unwrap`, `ord`, `next`, `prev`, `other`, `seats_from`, `cells`, `lines`, `neighbors`,
`in_bounds`, `cell(r, c)`, `win_loss(winner, win, loss)`, `fill(value)`; and, only as the right-hand
side of an assignment in chance, `roll(n)`, `random(xs)`, `sample([(value, prob), …])`.

## 9. Effects and flow

**Statements** (in `start { … }`, `chance`/`auto` nodes, actions, `resolve`, `on_enter`,
`on_exit` and transitions):

| Statement | Notes |
|---|---|
| `let x = e` | local to the block |
| `x = e`, `x += e`, `x -= e`, `x *= e` | on the state: a variable, index or field (`hand[s]`, `pos.x`); `+=` concatenates lists |
| `if c { … } else if … else { … }` · `for x in xs { … }` | |
| `move SEL from Z1 to Z2 [at top\|bottom]` | `SEL`: `all`, `top n`, `bottom n`, `at i`, a value or a list of values |
| `flip SEL of Z face_up\|face_down\|face(b)` | |
| `shuffle Z` · `x = roll(6)` · `x = random(xs)` · `x = sample(…)` | random: only in `chance` nodes and in `start { … }` (E306) |
| `deal n from Z to each H` · `deal all from Z to each H` | one card at a time, round-robin |
| `reveal e to all\|s [as text]` · `[@visible(…)] emit name { field: e, … }` | information and events |
| `reward e to s` · `fail "text"` | `fail` = a rule error (a case the design does not cover) |

**Flow**:

```game
flow {
  start [{ setup }] -> Node
  decision N { actor: e  action …  -> … }
  simultaneous N { actors: e  action …  resolve { … }  -> … }
  window N { eligible: e  mode: priority|collect|race  [order: e]  action …  -> … }
  chance N { random effects  -> … }
  auto N { effects  -> … }
  phase N { start -> M  [on_enter { … }]  [on_exit { … }]  nodes…  -> … }
  terminal N { [let x = e]  payoff: e  [rank: e] }
}
```

- **Actions**: `action name(p: Type in domain, …) requires cond { effects  -> transitions }`. The
  domain of each parameter is a finite collection that may depend on the previous ones; with an
  enum or `Bool` the type is enough (`c: Choice`); with a domain, the domain is enough
  (`c in cells(board)`). An action's transitions go at the end of its body.
- **Transitions**: `-> Target [when cond] [{ effects }]`, in order; the first one that holds
  wins. After an action, the action's transitions are tried first and then the node's. A
  transition without `when` followed by others is an error (E403); if all of them have a
  condition, `check` warns (W402). `-> exit` leaves the phase: its `on_exit` runs and then its
  transitions.
- **Nodes**: `decision` (one actor), `simultaneous` (everyone at once, in secret; no per-action
  transitions), `window` (reaction: passing is implicit; `priority` in order, `collect` in
  secret, `race` the first one), `chance` (chance), `auto` (no waiting), `phase` (a sub-diagram),
  `terminal` (payoffs: one number per seat). The exact semantics, in
  [engine §5](engine.md#5-flow-semantics).

## 10. Tests and invariants

```game
test "the high card wins" {
  players 2                                       // configuration, at the start
  params { max_play: 2 }
  seed 7
  chance where only(hand[0]) == K and only(hand[1]) == J
  play check(), bet(), call()                     // the seat: the only one that can act
  play 0: choose(Defect), 1: choose(Cooperate)    // or given explicitly
  expect at(Showdown) and payoff == [2, -2]
  expect legal call()
  expect illegal raise()
  set hand[0] = [Card { suit: Clubs, rank: Ace }] // change the state by hand
}

/// No card gets lost
invariant size(deck) + sum(s in seats : size(hand[s])) == 3
```

- `players`, `params` and `seed` go at the start (E601); by default, the minimum number of
  players, the default options and seed 0.
- Before each step, pending chance is resolved with PCG32(seed). `chance [r, …]` fixes the
  outcome; `chance where c` picks one that satisfies `c`, with its conditional probability (by
  enumeration or, if there are too many outcomes, by sampling).
- `payoff` (only at the end) and `active` exist in `expect` and in action arguments.
- After a `set`, the test stops checking invariants (the state may not be reachable).
- **Invariants** are checked in every state a test reaches and in random matches
  (`gamehub test --playouts N`, 20 by default, rotating the number of players).

Failures are explained rustc-style, with the values involved
(`` `payoff == [1, -1]` is false: `payoff` is [2, -2] ``) and the legal moves.

## 11. Mods and combinators

```game
import tictactoe.{TicTacToe}

game Misere extends TicTacToe {
  meta { title: "Misère tic-tac-toe" }
  override terminal Win { payoff: win_loss(turn, -1, 1) }
}

game WithPass extends TicTacToe {
  state { passed: per_player Bool = false }
  extend node Move {
    action skip() requires not passed[actor] { passed[actor] = true }
  }
}

game IteratedPD = repeat(PrisonersDilemma, rounds: 10, payoff: sum)
game Match = best_of(PrisonersDilemma, rounds: 3)
```

- **`extends`**: the variant starts from the base (from the file, imported or a combinator) and
  applies, in order: new declarations (they cannot share a name with one of the base), `override`
  (fn, enum, struct, a node —also inside phases—, `params`, `state`; an `override params` with
  `assert`s replaces the base's constraints), `remove node|fn|state|param|enum|struct X` and
  `remove action Node.action`, and `extend node X { … }` (actions at the end, transitions
  **before** the base's). `meta` is merged (without inheriting `id` or `version`); tests and
  invariants are not inherited. Errors E505.
- **`repeat(Base, rounds: n, payoff: sum|mean)`** and **`best_of(Base, rounds: n)`** transform the
  IR: one phase per round that resets the state to its initial value, terminals that record the
  result, and a final terminal (sum or mean; or `num_players - 1` for whoever wins the most rounds
  and `-1` for the rest). `rounds` becomes an option of the game. A combinator has no tests: it is
  extended (`game Checks extends IteratedPD { test … }`). Errors E506.

## 12. Presentation: `ui { … }`

Hints for interfaces: how to draw the state, what things are called on screen and how an action's
arguments are picked by touching the board. **They are not rules**: they reach the IR under the
`ui` key, which does not count for the rules hash, and the web's generic UI
(`@gamehub/auto-ui`) reads them. Without them the game plays the same: the generic UI deduces
almost everything from the types and the action domains (`cells(board)` → click squares;
`subsets(items(hand))` → pick cards from the hand).

```game
ui {
  board: grid
  cup: dice, label({ en: "Cup", es: "Cubilete" })
  dice_left: counter, place(seats)
  die: hidden
  rank: place(top)
  dice: label({ en: "Dice per player", es: "Dados por jugador" })   // an option
  Mark: symbols(X: "✕", O: "◯")
  Disc: colors(Red: "#e53935", Yellow: "#fdd835"), labels(Red: "Red", Yellow: "Yellow")
  Card: card(rank: rank, suit: suit)
  action bid: label({ en: "Bid", es: "Apostar" })
  action drop.c: column(board)
  node Bid: label({ en: "Bidding", es: "Apuestas" })
  seats: colors("#e53935", "#fdd835"), names("Red", "Yellow")
}
```

Each line is `target: hint, hint…`. `ui` is only a keyword at the start of the section.

| Target | Hints |
|---|---|
| state variable | **how to draw it** (one): `grid` (grid), `hand` (fan), `pile` (pile showing the top card), `deck` (face-down deck), `row` (in a row), `dice` (dice: an `Int` or a collection of `Int`s), `counter` (number), `chips` (betting chips), `seat` (a player), `hidden` (not drawn); `place(table \| seats \| top)` (on the table, in each seat's panel —`per_player` only— or in the top bar); `label(text)` |
| option (`params`) | `label(text)` |
| enum | `symbols(Value: "…", …)`, `colors(Value: "#rrggbb", …)`, `labels(Value: text, …)`, `card` (its values are cards), `label(text)` |
| struct | `card(rank: field, suit: field)` (a playing card: the field with the rank and, if any, the one with the suit), `label(text)` |
| `action name` | `label(text)` |
| `action name.parameter` | `label(text)`; how to pick it: `cell(grid)` (click a square; the parameter is a `Cell`), `column(grid)` / `row(grid)` (click in a column or row; the parameter is an `Int`), `pick(zone)` (pick from a collection: one item or a list of them) |
| `node Name` | `label(text)` |
| `seats` | `colors("#…", …)` (one color per seat), `names(text, …)` (e.g. "White", "Black") |

Errors: unknown target, with a suggestion (E701); a hint that is not valid for that target or type
(E702); invalid arguments —an enum value, field or color that does not exist, `place(seats)` on
something that is not `per_player`, `column(x)` for a parameter that is not an `Int`…— (E703); two
hints for the same slot (two drawing forms, two `label`s…) (E704). In a variant (`extends`), each
hint replaces the one in the same slot of the base.

## 13. Tools

| Command | What it does |
|---|---|
| `gamehub check PATH…` | Compiles and checks (types, flow, static warnings, classification); `--format json` for editors |
| `gamehub fmt PATH…` | Canonical formatting (`--check`, `--diff`, `--stdin`) |
| `gamehub test PATH…` | Tests and invariants (`--playouts`, `--seed`, `-k`, `--format json`) |
| `gamehub compile` / `decompile` | `.game` ↔ IR (`.ir.json`); the round trip is exact |
| `gamehub viz GAME` | Flow diagram (Mermaid or `--format dot`) |
| `gamehub rules GAME` | Rulebook in Markdown (`--lang en`) |
| `gamehub diff A B` · `gamehub diff REV1..REV2 file` | Semantic diff (text or JSON) |
| `gamehub new` · `fetch` · `clone` · `fork` | Packages (`new --template vacio\|carrera\|tablero\|cartas\|dados\|matriz`) |
| `gamehub play` · `fuzz` · `replay` | Play in the terminal, random matches (`fuzz --jobs N` across several processes), replays (they accept `.game`) |
| `gamehub perft GAME --depth N` | Counts the sequences of legal moves (`--divide`, `--skip`, `--jobs`, `--param`); chance points add up all their outcomes |
| `gamehub natives list\|check\|build` | Native plugins: which ones exist, whether they match the reference (`--trials`), compile WAT to WASM (`--check`, `--write`) |
| `gamehub wasm --check\|--write` | The C++ core compiled to WebAssembly for the browser (`web/packages/engine/wasm`; `--write` needs Emscripten) |
| `gamehub web export DIR [GAMES…]` | A static site with the play app and the games, without a match server: matches on one device with the engine in the browser |
| `gamehub studio [PATH]` | The [Studio](studio.md): design with the diagram and the text at once, and simulate (`--open`, `--port`) |
| `gamehub lsp` | Language server over standard input, for any editor with LSP |

The language server provides diagnostics, completion depending on where the cursor is (also with
half-written text), hover with types and signatures, go to definition (also into the standard
library), references, rename (checking clashes and that the game still compiles), formatting,
document outline, folding, signature help and quick fixes. VS Code extension:
[`editors/vscode/nomos`](../../editors/vscode/nomos) (highlighting, diagnostics on save and
formatting; still with `gamehub check` and `gamehub fmt`, not with the LSP).

## 14. Translation to the IR

The checker elaborates and translates in a single pass; whatever does not appear here is
translated 1:1.

| Nomos | IR |
|---|---|
| `a + b + c` | `["add", a, b, c]` (chains are flattened unless the left one is parenthesized) |
| `-5`, `0.25`, `a..<b` | `["const", -5]`, `["rat", 1, 4]`, `["range", a, b - 1]` |
| `xs + ys`, `xs - ys`, `x in xs`, `x not in xs` | `concat`, `difference`, `["contains", xs, x]`, `["not", ["contains", …]]` |
| `x += e` | `["assign", x, ["add", x, e]]` (or `concat` on lists) |
| `deal n from Z to each H` | loops of `move top 1` per seat (`deal all`: until Z is empty, round-robin) |
| `match` | `case` (if exhaustive, the last branch is the default case) |
| `max(x in xs : e)`, `sum(xs)` | `["max_of", "x", xs, e]`, `["sum", "x", xs, ["local", "x"]]` |
| `{ let x = e; r }` | `["let", "x", e, r]` |
| `[e for x in xs if c]` | `["map", "x", ["filter", "x", xs, c], e]` |
| `next(s)`, `other(s)` | `["next_seat", s]`, `["other_seat", s]` |
| `@native("m.f") fn …` | the function with `"native": "m.f"` and its body |
| variables without an initial value | the type's zero |
| unused module declarations | do not reach the IR |
| `test`, `invariant`, comments | do not reach the IR (`///` ones do, as `doc`) |

## 15. Diagnostics

`rustc`-style: code, message, position with the underlined snippet, notes and help. All errors of
a file are reported (the parser recovers at the level of the block it is in).

| Codes | Family |
|---|---|
| E101–E103 | lexical: unexpected character, unterminated comment or text, unknown escape |
| E110–E112 | syntax: unexpected element, annotation not allowed, order within an action |
| E201–E211 | names and declarations: unknown (with a suggestion), duplicate or clash, ambiguous, shadows a global, out of its context (`actor`, state in module functions…), reserved, arity, recursion, struct without values, players, a signature that cannot be `@native` |
| E301–E307 | types: mismatch, operator not applicable, not iterable, non-exhaustive `match` or unreachable branch, non-finite domain, chance out of place, assignment to something that is not state |
| E401–E406 | flow: duplicate or empty nodes, invalid members, unreachable transitions or `-> exit` outside a phase, nodes without an exit, `start` and `flow`, repeated or misplaced actions |
| E502–E507 | modules, mods and packages: `override` without `extends`, module not found, circular import, mods (E505), combinators (E506), dependencies (E507) |
| E601–E602 | tests: misplaced configuration, number of players |
| E701–E704 | presentation (`ui`): unknown target, hint not valid there, invalid arguments, repeated hint |
| E610–E614 | failures when running tests (`gamehub test`): an expectation does not hold, impossible move, chance, invariant, rule error |
| E900 | internal error: the generated IR is not valid (a GameHub bug) |
| W101 | `@size_visible` on something that is neither a zone nor a bag |
| W401–W407 | `gamehub check` warnings: unreachable node, transitions that may not cover every case, node without a path to an end, loop of automatic nodes without effects, possible information leak, unused declaration, shadowed transition (in hand-written IR) |

**Information leaks (W405, v1)**: hidden data that reaches state or events visible to everyone
(also through an `if`), that decides who plays or which node the match goes to, or on which the
legal moves of someone who cannot see it depend. The size of something whose size is visible does
not count, nor does the actor's part of an `@visible(owner)` variable (or of
`@visible(viewer == owner or …)`), nor what was revealed earlier with `reveal … to all` in the
same block.

## 16. Canonical formatting

`gamehub fmt` (idempotent, it keeps comments and the blank lines that separate them): 2-space
indentation, 100 columns, one declaration or statement per line, at most one blank line in a row.
A node with a single member, an action with a single simple statement and a transition with a
single simple statement go on one line if they fit. If an expression does not fit: after `=` or
`key:` the value moves to the next line (or, if it starts with a bracket and does not fit there
either, it opens on the same line and is split inside); an arithmetic chain spreads its operands
filling lines; an `and`/`or` chain, one per line; conditions followed by a block get double
indentation.

## 17. Differences from the Phase 0 RFC

| RFC (Phase 0) | v0.1 |
|---|---|
| `roll d6 into x`, `draw_random c from Z` | `x = roll(6)`, `x = random(xs)`, `x = sample(…)` |
| `payoff: table (…) { … }`, `zero_sum(winner: …)` | `match` / `case` and `win_loss(winner, win, loss)` |
| `action play(cards: subset(hand, size: 1..4))` | `action play(cards in subsets(items(hand[actor]), 1, 4))` |
| `move_all Z1 to Z2`, `log "…"` | `move all from Z1 to Z2`, `emit` |
| `mode: priority(order)`, `phase … for r in …`, `call Module.Subflow` | `mode: …` + `order: …`; phases with transitions; subflows: pending |
| `import std.tricktaking as tt` (alias), `roles`/`teams`, `deck` | pending (no aliases; roles and declarative decks will come with their phase) |
| `ui { … }` | presentation hints with a target (§12), since Phase 4 |

Related decisions: [ADR-017, ADR-018](decisions.md) (name and braces), ADR-027 to ADR-034
(implementation, Phase 2) and ADR-062, ADR-066 (Phase 6).
