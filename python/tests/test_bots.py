# SPDX-License-Identifier: Apache-2.0
"""Fase 9: heurísticas (lenguaje, IR, evaluación en los dos motores), determinización, bots,
arena, valoraciones, SPRT, balance, ajuste de pesos, paquetes y sandbox."""

from __future__ import annotations

import json
import textwrap
from fractions import Fraction
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from gamehub.bots.agents import BotSpecError, CoreBot, make_bot, parse_bot_spec
from gamehub.bots.heuristic import NO_PRIORITY, Heuristic
from gamehub.bots.ratings import (
    Glicko,
    Result,
    Skill,
    Sprt,
    elo,
    glicko2,
    trueskill,
    trueskill_rate,
)
from gamehub.engine.core import available, core_game
from gamehub.engine.game import Game
from gamehub.engine.match import RandomAgent, play_match
from gamehub.engine.rng import Pcg32
from gamehub.engine.state import Action
from gamehub.ir import check as check_ir
from gamehub.ir.hashing import heuristic_hash, rules_hash
from gamehub.lang.compiler import compile_text, load_nomos
from gamehub.lang.decompile import decompile_text

GAMES = Path(__file__).resolve().parents[2] / "games"
core = pytest.mark.skipif(not available(), reason="gamehub-core no está instalado")


@cache
def nomos(name: str) -> Game:
    return load_nomos(GAMES / name / f"{name}.game")


def catalog() -> list[str]:
    return sorted(p.stem for p in GAMES.glob("*/*.game") if p.name != "tests.game")


# --- Lenguaje e IR -------------------------------------------------------------------------------

LINES = """
game Lines {
  players 2
  enum Mark { X, O }
  state {
    board: Grid[3, 3] of Mark? = none
    turn: Seat = 0
  }
  fn mark(p: Seat) -> Mark = X if p == 0 else O
  fn wins(m: Mark) -> Bool = any(line in lines(board, 3) : all(c in line : board[c] == m))
  flow {
    start -> Move
    decision Move {
      actor: turn
      action place(c in cells(board)) requires is_none(board[c]) { board[c] = mark(turn) }
      -> Win when wins(mark(turn))
      -> Draw when all(c in cells(board) : not is_none(board[c]))
      -> Move { turn = next(turn) }
    }
    terminal Win { payoff: win_loss(turn, 1, -1) }
    terminal Draw { payoff: fill(0) }
  }
  HEURISTIC
}
"""

HEURISTIC = """
  /// Centro primero
  heuristic Center {
    fn mine(m: Mark) -> Int = count(c in cells(board) : board[c] == m)
    feature marks = mine(mark(me))
    feature theirs = mine(mark(other(me)))
    weights { theirs: -0.5 }
    prefer place(c) when c == (1, 1)
    order place(c) by 1 if c[0] != 1 and c[1] != 1 else 0
  }
"""


def compiled(heuristic: str = HEURISTIC) -> Any:
    return compile_text(LINES.replace("HEURISTIC", heuristic))


def codes(heuristic: str) -> list[str]:
    return [d.code for d in compiled(heuristic).diagnostics.sorted()]


def test_heuristic_reaches_the_ir_outside_the_rules() -> None:
    result = compiled()
    assert result.ok, result.diagnostics
    ir = result.game().ir
    assert check_ir(ir) == []
    [h] = ir["heuristics"]
    assert h["name"] == "Center" and h["doc"] == "Centro primero"
    assert [f["name"] for f in h["functions"]] == ["mine"]
    assert [f["name"] for f in h["features"]] == ["marks", "theirs"]
    assert "weight" not in h["features"][0] and h["features"][1]["weight"] == ["rat", -1, 2]
    assert h["prefer"][0]["params"] == ["c"] and h["order"][0]["action"] == "place"
    # Ni la heurística ni su función cambian las reglas.
    plain = compiled("").game().ir
    assert "mine" not in [f["name"] for f in ir.get("functions", [])]
    assert rules_hash(ir) == rules_hash(plain)
    assert heuristic_hash(ir, "Center").startswith("sha256:")
    assert heuristic_hash(ir, "Center") != heuristic_hash(
        compiled(HEURISTIC.replace("-0.5", "-1")).game().ir, "Center"
    )


