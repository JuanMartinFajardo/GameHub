# SPDX-License-Identifier: Apache-2.0
"""`gamehub test`: ejecución de los bloques `test` e `invariant` de Nomos."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gamehub.cli import main
from gamehub.lang.compiler import compile_file, compile_text
from gamehub.lang.diagnostics import Diagnostic
from gamehub.lang.testing import GameTester, TestResult

ROOT = Path(__file__).resolve().parents[2]
GAMES = sorted((ROOT / "games").glob("*/*.game"))
KUHN = ROOT / "games" / "kuhn-poker" / "kuhn-poker.game"
DILEMMA = ROOT / "games" / "prisoners-dilemma" / "prisoners-dilemma.game"


def with_tests(path: Path, tests: str, invariant: str | None = None) -> GameTester:
    """El juego de `path` con sus tests sustituidos por `tests` (y, si se indica, su invariante
    por `invariant`)."""
    text = path.read_text(encoding="utf-8")
    start = text.find('  test "')
    end = text.rindex("}")
    body = text[:start] if start >= 0 else text[:end]
    rest = text[start:end] if start >= 0 else ""
    kept = [line for line in rest.splitlines() if line.startswith("  invariant")]
    if invariant is not None:
        kept = [f"  invariant {invariant}"]
    result = compile_text(body + tests + "\n" + "\n".join(kept) + "\n}\n", path.name)
    assert result.ok, [str(d) for d in result.diagnostics]
    return GameTester(result.game())


def only(tester: GameTester) -> TestResult:
    [result] = tester.run_all().tests
    return result


def failure(tester: GameTester) -> Diagnostic:
    result = only(tester)
    assert result.failure is not None, "el test debía fallar"
    return result.failure


@pytest.mark.parametrize("path", GAMES, ids=lambda p: p.stem)
def test_games_pass_their_own_tests(path: Path) -> None:
    result = compile_file(path)
    assert result.ok
    for compiled in result.games.values():
        report = GameTester(compiled).run_all(playouts=2)
        assert [str(t.failure) for t in report.tests if t.failure] == []
        assert report.playouts.failure is None
        assert report.tests, "cada juego trae sus tests"


def test_failed_expectation_shows_the_values() -> None:
    tester = with_tests(
        KUHN,
        """  test "t" {
    chance where only(hand[0]) == K and only(hand[1]) == J
    play check(), bet(), call()
    expect at(Showdown) and payoff == [1, -1]
  }""",
    )
    d = failure(tester)
    assert d.code == "E610"
    assert d.labels[0].message == "`payoff == [1, -1]` es falso: `payoff` vale [2, -2]"
    assert d.notes == ["la partida terminó en Showdown con pagos [2, -2]"]


def test_illegal_play_lists_the_legal_actions() -> None:
    d = failure(with_tests(KUHN, '  test "t" {\n    play check(), call()\n  }'))
    assert d.code == "E611"
    assert d.message == "jugada ilegal del asiento 1: call()"
    assert d.notes == ["jugadas legales del asiento 1: check(), bet()"]


def test_payoff_only_exists_at_the_end() -> None:
    d = failure(with_tests(KUHN, '  test "t" {\n    expect payoff == [0, 0]\n  }'))
    assert d.code == "E610" and "payoff" in d.message


def test_legal_and_illegal_expectations() -> None:
    tester = with_tests(
        KUHN,
        """  test "bien" {
    expect legal check()
    expect illegal call()
    expect illegal fold()
  }
  test "mal" {
    expect illegal check()
  }""",
    )
    good, bad = tester.run_all().tests
    assert good.ok
    assert bad.failure is not None and bad.failure.code == "E610"
    assert "fuera ilegal" in bad.failure.message


def test_chance_where_conditions_on_the_outcome() -> None:
    tests = "\n".join(
        f'  test "semilla {seed}" {{\n    seed {seed}\n    chance where only(hand[0]) == K\n'
        f"    expect only(hand[1]) == J\n  }}"
        for seed in range(20)
    )
    report = with_tests(KUHN, tests).run_all()
    passed = sum(t.ok for t in report.tests)
    assert 0 < passed < 20  # la mano del asiento 1 es J o Q según la semilla
    for t in report.tests:
        assert t.ok or (t.failure is not None and t.failure.code == "E610")


def test_chance_errors() -> None:
    impossible = with_tests(KUHN, '  test "t" {\n    chance where hand[0] == hand[1]\n  }')
    assert failure(impossible).code == "E612"
    not_pending = with_tests(KUHN, '  test "t" {\n    play check()\n    chance where true\n  }')
    d = failure(not_pending)
    assert d.code == "E612" and d.message == "no hay azar pendiente"


def test_explicit_chance_outcome() -> None:
    expect = "expect only(hand[0]) == K and only(hand[1]) == J"
    tester = with_tests(KUHN, f'  test "t" {{\n    chance [1, 0]\n    {expect}\n  }}')
    assert only(tester).ok


def test_several_active_seats_need_an_explicit_seat() -> None:
    d = failure(with_tests(DILEMMA, '  test "t" {\n    play choose(Cooperate)\n  }'))
    assert d.code == "E611" and "pueden actuar varios asientos (0, 1)" in d.message


def test_invariants_are_checked_after_each_step() -> None:
    tester = with_tests(
        KUHN, '  test "t" {\n    play check(), bet()\n  }', invariant="len(moves) < 2"
    )
    d = failure(tester)
    assert d.code == "E613"
    assert [label.message for label in d.labels] == [
        "`len(moves) < 2` es falso: `len(moves)` vale 2",
        "tras este paso",
    ]


def test_set_stops_invariant_checks() -> None:
    tester = with_tests(KUHN, '  test "t" {\n    set deck = []\n    play check()\n  }')
    assert only(tester).ok


def test_playouts_find_invariant_violations() -> None:
    tester = with_tests(KUHN, "", invariant="len(moves) < 2")
    report = tester.playouts(5)
    assert report.failure is not None and report.failure.code == "E613"
    assert report.failure.notes[0].startswith("partida aleatoria con semilla 0 y 2 jugadores")


def test_test_configuration_is_checked_at_compile_time() -> None:
    text = KUHN.read_text(encoding="utf-8")
    end = text.rindex("}")
    misplaced = '  test "t" {\n    play check()\n    seed 3\n  }\n'
    wrong_players = '  test "u" {\n    players 3\n  }\n'
    result = compile_text(text[:end] + misplaced + wrong_players + "}\n")
    codes = sorted(d.code for d in result.diagnostics.errors)
    assert codes == ["E601", "E602"]


def test_test_command(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["test", str(KUHN), "--playouts", "2"]) == 0
    out = capsys.readouterr().out
    assert "✓ la carta alta gana el enfrentamiento" in out
    assert "✓ 1 invariante en 2 partidas aleatorias" in out
    assert out.rstrip().endswith("4 comprobaciones: 4 correctas, 0 fallidas")

    bad = tmp_path / "kuhn.game"
    text = KUHN.read_text(encoding="utf-8").replace("payoff == [2, -2]", "payoff == [9, -9]")
    bad.write_text(text, encoding="utf-8")
    assert main(["test", str(bad), "--playouts", "0", "--format", "json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["failed"] == 1
    failed = [t for t in report["results"][0]["tests"] if not t["ok"]]
    assert failed[0]["failure"]["code"] == "E610"
    assert main(["test", str(bad), "-k", "retirarse", "--playouts", "0"]) == 0
