# SPDX-License-Identifier: Apache-2.0
"""Transporte del servidor de partidas: API REST y WebSocket (Starlette sobre uvicorn).

Capa fina sobre `Rooms`/`Room`: lee y valida los mensajes, llama a la sala, entrega lo que deja en
su `outbox` a las conexiones y programa un temporizador por sala para su `next_wakeup` (bots,
plazos y retardo de los espectadores). Todo ocurre en el bucle de eventos: las salas no necesitan
cerrojos. Cada conexión tiene una cola de salida propia, así que un cliente lento no frena al
resto (si su cola se llena, se le desconecta y puede reconectar).

Rutas: `GET /api/v1/info`, `GET|POST /api/v1/rooms`, `GET /api/v1/rooms/{code}`,
`GET /api/v1/rooms/{code}/ir`, `GET /api/v1/games/{id}`, `GET /api/v1/matches`,
`GET /api/v1/replays/{id}`, `GET /r/{code}` (página de la sala) y `WS /ws`.
"""

from __future__ import annotations

import asyncio
import contextlib
import html
import json
import time
from collections.abc import AsyncIterator
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect, WebSocketState

from gamehub import __version__
from gamehub.engine import Game, RuleError
from gamehub.protocol import VERSION, ProtocolError, message, parse_client, problems
from gamehub.server.codes import display
from gamehub.server.room import Room, RoomError
from gamehub.server.rooms import Rooms, TokenBucket

#: Segundos para enviar `hello` tras conectar.
HELLO_TIMEOUT = 10.0
#: Mensajes pendientes por conexión antes de darla por atascada.
QUEUE_SIZE = 1000
#: Avisos por exceso de tasa antes de cerrar la conexión.
MAX_VIOLATIONS = 20
#: Cada cuánto se retiran las salas abandonadas.
SWEEP_EVERY = 60.0


class Connection:
    """Una conexión WebSocket y la sesión (sala y participante) que tiene asociada."""

    def __init__(self, ws: WebSocket, bucket: TokenBucket) -> None:
        self.ws = ws
        self.bucket = bucket
        self.queue: asyncio.Queue[tuple[dict[str, Any] | None, bool]] = asyncio.Queue(QUEUE_SIZE)
        self.hello = False
        self.client: dict[str, Any] = {"name": "?", "kind": "human"}
        self.legal_limit = 256
        self.room: str | None = None
        self.pid: str | None = None
        self.violations = 0
        self.closing = False

    def send(self, msg: dict[str, Any], *, close: bool = False) -> None:
        if self.closing:
            return
        try:
            self.queue.put_nowait((msg, close))
        except asyncio.QueueFull:
            self.close()
            return
        if close:
            self.closing = True

    def close(self) -> None:
        if not self.closing:
            self.closing = True
            with contextlib.suppress(asyncio.QueueFull):
                self.queue.put_nowait((None, True))

    async def writer(self) -> None:
        while True:
            msg, close = await self.queue.get()
            if msg is not None and self.ws.client_state is WebSocketState.CONNECTED:
                await self.ws.send_text(json.dumps(msg, ensure_ascii=False))
            if close:
                with contextlib.suppress(Exception):
                    await self.ws.close()
                return


