# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from collections import Counter
from fractions import Fraction

import pytest

from gamehub.engine.errors import IllegalAction, NotEnumerable
from gamehub.engine.rng import (
    Pcg32,
    RngDraws,
    ScriptedDraws,
    enumerate_outcomes,
    replay_outcome,
)


def test_pcg32_matches_reference_implementation() -> None:
    # Salida de la demo de referencia en C: pcg32_srandom_r(&rng, 42u, 54u).
    rng = Pcg32(42, 54)
    expected = [0xA15C02B7, 0x7B47F409, 0xBA1D3330, 0x83D2F293, 0xBFA4784B, 0xCBED606E]
    assert [rng.next_u32() for _ in expected] == expected


def test_below_is_in_range_and_roughly_uniform() -> None:
    rng = Pcg32(7)
    counts = Counter(rng.below(6) for _ in range(60_000))
    assert set(counts) == set(range(6))
    assert all(9_000 < c < 11_000 for c in counts.values())


def test_streams_are_independent() -> None:
    a, b = Pcg32(1, 1), Pcg32(1, 2)
    assert [a.next_u32() for _ in range(4)] != [b.next_u32() for _ in range(4)]


def test_weighted_respects_probabilities() -> None:
    draws = RngDraws(Pcg32(3))
    probs = [Fraction(1, 4), Fraction(0), Fraction(3, 4)]
    counts = Counter(draws.weighted(probs) for _ in range(8_000))
    assert counts[1] == 0
    assert 1_700 < counts[0] < 2_300
    assert draws.taken.count(2) == counts[2]


def _two_dice(draws: ScriptedDraws) -> None:
    draws.uniform(6)
    draws.uniform(6)


def test_enumerate_two_dice() -> None:
    outcomes = enumerate_outcomes(_two_dice)
    assert len(outcomes) == 36
    assert sum(p for _, p in outcomes) == 1
    assert outcomes[0] == ((0, 0), Fraction(1, 36))


def test_enumerate_dependent_draws() -> None:
    def run(draws: ScriptedDraws) -> None:
        n = draws.uniform(3) + 1  # cuántas monedas lanzar
        for _ in range(n):
            draws.weighted([Fraction(1, 2), Fraction(1, 2)])

    outcomes = dict(enumerate_outcomes(run))
    assert outcomes[(0, 1)] == Fraction(1, 6)
    assert outcomes[(2, 0, 1, 1)] == Fraction(1, 24)
    assert sum(outcomes.values()) == 1


def test_enumeration_limit() -> None:
    with pytest.raises(NotEnumerable):
        enumerate_outcomes(_two_dice, limit=10)


def test_replay_outcome_checks_length_and_range() -> None:
    replay_outcome(_two_dice, (5, 0))
    with pytest.raises(IllegalAction, match="incompleto"):
        replay_outcome(_two_dice, (5,))
    with pytest.raises(IllegalAction, match="de más"):
        replay_outcome(_two_dice, (5, 0, 1))
    with pytest.raises(IllegalAction, match="fuera de rango"):
        replay_outcome(_two_dice, (6, 0))
