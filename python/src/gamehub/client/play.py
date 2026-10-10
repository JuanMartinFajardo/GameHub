# SPDX-License-Identifier: Apache-2.0
"""Jugar en red desde la terminal: hospedar una sala (`gamehub host`), unirse a una
(`gamehub join`) y ver las salas de la LAN (`gamehub rooms`)."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from gamehub.client.connection import Client, ClientError, fetch_json, target
from gamehub.client.terminal import Sessions, Terminal
from gamehub.engine import Game
from gamehub.server import DEFAULT_PORT
from gamehub.server.catalog import Catalog
from gamehub.server.codes import display, normalize
from gamehub.server.lan import Advertiser, base_url, discover, qr_text
from gamehub.server.rooms import Rooms, Store
from gamehub.server.serve import running, until_stopped

Out = Callable[[str], None]


async def find_room(code: str, *, timeout: float = 2.0) -> str | None:
    """El servidor que tiene la sala: este equipo o uno de la LAN (mDNS)."""
    candidates = [f"http://127.0.0.1:{DEFAULT_PORT}"]
    candidates += [found.url for found in await discover(timeout)]
    for url in candidates:
        with contextlib.suppress(ClientError):
            await fetch_json(f"{url}/api/v1/rooms/{code}")
            return url
    return None


async def resolve(room: str, server: str | None, out: Out) -> tuple[str, str]:
    """Servidor y código de lo que escribe quien se une; si solo da el código, lo busca."""
    if server is not None or "/" in room or ":" in room:
        return target(room, server)
    code = normalize(room)
    if code is None:
        raise ClientError("unknown_room", f"código de sala no válido: {room}")
    out(f"Buscando la sala {display(code)} en esta red…")
    found = await find_room(code)
    if found is None:
        raise ClientError(
            "unknown_room",
            f"no encuentro la sala {display(code)}: usa el enlace que te pasaron "
            "(gamehub join http://IP:7420/r/CÓDIGO) o --server",
        )
    return found, code


async def join(
    room: str,
    *,
    server: str | None = None,
    player: str,
    role: str = "player",
    seat: int | None = None,
    lines: AsyncIterator[str],
    out: Out = print,
    sessions: Sessions | None = None,
    on_terminal: Callable[[Terminal], None] | None = None,
) -> int:
    http, code = await resolve(room, server, out)
    sessions = sessions or Sessions()
    token = sessions.get(http, code)
    client = Client(
        http, name=player, legal_limit=20_000, token=token, on_status=_status_printer(out)
    )
    welcome = await client.connect()
    session = welcome.get("session")
    if session is not None and session["room"] == code:
        out(f"Has vuelto a la sala {display(code)}.")
    else:
        await client.join(code, role=role, seat=seat)
    terminal = Terminal(client, out=out, sessions=sessions)
    if on_terminal is not None:
        on_terminal(terminal)
    try:
        return await terminal.run(lines)
    finally:
        await client.close()


async def host(
    game: Game,
    *,
    player: str,
    lines: AsyncIterator[str] | None,
    out: Out = print,
    store: Store | None = None,
    listen: str = "0.0.0.0",
    port: int = DEFAULT_PORT,
    players: int | None = None,
    params: dict[str, Any] | None = None,
    settings: dict[str, Any] | None = None,
    bots: int = 0,
    mdns: bool = True,
    qr: bool = True,
    ready: asyncio.Event | None = None,
    info: dict[str, Any] | None = None,
    on_terminal: Callable[[Terminal], None] | None = None,
    web: Path | None = None,
    open_browser: bool = False,
) -> int:
    """Abre un servidor con una sala del juego y, si hay `lines`, juega en ella desde la
    terminal; si no, la sirve hasta Ctrl+C. Con `web`, el enlace de la sala abre la app web
    para jugar en el navegador. `ready` se activa (y `info` recibe la URL, el código y el
    puerto) cuando la sala ya acepta jugadores."""
    rooms = Rooms(Catalog([game]), store, name=f"GameHub de {player}")
    async with running(rooms, listen, port, web=web) as (game_server, server):
        now = asyncio.get_running_loop().time()
        room, token = rooms.create(
            game, now=now, players=players, params=params, settings=settings, host_name=player
        )
        found = rooms.session(token)
        assert found is not None
        host_id = found[1]
        for seat in range(len(room.seats) - bots, len(room.seats)):
            room.set_seat(host_id, max(seat, 0), "bot", now)
        game_server.flush(room)
        url = base_url(listen, server.port)
        link = f"{url}/r/{room.code}"
        _banner(out, game, room.display_code, link, qr=qr, web=web is not None)
        if open_browser and web is not None:
            import webbrowser

            webbrowser.open(link)
        if info is not None:
            info.update(url=url, code=room.code, port=server.port, token=token)
        advertiser = Advertiser(rooms.name, server.port) if mdns else None
        if advertiser is not None and not await advertiser.start():
            out("  (mDNS no disponible: comparte el enlace para que se unan)")
        if ready is not None:
            ready.set()
        try:
            if lines is None:
                out("Sirviendo la sala; Ctrl+C para cerrarla.")
                await until_stopped()
                return 0
            local = f"http://127.0.0.1:{server.port}"
            client = Client(local, name=player, legal_limit=20_000, token=token)
            await client.connect()
            await client.sit()
            terminal = Terminal(client, out=out, host_mode=True)
            if on_terminal is not None:
                on_terminal(terminal)
            try:
                return await terminal.run(lines)
            finally:
                await client.close()
        finally:
            if advertiser is not None:
                await advertiser.stop()
            await game_server.shutdown()


async def list_rooms(*, server: str | None = None, timeout: float = 2.0, out: Out = print) -> int:
    """Las salas abiertas de un servidor o de todos los de la LAN."""
    if server is not None:
        servers = [(server, server)]
    else:
        found = await discover(timeout)
        servers = [(f.name, f.url) for f in found]
        with contextlib.suppress(ClientError):
            local = f"http://127.0.0.1:{DEFAULT_PORT}"
            info = await fetch_json(f"{local}/api/v1/info")
            if all(url != local for _, url in servers):
                servers.insert(0, (info["name"] + " (este equipo)", local))
    if not servers:
        out("No hay servidores de partidas a la vista en esta red.")
        return 0
    for name, url in servers:
        try:
            listed = (await fetch_json(f"{url}/api/v1/rooms"))["rooms"]
        except ClientError as exc:
            out(f"{name} · {url}: {exc.message}")
            continue
        out(f"{name} · {url}")
        if not listed:
            out("  (ninguna sala abierta)")
        for room in listed:
            free = sum(1 for s in room["seats"] if s["kind"] in ("open", "reserved"))
            state = "jugando" if room["status"] == "running" else f"{free} asiento(s) libre(s)"
            out(f"  {display(room['code'])} · {room['game']['title']} · {state}")
    return 0


def _banner(out: Out, game: Game, code: str, link: str, *, qr: bool, web: bool = False) -> None:
    out(f"GameHub · {game.title}")
    out(f"  Sala:   {code}")
    out(f"  Enlace: {link}")
    if qr:
        out(qr_text(link).rstrip("\n"))
    if web:
        out("  Para jugar en el navegador (también en el móvil, con el QR): abre el enlace")
    out(f"  Para unirse desde otro equipo de esta red: gamehub join {code}")
    out(f"  (o con el enlace: gamehub join {link})")


def _status_printer(out: Out) -> Callable[[str], None]:
    def show(status: str) -> None:
        if status == "reconnecting":
            out("  Se ha perdido la conexión; reconectando…")

    return show
