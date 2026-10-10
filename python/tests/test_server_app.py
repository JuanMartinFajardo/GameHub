# SPDX-License-Identifier: Apache-2.0
"""El servidor de partidas de verdad (uvicorn en un hilo): API REST y WebSocket de punta a punta."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Iterator
from typing import Any

import pytest
from websockets.sync.client import ClientConnection, connect

from gamehub.engine.fairness import verify
from gamehub.protocol import check_server, client_message
from gamehub.server.catalog import Catalog
from gamehub.server.codes import display
from gamehub.server.rooms import Limits, Rooms
from gamehub.server.run import ServerThread
from server_harness import game


@pytest.fixture(scope="module")
def server() -> Iterator[ServerThread]:
    catalog = Catalog([game("tictactoe"), game("nim"), game("kuhn-poker")])
    rooms = Rooms(catalog, allow_upload=True, limits=Limits(rate=200, burst=200))
    with ServerThread(rooms) as running:
        yield running


def http(server: ServerThread, path: str, body: Any = None) -> tuple[int, Any]:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        server.url + path, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            text = response.read().decode()
            status = response.status
    except urllib.error.HTTPError as exc:
        text, status = exc.read().decode(), exc.code
    try:
        return status, json.loads(text)
    except ValueError:
        return status, text


class Client:
    def __init__(self, server: ServerThread) -> None:
        # Como gestor de contexto (así lo pide websockets ≥ 17.1); se cierra con `close`.
        self.ws: ClientConnection = connect(server.ws_url).__enter__()
        self.seen: list[dict[str, Any]] = []

    def send(self, kind: str, data: dict[str, Any], mid: str | None = None) -> None:
        self.ws.send(json.dumps(client_message(kind, data, mid)))

    def hello(self, **data: Any) -> dict[str, Any]:
        self.send("hello", {"client": {"name": "test", "kind": "human"}, **data})
        return self.wait("welcome")

    def recv(self, timeout: float = 5) -> dict[str, Any]:
        msg = json.loads(self.ws.recv(timeout))
        assert check_server(msg) == [], msg
        self.seen.append(msg)
        return msg

    def wait(self, kind: str, timeout: float = 5) -> dict[str, Any]:
        while True:
            msg = self.recv(timeout)
            if msg["type"] == kind:
                return msg["data"]

    def close(self) -> None:
        self.ws.close()


def create(server: ServerThread, **body: Any) -> dict[str, Any]:
    status, data = http(server, "/api/v1/rooms", body)
    assert status == 201, data
    return data


def test_rest_api(server: ServerThread) -> None:
    status, info = http(server, "/api/v1/info")
    assert status == 200 and info["protocol"] == 1 and info["upload"] is True
    assert {g["id"] for g in info["games"]} == {"tictactoe", "nim", "kuhn-poker"}
    created = create(server, game="nim", name="Ana", settings={"private": True})
    code = created["code"]
    assert created["url"].endswith(f"/r/{code}") and created["room"]["status"] == "lobby"
    assert http(server, f"/api/v1/rooms/{display(code).lower()}")[1]["code"] == code
    assert http(server, f"/api/v1/rooms/{code}/ir")[1]["game"]["id"] == "nim"
    assert http(server, "/api/v1/games/tictactoe")[1]["game"]["id"] == "tictactoe"
    status, page = http(server, f"/r/{code}")
    assert status == 200 and display(code) in page and "gamehub join" in page
    # Las salas privadas no se listan.
    listed = http(server, "/api/v1/rooms")[1]["rooms"]
    assert code not in [r["code"] for r in listed]


@pytest.mark.parametrize(
    "body,status,code",
    [
        ({"game": "chess"}, 404, "unknown_room"),
        ({}, 400, "bad_message"),
        ({"game": "nim", "players": 9}, 400, "invalid_params"),
        ({"game": "nim", "colour": "red"}, 400, "bad_message"),
        ({"ir": {"no": "es una IR"}}, 400, "bad_message"),
    ],
)
def test_rest_errors(server: ServerThread, body: dict[str, Any], status: int, code: str) -> None:
    got, data = http(server, "/api/v1/rooms", body)
    assert got == status and data["error"]["code"] == code, data


def test_uploading_an_ir(server: ServerThread) -> None:
    created = create(server, ir=game("rock-paper-scissors").ir)
    assert created["room"]["game"]["id"] == "rock-paper-scissors"


def test_play_a_match_over_websocket(server: ServerThread) -> None:
    created = create(server, game="tictactoe", name="Ana")
    ana = Client(server)
    welcome = ana.hello(token=created["token"])
    assert welcome["session"]["host"] is True and welcome["session"]["role"] == "spectator"
    ana.send("sit", {"seat": 0})
    ana.send("ready", {"ready": True, "seed": "ana"})
    luis = Client(server)
    assert "session" not in luis.hello()
    luis.send("join", {"room": display(created["code"]).lower(), "role": "player", "name": "Luis"})
    joined = luis.wait("joined")
    assert joined["session"]["seat"] == 1 and joined["token"]
    luis.send("ready", {"ready": True})
    start = ana.wait("match_start")
    assert start["seat"] == 0 and start["fairness"]["client_seeds"] == ["ana", ""]
    moves = [(ana, [0, 0]), (luis, [1, 1]), (ana, [0, 1]), (luis, [2, 2]), (ana, [0, 2])]
    seq = ana.wait("update")["seq"]
    for i, (who, cell) in enumerate(moves):
        who.send("act", {"seq": seq, "action": {"name": "place", "args": {"c": cell}}}, f"m{i}")
        seq = ana.wait("update")["seq"]
    end = luis.wait("match_end")
    assert end["payoffs"] == [1, -1] and end["ranking"] == [1, 2]
    status, data = http(server, f"/api/v1/replays/{end['replay']}")
    assert status == 200 and verify(game("tictactoe"), data).payoffs == (1, -1)
    matches = http(server, "/api/v1/matches")[1]["matches"]
    assert end["replay"] in [m["id"] for m in matches]
    ana.close()
    luis.close()


def test_protocol_errors(server: ServerThread) -> None:
    c = Client(server)
    c.ws.send("esto no es json")
    assert c.wait("error")["code"] == "bad_message"
    c.send("ready", {"ready": True}, "r1")
    error = c.recv()
    assert error["re"] == "r1" and "hello" in error["data"]["message"]
    welcome_error = c.hello(token="no-existe")
    assert "session" not in welcome_error
    assert any(m["data"].get("code") == "invalid_token" for m in c.seen if m["type"] == "error")
    c.send("join", {"room": "ZZZZZZ", "role": "player", "name": "X"}, "j1")
    assert c.wait("error")["code"] == "unknown_room"
    c.send("ping", {"t": 3.5}, "p1")
    assert c.wait("pong")["t"] == 3.5
    c.close()


def test_reconnect_resumes_the_match(server: ServerThread) -> None:
    created = create(server, game="nim", name="Ana")
    ana = Client(server)
    ana.hello(token=created["token"])
    ana.send("sit", {})
    ana.send("ready", {"ready": True})
    luis = Client(server)
    luis.hello()
    luis.send("join", {"room": created["code"], "role": "player", "name": "Luis"})
    token = luis.wait("joined")["token"]
    luis.send("ready", {"ready": True})
    match_id = luis.wait("match_start")["match"]["id"]
    seq = luis.wait("update")["seq"]
    luis.close()
    ana.wait("room")  # Luis aparece desconectado
    ana.send("act", {"seq": seq, "action": {"name": "take", "args": {"heap": 0, "count": 1}}})
    ana.wait("update")
    back = Client(server)
    welcome = back.hello(token=token, resume={"match": match_id, "seq": seq})
    assert welcome["session"]["seat"] == 1
    update = back.wait("update")
    assert update["seq"] == seq + 1 and update["events"] and update["legal"]["kind"] == "enumerated"
    # La conexión antigua de Ana se sustituye si vuelve a entrar con su token.
    again = Client(server)
    again.hello(token=created["token"])
    assert ana.wait("error")["code"] == "replaced"
    back.close()
    again.close()


def test_rate_limit() -> None:
    rooms = Rooms(Catalog([game("nim")]), limits=Limits(rate=1, burst=3))
    with ServerThread(rooms) as slow:
        c = Client(slow)
        for i in range(6):
            c.send("ping", {}, f"p{i}")
        kinds = [c.recv()["type"] for _ in range(6)]
        assert kinds.count("pong") == 3 and kinds.count("error") == 3
        c.close()


def test_limits_body_rooms_and_connections() -> None:
    from websockets.exceptions import ConnectionClosed

    limits = Limits(max_rooms=2, max_connections=2, max_body=1000, rate=100, burst=100)
    rooms = Rooms(Catalog([game("nim")]), allow_upload=True, limits=limits)
    with ServerThread(rooms) as small:
        status, data = http(small, "/api/v1/rooms", {"ir": game("rock-paper-scissors").ir})
        assert status == 413 and data["error"]["code"] == "bad_message"
        assert http(small, "/api/v1/rooms", {"game": "nim"})[0] == 201
        assert http(small, "/api/v1/rooms", {"game": "nim"})[0] == 201
        status, data = http(small, "/api/v1/rooms", {"game": "nim"})
        assert status == 503 and data["error"]["code"] == "not_allowed"
        first, second = Client(small), Client(small)
        first.hello()
        second.hello()
        third = connect(small.ws_url).__enter__()
        with pytest.raises(ConnectionClosed) as closed:
            third.recv(5)
        assert closed.value.rcvd is not None and closed.value.rcvd.code == 1013  # «más tarde»
        for c in (first, second):
            c.close()


def test_load_many_rooms_at_once() -> None:
    """Una prueba de carga reducida (la completa, de 100 salas: `gamehub loadtest`)."""
    import asyncio

    from gamehub.server.loadtest import run_load

    limits = Limits(rate=1000, burst=1000)
    rooms = Rooms(Catalog([game("nim"), game("dudo")]), limits=limits)
    with ServerThread(rooms) as busy:
        nim = asyncio.run(run_load(busy.url, "nim", rooms=20, matches=2))
        dudo = asyncio.run(run_load(busy.url, "dudo", rooms=10, players=4))
    assert nim.failures == [] and nim.matches == 40
    assert dudo.failures == [] and dudo.matches == 10 and dudo.clients == 40
    assert "40 partidas" in nim.summary() and nim.percentile(0.5) > 0