def test_heuristic_round_trip_and_format() -> None:
    ir = compiled().game().ir
    text = decompile_text(ir)
    assert "heuristic Center {" in text and "weights { theirs: -0.5 }" in text
    again = compile_text(text)
    assert again.ok and again.game().ir == ir
    from gamehub.lang.printer import format_source
    from gamehub.lang.source import Source

    assert format_source(Source("x", text)) == text


@pytest.mark.parametrize(
    ("heuristic", "code"),
    [
        ("heuristic H { weights { nada: 2 } }", "E201"),
        ("heuristic H { feature f = turn == 0 }", "E301"),
        ("heuristic H { prefer jump(c) when true }", "E201"),
        ("heuristic H { order place(a, b) by 0 }", "E207"),
        ("heuristic H { feature f = 1\n weights { f: turn } }", "E205"),
        ("heuristic H { feature f = 1\n feature f = 2 }", "E202"),
        ("heuristic H { prefer place(c) when actor == 0 }", "E205"),
    ],
)
def test_heuristic_errors(heuristic: str, code: str) -> None:
    assert code in codes(heuristic)


def test_heuristic_functions_are_not_rules() -> None:
    # Una función de la heurística no se ve desde las reglas.
    text = LINES.replace("HEURISTIC", HEURISTIC).replace(
        "-> Draw when all(", "-> Draw when mine(X) == 9 or all("
    )
    result = compile_text(text)
    assert not result.ok and "mine" in str(result.diagnostics.sorted()[0].message)


def test_mods_inherit_override_and_remove_heuristics() -> None:
    base = LINES.replace("HEURISTIC", HEURISTIC)
    text = base + textwrap.dedent(
        """
        game Plus extends Lines {
          heuristic Extra { order place(c) by c[0] }
        }
        game Other extends Lines {
          override heuristic Center { order place(c) by 0 }
        }
        game Bare extends Lines {
          remove heuristic Center
        }
        """
    )
    result = compile_text(text)
    assert result.ok, result.diagnostics
    names = {
        g: [h["name"] for h in result.game(g).ir.get("heuristics", [])]
        for g in ("Plus", "Other", "Bare")
    }
    assert names == {"Plus": ["Center", "Extra"], "Other": ["Center"], "Bare": []}
    assert "features" not in result.game("Other").ir["heuristics"][0]

    # Las reglas son las mismas (salvo el id del juego, que también cuenta para el hash).
    def rules(name: str) -> dict[str, Any]:
        ir = result.game(name).ir
        return {k: v for k, v in ir.items() if k not in ("game", "meta", "heuristics")}

    assert rules("Plus") == rules("Lines") == rules("Bare")


def test_every_catalog_game_has_a_heuristic() -> None:
    for name in catalog():
        ir = nomos(name).ir
        assert ir.get("heuristics"), f"{name} no tiene heurística"


# --- Evaluación (motor de referencia y núcleo) ---------------------------------------------------


def test_reference_evaluation() -> None:
    game = Game(compiled().game().ir)
    h = Heuristic(game)
    s = game.new_state(2)
    s = s.apply_action(0, Action.of("place", c=(0, 0)))
    assert h.feature_values(s, 0) == {"marks": 1, "theirs": 0}
    assert h.evaluate(s, 1) == Fraction(-1, 2)
    legal = s.legal_actions(1)
    assert h.key(s, 1, Action.of("place", c=(1, 1))) == (0, 0)
    assert h.key(s, 1, Action.of("place", c=(2, 2))) == (NO_PRIORITY, -1)
    assert h.ordered(s, 1, legal)[0] == Action.of("place", c=(1, 1))


