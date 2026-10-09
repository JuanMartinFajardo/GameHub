# SPDX-License-Identifier: Apache-2.0
"""Mods (`extends`, `override`, `remove`, `extend node`) y combinadores (`repeat`, `best_of`)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from gamehub.ir.hashing import rules_hash
from gamehub.lang.compiler import CompileResult, compile_file
from gamehub.lang.testing import GameTester

GAMES = Path(__file__).resolve().parents[2] / "games"


@pytest.fixture
def workdir(tmp_path: Path) -> Path:
    for name in ("tictactoe", "prisoners-dilemma"):
        shutil.copy(GAMES / name / f"{name}.game", tmp_path)
    return tmp_path


def compile_with(workdir: Path, text: str) -> CompileResult:
    path = workdir / "variants.game"
    path.write_text(text, encoding="utf-8")
    return compile_file(path)


def passes(result: CompileResult) -> None:
    assert result.ok, [str(d) for d in result.diagnostics]
    for compiled in result.games.values():
        report = GameTester(compiled).run_all(playouts=3)
        assert [str(t.failure) for t in report.tests if t.failure] == []
        assert report.playouts.failure is None, str(report.playouts.failure)


def errors(result: CompileResult) -> list[str]:
    return [f"{d.code} {d.message}" for d in result.diagnostics.errors]


def test_override_extend_and_new_declarations(workdir: Path) -> None:
    result = compile_with(
        workdir,
        """import tictactoe.{TicTacToe}

game Misere extends TicTacToe {
  meta { title: "Tres en raya inverso" }
  override terminal Win { payoff: win_loss(turn, -1, 1) }

  test "hacer línea pierde" {
    play place((0, 0)), place((0, 1)), place((1, 1)), place((0, 2)), place((2, 2))
    expect at(Win) and payoff == [-1, 1]
  }
}

game WithPass extends TicTacToe {
  state {
    passed: per_player Bool = false
  }
  extend node Move {
    action skip() requires not passed[actor] { passed[actor] = true }
  }

  test "se puede pasar una vez" {
    play skip(), skip()
    expect illegal skip()
  }
}

game Bigger extends TicTacToe {
  params {
    size: Int = 4
  }
  override state {
    board: Grid[size, size] of Mark? = none
  }
  override fn wins(m: Mark) -> Bool =
    any(line in lines(board, size) : all(c in line : board[c] == m))

  test "cuatro en diagonal" {
    play place((0, 0)), place((0, 1)), place((1, 1)), place((0, 2)), place((2, 2)), place((0, 3))
    play place((3, 3))
    expect at(Win) and payoff == [1, -1]
  }
}
""",
    )
    passes(result)
    misere = result.game("Misere").ir
    assert misere["game"] == {"id": "misere", "version": "0.1.0"}
    assert misere["meta"]["title"] == "Tres en raya inverso"


def test_the_base_does_not_change(workdir: Path) -> None:
    alone = compile_file(workdir / "tictactoe.game").game().ir
    result = compile_with(
        workdir,
        """game Base {
  players 2
  state { x: Int = 0 }
  flow {
    start -> A
    decision A {
      actor: 0
      action go() { x += 1 }
      -> End when x > 2
      -> A
    }
    terminal End { payoff: [x, -x] }
  }
}

game Variant extends Base {
  extend node A {
    action jump() { x += 2 }
    -> End when x == 2
  }
  remove action A.go
}
""",
    )
    assert result.ok, [str(d) for d in result.diagnostics]
    base, variant = result.game("Base").ir, result.game("Variant").ir
    assert [a["name"] for a in base["flow"]["nodes"][0]["actions"]] == ["go"]
    node = variant["flow"]["nodes"][0]
    assert [a["name"] for a in node["actions"]] == ["jump"]
    assert [t["to"] for t in node["transitions"]] == ["End", "End", "A"]  # las nuevas, delante
    assert rules_hash(compile_file(workdir / "tictactoe.game").game().ir) == rules_hash(alone)


def test_override_params_with_asserts_replaces_the_constraints(workdir: Path) -> None:
    result = compile_with(
        workdir,
        """import prisoners_dilemma.{PrisonersDilemma}

