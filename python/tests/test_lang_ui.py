# SPDX-License-Identifier: Apache-2.0
"""La sección `ui { … }`: pistas de presentación, su comprobación y su traducción a la IR."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from gamehub.ir.hashing import rules_hash
from gamehub.ir.schema import schema_problems
from gamehub.ir.wellformed import wellformed_problems
from gamehub.lang.compiler import compile_text
from gamehub.lang.printer import format_source
from gamehub.lang.source import Source

BASE = """
game T {
  players 2

  params {
    size: Int = 3
  }

  enum Mark { X, O }
  struct Card { suit: Mark, value: Int }

  state {
    board: Grid[size, size] of Mark? = none
    hand: per_player Bag<Card>
    pile: Zone<Card>
    score: per_player Int
    turn: Seat = 0
    note: Text = ""
  }

  flow {
    start -> Move

    decision Move {
      actor: turn
      action place(c in cells(board)) requires is_none(board[c]) { board[c] = X }
      action drop(col in 0..<size) { board[cell(0, col)] = O }
      action give(card in items(hand[actor])) { move card from hand[actor] to pile }
      -> End
    }

    terminal End { payoff: fill(0) }
  }

  ui {
%s
  }
}
"""


def compile_ui(lines: str) -> Any:
    return compile_text(BASE % lines)


def ui_ir(lines: str) -> dict[str, Any]:
    result = compile_ui(lines)
    assert result.ok, "\n".join(str(d) for d in result.diagnostics)
    return result.game().ir.get("ui", {})


def errors(lines: str) -> list[str]:
    return [f"{d.code} {d.message} {d.help or ''}" for d in compile_ui(lines).diagnostics.errors]


def test_hints_reach_the_ir_by_category() -> None:
    ui = ui_ir(
        """
    board: grid, label({ es: "Tablero", en: "Board" })
    score: counter, place(seats)
    note: hidden
    size: label("Tamaño")
    Mark: symbols(X: "✕", O: "◯"), colors(X: "#e53935", O: "#1e88e5")
    Card: card(rank: value, suit: suit)
    action place: label("Marcar")
    action place.c: cell(board)
    action drop.col: column(board), label("Columna")
    action give.card: pick(hand)
    node Move: label({ es: "Turno", en: "Move" })
    seats: colors("#e53935", "#1e88e5"), names("Cruces", "Círculos")
