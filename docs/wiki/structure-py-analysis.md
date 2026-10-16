# Analysis of the `structure.py` prototype

`structure.py` (repository root, 141 lines, May 2026) is the first attempt at formalizing
GameHub. **It is kept unmodified** as a historical reference. This document records which
intuitions are kept, what problems it has and how each concept translates into the new model.

## 1. Sound intuitions that are kept

| Concept in `structure.py` | Underlying idea (sound) | Equivalent in GameHub |
|---|---|---|
| `GameState.global_variables` | The game has an explicit state | **Typed state schema** (`state { … }`) |
| `variable_permissions` (`'card': ['player1']`) | Information is part of the rules | **Visibility policies** (`@visible(owner)`, `@visible(all)`…) |
| `Player_Category` (white/black, teams) | Roles with different permissions | **Roles and teams** (`roles`, `teams`) |
| `Flowchart`, `Node`, `current_node` | The game is a flow chart | **Flow**: a hierarchical statechart of typed nodes |
| `Node.sequential` / `Action.multiplayer` | Sequential vs. simultaneous turns | Node kinds `decision`, `simultaneous`, `window` |
| `action_activation_functions` | An action is only legal if a condition holds | Action **guards** (`requires …`) |
| `players_activation_functions` | Who may act depends on the state | The node's `actor:` / `actors:` expressions |
| `Action.action_parameters` | Actions carry parameters (which card…) | **Typed parameters with a domain** (`play(c: Card in hand[actor])`) |
| `modification_function` → `{'variables_to_update', 'permissions_to_update'}` | Effects are *data* (a state diff) | **Declarative effects** (assignments, `move`, `reveal`…) |
| `Node.terminal` | There are final states | `terminal` nodes with **payoffs** |
| `game_history` | A record of what happened | **Event log** + **replay** format |
| `get_action(player)` separate from the engine | Player input is external | **Protocol** (`act`) and the `Agent` interface |

The most valuable intuition: **effects return a dictionary of changes instead of mutating the state
by hand**. Generalized, this is exactly what allows rules to be analyzable data.

## 2. Problems found

### Bugs that prevent running it
1. **L44** `GameState('game_state')`: `__new__(cls)` takes no arguments → `TypeError` on import.
2. **L99–106** `apply_action(self, actions, players, parameters)` uses `action` (undefined); it
   returns after the first player and ignores the rest; it never uses `parameters`.
3. **L95–97 / L101** the default activation functions are `None`; calling them raises
   `TypeError`. Also, the documented signature `(state, player, extra)` does not match the call
   `(state, player)`.
4. **L52–57** `Player.category`: `categories = []` is reset *inside* the loop (it only returns the
   last category) and raises `UnboundLocalError` when there are no categories.
5. **L40–41** `update_history` does a `deepcopy` and discards the result; `game_history` is never
   filled.
6. **L131–141** `run_game` is incomplete; the non-sequential branch asks for and applies actions
   player by player (it is not truly simultaneous) and the sequential branch is missing.

### Design problems (the important ones)
1. **State singleton.** Only *one* match can exist per process. Simulating branches (minimax,
   MCTS), training in parallel (RL) or serving several rooms is impossible. → **Immutable
   states**: `s' = apply(s, a)`; any number of states can coexist.
2. **Rules as arbitrary Python functions.** They cannot be serialized, ported to C++/the browser,
   run safely on a server or analyzed. → A **pure, typed expression language**.
3. **`Action.end` fixes the destination.** The transition cannot depend on the state ("if someone
   wins, go to End; otherwise, next turn"). → **Transitions with guards** evaluated in order.
4. **Visibility at the level of a whole variable.** It cannot express "the number of cards in your
   hand is public, but which ones is not", per-player variables, cards changing zones or revealing
   at a given moment. → **Visibility per location** (variable, zone, component, event) and
   **state-dependent**.
5. **Essential concepts are missing:** chance (a *nature* player with distributions), payoffs and
   outcomes, parameters/variants, a variable number of players, time (clocks, deadlines),
   reaction windows (Bullshit!), rules that depend on history (threefold repetition).
6. **I/O mixed with the engine** (`get_action` inside `run_game`). → The engine is a pure
   function; the match loop lives in a *driver* (server, CLI, simulator, trainer).
7. **The concept of "player" mixed up with "seat".** → **Seats** (positions in the rules:
   0..n-1) are distinguished from **participants** (a human, bot or spectator occupying a seat).

## 3. The same spirit, in the new model

What `structure.py` was trying to express, written with the planned Python API (which generates
IR rather than running lambdas):

```python
from gamehub.build import Game, Seat, Enum, Grid, opt

g = Game("TicTacToe", players=2)
Mark = g.enum("Mark", ["X", "O"])
board = g.state("board", Grid(3, 3, opt(Mark)), init=None)          # public by default
turn  = g.state("turn", Seat, init=0)

move = g.decision("Move", actor=turn)
c = move.action("place", c=board.cells()).requires(board[c].is_none())
c.effect(board[c].set(Mark.of_seat(turn)))
move.to("Win",  when=board.has_line(Mark.of_seat(turn), length=3))
move.to("Draw", when=board.is_full())
move.to("Move", effect=turn.set(turn.next()))

g.terminal("Win",  payoff=g.zero_sum(winner=turn))
g.terminal("Draw", payoff=0)
g.start("Move")

ir = g.build()        # → GameIR (canonical JSON), identical to the one the .game text produces
```

See the [Formal model](formal-model.md) and the [`.game` language](language.md).
