# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy

import pytest

from gamehub.engine import Game, IllegalAction, RuleError, load_game
from gamehub.engine.conformance import sync, verify_all
from gamehub.engine.match import FirstAgent, RandomAgent, fuzz, play_match
from gamehub.engine.replay import ReplayMismatch, record, replay
from gamehub.ir.spec import examples_dir

GAMES = [
    ("tictactoe", 2),
    ("prisoners-dilemma", 2),
    ("rock-paper-scissors", 2),
    ("nim", 2),
    ("kuhn-poker", 2),
    ("mentiroso", 3),
]


def game(name: str) -> Game:
    return load_game(examples_dir() / f"{name}.ir.json")


@pytest.mark.parametrize(("name", "n"), GAMES)
def test_record_and_replay_roundtrip(name: str, n: int) -> None:
    g = game(name)
    for seed in (10, 11):
        result = play_match(g, [RandomAgent(seed, s) for s in range(n)], seed=seed, num_players=n)
        assert result.state.is_terminal
        data = record(result.state, seed)
        again = replay(g, data)
        assert again.digest() == result.state.digest()
        assert again.payoffs == result.payoffs


def test_matches_are_deterministic() -> None:
    g = game("mentiroso")

    def run(seed: int) -> str:
        agents = [RandomAgent(seed, s) for s in range(3)]
        return play_match(g, agents, seed=seed, num_players=3).state.digest()

    assert run(5) == run(5)
    assert run(5) != run(6)


def test_tampered_replays_are_rejected() -> None:
    g = game("kuhn-poker")
    data = record(play_match(g, [FirstAgent(), FirstAgent()], seed=3).state, 3)
    swapped = copy.deepcopy(data)
    swapped["steps"][0]["chance"] = [0, 0] if data["steps"][0]["chance"] != [0, 0] else [1, 0]
    with pytest.raises(ReplayMismatch, match="diverge"):
        replay(g, swapped)
    truncated = copy.deepcopy(data)
    truncated["steps"][0]["chance"] = [0]
    with pytest.raises(IllegalAction, match="incompleto"):
        replay(g, truncated)
    other_rules = copy.deepcopy(data)
    other_rules["game"]["rules_hash"] = "sha256:" + "0" * 64
    with pytest.raises(ReplayMismatch, match="otra versión"):
        replay(g, other_rules)


def test_conformance_traces_are_current_and_reproducible() -> None:
    assert sync(write=False) == []
    assert verify_all() == []


def test_fuzz_small_games() -> None:
    for name, n in GAMES[:5]:
        report = fuzz(game(name), 200, seed=1, num_players=n)
        assert report.completed == 200 and report.errors == [] and report.truncated == 0


def test_fuzz_reports_rule_errors() -> None:
    ir = copy.deepcopy(game("tictactoe").ir)
    # Error de diseño deliberado: tras 3 jugadas se lee un opcional vacío.
    move = ir["flow"]["nodes"][0]
    move["transitions"].insert(
        0,
        {
            "to": "Draw",
            "when": [
                "eq",
                [
                    "count",
                    "c",
                    ["cells", ["var", "board"]],
                    ["not", ["is_none", ["index", ["var", "board"], ["local", "c"]]]],
                ],
                ["unwrap", ["const", None]],
            ],
        },
    )
    seen: list[int] = []
    report = fuzz(Game(ir), 3, on_error=lambda seed, state, exc: seen.append(seed))
    assert len(report.errors) == 3 and seen == [0, 1, 2]
    assert "unwrap" in report.errors[0][1]
    with pytest.raises(RuleError):
        play_match(Game(ir), [FirstAgent(), FirstAgent()])