class GameServer:
    """El estado del servidor en marcha: salas, conexiones y temporizadores."""

    def __init__(self, rooms: Rooms, *, public_url: str | None = None) -> None:
        self.rooms = rooms
        self.public_url = public_url
        self.connections: dict[tuple[str, str], Connection] = {}
        self.open_connections = 0
        self.timers: dict[str, asyncio.TimerHandle] = {}
        self._sweeper: asyncio.Task[None] | None = None

    @staticmethod
    def now() -> float:
        return asyncio.get_running_loop().time()

    # --- ciclo de vida --------------------------------------------------------------------------

    @contextlib.asynccontextmanager
    async def lifespan(self, app: Starlette) -> AsyncIterator[None]:
        self._sweeper = asyncio.create_task(self._sweep_loop())
        try:
            yield
        finally:
            self._sweeper.cancel()
            now = self.now()
            for room in list(self.rooms.rooms.values()):
                room.close(now)
                self.flush(room)
            for handle in self.timers.values():
                handle.cancel()

    async def shutdown(self, grace: float = 1.0) -> None:
        """Cierra todas las salas (los clientes reciben el fin) y espera un poco a que salgan
        los mensajes antes de parar el servidor."""
        now = self.now()
        for room in list(self.rooms.rooms.values()):
            room.close(now)
            self.flush(room)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + grace
        while loop.time() < deadline and any(
            not c.queue.empty() for c in self.connections.values()
        ):
            await asyncio.sleep(0.02)

    async def _sweep_loop(self) -> None:
        while True:
            await asyncio.sleep(SWEEP_EVERY)
            for room in self.rooms.sweep(self.now()):
                handle = self.timers.pop(room.code, None)
                if handle is not None:
                    handle.cancel()

    # --- entrega y temporizadores ---------------------------------------------------------------

    def flush(self, room: Room) -> None:
        """Entrega lo que la sala ya puede enviar y reprograma su temporizador."""
        for out in room.drain(self.now()):
            conn = self.connections.get((room.code, out.to))
            if conn is not None:
                conn.send(out.msg, close=out.close)
                if out.close:
                    self._unbind(conn)
        self._schedule(room)

    def _schedule(self, room: Room) -> None:
        handle = self.timers.pop(room.code, None)
        if handle is not None:
            handle.cancel()
        wake = room.next_wakeup()
        if wake is not None:
            loop = asyncio.get_running_loop()
            self.timers[room.code] = loop.call_at(wake, self._wake, room.code)

    def _wake(self, code: str) -> None:
        self.timers.pop(code, None)
        room = self.rooms.rooms.get(code)
        if room is not None:
            room.tick(self.now())
            self.flush(room)

    # --- conexiones -----------------------------------------------------------------------------

    def _bind(self, conn: Connection, room: Room, pid: str) -> None:
        old = self.connections.get((room.code, pid))
        if old is not None and old is not conn:
            text = "tu sesión se ha abierto desde otra conexión"
            old.send(message("error", {"code": "replaced", "message": text}), close=True)
            self._unbind(old)
        conn.room, conn.pid = room.code, pid
        self.connections[(room.code, pid)] = conn

    def _unbind(self, conn: Connection) -> None:
        if conn.room is not None and conn.pid is not None:
            key = (conn.room, conn.pid)
            if self.connections.get(key) is conn:
                del self.connections[key]
        conn.room = conn.pid = None

    def disconnected(self, conn: Connection) -> None:
        room = self.rooms.rooms.get(conn.room or "")
        pid = conn.pid
        if room is not None and pid is not None and self.connections.get((room.code, pid)) is conn:
            self._unbind(conn)
            room.disconnect(pid, self.now())
            self.flush(room)

    # --- mensajes -------------------------------------------------------------------------------

    def handle(self, conn: Connection, raw: str | bytes) -> None:
        now = self.now()
        if not conn.bucket.take(now):
            conn.violations += 1
            if conn.violations > MAX_VIOLATIONS:
                conn.close()
            else:
                conn.send(_error("rate_limited", "demasiados mensajes: espera un momento"))
            return
        try:
            kind, data, mid = parse_client(raw)
        except ProtocolError as exc:
            conn.send(_error(exc.code, exc.message, exc.id))
            return
        if kind == "ping":
            pong: dict[str, Any] = {"server_time": time.time()}
            if "t" in data:
                pong["t"] = data["t"]
            conn.send(message("pong", pong, mid))
            return
        if kind == "hello":
            self._hello(conn, data, mid, now)
            return
        if not conn.hello:
            conn.send(_error("bad_message", "el primer mensaje debe ser 'hello'", mid))
            return
        if kind == "join":
            self._join(conn, data, mid, now)
            return
        room = self.rooms.rooms.get(conn.room or "")
        pid = conn.pid
        if room is None or pid is None:
            conn.send(_error("not_allowed", "primero entra en una sala ('join')", mid))
            return
        try:
            self._dispatch(room, pid, kind, data, mid, now)
            if kind == "leave":
                self._unbind(conn)
        except RoomError as exc:
            conn.send(_error(exc.code, exc.message, mid))
        finally:
            self.flush(room)

    def _hello(self, conn: Connection, data: dict[str, Any], mid: str | None, now: float) -> None:
        if conn.hello:
            conn.send(_error("bad_message", "'hello' solo se envía una vez", mid))
            return
        conn.hello = True
        conn.client = data["client"]
        conn.legal_limit = data.get("legal_limit", conn.legal_limit)
        server = {"name": self.rooms.name, "version": __version__}
        token = data.get("token")
        found = self.rooms.session(token) if token is not None else None
        if found is None:
            if token is not None:
                text = "sesión desconocida o caducada: vuelve a entrar en la sala"
                conn.send(_error("invalid_token", text, mid))
            conn.send(message("welcome", {"server": server}, mid))
            return
        room, pid = found
        self._bind(conn, room, pid)
        room.participants[pid].legal_limit = conn.legal_limit
        room.resume(pid, now, data.get("resume"), re=mid)
        self.flush(room)

    def _join(self, conn: Connection, data: dict[str, Any], mid: str | None, now: float) -> None:
        if conn.pid is not None:
            conn.send(_error("not_allowed", "ya estás en una sala", mid))
            return
        room = self.rooms.get(data["room"])
        if room is None:
            conn.send(_error("unknown_room", f"no hay ninguna sala {data['room']}", mid))
            return
        try:
            p, _ = self.rooms.join(
                room,
                now=now,
                name=data["name"],
                role=data["role"],
                seat=data.get("seat"),
                kind=conn.client.get("kind", "human"),
                legal_limit=conn.legal_limit,
                re=mid,
            )
        except RoomError as exc:
            conn.send(_error(exc.code, exc.message, mid))
            return
        self._bind(conn, room, p.id)
        self.flush(room)

    @staticmethod
    def _dispatch(
        room: Room, pid: str, kind: str, data: dict[str, Any], mid: str | None, now: float
    ) -> None:
        match kind:
            case "sit":
                room.sit(pid, data.get("seat"), now)
            case "stand":
                room.stand(pid, now)
            case "leave":
                room.leave(pid, now)
            case "ready":
                room.ready(pid, data["ready"], data.get("seed"), now)
            case "act":
                room.act(pid, data["seq"], data["action"], now, re=mid)
            case "query_actions":
                room.query_actions(
                    pid, data["seq"], data.get("name"), data.get("args"), now, re=mid
                )
            case "resign":
                room.resign(pid, now)
            case "chat":
                room.chat(pid, data["text"], now)
            case "resync":
                room.resync(pid, now)
            case "configure":
                room.configure(
                    pid,
                    now,
                    players=data.get("players"),
                    params=data.get("params"),
                    settings=data.get("settings"),
                )
            case "set_seat":
                room.set_seat(
                    pid, data["seat"], data["kind"], now, name=data.get("name"), bot=data.get("bot")
                )
            case "kick":
                room.kick(pid, data["participant"], now)
            case _:
                raise RoomError("bad_message", f"mensaje no admitido aquí: {kind}")

    # --- WebSocket ------------------------------------------------------------------------------

    async def websocket(self, ws: WebSocket) -> None:
        if self.open_connections >= self.rooms.limits.max_connections:
            await ws.close(code=1013)  # "try again later"
            return
        await ws.accept()
        self.open_connections += 1
        limits = self.rooms.limits
        conn = Connection(ws, TokenBucket(limits.rate, limits.burst, self.now()))
        writer = asyncio.create_task(conn.writer())
        try:
            while not conn.closing:
                timeout = None if conn.hello else HELLO_TIMEOUT
                try:
                    event = await asyncio.wait_for(ws.receive(), timeout)
                except TimeoutError:
                    conn.send(_error("bad_message", "no ha llegado 'hello' a tiempo"), close=True)
                    break
                if event["type"] == "websocket.disconnect":
                    break
                raw = event.get("text")
                if raw is None:
                    raw = event.get("bytes") or b""
                self.handle(conn, raw)
        except WebSocketDisconnect:
            pass
        finally:
            self.open_connections -= 1
            self.disconnected(conn)
            conn.close()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(writer, 5.0)
            writer.cancel()

    # --- REST -----------------------------------------------------------------------------------

    def url(self, request: Request, path: str) -> str:
        base = self.public_url or str(request.base_url).rstrip("/")
        return f"{base}{path}"

    async def info(self, request: Request) -> Response:
        return JSONResponse(
            {
                "name": self.rooms.name,
                "version": __version__,
                "protocol": VERSION,
                "upload": self.rooms.allow_upload,
                "games": self.rooms.catalog.info(),
                "rooms": len(self.rooms.rooms),
            }
        )

    async def list_rooms(self, request: Request) -> Response:
        return JSONResponse({"rooms": [r.info() for r in self.rooms.listed()]})

    async def create_room(self, request: Request) -> Response:
        body = await request.body()
        if len(body) > self.rooms.limits.max_body:
            return _api_error(413, "bad_message", "petición demasiado grande")
        try:
            data = json.loads(body or b"{}")
        except ValueError:
            return _api_error(400, "bad_message", "el cuerpo no es JSON")
        found = problems("CreateRoom", data)
        if found:
            return _api_error(400, "bad_message", "; ".join(found[:3]))
        game = self._game_for(data)
        if isinstance(game, Response):
            return game
        try:
            room, token = self.rooms.create(
                game,
                now=self.now(),
                players=data.get("players"),
                params=data.get("params"),
                settings=data.get("settings"),
                host_name=data.get("name"),
            )
        except RoomError as exc:
            status = 503 if exc.code == "not_allowed" else 400
            return _api_error(status, exc.code, exc.message)
        url = self.url(request, f"/r/{room.code}")
        return JSONResponse(
            {"code": room.code, "token": token, "url": url, "room": room.info()}, status_code=201
        )

    def _game_for(self, data: dict[str, Any]) -> Game | Response:
        if ("game" in data) == ("ir" in data):
            return _api_error(400, "bad_message", "indica 'game' (del catálogo) o 'ir', no ambos")
        if "game" in data:
            game = self.rooms.catalog.get(data["game"])
            if game is None:
                return _api_error(
                    404, "unknown_room", f"el servidor no tiene el juego {data['game']}"
                )
            return game
        if not self.rooms.allow_upload:
            return _api_error(403, "not_allowed", "este servidor no admite subir juegos")
        try:
            return Game(data["ir"])
        except RuleError as exc:
            return _api_error(400, "bad_message", str(exc))

    async def room_info(self, request: Request) -> Response:
        room = self.rooms.get(request.path_params["code"])
        if room is None:
            return _api_error(404, "unknown_room", "no existe esa sala")
        return JSONResponse(room.info())

    async def room_ir(self, request: Request) -> Response:
        room = self.rooms.get(request.path_params["code"])
        if room is None:
            return _api_error(404, "unknown_room", "no existe esa sala")
        return JSONResponse(room.game.ir)

    async def game_ir(self, request: Request) -> Response:
        game = self.rooms.catalog.get(request.path_params["id"])
        if game is None:
            return _api_error(404, "unknown_room", "el servidor no tiene ese juego")
        return JSONResponse(game.ir)

    async def matches(self, request: Request) -> Response:
        return JSONResponse({"matches": self.rooms.store.matches()})

    async def replay(self, request: Request) -> Response:
        data = self.rooms.store.replay(request.path_params["id"])
        if data is None:
            return _api_error(404, "unknown_room", "no hay ninguna partida terminada con ese id")
        return JSONResponse(data)

    async def room_page(self, request: Request) -> Response:
        room = self.rooms.get(request.path_params["code"])
        if "application/json" in request.headers.get("accept", ""):
            if room is None:
                return _api_error(404, "unknown_room", "no existe esa sala")
            return JSONResponse(room.info())
        if room is None:
            return HTMLResponse(_page("Sala no encontrada", "<p>No existe esa sala.</p>"), 404)
        return HTMLResponse(_room_page(room, self.url(request, f"/r/{room.code}")))

    async def index(self, request: Request) -> Response:
        rows = "".join(
            f'<li><a href="/r/{r.code}">{display(r.code)}</a> · {html.escape(r.game.title)}'
            f" · {_status_text(r)}</li>"
            for r in self.rooms.listed()
        )
        games = ", ".join(html.escape(g["title"]) for g in self.rooms.catalog.info())
        body = (
            f"<p>Servidor de partidas de GameHub {__version__} · protocolo v{VERSION}.</p>"
            f"<h2>Salas abiertas</h2><ul>{rows or '<li>Ninguna por ahora.</li>'}</ul>"
            f"<p>Juegos disponibles: {games or 'ninguno (solo las salas del anfitrión)'}.</p>"
        )
        return HTMLResponse(_page(self.rooms.name, body))


