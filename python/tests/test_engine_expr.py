# SPDX-License-Identifier: Apache-2.0
"""Semántica de los operadores de expresión y sentencia del motor de referencia."""

from __future__ import annotations

from fractions import Fraction
from typing import Any

import pytest

from gamehub.engine.env import Ctx, Env
from gamehub.engine.errors import RuleError
from gamehub.engine.expr import OPERATORS, ExprCompiler
from gamehub.engine.stmt import StmtCompiler
from gamehub.engine.values import Grid, SetValue, TypeTable
from gamehub.ir.catalog import load_catalog

TYPES = TypeTable([{"kind": "enum", "name": "Rank", "values": ["Low", "Mid", "High"]}])


def ev(e: list[Any], n: int = 3, **locals_: Any) -> Any:
    fn = ExprCompiler(TYPES).compile(e)
    return fn(Env(Ctx(None, [], {"num_players": n}, n), locals_=locals_))  # type: ignore[arg-type]


def c(v: Any) -> list[Any]:
    return ["const", v]


def lst(*xs: Any) -> list[Any]:
    return ["list", *(c(x) for x in xs)]


def test_every_catalog_operator_is_implemented() -> None:
    catalog = load_catalog()
    assert set(catalog.expressions) == set(OPERATORS)
    missing = [s for s in catalog.statements if not hasattr(StmtCompiler, f"_{s}")]
    assert missing == []


def test_exact_arithmetic() -> None:
    assert ev(["div", c(1), c(3)]) == Fraction(1, 3)
    assert ev(["add", ["div", c(1), c(3)], ["div", c(2), c(3)]]) == 1
    assert isinstance(ev(["add", ["div", c(1), c(3)], ["div", c(2), c(3)]]), int)
    assert ev(["idiv", c(-7), c(2)]) == -4
    assert ev(["mod", c(-7), c(3)]) == 2
    assert ev(["rat", 6, 4]) == Fraction(3, 2)
    with pytest.raises(RuleError, match="división por cero"):
        ev(["div", c(1), c(0)])
    with pytest.raises(RuleError, match="espera números"):
        ev(["add", c(1), c("x")])


def test_logic_short_circuits() -> None:
    assert ev(["or", c(True), ["unwrap", c(None)]]) is True
    assert ev(["and", c(False), ["unwrap", c(None)]]) is False
    with pytest.raises(RuleError):
        ev(["and", c(1), c(True)])


def test_enums_compare_by_declaration_order() -> None:
    assert ev(["lt", ["enum", "Rank", "Low"], ["enum", "Rank", "High"]]) is True
    assert ev(["ord", ["enum", "Rank", "Mid"]]) == 1
    ranks = ev(["enum_values", "Rank"])
    assert [r.name for r in ranks] == ["Low", "Mid", "High"]


def test_collections() -> None:
    assert ev(["slice", lst(1, 2, 3, 4), c(-2), c(2)]) == (1, 2)
    assert ev(["range", c(2), c(4)]) == (2, 3, 4)
    assert ev(["range", c(3), c(2)]) == ()
    assert ev(["difference", lst(3, 1, 2, 1), lst(1)]) == (3, 2)
    assert ev(["union", lst(3, 1), lst(2, 1)]) == SetValue((1, 2, 3))
    assert ev(["distinct", lst(2, 1, 2)]) == (2, 1)
    assert ev(["only", lst(9)]) == 9
    with pytest.raises(RuleError, match="exactamente un elemento"):
        ev(["only", lst(1, 2)])
    with pytest.raises(RuleError, match="fuera de rango"):
        ev(["index", lst(1, 2), c(2)])


def test_subsets_are_canonical_multisets() -> None:
    subsets = ev(["subsets", lst(2, 1, 1), c(1), c(2)])
    assert subsets == ((1,), (2,), (1, 1), (1, 2))


def test_comprehensions_bind_the_variable() -> None:
    xs = lst(3, 1, 2)
    assert ev(["map", "x", xs, ["mul", ["local", "x"], c(2)]]) == (6, 2, 4)
    assert ev(["filter", "x", xs, ["gt", ["local", "x"], c(1)]]) == (3, 2)
    assert ev(["count", "x", xs, ["gt", ["local", "x"], c(1)]]) == 2
    assert ev(["sum", "x", lst(), ["local", "x"]]) == 0
    assert ev(["argmax", "x", lst(1, 3, 3), ["local", "x"]]) == 3
    assert ev(["argmin", "x", lst("b", "a"), ["local", "x"]]) == "a"
    assert ev(["sort_by", "x", lst(3, 1, 2), ["neg", ["local", "x"]]]) == (3, 2, 1)
    assert ev(["flat_map", "x", lst(1, 2), ["list", ["local", "x"], ["local", "x"]]]) == (
        1,
        1,
        2,
        2,
    )
    assert ev(["let", "y", c(5), ["add", ["local", "y"], c(1)]]) == 6


def test_seats() -> None:
    assert ev(["seats"], n=4) == (0, 1, 2, 3)
    assert ev(["next_seat", c(3)], n=4) == 0
    assert ev(["prev_seat", c(0)], n=4) == 3
    assert ev(["seats_from", c(2)], n=4) == (2, 3, 0, 1)
    assert ev(["other_seat", c(1)], n=2) == 0
    with pytest.raises(RuleError, match="2 jugadores"):
        ev(["other_seat", c(1)], n=3)


def test_grid_operators() -> None:
    g = Grid.filled(3, 3, None)
    assert len(ev(["lines", ["local", "g"], c(3)], g=g)) == 8
    assert len(ev(["lines", ["local", "g"], c(2)], g=g)) == 6 + 6 + 4 + 4
    assert ev(["cells", ["local", "g"]], g=g)[:2] == ((0, 0), (0, 1))
    assert len(ev(["neighbors", ["local", "g"], ["cell", c(0), c(0)]], g=g)) == 3
    assert len(ev(["neighbors", ["local", "g"], ["cell", c(1), c(1)]], g=g)) == 8


def test_payoff_helpers() -> None:
    assert ev(["win_loss", c(1), c(1), c(-1)], n=3) == (-1, 1, -1)
    assert ev(["fill", ["div", c(1), c(2)]], n=2) == (Fraction(1, 2), Fraction(1, 2))
