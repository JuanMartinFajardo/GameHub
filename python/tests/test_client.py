# SPDX-License-Identifier: Apache-2.0
"""SDK cliente de Python y bots por la red, contra el servidor de partidas de verdad."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from gamehub.cli import main
from gamehub.client import (
    AgentLoadError,
    AgentRunner,
    Client,
    ClientError,
    create_room,
    endpoints,
    load_agent,
    target,
)
from gamehub.engine import Game
from gamehub.engine.fairness import verify
from gamehub.server.catalog import Catalog
from gamehub.server.rooms import Limits, Rooms
from gamehub.server.run import ServerThread
from server_harness import game


@pytest.fixture(scope="module")
def server() -> Iterator[ServerThread]:
    names = ["tictactoe", "nim", "kuhn-poker", "mentiroso", "dudo", "rock-paper-scissors"]
    rooms = Rooms(Catalog([game(n) for n in names]), limits=Limits(rate=1000, burst=1000))
    with ServerThread(rooms) as running:
        yield running


def run(coro: Any) -> Any:
    return asyncio.run(asyncio.wait_for(coro, 60))


def test_endpoints_and_targets() -> None:
    assert endpoints("192.168.1.20") == (
        "http://192.168.1.20:7420",
        "ws://192.168.1.20:7420/ws",
        None,
    )
    assert endpoints("http://h:8000/r/k7f-q2p") == ("http://h:8000", "ws://h:8000/ws", "K7FQ2P")
    assert endpoints("ws://h:9/ws")[0] == "http://h:9"
    assert endpoints("https://juegos.example")[1] == "wss://juegos.example:443/ws"
    assert target("k7f-q2p") == ("http://127.0.0.1:7420", "K7FQ2P")
    assert target("K7FQ2P", "10.0.0.2:7000") == ("http://10.0.0.2:7000", "K7FQ2P")
    assert target("http://10.0.0.2:7420/r/K7FQ2P") == ("http://10.0.0.2:7420", "K7FQ2P")
    with pytest.raises(ClientError):
        target("corto")  # (curioso: «no-vale» sí sería un código válido, N0VA1E)
    with pytest.raises(ClientError):
        target("http://10.0.0.2:7420/")


async def bot(server: ServerThread, code: str, agent: str = "random", **kw: Any) -> list[dict]:
    async with Client(server.url, name=f"bot-{agent}", kind="bot", validate=True) as client:
        await client.join(code)
        g = Game(await client.room_ir())
        runner = AgentRunner(client, load_agent(agent, seed=3), g, **kw)
        return await runner.run()


def test_two_bots_play_several_matches(server: ServerThread) -> None:
    async def scenario() -> tuple[list[dict], list[dict]]:
        created = await create_room(server.url, game="nim")
        return await asyncio.gather(
            bot(server, created["code"], matches=3),
            bot(server, created["code"], "first", matches=3),
        )

    a, b = run(scenario())
    assert len(a) == len(b) == 3
    assert [r["match"]["number"] for r in a] == [1, 2, 3]
    assert all(r["reason"] == "terminal" and sorted(r["ranking"]) == [1, 2] for r in a)


def test_a_person_and_a_bot(server: ServerThread) -> None:
    async def scenario() -> dict[str, Any]:
        created = await create_room(server.url, game="tictactoe", name="Ana")
        task = asyncio.create_task(bot(server, created["code"], "first"))
        async with Client(server.url, token=created["token"], validate=True) as ana:
            assert ana.session is not None and ana.session["host"]
            await ana.sit(0)
            await ana.ready(seed="ana")
            async for msg in ana:
                if msg["type"] == "update" and ana.my_turn:
                    legal = ana.legal
                    assert legal
                    await ana.act(legal[-1])
                if msg["type"] == "match_end":
                    break
            assert ana.ending is not None
            await task
            return ana.ending

    end = run(scenario())
    data = run(Client(server.url).get_json(f"/api/v1/replays/{end['replay']}"))
    assert verify(game("tictactoe"), data).is_terminal
    assert data["fairness"]["client_seeds"][0] == "ana"


def test_agent_from_a_file_with_hooks(server: ServerThread, tmp_path: Path) -> None:
    agent_file = tmp_path / "primero.py"
    agent_file.write_text(
        """
calls = []


class Agent:
    def __init__(self, game, seat):
        self.seat = seat

    def reset(self, observation):
        calls.append(("reset", observation.seat))

    def observe(self, observation):
        calls.append(("observe", observation.view["node"]))

    def act(self, observation, legal):
        calls.append(("act", len(legal)))
        return legal[0]

    def end(self, result):
        calls.append(("end", result["reason"]))