def create_app(server: GameServer) -> Starlette:
    routes = [
        Route("/", server.index),
        Route("/api/v1/info", server.info),
        Route("/api/v1/rooms", server.list_rooms, methods=["GET"]),
        Route("/api/v1/rooms", server.create_room, methods=["POST"]),
        Route("/api/v1/rooms/{code}", server.room_info),
        Route("/api/v1/rooms/{code}/ir", server.room_ir),
        Route("/api/v1/games/{id}", server.game_ir),
        Route("/api/v1/matches", server.matches),
        Route("/api/v1/replays/{id}", server.replay),
        Route("/r/{code}", server.room_page),
        WebSocketRoute("/ws", server.websocket),
    ]
    app = Starlette(routes=routes, lifespan=server.lifespan)
    app.state.server = server
    return app


# --- utilidades ----------------------------------------------------------------------------------


def _error(code: str, text: str, re: str | None = None) -> dict[str, Any]:
    return message("error", {"code": code, "message": text}, re)


def _api_error(status: int, code: str, text: str) -> Response:
    return JSONResponse({"error": {"code": code, "message": text}}, status_code=status)


def _status_text(room: Room) -> str:
    if room.status == "running":
        return "jugando"
    free = sum(1 for s in room.seats if s.empty)
    return f"esperando ({free} {'asiento libre' if free == 1 else 'asientos libres'})"


