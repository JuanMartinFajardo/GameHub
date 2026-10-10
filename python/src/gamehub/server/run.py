# SPDX-License-Identifier: Apache-2.0
"""Arrancar el servidor de partidas con uvicorn: en el bucle de eventos actual (`serve`, para
`gamehub host` y `gamehub serve`) o en un hilo propio (`ServerThread`, para tests y scripts)."""

from __future__ import annotations

import asyncio
import contextlib
import threading
from collections.abc import Iterator

import uvicorn
from starlette.applications import Starlette

from gamehub.protocol import MAX_MESSAGE_BYTES
from gamehub.server import DEFAULT_PORT as DEFAULT_PORT
from gamehub.server.app import GameServer, create_app
from gamehub.server.rooms import Rooms


def config(app: Starlette, host: str, port: int) -> uvicorn.Config:
    return uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
        ws_max_size=MAX_MESSAGE_BYTES + 1024,
        ws_ping_interval=15.0,
        ws_ping_timeout=15.0,
        lifespan="on",
    )


class Server(uvicorn.Server):
    """uvicorn sin capturar las señales: quien lo arranca decide cómo se para."""

    @contextlib.contextmanager
    def capture_signals(self) -> Iterator[None]:
        yield

    @property
    def port(self) -> int:
        return self.servers[0].sockets[0].getsockname()[1]


async def start(app: Starlette, host: str, port: int) -> tuple[Server, asyncio.Task[None]]:
    """Arranca el servidor en el bucle actual y espera a que escuche."""
    server = Server(config(app, host, port))
    task = asyncio.create_task(server.serve())
    while not server.started:
        if task.done():
            task.result()  # propaga el error (p. ej. el puerto está ocupado)
            raise OSError("el servidor no ha arrancado")
        await asyncio.sleep(0.01)
    return server, task


async def stop(server: Server, task: asyncio.Task[None]) -> None:
    server.should_exit = True
    await task


class ServerThread:
    """Un servidor de partidas en un hilo propio, en 127.0.0.1 y un puerto libre."""

    def __init__(self, rooms: Rooms, *, host: str = "127.0.0.1", port: int = 0) -> None:
        self.game_server = GameServer(rooms)
        self.server = Server(config(create_app(self.game_server), host, port))
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.host = host

    def __enter__(self) -> ServerThread:
        self.thread.start()
        for _ in range(500):
            if self.server.started:
                return self
            if not self.thread.is_alive():
                break
            threading.Event().wait(0.01)
        raise OSError("el servidor de partidas no ha arrancado")

    def __exit__(self, *exc: object) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)

    @property
    def port(self) -> int:
        return self.server.port

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def ws_url(self) -> str:
        return f"ws://{self.host}:{self.port}/ws"
