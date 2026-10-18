# SPDX-License-Identifier: Apache-2.0
"""Registro de salas de un servidor: creación con código, sesiones por token, límites y limpieza
de salas abandonadas. Lógica pura, como las salas: el tiempo lo pone quien llama."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from gamehub.engine import Game
from gamehub.server.catalog import Catalog
from gamehub.server.codes import new_code, normalize
from gamehub.server.room import Participant, Recorder, Room, RoomError, token_hash
from gamehub.server.settings import Settings
from gamehub.server.store import MemoryStore


class Store(Recorder, Protocol):
    def replay(self, match_id: str) -> dict[str, Any] | None: ...

    def game(self, rules_hash: str) -> dict[str, Any] | None: ...

    def matches(self, limit: int = 50) -> list[dict[str, Any]]: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class Limits:
    #: Salas abiertas a la vez.
    max_rooms: int = 1000
    #: Segundos que sobrevive una sala sin nadie conectado (en el lobby y en partida).
    idle_lobby: float = 30 * 60
    idle_running: float = 2 * 60 * 60
    #: Conexiones WebSocket a la vez.
    max_connections: int = 5000
    #: Mensajes por segundo de cada conexión (con ráfagas de `burst`).
    rate: float = 20.0
    burst: int = 60
    #: Tamaño máximo del cuerpo de una petición REST (una IR subida).
    max_body: int = 2 * 1024 * 1024


class Rooms:
    def __init__(
        self,
        catalog: Catalog | None = None,
        store: Store | None = None,
        *,
        allow_upload: bool = False,
        limits: Limits | None = None,
        name: str = "GameHub",
    ) -> None:
        self.catalog = catalog if catalog is not None else Catalog()
        self.store: Store = store or MemoryStore()
        self.allow_upload = allow_upload
        self.limits = limits or Limits()
        self.name = name
        self.rooms: dict[str, Room] = {}
        self.tokens: dict[str, tuple[str, str]] = {}

    # --- salas ----------------------------------------------------------------------------------

    def create(
        self,
        game: Game,
        *,
        now: float,
        players: int | None = None,
        params: dict[str, Any] | None = None,
        settings: dict[str, Any] | None = None,
        host_name: str | None = None,
    ) -> tuple[Room, str]:
        """Una sala nueva y el token del anfitrión (aún sin conectar ni sentar)."""
        if len(self.rooms) >= self.limits.max_rooms:
            raise RoomError("not_allowed", "el servidor no admite más salas ahora mismo")
        config = Settings(players or game.players[0]).patched(settings or {})
        room = Room(
            new_code(self.rooms),
            game,
            settings=config,
            params=params,
            now=now,
            recorder=self.store,
        )
        host, token = room.join(
            name=host_name or "Anfitrión", role="spectator", host=True, connected=False, now=now
        )
        self.rooms[room.code] = room
        self._remember(room, host, token)
        return room, token

    def get(self, code: str) -> Room | None:
        normal = normalize(code)
        return self.rooms.get(normal) if normal is not None else None

    def join(self, room: Room, *, now: float, **kw: Any) -> tuple[Participant, str]:
        p, token = room.join(now=now, **kw)
        self._remember(room, p, token)
        return p, token

    def session(self, token: str) -> tuple[Room, str] | None:
        """La sala y el participante de un token de sesión (si siguen existiendo)."""
        found = self.tokens.get(token_hash(token))
        if found is None:
            return None
        code, pid = found
        room = self.rooms.get(code)
        if room is None or pid not in room.participants:
            del self.tokens[token_hash(token)]
            return None
        return room, pid

    def listed(self) -> list[Room]:
        """Salas públicas abiertas."""
        return [r for r in self.rooms.values() if not r.settings.private and r.status != "closed"]

    def sweep(self, now: float) -> list[Room]:
        """Cierra las salas sin nadie conectado desde hace demasiado y olvida las cerradas.
        Devuelve las salas retiradas."""
        removed = []
        for room in list(self.rooms.values()):
            idle = self.limits.idle_running if room.running_match else self.limits.idle_lobby
            if room.connected_count() == 0 and now - room.touched >= idle:
                room.close(now)
            if room.status == "closed" and not room.outbox:
                removed.append(self.rooms.pop(room.code))
        if removed:
            gone = {r.code for r in removed}
            self.tokens = {h: v for h, v in self.tokens.items() if v[0] not in gone}
        return removed

    def close_all(self, now: float) -> None:
        for room in self.rooms.values():
            room.close(now)

    def _remember(self, room: Room, p: Participant, token: str) -> None:
        self.tokens[token_hash(token)] = (room.code, p.id)


class TokenBucket:
    """Limitador de tasa: `rate` fichas por segundo, hasta `burst` acumuladas."""

    def __init__(self, rate: float, burst: int, now: float) -> None:
        self.rate = rate
        self.burst = burst
        self.tokens = float(burst)
        self.updated = now

    def take(self, now: float) -> bool:
        self.tokens = min(self.burst, self.tokens + (now - self.updated) * self.rate)
        self.updated = now
        if self.tokens < 1:
            return False
        self.tokens -= 1
        return True
