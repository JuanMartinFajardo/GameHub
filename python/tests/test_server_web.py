# SPDX-License-Identifier: Apache-2.0
"""Lo que el servidor sirve para la app web: la propia app (con sus rutas), el QR de cada sala y
las partidas terminadas paso a paso para verlas en el navegador."""

from __future__ import annotations

import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

from gamehub.server.catalog import Catalog
from gamehub.server.codes import display
from gamehub.server.rooms import Limits, Rooms
from gamehub.server.run import ServerThread
from gamehub.server.webapp import web_dir
from server_harness import game
from test_server_app import Client, create, http


def get(server: ServerThread, path: str, accept: str = "text/html") -> tuple[int, str, str]:
    request = urllib.request.Request(server.url + path, headers={"Accept": accept})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.headers["content-type"], response.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers["content-type"], exc.read().decode()


@pytest.fixture(scope="module")
def web(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("web")
    (root / "index.html").write_text("<!doctype html><title>app</title>", encoding="utf-8")
    (root / "assets").mkdir()
    (root / "assets" / "app.js").write_text("console.log('hola')", encoding="utf-8")
    return root


@pytest.fixture(scope="module")
def server(web: Path) -> Iterator[ServerThread]:
    rooms = Rooms(Catalog([game("tictactoe"), game("nim")]), limits=Limits(rate=200, burst=200))
    with ServerThread(rooms, web=web) as running:
        yield running


def test_the_app_and_its_routes(server: ServerThread) -> None:
    code = create(server, game="nim")["code"]
    for path in ("/", f"/r/{code}", "/r/ZZZZZZ", "/replay/abc", "/local/nim", "/kit"):
        status, kind, body = get(server, path)
        assert status == 200 and kind.startswith("text/html") and "<title>app</title>" in body, path
    status, kind, body = get(server, "/assets/app.js")
    assert status == 200 and "javascript" in kind and "hola" in body
    assert get(server, "/assets/missing.js")[0] == 404
    # Las interfaces que piden JSON siguen recibiendo la sala.
    status, kind, body = get(server, f"/r/{code}", accept="application/json")
    assert status == 200 and kind == "application/json" and f'"code":"{code}"' in body
    # La API no se tapa con la app.
    assert http(server, "/api/v1/info")[1]["protocol"] == 1


def test_without_the_app_there_are_minimal_pages() -> None:
    rooms = Rooms(Catalog([game("nim")]))
    with ServerThread(rooms) as running:
        code = create(running, game="nim")["code"]
        status, _, body = get(running, f"/r/{code}")
        assert status == 200 and display(code) in body and "gamehub join" in body
        status, _, body = get(running, "/kit")
        assert status == 404 and "pnpm" in body
        assert "Salas abiertas" in get(running, "/")[2]


def test_room_qr_as_svg(server: ServerThread) -> None:
    code = create(server, game="nim")["code"]
    status, kind, body = get(server, f"/api/v1/rooms/{code}/qr.svg")
    assert status == 200 and kind.startswith("image/svg+xml") and body.startswith("<svg")
    assert 'xmlns="http://www.w3.org/2000/svg"' in body  # para usarlo en un <img>
    assert get(server, "/api/v1/rooms/ZZZZZZ/qr.svg")[0] == 404


def test_a_finished_match_step_by_step(server: ServerThread) -> None:
    created = create(server, game="tictactoe", name="Ana")
    ana = Client(server)
    ana.hello(token=created["token"])
    ana.send("sit", {"seat": 0})
    ana.send("ready", {"ready": True})
    luis = Client(server)
    luis.hello()
    luis.send("join", {"room": created["code"], "role": "player", "name": "Luis"})
    luis.wait("joined")
    luis.send("ready", {"ready": True})
    seq = ana.wait("update")["seq"]
    for i, (who, cell) in enumerate(
        [(ana, [0, 0]), (luis, [1, 1]), (ana, [0, 1]), (luis, [2, 2]), (ana, [0, 2])]
    ):
        who.send("act", {"seq": seq, "action": {"name": "place", "args": {"c": cell}}}, f"m{i}")
        seq = ana.wait("update")["seq"]
    end = luis.wait("match_end")
    ana.close()
    luis.close()
    status, data = http(server, f"/api/v1/replays/{end['replay']}/frames")
    assert status == 200 and data["seat"] == "all" and data["ir"]["game"]["id"] == "tictactoe"
    frames = data["frames"]
    assert len(frames) == 6 and [f["step"] for f in frames] == list(range(6))
    assert frames[0]["view"]["node"] == "Move" and frames[-1]["view"]["status"] == "terminal"
    assert frames[-1]["view"]["state"]["board"][0] == ["X", "X", "X"]
    assert any(e["type"] == "action" for e in frames[1]["events"])
    assert [p["name"] for p in data["players"]] == ["Ana", "Luis"]
    assert data["result"]["payoffs"] == [1, -1]
    for seat in ("0", "public"):
        status, seen = http(server, f"/api/v1/replays/{end['replay']}/frames?seat={seat}")
        assert status == 200 and len(seen["frames"]) == 6
    assert http(server, f"/api/v1/replays/{end['replay']}/frames?seat=7")[0] == 400
    assert http(server, "/api/v1/replays/nope/frames")[0] == 404


def test_web_dir_from_the_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GAMEHUB_WEB_DIR", str(tmp_path))
    assert web_dir() is None
    (tmp_path / "index.html").write_text("<!doctype html>", encoding="utf-8")
    assert web_dir() == tmp_path
