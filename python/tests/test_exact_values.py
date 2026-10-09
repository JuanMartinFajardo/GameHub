# SPDX-License-Identifier: Apache-2.0
"""Valor esperado EXACTO del juego aleatorio uniforme, recorriendo el árbol completo con las
probabilidades exactas del azar. Comprueba a la vez el motor y la enumeración del azar."""

from __future__ import annotations

from fractions import Fraction

import pytest

from gamehub.engine import State, Status, load_game
from gamehub.ir.spec import examples_dir


def random_play_value(state: State) -> tuple[Fraction, ...]:
    if state.status is Status.TERMINAL:
        assert state.payoffs is not None
        return tuple(Fraction(p) for p in state.payoffs)
    if state.status is Status.CHANCE:
        branches = [
            (p, random_play_value(state.apply_chance(o))) for o, p in state.chance_outcomes()
        ]
    else:
        seat = state.active_seats[0]
        legal = state.legal_actions(seat)
        weight = Fraction(1, len(legal))
        branches = [(weight, random_play_value(state.apply_action(seat, a))) for a in legal]
    n = len(branches[0][1])
    return tuple(sum((p * v[i] for p, v in branches), start=Fraction(0)) for i in range(n))


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        # Kuhn: los enfrentamientos se anulan por simetría; quedan bet-fold (+1, prob 1/4) y
        # check-bet-fold (-1, prob 1/8): 1/4 - 1/8 = 1/8.
        ("kuhn-poker", (Fraction(1, 8), Fraction(-1, 8))),
        # Dilema: media de (3,3), (0,5), (5,0), (1,1).
        ("prisoners-dilemma", (Fraction(9, 4), Fraction(9, 4))),
        ("rock-paper-scissors", (Fraction(0), Fraction(0))),
    ],
)
def test_random_play_value(name: str, expected: tuple[Fraction, ...]) -> None:
    game = load_game(examples_dir() / f"{name}.ir.json")
    assert random_play_value(game.new_state()) == expected


def test_kuhn_chance_tree_is_exact() -> None:
    game = load_game(examples_dir() / "kuhn-poker.ir.json")
    root = game.new_state()
    total = sum(p for _, p in root.chance_outcomes())
    assert total == 1
