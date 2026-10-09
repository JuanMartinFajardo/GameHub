# SPDX-License-Identifier: Apache-2.0
"""El motor de referencia sobre los juegos de validación de spec/ir/examples."""

from __future__ import annotations

from fractions import Fraction

import pytest

from gamehub.engine import (
    Action,
    Game,
    IllegalAction,
    InvalidParams,
    Pcg32,
    State,
    Status,
    load_game,
)
from gamehub.ir.spec import examples_dir


def game(name: str) -> Game:
    return load_game(examples_dir() / f"{name}.ir.json")


def play(state: State, *moves: tuple[int, Action]) -> State:
    for seat, action in moves:
        state = state.apply_action(seat, action)
    return state


# --- Tres en raya ------------------------------------------------------------------------------


def place(r: int, c: int) -> Action:
    return Action.of("place", c=(r, c))


def test_tictactoe_win_and_turns() -> None:
    s = game("tictactoe").new_state()
    assert s.status is Status.DECISION and s.active_seats == (0,)
    assert len(s.legal_actions(0)) == 9 and s.legal_actions(1) == []
    s = play(s, (0, place(0, 0)), (1, place(0, 1)), (0, place(1, 1)), (1, place(0, 2)))
    s = s.apply_action(0, place(2, 2))
    assert s.is_terminal and s.node == "Win" and s.payoffs == (1, -1)
    assert s.view(1)["state"]["board"][2] == [None, None, "X"]


def test_tictactoe_draw() -> None:
    s = game("tictactoe").new_state()
    cells = [(0, 0), (0, 1), (0, 2), (1, 1), (1, 0), (1, 2), (2, 1), (2, 0), (2, 2)]
    for i, cell in enumerate(cells):
        s = s.apply_action(i % 2, place(*cell))
    assert s.node == "Draw" and s.payoffs == (0, 0)


def test_tictactoe_rejects_illegal_moves() -> None:
    s = game("tictactoe").new_state().apply_action(0, place(1, 1))
    with pytest.raises(IllegalAction, match="no puede actuar"):
        s.apply_action(0, place(0, 0))
    with pytest.raises(IllegalAction, match="condición"):
        s.apply_action(1, place(1, 1))
    with pytest.raises(IllegalAction, match="no permitido"):
        s.apply_action(1, place(3, 0))
    with pytest.raises(IllegalAction, match="desconocida"):
        s.apply_action(1, Action.of("resign"))


def test_states_are_immutable() -> None:
    s0 = game("tictactoe").new_state()
    s1 = s0.apply_action(0, place(0, 0))
    assert s0.value("board").get((0, 0)) is None
    assert s1.value("board").get((0, 0)).name == "X"
    assert s1.parent is s0 and [st.kind for st in s1.history()] == ["start", "action"]


# --- Dilema del prisionero ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("a", "b", "payoffs"),
    [
        ("Cooperate", "Cooperate", (3, 3)),
        ("Cooperate", "Defect", (0, 5)),
        ("Defect", "Cooperate", (5, 0)),
        ("Defect", "Defect", (1, 1)),
    ],
)
def test_prisoners_dilemma_payoffs(a: str, b: str, payoffs: tuple[int, int]) -> None:
    pd = game("prisoners-dilemma")
    choice = lambda name: Action.of("choose", c=pd.defn.types.enum_value("Choice", name))  # noqa: E731
    s = pd.new_state().apply_action(0, choice(a))
    assert s.active_seats == (1,)
    assert s.events(1) == [{"type": "submitted", "seat": 0}]  # la elección sigue oculta
    s = s.apply_action(1, choice(b))
    assert s.payoffs == payoffs
    assert {"type": "action", "seat": 0, "name": "choose", "args": {"c": a}} in s.events(1)


def test_prisoners_dilemma_params_and_constraints() -> None:
    pd = game("prisoners-dilemma")
    s = pd.new_state(params={"T": 6, "R": "7/2"})
    assert s.params["T"] == 6 and s.params["R"] == Fraction(7, 2)
    with pytest.raises(InvalidParams, match="T > R > P > S"):
        pd.new_state(params={"T": 2})
    with pytest.raises(InvalidParams, match="desconocidos"):
        pd.new_state(params={"Q": 1})
    with pytest.raises(InvalidParams, match="de 2 a 2 jugadores"):
        pd.new_state(num_players=3)


# --- Póker de Kuhn -----------------------------------------------------------------------------


