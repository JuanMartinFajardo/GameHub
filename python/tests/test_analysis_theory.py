# SPDX-License-Identifier: Apache-2.0
"""Teoría de juegos (F7): programación lineal, forma extensiva, grafo de estados, viabilidad,
forma normal y equilibrios. Los resultados de referencia de docs/wiki/game-theory.md §6 están en
test_analysis_reference.py."""

from __future__ import annotations

import functools
import itertools
from fractions import Fraction
from pathlib import Path

import pytest

from gamehub.analysis import nash
from gamehub.analysis.feasibility import feasibility
from gamehub.analysis.lp import Backend, highs_available, linprog
from gamehub.analysis.normal_form import NormalForm, normal_form
from gamehub.analysis.tree import TooLarge, build_tree, state_graph
from gamehub.engine.game import Game
from gamehub.lang.compiler import compile_text, load_nomos

ROOT = Path(__file__).resolve().parents[2]
F = Fraction


@functools.cache
def game(name: str) -> Game:
    return load_nomos(ROOT / "games" / name / f"{name}.game")


def from_text(source: str) -> Game:
    return Game(compile_text(source, "g.game").game().ir)


# --- Programación lineal -------------------------------------------------------------------------


BACKENDS = [
    "exact",
    pytest.param("highs", marks=pytest.mark.skipif(not highs_available(), reason="sin highspy")),
]


@pytest.mark.parametrize("backend", BACKENDS)
def test_linprog(backend: Backend) -> None:
    res = linprog([1, 1], A_ub=[[-1, -2], [-3, -1]], b_ub=[-4, -6], backend=backend)
    assert res.status == "optimal"
    assert res.value == pytest.approx(F(14, 5))
    assert res.x == pytest.approx((F(8, 5), F(6, 5)))
    free = linprog(
        [1, 0], A_ub=[[-1, 1]], b_ub=[0], A_eq=[[0, 1]], b_eq=[-3], free=[0, 1], backend=backend
    )
    assert free.value == pytest.approx(-3)
    assert linprog([1], A_ub=[[1]], b_ub=[-1], backend=backend).status == "infeasible"
    assert linprog([-1], A_ub=[[-1]], b_ub=[1], backend=backend).status == "unbounded"


def test_exact_linprog_is_exact_and_handles_degeneracy() -> None:
    # Un programa muy degenerado (todas las restricciones pasan por el óptimo).
    res = linprog(
        [-1, -1, -1],
        A_ub=[[1, 1, 0], [0, 1, 1], [1, 0, 1], [1, 1, 1], [2, 2, 2]],
        b_ub=[1, 1, 1, F(3, 2), 3],
        backend="exact",
    )
    assert res.value == F(-3, 2)
    assert all(isinstance(v, Fraction) for v in res.x or ())
    # Filas redundantes en las igualdades.
    res = linprog([1, 2], A_eq=[[1, 1], [2, 2]], b_eq=[1, 2], backend="exact")
    assert res.x == (1, 0)


# --- Forma extensiva y grafo de estados ----------------------------------------------------------


def test_kuhn_tree() -> None:
    tree = build_tree(game("kuhn-poker"))
    assert tree.counts() == {
        "nodes": 55,
        "terminals": 30,
        "chance": 1,
        "decision": 24,
        "infosets": 12,
    }
    assert tree.root.probs == [F(1, 6)] * 6
    assert sorted(len(s.nodes) for s in tree.infosets) == [2] * 12
    assert {s.player for s in tree.infosets} == {0, 1}
    # Las descripciones solo muestran lo que distingue los conjuntos.
    assert "deck" not in tree.infosets[0].description
    assert "?" in tree.infosets[0].description


def test_infosets_match_the_engine_keys() -> None:
    """La clave incremental es la misma que `State.information_state`."""
    g = game("kuhn-poker")
    tree = build_tree(g)
    root = g.new_state()
    for path in [(0, "check"), (3, "bet")]:
        outcome, _ = root.chance_outcomes()[path[0]]
        state = root.apply_chance(outcome)
        state = state.apply_action(0, next(a for a in state.legal_actions(0) if a.name == path[1]))
        key = state.information_state(1)
        assert any(s.key == key for s in tree.infosets if s.player == 1)


def test_simultaneous_moves_hide_the_first_choice() -> None:
    tree = build_tree(game("prisoners-dilemma"))
    assert [(s.player, len(s.nodes)) for s in tree.infosets] == [(0, 1), (1, 2)]
    assert tree.infosets[1].labels == ["Cooperate", "Defect"]


def test_equivalent_chance_outcomes_are_merged() -> None:
    source = """
game Pair {
  players 1
  state {
    @visible(none) deck: Zone<Int> = [1, 1, 2]
    top: Int = 0
  }
  flow {
    start -> Deal
    chance Deal {
      shuffle deck
      top = 0
      -> Pick
    }
    decision Pick {
      actor: 0
      action keep() { }
      -> End
    }
    terminal End { payoff: [0] }
  }
}
"""
    g = from_text(source)
    tree = build_tree(g)
    # 3! = 6 sorteos, pero solo 3 órdenes distintos de [1, 1, 2].
    assert tree.root.probs == [F(1, 3)] * 3


