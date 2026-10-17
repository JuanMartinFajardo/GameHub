# SPDX-License-Identifier: Apache-2.0
"""Aceptación de la fase 7: los resultados de referencia de docs/wiki/game-theory.md §6,
calculados con los juegos del catálogo y el motor de referencia."""

from __future__ import annotations

import functools
import itertools
from fractions import Fraction
from pathlib import Path

import pytest

from gamehub.analysis import cgt, nash, search
from gamehub.analysis.normal_form import normal_form
from gamehub.analysis.policy import exploitability
from gamehub.analysis.sequence_form import sequence_form
from gamehub.analysis.tree import build_tree, state_graph
from gamehub.engine.game import Game
from gamehub.lang.compiler import load_nomos

ROOT = Path(__file__).resolve().parents[2]
F = Fraction


@functools.cache
def game(name: str) -> Game:
    return load_nomos(ROOT / "games" / name / f"{name}.game")


def test_tictactoe() -> None:
    """Valor = empate; 5.478 posiciones legales; 255.168 partidas posibles."""
    assert search.solve(game("tictactoe")).value == (0, 0)
    graph = state_graph(game("tictactoe"))
    assert graph.positions == 5478 and graph.games() == 255168


def test_prisoners_dilemma() -> None:
    """Único equilibrio de Nash (D, D), dominado en Pareto por (C, C)."""
    nf = normal_form(game("prisoners-dilemma"))
    assert nf.strategies[0] == ("Cooperate", "Defect")
    assert nash.equilibria(nf) == [nash.pure_as_mixed(nf, (1, 1))]
    assert nash.pareto_dominators(nf, (1, 1)) == [(0, 0)]


@pytest.mark.parametrize(
    ("name", "mix"), [("rock-paper-scissors", (F(1, 3),) * 3), ("matching-pennies", (F(1, 2),) * 2)]
)
def test_unique_mixed_equilibrium_with_value_zero(name: str, mix: tuple[Fraction, ...]) -> None:
    """Piedra-papel-tijera: (1/3, 1/3, 1/3); cara o cruz: (1/2, 1/2); valor 0."""
    nf = normal_form(game(name))
    assert nash.equilibria(nf) == [(mix, mix)]
    assert nash.zero_sum(nf).value == 0


def test_kuhn_poker() -> None:
    """Valor para el primer jugador = −1/18 (forma de secuencias y forma normal, exactas)."""
    tree = build_tree(game("kuhn-poker"))
    sol = sequence_form(tree)
    assert sol.value == F(-1, 18) and exploitability(tree, sol.policy) == 0
    assert nash.zero_sum(normal_form(tree)).value == F(-1, 18)


def test_nim_p_positions_are_those_with_nim_sum_zero() -> None:
    """Posición P (pierde quien mueve) ⇔ suma-nim (XOR) = 0, con juego perfecto (alfa-beta, sin
    usar la teoría de Grundy)."""
    nim = game("nim")
    for heaps in itertools.product(range(4), repeat=3):
        if sum(heaps) == 0:
            continue
        expected = "P" if cgt.nim_sum(heaps) == 0 else "N"
        assert cgt.outcome_class(nim, params={"sizes": list(heaps)}) == expected, heaps


@pytest.mark.slow
def test_connect_four_four_by_four_is_a_draw() -> None:
    sol = search.alphabeta(game("connect-four"), params={"columns": 4, "rows": 4, "connect": 4})
    assert sol.value == (0, 0)


@pytest.mark.skip(
    reason="Conecta 4 en 7×6 (gana el primero: Allis y Allen, 1988): ni con el orden de la "
    "heurística Threats (F9) llega el solver de la VM genérica (ADR-089, pregunta 28)"
)
def test_connect_four_first_player_wins() -> None:  # pragma: no cover
    assert search.alphabeta(game("connect-four")).value == (1, -1)
