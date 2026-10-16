# SPDX-License-Identifier: Apache-2.0
"""Teoría de juegos (F7): información perfecta (inducción hacia atrás, alfa-beta), juegos
combinatorios (Sprague–Grundy) e información imperfecta (mejor respuesta, explotabilidad, CFR,
forma de secuencias)."""

from __future__ import annotations

import functools
from fractions import Fraction
from pathlib import Path

import pytest

from gamehub.analysis import cgt, search
from gamehub.analysis.cfr import CFR, solve_cfr
from gamehub.analysis.nash import GameShapeError, zero_sum
from gamehub.analysis.normal_form import normal_form
from gamehub.analysis.policy import (
    best_response,
    expected_values,
    exploitability,
    nash_conv,
    pure_policy,
    uniform_policy,
)
from gamehub.analysis.sequence_form import sequence_form
from gamehub.analysis.tree import build_tree
from gamehub.engine.game import Game
from gamehub.lang.compiler import compile_text, load_nomos

ROOT = Path(__file__).resolve().parents[2]
F = Fraction


@functools.cache
def game(name: str) -> Game:
    return load_nomos(ROOT / "games" / name / f"{name}.game")


def from_text(source: str) -> Game:
    return Game(compile_text(source, "g.game").game().ir)


CENTIPEDE = """
game Centipede {
  players 2
  params { rounds: Int = 4 }
  state {
    small: Int = 1
    big: Int = 4
    turn: Seat = 0
    step: Int = 0
    taken: Bool = false
  }
  flow {
    start -> Move
    decision Move {
      actor: turn
      action take() { taken = true }
      action pass() {
        small = small * 2
        big = big * 2
        step += 1
      }
      -> Taken when taken
      -> Out when step == rounds
      -> Move { turn = other(turn) }
    }
    /// Quien se lo lleva cobra el montón grande.
    terminal Taken { payoff: [big if s == turn else small for s in seats] }
    /// Si nadie se lo lleva, el grande es para el otro.
    terminal Out { payoff: [small if s == turn else big for s in seats] }
  }
}
"""

REROLL = """
game Reroll {
  players 1
  state {
    value: Int = 0
    rerolled: Bool = false
  }
  flow {
    start -> Roll
    chance Roll {
      value = roll(6)
      -> Choose when not rerolled
      -> End
    }
    decision Choose {
      actor: 0
      action keep()
      action again() { rerolled = true }
      -> Roll when rerolled
      -> End
    }
    terminal End { payoff: [value] }
  }
}
"""


# --- Información perfecta ------------------------------------------------------------------------


def test_backward_induction_on_the_centipede() -> None:
    """El ciempiés: el equilibrio perfecto en subjuegos se lo lleva en la primera jugada, aunque
    pasar haría crecer el bote para los dos."""
    g = from_text(CENTIPEDE)
    sol = search.solve(g)
    assert sol.method == "backward_induction"
    assert sol.value == (4, 1)
    assert sol.best == ["take"] and sol.pv == ["take"]


def test_expectimax_with_chance() -> None:
    """Tirar un dado y poder repetir una vez: se repite con 1, 2 o 3 → 3/6·7/2 + (4+5+6)/6."""
    sol = search.backward_induction(from_text(REROLL))
    assert sol.value == (F(17, 4),)


def test_alphabeta_and_backward_induction_agree() -> None:
    ttt = game("tictactoe")
    a, b = search.alphabeta(ttt), search.backward_induction(ttt)
    assert a.value == b.value == (0, 0)
    assert a.best == b.best and len(a.best) == 9
    assert a.states < b.states  # la poda visita menos estados


def test_depth_limited_search_needs_an_evaluation() -> None:
    ttt = game("tictactoe")
    sol = search.alphabeta(ttt, max_depth=2, evaluate=lambda s: 0)
    assert sol.value == (0, 0)
    with pytest.raises(ValueError):
        search.alphabeta(ttt, max_depth=2)


def test_imperfect_information_is_rejected() -> None:
    with pytest.raises(search.ImperfectInformation):
        search.solve(game("prisoners-dilemma"))
    with pytest.raises(search.NotConstantSum):
        search.alphabeta(from_text(CENTIPEDE))


def connect_value(columns: int, rows: int, k: int) -> int:
    """Valor de Conecta-k para quien empieza (1, 0, -1) con un negamax independiente del motor."""
    from functools import cache

    lines = []
    for r in range(rows):
        for c in range(columns):
            for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
                cells = [(r + dr * i, c + dc * i) for i in range(k)]
                if all(0 <= x < rows and 0 <= y < columns for x, y in cells):
                    lines.append(cells)

    @cache
    def value(board: tuple[tuple[int, ...], ...], player: int) -> int:
        grid = {(r, c): v for c, col in enumerate(board) for r, v in enumerate(col)}
        moves = [c for c in range(columns) if len(board[c]) < rows]
        if not moves:
            return 0
        best = -2
        for c in moves:
            col = (*board[c], player)
            new = (*board[:c], col, *board[c + 1 :])
            grid[(len(col) - 1, c)] = player
            won = any(all(grid.get(x) == player for x in line) for line in lines)
            del grid[(len(col) - 1, c)]
            best = max(best, 1 if won else -value(new, 1 - player))
            if best == 1:
                break
        return best

    return value(((),) * columns, 0)


