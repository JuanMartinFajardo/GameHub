# SPDX-License-Identifier: Apache-2.0
"""Comprobador de Nomos y traducción a GameIR."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from gamehub.cli import main
from gamehub.engine import load_game
from gamehub.engine.match import fuzz
from gamehub.ir.hashing import rules_hash
from gamehub.ir.spec import examples_dir, load_json
from gamehub.lang.compiler import CompileResult, compile_file, compile_text, load_nomos
from gamehub.lang.diagnostics import CompileError

GAMES = sorted((Path(__file__).resolve().parents[2] / "games").glob("*/*.game"))
F1_GAMES = [p for p in GAMES if (examples_dir() / f"{p.stem}.ir.json").exists()]


def game(decls: str = "", nodes: str = "", players: str = "players 2") -> str:
    nodes = nodes or "terminal A { payoff: fill(0) }"
    return f"game T {{\n  {players}\n{decls}\n  flow {{\n    start -> A\n{nodes}\n  }}\n}}\n"


def compiled(decls: str = "", nodes: str = "", players: str = "players 2") -> dict[str, Any]:
    result = compile_text(game(decls, nodes, players))
    assert result.ok, "\n\n".join(str(d) for d in result.diagnostics)
    return result.game().ir


def errors(decls: str = "", nodes: str = "", players: str = "players 2") -> list[str]:
    result = compile_text(game(decls, nodes, players))
    return [f"{d.code} {d.message} {d.help or ''}" for d in result.diagnostics.errors]


def body(expr: str, params: str = "", returns: str = "Int", decls: str = "") -> Any:
    ir = compiled(f"{decls}\n  fn f({params}) -> {returns} = {expr}")
    return next(f for f in ir["functions"] if f["name"] == "f")["body"]


def effects(stmts: str, decls: str = "", kind: str = "chance") -> list[Any]:
    nodes = f"    {kind} A {{\n{stmts}\n      -> B\n    }}\n    terminal B {{ payoff: fill(0) }}"
    ir = compiled(decls, nodes)
    return ir["flow"]["nodes"][0].get("effects", [])


# --- los juegos de la Fase 1 --------------------------------------------------------------------


@pytest.mark.parametrize("path", F1_GAMES, ids=lambda p: p.stem)
def test_nomos_games_match_the_hand_written_ir(path: Path) -> None:
    result = compile_file(path)
    assert result.ok and not result.diagnostics.items, [str(d) for d in result.diagnostics]
    ir = result.game().ir
    assert rules_hash(ir) == rules_hash(load_json(examples_dir() / f"{path.stem}.ir.json"))


@pytest.mark.parametrize("path", GAMES, ids=lambda p: p.stem)
def test_nomos_games_are_playable(path: Path) -> None:
    game_ = load_nomos(path)
    # Mentiroso es lento en el motor de referencia (≈ 1 s por partida) y su IR es idéntica a la
    # del ejemplo, que ya se juega en los tests del motor.
    games = {"mentiroso": 3, "connect-four": 60, "dudo": 100}.get(path.stem, 300)
    report = fuzz(game_, games, seed=1, num_players=game_.players[0])
    assert not report.errors and report.completed == games


# --- traducción de expresiones ------------------------------------------------------------------


def test_associative_chains_are_flattened_unless_parenthesized() -> None:
    assert body("a + b + c", "a: Int, b: Int, c: Int") == [
        "add", ["arg", "a"], ["arg", "b"], ["arg", "c"],
    ]  # fmt: skip
    assert body("(a + b) + c", "a: Int, b: Int, c: Int") == [
        "add", ["add", ["arg", "a"], ["arg", "b"]], ["arg", "c"],
    ]  # fmt: skip
    assert body("a and b or c", "a: Bool, b: Bool, c: Bool", "Bool") == [
        "or", ["and", ["arg", "a"], ["arg", "b"]], ["arg", "c"],
    ]  # fmt: skip


def test_literals() -> None:
    assert body("-3") == ["const", -3]
    assert body("-x", "x: Int") == ["neg", ["arg", "x"]]
    assert body("0.25", returns="Real") == ["rat", 1, 4]
    assert body("rat(1, 3)", returns="Real") == ["rat", 1, 3]
    assert body("none", returns="Int?") == ["const", None]
    assert body('"hola"', returns="Text") == ["const", "hola"]


def test_ranges_and_collections() -> None:
    assert body("1..n", "n: Int", "List<Int>") == ["range", ["const", 1], ["arg", "n"]]
    assert body("0..<n", "n: Int", "List<Int>") == [
        "range", ["const", 0], ["sub", ["arg", "n"], ["const", 1]],
    ]  # fmt: skip
    xs = "xs: List<Int>, ys: List<Int>"
    assert body("xs + ys", xs, "List<Int>") == ["concat", ["arg", "xs"], ["arg", "ys"]]
    assert body("xs - ys", xs, "List<Int>") == ["difference", ["arg", "xs"], ["arg", "ys"]]
    assert body("3 in xs", xs, "Bool") == ["contains", ["arg", "xs"], ["const", 3]]
    assert body("3 not in xs", xs, "Bool") == [
        "not", ["contains", ["arg", "xs"], ["const", 3]],
    ]  # fmt: skip
    assert body("xs[1:]", xs, "List<Int>") == [
        "slice", ["arg", "xs"], ["const", 1], ["len", ["arg", "xs"]],
    ]  # fmt: skip


def test_aggregates_and_comprehensions() -> None:
    xs = "xs: List<Int>"
    assert body("sum(xs)", xs) == ["sum", "x", ["arg", "xs"], ["local", "x"]]
    assert body("max(xs)", xs) == ["max_of", "x", ["arg", "xs"], ["local", "x"]]
    assert body("max(1, 2)") == ["max", ["const", 1], ["const", 2]]
    assert body("count(y in xs : y > 0)", xs) == [
        "count", "y", ["arg", "xs"], ["gt", ["local", "y"], ["const", 0]],
    ]  # fmt: skip
    assert body("[y for y in xs if y > 0]", xs, "List<Int>") == [
        "filter", "y", ["arg", "xs"], ["gt", ["local", "y"], ["const", 0]],
    ]  # fmt: skip
    assert body("[y * 2 for y in xs]", xs, "List<Int>") == [
        "map", "y", ["arg", "xs"], ["mul", ["local", "y"], ["const", 2]],
    ]  # fmt: skip
    assert body("[(a, b) for a in xs for b in xs]", xs, "List<(Int, Int)>") == [
        "flat_map", "a", ["arg", "xs"],
        ["map", "b", ["arg", "xs"], ["tuple", ["local", "a"], ["local", "b"]]],
    ]  # fmt: skip


def test_enums_and_structs() -> None:
    decls = "  enum Mark { X, O }\n  struct P { m: Mark, n: Int }"
    assert body("X", returns="Mark", decls=decls) == ["enum", "Mark", "X"]
    assert body("Mark.O", returns="Mark", decls=decls) == ["enum", "Mark", "O"]
    assert body("Mark.values", returns="List<Mark>", decls=decls) == ["enum_values", "Mark"]
    assert body("P { n: 1, m: X }.n", decls=decls) == [
        "field", ["struct", "P", {"n": ["const", 1], "m": ["enum", "Mark", "X"]}], "n",
    ]  # fmt: skip


def test_let_blocks_case_and_match() -> None:
    assert body("{ let a = 1; let b = a + 1; b * 2 }") == [
        "let", "a", ["const", 1],
        ["let", "b", ["add", ["local", "a"], ["const", 1]], ["mul", ["local", "b"], ["const", 2]]],
    ]  # fmt: skip
    assert body("case {\n x > 0 => 1\n else => 0\n }", "x: Int") == [
        "case", [[["gt", ["arg", "x"], ["const", 0]], ["const", 1]]], ["const", 0],
    ]  # fmt: skip
    decls = "  enum C { A, B }"
    exhaustive = "match (p, q) {\n (A, _) => 1\n (B, A) => 2\n (B, B) => 3\n }"
    assert body(exhaustive, "p: C, q: C", decls=decls) == [
        "case",
        [
            [["eq", ["arg", "p"], ["enum", "C", "A"]], ["const", 1]],
            [
                ["and", ["eq", ["arg", "p"], ["enum", "C", "B"]],
                 ["eq", ["arg", "q"], ["enum", "C", "A"]]],
                ["const", 2],
            ],
        ],
        ["const", 3],
    ]  # fmt: skip
    assert body("match b {\n true => 1\n _ => 0\n }", "b: Bool") == [
        "case", [[["eq", ["arg", "b"], ["const", True]], ["const", 1]]], ["const", 0],
    ]  # fmt: skip


def test_seat_builtins() -> None:
    assert body("next(s)", "s: Seat", "Seat") == ["next_seat", ["arg", "s"]]
    assert body("other(s)", "s: Seat", "Seat") == ["other_seat", ["arg", "s"]]
    assert body("num_players") == ["param", "num_players"]


# --- traducción de sentencias -------------------------------------------------------------------

CARDS = """  enum Card { A, B, C }
  state {
    deck: Zone<Card> = [A, B, C]
    hand: per_player Bag<Card>
    pile: Zone<Card>
    n: Int = 0
    log: List<Int>
    die: Int = 0
  }"""


def test_deal_lowering() -> None:
    move = [
        "move",
        ["var", "deck"],
        ["index", ["var", "hand"], ["local", "s"]],
        ["top", ["const", 1]],
    ]
    assert effects("      deal 1 from deck to each hand", CARDS) == [
        ["for", "s", ["seats"], [move]]
    ]
    assert effects("      deal 2 from deck to each hand", CARDS) == [
        ["for", "k", ["range", ["const", 1], ["const", 2]], [["for", "s", ["seats"], [move]]]]
    ]
    assert effects("      deal all from deck to each hand", CARDS) == [
        [
            "for", "i", ["range", ["const", 0], ["sub", ["size", ["var", "deck"]], ["const", 1]]],
            [["move", ["var", "deck"],
              ["index", ["var", "hand"], ["mod", ["local", "i"], ["param", "num_players"]]],
              ["top", ["const", 1]]]],
        ]
    ]  # fmt: skip


def test_compound_assignment_move_and_random() -> None:
    stmts = """      n += 2
      log += [n]
      move A from deck to pile
      move [B, C] from deck to pile at bottom
      move top 1 from pile to hand[0]
      shuffle deck
      die = roll(6)
      reveal n to 0"""
    assert effects(stmts, CARDS) == [
        ["assign", ["var", "n"], ["add", ["var", "n"], ["const", 2]]],
        ["assign", ["var", "log"], ["concat", ["var", "log"], ["list", ["var", "n"]]]],
        ["move", ["var", "deck"], ["var", "pile"], ["value", ["enum", "Card", "A"]]],
        ["move", ["var", "deck"], ["var", "pile"],
         ["values", ["list", ["enum", "Card", "B"], ["enum", "Card", "C"]]], "bottom"],
        ["move", ["var", "pile"], ["index", ["var", "hand"], ["const", 0]], ["top", ["const", 1]]],
        ["shuffle", ["var", "deck"]],
        ["roll", ["var", "die"], ["const", 6]],
        ["reveal", ["var", "n"], ["list", ["const", 0]]],
    ]  # fmt: skip


def test_module_level_declarations_are_included_only_when_used() -> None:
    source = """enum Color { Red, Blue }
