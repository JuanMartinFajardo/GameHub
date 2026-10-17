# SPDX-License-Identifier: Apache-2.0
"""Números globales de acción desde la IR (ADR-079), el rango declarado de las variables
(`@range`) y el puente con OpenSpiel sin explorar el juego."""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any

import pytest

from gamehub.analysis.action_space import Unbounded, action_space, chance_bound
from gamehub.engine.errors import RuleError
from gamehub.engine.game import Game
from gamehub.engine.rng import Pcg32
from gamehub.engine.state import Status
from gamehub.lang.compiler import compile_source, load_nomos
from gamehub.lang.decompile import decompile
from gamehub.lang.printer import format_file
from gamehub.lang.source import Source

GAMES = Path(__file__).resolve().parents[2] / "games"


def catalog() -> list[str]:
    return sorted(p.stem for p in GAMES.glob("*/*.game") if p.name != "tests.game")


@cache
def game(name: str) -> Game:
    return load_nomos(GAMES / name / f"{name}.game")


def space_of(name: str, n: int | None = None, given: dict[str, Any] | None = None) -> Any:
    g = game(name)
    root = g.new_state(n, given)
    params = {k: v for k, v in root.params.items() if k != "num_players"}
    return action_space(g.ir, root.n, params)


def test_known_sizes() -> None:
    chess = space_of("chess")
    assert chess.size == 20_481  # play 64·64 + promote 64·64·4 + claim_draw
    assert [(b.name, b.size) for b in chess.blocks] == [
        ("play", 4096),
        ("promote", 16384),
        ("claim_draw", 1),
    ]
    assert space_of("tictactoe").size == 9
    assert space_of("connect-four").size == 7
    assert space_of("nim").size == 3 * 7
    assert space_of("kuhn-poker").size == 4
    holdem = space_of("texas-holdem")
    assert [(b.name, b.size) for b in holdem.blocks][-2:] == [("bet", 401), ("raise", 801)]
    assert space_of("texas-holdem", 6).blocks[-1].size == 6 * 200 * 2 + 1


@pytest.mark.parametrize("name", catalog())
def test_every_legal_action_has_a_unique_number(name: str) -> None:
    g = game(name)
    space = space_of(name)
    n = g.players[0]
    for seed in range(3):
        state = g.new_state(n)
        chance = Pcg32(seed)
        agents = [Pcg32(seed, 1000 + s) for s in range(n)]
        for _ in range(60):
            if state.is_terminal:
                break
            if state.status is Status.CHANCE:
                state = state.apply_chance(state.sample_chance(chance))
                continue
            seat = state.active_seats[0]
            legal = state.legal_actions(seat)[:300]
            numbers = [space.encode(state.node, a) for a in legal]
            assert len(set(numbers)) == len(numbers)
            assert all(0 <= x < space.size for x in numbers)
            assert [space.decode(state.node, x) for x in numbers] == legal
            state = state.apply_action(seat, legal[agents[seat].below(len(legal))])


