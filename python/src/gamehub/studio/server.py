# SPDX-License-Identifier: Apache-2.0
"""`gamehub studio`: el servidor local del Studio.

Sirve la app web del Studio (`web/apps/studio`), una API para el espacio de trabajo (listar,
leer y guardar juegos, la disposición del diagrama, plantillas, historia de git) y, por
WebSocket (`/lsp`), el servidor de lenguaje con los métodos del Studio (ver
`gamehub.studio.session`).

Seguridad: el Studio lee y escribe archivos, así que solo escucha en la máquina local (por
defecto) y pide un **token** que se genera al arrancar y va en el enlace que se abre
(`/?token=…`); la app lo guarda en una cookie solo para este origen. Además se comprueban la
cabecera `Host` (contra el *DNS rebinding*) y el `Origin` de los WebSocket (contra otras webs
abiertas en el mismo navegador).
"""

from __future__ import annotations

import hmac
import os
import re
import secrets
from collections.abc import Awaitable, Callable
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket

from gamehub import gametemplates
from gamehub.lsp.server import run_websocket
from gamehub.packages import NAME, PackageError, new_package
from gamehub.studio.session import StudioSession
from gamehub.studio.workspace import Workspace, WorkspaceError

DEFAULT_PORT = 7421
COOKIE = "gamehub_studio"
# Por el WebSocket llega el texto entero de cada archivo abierto (didOpen): sin el límite de los
# mensajes de partida (64 KB).
WS_MAX_SIZE = 8 * 1024 * 1024
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

ASGIApp = Callable[[dict[str, Any], Any, Any], Awaitable[None]]


def studio_dir() -> Path | None:
    """La app del Studio compilada: `GAMEHUB_STUDIO_DIR`, la que viaja en la rueda
    (`gamehub/studioapp`) o la del repositorio (`web/apps/studio/dist`)."""
    env = os.environ.get("GAMEHUB_STUDIO_DIR")
    if env:
        path = Path(env)
        return path if (path / "index.html").is_file() else None
    for parent in Path(__file__).resolve().parents:
        for candidate in (parent / "studioapp", parent / "web" / "apps" / "studio" / "dist"):
            if (candidate / "index.html").is_file():
                return candidate
    return None


def _hostname(value: str) -> str:
    """El nombre de una cabecera Host (`127.0.0.1:7421` → `127.0.0.1`, `[::1]:7421` → `::1`)."""
    value = value.strip().lower()
    if value.startswith("["):
        return value[1 : value.find("]")] if "]" in value else value
    return value.rsplit(":", 1)[0] if value.count(":") == 1 else value


class Guard:
    """Middleware ASGI de seguridad: Host, Origin y token."""

    def __init__(self, app: ASGIApp, token: str | None, hosts: frozenset[str] | None) -> None:
        self.app = app
        self.token = token
        #: Nombres de máquina permitidos en Host y Origin (None: cualquiera, con el token).
        self.hosts = hosts

    def allowed_host(self, headers: dict[str, str]) -> bool:
        return self.hosts is None or _hostname(headers.get("host", "")) in self.hosts

    def allowed_origin(self, headers: dict[str, str]) -> bool:
        origin = headers.get("origin")
        if origin is None:
            return True
        host = (urlparse(origin).hostname or "").lower()
        if self.hosts is None:
            return host == _hostname(headers.get("host", ""))
        return host in self.hosts

    def has_token(self, headers: dict[str, str], query: str) -> bool:
        if self.token is None:
            return True
        given = headers.get("x-gamehub-token")
        if given is None:
            cookie = SimpleCookie(headers.get("cookie", ""))
            given = cookie[COOKIE].value if COOKIE in cookie else None
        if given is None:
            given = (parse_qs(query).get("token") or [None])[0]
        return given is not None and hmac.compare_digest(given, self.token)

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        query = scope.get("query_string", b"").decode("latin-1")
        path = scope.get("path", "")
        if not self.allowed_host(headers):
            await self.deny(scope, receive, send, 403, "host no permitido")
            return
        if scope["type"] == "websocket":
            if not self.allowed_origin(headers) or not self.has_token(headers, query):
                await send({"type": "websocket.close", "code": 1008})
                return
        elif (path.startswith("/api/") or path == "/lsp") and not self.has_token(headers, query):
            await self.deny(scope, receive, send, 401, "falta el token del Studio")
            return
        await self.app(scope, receive, send)

    async def deny(
        self, scope: dict[str, Any], receive: Any, send: Any, status: int, why: str
    ) -> None:
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        await JSONResponse({"error": why}, status_code=status)(scope, receive, send)


TOKEN_PAGE = """<!doctype html><html lang="es"><meta charset="utf-8">
<title>GameHub Studio</title>
<body style="font-family:system-ui;max-width:36rem;margin:4rem auto;line-height:1.5">
<h1>GameHub Studio</h1>
<p>Abre el Studio con el enlace que muestra <code>gamehub studio</code> al arrancar: lleva un token
que protege tus archivos.</p></body></html>"""

