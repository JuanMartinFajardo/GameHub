# SPDX-License-Identifier: Apache-2.0
"""Análisis estáticos (`gamehub check`): avisos del flow, fugas de información, declaraciones sin
usar y clasificación."""

from __future__ import annotations

from pathlib import Path

import pytest

from gamehub.analysis import classify, lint
from gamehub.cli import main
from gamehub.lang.compiler import compile_file, compile_text

ROOT = Path(__file__).resolve().parents[2]
GAMES = sorted((ROOT / "games").glob("*/*.game"))


def warnings(source: str) -> list[tuple[str, int]]:
    """(código, línea) de cada aviso de un juego que compila sin errores."""
    result = compile_text(source, "g.game")
    assert result.ok, [str(d) for d in result.diagnostics]
    return sorted((d.code, d.span.line) for d in result.diagnostics.warnings if d.span is not None)


def line(source: str, text: str, nth: int = 1) -> int:
    """Línea de la `nth`-ésima aparición de `text` en `source`."""
    pos = -1
    for _ in range(nth):
        pos = source.index(text, pos + 1)
    return source.count("\n", 0, pos) + 1


def game(flow: str, state: str = "x: Int = 0", extra: str = "") -> str:
    return (
        f"game G {{\n  players 2\n  state {{\n    {state}\n  }}\n{extra}  flow {{\n"
        f"    start -> A\n{flow}\n    terminal End {{ payoff: [0, 0] }}\n  }}\n}}\n"
    )


@pytest.mark.parametrize("path", GAMES, ids=lambda p: p.stem)
def test_the_games_have_no_warnings(path: Path) -> None:
    result = compile_file(path)
    assert [str(d) for d in result.diagnostics.warnings] == []


def test_unreachable_node() -> None:
    source = game(
        """    decision A {
      actor: 0
      action go() { x += 1 }
      -> End
    }
    decision Lost {
      actor: 1
      action go()
      -> End
    }"""
    )
    assert warnings(source) == [("W401", line(source, "Lost"))]


def test_dead_end() -> None:
    source = game(
        """    decision A {
      actor: 0
      action go() { x += 1 }
      -> B
    }
    decision B {
      actor: 1
      action go()
      -> A
    }"""
    )
    assert warnings(source) == [
        ("W401", line(source, "terminal End")),
        ("W403", line(source, "decision A")),  # desde A no se llega a ningún final
    ]


def test_guarded_transitions_may_not_cover_every_case() -> None:
    flow = """    decision A {{
      actor: 0
      action go() {{ x += 1 }}
      -> End when {first}
      -> A when {second}
    }}"""
    uncovered = game(flow.format(first="x > 2", second="x <= 1"))
    assert warnings(uncovered) == [("W402", line(uncovered, "-> A when"))]
    assert warnings(game(flow.format(first="x > 2", second="x <= 2"))) == []
    assert warnings(game(flow.format(first="x > 2", second="2 >= x"))) == []
    assert warnings(game(flow.format(first="x == 1", second="x != 1"))) == []


def test_enum_guards_can_be_exhaustive() -> None:
    flow = """    decision A {{
      actor: 0
      action go() {{ c = Blue }}
      -> End when c == Red
      -> A when {last}
    }}"""
    extra = "  enum Color { Red, Blue }\n"
    state = "c: Color = Red"
    covered = game(flow.format(last="c == Blue"), state, extra)
    assert warnings(covered) == []
    partial = game(flow.format(last="c == Red"), state, extra)
    assert warnings(partial) == [("W402", line(partial, "-> A when"))]


def test_loops_of_automatic_nodes_without_effects() -> None:
    flow = """    auto A {{
      -> B when x > 0
      -> End
    }}
    auto B {{
      {effect}-> A
    }}"""
    quiet = game(flow.format(effect=""))
    assert warnings(quiet) == [("W404", line(quiet, "auto A"))]
    assert warnings(game(flow.format(effect="x -= 1\n      "))) == []