def _random_states(game: Any, count: int, seed: int) -> list[Any]:
    rng = Pcg32(seed, 5)
    out = []
    s = game.new_state(game.players[0])
    while len(out) < count:
        if s.is_terminal:
            s = game.new_state(game.players[0])
        if s.status.value == "chance":
            s = s.apply_chance(s.sample_chance(rng))
            continue
        out.append(s)
        seat = s.active_seats[0]
        legal = s.legal_actions(seat)
        s = s.apply_action(seat, legal[rng.below(len(legal))])
    return out


@core
@pytest.mark.parametrize(
    "name", ["connect-four", "nim", "kuhn-poker", "parchis", "wizard", "chess", "two-by-two"]
)
def test_core_evaluates_like_the_reference(name: str) -> None:
    game = nomos(name)
    cg = core_game(game)
    for h_ir in game.ir["heuristics"]:
        h = Heuristic(game, h_ir["name"])
        for s in _random_states(game, 12, 3):
            cs = cg.new_state(s.n, None).core
            for st in s.history():
                if st.kind == "chance":
                    cs = cs.apply_chance(list(st.outcome))
                elif st.kind == "action":
                    cs = cs.apply_action(st.seat, cs.decode_action(st.action.to_json()))
            for seat in range(s.n):
                assert Fraction(*cs.heuristic_value(h.name, seat)) == h.evaluate(s, seat)
                if s.is_terminal or seat not in s.active_seats:
                    continue
                for a in s.legal_actions(seat)[:12]:
                    prio, (num, den) = cs.heuristic_key(h.name, seat, cs.decode_action(a.to_json()))
                    assert (prio, -Fraction(num, den)) == h.key(s, seat, a)


# --- Determinización ----------------------------------------------------------------------------


@core
def test_determinization_keeps_what_the_seat_sees() -> None:
    import gamehub_core  # pyright: ignore[reportMissingImports]

    cg = core_game(nomos("kuhn-poker"))
    s = cg.new_state(2)
    s = s.apply_chance(s.sample_chance(Pcg32(1, 1)))
    raw = s.core
    assert gamehub_core.has_hidden(raw, 0)
    hands = set()
    for k in range(40):
        d = gamehub_core.determinize(raw, 0, k)
        assert d.view(0) == raw.view(0)  # lo que ve el asiento 0 no cambia
        hands.add(json.dumps(d.view(None)["state"]["hand"][1]))
    assert len(hands) == 2  # la carta del rival: las dos que no tiene el asiento 0


@core
def test_determinization_resamples_dice() -> None:
    import gamehub_core  # pyright: ignore[reportMissingImports]

    cg = core_game(nomos("dudo"))
    s = cg.new_state(2)
    s = s.apply_chance(s.sample_chance(Pcg32(2, 1)))
    raw = s.core
    mine = raw.view(0)["state"]["cup"][0]
    seen = set()
    for k in range(30):
        d = gamehub_core.determinize(raw, 0, k)
        assert d.view(0)["state"]["cup"][0] == mine
        seen.add(json.dumps(d.view(None)["state"]["cup"][1]))
    assert len(seen) > 5  # dados del rival sorteados de nuevo


@core
def test_determinization_forgets_other_submissions() -> None:
    import gamehub_core  # pyright: ignore[reportMissingImports]

    cg = core_game(nomos("rock-paper-scissors"))
    s = cg.new_state(2)
    s = s.apply_action(1, s.legal_actions(1)[0])
    assert s.active_seats == (0,)
    d = gamehub_core.determinize(s.core, 0, 3)
    assert d.active_seats == (0, 1)  # el envío del rival ya no se ve
    assert not gamehub_core.has_hidden(cg.new_state(2).core, 0)


# --- Bots ----------------------------------------------------------------------------------------


