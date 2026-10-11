# SPDX-License-Identifier: Apache-2.0
"""Servidor de partidas en marcha hasta que se pide parar (Ctrl+C o SIGTERM): lo usan
`gamehub serve` y `gamehub host`."""

from __future__ import annotations

import asyncio
import contextlib
import signal
from collections.abc import AsyncIterator
from pathlib import Path

from gamehub.server.app import GameServer, create_app
from gamehub.server.rooms import Rooms
from gamehub.server.run import Server, start, stop


@contextlib.asynccontextmanager
async def running(
    rooms: Rooms,
    host: str,
    port: int,
    *,
    public_url: str | None = None,
    web: Path | None = None,
) -> AsyncIterator[tuple[GameServer, Server]]:
    """El servidor escuchando mientras dura el bloque (con la app web de `web`, si se da)."""
    game_server = GameServer(rooms, public_url=public_url, web=web)
    server, task = await start(create_app(game_server), host, port)
    try:
        yield game_server, server
    finally:
        await game_server.shutdown()
        await stop(server, task)


async def until_stopped(extra: asyncio.Event | None = None) -> None:
    """Espera a Ctrl+C, SIGTERM o, si se da, a que se active `extra`."""
    done = extra or asyncio.Event()
    loop = asyncio.get_running_loop()
    installed = []
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError, RuntimeError, ValueError):
            loop.add_signal_handler(sig, done.set)
            installed.append(sig)
    try:
        await done.wait()
    finally:
        for sig in installed:
            loop.remove_signal_handler(sig)