"""
    )
    assert ui == {
        "state": {
            "board": {"widget": "grid", "label": {"es": "Tablero", "en": "Board"}},
            "score": {"widget": "counter", "place": "seats"},
            "note": {"widget": "hidden"},
        },
        "params": {"size": {"label": "Tamaño"}},
        "types": {
            "Mark": {
                "symbols": {"X": "✕", "O": "◯"},
                "colors": {"X": "#e53935", "O": "#1e88e5"},
            },
            "Card": {"card": {"rank": "value", "suit": "suit"}},
        },
        "actions": {
            "place": {"label": "Marcar", "params": {"c": {"input": "cell", "of": "board"}}},
            "drop": {"params": {"col": {"input": "column", "of": "board", "label": "Columna"}}},
            "give": {"params": {"card": {"input": "pick", "of": "hand"}}},
        },
        "nodes": {"Move": {"label": {"es": "Turno", "en": "Move"}}},
        "seats": {"colors": ["#e53935", "#1e88e5"], "names": ["Cruces", "Círculos"]},
    }


def test_hints_do_not_change_the_rules() -> None:
    result = compile_ui('    board: grid\n    Mark: symbols(X: "x", O: "o")')
    ir = result.game().ir
    plain = copy.deepcopy(ir)
    del plain["ui"]
    assert rules_hash(ir) == rules_hash(plain)
    assert schema_problems(ir) == [] and wellformed_problems(ir) == []


def test_an_empty_section_adds_nothing() -> None:
    result = compile_ui("")
    assert result.ok and "ui" not in result.game().ir


@pytest.mark.parametrize(
    ("lines", "fragment"),
    [
        ("    bord: grid", "E701 `bord` no es una variable de estado"),
        ("    bord: grid", "¿quisiste decir `board`?"),
        ('    action jump: label("x")', "E701 no hay ninguna acción `jump`"),
        ("    action place.x: cell(board)", "E701 la acción `place` no tiene el parámetro `x`"),
        ('    node Nowhere: label("x")', "E701 no hay ningún nodo `Nowhere`"),
        ("    board: sparkle", "E702 `sparkle` no es una pista para una variable de estado"),
        ("    score: grid", "E702 `grid` no sirve para dibujar `score`"),
        ("    note: dice", "E702 `dice` no sirve para dibujar `note`"),
        ("    Mark: card(rank: value)", "E703 `card` no lleva argumentos"),
        ("    size: grid", "E702 `grid` no es una pista para una opción"),
        ('    seats: label("x")', "E702 `label` no es una pista para seats"),
        ('    Mark: symbols(Z: "z")', "E703 `Mark` no tiene el valor `Z`"),
        ('    Mark: colors(X: "rojo")', "E703 color no válido: 'rojo'"),
        ('    Mark: symbols("x")', "E703 los argumentos de `symbols` llevan nombre"),
        ("    turn: place(seats)", "E703 place(seats) es para variables per_player"),
        ("    turn: place(left)", "E703 `left` no vale aquí"),
        ("    board: label(42)", "E703 se esperaba un texto"),
        ("    Card: card(suit: suit)", "E703 card(…) de un struct necesita al menos rank"),
        ("    Card: card(rank: colour)", "E703 `Card` no tiene el campo `colour`"),
        ("    action place.c: column(board)", "E703 column(board) da un Int"),
        ("    action drop.col: cell(board)", "E703 cell(board) da una casilla"),
        ("    action drop.col: cell(hand)", "E703 `hand` no es una rejilla"),
        ("    action give.card: pick(turn)", "E703 `turn` no es una colección"),
        ("    board: grid, hidden", "E704 `board` ya tiene una pista de dibujo"),
        (
            '    board: label("a")\n    board: label("b")',
            "E704 `board` ya tiene una pista `label`",
        ),
        ("    seats: colors()", "E703 colors(…) necesita al menos un valor"),
    ],
)
def test_mistakes_are_reported(lines: str, fragment: str) -> None:
    found = errors(lines)
    assert any(fragment in e for e in found), found


def test_the_section_formats_canonically() -> None:
    text = BASE % '    board:grid,label( "Tablero" )\n    action  place . c :cell( board )'
    formatted = format_source(Source("t.game", text))
    assert '    board: grid, label("Tablero")\n' in formatted
    assert "    action place.c: cell(board)\n" in formatted
    assert format_source(Source("t.game", formatted)) == formatted


def test_ui_is_a_context_word() -> None:
    # Fuera de su sitio, `ui` sigue siendo un nombre cualquiera.
    result = compile_text(
        "game T {\n  players 2\n  state {\n    ui: Int = 1\n  }\n"
        "  flow {\n    start -> A\n    terminal A { payoff: fill(ui) }\n  }\n}\n"
    )
    assert result.ok, [str(d) for d in result.diagnostics]


VARIANT = """
game Base {
  players 2
  enum Mark { X, O }
  state {
    board: Grid[3, 3] of Mark? = none
  }
  flow {
    start -> A
    terminal A { payoff: fill(0) }
  }
  ui {
    board: grid, label("Tablero")
    Mark: symbols(X: "x", O: "o")
  }
}

game Variant extends Base {
  ui {
    board: hidden
    Mark: colors(X: "#f00", O: "#00f")
  }
}
"""


def test_a_variant_overrides_hints_by_slot() -> None:
    result = compile_text(VARIANT)
    assert result.ok, [str(d) for d in result.diagnostics]
    base, variant = result.game("Base").ir["ui"], result.game("Variant").ir["ui"]
    assert base["state"]["board"] == {"widget": "grid", "label": "Tablero"}
    assert variant["state"]["board"] == {"widget": "hidden", "label": "Tablero"}
    assert variant["types"]["Mark"] == {
        "symbols": {"X": "x", "O": "o"},
        "colors": {"X": "#f00", "O": "#00f"},
    }


def test_hand_written_ir_is_checked_too() -> None:
    ir = compile_ui("    board: grid").game().ir
    ir["ui"]["state"]["ghost"] = {"widget": "row"}
    ir["ui"]["types"] = {"Mark": {"symbols": {"Q": "q"}}}
    problems = [str(p) for p in wellformed_problems(ir)]
    assert any("ghost" in p for p in problems), problems
    assert any("no tiene el valor Q" in p for p in problems), problems
    ir["ui"]["state"]["board"] = {"widget": "sparkle"}
    assert schema_problems(ir)