def test_bot_specs() -> None:
    assert parse_bot_spec("alphabeta:depth=3,seconds=0.5,heuristic=none") == {
        "kind": "alphabeta",
        "depth": 3,
        "seconds": 0.5,
        "heuristic": None,
    }
    for bad in ("magic", "mcts:speed=3", "mcts:depth=x", "mcts:depth"):
        with pytest.raises(BotSpecError):
            parse_bot_spec(bad)
    assert isinstance(make_bot(nomos("nim"), "random", 0), RandomAgent)


@core
@pytest.mark.parametrize("kind", ["greedy", "alphabeta", "mcts", "ismcts", "pimc"])
@pytest.mark.parametrize("name", ["tictactoe", "kuhn-poker", "dudo", "mentiroso", "parchis"])
def test_every_bot_plays_legal_moves(kind: str, name: str) -> None:
    import gamehub_core  # pyright: ignore[reportMissingImports]

    game = nomos(name)
    cg = core_game(game)
    n = game.players[0]
    spec = {
        "kind": kind,
        "seconds": 0.005,
        "iterations": 30,
        "depth": 2,
        "samples": 2,
        "max_rollout": 40,
    }
    r = gamehub_core.play_bots(cg.core, n, {}, [spec] + ["random"] * (n - 1), seed=4)
    assert r["error"] is None and not r["truncated"] and r["payoffs"] is not None


@core
def test_bots_beat_random() -> None:
    import gamehub_core  # pyright: ignore[reportMissingImports]

    for name, kind in (("tictactoe", "greedy"), ("connect-four", "alphabeta"), ("nim", "greedy")):
        cg = core_game(nomos(name)).core
        spec = {"kind": kind, "seconds": 0, "depth": 3}
        wins = 0
        for k in range(10):
            seat = k % 2
            specs = ["random", "random"]
            specs[seat] = spec  # type: ignore[call-overload]
            r = gamehub_core.play_bots(cg, 2, {}, specs, seed=k)
            wins += r["ranking"][seat] == 1
        assert wins >= 9, (name, wins)


@core
def test_core_bot_plays_on_the_reference_engine() -> None:
    game = nomos("connect-four")
    agents = [CoreBot(game, "alphabeta:depth=2,seconds=0", 0), RandomAgent(1, 1)]
    r = play_match(game, agents, seed=2)
    assert r.payoffs == (1, -1)
    assert agents[0].stats["depth"] in (1, 2)  # 1 si ya ve una victoria inmediata


@core
def test_solver_with_heuristic_ordering() -> None:
    from gamehub.analysis.cpp import solve_wdl

    game = nomos("connect-four")
    small = {"columns": 5, "rows": 4, "connect": 4}
    plain = solve_wdl(game, params=small, table_bits=20)
    ordered = solve_wdl(game, params=small, table_bits=20, heuristic="Threats")
    assert plain["outcome"] == ordered["outcome"] == 0
    assert ordered["nodes"] * 3 < plain["nodes"]
    # Desde una posición: con tres fichas rojas abajo y la cuarta a punto, gana rojo.
    drops = [{"name": "drop", "args": {"c": c}} for c in (0, 0, 1, 1, 2, 2)]
    assert solve_wdl(game, params=small, moves=drops, heuristic="Threats")["outcome"] == 1


# --- Valoraciones y SPRT -------------------------------------------------------------------------


def test_trueskill_reference_values() -> None:
    a, b = trueskill_rate([Skill(), Skill()], [0, 1])
    assert (round(a.mu, 3), round(a.sigma, 3)) == (29.396, 7.171)
    assert (round(b.mu, 3), round(b.sigma, 3)) == (20.604, 7.171)
    d1, _ = trueskill_rate([Skill(), Skill()], [0, 0])
    assert (round(d1.mu, 3), round(d1.sigma, 3)) == (25.0, 6.458)
    first, second, third = trueskill_rate([Skill(), Skill(), Skill()], [0, 1, 2])
    assert (round(first.mu, 3), round(second.mu, 3), round(third.mu, 3)) == (31.675, 25.0, 18.325)
    assert trueskill([Result(("a", "b"), (0, 1))])["a"].mu > 25