enum Unused { Z }
fn favourite() -> Color = Blue
fn unused() -> Int = 1

game T {
  players 1
  state { c: Color = favourite() }
  flow {
    start -> A
    terminal A { payoff: fill(0) }
  }
}
"""
    ir = compile_text(source).game().ir
    assert [t["name"] for t in ir["types"]] == ["Color"]
    assert [f["name"] for f in ir["functions"]] == ["favourite"]


def test_tests_and_invariants_are_compiled() -> None:
    result = compile_file(next(p for p in GAMES if p.stem == "kuhn-poker"))
    compiled_game = result.game()
    assert compiled_game.tests[0].name == "la carta alta gana el enfrentamiento"
    assert compiled_game.invariants[0].label.startswith("Hay siempre tres cartas")


# --- errores ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("decls", "nodes", "expected"),
    [
        (
            "  state { turn: Seat = 0 }\n  fn f() -> Seat = tunr",
            "",
            "E201 nombre desconocido: `tunr`",
        ),
        ("  state { turn: Seat = 0 }\n  fn f() -> Seat = tunr", "", "¿quisiste decir `turn`?"),
        ("  state { x: Int = true }", "", "E301 tipos incompatibles"),
        ("  fn f() -> Seat = actor", "", "E205 'actor' solo existe"),
        ("  state { a: Int = 0\n b: Int = a }", "", "E205 en la inicialización del estado"),
        ("  params { n: Int = m\n m: Int = 1 }", "", "E205 el parámetro `m` se declara después"),
        (
            "  state { d: Int = 0 }",
            "    auto A {\n      d = roll(6)\n      -> B\n    }\n"
            "    terminal B { payoff: fill(0) }",
            "E306 'roll(…)' es aleatorio",
        ),
        (
            "",
            "    auto A {\n      -> B\n      -> A when true\n    }\n"
            "    terminal B { payoff: fill(0) }",
            "E403 transición sin condición antes de otras",
        ),
        ("", "    auto A { -> exit }", "E403 '-> exit' solo se permite dentro de una fase"),
        (
            "",
            "    auto A { -> Fin }\n    terminal Final { payoff: fill(0) }",
            "E401 nodo desconocido: Fin ¿quisiste decir `Final`?",
        ),
        (
            "",
            "    decision A {\n      actor: 0\n      action go()\n    }",
            "E404 el nodo A no tiene salida",
        ),
        (
            "",
            "    window A {\n      eligible: seats\n      mode: race\n      action pass()\n"
            "      -> A\n    }",
            "E406 'pass' está reservado",
        ),
        (
            "  enum C { P, Q }\n  fn f(c: C) -> Int = match c {\n P => 1\n }",
            "",
            "E304 match no exhaustivo: falta el caso Q",
        ),
        ("  fn f() -> Int = g()\n  fn g() -> Int = f()", "", "E208 recursión no permitida"),
        (
            "  state { x: Int = 0 }\n  fn f(x: Int) -> Int = x",
            "",
            "E204 `x` oculta un nombre global",
        ),
        ("  enum A { V }\n  enum B { V }\n  fn f() -> Int = ord(V)", "", "E203 `V` es ambiguo"),
        (
            "  struct P { a: Int, b: Int }\n  fn f() -> P = P { a: 1 }",
            "",
            "E209 P necesita exactamente",
        ),
        (
            "",
            "    decision A {\n      actor: 0\n      action go() { seats = [] }\n      -> A\n    }",
            "E307 solo se puede modificar el estado",
        ),
        (
            "",
            "    decision A {\n      actor: 0\n      action go(n: Int)\n      -> A\n    }",
            "E305 el parámetro n: Int necesita un dominio finito",
        ),
        (
            "",
            "    decision A {\n      action go()\n      -> A\n    }",
            "E402 al nodo decision A le falta 'actor:'",
        ),
        (
            "  state { b: Bag<Int> }",
            "    chance A {\n      shuffle b\n      -> A\n    }",
            "E302 no se puede barajar una bolsa",
        ),
        ("  fn f() -> Int = len(3)", "", "E301 len espera una colección"),
        ("  fn f(x: Int) -> Int = x if x > 0 else true", "", "E301 las dos ramas del if"),
        ("  fn len() -> Int = 1", "", "E206 `len` es una función predefinida"),
    ],
)
def test_errors(decls: str, nodes: str, expected: str) -> None:
    found = errors(decls, nodes)
    assert any(expected in e for e in found), found


def test_missing_players_and_bad_meta() -> None:
    found = errors(players='meta { id: "Mal Id", version: "1.0", color: "rojo" }')
    assert any("E210 el juego T no declara cuántos jugadores" in e for e in found)
    assert any("id de juego inválido" in e for e in found)
    assert any("versión inválida" in e for e in found)
    assert any("campo de meta desconocido: color" in e for e in found)


def test_one_error_does_not_cascade() -> None:
    found = errors("  state { x: Int = 0 }\n  fn f() -> Int = (zz + 1) * 2 + x")
    assert len(found) == 1


def test_compile_error_object() -> None:
    result: CompileResult = compile_text("game T { players 2 }")
    with pytest.raises(CompileError) as exc:
        result.game()
    assert "flow" in str(exc.value)


# --- línea de comandos --------------------------------------------------------------------------


def test_check_and_compile_commands(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    good = next(p for p in GAMES if p.stem == "nim")
    assert main(["check", str(good)]) == 0
    assert "✓" in capsys.readouterr().out
    out = tmp_path / "nim.ir.json"
    assert main(["compile", str(good), "-o", str(out)]) == 0
    assert rules_hash(load_game(out).ir) == rules_hash(load_json(examples_dir() / "nim.ir.json"))
    bad = tmp_path / "bad.game"
    bad.write_text(game("  fn f() -> Int = nada"))
    assert main(["check", str(bad)]) == 1
    assert "nombre desconocido" in capsys.readouterr().out
    assert main(["check", "--format", "json", str(bad)]) == 1
    assert '"code": "E201"' in capsys.readouterr().out


def test_fuzz_accepts_game_files(capsys: pytest.CaptureFixture[str]) -> None:
    path = next(p for p in GAMES if p.stem == "tictactoe")
    assert main(["fuzz", str(path), "--games", "50"]) == 0
    assert "errores: 0" in capsys.readouterr().out