@pytest.mark.parametrize(("columns", "rows", "k"), [(4, 3, 3), (3, 4, 3), (3, 3, 3)])
def test_connect_four_small_boards(columns: int, rows: int, k: int) -> None:
    sol = search.alphabeta(
        game("connect-four"), params={"columns": columns, "rows": rows, "connect": k}
    )
    assert sol.value[0] == connect_value(columns, rows, k)


# --- Juegos combinatorios ------------------------------------------------------------------------


def test_mex_and_nim_sum() -> None:
    assert cgt.mex([0, 1, 3]) == 2 and cgt.mex([]) == 0
    assert cgt.nim_sum([3, 5, 7]) == 1


def test_grundy_values_of_nim() -> None:
    nim = game("nim")
    assert cgt.grundy_table(nim, "sizes", [[n] for n in range(6)][1:]) == [
        ([n], n) for n in range(1, 6)
    ]
    # Sprague–Grundy: el valor de una suma es el XOR de los valores.
    for heaps in ([1, 2], [2, 3, 1], [3, 5, 6]):
        assert cgt.grundy(nim, params={"sizes": heaps}).value == cgt.nim_sum(heaps)
    result = cgt.grundy(nim, params={"sizes": [3, 5, 7]})
    assert result.value == 1
    assert result.winning_moves == ["take(0, 1)", "take(1, 1)", "take(2, 1)"]


def test_misere_is_not_normal_play() -> None:
    with pytest.raises(cgt.NotNormalPlay):
        cgt.grundy(game("nim"), params={"sizes": [2, 2], "misere": True})


def test_outcome_classes() -> None:
    nim = game("nim")
    assert cgt.outcome_class(nim, params={"sizes": [1, 2, 3]}) == "P"
    assert cgt.outcome_class(nim, params={"sizes": [1, 2, 2]}) == "N"
    assert cgt.outcome_class(game("tictactoe")) == "D"
    # Misère con dos montones de uno: quien mueve deja uno y gana.
    assert cgt.outcome_class(nim, params={"sizes": [1, 1], "misere": True}) == "N"


# --- Información imperfecta ----------------------------------------------------------------------


@functools.cache
def kuhn_tree():
    return build_tree(game("kuhn-poker"))


def test_uniform_policy_in_kuhn() -> None:
    tree = kuhn_tree()
    uniform = uniform_policy(tree)
    assert expected_values(tree, uniform) == (F(1, 8), F(-1, 8))
    # El mismo valor que da OpenSpiel para su kuhn_poker: NashConv 11/12.
    assert nash_conv(tree, uniform) == F(11, 12)
    assert exploitability(tree, uniform) == F(11, 24)


def test_best_response_to_a_pure_policy() -> None:
    tree = kuhn_tree()
    always_bet = pure_policy(tree, {s.id: 1 for s in tree.infosets if s.labels[1] == "bet"})
    br = best_response(tree, always_bet, 1)
    # Contra quien siempre apuesta, se iguala con K, nunca con J.
    k = next(
        s
        for s in tree.infosets
        if s.player == 1 and "K" in s.description and "Bet" in s.description
    )
    j = next(
        s
        for s in tree.infosets
        if s.player == 1 and "J" in s.description and "Bet" in s.description
    )
    assert br.choices[k.id] == 0 and br.choices[j.id] == 1
    assert set(br.choices) == {s.id for s in tree.infosets if s.player == 1}


def test_sequence_form_solves_kuhn_exactly() -> None:
    tree = kuhn_tree()
    sol = sequence_form(tree)
    assert sol.value == F(-1, 18)
    assert exploitability(tree, sol.policy) == 0
    assert expected_values(tree, sol.policy) == (F(-1, 18), F(1, 18))
    # Igual que la programación lineal sobre la forma normal reducida.
    assert zero_sum(normal_form(tree)).value == sol.value


def test_sequence_form_of_matching_pennies() -> None:
    tree = build_tree(game("matching-pennies"))
    sol = sequence_form(tree)
    assert sol.value == 0
    assert sol.policy == {0: [F(1, 2), F(1, 2)], 1: [F(1, 2), F(1, 2)]}
    with pytest.raises(GameShapeError):
        sequence_form(build_tree(game("prisoners-dilemma")))


def test_cfr_plus_converges_on_kuhn() -> None:
    tree = kuhn_tree()
    policy, convergence = solve_cfr(tree, 400, plus=True, measure_every=100)
    values = expected_values(tree, policy)
    assert values[0] == pytest.approx(-1 / 18, abs=2e-3)
    assert [i for i, _ in convergence.points] == [100, 200, 300, 400]
    gaps = [e for _, e in convergence.points]
    assert gaps[-1] < 2e-3 and gaps[-1] < gaps[0]


def test_vanilla_cfr_also_converges() -> None:
    tree = kuhn_tree()
    solver = CFR(tree)
    solver.run(50)
    early = float(exploitability(tree, solver.average()))
    solver.run(250)
    late = float(exploitability(tree, solver.average()))
    assert late < early and late < 0.02