def test_tictactoe_state_graph() -> None:
    graph = state_graph(game("tictactoe"))
    assert (graph.positions, graph.terminals, graph.games()) == (5478, 958, 255168)
    assert not graph.cyclic


def test_limits() -> None:
    with pytest.raises(TooLarge):
        build_tree(game("tictactoe"), max_nodes=100)
    with pytest.raises(TooLarge):
        state_graph(game("tictactoe"), max_nodes=100)


# --- Viabilidad ----------------------------------------------------------------------------------


def codes(name: str, **params: object) -> list[str]:
    return [
        r.code for r in feasibility(game(name), params=params or None, samples=60).recommendations
    ]


def test_feasibility_counts_and_estimates() -> None:
    f = feasibility(game("tictactoe"), samples=200)
    assert f.exact["positions"] == 5478 and f.exact["games"] == 255168
    # El árbol tiene 549.946 nodos: el estimador de Knuth anda cerca.
    assert 5.3 < f.tree_log10 < 6.1
    assert f.classification.perfect_information and f.depth_max == 9
    kuhn = feasibility(game("kuhn-poker"), samples=100)
    assert kuhn.exact == {"nodes": 55, "terminals": 30, "infosets": 12}


def test_feasibility_recommendations() -> None:
    assert codes("tictactoe") == ["solve"]
    assert codes("nim") == ["grundy", "solve"]
    assert codes("prisoners-dilemma")[:2] == ["normal_form", "nash"]
    assert {"sequence_form", "cfr"} <= set(codes("kuhn-poker"))
    assert "tournament" in codes("iterated-pd")
    assert codes("connect-four") == ["approximate"]


def test_feasibility_json() -> None:
    data = feasibility(game("nim"), samples=30).to_json()
    assert data["classification"]["zero_sum"] is True
    assert data["exact"]["positions"] == 376
    assert data["recommendations"][0]["code"] == "grundy"


# --- Forma normal --------------------------------------------------------------------------------


def test_normal_form_of_simultaneous_games() -> None:
    nf = normal_form(game("prisoners-dilemma"))
    assert nf.strategies == (("Cooperate", "Defect"), ("Cooperate", "Defect"))
    assert nf.matrix(0) == [[3, 0], [5, 1]]
    assert nf.matrix(1) == [[3, 5], [0, 1]]


def test_reduced_normal_form_of_kuhn() -> None:
    nf = normal_form(game("kuhn-poker"))
    # Cada carta: apostar, pasar e igualar, pasar y retirarse (3³); el segundo, por carta, qué
    # hace si le pasan y si le apuestan (4³).
    assert nf.shape == (27, 64)
    assert nf.is_constant_sum()
    assert nf.plans is not None
    assert len({tuple(sorted(p.items())) for p in nf.plans[0]}) == 27


def test_normal_form_of_a_sequential_game() -> None:
    """En un juego por turnos, el segundo jugador elige una respuesta para cada jugada del primero
    (4 estrategias); las del primero que ya no alcanzan nada no se repiten."""
    source = """
game Ultimatum {
  players 2
  enum Offer { Fair, Greedy }
  state { offer: Offer? = none }
  flow {
    start -> Propose
    decision Propose {
      actor: 0
      action make(o: Offer) { offer = o }
      -> Respond
    }
    decision Respond {
      actor: 1
      action accept()
      action reject()
      -> Deal when true
    }
    terminal Deal { payoff: [0, 0] }
  }
}
"""
    nf = normal_form(from_text(source))
    assert nf.shape == (2, 4)


def test_from_matrices_and_restrict() -> None:
    nf = NormalForm.from_matrices([[1, -1], [-1, 1]], rows=["H", "T"], columns=["h", "t"])
    assert nf.payoff((0, 1)) == (-1, 1)
    small = nf.restrict([[1], [0, 1]])
    assert small.strategies == (("T",), ("h", "t"))
    assert small.payoff((0, 0)) == (-1, 1)
    assert nf.expected(((F(1, 2), F(1, 2)), (F(1, 2), F(1, 2)))) == (0, 0)


# --- Equilibrios ---------------------------------------------------------------------------------


def all_are_equilibria(nf: NormalForm, found: list[nash.MixedProfile]) -> bool:
    return all(nash.is_equilibrium(nf, eq) for eq in found)


def test_battle_of_the_sexes_has_three_equilibria() -> None:
    nf = normal_form(game("battle-of-the-sexes"))
    found = nash.support_enumeration(nf)
    assert len(found) == 3 and all_are_equilibria(nf, found)
    assert ((F(3, 5), F(2, 5)), (F(2, 5), F(3, 5))) in found
    assert nash.pure_equilibria(nf) == [(0, 0), (1, 1)]
    # Lemke–Howson encuentra los puros (según la etiqueta que suelte).
    assert set(nash.lemke_howson_all(nf)) <= set(found)
    assert nash.price_of_anarchy(nf) == F(25, 12)
    assert nash.price_of_stability(nf) == 1