def kuhn_deal(order: str) -> State:
    """Estado tras repartir: `order` = carta del asiento 0 y del asiento 1, p. ej. "JQ"."""
    s = game("kuhn-poker").new_state()
    for outcome, _ in s.chance_outcomes():
        dealt = s.apply_chance(outcome)
        hands = [dealt.value("hand")[i].values()[0].name for i in (0, 1)]
        if "".join(hands) == order:
            return dealt
    raise AssertionError(order)


def test_kuhn_chance_is_enumerable() -> None:
    outcomes = game("kuhn-poker").new_state().chance_outcomes()
    assert len(outcomes) == 6 and all(p == Fraction(1, 6) for _, p in outcomes)


@pytest.mark.parametrize(
    ("deal", "moves", "payoffs"),
    [
        ("KQ", ["check", "check"], (1, -1)),
        ("JQ", ["check", "check"], (-1, 1)),
        ("JQ", ["bet", "fold"], (1, -1)),
        ("KJ", ["check", "bet", "fold"], (-1, 1)),
        ("QK", ["bet", "call"], (-2, 2)),
        ("KQ", ["check", "bet", "call"], (2, -2)),
    ],
)
def test_kuhn_payoffs(deal: str, moves: list[str], payoffs: tuple[int, int]) -> None:
    s = kuhn_deal(deal)
    for name in moves:
        s = s.apply_action(s.active_seats[0], Action.of(name))
    assert s.payoffs == payoffs


def test_kuhn_hides_the_opponent_card() -> None:
    s = kuhn_deal("KJ")
    assert s.view(0)["state"]["hand"] == [{"size": 1, "items": ["K"]}, {"size": 1, "items": []}]
    assert s.view(1)["state"]["hand"] == [{"size": 1, "items": []}, {"size": 1, "items": ["J"]}]
    assert s.view(1)["state"]["deck"] == {"size": 1, "items": [{"$hidden": True}]}


def test_kuhn_information_sets() -> None:
    # Con la misma carta y las mismas jugadas, el asiento 1 no distingue los repartos KQ y JQ.
    a = kuhn_deal("KQ").apply_action(0, Action.of("bet"))
    b = kuhn_deal("JQ").apply_action(0, Action.of("bet"))
    assert a.information_state(1) == b.information_state(1)
    assert a.information_state(0) != b.information_state(0)


# --- Mentiroso ---------------------------------------------------------------------------------


def mentiroso_dealt(seed: int = 1) -> State:
    s = game("mentiroso").new_state(num_players=3)
    assert s.status is Status.CHANCE
    return s.apply_chance(s.sample_chance(Pcg32(seed)))


def test_mentiroso_deal() -> None:
    s = mentiroso_dealt()
    assert [len(h) for h in s.value("hand")] == [18, 17, 17]
    assert len(s.value("deck")) == 0 and s.active_seats == (0,)


def _play_claiming_aces(s: State, honest: bool) -> State:
    hand = s.value("hand")[0].values()
    is_ace = lambda card: card.get("rank").name == "Ace"  # noqa: E731
    card = next(c for c in hand if is_ace(c) == honest)
    return s.apply_action(0, Action.of("play", cards=(card,)))


@pytest.mark.parametrize("honest", [True, False])
def test_mentiroso_challenge(honest: bool) -> None:
    s = _play_claiming_aces(mentiroso_dealt(), honest)
    assert s.node == "Challenge" and set(s.active_seats) == {1, 2}
    seen_by_1 = s.events(1)[0]
    assert seen_by_1["type"] == "move" and seen_by_1["items"] == [{"$hidden": True}]
    claim = next(e for e in s.events(1) if e["type"] == "emit")
    assert claim["fields"] == {"seat": 0, "count": 1, "rank": "Ace"}
    s = s.apply_action(1, Action.of("liar"))
    assert s.active_seats == (2,)
    s = s.apply_action(2, Action.of("pass"))
    loser = 1 if honest else 0
    assert len(s.value("hand")[loser]) == 18  # 17 + la carta del montón, o 18 - 1 + 1
    assert len(s.value("pile")) == 0
    assert any(e["type"] == "reveal" for e in s.events(2))
    assert s.node == "Play" and s.active_seats == (1,) and s.value("rank").name == "Two"


def test_mentiroso_canonicalizes_card_order() -> None:
    s = mentiroso_dealt()
    hand = s.value("hand")[0].values()
    a = s.apply_action(0, Action.of("play", cards=(hand[1], hand[0])))
    b = s.apply_action(0, Action.of("play", cards=(hand[0], hand[1])))
    assert a.step.action == b.step.action