/// La caza del ciervo: cooperar es lo mejor si el otro coopera, pero arriesgado.
game StagHunt extends PrisonersDilemma {
  override params {
    T: Real = 3
    R: Real = 4
    P: Real = 2
    S: Real = 0
    assert R > T and T >= P and P > S
  }

  test "cazar juntos" {
    play 0: choose(Cooperate), 1: choose(Cooperate)
    expect payoff == [4, 4]
  }
}
""",
    )
    passes(result)
    assert len(result.game().ir["constraints"]) == 1


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("override fn nope() -> Int = 1", "E505 la función `nope` no existe en el juego base"),
        (
            "override terminal Lose { payoff: fill(0) }",
            "E505 el nodo `Lose` no existe en el juego base",
        ),
        ("fn full() -> Bool = true", "E505 la función `full` ya existe en el juego base"),
        ("state {\n    turn: Seat = 1\n  }", "E505 la variable `turn` ya existe en el juego base"),
        ("remove node Nowhere", "E505 el nodo `Nowhere` no existe en el juego base"),
        ("remove action Move.jump", "E505 la acción `Move.jump` no existe en el juego base"),
        (
            "extend node Move {\n    actor: 1\n  }",
            "E505 extend node solo añade acciones y transiciones",
        ),
    ],
)
def test_mod_errors(workdir: Path, body: str, expected: str) -> None:
    result = compile_with(
        workdir, f"import tictactoe.{{TicTacToe}}\n\ngame V extends TicTacToe {{\n  {body}\n}}\n"
    )
    assert expected in errors(result)


def test_removed_nodes_leave_dangling_transitions(workdir: Path) -> None:
    result = compile_with(
        workdir,
        "import tictactoe.{TicTacToe}\n\ngame V extends TicTacToe {\n  remove node Draw\n}\n",
    )
    assert any("Draw" in e for e in errors(result))


def test_inheritance_cycles_and_unknown_bases(workdir: Path) -> None:
    cycle = compile_with(workdir, "game A extends B {\n}\n\ngame B extends A {\n}\n")
    assert any(e.startswith("E505 un juego no puede basarse en sí mismo") for e in errors(cycle))
    unknown = compile_with(workdir, "game A extends Nothing {\n}\n")
    assert errors(unknown) == ["E201 juego desconocido: Nothing"]


def test_repeat_and_best_of(workdir: Path) -> None:
    result = compile_with(
        workdir,
        """import prisoners_dilemma.{PrisonersDilemma}

game IteratedPD = repeat(PrisonersDilemma, rounds: 3, payoff: sum)
game MeanPD = repeat(PrisonersDilemma, rounds: 3, payoff: mean)
game Match = best_of(PrisonersDilemma, rounds: 3)

game IteratedPDChecked extends IteratedPD {
  test "cooperar siempre da 9 a cada uno" {
    play 0: choose(Cooperate), 1: choose(Cooperate)
    play 0: choose(Cooperate), 1: choose(Cooperate)
    play 0: choose(Cooperate), 1: choose(Cooperate)
    expect payoff == [9, 9] and round == 3
  }
}

game MeanPDChecked extends MeanPD {
  test "la media de tres rondas" {
    play 0: choose(Defect), 1: choose(Cooperate)
    play 0: choose(Cooperate), 1: choose(Cooperate)
    play 0: choose(Defect), 1: choose(Defect)
    expect payoff == [3, rat(4, 3)]
  }
}

game MatchChecked extends Match {
  test "dos rondas ganadas bastan" {
    play 0: choose(Defect), 1: choose(Cooperate)
    play 0: choose(Defect), 1: choose(Cooperate)
    expect payoff == [1, -1] and round == 2
  }
}
""",
    )
    passes(result)
    ir = result.game("IteratedPD").ir
    assert ir["meta"]["title"]["es"] == "Dilema del prisionero (3 rondas)"
    assert ir["params"][-1] == {"name": "rounds", "type": "Int", "default": ["const", 3]}


@pytest.mark.parametrize(
    ("alias", "expected"),
    [
        ("twice(PrisonersDilemma, rounds: 2)", "E506 combinador desconocido: twice"),
        ("repeat(PrisonersDilemma)", "E506 repeat necesita rounds: <número de rondas>"),
        ("repeat(PrisonersDilemma, rounds: 0)", "E506 rounds tiene que ser un entero positivo"),
        ("repeat(PrisonersDilemma, rounds: 2, payoff: max)", "E506 payoff es sum o mean"),
        (
            "best_of(PrisonersDilemma, rounds: 3, payoff: sum)",
            "E506 best_of no tiene el argumento `payoff`",
        ),
        ("repeat(Nothing, rounds: 2)", "E201 juego desconocido: Nothing"),
    ],
)
def test_combinator_errors(workdir: Path, alias: str, expected: str) -> None:
    result = compile_with(
        workdir, f"import prisoners_dilemma.{{PrisonersDilemma}}\n\ngame G = {alias}\n"
    )
    assert errors(result) == [expected]
