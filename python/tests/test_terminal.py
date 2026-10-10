# SPDX-License-Identifier: Apache-2.0
"""Cliente de terminal para jugar en red (`gamehub host`, `gamehub join`, `gamehub rooms`),
con un servidor de verdad y las líneas del usuario guionizadas."""

from __future__ import annotations

import asyncio
import random
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from gamehub.client import Client, create_room
from gamehub.client.play import host, join, list_rooms
from gamehub.client.terminal import Sessions, Terminal
from gamehub.server.catalog import Catalog
from gamehub.server.rooms import Limits, Rooms
from gamehub.server.run import ServerThread
from gamehub.server.store import MemoryStore
from server_harness import game

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def server() -> Iterator[ServerThread]:
    names = ["tictactoe", "nim", "dudo"]
    rooms = Rooms(Catalog([game(n) for n in names]), limits=Limits(rate=1000, burst=1000))
    with ServerThread(rooms) as running:
        yield running


def run(coro: Any) -> Any:
    return asyncio.run(asyncio.wait_for(coro, 60))


class User:
    """Una persona guionizada delante de la terminal: escribe cuando le toca."""

    def __init__(self, choose: Callable[[Terminal], str] | None = None) -> None:
        self.output: list[str] = []
        self.terminal: Terminal | None = None
        self.choose = choose or (lambda term: "1")
        self.before: list[str] = ["/listo"]
        self.after: list[str] = ["/salir"]

    @property
    def text(self) -> str:
        return "\n".join(self.output)

    async def lines(self) -> AsyncIterator[str]:
        while self.terminal is None:
            await asyncio.sleep(0.01)
        term = self.terminal
        for line in self.before:
            yield line
        while not term.finished and term.client.ending is None:
            chooser = term.chooser
            if chooser is not None:
                yield self.choose(term)
                # Espera a que la respuesta se procese (otro menú o fin del turno).
                while term.chooser is chooser and not term.finished:
                    await asyncio.sleep(0.01)
            else:
                await asyncio.sleep(0.01)
        for line in self.after:
            yield line


async def play(user: User, client: Client) -> int:
    term = Terminal(client, out=user.output.append)
    user.terminal = term
    return await term.run(user.lines())


def test_terminal_plays_against_a_server_bot(server: ServerThread) -> None:
    async def scenario() -> User:
        created = await create_room(server.url, game="tictactoe", name="Ana")
        user = User()
        async with Client(server.url, name="Ana", token=created["token"]) as client:
            await client.sit(0)
            await client.set_seat(1, "bot", bot="first")
            await play(user, client)
        return user

    user = run(scenario())
    text = user.text
    assert "── Sala" in text and "Te toca" in text and "place(c: [0, 0])" in text
    assert "── Fin de la partida (fin) ──" in text and "1.º" in text
    assert "Has salido de la sala." in text


def test_two_terminals_play_each_other(server: ServerThread) -> None:
    rng = random.Random(4)

    def pick(term: Terminal) -> str:
        assert term.chooser is not None
        return str(rng.randint(1, min(len(term.chooser.candidates), 30)))

    async def scenario() -> tuple[User, User]:
        created = await create_room(server.url, game="nim")
        a, b = User(pick), User(pick)
        async with (
            Client(server.url, name="Ana") as ca,
            Client(server.url, name="Luis") as cb,
        ):
            await ca.join(created["code"])
            await cb.join(created["code"])
            await asyncio.gather(play(a, ca), play(b, cb))
        return a, b

    a, b = run(scenario())
    assert "Fin de la partida" in a.text and "Fin de la partida" in b.text
    assert "Turno de Luis" in a.text or "Turno de Ana" in b.text


def test_progressive_choice_in_the_terminal(server: ServerThread) -> None:
    """Con un límite de una acción, Dudo se elige paso a paso: acción, cantidad, cara."""

    async def scenario() -> User:
        created = await create_room(server.url, game="dudo", name="Ana", params={"dice": 1})
        user = User()
        async with Client(server.url, name="Ana", token=created["token"], legal_limit=1) as c:
            await c.sit(0)
            await c.set_seat(1, "bot", bot="first")
            await play(user, c)
        return user

    user = run(scenario())
    assert "bid: elige q" in user.text and "bid: elige f" in user.text
    assert "Fin de la partida" in user.text


