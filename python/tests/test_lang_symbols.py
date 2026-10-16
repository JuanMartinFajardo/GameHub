# SPDX-License-Identifier: Apache-2.0
"""Índice de símbolos: qué declara cada nombre, dónde se usa y el tipo de cada expresión."""

from __future__ import annotations

from pathlib import Path

import pytest

from gamehub.lang.compiler import compile_source
from gamehub.lang.source import Source
from gamehub.lang.symbols import SymbolIndex

ROOT = Path(__file__).resolve().parents[2]
GAMES = sorted(p for p in (ROOT / "games").glob("*/*.game") if p.parent.name != "tests")


def indexed(path: Path) -> tuple[Source, SymbolIndex]:
    source = Source.from_path(path)
    index = SymbolIndex()
    result = compile_source(source, index=index, schema=False)
    assert result.ok
    return source, index


def uses(index: SymbolIndex, source: Source, key: str) -> list[str]:
    return [
        source.text[o.span.start : o.span.end] for o in index.of(key, source.name) if not o.decl
    ]


def test_tictactoe() -> None:
    source, index = indexed(ROOT / "games" / "tictactoe" / "tictactoe.game")
    board = index.symbols["state:board"]
    assert board.detail == "board: Grid[3, 3] of Mark?"
    assert [source.text[d.start : d.end] for d in board.decls] == ["board"]
    assert set(uses(index, source, "state:board")) == {"board"}
    assert len(uses(index, source, "state:board")) == 12
    assert index.symbols["fn:wins"].detail == "fn wins(m: Mark) -> Bool"
    assert index.symbols["node:Move"].detail == "decision Move"
    # `start -> Move`, `-> Move` y la pista `node Move` del ui.
    assert len(uses(index, source, "node:Move")) == 3
    assert uses(index, source, "value:Mark.X").count("X") == 4
    # El parámetro de la acción: en requires, en los efectos y en la pista `action place.c`.
    assert len(uses(index, source, "aparam:place.c")) == 3


def test_lookup_by_position_and_types() -> None:
    source, index = indexed(ROOT / "games" / "tictactoe" / "tictactoe.game")
    text = source.text
    at = text.index("board[c] = mark(turn)")
    occ = index.at(source.name, at + 2)
    assert occ is not None and occ.key == "state:board" and not occ.decl
    # El final del nombre también cuenta (el cursor justo detrás).
    occ = index.at(source.name, at + len("board"))
    assert occ is not None and occ.key == "state:board"
    typed = index.type_at(source.name, text.index("mark(turn)", at) + 1)
    assert typed is not None and typed[1] == "Mark"
    local = index.at(source.name, text.index("m: Mark") + 0)
    assert local is not None and local.decl and local.key.startswith("local:")


def test_grid_dimensions_struct_fields_and_ui_refer_to_their_declarations() -> None:
    source, index = indexed(ROOT / "games" / "connect-four" / "connect-four.game")
    assert "columns" in uses(index, source, "param:columns")
    texts = [source.text[o.span.start : o.span.start + 30] for o in index.of("param:columns")]
    assert any(t.startswith("columns, rows]") for t in texts)
    # `action drop.c: column(board)`: el parámetro y la variable.
    params = index.of("aparam:drop.c", source.name)
    assert any(source.text[o.span.start - 7 : o.span.start] == "n drop." for o in params)
    source, index = indexed(ROOT / "games" / "mentiroso" / "mentiroso.game")
    fields = [k for k in index.symbols if k.startswith("field:")]
    assert fields
    assert any(uses(index, source, k) for k in fields)


@pytest.mark.parametrize("path", GAMES, ids=lambda p: p.stem)
def test_every_name_in_expressions_is_resolved(path: Path) -> None:
    """Cada nombre de una expresión compilada se refiere a algo del índice."""
    import re

    source, index = indexed(path)
    keys = set(index.symbols)
    for occ in index.occurrences:
        if occ.key.startswith(("builtin:", "context:")):
            continue
        assert occ.key in keys, occ
        span = occ.span
        if span.source is source or (span.source and span.source.name == source.name):
            word = source.text[span.start : span.end]
            assert re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", word), (occ.key, word)
