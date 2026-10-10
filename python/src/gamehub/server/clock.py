# SPDX-License-Identifier: Apache-2.0
"""Relojes y plazos de una partida.

- `none`: sin plazos.
- `move`: cada turno tiene `seconds` segundos.
- `match`: reloj de ajedrez: cada asiento tiene un tiempo total (`initial`) que corre mientras le
  toca; al jugar se le suma `increment`. Si un turno acaba sin que el asiento juegue (en una
  ventana `race` actuó otro), se le descuenta el tiempo igualmente, sin incremento.

Un turno empieza cuando el asiento pasa a poder actuar en una actualización nueva (ver
`Match.turns`) y acaba cuando juega o deja de poder hacerlo. El tiempo lo pone quien llama
(`now`, en segundos de un reloj monótono): el reloj no lee la hora.
"""

from __future__ import annotations

from typing import Any


class Clock:
    def __init__(self, spec: dict[str, Any], n: int) -> None:
        self.kind: str = spec["kind"]
        self.seconds = float(spec.get("seconds", 0))
        self.increment = float(spec.get("increment", 0))
        initial = float(spec.get("initial", 0))
        self.bank: list[float] = [initial] * n
        self.started: dict[int, float] = {}

    @property
    def enabled(self) -> bool:
        return self.kind != "none"

    def start(self, seat: int, now: float) -> None:
        if self.enabled:
            self.started[seat] = now

    def stop(self, seat: int, now: float, *, acted: bool) -> None:
        began = self.started.pop(seat, None)
        if began is None or self.kind != "match":
            return
        self.bank[seat] = max(0.0, self.bank[seat] - (now - began))
        if acted:
            self.bank[seat] += self.increment

    def deadline(self, seat: int) -> float | None:
        began = self.started.get(seat)
        if began is None:
            return None
        return began + (self.seconds if self.kind == "move" else self.bank[seat])

    def deadlines(self) -> dict[int, float]:
        return {s: d for s in self.started if (d := self.deadline(s)) is not None}

    def remaining(self, seat: int, now: float) -> float | None:
        """Lo que le queda al asiento: en su turno, hasta el plazo; con reloj de partida y fuera
        de su turno, su tiempo total; si no, `None`."""
        deadline = self.deadline(seat)
        if deadline is not None:
            return max(0.0, deadline - now)
        return self.bank[seat] if self.kind == "match" else None

    def snapshot(self, now: float) -> dict[str, Any] | None:
        """Datos `clocks` de una actualización (milisegundos), o `None` sin reloj."""
        if not self.enabled:
            return None
        remaining = [self.remaining(s, now) for s in range(len(self.bank))]
        return {
            "kind": self.kind,
            "remaining_ms": [None if r is None else round(r * 1000) for r in remaining],
            "running": sorted(self.started),
        }