def test_cpp_encoding_matches() -> None:
    core = pytest.importorskip("gamehub_core")
    from gamehub.engine.core import core_game

    for name in ("chess", "texas-holdem", "mentiroso", "skat"):
        g = game(name)
        space = space_of(name)
        cg = core_game(g)
        cspace = core.ActionSpace(cg.core, space.to_json())
        state = cg.new_state(g.players[0])
        chance = Pcg32(7)
        for _ in range(40):
            if state.is_terminal:
                break
            if state.status is Status.CHANCE:
                state = state.apply_chance(state.sample_chance(chance))
                continue
            seat = state.active_seats[0]
            legal = state.legal_actions(seat)
            assert cspace.legal_ids(state.core, seat) == [
                space.encode(state.node, a) for a in legal
            ]
            state = state.apply_action(seat, legal[len(legal) // 2])


def test_chance_bounds() -> None:
    assert chance_bound(game("texas-holdem").ir, 2, {"stack": 200}) == 52
    assert chance_bound(game("chess").ir, 2, {}) == 0


# --- @range ------------------------------------------------------------------------------------

RANGED = """
game RangeProbe {
  players 2
  params { cap: Int = 5 }
  state {
    @range(0..cap * num_players) chips: per_player Int = 3
    @range(1..<4) level: Int = 1
    plain: Int = 0
  }
  flow {
    start -> Pay
    decision Pay {
      actor: 0
      action give(k in 1..3) { chips[actor] += k }
      action climb(k in 1..chips[actor]) { plain = plain + k }
      -> End when chips[0] >= 9
      -> Pay
    }
    terminal End { payoff: [1, -1] }
  }
}
"""


def ranged_game() -> Game:
    result = compile_source(Source("range.game", RANGED))
    return Game(result.game().ir)


def test_range_compiles_and_decompiles() -> None:
    g = ranged_game()
    ranges = [v.get("range") for v in g.ir["state"]]
    assert ranges[0] == [["const", 0], ["mul", ["param", "cap"], ["param", "num_players"]]]
    assert ranges[1] == [["const", 1], ["sub", ["const", 4], ["const", 1]]]
    assert ranges[2] is None
    text = format_file(decompile(g.ir))
    assert "@range(0..cap * num_players)" in text and "@range(1..<4)" in text


def test_writes_outside_the_range_fail_in_both_engines() -> None:
    g = ranged_game()
    engines: list[Any] = [g]
    try:
        from gamehub.engine.core import available, core_game

        if available():
            engines.append(core_game(g))
    except ImportError:
        pass
    for engine in engines:
        state = engine.new_state(2, {"cap": 4})
        give3 = state.legal_actions(0)[2]
        state = state.apply_action(0, give3)  # 6
        with pytest.raises(RuleError, match=r"chips: 9 fuera de su rango 0\.\.8"):
            state.apply_action(0, give3)


def test_ranges_bound_the_action_space() -> None:
    g = ranged_game()
    space = action_space(g.ir, 2, {"cap": 5})
    assert [(b.name, b.size) for b in space.blocks] == [("give", 3), ("climb", 10)]
    unbounded = dict(g.ir)
    unbounded["state"] = [{k: v for k, v in var.items() if k != "range"} for var in g.ir["state"]]
    with pytest.raises(Unbounded, match="climb"):
        action_space(unbounded, 2, {"cap": 5})


# --- OpenSpiel ---------------------------------------------------------------------------------


def test_openspiel_mccfr_on_holdem() -> None:
    pyspiel = pytest.importorskip("pyspiel")
    from open_spiel.python.algorithms import external_sampling_mccfr, outcome_sampling_mccfr

    from gamehub.analysis.openspiel import to_openspiel

    holdem = to_openspiel(game("texas-holdem"), params={"hands": 1})
    assert holdem.num_distinct_actions() == 1205 and holdem.max_chance_outcomes() == 52
    pyspiel.random_sim_test(holdem, num_sims=2, serialize=False, verbose=False)
    solver = outcome_sampling_mccfr.OutcomeSamplingSolver(holdem)
    for _ in range(50):
        solver.iteration()
    assert len(solver._infostates) > 100  # pyright: ignore[reportAttributeAccessIssue]
    small = to_openspiel(game("texas-holdem"), params={"hands": 1, "stack": 6})
    external = external_sampling_mccfr.ExternalSamplingSolver(small)
    for _ in range(5):
        external.iteration()


@pytest.mark.slow
def test_openspiel_mcts_on_chess() -> None:
    pytest.importorskip("pyspiel")
    import numpy as np
    from open_spiel.python.algorithms import mcts

    from gamehub.analysis.openspiel import to_openspiel

    chess = to_openspiel(game("chess"))
    assert chess.num_distinct_actions() == 20_481
    rng = np.random.RandomState(0)
    evaluator = mcts.RandomRolloutEvaluator(1, rng)
    bot = mcts.MCTSBot(chess, 2.0, 10, evaluator, random_state=rng)
    state = chess.new_initial_state()
    for _ in range(2):
        state.apply_action(bot.step(state))
    assert not state.is_terminal()
