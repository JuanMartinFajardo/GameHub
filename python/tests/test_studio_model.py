# SPDX-License-Identifier: Apache-2.0
"""El modelo del documento para el Studio (lo que dibujan el diagrama y los formularios)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from gamehub.analysis import irwalk
from gamehub.lang.compiler import compile_source
from gamehub.lang.parser import parse_text
from gamehub.lang.source import Source
from gamehub.studio.model import Utf16, document_model

ROOT = Path(__file__).resolve().parents[2]
GAMES = sorted(p for p in (ROOT / "games").glob("*/*.game") if p.parent.name != "tests")


def model_of(path: Path) -> tuple[Source, dict[str, Any], dict[str, Any] | None]:
    source = Source.from_path(path)
    result = compile_source(source, schema=False)
    assert result.ok
    ir = next(iter(result.games.values())).ir if result.games else None
    return source, document_model(source, result.file, result.models), ir


@pytest.mark.parametrize("path", GAMES, ids=lambda p: p.stem)
def test_the_model_has_every_node_and_transition_of_the_ir(path: Path) -> None:
    source, model, ir = model_of(path)
    game = model["game"]
    if game is None:  # un combinador (repeat, best_of): no hay nada que dibujar del texto
        assert model["games"][0]["kind"] == "alias"
        return
    assert ir is not None
    nodes = {n["id"]: n for n in game["flow"]["nodes"]}
    for node, parent in irwalk.all_nodes(ir):
        mine = nodes[node["id"]]
        assert mine["kind"] == node["kind"]
        assert mine["parent"] == parent
        assert len(mine["transitions"]) == len(node.get("transitions", [])), node["id"]
        assert [a["name"] for a in mine["actions"]] == [a["name"] for a in node.get("actions", [])]
        if mine["local"]:
            start, end = mine["nameSpan"]
            assert source.text[start:end] == node["id"]
    assert game["flow"]["start"]["target"] == ir["flow"]["start"]
    assert [v["name"] for v in game["state"]] == [v["name"] for v in ir["state"]]


def test_tictactoe_model_texts() -> None:
    _, model, _ = model_of(ROOT / "games" / "tictactoe" / "tictactoe.game")
    game = model["game"]
    assert game["meta"]["title"] == {"es": "Tres en raya", "en": "Tic-tac-toe"}
    assert game["players"] == {"min": 2, "max": 2, "local": True}
    move = game["flow"]["nodes"][0]
    assert move["members"] == {"actor": "turn"}
    place = move["actions"][0]
    assert place["params"][0]["domain"] == "cells(board)"
    assert place["requires"] == "is_none(board[c])"
    assert place["effects"] == "board[c] = mark(turn)"
    assert [(t["target"], t["when"]) for t in move["transitions"]] == [
        ("Win", "wins(mark(turn))"),
        ("Draw", "full()"),
        ("Move", None),
    ]
    assert move["transitions"][2]["effects"] == "turn = next(turn)"
    assert game["state"][0] == {
        **game["state"][0],
        "name": "board",
        "type": "Grid[3, 3] of Mark?",
        "init": "none",
    }
    assert {"target": "board", "hints": 'grid, label({ es: "Tablero", en: "Board" })'}.items() <= (
        game["ui"][0].items()
    )


def test_variants_show_their_base_as_not_local() -> None:
    _, model, _ = model_of(ROOT / "games" / "battle-of-the-sexes" / "battle-of-the-sexes.game")
    game = model["game"]
    assert game["extends"] == "TwoByTwo"
    assert all(not n["local"] for n in game["flow"]["nodes"])
    choice = next(t for t in game["types"] if t["name"] == "Choice")
    assert choice["local"] and choice["values"] == ["Opera", "Football"]


def test_a_model_without_compiling() -> None:
    text = (
        "game G {\n  players 2\n  flow {\n    start -> A\n    terminal A { payoff: oops }\n  }\n}\n"
    )
    tree, _ = parse_text(text)
    model = document_model(Source("<t>", text), tree)
    assert model["game"]["flow"]["nodes"][0]["members"] == {"payoff": "oops"}


def test_utf16_offsets() -> None:
    text = "a🎲b🎲c"
    utf16 = Utf16(text)
    assert [utf16(i) for i in range(len(text) + 1)] == [0, 1, 3, 4, 6, 7]
    assert [utf16.to_python(u) for u in (0, 1, 3, 4, 6, 7)] == [0, 1, 2, 3, 4, 5]
    assert Utf16("abc")(2) == 2
