# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from gamehub.cli import main
from gamehub.console.play import ConsoleIO, Quit, choose, play_terminal
from gamehub.engine import Action, load_game
from gamehub.ir.spec import examples_dir


class Script:
    """Entrada simulada: devuelve las respuestas en orden y registra la salida."""

    def __init__(self, answers: list[str]) -> None:
        self._answers: Iterator[str] = iter(answers)
        self.output: list[str] = []
        self.io = ConsoleIO(read=self._read, write=self.output.append)

    def _read(self, prompt: str) -> str:
        self.output.append(prompt)
        try:
            return next(self._answers)
        except StopIteration:
            raise EOFError from None

    @property
    def text(self) -> str:
        return "\n".join(self.output)


def test_choose_by_number_and_filter() -> None:
    legal = [Action.of("bid", x=i) for i in range(50)]
    script = Script(["4", "1"])  # filtra por "4" (4, 14, 24…) y elige el primero
    assert choose(legal, script.io) == Action.of("bid", x=4)
    with pytest.raises(Quit):
        choose(legal, Script([]).io)


def test_terminal_game_against_a_bot(tmp_path: Path) -> None:
    game = load_game(examples_dir() / "tictactoe.ir.json")
    script = Script(["5", "1", "4"])
    replay_path = tmp_path / "ttt.ghr.json"
    state = play_terminal(game, ["human", "first"], io=script.io, save_replay=replay_path)
    assert state.is_terminal and state.payoffs == (1, -1)
    assert "pagos: 1, -1" in script.text
    assert main(["replay", str(replay_path), "--quiet"]) == 0


def test_hot_seat_hides_private_information() -> None:
    game = load_game(examples_dir() / "kuhn-poker.ir.json")
    script = Script(["1", "", "1"])  # asiento 0 pasa; cambio de jugador; asiento 1 pasa
    state = play_terminal(game, ["human", "human"], seed=3, io=script.io)
    assert state.is_terminal
    assert "Pasa el dispositivo" in script.text
    seat0_card = state.view(None)["state"]["hand"][0]["items"][0]
    seat1_view = script.text.split("vista del asiento 1")[1].split("vista omnisciente")[0]
    hand_line = next(ln for ln in seat1_view.splitlines() if "asiento 0:" in ln)
    assert seat0_card not in hand_line


def test_fuzz_and_conformance_commands(capsys: pytest.CaptureFixture[str]) -> None:
    game = str(examples_dir() / "prisoners-dilemma.ir.json")
    assert main(["fuzz", game, "--games", "50", "--param", "T=11/2"]) == 0
    assert "completas: 50" in capsys.readouterr().out
    assert main(["fuzz", game, "--games", "5", "--param", "T=6"]) == 2
    assert "2R > T + S" in capsys.readouterr().err
    assert main(["conformance", "--check"]) == 0
