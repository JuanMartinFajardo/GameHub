# SPDX-License-Identifier: Apache-2.0
"""Semántica del flow con juegos sintéticos mínimos."""

from __future__ import annotations

from typing import Any

import pytest

from gamehub.engine import PASS, Action, Game, RuleError, Status

Node = dict[str, Any]


def c(v: Any) -> list[Any]:
    return ["const", v]


def var(name: str) -> list[Any]:
    return ["var", name]


def log(n: int) -> list[Any]:
    """Sentencia: añade n al registro `log`."""
    return ["assign", var("log"), ["append", var("log"), c(n)]]


def make_game(
    nodes: list[Node],
    *,
    players: int = 1,
    state: list[dict[str, Any]] | None = None,
    setup: list[Any] | None = None,
    start: str | None = None,
) -> Game:
    base_state = [{"name": "log", "type": ["list", "Int"], "init": ["list"]}]
    flow: dict[str, Any] = {"start": start or nodes[0]["id"], "nodes": nodes}
    if setup:
        flow["setup"] = setup
    return Game(
        {
            "ir_version": "0.1.0",
            "game": {"id": "synthetic", "version": "0.0.1"},
            "players": {"min": players, "max": players},
            "state": base_state + (state or []),
            "flow": flow,
        }
    )


END: Node = {"id": "End", "kind": "terminal", "payoff": ["fill", ["len", var("log")]]}


def test_phases_enter_exit_and_loops() -> None:
    nodes = [
        {
            "id": "Match",
            "kind": "phase",
            "start": "Round",
            "on_enter": [log(1)],
            "on_exit": [log(9)],
            "transitions": [{"to": "End"}],
            "nodes": [
                {
                    "id": "Round",
                    "kind": "phase",
                    "start": "Turn",
                    "on_enter": [log(2), ["assign", var("rounds"), ["add", var("rounds"), c(1)]]],
                    "on_exit": [log(8)],
                    "transitions": [
                        {"to": "$exit", "when": ["ge", var("rounds"), c(2)]},
                        {"to": "Round"},
                    ],
                    "nodes": [
                        {
                            "id": "Turn",
                            "kind": "decision",
                            "actor": c(0),
                            "actions": [{"name": "go", "requires": ["at", "Round"]}],
                            "transitions": [{"to": "$exit"}],
                        }
                    ],
                }
            ],
        },
        END,
    ]
    rounds = {"name": "rounds", "type": "Int", "init": c(0)}
    s = make_game(nodes, state=[rounds]).new_state()
    assert s.node == "Turn" and s.value("log") == (1, 2)
    s = s.apply_action(0, Action("go"))
    assert s.node == "Turn" and s.value("log") == (1, 2, 8, 2)
    s = s.apply_action(0, Action("go"))
    assert s.is_terminal and s.value("log") == (1, 2, 8, 2, 8, 9)


def _window(mode: str, order: list[Any] | None = None) -> Game:
    window: Node = {
        "id": "Shout",
        "kind": "window",
        "eligible": ["list", c(1), c(2), c(3)],
        "mode": mode,
        "actions": [{"name": "shout", "effects": [["assign", var("caller"), ["actor"]]]}],
        "transitions": [{"to": "End"}],
    }
    if order is not None:
        window["order"] = order
    caller = {"name": "caller", "type": ["option", "Seat"], "init": c(None)}
    return make_game([window, END], players=4, state=[caller])


def test_priority_window_asks_in_order() -> None:
    s = _window("priority", ["list", c(2), c(3)]).new_state()
    assert s.active_seats == (2,)
    assert s.legal_actions(2) == [Action("shout"), PASS]
    s = s.apply_action(2, PASS)
    assert s.active_seats == (3,)
    s = s.apply_action(3, Action("shout"))
    assert s.is_terminal and s.value("caller") == 3


def test_priority_window_all_pass() -> None:
    s = _window("priority").new_state()
    for seat in (1, 2, 3):
        s = s.apply_action(seat, PASS)
    assert s.is_terminal and s.value("caller") is None


