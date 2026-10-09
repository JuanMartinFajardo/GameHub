# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from gamehub.ir.hashing import canonical_json, rules_hash
from gamehub.ir.spec import examples_dir, load_json


@pytest.fixture
def ttt() -> dict[str, Any]:
    return load_json(examples_dir() / "tictactoe.ir.json")


def test_hash_format(ttt: dict[str, Any]) -> None:
    h = rules_hash(ttt)
    assert h.startswith("sha256:") and len(h) == len("sha256:") + 64


def test_hash_ignores_cosmetics(ttt: dict[str, Any]) -> None:
    variant = json.loads(json.dumps(ttt, indent=7, sort_keys=False))
    variant["meta"] = {"title": "Otro título"}
    variant["functions"][0]["doc"] = "comentario"
    variant["flow"]["nodes"][0]["transitions"][0]["doc"] = {"es": "gana"}
    reordered = dict(reversed(list(variant.items())))
    assert rules_hash(reordered) == rules_hash(ttt)


def test_hash_ignores_constraint_messages() -> None:
    pd = load_json(examples_dir() / "prisoners-dilemma.ir.json")
    variant = copy.deepcopy(pd)
    variant["constraints"][0]["message"] = "otro texto"
    assert rules_hash(variant) == rules_hash(pd)


def test_hash_changes_with_rules(ttt: dict[str, Any]) -> None:
    variant = copy.deepcopy(ttt)
    variant["flow"]["nodes"][1]["payoff"][2] = ["const", 2]
    assert rules_hash(variant) != rules_hash(ttt)


def test_doc_inside_expressions_is_part_of_the_rules() -> None:
    a = {"x": ["struct", "Note", {"doc": ["const", 1]}]}
    b = {"x": ["struct", "Note", {"doc": ["const", 2]}]}
    assert rules_hash(a) != rules_hash(b)


def test_canonical_json_is_compact_sorted_utf8() -> None:
    assert canonical_json({"b": 1, "a": ["ñ", None, True]}) == '{"a":["ñ",null,true],"b":1}'


def test_floats_are_rejected() -> None:
    with pytest.raises(TypeError):
        canonical_json({"x": 0.5})


def test_hash_ignores_explicit_defaults(ttt: dict[str, Any]) -> None:
    variant = copy.deepcopy(ttt)
    for var in variant["state"]:
        var.pop("visibility", None)
    variant["params"] = []
    variant["flow"]["nodes"][0]["actions"][0]["transitions"] = []
    assert rules_hash(variant) == rules_hash(ttt)
