# SPDX-License-Identifier: Apache-2.0
"""Aceptación de la Fase 3, con procesos de verdad en la red local:

- 4 personas, cada una con su `gamehub join` (como si fueran 4 ordenadores: datos propios, dos
  entran por el código —la sala se encuentra por mDNS— y dos por el enlace con la IP de la LAN),
  juegan Dudo en una sala de `gamehub host`;
- a mitad de partida se cae la terminal de una de ellas y vuelve a entrar: la partida sigue;
- después, una deja la sala y un bot entra por el código (`gamehub bot run`) para la revancha.

Usa la red real (IP de la LAN, multidifusión): solo con `GAMEHUB_LAN_TESTS=1`.
"""

from __future__ import annotations

import json
import os
import random
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import pytest

from gamehub.engine.fairness import verify
from gamehub.server.lan import lan_ip
from server_harness import game

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(
    os.environ.get("GAMEHUB_LAN_TESTS") != "1", reason="red local: define GAMEHUB_LAN_TESTS=1"
)


def gamehub(argv: list[str], data: Path, **kw: object) -> subprocess.Popen[str]:
    code = f"import sys; from gamehub.cli import main; sys.exit(main({argv!r}))"
    env = {**os.environ, "GAMEHUB_DATA": str(data), "PYTHONUNBUFFERED": "1"}
    return subprocess.Popen(
        [sys.executable, "-c", code],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.PIPE,
        text=True,
        env=env,
        **kw,  # type: ignore[arg-type]
    )


class Person:
    """Alguien delante de su terminal: se declara listo y, cuando le toca, juega al azar
    (dudar o apostar a una cara elegida filtrando el menú)."""

    def __init__(
        self, name: str, room: str, data: Path, seed: int, *, pause_at_turn: bool = False
    ) -> None:
        self.name = name
        self.room = room
        self.data = data
        self.rng = random.Random(seed)
        self.lines: list[str] = []
        self.moves = 0
        self.ends = 0
        self.ready_when_asked = True
        self.pause_at_turn = pause_at_turn  # al llegarle el turno, no contesta: avisa en `held`
        self.held = threading.Event()
        self.proc: subprocess.Popen[str] | None = None
        self.start()

    def start(self) -> None:
        self.data.mkdir(parents=True, exist_ok=True)
        self.proc = gamehub(["join", self.room, "--player", self.name], self.data)
        threading.Thread(target=self._read, args=(self.proc,), daemon=True).start()

    def _read(self, proc: subprocess.Popen[str]) -> None:
        try:
            self._follow(proc)
        except Exception as exc:  # que se vea en el diagnóstico
            self.lines.append(f"» excepción en el guion: {exc!r}")

    def _follow(self, proc: subprocess.Popen[str]) -> None:
        assert proc.stdout is not None
        menu: list[str] = []
        for line in proc.stdout:
            if proc is not self.proc:
                return  # salida atrasada de un proceso que ya no es el de esta persona
            line = line.rstrip("\n")
            self.lines.append(line)
            if re.match(r"\s+\d+\. ", line):
                menu.append(line)
            elif "Fin de la partida" in line:
                self.ends += 1
            elif "Escribe /listo" in line and self.ready_when_asked:
                self.ready_when_asked = False
                self.say("/listo")
            elif self.pause_at_turn and line.startswith(("Filtro", "Elige un número")):
                self.lines.append(f"» (en espera, {time.monotonic():.2f})")
                self.held.set()
            elif line.startswith("Filtro"):
                menu = []
                self.say(self.rng.choice(["dudo", f"f: {self.rng.randint(2, 6)}"]))
            elif line.startswith("Elige un número"):
                count = len(menu)
                menu = []
                self.moves += 1
                self.say(str(self.rng.randint(1, max(count, 1))))

    def say(self, text: str) -> None:
        proc = self.proc
        self.lines.append(f"» {text}")
        if proc is not None and proc.stdin is not None and proc.poll() is None:
            try:
                proc.stdin.write(text + "\n")
                proc.stdin.flush()
            except (BrokenPipeError, ValueError) as exc:
                self.lines.append(f"» no se ha podido escribir: {exc!r}")

    def crash(self) -> None:
        """Se cae el ordenador: el proceso muere sin despedirse."""
        assert self.proc is not None
        self.proc.kill()
        self.proc.wait(10)

    def quit(self) -> int:
        self.say("/salir")
        assert self.proc is not None
        return self.proc.wait(30)

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


