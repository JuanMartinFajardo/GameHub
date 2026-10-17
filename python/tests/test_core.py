# SPDX-License-Identifier: Apache-2.0
"""El motor C++ (`gamehub-core`) contra el de referencia: primitivas, operadores, trazas doradas y
partidas aleatorias paso a paso (ADR-075 a 078)."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any, cast

import pytest

from gamehub.engine.conformance import conformance_dir
from gamehub.engine.core import CoreGame, available, core_game
from gamehub.engine.differential import compare_match, diff
from gamehub.engine.errors import IllegalAction, InvalidParams, RuleError
from gamehub.engine.game import Game, load_game
from gamehub.engine.replay import replay
from gamehub.engine.rng import Pcg32
from gamehub.engine.values import to_json
from gamehub.ir.hashing import canonical_json
from gamehub.ir.spec import examples_dir
from gamehub.lang.compiler import load_nomos

pytestmark = pytest.mark.skipif(not available(), reason="gamehub-core no está instalado")

GAMES = Path(__file__).resolve().parents[2] / "games"


def catalog() -> list[str]:
    return sorted(p.stem for p in GAMES.glob("*/*.game") if p.name != "tests.game")


@cache
def nomos(name: str) -> Game:
    return load_nomos(GAMES / name / f"{name}.game")


def test_primitives_match_python() -> None:
    import gamehub_core as C  # pyright: ignore[reportMissingImports]

    rng = Pcg32(42, 54)
    assert C.pcg32(42, 54, 8) == [rng.next_u32() for _ in range(8)]
    value = {"b": [1, 'é\n\u0001"\\', None, True], "a": {"z": -5, "é": "x", "": []}}
    assert C.canonical_json(value) == canonical_json(value)
    assert C.sha256("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


@pytest.mark.parametrize("name", catalog())
def test_rules_hash_matches(name: str) -> None:
    game = nomos(name)
    assert core_game(game).rules_hash == game.rules_hash


@pytest.mark.parametrize(
    "path",
    sorted(conformance_dir().glob("*/*.ghr.json")),
    ids=lambda p: f"{p.parent.name}/{p.name}",
)
def test_golden_traces(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    game = CoreGame(load_game(examples_dir() / f"{path.parent.name}.ir.json").ir)
    final = replay(cast(Game, game), data)  # los drivers aceptan cualquiera de los dos motores
    assert final.digest() == data["digests"][-1]


# --- Operadores --------------------------------------------------------------------------------

#: Un juego con estado de todos los tipos para evaluar expresiones sobre él.
PROBE: dict[str, Any] = {
    "ir_version": "0.1.0",
    "game": {"id": "probe", "version": "0.1.0"},
    "players": {"min": 2, "max": 4},
    "params": [{"name": "k", "type": "Int", "default": ["const", 3]}],
    "types": [
        {"kind": "enum", "name": "Rank", "values": ["Low", "Mid", "High"]},
        {"kind": "enum", "name": "Suit", "values": ["Clubs", "Hearts"]},
        {
            "kind": "struct",
            "name": "Card",
            "fields": [{"name": "suit", "type": "Suit"}, {"name": "rank", "type": "Rank"}],
        },
    ],
    "state": [
        {"name": "g", "type": ["grid", 3, 3, ["option", "Rank"]], "init": ["const", None]},
        {
            "name": "xs",
            "type": ["list", "Int"],
            "init": ["list", *(["const", x] for x in (3, 1, 2))],
        },
        {
            "name": "deck",
            "type": ["zone", "Card"],
            "init": [
                "flat_map",
                "s",
                ["enum_values", "Suit"],
                [
                    "map",
                    "r",
                    ["enum_values", "Rank"],
                    ["struct", "Card", {"suit": ["local", "s"], "rank": ["local", "r"]}],
                ],
            ],
        },
        {
            "name": "pile",
            "type": ["bag", "Int"],
            "init": ["list", *(["const", x] for x in (3, 1, 3))],
        },
        {"name": "m", "type": ["map", "Text", "Int"], "init": ["list"]},
        {"name": "q", "type": ["set", "Int"], "init": ["list", ["const", 2], ["const", 1]]},
        {"name": "t", "type": "Text", "init": ["const", "añoño"]},
    ],
    "flow": {
        "start": "End",
        "nodes": [{"id": "End", "kind": "terminal", "payoff": ["fill", ["const", 0]]}],
    },
}


def c(v: Any) -> list[Any]:
    return ["const", v]


def lst(*xs: Any) -> list[Any]:
    return ["list", *(c(x) for x in xs)]


def var(name: str) -> list[Any]:
    return ["var", name]


X = ["local", "x"]
LOW, HIGH = ["enum", "Rank", "Low"], ["enum", "Rank", "High"]
CARD = ["struct", "Card", {"suit": ["enum", "Suit", "Hearts"], "rank": LOW}]

# fmt: off
EXPRESSIONS: list[list[Any]] = [
    # literales y referencias
    c(None), c(True), c(-7), c("txt"), ["rat", 6, 4], ["rat", 2, 1], LOW, ["param", "k"],
    ["param", "num_players"], ["seats"], ["at", "End"], var("deck"), var("pile"), var("g"),
    # aritmética exacta
    ["add", c(1), c(2), c(3)], ["add"], ["add", ["rat", 1, 3], ["rat", 2, 3]], ["sub", c(1), c(5)],
    ["mul", c(3), ["rat", 1, 6]], ["div", c(1), c(3)], ["div", c(1), c(0)], ["idiv", c(-7), c(2)],
    ["idiv", ["rat", 7, 2], c(1)], ["mod", c(-7), c(3)], ["mod", c(7), c(-3)],
    ["mod", ["rat", 7, 2], c(2)], ["mod", c(1), c(0)], ["neg", ["rat", 1, 2]], ["abs", c(-4)],
    ["min", c(3), ["rat", 1, 2], c(2)], ["max", c(3), c(9)], ["add", c(1), c("x")],
    ["add", c(True), c(1)], ["mul", c(2), c(None)],
    # comparación y lógica
    ["eq", lst(1, 2), ["cell", c(1), c(2)]], ["eq", c(True), c(1)], ["ne", CARD, CARD],
    ["lt", LOW, HIGH], ["lt", c("a"), c("b")], ["lt", c(1), c("b")], ["ge", ["rat", 1, 2], c(0)],
    ["lt", LOW, ["enum", "Suit", "Clubs"]], ["and"], ["or"], ["and", c(True), c(1)],
    ["or", c(True), ["unwrap", c(None)]], ["and", c(False), ["unwrap", c(None)]], ["not", c(1)],
    ["if", c(True), c(1), ["unwrap", c(None)]], ["if", c(3), c(1), c(2)],
    ["case", [[c(False), c(1)], [c(True), c(2)]], c(3)], ["case", [[c(5), c(1)]], c(3)],
    ["let", "y", c(5), ["add", ["local", "y"], c(1)]],
    ["let", "x", c(1), ["let", "x", c(2), ["local", "x"]]],
    # opcionales y colecciones
    ["is_none", c(None)], ["unwrap", c(None)], ["len", var("t")], ["len", var("deck")],
    ["len", var("m")], ["len", c(3)], ["contains", var("t"), c("ño")],
    ["contains", lst(1, 2), c(2)],
    ["contains", var("pile"), c(3)], ["contains", c(3), c(1)], ["index", lst(1, 2), c(2)],
    ["index", lst(1, 2), c(True)], ["index", var("g"), ["cell", c(2), c(2)]],
    ["index", var("g"), ["cell", c(3), c(0)]], ["index", var("m"), c("x")], ["index", c(1), c(0)],
    ["index", ["cell", c(4), c(5)], c(1)], ["field", CARD, "rank"], ["field", c(1), "rank"],
    ["first", lst()], ["last", lst(1, 2)], ["first", var("q")], ["only", lst(9)],
    ["only", lst(1, 2)], ["append", lst(1), c(2)], ["concat", lst(1), lst(2, 3)],
    ["concat", lst(1), var("q")], ["range", c(2), c(4)], ["range", c(3), c(2)],
    ["range", ["rat", 1, 2], c(3)], ["slice", lst(1, 2, 3, 4), c(-2), c(2)],
    ["slice", lst(1, 2, 3), c(2), c(9)], ["reverse", lst(1, 2)], ["distinct", lst(2, 1, 2)],
    ["union", lst(3, 1), lst(2, 1)], ["union", var("pile"), var("q")],
    ["intersection", lst(3, 1, 2), lst(1, 3)], ["difference", lst(3, 1, 2, 1), lst(1)],
    ["difference", lst(), c(1)], ["subsets", lst(2, 1, 1), c(1), c(2)],
    ["subsets", var("pile"), c(0), c(9)], ["subsets", lst(), c(1), c(2)],
    # comprensiones
    ["map", "x", var("xs"), ["mul", X, c(2)]], ["filter", "x", var("xs"), ["gt", X, c(1)]],
    ["count", "x", var("xs"), ["gt", X, c(1)]], ["sum", "x", lst(), X],
    ["sum", "x", lst(1, 2), ["rat", 1, 2]], ["argmax", "x", lst(1, 3, 3), X],
    ["argmin", "x", lst("b", "a"), X], ["argmax", "x", lst(), X], ["max_of", "x", lst(), X],
    ["max_of", "x", var("xs"), ["neg", X]], ["min_of", "x", var("pile"), X],
    ["sort_by", "x", lst(3, 1, 2), ["neg", X]], ["sort_by", "x", var("deck"), ["field", X, "rank"]],
    ["flat_map", "x", lst(1, 2), ["list", X, X]], ["all", "x", var("xs"), ["gt", X, c(0)]],
    ["any", "x", var("xs"), ["gt", X, c(2)]], ["all", "x", lst(1, "a"), ["gt", X, c(1)]],
    ["all", "x", c(3), c(True)], ["count", "x", var("m"), c(True)],
    ["map", "x", var("q"), ["map", "y", var("xs"), ["add", X, ["local", "y"]]]],
    # asientos, tableros, zonas, enumerados
    ["next_seat", c(1)], ["prev_seat", c(0)], ["seats_from", c(1)], ["other_seat", c(0)],
    ["next_seat", c(7)], ["cells", var("g")], ["lines", var("g"), c(3)], ["lines", var("g"), c(0)],
    ["neighbors", var("g"), ["cell", c(0), c(0)]], ["in_bounds", var("g"), ["cell", c(2), c(3)]],
    ["cells", c(1)], ["size", var("deck")], ["items", var("pile")], ["top", var("deck")],
    ["top", var("pile")], ["size", c(1)], ["enum_values", "Rank"], ["ord", HIGH], ["ord", c(1)],
    # pagos
    ["win_loss", c(1), c(1), c(-1)], ["win_loss", c(5), c(1), c(-1)],
    ["fill", ["div", c(1), c(2)]], ["fill", c("x")],
    # desbordamientos que Python no tiene: los dos dan un resultado o los dos un error
    ["mul", c(2**40), c(2**20)],
]
# fmt: on


@pytest.mark.parametrize("n", [2, 3])
def test_every_operator_matches(n: int) -> None:
    reference = Game(PROBE).new_state(n)
    native = CoreGame(PROBE).new_state(n).core
    for e in EXPRESSIONS:
        try:
            expected: Any = to_json(reference.evaluate(e))
        except (RuleError, TypeError):
            # Un `range` con racionales rompe Python con TypeError; en C++ es un RuleError.
            expected = RuleError
        try:
            got: Any = native.evaluate(e)
        except RuleError:
            got = RuleError
        assert got == expected, e


def test_integers_are_64_bits() -> None:
    state = CoreGame(PROBE).new_state(2).core
    with pytest.raises(RuleError, match="64 bits"):
        state.evaluate(["mul", c(2**40), c(2**40)])


# --- Partidas ----------------------------------------------------------------------------------

#: Partidas por juego en la suite normal (las largas, menos); `gamehub diff` hace millones.
MATCHES = {"chess": 2, "skat": 2, "wizard": 2, "mentiroso": 3, "solitaire": 2}


@pytest.mark.parametrize("name", catalog())
def test_random_matches_step_by_step(name: str) -> None:
    game = nomos(name)
    report = diff(game, MATCHES.get(name, 12), deep_every=4, max_steps=400)
    assert report.differences == []
    assert report.games == MATCHES.get(name, 12)


def test_more_players_and_parameters() -> None:
    cases = [("dudo", 4, None), ("texas-holdem", 6, None), ("wizard", 6, None), ("skat", 4, None)]
    for name, n, params in cases:
        game = nomos(name)
        core = core_game(game)
        for seed in range(2):
            steps, problem, _, _ = compare_match(
                game, core, seed, num_players=n, params=params, max_steps=300, deep=seed == 0
            )
            assert problem is None, (name, n, seed, steps, problem)


def test_errors_and_invalid_input_match() -> None:
    game = nomos("connect-four")
    core = core_game(game)
    with pytest.raises(InvalidParams):
        core.new_state(3)
    with pytest.raises(InvalidParams):
        core.new_state(2, {"nope": 1})
    state = core.new_state(2)
    with pytest.raises(IllegalAction):
        state.decode_action(0, {"name": "fly"})
    reference = game.new_state(2)
    wrong = reference.decode_action(0, {"name": "drop", "args": {"c": 99}})
    assert state.illegal_reason(0, wrong) == reference.illegal_reason(0, wrong)
    with pytest.raises(IllegalAction):
        state.apply_action(1, reference.legal_actions(0)[0])
    assert state.options(0) == reference.options(0)
    assert state.options(0, "drop") == reference.options(0, "drop")


# --- Algoritmos en C++ -------------------------------------------------------------------------


def test_perft_matches_python_and_chess_reference_values() -> None:
    from gamehub.analysis import cpp
    from gamehub.analysis.perft import perft as py_perft

    for name, depth in (("tictactoe", 4), ("connect-four", 4), ("nim", 3), ("kuhn-poker", 3)):
        g = nomos(name)
        assert cpp.perft(g, depth) == py_perft(g.new_state(g.players[0]), depth)
    chess = nomos("chess")
    assert cpp.perft(chess, 3, ["claim_draw"]) == 8_902
    assert cpp.perft(chess, 4, ["claim_draw"]) == 197_281


@pytest.mark.slow
def test_chess_perft_5() -> None:
    from gamehub.analysis import cpp

    assert cpp.perft(nomos("chess"), 5, ["claim_draw"]) == 4_865_609


def test_alphabeta_and_retrograde() -> None:
    from gamehub.analysis import cpp
    from gamehub.analysis.search import alphabeta as py_alphabeta

    ttt = nomos("tictactoe")
    solution = cpp.alphabeta(ttt)
    assert solution.value == (0, 0)
    assert solution.best == py_alphabeta(ttt).best
    assert len(solution.pv) == 9
    retro = cpp.retrograde(ttt)
    assert retro["outcome"] == 0 and retro["positions"] == 5_478
    nim = cpp.retrograde(nomos("nim"))
    assert nim["outcome"] == 1 and nim["positions"] == 376
    small = {"columns": 4, "rows": 4, "connect": 3}
    c4 = nomos("connect-four")
    assert cpp.alphabeta(c4, params=small).value == (1, -1)
    assert cpp.retrograde(c4, params=small)["outcome"] == 1


def test_cfr_reproduces_the_python_tree_and_policy() -> None:
    from gamehub.analysis import cpp
    from gamehub.analysis.cfr import solve_cfr
    from gamehub.analysis.tree import build_tree

    kuhn = nomos("kuhn-poker")
    native = cpp.cfr(kuhn, 300)
    tree = build_tree(kuhn)
    policy, _ = solve_cfr(tree, 300)
    assert [key for _, key, _ in native["infosets"]] == [s.key for s in tree.infosets]
    for i in range(len(tree.infosets)):
        assert native["policy"][i] == pytest.approx(policy[i], abs=1e-12)
    assert native["exploitability"] < 1e-3


def test_mcts_prefers_the_center_in_connect_four() -> None:
    from gamehub.analysis import cpp

    g = nomos("connect-four")
    result = cpp.mcts(core_game(g).new_state(2), 3000, seed=1)
    assert result["actions"][result["best"]].args == (("c", 3),)
    assert sum(result["visits"]) == 3000
