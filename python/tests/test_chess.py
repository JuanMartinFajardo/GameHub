# SPDX-License-Identifier: Apache-2.0
"""El ajedrez de games/chess contra los recuentos de *perft* publicados.

Las posiciones son las de referencia de la Chess Programming Wiki («Perft Results»): cada una
ejercita reglas difíciles (enroques, capturas al paso con jaque descubierto, promociones con
captura, clavadas). Los recuentos grandes son lentos con el motor de referencia: van marcados
como `slow` (`uv run pytest -m slow`).
"""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any

import pytest

from gamehub.analysis.perft import perft
from gamehub.engine import Game, State
from gamehub.lang.compiler import load_nomos

ROOT = Path(__file__).resolve().parents[2]
SKIP = ("claim_draw",)

KINDS = {"p": "Pawn", "n": "Knight", "b": "Bishop", "r": "Rook", "q": "Queen", "k": "King"}

START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
KIWIPETE = "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"
POSITION_3 = "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1"
POSITION_4 = "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1"
POSITION_5 = "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8"
POSITION_6 = "r4rk1/1pp1qppp/p1np1n2/2b1p1B1/2B1P1b1/P1NP1N2/1PP1QPPP/R4RK1 w - - 0 10"


@cache
def chess() -> Game:
    return load_nomos(ROOT / "games" / "chess" / "chess.game")


def cell(r: int, c: int) -> list[Any]:
    return ["cell", ["const", r], ["const", c]]


def square(name: str) -> tuple[int, int]:
    """«e2» → (6, 4): la fila 0 es la octava y la columna 0, la «a»."""
    return 8 - int(name[1]), ord(name[0]) - ord("a")


def position(fen: str) -> State:
    """El estado de una posición FEN. Solo con las blancas al turno: `State.edited` no vuelve a
    elegir quién juega."""
    placement, side, rights, ep, halfmove, fullmove = fen.split()
    assert side == "w", "solo posiciones con las blancas al turno"
    rows: list[list[Any]] = []
    kings: dict[str, tuple[int, int]] = {}
    for r, text in enumerate(placement.split("/")):
        row: list[Any] = []
        for ch in text:
            if ch.isdigit():
                row.extend(["const", None] for _ in range(int(ch)))
                continue
            color = "White" if ch.isupper() else "Black"
            kind = KINDS[ch.lower()]
            if kind == "King":
                kings[color] = (r, len(row))
            row.append(["enum", "Piece", color + kind])
        assert len(row) == 8
        rows.append(["list", *row])
    passant = ["const", None] if ep == "-" else cell(*square(ep))
    stmts = [
        ["assign", ["var", "board"], ["list", *rows]],
        ["assign", ["var", "kings"], ["list", cell(*kings["White"]), cell(*kings["Black"])]],
        ["assign", ["var", "castling"], ["list", *(["const", c in rights] for c in "KQkq")]],
        ["assign", ["var", "en_passant"], passant],
        ["assign", ["var", "halfmove"], ["const", int(halfmove)]],
        ["assign", ["var", "fullmove"], ["const", int(fullmove)]],
        ["assign", ["var", "history"], ["list", ["tuple", ["var", "board"], passant]]],
    ]
    return chess().new_state().edited(stmts)


def test_the_start_position_is_the_standard_one() -> None:
    assert position(START).snapshot()["store"] == chess().new_state().snapshot()["store"]


@pytest.mark.parametrize(
    ("fen", "depth", "nodes"),
    [
        (START, 3, 8_902),
        (KIWIPETE, 1, 48),
        (KIWIPETE, 2, 2_039),
        (POSITION_3, 3, 2_812),
        (POSITION_4, 2, 264),
        (POSITION_5, 2, 1_486),
        (POSITION_6, 2, 2_079),
    ],
)
def test_perft(fen: str, depth: int, nodes: int) -> None:
    assert perft(position(fen), depth, SKIP) == nodes


@pytest.mark.slow
@pytest.mark.parametrize(
    ("fen", "depth", "nodes"),
    [
        (START, 4, 197_281),
        (KIWIPETE, 3, 97_862),
        (POSITION_3, 4, 43_238),
        (POSITION_4, 3, 9_467),
        (POSITION_5, 3, 62_379),
        (POSITION_6, 3, 89_890),
    ],
)
def test_perft_deep(fen: str, depth: int, nodes: int) -> None:
    assert perft(position(fen), depth, SKIP) == nodes
