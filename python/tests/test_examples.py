# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from pathlib import Path

import pytest

from gamehub.ir import check_file
from gamehub.ir.spec import examples_dir

EXAMPLES = sorted(examples_dir().glob("*.ir.json"))


def test_validation_games_are_present() -> None:
    names = {p.name for p in EXAMPLES}
    assert {
        "tictactoe.ir.json",
        "prisoners-dilemma.ir.json",
        "kuhn-poker.ir.json",
        "mentiroso.ir.json",
    } <= names


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_example_is_valid(path: Path) -> None:
    assert check_file(path) == []