def test_glicko2_reference_example() -> None:
    start = {
        "a": Glicko(1500, 200),
        "b": Glicko(1400, 30),
        "c": Glicko(1550, 100),
        "d": Glicko(1700, 300),
    }
    period = [
        Result(("a", "b"), (0, 1)),
        Result(("a", "c"), (1, 0)),
        Result(("a", "d"), (1, 0)),
    ]
    a = glicko2([period], start=start)["a"]
    assert (round(a.rating, 1), round(a.rd, 1), round(a.volatility, 5)) == (1464.1, 151.5, 0.06)


def test_elo_is_symmetric_and_ordered() -> None:
    results = [Result(("a", "b"), (0, 1))] * 3 + [Result(("a", "b"), (1, 0))]
    ratings = elo(results)
    assert ratings["a"] > 1500 > ratings["b"]
    assert abs(ratings["a"] + ratings["b"] - 3000) < 1e-6
    # Partidas de tres: cuentan como parejas por la clasificación.
    three = elo([Result(("a", "b", "c"), (0, 1, 2))] * 4)
    assert three["a"] > three["b"] > three["c"]


def test_sprt() -> None:
    test = Sprt(0, 20)
    for _ in range(300):
        test.add(1)
        test.add(0.5)
        if test.verdict:
            break
    assert test.verdict == "H1"
    even = Sprt(0, 20)
    for _ in range(2000):
        even.add(1)
        even.add(0)
        if even.verdict:
            break
    assert even.verdict == "H0"


# --- Arena ---------------------------------------------------------------------------------------


@core
def test_round_robin_arena(tmp_path: Path) -> None:
    from gamehub.bots.arena import load_history, run_arena, save_history
    from gamehub.bots.package import load_entrant

    game = nomos("tictactoe")
    entrants = [load_entrant(x) for x in ("random", "greedy", "ab=alphabeta:depth=9,seconds=0")]
    result = run_arena(game, entrants, games=4, jobs=2)
    assert len(result.matches) == 3 * 4 * 2  # tres mesas, cuatro semillas, dos rotaciones
    standings = result.standings()
    assert [s.name for s in standings][-1] == "random"
    assert all(s.matches == 16 for s in standings)
    assert "Elo" in result.table()
    db = tmp_path / "arena.json"
    save_history(db, result)
    assert len(load_history(db, game.rules_hash)) == 24
    assert load_history(db, "sha256:otro") == []


@core
def test_gauntlet_and_swiss_with_more_players() -> None:
    from gamehub.bots.arena import run_arena
    from gamehub.bots.package import load_entrant

    game = nomos("parchis")
    entrants = [load_entrant(x) for x in ("greedy", "random", "first")]
    gauntlet = run_arena(
        game, entrants, num_players=4, tournament="gauntlet", games=2, mirror=False
    )
    assert all("greedy" in m.players for m in gauntlet.matches)
    swiss = run_arena(game, entrants, num_players=3, tournament="swiss", games=1, rounds=2)
    assert len(swiss.matches) == 2 * 3


