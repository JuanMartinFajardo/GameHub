# SPDX-License-Identifier: Apache-2.0
"""Lo que hace el motor de referencia para ir más rápido sin cambiar ningún resultado: guardar
los resultados de las funciones puras, perft y partidas aleatorias en varios procesos."""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import pytest

from gamehub.analysis.perft import divide, perft, perft_parallel
from gamehub.engine import Game, RuleError, load_game
from gamehub.engine.game import _memo_kinds
from gamehub.engine.match import fuzz, fuzz_parallel
from gamehub.engine.values import TypeTable
from gamehub.ir.spec import examples_dir
from gamehub.lang.compiler import compile_source
from gamehub.lang.source import Source

ROOT = Path(__file__).resolve().parents[2]


def nomos(text: str) -> Game:
    result = compile_source(Source("<test>", text, None))
    assert result.ok, [str(d) for d in result.diagnostics.errors]
    return Game(result.game().ir)


def fn(name: str, body: Any) -> dict[str, Any]:
    return {"name": name, "params": [], "returns": "Int", "body": body}


def test_memo_kinds() -> None:
    loop = ["count", "x", ["range", ["const", 1], ["const", 3]], ["const", True]]
    kinds = _memo_kinds(
        [
            fn("table", loop),  # solo sus argumentos: para siempre
            fn("reads", ["add", ["var", "n"], ["call", "table"]]),  # el estado: mientras no cambie
            fn("cheap", ["var", "n"]),  # sin bucles ni llamadas: no compensa
            fn("where", ["if", ["at", "Move"], loop, ["const", 0]]),  # depende del nodo
            fn("caller", ["call", "where"]),  # …también a través de otra función
            fn("seats", ["count", "s", ["seats"], ["const", True]]),  # el número de asientos
        ]
    )
    assert kinds == {
        "table": "static",
        "reads": "state",
        "cheap": None,
        "where": None,
        "caller": None,
        "seats": "state",
    }


COUNTER = """
game Counter {
  players 1
  state { n: Int = 0 }
  fn evens() -> Int = count(i in 1..n : i % 2 == 0)
  flow {
    start -> Step
    decision Step {
      actor: 0
      action add(k in 1..3) { n += k }
      -> End when evens() >= 3
      -> Step
    }
    terminal End { payoff: [evens()] }
  }
}
"""


def test_the_memo_is_emptied_when_the_state_changes() -> None:
    game = nomos(COUNTER)
    s = game.new_state()
    seen = []
    from gamehub.engine import Action

    while not s.is_terminal:
        seen.append(s.evaluate(["call", "evens"]))
        s = s.apply_action(0, Action.of("add", k=1))
    assert seen == [0, 0, 1, 1, 2, 2] and s.payoffs == (3,)


def test_a_grid_can_be_assigned_its_rows() -> None:
    game = nomos("""
game Rows {
  players 1
  state { g: Grid[2, 2] of Int = 0 }
  flow {
    start { g = [[1, 2], [3, 4]] } -> End
    terminal End { payoff: [g[(1, 0)]] }
  }
}
""")
    assert game.new_state().payoffs == (3,)
    bad = nomos("""
game Bad {
  players 1
  state { g: Grid[2, 2] of Int = 0 }
  flow {
    start { g = [[1, 2, 3]] } -> End
    terminal End { payoff: [0] }
  }
}
""")
    with pytest.raises(RuleError, match="2 filas de 2"):
        bad.new_state()


def tictactoe() -> Game:
    return load_game(examples_dir() / "tictactoe.ir.json")


def test_perft_counts_move_sequences() -> None:
    root = tictactoe().new_state()
    assert [perft(root, d) for d in range(4)] == [1, 9, 72, 504]
    first = divide(root, 2)
    assert len(first) == 9 and all(count == 8 for _, count in first)
    assert perft_parallel(tictactoe, 4, jobs=2) == 3024


def test_parallel_fuzz_gives_the_same_report() -> None:
    loader = functools.partial(load_game, examples_dir() / "kuhn-poker.ir.json")
    one = fuzz(loader(), 60, seed=5)
    many = fuzz_parallel(loader, 60, jobs=2, seed=5, chunk=7)
    assert (many.games, many.completed, many.total_steps) == (
        one.games,
        one.completed,
        one.total_steps,
    )
    assert many.payoff_sums == one.payoff_sums and many.errors == one.errors == []


# --- Código generado -----------------------------------------------------------------------------

GAMES = sorted(p for p in (ROOT / "games").glob("*/*.game") if p.parent.name != "tests")


def test_codegen_covers_every_operator() -> None:
    from gamehub.engine import codegen
    from gamehub.engine.expr import FAST, OPERATORS, PURE, REDUCERS, SEATED

    unit = codegen._Unit(codegen.Codegen(TypeTable([]), {}, {}), mode="env")
    special = {name[3:] for name in dir(unit) if name.startswith("op_")}
    covered = special | set(PURE) | set(SEATED) | set(FAST) | set(REDUCERS)
    assert set(OPERATORS) <= covered


@pytest.mark.parametrize("path", GAMES, ids=lambda p: p.parent.name)
def test_generated_code_plays_exactly_like_the_closures(path: Path) -> None:
    """Las mismas partidas al azar con el código generado y con los cierres: la misma huella en
    cada paso (y las mismas jugadas legales)."""
    from gamehub.engine.match import RandomAgent, play_match
    from gamehub.lang.compiler import compile_file

    ir = compile_file(path).game().ir
    fast, slow = Game(ir, codegen=True), Game(ir, codegen=False)
    games = 1 if path.parent.name in ("chess", "solitaire", "mentiroso") else 3
    for seed in range(games):
        traces: list[list[tuple[str, int]]] = []
        for game_ in (fast, slow):
            trace: list[tuple[str, int]] = []
            n = game_.players[0]
            play_match(
                game_,
                [RandomAgent(seed, s) for s in range(n)],
                seed=seed,
                max_steps=300,
                on_step=lambda st, t=trace: t.append(
                    (
                        st.digest(),
                        len(st.legal_actions(st.active_seats[0])) if st.active_seats else 0,
                    )
                ),
            )
            traces.append(trace)
        assert traces[0] == traces[1]
