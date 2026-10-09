# SPDX-License-Identifier: Apache-2.0
"""Eventos: lo que ocurre en un paso, con lo que ve cada asiento ya resuelto."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Event:
    """`full` es la versión omnisciente; `seen[s]` lo que ve el asiento s (None = no lo ve)."""

    full: dict[str, Any]
    seen: tuple[dict[str, Any] | None, ...]

    def for_seat(self, seat: int | None) -> dict[str, Any] | None:
        return self.full if seat is None else self.seen[seat]

    @staticmethod
    def public(payload: dict[str, Any], n: int) -> Event:
        return Event(payload, (payload,) * n)
