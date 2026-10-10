# SPDX-License-Identifier: Apache-2.0
"""El validador debe rechazar documentos mal formados con un mensaje localizado."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from gamehub.ir import check

Doc = dict[str, Any]


def _guess(doc: Doc) -> Doc:
    return doc["flow"]["nodes"][0]


def _end(doc: Doc) -> Doc:
    return doc["flow"]["nodes"][2]


def unknown_op(doc: Doc) -> None:
    _end(doc)["payoff"] = ["frobnicate", ["const", 1]]


def wrong_arity(doc: Doc) -> None:
    doc["functions"][0]["body"] = ["not"]


def missing_flow(doc: Doc) -> None:
    del doc["flow"]


def unknown_target(doc: Doc) -> None:
    _guess(doc)["transitions"] = [{"to": "Nowhere"}]


def chance_outside_chance_node(doc: Doc) -> None:
    effects = _guess(doc)["actions"][0]["effects"]
    effects.append(["random_choice", ["var", "coin"], ["enum_values", "Side"]])


def actor_in_payoff(doc: Doc) -> None:
    _end(doc)["payoff"] = ["fill", ["actor"]]


def recursion(doc: Doc) -> None:
    doc["functions"][0]["body"] = ["call", "hit"]


def exit_outside_phase(doc: Doc) -> None:
    _guess(doc)["transitions"] = [{"to": "$exit"}]


def unconditional_first(doc: Doc) -> None:
    _guess(doc)["transitions"] = [{"to": "Flip"}, {"to": "End", "when": ["const", True]}]


def owner_on_shared_var(doc: Doc) -> None:
    doc["state"][0]["visibility"] = "owner"


def unknown_enum_value(doc: Doc) -> None:
    _end(doc)["payoff"] = [
        "fill",
        ["if", ["eq", ["var", "coin"], ["enum", "Side", "Edge"]], ["const", 1], ["const", 0]],
    ]


def unbound_local(doc: Doc) -> None:
    _end(doc)["payoff"] = ["fill", ["local", "x"]]


def binder_not_visible_in_collection(doc: Doc) -> None:
    _end(doc)["payoff"] = ["fill", ["count", "x", ["list", ["local", "x"]], ["const", True]]]


def state_in_param_default(doc: Doc) -> None:
    doc["params"] = [{"name": "k", "type": "Int", "default": ["var", "guess"]}]


def assign_to_constant(doc: Doc) -> None:
    _guess(doc)["actions"][0]["effects"] = [["assign", ["const", 1], ["arg", "s"]]]


def unknown_type(doc: Doc) -> None:
    doc["state"][0]["type"] = ["option", "Coin"]


def duplicate_node(doc: Doc) -> None:
    doc["flow"]["nodes"][1]["id"] = "Guess"


def wrong_call_arity(doc: Doc) -> None:
    _end(doc)["payoff"] = [
        "fill",
        ["if", ["call", "hit", ["const", 1]], ["const", 1], ["const", 0]],
    ]


def window_without_exit(doc: Doc) -> None:
    doc["flow"]["nodes"][1] = {
        "id": "Flip",
        "kind": "window",
        "eligible": ["seats"],
        "mode": "priority",
        "actions": [{"name": "shout"}],
    }


def bad_struct_literal(doc: Doc) -> None:
    doc["types"].append(
        {
            "kind": "struct",
            "name": "Pair",
            "fields": [{"name": "a", "type": "Int"}, {"name": "b", "type": "Int"}],
        }
    )
    _end(doc)["payoff"] = ["fill", ["field", ["struct", "Pair", {"a": ["const", 1]}], "a"]]


CASES: list[tuple[Callable[[Doc], None], str, str]] = [
    (unknown_op, "flow/nodes/2/payoff", "frobnicate"),
    (wrong_arity, "functions/0/body", "too short"),
    (missing_flow, "", "'flow' is a required property"),
    (unknown_target, "flow/nodes/0/transitions/0/to", "nodo desconocido: Nowhere"),
    (chance_outside_chance_node, "flow/nodes/0/actions/0/effects/1", "es aleatoria"),
    (actor_in_payoff, "flow/nodes/2/payoff/1", "'actor' solo existe"),
    (recursion, "functions", "recursión no permitida: hit → hit"),
    (exit_outside_phase, "flow/nodes/0/transitions/0/to", "'$exit' solo se permite"),
    (unconditional_first, "flow/nodes/0/transitions/0", "transición incondicional"),
    (owner_on_shared_var, "state/0/visibility", "'owner' solo tiene sentido"),
    (unknown_enum_value, "flow/nodes/2/payoff", "Side no tiene el valor Edge"),
    (unbound_local, "flow/nodes/2/payoff/1", "variable local no ligada: x"),
    (binder_not_visible_in_collection, "flow/nodes/2/payoff", "variable local no ligada: x"),
    (state_in_param_default, "params/0/default", "no se puede leer el estado"),
    (assign_to_constant, "flow/nodes/0/actions/0/effects/0/1", "solo se puede modificar el estado"),
    (unknown_type, "state/0/type/1", "tipo desconocido: Coin"),
    (duplicate_node, "flow/nodes/1/id", "id de nodo duplicado: Guess"),
    (wrong_call_arity, "flow/nodes/2/payoff", "hit espera 0 argumentos, recibe 1"),
    (window_without_exit, "flow/nodes/1", "una ventana necesita transiciones"),
    (bad_struct_literal, "flow/nodes/2/payoff", "Pair requiere exactamente los campos"),
]


def test_base_game_is_valid(coin_game: Doc) -> None:
    assert check(coin_game) == []


@pytest.mark.parametrize(
    ("mutate", "path_prefix", "fragment"), CASES, ids=lambda c: getattr(c, "__name__", "")
)
def test_invalid_document_is_rejected(
    coin_game: Doc, mutate: Callable[[Doc], None], path_prefix: str, fragment: str
) -> None:
    mutate(coin_game)
    problems = check(coin_game)
    assert any(p.path.startswith(path_prefix) and fragment in p.message for p in problems), (
        f"no se encontró {fragment!r} en {path_prefix!r}: {[str(p) for p in problems]}"
    )


def test_exit_inside_phase_is_valid(coin_game: Doc) -> None:
    guess, flip, end = coin_game["flow"]["nodes"]
    flip["transitions"] = [{"to": "$exit"}]
    coin_game["flow"]["nodes"] = [
        {
            "id": "Round",
            "kind": "phase",
            "start": "Guess",
            "nodes": [guess, flip],
            "transitions": [{"to": "End"}],
        },
        end,
    ]
    coin_game["flow"]["start"] = "Round"
    assert check(coin_game) == []


def test_window_reserves_pass(coin_game: Doc) -> None:
    window_without_exit(coin_game)
    window = coin_game["flow"]["nodes"][1]
    window["actions"] = [{"name": "pass"}]
    window["transitions"] = [{"to": "End"}]
    assert any("'pass' está reservado" in p.message for p in check(coin_game))


def test_simultaneous_actions_cannot_transition(coin_game: Doc) -> None:
    guess = coin_game["flow"]["nodes"][0]
    guess["kind"] = "simultaneous"
    guess["actors"] = guess.pop("actor")
    guess["actions"][0]["transitions"] = [{"to": "Flip"}]
    problems = check(coin_game)
    assert any("se resuelven juntas" in p.message for p in problems), problems


def test_phase_without_transitions_cannot_be_exited(coin_game: Doc) -> None:
    test_exit_inside_phase_is_valid(coin_game)
    coin_game["flow"]["nodes"][0]["transitions"] = []
    assert any("la fase no tiene transiciones" in p.message for p in check(coin_game))


def test_at_can_reference_nodes_from_state_visibility(coin_game: Doc) -> None:
    """Regresión: `at(Nodo)` en la visibilidad del estado se revisaba antes de reunir los nodos."""
    coin_game["state"][0]["visibility"] = {"when": ["at", "Guess"]}
    coin_game["functions"][0]["body"] = ["at", "Flip"]
    assert check(coin_game) == []
