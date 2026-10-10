# SPDX-License-Identifier: Apache-2.0
"""Banco de pruebas de salas: una `Room` con reloj simulado y buzones por participante.

Todo mensaje que sale de la sala se valida contra el esquema del protocolo.
"""

from __future__ import annotations

from collections import defaultdict
from functools import cache
from pathlib import Path
from typing import Any

from gamehub.engine import Game, load_game
from gamehub.ir.spec import examples_dir
from gamehub.lang.compiler import load_nomos
from gamehub.protocol import check_server
from gamehub.server.room import Participant, Room
from gamehub.server.settings import Settings

ROOT = Path(__file__).resolve().parents[2]


@cache
def game(name: str) -> Game:
    """Un juego de los ejemplos de la IR o, si no, del catálogo en Nomos."""
    path = examples_dir() / f"{name}.ir.json"
    if path.exists():
        return load_game(path)
    return load_nomos(ROOT / "games" / name / f"{name}.game")


class Harness:
    def __init__(
        self, name: str, players: int = 2, *, params: dict[str, Any] | None = None, **settings: Any
    ) -> None:
        self.now = 0.0
        settings.setdefault("bot_delay", 0.0)
        self.room = Room(
            "K7FQ2P",
            game(name),
            settings=Settings(players, **settings),
            params=params,
            now=self.now,
        )
        self.inbox: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.closed: set[str] = set()
        self.tokens: dict[str, str] = {}

    # --- entrega --------------------------------------------------------------------------------

    def deliver(self) -> None:
        for out in self.room.drain(self.now):
            problems = check_server(out.msg)
            assert problems == [], (out.msg["type"], problems)
            self.inbox[out.to].append(out.msg)
            if out.close:
                self.closed.add(out.to)

    def advance(self, seconds: float) -> None:
        self.now += seconds
        self.room.tick(self.now)
        self.deliver()

    # --- acciones de los participantes ----------------------------------------------------------

    def join(self, name: str, role: str = "player", **kw: Any) -> Participant:
        p, token = self.room.join(name=name, role=role, now=self.now, **kw)
        self.tokens[p.id] = token
        self.deliver()
        return p

    def seat(self, name: str, **kw: Any) -> Participant:
        """Se une como jugador y se declara listo."""
        p = self.join(name, **kw)
        self.ready(p)
        return p

    def ready(self, p: Participant, seed: str | None = None) -> None:
        self.room.ready(p.id, True, seed, self.now)
        self.deliver()

    def act(
        self, p: Participant, name: str, seq: int | None = None, re: str | None = None, **args: Any
    ) -> None:
        seq = self.seq(p) if seq is None else seq
        self.room.act(p.id, seq, {"name": name, "args": args}, self.now, re=re)
        self.deliver()

    def act_json(self, p: Participant, action: dict[str, Any], seq: int | None = None) -> None:
        seq = self.seq(p) if seq is None else seq
        self.room.act(p.id, seq, action, self.now)
        self.deliver()

    # --- consulta de los buzones ----------------------------------------------------------------

    def messages(self, p: Participant, kind: str | None = None) -> list[dict[str, Any]]:
        return [m for m in self.inbox[p.id] if kind is None or m["type"] == kind]

    def last(self, p: Participant, kind: str) -> dict[str, Any]:
        found = self.messages(p, kind)
        assert found, f"{p.name} no ha recibido ningún '{kind}'"
        return found[-1]["data"]

    def seq(self, p: Participant) -> int:
        return self.last(p, "update")["seq"]

    def legal(self, p: Participant) -> list[dict[str, Any]]:
        legal = self.last(p, "update").get("legal")
        assert legal is not None and legal["kind"] == "enumerated", legal
        return legal["actions"]

    def clear(self) -> None:
        self.inbox.clear()