def _page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root {{ color-scheme: light dark; --fg: #1d2330; --bg: #f6f7fb; --muted: #5d6475; --card: #fff; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --fg: #e8eaf0; --bg: #14171f; --muted: #a0a6b5; --card: #1d212c; }}
}}
body {{ font: 16px/1.5 system-ui, sans-serif; color: var(--fg); background: var(--bg);
  margin: 0; padding: 2rem 1rem; }}
main {{ max-width: 40rem; margin: auto; background: var(--card); padding: 1.5rem;
  border-radius: 12px; }}
h1 {{ margin-top: 0; }} code {{ font-size: 1.05em; }} .muted {{ color: var(--muted); }}
.code {{ font: 700 2.5rem/1 ui-monospace, monospace; letter-spacing: .1em; }}
</style></head>
<body><main><h1>{html.escape(title)}</h1>{body}</main></body></html>
"""


def _room_page(room: Room, url: str) -> str:
    seats = "".join(
        f"<li>Asiento {s['seat'] + 1}: {html.escape(s.get('name', 'libre'))}"
        f" <span class='muted'>({s['kind']})</span></li>"
        for s in room.info()["seats"]
    )
    body = (
        f"<p class='code'>{display(room.code)}</p>"
        f"<p>{html.escape(room.game.title)} · {_status_text(room)}</p><ul>{seats}</ul>"
        "<p>Para unirte desde la terminal:</p>"
        f"<pre><code>gamehub join {html.escape(url)}</code></pre>"
        "<p class='muted'>El cliente web llega en la Fase 4.</p>"
    )
    return _page(f"Sala {display(room.code)}", body)