def test_information_leaks() -> None:
    state = """@visible(owner)
    hand: per_player Int = 0
    @visible(none)
    secret: Int = 0
    shown: Int = 0"""
    flow = """    decision A {
      actor: 0
      action copy() { shown = secret }
      action tell() { emit said { v: secret } }
      action implicit() {
        if secret > 0 {
          shown = 1
        }
      }
      action peek() requires hand[1] > 0
      action own() requires hand[actor] >= 0 { shown = 1 }
      action mine() { shown = hand[actor] }
      -> End when secret > 5
      -> End
    }"""
    source = game(flow, state)
    assert warnings(source) == [
        ("W405", line(source, "copy")),  # secret → shown
        ("W405", line(source, "tell")),  # evento público con secret
        ("W405", line(source, "implicit")),  # if secret … shown = 1
        ("W405", line(source, "peek")),  # legalidad según la mano del otro
        ("W405", line(source, "mine")),  # la mano del actor, a la vista de todos
        ("W405", line(source, "-> End when")),  # el camino a End depende de secret
    ]


def test_revealing_to_everyone_is_not_a_leak() -> None:
    state = "@visible(none)\n    secret: Int = 0\n    shown: Int = 0"
    revealed = """    decision A {
      actor: 0
      action open() {
        reveal secret to all
        shown = secret
      }
      -> End
    }"""
    assert warnings(game(revealed, state)) == []
    late = revealed.replace(
        "reveal secret to all\n        shown = secret",
        "shown = secret\n        reveal secret to all",
    )
    source = game(late, state)
    assert warnings(source) == [("W405", line(source, "open"))]


def test_who_plays_can_leak() -> None:
    state = "@visible(none)\n    secret: Int = 0"
    flow = """    decision A {
      actor: secret % 2
      action go()
      -> End
    }"""
    source = game(flow, state)
    assert warnings(source) == [("W405", line(source, "decision A"))]


def test_unused_declarations_and_uses_in_tests() -> None:
    source = """game G {
  players 2
  params {
    unused: Int = 3
    used_in_test: Int = 1
  }
  enum Lonely { One }
  state {
    x: Int = 0
    idle: Int = 0
  }
  fn helper() -> Int = 1
  fn tested() -> Int = used_in_test
  flow {
    start -> A
    decision A {
      actor: 0
      action go() { x += helper() }
      -> End
    }
    terminal End { payoff: [x, -x] }
  }
  test "t" {
    expect tested() == 1
  }
}
"""
    assert warnings(source) == [
        ("W406", line(source, "unused")),
        ("W406", line(source, "Lonely")),
        ("W406", line(source, "idle")),
    ]


def test_classification() -> None:
    def labels(name: str) -> list[str]:
        result = compile_file(ROOT / "games" / name / f"{name}.game")
        return classify(result.game().ir).labels()

    assert labels("kuhn-poker") == [
        "2 jugadores",
        "azar",
        "información imperfecta",
        "por turnos",
        "suma cero",
    ]
    assert labels("nim") == [
        "2 jugadores",
        "determinista",
        "información perfecta",
        "por turnos",
        "suma cero",
    ]
    assert labels("prisoners-dilemma")[2:] == ["información imperfecta", "jugadas simultáneas"]
    assert labels("mentiroso")[0] == "3–6 jugadores"


def test_lint_works_on_plain_ir() -> None:
    ir = compile_file(ROOT / "games" / "nim" / "nim.game").game().ir
    assert lint(ir) == []
    ir["flow"]["nodes"].append(
        {"id": "Orphan", "kind": "terminal", "payoff": ["fill", ["const", 0]]}
    )
    assert [(f.code, f.where) for f in lint(ir)] == [("W401", ("node", "Orphan"))]
    # En Nomos, una transición sin condición seguida de otras es un error (E403); en una IR
    # escrita a mano es un aviso.
    ir["flow"]["nodes"].pop()
    move = next(n for n in ir["flow"]["nodes"] if n["kind"] == "decision")
    move["transitions"].insert(0, {"to": move["transitions"][-1]["to"]})
    assert ("W407", ("transition", move["id"], "1")) in [(f.code, f.where) for f in lint(ir)]


def test_check_command_shows_warnings_and_classification(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "g.game"
    path.write_text(
        game("    decision A {\n      actor: 0\n      action go()\n      -> End when x > 0\n    }"),
        encoding="utf-8",
    )
    assert main(["check", str(path)]) == 0  # los avisos no hacen fallar
    out = capsys.readouterr().out
    assert "aviso[W402]" in out
    assert "· 1 aviso" in out
    assert "2 jugadores · determinista · información perfecta · por turnos · suma cero" in out
