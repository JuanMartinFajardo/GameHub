# SPDX-License-Identifier: Apache-2.0
"""Eventos: lo que ocurre en un paso, con lo que ve cada asiento ya resuelto."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gamehub.engine.env import PUBLIC


@dataclass(frozen=True, slots=True)
class Event:
    """`full` es la versión omnisciente; `seen[s]` lo que ve el asiento s y `public` lo que ve
    un espectador, que no ocupa ningún asiento (None = no lo ve)."""

    full: dict[str, Any]
    seen: tuple[dict[str, Any] | None, ...]
    public: dict[str, Any] | None

    def for_seat(self, seat: int | None) -> dict[str, Any] | None:
        """Lo que ve un asiento (`None` = vista omnisciente, `PUBLIC` = espectador)."""
        if seat is None:
            return self.full
        if seat == PUBLIC:
            return self.public
        return self.seen[seat]

    @staticmethod
    def shared(payload: dict[str, Any], n: int) -> Event:
        """Un evento que todos ven igual (también los espectadores)."""
        return Event(payload, (payload,) * n, payload)