def test_terminal_commands(server: ServerThread) -> None:
    commands = [
        "/ayuda",
        "/estado",
        "/teletransporte",
        "hola a todos",
        "3",
        "/jugadores 3",
        "/opcion dice=2",
        "/bot 2",
        "/bot 3 first",
        "/sala",
    ]

    async def scenario() -> tuple[list[str], dict[str, Any]]:
        created = await create_room(server.url, game="dudo", name="Ana")
        out: list[str] = []

        async def lines() -> AsyncIterator[str]:
            for line in commands:
                yield line
                await asyncio.sleep(0.05)
            await asyncio.sleep(0.3)
            yield "/salir"

        async with Client(server.url, name="Ana", token=created["token"]) as client:
            await client.sit(0)
            await Terminal(client, out=out.append).run(lines())
            assert client.room is not None
            return out, client.room

    out, room = run(scenario())
    assert len(room["seats"]) == 3 and room["params"] == {"dice": 2}
    assert [s["kind"] for s in room["seats"]] == ["human", "bot", "bot"]
    text = "\n".join(out)
    assert "Comandos" in text and "No hay ninguna partida en marcha." in text
    assert "Comando desconocido" in text and "No es tu turno." in text
    assert "[Ana] hola a todos" in text and "Has salido de la sala." in text


def test_join_resumes_a_saved_session(server: ServerThread, tmp_path: Path) -> None:
    """Si se cierra la terminal a mitad (sin /salir), `gamehub join` vuelve al mismo sitio."""
    sessions = Sessions(tmp_path / "sessions.json")

    async def forever() -> AsyncIterator[str]:
        await asyncio.Event().wait()
        yield ""

    async def scenario() -> tuple[str, str]:
        created = await create_room(server.url, game="nim", name="Ana")
        out1: list[str] = []
        task = asyncio.create_task(
            join(
                created["code"],
                server=server.url,
                player="Luis",
                lines=forever(),
                out=out1.append,
                sessions=sessions,
            )
        )
        while not any("Has entrado" in line for line in out1):
            await asyncio.sleep(0.01)
        task.cancel()  # se mata el proceso: no llega a salir de la sala
        await asyncio.gather(task, return_exceptions=True)
        assert sessions.get(server.url, created["code"]) is not None
        user = User()
        user.before, user.after = ["/levantar", "/sentar"], ["/salir"]
        out2: list[str] = []

        async def lines() -> AsyncIterator[str]:
            while user.terminal is None:
                await asyncio.sleep(0.01)
            for line in ["/levantar", "/sentar", "/salir"]:
                await asyncio.sleep(0.1)
                yield line

        await join(
            created["code"],
            server=server.url,
            player="Luis",
            lines=lines(),
            out=out2.append,
            sessions=sessions,
            on_terminal=lambda t: setattr(user, "terminal", t),
        )
        assert sessions.get(server.url, created["code"]) is None  # salió: se olvida
        return "\n".join(out1), "\n".join(out2)

    first_text, second_text = run(scenario())
    assert "Has entrado en la sala" in first_text
    assert "Has vuelto a la sala" in second_text and "Eres espectador" in second_text


def test_host_and_join_over_the_network(tmp_path: Path) -> None:
    """`gamehub host` (sin QR ni mDNS) y otra terminal que se une por el enlace."""
    nim = game("nim")

    async def scenario() -> tuple[User, User, dict[str, Any]]:
        ready = asyncio.Event()
        info: dict[str, Any] = {}
        hosting, guest = User(), User()
        host_task = asyncio.create_task(
            host(
                nim,
                player="Ana",
                lines=hosting.lines(),
                out=hosting.output.append,
                store=MemoryStore(),
                listen="127.0.0.1",
                port=0,
                mdns=False,
                qr=False,
                ready=ready,
                info=info,
                on_terminal=lambda t: setattr(hosting, "terminal", t),
            )
        )
        await ready.wait()
        link = f"{info['url']}/r/{info['code']}"
        await join(
            link,
            player="Luis",
            lines=guest.lines(),
            out=guest.output.append,
            sessions=Sessions(tmp_path / "sessions.json"),
            on_terminal=lambda t: setattr(guest, "terminal", t),
        )
        await host_task
        return hosting, guest, info

    hosting, guest, info = run(scenario())
    assert f"Sala:   {info['code'][:3]}-{info['code'][3:]}" in hosting.text
    assert "gamehub join" in hosting.text
    assert "Fin de la partida" in hosting.text and "Fin de la partida" in guest.text


def test_list_rooms(server: ServerThread) -> None:
    async def scenario() -> list[str]:
        created = await create_room(server.url, game="nim")
        out: list[str] = []
        await list_rooms(server=server.url, out=out.append)
        return [created["code"], *out]

    code, *out = run(scenario())
    text = "\n".join(out)
    assert f"{code[:3]}-{code[3:]}" in text and "Nim" in text
