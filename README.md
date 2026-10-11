# GameHub

**GitHub para juegos.** Una plataforma y un protocolo para:

1. **Diseñar** juegos de forma axiomática, con el lenguaje **Nomos** (archivos `.game`) o con un editor visual de
   diagramas de flujo — dos vistas de la misma especificación formal.
2. **Ejecutarlos** como una API pura de entradas y salidas, con información oculta, azar,
   simultaneidad y tiempo modelados con precisión.
3. **Jugarlos** en local, en LAN u online desde cualquier interfaz (genérica, oficial o propia).
4. **Estudiarlos**: árboles, minimax, equilibrios de Nash, Pareto, forma matricial, teoría
   combinatoria, heurísticas, bots, arena y aprendizaje por refuerzo.
5. **Colaborar**: publicar, clonar, bifurcar y proponer cambios de reglas con diffs semánticos.

> Estado: **Fase 4 — se juega en el navegador** (≈ 41 %). Los juegos se escriben en Nomos y se
> juegan en la terminal, en red (salas con código, enlace y QR en la LAN) y en una app web, también
> en el móvil: cualquier juego del catálogo con la interfaz genérica, y el tres en raya, Conecta 4
> y Dudo con la suya propia.

## Documentación

- 📚 [Wiki del proyecto](docs/wiki/README.md) — visión, especificaciones, arquitectura, roadmap
- 🗺️ [Roadmap 0 → 100 %](docs/wiki/roadmap.md)
- 📝 [Registro de trabajo](log.md)

## Desarrollo

```bash
pnpm install && pnpm build                       # la app web (Node 22 + pnpm, en la raíz)
cd python
uv sync                                          # entorno de Python (3.12+)
uv run gamehub serve ../games --open             # servidor de partidas y la app en el navegador
uv run gamehub host ../games/dudo --players 4    # una sala en la LAN (los demás: gamehub join)
uv run gamehub play ../games/nim --seats human,random   # en la terminal, contra un bot
uv run gamehub check ../games && uv run gamehub test ../games
uv run pytest                                    # tests de Python (y pnpm test, los de la web)
```

Licencias: Apache-2.0 en general; ver [`LICENSING.md`](LICENSING.md).

## Así es un juego

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

Ejemplo completo, con tests e invariantes: [`games/tictactoe`](games/tictactoe/tictactoe.game).
Referencia del lenguaje: [Nomos](docs/wiki/lenguaje-game.md).
