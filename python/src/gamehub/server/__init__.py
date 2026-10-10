# SPDX-License-Identifier: Apache-2.0
"""Servidor de partidas (Fase 3): salas, protocolo WebSocket, API REST, LAN y persistencia.

Semántica: docs/wiki/protocolo.md. Piezas: `room`/`match` (núcleo puro), `rooms` (registro),
`app` (transporte), `run` (uvicorn), `store` (memoria y SQLite), `catalog`, `lan`.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Puerto por defecto del servidor de partidas.
DEFAULT_PORT = 7420


def data_dir() -> Path:
    """Datos del usuario (base de datos del servidor, sesiones del cliente): `GAMEHUB_DATA` o
    `~/.local/share/gamehub`."""
    override = os.environ.get("GAMEHUB_DATA")
    return Path(override) if override else Path.home() / ".local" / "share" / "gamehub"


def default_db() -> Path:
    return data_dir() / "server.sqlite3"
