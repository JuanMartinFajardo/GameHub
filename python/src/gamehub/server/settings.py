# SPDX-License-Identifier: Apache-2.0
"""Configuración de una sala (`RoomSettings` del protocolo) con sus valores por defecto."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Any

#: Bots que ejecuta el propio servidor: los del motor de referencia y los del núcleo C++ (F9; sin
#: el núcleo instalado, juegan al azar).
BOT_KINDS = ("random", "first", "greedy", "alphabeta", "mcts", "ismcts", "pimc")
ON_TIMEOUT = ("random", "pass", "bot", "forfeit")
SPECTATOR_VIEWS = ("public", "omniscient")


def _no_clock() -> dict[str, Any]:
    return {"kind": "none"}


@dataclass(frozen=True)
class Settings:
    players: int
    clock: dict[str, Any] = field(default_factory=_no_clock)
    on_timeout: str = "random"
    spectators: bool = True
    spectator_view: str = "public"
    spectator_delay: float = 0.0
    bot_delay: float = 0.5
    private: bool = False

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    def patched(self, patch: dict[str, Any]) -> Settings:
        """Con los campos de un `SettingsPatch` (ya validado por el esquema)."""
        return replace(self, **patch)
