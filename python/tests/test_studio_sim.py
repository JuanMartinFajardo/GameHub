# SPDX-License-Identifier: Apache-2.0
"""El simulador del Studio y las plantillas de juego."""

from __future__ import annotations

from pathlib import Path

import pytest

from gamehub import gametemplates
from gamehub.engine import Game
from gamehub.engine.state import TRACE
from gamehub.lang.compiler import compile_file, compile_text
from gamehub.lang.testing import GameTester
from gamehub.packages import new_package
from gamehub.studio.sim import (
    Condition,
    SimError,
    Simulation,
    count_tree,
    estimate_size,
    playouts,
    tree,
)

ROOT = Path(__file__).resolve().parents[2]


def game(name: str) -> Game:
    return Game(compile_file(ROOT / "games" / name / f"{name}.game").game().ir)


def test_time_travel_and_acting_as_any_seat() -> None:
    sim = Simulation(game("tictactoe"))
    assert sim.snapshot(0)["active"] == [0]
    one = sim.act(0, 0, {"name": "place", "args": {"c": [1, 1]}})
    two = sim.act(one, 1, {"name": "place", "args": {"c": [0, 0]}})
    assert two == 2 and sim.snapshot(two)["omniscient"]["state"]["board"][0][0] == "O"
    # Desde un paso anterior se puede jugar otra cosa: la historia se recorta.
    other = sim.act(one, 1, {"name": "place", "args": {"c": [2, 2]}})
    assert other == 2 and len(sim.states) == 3
    assert sim.snapshot(other)["omniscient"]["state"]["board"][2][2] == "O"
    with pytest.raises(SimError, match="ilegal"):
        sim.act(other, 0, {"name": "place", "args": {"c": [1, 1]}})
    with pytest.raises(SimError):
        sim.act(other, 0, {"name": "fly", "args": {}})


def test_each_step_records_its_transitions_and_nodes() -> None:
    sim = Simulation(game("tictactoe"))
    i = sim.act(0, 0, {"name": "place", "args": {"c": [0, 0]}})
    step = sim.steps[i]
    assert step.trace == [["node", "Move", "2"]] and step.nodes == ["Move"]
    assert TRACE.get() is None  # la traza solo existe durante el paso


def test_chance_by_hand_or_at_random() -> None:
    sim = Simulation(game("kuhn-poker"), seed=2)
    snap = sim.snapshot(0)
    assert snap["status"] == "chance" and snap["chance"]["enumerable"]
    outcomes = snap["chance"]["outcomes"]
    assert len(outcomes) == 6 and outcomes[0]["probability"] == "1/6"
    i = sim.chance(0, outcomes[3]["outcome"])
    assert sim.snapshot(i)["step"]["outcome"] == outcomes[3]["outcome"]
    j = sim.chance(0)
    assert j == 1


def test_run_until_the_end_a_node_or_a_condition() -> None:
    sim = Simulation(game("nim"), seed=4)
    end, reason, _ = sim.run(0)
    assert reason == "end" and sim.state(end).is_terminal
    sim = Simulation(game("dudo"), seed=4)
    at, reason, label = sim.run(0, breakpoints=[Condition(node="Bid")])
    assert reason == "breakpoint" and label == "Bid" and sim.state(at).node == "Bid"
    text = (ROOT / "games/dudo/dudo.game").read_text()
    expr = compile_text(text.replace("\n}\n", "\n  invariant quantity >= 2\n}\n", 1))
    assert expr.ok
    sim = Simulation(game("dudo"), seed=4)
    ir = next(iter(expr.games.values())).invariants[-1].expr
    at, reason, label = sim.run(0, breakpoints=[Condition(expr=ir, label="q≥2")])
    assert reason in ("breakpoint", "end")
    if reason == "breakpoint":
        assert sim.state(at).value("quantity") >= 2 and label == "q≥2"
    # Los asientos humanos detienen la carrera.
    sim = Simulation(game("tictactoe"))
    at, reason, _ = sim.run(0, stop_at_humans={1})
    assert reason == "human" and sim.state(at).active_seats == (1,)


def test_reloading_rules_replays_what_still_applies() -> None:
    sim = Simulation(game("tictactoe"))
    i = sim.act(0, 0, {"name": "place", "args": {"c": [0, 0]}})
    sim.act(i, 1, {"name": "place", "args": {"c": [1, 1]}})
    text = (ROOT / "games/tictactoe/tictactoe.game").read_text()
    changed = Game(compile_text(text.replace("payoff: fill(0)", "payoff: fill(1)")).game().ir)
    assert sim.reload(changed) == 2 and len(sim.states) == 3


def test_playouts_and_coverage() -> None:
    stats = playouts(game("tictactoe"), games=40, seed=1)
    assert stats["games"] == stats["finished"] == 40 and not stats["errors"]
    coverage = stats["coverage"]
    assert coverage["nodes"]["Move"] > 40 and coverage["actions"]["Move.place"] > 40
    assert coverage["transitions"]["node/Move/2"] > 0
    assert 5 <= stats["length"]["min"] <= stats["length"]["max"] <= 9
    # En las tablas los dos quedan primeros: cada tasa está entre 0 y 1.
    assert all(r is not None and 0 <= r <= 1 for r in stats["winRate"])
    # Un empate no es una victoria de cada uno: victorias y empates suman 1.
    assert sum(stats["winRate"]) + stats["drawRate"] == pytest.approx(1)
    assert stats["drawRate"] > 0


def test_rule_errors_are_reported() -> None:
    text = (ROOT / "games/tictactoe/tictactoe.game").read_text()
    broken = text.replace("-> Move { turn = next(turn) }", "-> Move when false")
    stats = playouts(Game(compile_text(broken).game().ir), games=5, seed=1)
    assert stats["errorCount"] == 5 and "ninguna transición" in stats["errors"][0]["message"]


def test_tree_count_and_estimate() -> None:
    kuhn = game("kuhn-poker")
    root = kuhn.new_state()
    node = tree(root, [])
    assert node["status"] == "chance" and len(node["children"]) == 6
    deeper = tree(root, [0])
    assert deeper["status"] == "decision" and deeper["children"]
    counted = count_tree(root)
    assert counted == {"complete": True, "states": 55, "terminals": 30, "depth": 4}
    size = estimate_size(kuhn, samples=400, seed=1)
    assert 1.6 < size["log10States"] < 1.9  # ≈ 55 estados
    assert count_tree(game("tictactoe").new_state(), budget=1000)["complete"] is False


@pytest.mark.parametrize("template", gametemplates.ids())
def test_every_template_compiles_and_passes_its_tests(template: str, tmp_path: Path) -> None:
    manifest = new_package(tmp_path / "juego", "juego", template=template, title="Mi juego")
    result = compile_file(manifest.entry_path)
    assert result.ok, [str(d) for d in result.diagnostics.errors]
    assert not result.diagnostics.warnings, [str(d) for d in result.diagnostics.warnings]
    report = GameTester(result.game()).run_all(playouts=5)
    assert report.tests and report.failures == 0, report
    text = manifest.entry_path.read_text(encoding="utf-8")
    assert 'title: "Mi juego"' in text and "game Juego {" in text
