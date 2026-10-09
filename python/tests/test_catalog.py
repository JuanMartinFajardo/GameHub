# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from gamehub.ir.catalog import build_schemas, catalog_problems, load_catalog, render
from gamehub.ir.spec import spec_dir


def test_catalog_is_well_formed() -> None:
    assert catalog_problems(load_catalog()) == []


def test_generated_schemas_are_up_to_date() -> None:
    for filename, schema in build_schemas(load_catalog()).items():
        on_disk = (spec_dir() / filename).read_text(encoding="utf-8")
        assert on_disk == render(schema), f"{filename} desactualizado: gamehub ir schemas --write"


def test_randomness_is_confined_to_known_statements() -> None:
    assert load_catalog().chance_statements == {"shuffle", "roll", "random_choice", "sample"}


def test_variadic_expansion() -> None:
    add = load_catalog().expressions["add"]
    assert add.min_args == 2
    assert add.kinds_for(4) == ["e", "e", "e", "e"]
    move = load_catalog().statements["move"]
    assert move.kinds_for(3) == ["l", "l", "sel"]