@core
def test_sandboxed_python_bot(tmp_path: Path) -> None:
    from gamehub.bots.arena import run_arena
    from gamehub.bots.package import load_bot_package, load_entrant

    (tmp_path / "good").mkdir()
    (tmp_path / "good" / "agent.py").write_text(
        "def act(observation, legal):\n    return legal[-1]\n", encoding="utf-8"
    )
    (tmp_path / "good" / "bot.toml").write_text(
        '[bot]\nname = "last"\nversion = "1.0.0"\ngame = "nim"\nkind = "python"\n',
        encoding="utf-8",
    )
    (tmp_path / "slow.py").write_text(
        "import time\ndef act(observation, legal):\n    time.sleep(5)\n    return legal[0]\n",
        encoding="utf-8",
    )
    good = load_bot_package(tmp_path / "good")
    assert good.name == "last@1.0.0" and good.python is not None
    slow = load_entrant(str(tmp_path / "slow.py"))
    slow.limits.seconds_per_move = 0.5
    result = run_arena(nomos("nim"), [good, slow, load_entrant("random")], games=1, jobs=3)
    assert all(m.ok for m in result.matches)
    failures = [f for m in result.matches for f in m.failures]
    assert failures and all("a tiempo" in f for f in failures)
    other = load_bot_package(tmp_path / "good")
    other.game = "chess"
    with pytest.raises(ValueError, match="bot de chess"):
        run_arena(nomos("nim"), [other, load_entrant("random")], games=1)


# --- Balance y ajuste ----------------------------------------------------------------------------


@core
def test_balance_report_and_ci() -> None:
    from gamehub.bots.balance import BalanceOptions, balance, compare

    game = nomos("tictactoe")
    options = BalanceOptions(
        games=20, ladder=("random", "greedy"), ladder_games=10, kingmaking_games=0, jobs=2
    )
    report = balance(game, options)
    assert report.players == 2 and len(report.seats) == 2
    assert report.skill["skill_share"] > 0.5
    assert report.chain_depth == 1
    assert report.tension["heuristic"] == "Lines"
    # El autojuego de greedy siempre empata; las partidas contra random cubren la victoria.
    assert report.uncovered["transiciones"] == []
    assert report.draw_rate == 1.0
    md = report.markdown()
    assert "## Ventaja por asiento" in md and "## Cadena de habilidad" in md
    assert compare(report, report).regressions == []


@core
def test_kingmaking_probe() -> None:
    import gamehub_core  # pyright: ignore[reportMissingImports]

    cg = core_game(nomos("mentiroso")).core
    r = gamehub_core.kingmaking(cg, 3, {}, ["greedy"] * 3, seed=1, rollouts=4)
    assert r["error"] is None and r["probes"] > 0 and 0 <= r["events"] <= r["probes"]


def test_cmaes_minimizes_a_quadratic() -> None:
    from gamehub.bots.tuning import Cmaes

    es = Cmaes([3.0, -2.0, 1.0], 1.0, seed=1)
    for _ in range(60):
        xs = es.ask()
        es.tell(xs, [(x[0] - 1) ** 2 + 2 * (x[1] + 0.5) ** 2 + (x[2] - 2) ** 2 for x in xs])
    assert all(abs(a - b) < 0.05 for a, b in zip(es.mean, [1, -0.5, 2], strict=True))


@core
def test_texel_and_write_weights(tmp_path: Path) -> None:
    from gamehub.bots.tuning import initial_weights, texel_positions, tune_texel, write_weights

    game = nomos("tictactoe")
    features, start = initial_weights(game.ir, "Lines")
    assert features == ["mine", "theirs"] and start == [1.0, -1.0]
    positions = texel_positions(game.ir, "Lines", "random", 30, 2, {}, jobs=2)
    assert positions and all(len(x) == 2 for x, _ in positions)
    weights, loss = tune_texel(positions, start, epochs=50)
    assert 0 < loss < 0.25 and weights[0] > 0 > weights[1]
    path = tmp_path / "tictactoe.game"
    path.write_text((GAMES / "tictactoe" / "tictactoe.game").read_text(encoding="utf-8"))
    write_weights(path, "Lines", {"mine": 0.75, "theirs": -1.25})
    ir = load_nomos(path).ir
    [h] = ir["heuristics"]
    assert [f.get("weight") for f in h["features"]] == [["rat", 3, 4], ["rat", -5, 4]]
    assert rules_hash(ir) == game.rules_hash
