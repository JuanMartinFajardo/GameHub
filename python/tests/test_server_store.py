# SPDX-License-Identifier: Apache-2.0
"""Persistencia de partidas: SQLite guarda cada paso, los replays terminados y recupera las
partidas que quedaron a medias si el servidor se cae."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from gamehub.engine.fairness import verify
from gamehub.server.store import MemoryStore, SqliteStore
from server_harness import Harness, game


def harness(store: SqliteStore | MemoryStore, name: str = "nim") -> Harness:
    h = Harness(name)
    h.room.recorder = store
    return h


def test_sqlite_keeps_finished_matches(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "server.sqlite3", clock=lambda: 1000.0)
    h = harness(store, "tictactoe")
    x, o = h.seat("Ana"), h.seat("Luis")
    for p, cell in [(x, [0, 0]), (o, [1, 1]), (x, [0, 1]), (o, [2, 2]), (x, [0, 2])]:
        h.act(p, "place", c=cell)
    match_id = h.last(x, "match_end")["replay"]
    data = store.replay(match_id)
    assert data is not None and data["players"][1] == {"name": "Luis", "kind": "human"}
    assert verify(game("tictactoe"), data).payoffs == (1, -1)
    [summary] = store.matches()
    assert summary["id"] == match_id and summary["reason"] == "terminal"
    assert summary["payoffs"] == [1, -1] and summary["steps"] == 5
    store.close()
    # Otra instancia sobre el mismo archivo lo sigue viendo.
    again = SqliteStore(tmp_path / "server.sqlite3")
    assert again.replay(match_id) == data and again.recovered == 0
    again.close()


def test_running_matches_are_not_public_until_they_end(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "s.sqlite3")
    h = harness(store)
    a, b = h.seat("Ana"), h.seat("Luis")
    h.act(a, "take", heap=0, count=1)
    match_id = h.last(b, "match_start")["match"]["id"]
    assert store.replay(match_id) is None and store.matches() == []
    rows = store.db.execute("SELECT idx FROM steps WHERE match = ?", (match_id,)).fetchall()
    assert [r[0] for r in rows] == [0]


def test_crashed_matches_are_recovered_as_aborted(tmp_path: Path) -> None:
    path = tmp_path / "crash.sqlite3"
    store = SqliteStore(path)
    h = harness(store, "kuhn-poker")
    a, b = h.seat("Ana"), h.seat("Luis")
    h.act(a, "bet")
    match_id = h.last(b, "match_start")["match"]["id"]
    # El proceso muere sin cerrar la partida: al abrir de nuevo, se cierra como anulada.
    store.db.close()
    recovered = SqliteStore(path)
    assert recovered.recovered == 1
    data = recovered.replay(match_id)
    assert data is not None and data["result"]["reason"] == "aborted"
    assert len(data["steps"]) == 2  # el reparto y la apuesta
    final = verify(game("kuhn-poker"), data)
    assert not final.is_terminal
    reason = recovered.db.execute("SELECT reason FROM matches WHERE id = ?", (match_id,))
    assert reason.fetchone() == ("aborted",)


def test_schema_version(tmp_path: Path) -> None:
    SqliteStore(tmp_path / "v.sqlite3").close()
    db = sqlite3.connect(tmp_path / "v.sqlite3")
    assert db.execute("PRAGMA user_version").fetchone() == (1,)


def test_memory_store_is_bounded() -> None:
    store = MemoryStore(limit=2)
    ids = []
    for _ in range(3):
        h = harness(store)
        a, b = h.seat("Ana"), h.seat("Luis")
        h.room.resign(b.id, h.now)
        h.deliver()
        ids.append(h.last(a, "match_end")["replay"])
    assert store.replay(ids[0]) is None and store.replay(ids[2]) is not None
    assert [m["id"] for m in store.matches()] == [ids[2], ids[1]]


def test_serve_command(tmp_path: Path) -> None:
    """`gamehub serve` arranca, responde y se para con Ctrl+C (SIGINT)."""
    import json
    import signal
    import subprocess
    import sys
    import urllib.request

    root = Path(__file__).resolve().parents[2]
    db = tmp_path / "serve.sqlite3"
    argv = ["serve", str(root / "games" / "nim"), "--host", "127.0.0.1", "--port", "0"]
    argv += ["--db", str(db)]
    code = f"import sys; from gamehub.cli import main; sys.exit(main({argv!r}))"
    proc = subprocess.Popen(
        [sys.executable, "-c", code], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    try:
        assert proc.stdout is not None
        banner = proc.stdout.readline()
        assert banner.startswith("Servidor de partidas en http://127.0.0.1:"), banner
        url = banner.split()[-1]
        with urllib.request.urlopen(url + "/api/v1/info", timeout=5) as response:
            info = json.load(response)
        assert [g["id"] for g in info["games"]] == ["nim"]
    finally:
        proc.send_signal(signal.SIGINT)
        out, _ = proc.communicate(timeout=10)
    assert proc.returncode == 0 and "Servidor parado." in out
    assert db.exists()