""",
        encoding="utf-8",
    )

    async def scenario() -> list[dict]:
        created = await create_room(server.url, game="kuhn-poker")
        other = asyncio.create_task(bot(server, created["code"], "random"))
        mine = await bot(server, created["code"], str(agent_file))
        await other
        return mine

    results = run(scenario())
    import sys

    module = next(m for k, m in sys.modules.items() if k.startswith("gamehub_agent_primero"))
    kinds = [c[0] for c in module.calls]
    assert kinds[0] == "reset" and kinds[-1] == "end" and "act" in kinds
    assert results[0]["reason"] == "terminal"


def test_load_agent_errors(tmp_path: Path) -> None:
    with pytest.raises(AgentLoadError):
        load_agent("minimax")
    empty = tmp_path / "vacio.py"
    empty.write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(AgentLoadError, match="make_agent"):
        load_agent(str(empty))
    fn = tmp_path / "fn.py"
    fn.write_text("def act(observation, legal):\n    return legal[-1]\n", encoding="utf-8")
    agent = load_agent(str(fn))(game("nim"), 0)
    assert agent.act(None, [1, 2, 3]) == 3


def test_progressive_actions_for_bots(server: ServerThread) -> None:
    """Con un límite de una acción, las de Dudo llegan progresivas (`bid` tiene dos parámetros)
    y el bot las construye con `query_actions`."""

    async def player(code: str) -> list[dict]:
        async with Client(server.url, name="bot", kind="bot", legal_limit=1) as client:
            await client.join(code)
            g = Game(await client.room_ir())
            return await AgentRunner(client, load_agent("random", seed=1), g).run()

    async def scenario() -> list[list[dict]]:
        created = await create_room(server.url, game="dudo", players=3, params={"dice": 2})
        return await asyncio.gather(*(player(created["code"]) for _ in range(3)))

    results = run(scenario())
    assert all(r[0]["reason"] == "terminal" for r in results)


def test_reconnection_does_not_break_the_match(server: ServerThread) -> None:
    """Se corta la conexión de un jugador a mitad de partida: el cliente vuelve solo, recibe lo
    que se perdió y la partida termina con normalidad."""

    async def scenario() -> tuple[list[str], dict[str, Any]]:
        created = await create_room(server.url, game="dudo", players=2)
        other = asyncio.create_task(bot(server, created["code"], "random"))
        statuses: list[str] = []
        async with Client(server.url, name="Ana", on_status=statuses.append) as ana:
            await ana.join(created["code"])
            await ana.ready()
            cut = False
            async for msg in ana:
                if msg["type"] == "update" and ana.my_turn:
                    if not cut and ana.seq >= 1:
                        cut = True
                        assert ana.ws is not None
                        await ana.ws.close()  # se va la red
                        continue
                    legal = ana.legal
                    assert legal
                    await ana.act(legal[-1])  # dudar si se puede
                if msg["type"] == "match_end":
                    break
            await other
            assert ana.ending is not None
            return statuses, ana.ending

    statuses, end = run(scenario())
    assert statuses == ["reconnecting", "connected"]
    assert end["reason"] == "terminal"


def test_join_errors(server: ServerThread) -> None:
    async def scenario() -> None:
        async with Client(server.url) as c:
            with pytest.raises(ClientError) as info:
                await c.join("ZZZZZZ")
            assert info.value.code == "unknown_room"
        with pytest.raises(ClientError) as info:
            await create_room(server.url, game="chess")
        assert info.value.code == "unknown_room"

    run(scenario())


def test_cannot_connect() -> None:
    async def scenario() -> None:
        with pytest.raises(ClientError) as info:
            await Client("127.0.0.1:1").connect()
        assert info.value.code == "connection"

    run(scenario())


def test_bot_run_command(server: ServerThread, capsys: pytest.CaptureFixture[str]) -> None:
    import threading

    created = run(create_room(server.url, game="nim"))

    async def partner() -> list[dict]:
        await asyncio.sleep(0.2)
        return await bot(server, created["code"], "first")

    partner_thread = threading.Thread(target=lambda: run(partner()), daemon=True)
    partner_thread.start()
    codes: list[int] = []
    argv = ["bot", "run", "random", "--room", created["code"], "--server", server.url]
    cli_thread = threading.Thread(target=lambda: codes.append(main(argv)), daemon=True)
    cli_thread.start()
    cli_thread.join(60)
    partner_thread.join(30)
    assert not cli_thread.is_alive(), "gamehub bot run no ha terminado"
    out = capsys.readouterr().out
    assert codes == [0] and "partida 1: terminal" in out


def test_message_ids_are_unique_across_clients() -> None:
    """Dos procesos que retoman la misma sesión no pueden repetir ids: el servidor descartaría
    como reintento la jugada del segundo (lo encontró la prueba de aceptación)."""
    a, b = Client("127.0.0.1"), Client("127.0.0.1")
    ids_a = {a._next_id() for _ in range(100)}
    ids_b = {b._next_id() for _ in range(100)}
    assert len(ids_a) == 100 and not ids_a & ids_b
