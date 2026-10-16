# GameHub

**GitHub for games.** A platform and a protocol to:

1. **Design** games axiomatically, with the **Nomos** language (`.game` files) or with a visual
   flow-chart editor — two views of the same formal specification.
2. **Run** them as a pure input/output API, with hidden information, chance, simultaneity and
   time modeled precisely.
3. **Play** them locally, on a LAN or online from any interface (generic, official or custom).
4. **Study** them: trees, minimax, Nash equilibria, Pareto, the matrix form, combinatorial game
   theory, heuristics, bots, an arena and reinforcement learning.
5. **Collaborate**: publish, clone, fork and propose rule changes with semantic diffs.

> Status: **Phase 6 complete — catalog wave 2** (≈ 59 %). Games are designed in Nomos or in the
> **Studio** (diagram and text at once, with a simulator), and played in the terminal, over the
> network (rooms with a code, a link and a QR code on the LAN) and in a web app, also on phones.
> The catalog has 23 games, among them **chess, Skat, Texas Hold'em, Wizard, Parchís, Solitaire
> and Bullshit**; any of them can be played with the generic interface, and seven (tic-tac-toe,
> Connect Four, Dudo, chess, Hold'em, Wizard and Parchís) also have their own.

## Documentation

- 📚 [Project wiki](docs/wiki/README.md) — vision, specifications, architecture, roadmap
- 🗺️ [Roadmap 0 → 100 %](docs/wiki/roadmap.md)
- 📝 [Work log](log.md)

## Development

```bash
pnpm install && pnpm build                       # the web apps (Node 22 + pnpm, at the root)
cd python
uv sync                                          # Python environment (3.12+)
uv run gamehub studio ../games --open            # the Studio: design with diagram and text, simulate
uv run gamehub serve ../games --open             # match server and the app in the browser
uv run gamehub host ../games/dudo --players 4    # a room on the LAN (the others: gamehub join)
uv run gamehub play ../games/nim --seats human,random   # in the terminal, against a bot
uv run gamehub check ../games && uv run gamehub test ../games
uv run gamehub perft ../games/chess --depth 4 --jobs 6   # count the legal move sequences
uv run pytest                                    # Python tests (and pnpm test, the web ones)
```

Licenses: Apache-2.0 in general; see [`LICENSING.md`](LICENSING.md).

## What a game looks like

```game
game TicTacToe {
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

  ui {
    board: grid
    turn: hidden
    Mark: symbols(X: "✕", O: "◯"), colors(X: "#e53935", O: "#1e88e5")
  }
}
```

A complete example, with tests and invariants: [`games/tictactoe`](games/tictactoe/tictactoe.game).
Language reference: [Nomos](docs/wiki/language.md).