MISSING_APP = """<!doctype html><html lang="es"><meta charset="utf-8">
<title>GameHub Studio</title>
<body style="font-family:system-ui;max-width:36rem;margin:4rem auto;line-height:1.5">
<h1>GameHub Studio</h1>
<p>Falta la app web del Studio. Compílala en la raíz del repositorio con
<code>pnpm install &amp;&amp; pnpm build</code> y vuelve a arrancar <code>gamehub studio</code>.</p>
<p>El servidor de lenguaje ya funciona en <code>/lsp</code>.</p></body></html>"""


def create_app(
    workspace: Workspace,
    *,
    token: str | None,
    web: Path | None = None,
    hosts: frozenset[str] | None = LOCAL_HOSTS,
    open_file: str | None = None,
) -> ASGIApp:
    """La app ASGI del Studio (con su guardia de seguridad)."""

    async def index(request: Request) -> Response:
        given = request.query_params.get("token")
        if token is not None and given is not None:
            if not hmac.compare_digest(given, token):
                return HTMLResponse(TOKEN_PAGE, status_code=401)
            opened = request.query_params.get("file")
            target = "/" + (f"?file={quote(opened)}" if opened else "")
            response = RedirectResponse(target, status_code=303)
            response.set_cookie(COOKIE, token, httponly=True, samesite="strict", path="/")
            return response
        if token is not None and request.cookies.get(COOKIE) != token:
            return HTMLResponse(TOKEN_PAGE, status_code=401)
        if web is None:
            return HTMLResponse(MISSING_APP)
        response = HTMLResponse((web / "index.html").read_text(encoding="utf-8"))
        response.headers["cache-control"] = "no-cache"
        return response

    def error(exc: WorkspaceError) -> JSONResponse:
        return JSONResponse({"error": str(exc)}, status_code=exc.status)

    async def info(request: Request) -> Response:
        return JSONResponse(
            {
                "root": str(workspace.root),
                "name": workspace.root.name,
                "rootUri": workspace.root.as_uri(),
                "open": open_file,
                "files": workspace.files(),
                "templates": gametemplates.templates(),
            }
        )

    async def file(request: Request) -> Response:
        try:
            if request.method == "GET":
                return JSONResponse(workspace.read(request.query_params.get("path", "")))
            body = await request.json()
            path, text = str(body.get("path", "")), str(body.get("text", ""))
            result = workspace.write(path, text, body.get("mtime"))
            return JSONResponse(result)
        except WorkspaceError as exc:
            return error(exc)

    async def layout(request: Request) -> Response:
        try:
            body = await request.json()
            workspace.write_layout(str(body.get("path", "")), body.get("layout"))
            return JSONResponse({"ok": True})
        except WorkspaceError as exc:
            return error(exc)

    async def new_game(request: Request) -> Response:
        body = await request.json()
        name = str(body.get("name", ""))
        if not NAME.match(name):
            return JSONResponse(
                {"error": "el nombre va en minúsculas, con números y guiones"}, status_code=400
            )
        try:
            root = workspace.resolve(name)
            manifest = new_package(
                root, name, template=body.get("template"), title=body.get("title") or None
            )
        except (PackageError, WorkspaceError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        return JSONResponse({"path": workspace.relative(manifest.entry_path)})

    async def history(request: Request) -> Response:
        try:
            return JSONResponse(workspace.history(request.query_params.get("path", "")))
        except WorkspaceError as exc:
            return error(exc)

    async def show(request: Request) -> Response:
        try:
            text = workspace.show(
                request.query_params.get("path", ""), request.query_params.get("rev", "")
            )
            return JSONResponse({"text": text})
        except WorkspaceError as exc:
            return error(exc)

    async def lsp(websocket: WebSocket) -> None:
        await websocket.accept()
        session = StudioSession()
        await run_websocket(
            websocket, session.server, methods=session.methods, on_open=session.open
        )

    routes: list[Any] = [
        Route("/", index),
        Route("/api/workspace", info),
        Route("/api/file", file, methods=["GET", "PUT"]),
        Route("/api/layout", layout, methods=["PUT"]),
        Route("/api/new", new_game, methods=["POST"]),
        Route("/api/git/log", history),
        Route("/api/git/show", show),
        WebSocketRoute("/lsp", lsp),
    ]
    if web is not None:
        routes.append(Mount("/", StaticFiles(directory=web)))
    return Guard(Starlette(routes=routes), token, hosts)


def new_token() -> str:
    return secrets.token_urlsafe(24)


def safe_name(text: str) -> str:
    """Un nombre de paquete a partir de un título (`Mi Juego` → `mi-juego`)."""
    out = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return out or "juego"


class StudioThread:
    """El Studio en un hilo propio, en 127.0.0.1 y un puerto libre (para tests y scripts)."""

    def __init__(
        self,
        root: Path,
        *,
        token: str | None = None,
        web: Path | None = None,
        host: str = "127.0.0.1",
        port: int = 0,
    ) -> None:
        import threading

        from gamehub.server.run import Server, config

        self.token = token
        self.host = host
        app = create_app(Workspace(root), token=token, web=web)
        self.server = Server(config(app, host, port, ws_max_size=WS_MAX_SIZE))
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self) -> StudioThread:
        import threading

        self.thread.start()
        for _ in range(500):
            if self.server.started:
                return self
            if not self.thread.is_alive():
                break
            threading.Event().wait(0.01)
        raise OSError("el Studio no ha arrancado")

    def __exit__(self, *exc: object) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)

    @property
    def port(self) -> int:
        return self.server.port

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"
