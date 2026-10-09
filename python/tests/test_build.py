# SPDX-License-Identifier: Apache-2.0
"""La API builder produce exactamente las mismas reglas (mismo hash) que los ejemplos escritos
a mano: dos definiciones independientes que se verifican entre sí."""

from __future__ import annotations

from typing import Any

import pytest

from gamehub.build import (
    GameBuilder,
    T,
    all_,
    any_,
    arg,
    assign,
    case,
    const,
    if_,
    let,
    map_,
    op,
    p,
    param,
    seats,
    sum_,
)
from gamehub.engine import Action, RuleError, load_game
from gamehub.ir.hashing import rules_hash
from gamehub.ir.spec import examples_dir, load_json


def build_tictactoe() -> dict[str, Any]:
    g = GameBuilder("tictactoe", "1.0.0", players=2, title={"es": "Tres en raya"})
    mark_t = g.enum("Mark", ["X", "O"])
    board = g.state("board", T.grid(3, 3, T.option("Mark")), const(None))
    turn = g.state("turn", "Seat", const(0))
    mark = g.function("mark", [("p", "Seat")], "Mark", lambda s: if_(s == 0, mark_t.X, mark_t.O))
    wins = g.function(
        "wins",
        [("m", "Mark")],
        "Bool",
        lambda m: any_(
            "line", op("lines", board, 3), lambda line: all_("c", line, lambda c: board[c] == m)
        ),
    )
    full = g.function(
        "full", [], "Bool", lambda: all_("c", op("cells", board), lambda c: ~board[c].is_none())
    )
    move = g.decision("Move", actor=turn)
    move.action(
        "place",
        p("c", "Cell", op("cells", board)),
        requires=board[arg("c")].is_none(),
        effects=[assign(board[arg("c")], mark(turn))],
    )
    move.to("Win", when=wins(mark(turn)))
    move.to("Draw", when=full())
    move.to("Move", effects=[assign(turn, op("next_seat", turn))])
    g.terminal("Win", op("win_loss", turn, 1, -1))
    g.terminal("Draw", op("fill", 0))
    g.start("Move")
    return g.build()


def build_rps() -> dict[str, Any]:
    g = GameBuilder("rock-paper-scissors", "1.0.0", players=2)
    hand_t = g.enum("Hand", ["Rock", "Paper", "Scissors"])
    hand = g.state("hand", T.per_player(T.option("Hand")), const(None))
    beats = g.function(
        "beats", [("a", "Hand"), ("b", "Hand")], "Bool", lambda a, b: (a.ord() - b.ord()) % 3 == 1
    )

    def score_body(s: Any) -> Any:
        return let(
            "mine",
            hand[s].unwrap(),
            lambda mine: let(
                "theirs",
                hand[op("other_seat", s)].unwrap(),
                lambda theirs: case((beats(mine, theirs), 1), (beats(theirs, mine), -1), default=0),
            ),
        )

    score = g.function("score", [("s", "Seat")], "Int", score_body)
    show = g.simultaneous("Show", actors=seats())
    show.action(
        "show",
        p("h", "Hand", hand_t.values()),
        effects=[assign(hand[op("actor")], arg("h"))],
    )
    show.to("End")
    g.terminal("End", map_("s", seats(), lambda s: score(s)))
    g.start("Show")
    return g.build()


def build_nim() -> dict[str, Any]:
    g = GameBuilder("nim", "1.0.0", players=2)
    sizes = g.param("sizes", T.list("Int"), [3, 5, 7])
    misere = g.param("misere", "Bool", False)
    g.constraint(
        op(
            "and",
            sizes.len() > 0,
            all_("h", sizes, lambda h: h >= 0),
            sum_("h", sizes, lambda h: h) > 0,
        )
    )
    heaps = g.state("heaps", T.list("Int"), param("sizes"))
    turn = g.state("turn", "Seat", const(0))
    take = g.decision("Take", actor=turn)
    take.action(
        "take",
        p("heap", "Int", op("range", 0, heaps.len() - 1)),
        p("count", "Int", op("range", 1, heaps[arg("heap")])),
        effects=[assign(heaps[arg("heap")], heaps[arg("heap")] - arg("count"))],
    )
    take.to("End", when=sum_("h", heaps, lambda h: h) == 0)
    take.to("Take", effects=[assign(turn, op("next_seat", turn))])
    g.terminal("End", op("win_loss", if_(misere, op("other_seat", turn), turn), 1, -1))
    g.start("Take")
    return g.build()


@pytest.mark.parametrize(
    ("builder", "name"),
    [
        (build_tictactoe, "tictactoe"),
        (build_rps, "rock-paper-scissors"),
        (build_nim, "nim"),
    ],
)
def test_builder_matches_hand_written_rules(builder: Any, name: str) -> None:
    hand_written = load_json(examples_dir() / f"{name}.ir.json")
    assert rules_hash(builder()) == rules_hash(hand_written)


def test_built_game_is_playable() -> None:
    game = load_game(build_nim())
    s = game.new_state(params={"sizes": [1, 2]})
    assert s.options(0, "take") == [0, 1]
    assert s.options(0, "take", {"heap": 1}) == [1, 2]
    s = s.apply_action(0, Action.of("take", heap=1, count=2))
    s = s.apply_action(1, Action.of("take", heap=0, count=1))
    assert s.is_terminal and s.payoffs == (-1, 1)


def test_python_boolean_operators_are_rejected() -> None:
    with pytest.raises(TypeError, match=r"&, \| y ~"):
        bool(const(1) == 1)


def test_build_validates() -> None:
    g = GameBuilder("broken", players=1)
    g.decision("Move", actor=0).action("go").to("Nowhere")
    g.start("Move")
    with pytest.raises(RuleError, match="nodo desconocido: Nowhere"):
        g.build()
