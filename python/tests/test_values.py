# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from fractions import Fraction

import pytest

from gamehub.engine.errors import RuleError
from gamehub.engine.values import Grid, MapValue, SetValue, TypeTable, Zone, ZoneItem, sort_key

DECLS = [
    {"kind": "enum", "name": "Suit", "values": ["Clubs", "Hearts"]},
    {"kind": "enum", "name": "Rank", "values": ["Ace", "Two"]},
    {
        "kind": "struct",
        "name": "Card",
        "fields": [{"name": "suit", "type": "Suit"}, {"name": "rank", "type": "Rank"}],
    },
]


@pytest.fixture
def types() -> TypeTable:
    return TypeTable(DECLS)


def test_sets_and_bags_are_canonical(types: TypeTable) -> None:
    two, ace = types.enum_value("Rank", "Two"), types.enum_value("Rank", "Ace")
    assert SetValue.of([two, ace, two]).items == (ace, two)
    assert Zone.of([two, ace], ordered=False) == Zone.of([ace, two], ordered=False)
    assert Zone.of([two, ace]) != Zone.of([ace, two])


def test_sort_key_is_total_across_kinds() -> None:
    values = [Fraction(1, 2), None, "a", True, (1, 2), 3]
    assert sorted(values, key=sort_key) == [None, True, Fraction(1, 2), 3, "a", (1, 2)]


def test_map_get_and_set() -> None:
    m = MapValue.of([("b", 2), ("a", 1)]).set("c", 3).set("a", 9)
    assert m.items == (("a", 9), ("b", 2), ("c", 3))
    with pytest.raises(RuleError):
        m.get("z")


def test_grid_bounds() -> None:
    g = Grid.filled(3, 2, None).set((1, 2), "x")
    assert g.get((1, 2)) == "x" and g.rows()[1] == (None, None, "x")
    with pytest.raises(RuleError, match="fuera de la rejilla"):
        g.get((2, 0))


def test_json_roundtrip(types: TypeTable) -> None:
    card = types.parse("Card")
    hand = types.parse(["list", "Card"])
    j = [{"suit": "Hearts", "rank": "Ace"}, {"suit": "Clubs", "rank": "Two"}]
    value = types.decode(j, hand)
    assert types.encode(value, hand) == j
    assert types.decode({"suit": "Hearts", "rank": "Two"}, card).get("rank").name == "Two"
    real = types.parse("Real")
    assert types.encode(Fraction(5, 2), real) == "5/2"
    assert types.decode("4/2", real) == 2 and isinstance(types.decode("4/2", real), int)
    bag = types.parse(["bag", "Rank"])
    assert types.encode(types.decode(["Two", "Ace"], bag), bag) == {
        "size": 2,
        "items": ["Ace", "Two"],
    }


def test_decode_rejects_bad_values(types: TypeTable) -> None:
    with pytest.raises(ValueError):
        types.decode({"suit": "Hearts"}, types.parse("Card"))
    with pytest.raises(ValueError):
        types.decode("Joker", types.parse("Rank"))
    with pytest.raises(ValueError):
        types.decode(True, types.parse("Int"))


def test_zone_items_keep_face() -> None:
    z = Zone((ZoneItem(1, face_up=True), ZoneItem(2)))
    assert z.values() == (1, 2) and z.items[0].face_up
