# SPDX-License-Identifier: Apache-2.0
"""El servidor del Studio: seguridad, API del espacio de trabajo y una sesión por WebSocket con el
servidor de lenguaje, las ediciones del diagrama y el simulador."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from websockets.exceptions import InvalidStatus, WebSocketException
from websockets.sync.client import connect

from gamehub.studio.server import COOKIE, StudioThread
from studio_harness import TOKEN, Session, apply, call, open_session

ROOT = Path(__file__).resolve().parents[2]
TICTACTOE = "tictactoe/tictactoe.game"


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    for name in ("tictactoe", "dudo"):
        shutil.copytree(ROOT / "games" / name, tmp_path / name, ignore=shutil.ignore_patterns("ui"))
    return tmp_path


@pytest.fixture
def studio(workspace: Path) -> Iterator[StudioThread]:
    with StudioThread(workspace, token=TOKEN) as running:
        yield running


# --- Seguridad ------------------------------------------------------------------------------------


def test_the_api_needs_the_token(studio: StudioThread) -> None:
    assert call(studio, "GET", "/api/workspace", token=None).status == 401
    assert call(studio, "GET", "/api/workspace", token="otro").status == 401
    assert call(studio, "GET", "/api/workspace").status == 200
    assert call(studio, "GET", f"/api/workspace?token={TOKEN}", token=None).status == 200


def test_opening_with_the_token_sets_a_cookie(studio: StudioThread) -> None:
    page = call(studio, "GET", "/", token=None)
    assert page.status == 401 and "token" in page.text
    response = call(studio, "GET", f"/?token={TOKEN}&file={TICTACTOE}", token=None)
    assert response.status == 303
    assert response.headers["location"] == f"/?file={TICTACTOE}"
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{COOKIE}={TOKEN}")
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie
    with_cookie = {"cookie": f"{COOKIE}={TOKEN}"}
    assert call(studio, "GET", "/api/workspace", token=None, headers=with_cookie).status == 200
    # Sin la app compilada, una página que explica cómo compilarla.
    assert "pnpm build" in call(studio, "GET", "/", token=None, headers=with_cookie).text


def test_other_hosts_are_refused(studio: StudioThread) -> None:
    response = call(studio, "GET", "/api/workspace", headers={"host": "evil.example:7421"})
    assert response.status == 403


def test_websockets_need_the_token_and_a_local_origin(studio: StudioThread) -> None:
    url = f"ws://127.0.0.1:{studio.port}/lsp"
    for target, origin in ((url, None), (f"{url}?token={TOKEN}", "http://evil.example")):
        with (
            pytest.raises((InvalidStatus, WebSocketException)),
            connect(
                target,
                origin=origin,  # type: ignore[arg-type]
            ) as ws,
        ):
            ws.recv(timeout=5)
    with connect(f"{url}?token={TOKEN}", origin="http://127.0.0.1:5175") as ws:  # type: ignore[arg-type]
        ws.send(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "shutdown"}))
        assert json.loads(ws.recv(timeout=10))["id"] == 1


# --- Espacio de trabajo ---------------------------------------------------------------------------


def test_files_read_write_and_layout(studio: StudioThread, workspace: Path) -> None:
    info = call(studio, "GET", "/api/workspace").json()
    paths = [f["path"] for f in info["files"]]
    assert paths == ["dudo/dudo.game", TICTACTOE]
    assert info["files"][1]["package"] == "tictactoe"
    assert {t["id"] for t in info["templates"]} >= {"vacio", "tablero", "cartas"}
    file = call(studio, "GET", f"/api/file?path={TICTACTOE}").json()
    assert file["text"].startswith("// SPDX") and file["layout"] is None
    assert file["uri"] == (workspace / TICTACTOE).as_uri()
    assert 0 < file["mtime"] < 2**53  # exacto también como número de JavaScript
    saved = call(
        studio,
        "PUT",
        "/api/file",
        body={"path": TICTACTOE, "text": file["text"] + "\n", "mtime": file["mtime"]},
    )
    assert saved.status == 200
    stale = call(
        studio, "PUT", "/api/file", body={"path": TICTACTOE, "text": "x", "mtime": file["mtime"]}
    )
    assert stale.status == 409
    assert call(studio, "GET", "/api/file?path=../../etc/passwd").status == 403
    layout = {"games": {"TicTacToe": {"nodes": {"Move": {"x": 10, "y": 20}}}}}
    stored = call(studio, "PUT", "/api/layout", body={"path": TICTACTOE, "layout": layout})
    assert stored.status == 200
    assert (workspace / "tictactoe" / "tictactoe.layout.json").is_file()
    assert call(studio, "GET", f"/api/file?path={TICTACTOE}").json()["layout"] == layout


def test_new_game_from_a_template(studio: StudioThread, workspace: Path) -> None:
    body = {"name": "mi-juego", "template": "dados", "title": "Mi juego"}
    made = call(studio, "POST", "/api/new", body=body)
    assert made.status == 200 and made.json()["path"] == "mi-juego/mi-juego.game"
    text = (workspace / "mi-juego" / "mi-juego.game").read_text(encoding="utf-8")
    assert 'title: "Mi juego"' in text and "game MiJuego {" in text and "roll(6)" in text
    assert call(studio, "POST", "/api/new", body={"name": "Mal"}).status == 400
    assert call(studio, "POST", "/api/new", body={"name": "mi-juego"}).status == 400


def test_git_history(studio: StudioThread, workspace: Path) -> None:
    def git(*args: str) -> None:
        user = ["-c", "user.email=a@b.c", "-c", "user.name=A"]
        subprocess.run(["git", *user, *args], cwd=workspace, check=True, capture_output=True)

    git("init", "-q")
    git("add", ".")
    git("commit", "-qm", "primera versión")
    path = workspace / TICTACTOE
    original = path.read_text(encoding="utf-8")
    path.write_text(original.replace("Tres en raya", "Tres en línea"), encoding="utf-8")
    log = call(studio, "GET", f"/api/git/log?path={TICTACTOE}").json()
    assert [c["subject"] for c in log] == ["primera versión"]
    rev = log[0]["rev"]
    shown = call(studio, "GET", f"/api/git/show?path={TICTACTOE}&rev={rev}").json()
    assert shown["text"] == original
    assert call(studio, "GET", f"/api/git/show?path={TICTACTOE}&rev=;rm").status == 400


# --- Sesión por WebSocket -------------------------------------------------------------------------


@pytest.fixture
def session(studio: StudioThread, workspace: Path) -> Iterator[Session]:
    with open_session(studio, workspace) as s:
        yield s


def test_diagram_edits_round_trip_through_the_editor(session: Session, workspace: Path) -> None:
    s = session
    path = workspace / TICTACTOE
    uri = s.open(path)
    text = path.read_text(encoding="utf-8")
    analysis = s.wait("gamehub/analysis")
    assert analysis["compiled"] and analysis["classification"]["perfect_information"]
    nodes = [n["id"] for n in analysis["model"]["game"]["flow"]["nodes"]]
    assert nodes == ["Move", "Win", "Draw"]
    # Una edición del diagrama: el servidor responde con los cambios para el editor.
    add = {"op": "addNode", "kind": "terminal", "name": "Tie"}
    result = s.request("gamehub/edit", {"uri": uri, "version": 1, "ops": [add]})
    assert result["focus"] == {"node": "Tie"}
    new = apply(text, result["edits"])
    assert "terminal Tie { payoff: fill(0) }" in new
    change = {"textDocument": {"uri": uri, "version": 2}, "contentChanges": [{"text": new}]}
    s.notify("textDocument/didChange", change)
    analysis = s.wait("gamehub/analysis", lambda p: p["version"] == 2)
    assert [n["id"] for n in analysis["model"]["game"]["flow"]["nodes"]][-1] == "Tie"
    assert any(p["code"] == "W401" for p in analysis["problems"])  # inalcanzable
    # Con la versión equivocada, se rechaza.
    delete = {"op": "deleteNode", "node": "Tie"}
    with pytest.raises(RuntimeError, match="ha cambiado"):
        s.request("gamehub/edit", {"uri": uri, "version": 1, "ops": [delete]})
    wrong = {"op": "addTransition", "node": "Move", "target": "Tie", "when": "x =="}
    with pytest.raises(RuntimeError, match='"field": "when"'):
        s.request("gamehub/edit", {"uri": uri, "version": 2, "ops": [wrong]})
    # El LSP de siempre funciona en la misma conexión.
    line = new[: new.index("board: Grid")].count("\n")
    position = {"line": line, "character": 6}
    hover = s.request("textDocument/hover", {"textDocument": {"uri": uri}, "position": position})
    assert "Grid[3, 3] of Mark?" in hover["contents"]["value"]
    # El modelo de otra versión (para comparar).
    other = s.request("gamehub/modelOf", {"text": text, "path": str(path)})
    assert [n["id"] for n in other["model"]["game"]["flow"]["nodes"]] == ["Move", "Win", "Draw"]


def test_the_simulator(session: Session, workspace: Path) -> None:
    s = session
    uri = s.open(workspace / "dudo" / "dudo.game")
    s.wait("gamehub/analysis")
    started = s.request("gamehub/sim.start", {"uri": uri, "seed": 5})
    sid = started["session"]
    snap = started["snapshot"]
    assert snap["status"] == "chance" and snap["chance"]["enumerable"] is False
    snap = s.request("gamehub/sim.chance", {"session": sid, "index": 0})
    assert snap["index"] == 1 and snap["status"] == "decision"
    seat = snap["active"][0]
    # Cada asiento ve sus dados y no los del otro; la vista omnisciente, todos.
    cups = snap["omniscient"]["state"]["cup"]
    mine = snap["views"][str(seat)]["state"]["cup"]
    assert mine[seat] == cups[seat] and mine[1 - seat] != cups[1 - seat]
    first, second = snap["legal"][str(seat)]["actions"][:2]
    after = s.request(
        "gamehub/sim.act", {"session": sid, "index": 1, "seat": seat, "action": first}
    )
    assert after["index"] == 2 and after["step"]["kind"] == "action" and after["step"]["trace"]
    # Viaje en el tiempo: volver al paso 1 y jugar otra cosa recorta la historia.
    branch = s.request(
        "gamehub/sim.act", {"session": sid, "index": 1, "seat": seat, "action": second}
    )
    assert branch["index"] == 2 and branch["length"] == 3
    # Correr hasta un punto de ruptura: llegar otra vez a Roll, o una condición en Nomos.
    stop = {"session": sid, "index": 2, "breakpoints": [{"node": "Roll"}]}
    assert s.request("gamehub/sim.run", stop)["reason"] in ("breakpoint", "end")
    cond = {"session": sid, "index": 0, "breakpoints": [{"expr": "quantity >= 3"}]}
    ran = s.request("gamehub/sim.run", cond)
    assert ran["reason"] in ("breakpoint", "end")
    with pytest.raises(RuntimeError, match="nombre desconocido"):
        s.request("gamehub/sim.condition", {"uri": uri, "expr": "nada > 1"})
    timeline = s.request("gamehub/sim.timeline", {"session": sid})
    assert timeline[0]["kind"] == "start"
    stats = s.request("gamehub/sim.playouts", {"uri": uri, "games": 30, "seed": 1})
    assert stats["finished"] == 30 and stats["coverage"]["nodes"]["Bid"] > 0
    assert any(k.startswith("node/Roll/") for k in stats["coverage"]["transitions"])
    size = s.request("gamehub/sim.estimate", {"uri": uri, "samples": 20})
    assert size["log10States"] > 10
    report = s.request("gamehub/analyze", {"uri": uri, "analyses": ["feasibility", "solve"]})
    assert report["feasibility"]["recommendations"][-1]["code"] == "approximate"
    assert "información imperfecta" in report["errors"]["solve"]
    node = s.request("gamehub/sim.tree", {"session": sid, "index": 1, "path": [0]})
    assert node["path"] == [0] and node["children"]
