# SPDX-License-Identifier: Apache-2.0
"""Módulos de Nomos (`import`) y biblioteca estándar v0."""

from __future__ import annotations

from pathlib import Path

import pytest

from gamehub.lang.compiler import compile_file, compile_text
from gamehub.lang.modules import stdlib_dir
from gamehub.lang.printer import format_source
from gamehub.lang.source import Source
from gamehub.lang.testing import GameTester

FIXTURES = Path(__file__).resolve().parent / "fixtures"
STDLIB = sorted((stdlib_dir() / "std").glob("*.game"))

GAME = """game G {{
  players 2
  state {{
    {state}
  }}
  flow {{
    start -> End
    terminal End {{ payoff: [0, 0] }}
  }}
}}
"""


def errors(text: str, name: str = "g.game") -> list[str]:
    result = compile_text(text, name)
    return [f"{d.code} {d.message}" for d in result.diagnostics.errors]


@pytest.mark.parametrize("path", STDLIB, ids=lambda p: p.stem)
def test_stdlib_modules_check_and_are_formatted(path: Path) -> None:
    result = compile_file(path)
    assert result.ok, [str(d) for d in result.diagnostics]
    assert not result.diagnostics.warnings
    text = path.read_text(encoding="utf-8")
    assert format_source(Source(str(path), text)) == text, "ejecuta: gamehub fmt stdlib"


def test_stdlib_behaves_as_documented() -> None:
    report = GameTester(compile_file(FIXTURES / "stdlib.game").game()).run_all()
    assert [str(t.failure) for t in report.tests if t.failure] == []
    # Un test por módulo de la biblioteca estándar.
    modules = sorted(f"std.{p.stem}" for p in (stdlib_dir() / "std").glob("*.game"))
    assert sorted(t.name for t in report.tests) == modules


def test_only_what_is_used_reaches_the_ir() -> None:
    text = "import std.cards.{Card, french52}\n\n" + GAME.format(
        state="deck: Zone<Card> = french52()"
    )
    ir = compile_text(text).game().ir
    assert [t["name"] for t in ir["types"]] == ["Suit", "Rank", "Card"]
    assert [f["name"] for f in ir["functions"]] == ["french52"]


def test_star_imports_what_the_module_declares() -> None:
    text = "import std.dice.*\n\n" + GAME.format(state="n: Int = count_face(faces(6), 2)")
    assert errors(text) == []


def test_import_errors() -> None:
    state = "x: Int = 0"
    missing_module = errors("import std.cartas.{Card}\n\n" + GAME.format(state=state))
    assert missing_module == ["E503 módulo no encontrado: std.cartas"]
    missing_name = compile_text("import std.cards.{french53}\n\n" + GAME.format(state=state))
    [d] = missing_name.diagnostics.errors
    assert d.message == "el módulo std.cards no tiene `french53`"
    assert d.help == "¿quisiste decir `french52`?"
    clash = errors("import std.cards.{Suit}\n\nenum Suit { A, B }\n\n" + GAME.format(state=state))
    assert clash == ["E202 `Suit` choca con el importado de std.cards"]


def test_relative_and_transitive_imports(tmp_path: Path) -> None:
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "poker.game").write_text(
        "import std.cards.{Card, rank_value}\n\n"
        "/// Suma de los rangos de una mano.\n"
        "fn points(cards: List<Card>) -> Int = sum(c in cards : rank_value(c.rank))\n",
        encoding="utf-8",
    )
    game = tmp_path / "g.game"
    game.write_text(
        "import lib.poker.{points}\n\n" + GAME.format(state="score: Int = points([])"),
        encoding="utf-8",
    )
    result = compile_file(game)
    assert result.ok, [str(d) for d in result.diagnostics]
    ir = result.game().ir
    assert [f["name"] for f in ir["functions"]] == ["rank_value", "points"]
    assert {t["name"] for t in ir["types"]} == {"Card", "Suit", "Rank"}


def test_circular_imports(tmp_path: Path) -> None:
    (tmp_path / "a.game").write_text("import b.{g}\n\nfn f() -> Int = g()\n", encoding="utf-8")
    (tmp_path / "b.game").write_text("import a.{f}\n\nfn g() -> Int = 1\n", encoding="utf-8")
    result = compile_file(tmp_path / "a.game")
    assert [d.code for d in result.diagnostics.errors] == ["E504"]
    assert "a → b → a" in result.diagnostics.errors[0].message


def test_the_same_name_from_two_modules(tmp_path: Path) -> None:
    (tmp_path / "one.game").write_text("fn f() -> Int = 1\n", encoding="utf-8")
    (tmp_path / "two.game").write_text("fn f() -> Int = 2\n", encoding="utf-8")
    game = tmp_path / "g.game"
    game.write_text(
        "import one.{f}\nimport two.{f}\n\n" + GAME.format(state="x: Int = f()"),
        encoding="utf-8",
    )
    result = compile_file(game)
    assert [d.message for d in result.diagnostics.errors] == [
        "`f` se importa de dos módulos: one y two"
    ]


def test_module_functions_cannot_read_game_state(tmp_path: Path) -> None:
    (tmp_path / "bad.game").write_text("fn f() -> Int = turn\n", encoding="utf-8")
    result = compile_file(tmp_path / "bad.game")
    assert not result.ok


def test_module_functions_have_their_own_scope(tmp_path: Path) -> None:
    """Los parámetros de una función de módulo pueden llamarse como cosas del juego que la usa."""
    (tmp_path / "lib.game").write_text(
        "fn twice(score: Int) -> Int = 2 * score\n", encoding="utf-8"
    )
    game = tmp_path / "g.game"
    game.write_text(
        "import lib.{twice}\n\n" + GAME.format(state="score: Int = twice(2)"), encoding="utf-8"
    )
    assert compile_file(game).ok
    (tmp_path / "peek.game").write_text("fn peek() -> Int = score\n", encoding="utf-8")
    game.write_text(
        "import peek.{peek}\n\n" + GAME.format(state="score: Int = peek()"), encoding="utf-8"
    )
    [error] = compile_file(game).diagnostics.errors
    assert error.message == "una función de módulo no ve el estado del juego (`score`)"


def test_a_game_can_reuse_the_names_of_module_parameters() -> None:
    """std.tricktaking tiene un parámetro `led`; un juego que lo importa puede tener su propia
    función `led` (dentro del módulo, lo que declara el juego no existe)."""
    text = "import std.tricktaking.{can_play}\n\n" + GAME.format(state="x: Int = 0").replace(
        "  flow {",
        "  fn led() -> Int = 0\n  fn ok() -> Bool = can_play([led()], 0, led())\n  flow {",
    )
    assert compile_text(text).ok
