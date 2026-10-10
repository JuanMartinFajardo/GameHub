# SPDX-License-Identifier: Apache-2.0
"""Cliente del protocolo de partidas: una conexión asíncrona que sigue el estado de la sala y la
partida y se reconecta sola.

    client = Client("http://192.168.1.20:7420", name="Ana")
    await client.connect()
    await client.join("K7F-Q2P")
    await client.ready()
    async for msg in client:          # mensajes del servidor, ya incorporados al estado
        if client.legal:              # me toca
            await client.act(client.legal[0])

Si se corta la conexión y hay sesión, vuelve a conectar con espera creciente y retoma con el
último `seq` visto (`resume`): el servidor reenvía solo lo que faltaba. El flujo de mensajes no se
interrumpe; `on_status` avisa de "reconnecting" y "connected".
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import json
import secrets
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from websockets.asyncio.client import ClientConnection
from websockets.asyncio.client import connect as ws_connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake, InvalidURI

from gamehub import __version__
from gamehub.engine import Action
from gamehub.protocol import check_server, client_message
from gamehub.server import DEFAULT_PORT
from gamehub.server.codes import normalize

#: Nombre del software cliente en el `hello`.
CLIENT_NAME = "gamehub-python"
#: Segundos para conectar y para recibir la respuesta a una petición.
TIMEOUT = 10.0
#: Tiempo máximo intentando reconectar antes de rendirse.
RECONNECT_FOR = 120.0


class ClientError(Exception):
    """Un error del servidor (`code` del protocolo) o de la conexión (`code="connection"`)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def endpoints(target: str) -> tuple[str, str, str | None]:
    """URL HTTP base, URL del WebSocket y código de sala (si va en la dirección) de algo como
    `192.168.1.20`, `host:7420`, `http://host:7420/r/K7FQ2P` o `ws://host:7420/ws`."""
    text = target.strip()
    if "://" not in text:
        text = "http://" + text
    url = urllib.parse.urlsplit(text)
    scheme = {"ws": "http", "wss": "https"}.get(url.scheme, url.scheme)
    if scheme not in ("http", "https") or not url.hostname:
        raise ClientError("connection", f"dirección de servidor no válida: {target}")
    port = url.port or (DEFAULT_PORT if url.scheme in ("http", "ws") else 443)
    host = f"[{url.hostname}]" if ":" in url.hostname else url.hostname
    http = f"{scheme}://{host}:{port}"
    ws = ("wss" if scheme == "https" else "ws") + f"://{host}:{port}/ws"
    parts = [p for p in url.path.split("/") if p]
    code = normalize(parts[1]) if len(parts) == 2 and parts[0] == "r" else None
    return http, ws, code


def target(room: str, server: str | None = None) -> tuple[str, str]:
    """Servidor y código de sala de lo que escribe alguien: un enlace de sala
    (`http://192.168.1.20:7420/r/K7FQ2P`) o un código (`K7F-Q2P`, en el servidor `server` o, si
    no se indica, en este equipo)."""
    if "/" in room or ":" in room:
        http, _, code = endpoints(room)
        if code is None:
            raise ClientError("unknown_room", f"el enlace no lleva el código de la sala: {room}")
        return http, code
    code = normalize(room)
    if code is None:
        raise ClientError("unknown_room", f"código de sala no válido: {room}")
    return endpoints(server or f"127.0.0.1:{DEFAULT_PORT}")[0], code