@pytest.mark.parametrize("seed", range(6))
def test_lemke_howson_and_support_enumeration_agree(seed: int) -> None:
    """Juegos aleatorios (no degenerados con probabilidad 1): cada equilibrio de Lemke–Howson
    está en la lista de la enumeración de soportes, y todos son equilibrios."""
    from gamehub.engine.rng import Pcg32

    rng = Pcg32(seed, 3)
    m, n = 3 + seed % 2, 3
    a = [[rng.below(20) - 10 for _ in range(n)] for _ in range(m)]
    b = [[rng.below(20) - 10 for _ in range(n)] for _ in range(m)]
    nf = NormalForm.from_matrices(a, b)
    found = nash.support_enumeration(nf)
    assert found and all_are_equilibria(nf, found)
    assert len(found) % 2 == 1  # teorema del índice: número impar en juegos no degenerados
    for label in range(m + n):
        assert nash.lemke_howson(nf, label) in found


def test_lemke_howson_on_a_degenerate_game() -> None:
    nf = NormalForm.from_matrices([[1, 1], [1, 1]], [[1, 1], [1, 1]])
    for label in range(4):
        assert nash.is_equilibrium(nf, nash.lemke_howson(nf, label))


def test_zero_sum() -> None:
    rps = normal_form(game("rock-paper-scissors"))
    sol = nash.zero_sum(rps)
    assert sol.value == 0 and sol.strategies == ((F(1, 3),) * 3, (F(1, 3),) * 3)
    with pytest.raises(nash.GameShapeError):
        nash.zero_sum(normal_form(game("prisoners-dilemma")))
    kuhn = normal_form(game("kuhn-poker"))
    sol = nash.zero_sum(kuhn)
    assert sol.value == F(-1, 18)
    assert nash.is_equilibrium(kuhn, sol.strategies)


def test_dominance() -> None:
    pd = nash.iterated_dominance(normal_form(game("prisoners-dilemma")))
    assert pd.remaining == [[1], [1]]
    # Una fila dominada solo por una mezcla de las otras dos.
    nf = NormalForm.from_matrices([[3, 0], [0, 3], [1, 1]], [[0, 0], [0, 0], [0, 0]])
    assert nash.iterated_dominance(nf).remaining == [[0, 1, 2], [0, 1]]
    mixed = nash.iterated_dominance(nf, mixed=True)
    assert mixed.remaining == [[0, 1], [0, 1]] and mixed.steps == [(0, 2, "mixta")]
    # Dominancia débil.
    weak = NormalForm.from_matrices([[1, 1], [1, 0]], [[1, 1], [1, 1]])
    assert nash.iterated_dominance(weak).remaining == [[0, 1], [0, 1]]
    assert nash.iterated_dominance(weak, weak=True).remaining[0] == [0]


def test_correlated_equilibrium_of_chicken() -> None:
    """En el gallina clásico (Aumann), el equilibrio correlado de máximo bienestar reparte entre
    (C, C), (C, D) y (D, C) y supera a todos los de Nash."""
    nf = NormalForm.from_matrices([[6, 2], [7, 0]], [[6, 7], [2, 0]])
    dist = nash.correlated_equilibrium(nf)
    assert dist == {(0, 0): F(1, 2), (0, 1): F(1, 4), (1, 0): F(1, 4)}
    welfare = sum(q * sum(nf.payoffs[p]) for p, q in dist.items())
    assert welfare == F(21, 2)
    assert max(sum(nf.expected(eq)) for eq in nash.equilibria(nf)) < welfare


def test_pareto_and_welfare() -> None:
    nf = normal_form(game("prisoners-dilemma"))
    assert nash.pareto_optimal(nf) == [(0, 0), (0, 1), (1, 0)]
    assert nash.pareto_dominators(nf, (1, 1)) == [(0, 0)]
    assert nash.social_optimum(nf) == (6, [(0, 0)])
    assert nash.social_optimum(nf, "egalitarian") == (3, [(0, 0)])
    assert nash.price_of_anarchy(nf) == 3


def test_three_player_pure_equilibria() -> None:
    """Un juego de coordinación de tres: todos iguales cobra 1."""
    nf = NormalForm.from_function([["a", "b"]] * 3, lambda p: [1 if len(set(p)) == 1 else 0] * 3)
    assert nash.pure_equilibria(nf) == [(0, 0, 0), (1, 1, 1)]
    dist = nash.correlated_equilibrium(nf)
    assert sum(dist.values()) == 1 and set(dist) <= {(0, 0, 0), (1, 1, 1)}
    assert list(itertools.islice(nf.profiles(), 2)) == [(0, 0, 0), (0, 0, 1)]