DIAGNOSE: list[object] = []


def wait_for(condition: object, timeout: float, what: str) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if callable(condition) and condition():
            return
        time.sleep(0.05)
    details = "\n".join(str(d()) for d in DIAGNOSE if callable(d))
    raise AssertionError(f"no ha pasado a tiempo: {what}\n{details}")


def test_four_people_play_dudo_on_the_lan(tmp_path: Path) -> None:
    ip = lan_ip()
    if ip.startswith("127."):
        pytest.skip("este equipo no tiene red local")
    host = gamehub(
        [
            "host",
            str(ROOT / "games" / "dudo"),
            "--players",
            "4",
            "--no-play",
            "--no-qr",
            "--port",
            "0",
            "--db",
            str(tmp_path / "server.sqlite3"),
            "--player",
            "Anfitrión",
        ],
        tmp_path / "host",
    )
    people: list[Person] = []
    try:
        assert host.stdout is not None
        banner = [host.stdout.readline() for _ in range(3)]
        code = banner[1].split()[-1]
        link = banner[2].split()[-1]
        assert link.startswith(f"http://{ip}:"), banner
        server = link.rsplit("/r/", 1)[0]

        def diagnose() -> str:
            with urllib.request.urlopen(f"{server}/api/v1/rooms/{code}", timeout=10) as response:
                room = json.load(response)
            seats = [
                (x["seat"], x.get("name"), x["kind"], x["ready"], x["connected"])
                for x in room["seats"]
            ]
            dump = os.environ.get("GAMEHUB_ACCEPTANCE_LOGS")
            if dump:
                for p in people:
                    Path(dump, f"{p.name}.log").write_text("\n".join(p.lines), encoding="utf-8")
            tails = "\n".join(f"--- {p.name}\n" + "\n".join(p.lines[-30:]) for p in people)
            return f"sala: {room['status']} {seats}\n{tails}"

        DIAGNOSE[:] = [diagnose]
        people = [
            Person("Ana", code, tmp_path / "pc-ana", 1),
            Person("Luis", code, tmp_path / "pc-luis", 2),
            Person("Eva", link, tmp_path / "pc-eva", 3),
            # A Leo se le caerá el ordenador en su primer turno: la partida tendrá que esperarle.
            Person("Leo", link, tmp_path / "pc-leo", 4, pause_at_turn=True),
        ]
        wait_for(lambda: all("── Partida 1" in p.text for p in people), 60, "empieza la partida")
        leo = people[3]
        wait_for(leo.held.is_set, 120, "le toca a Leo")
        leo.crash()
        leo.pause_at_turn = False
        leo.start()  # vuelve a entrar con el mismo enlace desde el mismo ordenador
        wait_for(lambda: "Has vuelto a la sala" in leo.text, 30, "Leo vuelve")
        wait_for(lambda: all(p.ends >= 1 for p in people), 180, "termina la partida")
        # Revancha: Eva se va y un bot entra por el código en su asiento.
        assert people[2].quit() == 0
        bot = gamehub(["bot", "run", "random", "--room", code, "--matches", "1"], tmp_path / "bot")
        for p in (people[0], people[1], people[3]):
            p.ready_when_asked = True
            p.say("/listo")
        try:
            out, _ = bot.communicate(timeout=120)
        except subprocess.TimeoutExpired:
            bot.kill()
            out, _ = bot.communicate()
            raise AssertionError(f"bot: {out}\n{diagnose()}") from None
        assert bot.returncode == 0, out
        assert "partida 2: terminal" in out
        for p in (people[0], people[1], people[3]):
            wait_for(lambda p=p: p.ends >= 2, 60, f"{p.name} ve el final de la revancha")
            assert p.quit() == 0
        with urllib.request.urlopen(f"{server}/api/v1/matches", timeout=10) as response:
            matches = json.load(response)["matches"]
        assert len(matches) == 2 and all(m["reason"] == "terminal" for m in matches)
        for summary in matches:
            with urllib.request.urlopen(f"{server}/api/v1/replays/{summary['id']}") as response:
                data = json.load(response)
            assert verify(game("dudo"), data).is_terminal
        names = [player["name"] for player in matches[0]["players"]]
        assert "Bot random" in names
    finally:
        for p in people:
            if p.proc is not None and p.proc.poll() is None:
                p.proc.kill()
        host.send_signal(signal.SIGINT)
        host.communicate(timeout=20)
    assert host.returncode == 0