class Client:
    def __init__(
        self,
        server: str,
        *,
        name: str = "Anónimo",
        kind: str = "human",
        legal_limit: int = 256,
        token: str | None = None,
        reconnect: bool = True,
        on_status: Callable[[str], None] | None = None,
        validate: bool = False,
    ) -> None:
        self.http, self.ws_url, self.room_code = endpoints(server)
        self.name = name
        self.kind = kind
        self.legal_limit = legal_limit
        self.token = token
        self.reconnect = reconnect
        self.on_status = on_status
        self.validate = validate
        self.ws: ClientConnection | None = None
        self.inbox: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self.pending: dict[str, tuple[asyncio.Future[dict[str, Any]], set[str], set[str]]] = {}
        self.reader: asyncio.Task[None] | None = None
        self.closed = False
        # Los ids de mensaje deben ser únicos en toda la sesión, también entre procesos que la
        # retoman con el mismo token (el servidor descarta un `act` con un id ya visto).
        self._prefix = secrets.token_hex(4)
        self._ids = itertools.count(1)
        # Estado que se sigue de los mensajes.
        self.server: dict[str, Any] | None = None
        self.session: dict[str, Any] | None = None
        self.room: dict[str, Any] | None = None
        self.match: dict[str, Any] | None = None
        self.update: dict[str, Any] | None = None
        self.ending: dict[str, Any] | None = None

    # --- conexión -------------------------------------------------------------------------------

    async def connect(self) -> dict[str, Any]:
        """Conecta y saluda (retomando la sesión si hay `token`). Devuelve los datos de
        `welcome`."""
        self.ws = await self._open()
        self.reader = asyncio.create_task(self._read_loop())
        msg = await self._request("hello", self._hello(), {"welcome"}, tolerate={"invalid_token"})
        return msg["data"]

    async def close(self) -> None:
        self.closed = True
        if self.ws is not None:
            await self.ws.close()
        if self.reader is not None:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await asyncio.wait_for(self.reader, 5)

    async def __aenter__(self) -> Client:
        await self.connect()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    def __aiter__(self) -> Client:
        return self

    async def __anext__(self) -> dict[str, Any]:
        msg = await self.inbox.get()
        if msg is None:
            self.inbox.put_nowait(None)  # que las siguientes lecturas también terminen
            raise StopAsyncIteration
        return msg

    async def next(self, kind: str | None = None, timeout: float = TIMEOUT) -> dict[str, Any]:
        """El siguiente mensaje (del tipo indicado, descartando los demás)."""
        async with asyncio.timeout(timeout):
            async for msg in self:
                if kind is None or msg["type"] == kind:
                    return msg
        raise ClientError("connection", "la conexión se ha cerrado")

    # --- peticiones -----------------------------------------------------------------------------

    async def join(
        self,
        room: str | None = None,
        *,
        role: str = "player",
        seat: int | None = None,
    ) -> dict[str, Any]:
        """Entra en una sala (la de la dirección del servidor si no se indica). Devuelve los datos
        de `joined`."""
        code = room or self.room_code
        if code is None:
            raise ClientError("unknown_room", "falta el código de la sala")
        data: dict[str, Any] = {"room": code, "role": role, "name": self.name.strip()[:32]}
        if seat is not None:
            data["seat"] = seat
        msg = await self._request("join", data, {"joined"})
        return msg["data"]

    async def ready(self, ready: bool = True, seed: str | None = None) -> None:
        data: dict[str, Any] = {"ready": ready}
        if seed is not None:
            data["seed"] = seed
        await self.send("ready", data)

    async def act(self, action: Action | dict[str, Any], seq: int | None = None) -> str:
        """Juega una acción (con el `seq` de la última actualización si no se indica). Devuelve
        el id del mensaje: un `rejected` con ese `re` dice que no se aplicó."""
        payload = action.to_json() if isinstance(action, Action) else action
        if seq is None:
            seq = self.seq
        return await self.send("act", {"seq": seq, "action": payload})

    async def query_actions(
        self, name: str | None = None, args: dict[str, Any] | None = None
    ) -> list[Any]:
        data: dict[str, Any] = {"seq": self.seq}
        if name is not None:
            data["name"] = name
        if args is not None:
            data["args"] = args
        msg = await self._request("query_actions", data, {"actions"})
        return msg["data"]["options"]

    async def sit(self, seat: int | None = None) -> None:
        await self.send("sit", {} if seat is None else {"seat": seat})

    async def stand(self) -> None:
        await self.send("stand", {})

    async def leave(self) -> None:
        await self.send("leave", {})
        self.token = None  # la sesión ya no existe

    async def resign(self) -> None:
        await self.send("resign", {})

    async def chat(self, text: str) -> None:
        await self.send("chat", {"text": text})

    async def resync(self) -> None:
        await self.send("resync", {})

    async def configure(self, **data: Any) -> None:
        await self.send("configure", data)

    async def set_seat(self, seat: int, kind: str, **extra: Any) -> None:
        await self.send("set_seat", {"seat": seat, "kind": kind, **extra})

    async def kick(self, participant: str) -> None:
        await self.send("kick", {"participant": participant})

    async def send(self, kind: str, data: dict[str, Any]) -> str:
        mid = self._next_id()
        await self._raw(client_message(kind, data, mid))
        return mid

    # --- estado ---------------------------------------------------------------------------------

    @property
    def seat(self) -> int | None:
        return self.session["seat"] if self.session is not None else None

    @property
    def seq(self) -> int:
        return self.update["seq"] if self.update is not None else 0

    @property
    def view(self) -> dict[str, Any] | None:
        return self.update["view"] if self.update is not None else None

    @property
    def legal(self) -> list[dict[str, Any]] | None:
        """Las acciones legales enumeradas si me toca (o `[]` si son progresivas)."""
        if self.update is None or self.ending is not None or "legal" not in self.update:
            return None
        legal = self.update["legal"]
        return legal["actions"] if legal["kind"] == "enumerated" else []

    @property
    def my_turn(self) -> bool:
        return self.legal is not None

    @property
    def in_match(self) -> bool:
        return self.match is not None and self.ending is None

    def seat_info(self, seat: int) -> dict[str, Any] | None:
        if self.room is None:
            return None
        return next((s for s in self.room["seats"] if s["seat"] == seat), None)

    # --- HTTP -----------------------------------------------------------------------------------

    async def get_json(self, path: str) -> Any:
        return await fetch_json(self.http + path)

    async def room_ir(self, code: str | None = None) -> dict[str, Any]:
        """La IR del juego de la sala."""
        code = code or (self.session or {}).get("room") or self.room_code
        if code is None:
            raise ClientError("unknown_room", "falta el código de la sala")
        return await self.get_json(f"/api/v1/rooms/{code}/ir")

    # --- internos -------------------------------------------------------------------------------

    def _next_id(self) -> str:
        return f"{self._prefix}-{next(self._ids)}"

    def _hello(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "client": {"name": CLIENT_NAME, "kind": self.kind, "version": __version__},
            "legal_limit": self.legal_limit,
        }
        if self.token is not None:
            data["token"] = self.token
            if self.in_match and self.match is not None and self.update is not None:
                data["resume"] = {"match": self.match["match"]["id"], "seq": self.update["seq"]}
        return data

    async def _open(self) -> ClientConnection:
        try:
            return await ws_connect(
                self.ws_url, open_timeout=TIMEOUT, max_size=None, ping_interval=15
            )
        except (OSError, InvalidHandshake, InvalidURI, TimeoutError) as exc:
            raise ClientError(
                "connection", f"no se puede conectar con {self.http}: {exc}"
            ) from None

    async def _raw(self, msg: dict[str, Any]) -> None:
        if self.ws is None:
            raise ClientError("connection", "no hay conexión")
        try:
            await self.ws.send(json.dumps(msg, ensure_ascii=False))
        except ConnectionClosed:
            raise ClientError("connection", "se ha perdido la conexión") from None

    async def _request(
        self,
        kind: str,
        data: dict[str, Any],
        expect: set[str],
        *,
        tolerate: frozenset[str] | set[str] = frozenset(),
    ) -> dict[str, Any]:
        """Envía y espera la respuesta con su `re`. Un `error` lanza `ClientError`, salvo los de
        `tolerate`, tras los que se sigue esperando (al retomar una sesión caducada el servidor
        responde con `invalid_token` y después con `welcome`)."""
        mid = self._next_id()
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self.pending[mid] = (future, expect | {"error"}, set(tolerate))
        try:
            await self._raw(client_message(kind, data, mid))
            msg = await asyncio.wait_for(future, TIMEOUT)
        finally:
            self.pending.pop(mid, None)
        if msg["type"] == "error":
            raise ClientError(msg["data"]["code"], msg["data"]["message"])
        return msg

    async def _read_loop(self) -> None:
        while True:
            ws = self.ws
            assert ws is not None
            try:
                async for raw in ws:
                    self._dispatch(json.loads(raw))
            except ConnectionClosed:
                pass
            for future, _, _ in self.pending.values():
                if not future.done():
                    future.set_exception(ClientError("connection", "se ha perdido la conexión"))
            if self.closed or not self.reconnect or self.token is None or not await self._again():
                self.inbox.put_nowait(None)
                return

    async def _again(self) -> bool:
        """Reconecta con espera creciente y retoma la sesión."""
        self._status("reconnecting")
        loop = asyncio.get_running_loop()
        deadline = loop.time() + RECONNECT_FOR
        delay = 0.25
        while not self.closed and loop.time() < deadline:
            await asyncio.sleep(delay)
            delay = min(delay * 2, 5.0)
            try:
                self.ws = await self._open()
                await self._raw(client_message("hello", self._hello(), self._next_id()))
            except ClientError:
                continue
            self._status("connected")
            return True
        return False

    def _status(self, status: str) -> None:
        if self.on_status is not None:
            self.on_status(status)

    def _dispatch(self, msg: dict[str, Any]) -> None:
        if self.validate:
            problems = check_server(msg)
            if problems:
                raise ClientError("bad_message", f"mensaje del servidor inválido: {problems}")
        kind, data = msg["type"], msg["data"]
        match kind:
            case "welcome":
                self.server = data["server"]
                if "session" in data:
                    self.session = data["session"]
            case "joined":
                self.token = data["token"]
                self.session = data["session"]
            case "room":
                self.room = data
                self._follow_seat(data)
            case "match_start":
                self.match, self.update, self.ending = data, None, None
            case "update":
                self.update = data
            case "match_end":
                self.ending = data
            case "error" if data["code"] in ("invalid_token", "replaced"):
                self.token = None if data["code"] == "invalid_token" else self.token
        waiting = self.pending.get(msg.get("re") or "")
        if waiting is not None and not waiting[0].done():
            future, expect, tolerate = waiting
            if kind in expect and not (kind == "error" and data["code"] in tolerate):
                future.set_result(msg)
                if kind == "actions":
                    return  # respuesta consumida por quien la pidió
        self.inbox.put_nowait(msg)

    def _follow_seat(self, room: dict[str, Any]) -> None:
        """El asiento propio puede cambiar (sentarse, levantarse, configurar la sala)."""
        if self.session is None:
            return
        me = self.session["participant"]
        seat = next((s["seat"] for s in room["seats"] if s.get("participant") == me), None)
        self.session = {
            **self.session,
            "seat": seat,
            "role": "player" if seat is not None else "spectator",
        }


async def fetch_json(url: str, body: Any = None) -> Any:
    """GET (o POST con `body`) de JSON por HTTP, sin bloquear el bucle."""

    def run() -> Any:
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            try:
                error = json.loads(exc.read())["error"]
            except (ValueError, KeyError, TypeError):
                error = {"code": "connection", "message": f"HTTP {exc.code}"}
            raise ClientError(error["code"], error["message"]) from None
        except (urllib.error.URLError, OSError) as exc:
            raise ClientError("connection", f"no se puede conectar con {url}: {exc}") from None

    return await asyncio.to_thread(run)


async def create_room(server: str, **body: Any) -> dict[str, Any]:
    """Crea una sala por la API REST (`game` o `ir`, `players`, `params`, `settings`, `name`).
    Devuelve `{code, token, url, room}`; el token es la sesión del anfitrión."""
    http, _, _ = endpoints(server)
    return await fetch_json(http + "/api/v1/rooms", body)
