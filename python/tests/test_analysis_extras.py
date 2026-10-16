# SPDX-License-Identifier: Apache-2.0
"""Teoría de juegos (F7): juegos cooperativos, torneos de Axelrod, exportación a Gambit, el
envoltorio para OpenSpiel, los widgets y `gamehub analyze` / `gamehub export`."""

from __future__ import annotations

import functools
import json
import re
from fractions import Fraction
from pathlib import Path

import pytest

from gamehub.analysis import coop, repeated
from gamehub.analysis.export import to_efg, to_nfg
from gamehub.analysis.normal_form import NormalForm, normal_form
from gamehub.analysis.report import analyze, report_lines
from gamehub.analysis.tree import build_tree
from gamehub.cli import main
from gamehub.engine.game import Game
from gamehub.lang.compiler import load_nomos

ROOT = Path(__file__).resolve().parents[2]
GAMES = ROOT / "games"
F = Fraction


@functools.cache
def game(name: str) -> Game:
    return load_nomos(GAMES / name / f"{name}.game")


# --- Juegos cooperativos -------------------------------------------------------------------------


def glove_game() -> coop.Coalitional:
    """El jugador 0 tiene un guante izquierdo; el 1 y el 2, uno derecho cada uno."""
    return coop.Coalitional.from_function(3, lambda c: 1 if 0 in c and c & {1, 2} else 0)


def test_glove_game() -> None:
    cf = glove_game()
    assert coop.shapley(cf) == (F(2, 3), F(1, 6), F(1, 6))
    assert coop.core(cf) == (1, 0, 0)
    assert coop.nucleolus(cf) == (1, 0, 0)
    assert coop.in_core(cf, (1, 0, 0)) and not coop.in_core(cf, (F(2, 3), F(1, 6), F(1, 6)))
    assert cf.is_superadditive()


def test_majority_game_has_an_empty_core() -> None:
    cf = coop.Coalitional.from_function(3, lambda c: 1 if len(c) >= 2 else 0)
    assert coop.core(cf) is None
    eps, _ = coop.least_core(cf)
    assert eps == F(1, 3)
    assert coop.nucleolus(cf) == (F(1, 3),) * 3
    assert coop.shapley(cf) == (F(1, 3),) * 3
    assert coop.banzhaf(cf, normalized=True) == (F(1, 3),) * 3


@pytest.mark.parametrize(
    ("estate", "expected"),
    [(100, (F(100, 3),) * 3), (200, (50, 75, 75)), (300, (50, 100, 150))],
)
def test_nucleolus_of_the_talmud_bankruptcy_problems(estate: int, expected: tuple) -> None:
    """Aumann y Maschler (1985): el reparto del Talmud de una herencia `estate` entre deudas de
    100, 200 y 300 es el nucléolo del juego v(S) = máx(0, E − deudas de los demás)."""
    claims = (100, 200, 300)
    cf = coop.Coalitional.from_function(
        3, lambda c: max(0, estate - sum(claims[i] for i in range(3) if i not in c))
    )
    assert coop.nucleolus(cf) == tuple(F(x) for x in expected)


def test_characteristic_function_from_a_normal_form() -> None:
    cf = coop.characteristic_function(normal_form(game("prisoners-dilemma")))
    assert cf.v([0]) == 1 and cf.v([1]) == 1 and cf.grand == 6
    assert coop.shapley(cf) == (3, 3)


def test_nash_bargaining() -> None:
    bos = normal_form(game("battle-of-the-sexes"))
    result = coop.nash_bargaining(bos)
    assert result is not None
    assert result.disagreement == (F(6, 5), F(6, 5))
    assert result.payoffs == (F(5, 2), F(5, 2))
    pd = coop.nash_bargaining(normal_form(game("prisoners-dilemma")))
    assert pd is not None and pd.payoffs == (3, 3)


# --- Torneos -------------------------------------------------------------------------------------


@functools.cache
def stage() -> NormalForm:
    return normal_form(game("prisoners-dilemma"))


def test_repeated_matches() -> None:
    tft, alld, grim, alt = repeated.classic("TFT", "ALLD", "GRIM", "ALT")
    assert repeated.play(stage(), tft, alld, 200)[:2] == (199, 204)
    assert repeated.play(stage(), tft, tft, 200)[:2] == (600, 600)
    # GRIM coopera hasta la primera traición de ALT (ronda 2) y luego siempre traiciona.
    a, b, ca, cb = repeated.play(stage(), grim, alt, 4)
    assert (ca, cb) == (2, 2) and (a, b) == (3 + 0 + 5 + 1, 3 + 5 + 0 + 1)
    with pytest.raises(KeyError):
        repeated.classic("NOPE")


def test_tournament() -> None:
    result = repeated.tournament(
        stage(), repeated.classic("ALLC", "ALLD", "TFT", "GRIM"), rounds=100
    )
    scores = dict(result.ranking())
    assert scores["ALLD"] < scores["TFT"] and scores["TFT"] == scores["GRIM"]
    assert result.scores[0][1] == 0 and result.scores[1][0] == 5
    assert result.cooperation[2][2] == 1
    history = repeated.ecological(result, generations=200)
    assert all(abs(sum(row) - 1) < 1e-9 for row in history)
    assert history[-1][1] < 0.01  # ALLD se extingue
    noisy = repeated.tournament(stage(), rounds=50, noise=0.05, seed=3)
    assert noisy.scores == repeated.tournament(stage(), rounds=50, noise=0.05, seed=3).scores
    assert "<table" in result._repr_html_()


