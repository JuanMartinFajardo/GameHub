# SPDX-License-Identifier: Apache-2.0
"""Dónde guarda el servidor las partidas y sus replays.

- `MemoryStore`: en memoria (las últimas `limit` partidas terminadas).
- `SqliteStore`: en un archivo SQLite. Cada paso se guarda en cuanto se juega, así que si el
  servidor se cae a mitad de partida, al arrancar de nuevo esa partida se cierra como anulada
  (`aborted`) con su replay hasta el último paso, verificable igual que las demás.

Los dos implementan el `Recorder` de las salas, `replay(id)` (solo partidas terminadas: el replay
revela la semilla del servidor) y `matches()` (las más recientes primero).
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path
from typing import Any

from gamehub.engine import Game
from gamehub.engine.fairness import block, derive_seed
from gamehub.engine.replay import record, replay
from gamehub.server.match import Match
from gamehub.server.room import Room

SCHEMA_VERSION = 1


class MemoryStore:
    def __init__(self, limit: int = 1000) -> None:
        self.limit = limit
        self.replays: OrderedDict[str, dict[str, Any]] = OrderedDict()

    def match_started(self, room: Room, match: Match) -> None:
        pass

    def match_progress(self, room: Room, match: Match) -> None:
        pass

    def match_ended(self, room: Room, match: Match) -> None:
        self.replays[match.id] = match.replay(room.match_players)
        while len(self.replays) > self.limit:
            self.replays.popitem(last=False)

    def replay(self, match_id: str) -> dict[str, Any] | None:
        return self.replays.get(match_id)

    def matches(self, limit: int = 50) -> list[dict[str, Any]]:
        return [_summary(mid, data) for mid, data in reversed(self.replays.items())][:limit]

    def close(self) -> None:
        pass


_TABLES = """
CREATE TABLE IF NOT EXISTS games (
  rules_hash TEXT PRIMARY KEY,
  id TEXT NOT NULL,
  version TEXT NOT NULL,
  ir TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS matches (
  id TEXT PRIMARY KEY,
  room TEXT NOT NULL,
  number INTEGER NOT NULL,
  rules_hash TEXT NOT NULL REFERENCES games (rules_hash),
  num_players INTEGER NOT NULL,
  params TEXT NOT NULL,
  players TEXT NOT NULL,
  server_seed TEXT NOT NULL,
  client_seeds TEXT NOT NULL,
  started_at REAL NOT NULL,
  ended_at REAL,
  reason TEXT,
  replay TEXT
);
CREATE TABLE IF NOT EXISTS steps (
  match TEXT NOT NULL REFERENCES matches (id),
  idx INTEGER NOT NULL,
  step TEXT NOT NULL,
  PRIMARY KEY (match, idx)
);
CREATE INDEX IF NOT EXISTS matches_by_start ON matches (started_at);
"""


class SqliteStore:
    def __init__(self, path: Path | str, *, clock: Callable[[], float] = time.time) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode = WAL")
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(_TABLES)
        self.db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        self.clock = clock
        self.saved: dict[str, int] = {}
        self.recovered = self._recover()

    # --- Recorder -------------------------------------------------------------------------------

    def match_started(self, room: Room, match: Match) -> None:
        game = match.game
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO games (rules_hash, id, version, ir) VALUES (?, ?, ?, ?)",
                (game.rules_hash, game.id, game.version, json.dumps(game.ir, ensure_ascii=False)),
            )
            self.db.execute(
                "INSERT INTO matches (id, room, number, rules_hash, num_players, params, players,"
                " server_seed, client_seeds, started_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    match.id,
                    room.code,
                    match.number,
                    game.rules_hash,
                    match.n,
                    json.dumps(match.params, ensure_ascii=False),
                    json.dumps(room.match_players, ensure_ascii=False),
                    match.server_seed,
                    json.dumps(match.client_seeds, ensure_ascii=False),
                    self.clock(),
                ),
            )
        self.saved[match.id] = 0
        self.match_progress(room, match)

    def match_progress(self, room: Room, match: Match) -> None:
        start = self.saved.get(match.id, 0)
        steps = match.steps(start)
        if not steps:
            return
        with self.db:
            self.db.executemany(
                "INSERT INTO steps (match, idx, step) VALUES (?, ?, ?)",
                [(match.id, start + i, json.dumps(s)) for i, s in enumerate(steps)],
            )
        self.saved[match.id] = start + len(steps)

    def match_ended(self, room: Room, match: Match) -> None:
        self.match_progress(room, match)
        data = match.replay(room.match_players)
        reason = match.ending.reason if match.ending is not None else "aborted"
        with self.db:
            self.db.execute(
                "UPDATE matches SET ended_at = ?, reason = ?, replay = ? WHERE id = ?",
                (self.clock(), reason, json.dumps(data, ensure_ascii=False), match.id),
            )
        self.saved.pop(match.id, None)

    # --- consulta -------------------------------------------------------------------------------

    def replay(self, match_id: str) -> dict[str, Any] | None:
        row = self.db.execute(
            "SELECT replay FROM matches WHERE id = ? AND replay IS NOT NULL", (match_id,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def matches(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT id, replay FROM matches WHERE replay IS NOT NULL"
            " ORDER BY started_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_summary(mid, json.loads(text)) for mid, text in rows]

    def close(self) -> None:
        self.db.close()

    # --- recuperación ---------------------------------------------------------------------------

    def _recover(self) -> int:
        """Cierra como anuladas las partidas que quedaron a medias (el servidor se cayó)."""
        rows = self.db.execute(
            "SELECT m.id, m.num_players, m.params, m.players, m.server_seed, m.client_seeds,"
            " g.ir FROM matches m JOIN games g USING (rules_hash) WHERE m.ended_at IS NULL"
        ).fetchall()
        for mid, n, params, players, server_seed, client_seeds, ir in rows:
            game = Game(json.loads(ir))
            seeds = json.loads(client_seeds)
            steps = [
                json.loads(text)
                for (text,) in self.db.execute(
                    "SELECT step FROM steps WHERE match = ? ORDER BY idx", (mid,)
                )
            ]
            seed = derive_seed(server_seed, seeds)
            partial = {
                "format": "gamehub-replay/0.1",
                "game": {"id": game.id, "version": game.version, "rules_hash": game.rules_hash},
                "num_players": n,
                "params": json.loads(params),
                "seed": seed,
                "steps": steps,
            }
            state = replay(game, partial, verify=False)
            data = record(state, seed, game=game)
            data["players"] = json.loads(players)
            data["fairness"] = block(server_seed, seeds, reveal=True)
            ranking = state.ranking()
            if ranking is not None:  # llegó al final, pero no a guardarlo
                reason = "terminal"
                data["result"].update(reason=reason, ranking=list(ranking), forfeited=[])
            else:
                reason = "aborted"
                data["result"] = {"reason": reason, "ranking": [1] * n, "forfeited": []}
            with self.db:
                self.db.execute(
                    "UPDATE matches SET ended_at = ?, reason = ?, replay = ? WHERE id = ?",
                    (self.clock(), reason, json.dumps(data, ensure_ascii=False), mid),
                )
        return len(rows)


def _summary(match_id: str, data: dict[str, Any]) -> dict[str, Any]:
    result = data.get("result") or {}
    return {
        "id": match_id,
        "game": data["game"],
        "players": data.get("players", []),
        "reason": result.get("reason", "terminal"),
        "payoffs": result.get("payoffs"),
        "ranking": result.get("ranking"),
        "steps": len(data["steps"]),
    }
