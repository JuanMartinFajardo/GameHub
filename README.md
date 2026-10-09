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

> Estado: **Fase 0 completada** (≈ 4 %). Ya existe la especificación formal de la IR
> ([`spec/`](spec/README.md)) con cuatro juegos de validación y un validador en Python. Todavía
> no se puede jugar: eso llega con el motor de la Fase 1.

## Documentación

- 📚 [Wiki del proyecto](docs/wiki/README.md) — visión, especificaciones, arquitectura, roadmap
- 🗺️ [Roadmap 0 → 100 %](docs/wiki/roadmap.md)
- 📝 [Registro de trabajo](log.md)

## Desarrollo

```bash
cd python
uv sync                                                  # entorno (Python 3.12+)
uv run gamehub ir check ../spec/ir/examples/*.ir.json    # validar juegos en IR
uv run pytest                                            # tests
```

Licencias: Apache-2.0 en general; ver [`LICENSING.md`](LICENSING.md).

## Así se verá un juego

```game
game TicTacToe {
  players 2
  enum Mark { X, O }
  state { board: Grid[3, 3] of Mark? = none;  turn: Seat = 0 }
  // funciones mark, wins y full: ver el ejemplo completo en docs/wiki/lenguaje-game.md

  flow {
    start -> Move
    decision Move {
      actor: turn
      action place(c: Cell(board)) requires board[c] == none { board[c] = mark(turn) }
      -> Win  when wins(mark(turn))
      -> Draw when full(board)
      -> Move { turn = next(turn) }
    }
    terminal Win  { payoff: zero_sum(winner: turn) }
    terminal Draw { payoff: all(0) }
  }
}
```

```bash
gamehub check tictactoe.game          # tipos, alcanzabilidad, fugas de información
gamehub analyze tictactoe --solve     # → empate con juego perfecto
gamehub host tictactoe                # → código de sala K7F-Q2P
```