# --- Gambit --------------------------------------------------------------------------------------


def test_efg_of_kuhn() -> None:
    text = to_efg(build_tree(game("kuhn-poker")))
    lines = text.splitlines()
    assert lines[0] == 'EFG 2 R "Poker de Kuhn" { "Player 1" "Player 2" }'
    kinds = [line[0] for line in lines[3:]]
    assert (kinds.count("c"), kinds.count("p"), kinds.count("t")) == (1, 24, 30)
    assert lines[3].count("1/6") == 6
    infosets = {tuple(line.split()[2:4]) for line in lines if line.startswith("p ")}
    assert infosets == {(p, str(i)) for p in ("1", "2") for i in range(1, 7)}
    assert text.isascii()


def test_nfg() -> None:
    text = to_nfg(stage())
    assert text.splitlines()[0] == (
        'NFG 1 R "Dilema del prisionero" { "Player 1" "Player 2" } '
        '{ { "Cooperate" "Defect" } { "Cooperate" "Defect" } }'
    )
    # Perfiles con la estrategia del primer jugador variando más deprisa.
    assert text.splitlines()[-1] == "3 3 5 0 0 5 1 1"
    three = NormalForm.from_function([["a", "b"]] * 3, lambda p: [p[0], p[1], p[2]])
    assert to_nfg(three).splitlines()[-1].split()[:6] == ["0", "0", "0", "1", "0", "0"]


# --- OpenSpiel -----------------------------------------------------------------------------------


def test_openspiel_wrapper() -> None:
    pyspiel = pytest.importorskip("pyspiel")
    from open_spiel.python import policy as os_policy
    from open_spiel.python.algorithms import cfr, exploitability

    from gamehub.analysis.openspiel import to_openspiel

    wrapped = to_openspiel(game("kuhn-poker"))
    assert wrapped.num_distinct_actions() == 4 and wrapped.max_chance_outcomes() == 6
    assert pyspiel.load_game(wrapped.get_type().short_name).num_players() == 2
    pyspiel.random_sim_test(wrapped, num_sims=10, serialize=False, verbose=False)
    uniform = exploitability.exploitability(wrapped, os_policy.UniformRandomPolicy(wrapped))
    builtin = pyspiel.load_game("kuhn_poker")
    assert uniform == pytest.approx(
        exploitability.exploitability(builtin, os_policy.UniformRandomPolicy(builtin))
    )
    solver = cfr.CFRPlusSolver(wrapped)
    for _ in range(60):
        solver.evaluate_and_update_policy()
    assert exploitability.exploitability(wrapped, solver.average_policy()) < 0.02
    ttt = to_openspiel(game("tictactoe"))
    assert ttt.get_type().information == pyspiel.GameType.Information.PERFECT_INFORMATION
    assert ttt.num_distinct_actions() == 9 and ttt.max_game_length() == 9


# --- Widgets -------------------------------------------------------------------------------------


def test_widgets() -> None:
    from gamehub.analysis.widgets import convergence_svg, grundy_table_html

    html = stage()._repr_html_()
    assert html.count("<u>") == 4  # cada pago de (D, D) y las respuestas a C
    assert "outline" in html  # el equilibrio resaltado
    assert "<details" in build_tree(game("kuhn-poker"))._repr_html_()
    assert convergence_svg([(10, 0.5), (100, 0.05), (1000, 0.001)]).startswith("<svg")
    assert "Grundy" in grundy_table_html([(1, 1), (2, 2)])


# --- Informe y CLI -------------------------------------------------------------------------------


def test_report_auto() -> None:
    report = analyze(game("prisoners-dilemma"))
    assert {"feasibility", "normal_form", "nash", "pareto"} <= set(report)
    assert report["nash"]["pure"] == [[1, 1]]
    assert report["pareto"]["price_of_anarchy"] == "3"
    assert not report["errors"]
    json.dumps(report)  # todo serializable


def test_report_errors_do_not_break_it() -> None:
    report = analyze(game("prisoners-dilemma"), ["solve", "nash", "nope"])
    assert "solve" in report["errors"] and "nope" in report["errors"]
    assert "nash" in report
    assert any(line.startswith("✗ solve") for line in "\n".join(report_lines(report)).splitlines())


def test_cli_analyze(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["analyze", str(GAMES / "tictactoe"), "--solve", "--count"]) == 0
    out = capsys.readouterr().out
    assert "5,478 posiciones" in out and "255,168 partidas" in out and "valor: (0, 0)" in out
    assert main(["analyze", str(GAMES / "kuhn-poker"), "--sequence-form", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["sequence_form"]["value"] == "-1/18"
    assert main(["analyze", str(GAMES / "nim"), "--grundy", "--param", "sizes=[1,2,3]"]) == 0
    assert "posición P" in capsys.readouterr().out
    assert main(["analyze", str(GAMES / "nim"), "--grundy", "--param", "misere=true"]) == 1


def test_cli_export(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "kuhn.efg"
    assert main(["export", str(GAMES / "kuhn-poker"), "--to", "gambit-efg", "-o", str(out)]) == 0
    assert out.read_text().startswith("EFG 2 R")
    assert main(["export", str(GAMES / "prisoners-dilemma"), "--to", "gambit-nfg"]) == 0
    assert re.search(r"^3 3 5 0 0 5 1 1$", capsys.readouterr().out, re.M)