def test_collect_window_resolves_by_priority() -> None:
    s = _window("collect", ["list", c(3), c(2), c(1)]).new_state()
    assert s.active_seats == (3, 2, 1)
    s = s.apply_action(1, Action("shout"))
    s = s.apply_action(3, PASS)
    assert s.view(None)["responded"] == [1, 3]
    s = s.apply_action(2, Action("shout"))
    assert s.value("caller") == 2  # 2 precede a 1 en el orden de prioridad
    responses = next(e for e in s.events(0) if e["type"] == "responses")
    assert [r["name"] for r in responses["responses"]] == ["pass", "shout", "shout"]


def test_race_window_first_action_wins() -> None:
    s = _window("race").new_state()
    s = s.apply_action(2, PASS).apply_action(3, Action("shout"))
    assert s.is_terminal and s.value("caller") == 3


def test_simultaneous_resolve_block() -> None:
    nodes = [
        {
            "id": "Bid",
            "kind": "simultaneous",
            "actors": ["seats"],
            "actions": [
                {
                    "name": "bid",
                    "params": [{"name": "x", "type": "Int", "domain": ["range", c(0), c(3)]}],
                    "effects": [log_arg("x")],
                }
            ],
            "resolve": [["assign", var("total"), ["sum", "v", var("log"), ["local", "v"]]]],
            "transitions": [{"to": "End"}],
        },
        END,
    ]
    total = {"name": "total", "type": "Int", "init": c(0)}
    s = make_game(nodes, players=3, state=[total]).new_state()
    s = s.apply_action(2, Action.of("bid", x=3)).apply_action(0, Action.of("bid", x=1))
    assert s.value("log") == () and s.active_seats == (1,)
    s = s.apply_action(1, Action.of("bid", x=2))
    assert s.value("log") == (1, 2, 3)  # efectos en orden de asiento
    assert s.value("total") == 6 and s.is_terminal


def log_arg(name: str) -> list[Any]:
    return ["assign", var("log"), ["append", var("log"), ["arg", name]]]


def test_auto_loop_without_progress_is_detected() -> None:
    nodes = [{"id": "Spin", "kind": "auto", "transitions": [{"to": "Spin"}]}, END]
    with pytest.raises(RuleError, match="bucle sin progreso"):
        make_game(nodes).new_state()


def test_long_auto_chains_do_not_overflow_the_stack() -> None:
    count = ["assign", var("n"), ["add", var("n"), c(1)]]
    nodes = [
        {
            "id": "Count",
            "kind": "auto",
            "effects": [count],
            "transitions": [{"to": "End", "when": ["ge", var("n"), c(5000)]}, {"to": "Count"}],
        },
        END,
    ]
    s = make_game(nodes, state=[{"name": "n", "type": "Int", "init": c(0)}]).new_state()
    assert s.is_terminal and s.value("n") == 5000


def test_decision_without_legal_actions_is_a_rule_error() -> None:
    nodes = [
        {
            "id": "Stuck",
            "kind": "decision",
            "actor": c(0),
            "actions": [{"name": "go", "requires": c(False)}],
            "transitions": [{"to": "End"}],
        },
        END,
    ]
    with pytest.raises(RuleError, match="ninguna acción legal"):
        make_game(nodes).new_state()


def test_payoff_length_is_checked() -> None:
    nodes = [{"id": "End", "kind": "terminal", "payoff": ["list", c(1)]}]
    with pytest.raises(RuleError, match="1 valores para 2 asientos"):
        make_game(nodes, players=2).new_state()


def test_random_setup_is_a_chance_point() -> None:
    nodes = [{"id": "End", "kind": "terminal", "payoff": ["fill", var("die")]}]
    die = {"name": "die", "type": "Int", "init": c(0)}
    g = make_game(nodes, state=[die], setup=[["roll", var("die"), c(6)]])
    s = g.new_state()
    assert s.status is Status.CHANCE and s.node is None
    outcomes = s.chance_outcomes()
    assert [o for o, _ in outcomes] == [(i,) for i in range(6)]
    assert s.apply_chance((4,)).payoffs == (5,)
