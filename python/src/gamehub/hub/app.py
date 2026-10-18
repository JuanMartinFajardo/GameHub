# SPDX-License-Identifier: AGPL-3.0-or-later
"""El hub en HTTP (Starlette): la API REST, git por HTTP, OAuth, las Pages, el servidor de
partidas y la app web.

- `/api/v1/…`: la API (JSON). Autenticación con la cookie de sesión del navegador, con
  `Authorization: Bearer ghb_…` (CLI) o con HTTP Basic (git). Errores: `{"error": {code,
  message}}` con su estado HTTP.
- `/{dueño}/{repo}.git/…`: git por HTTP inteligente (`git clone`, `git push`), servido por
  `git http-backend`; empujar exige permiso de escritura (un token como contraseña).
- `/auth/{proveedor}/login|callback`: OAuth.
- `/pages/{dueño}/{repo}/{nombre}/…`: las interfaces publicadas, en un origen opaco.
- `/api/v1/rooms`, `/ws`…: el servidor de partidas (`gamehub.server`), con el catálogo del hub.
- El resto: la app web del hub (`web/apps/hub`), que se enruta en el navegador.

El trabajo del servicio (base de datos, git, compilar) va a un hilo para no parar el bucle de
eventos, donde viven las salas.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import os
import secrets
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)
from starlette.routing import BaseRoute, Route, WebSocketRoute

from gamehub import __version__
from gamehub.hub import accounts as acc
from gamehub.hub import explore, jobs, pages, play, pulls, registry
from gamehub.hub.gitrepo import git_env
from gamehub.hub.service import Account, Hub, HubError, Repo, bad, forbidden, not_found, read_terms
from gamehub.server.app import Connection, GameServer
from gamehub.server.room import Room
from gamehub.server.rooms import Rooms, TokenBucket
from gamehub.server.store import MemoryStore, SqliteStore

#: Peticiones por segundo de cada dirección a la API (con ráfagas).
API_RATE = 30.0
API_BURST = 120


def hub_web_dir() -> Path | None:
    """La app web del hub compilada: `GAMEHUB_HUB_WEB_DIR`, la copia dentro del paquete
    (`gamehub/hubapp`) o la del repositorio (`web/apps/hub/dist`)."""
    env = os.environ.get("GAMEHUB_HUB_WEB_DIR")
    if env:
        path = Path(env)
        return path if (path / "index.html").is_file() else None
    for parent in Path(__file__).resolve().parents:
        for candidate in (parent / "hubapp", parent / "web" / "apps" / "hub" / "dist"):
            if (candidate / "index.html").is_file():
                return candidate
    return None


@dataclass
class Ctx:
    """Lo que recibe un manejador de la API (ya en su hilo)."""

    request: Request
    viewer: Account | None
    body: Any
    raw: bytes

    def param(self, name: str) -> str:
        return self.request.path_params[name]

    def query(self, name: str, default: str | None = None) -> str | None:
        return self.request.query_params.get(name, default)

    def user(self) -> Account:
        if self.viewer is None:
            raise HubError(401, "unauthenticated", "inicia sesión para hacerlo")
        return self.viewer

    def field(
        self, name: str, kind: type = str, *, required: bool = True, default: Any = None
    ) -> Any:
        if not isinstance(self.body, dict):
            raise bad("el cuerpo tiene que ser un objeto JSON")
        value = self.body.get(name, default)
        if value is None:
            if required:
                raise bad(f"falta {name}")
            return default
        if kind is int and isinstance(value, bool):
            raise bad(f"{name} tiene que ser un número")
        if not isinstance(value, kind):
            raise bad(f"{name} no tiene el tipo esperado")
        return value


Handler = Callable[[Ctx], Any]


class HubGameServer(GameServer):
    """El servidor de partidas dentro del hub: el asiento de quien entra con sesión queda a su
    nombre (para las valoraciones)."""

    def __init__(self, rooms: Rooms, app: HubApp) -> None:
        super().__init__(rooms, public_url=app.hub.config.public_url)
        self.hub_app = app

    def _bind(self, conn: Connection, room: Room, pid: str) -> None:
        super()._bind(conn, room, pid)
        p = room.participants.get(pid)
        if p is not None and p.account is None:
            account = self.hub_app.cookie_account(conn.ws.cookies.get(acc.SESSION_COOKIE))
            if account is not None:
                p.account = account["id"]


class HubApp:
    def __init__(self, hub: Hub, *, web: Path | None = None, workers: int | None = None) -> None:
        self.hub = hub
        self.web = web
        jobs.install(hub)
        self.catalog = play.HubCatalog(hub)
        store = (
            SqliteStore(hub.config.data / "matches.db")
            if hub.config.database is None
            else MemoryStore()
        )
        self.rooms = Rooms(
            self.catalog, play.HubRecorder(hub, self.catalog, store), name=hub.config.name
        )
        self.server = HubGameServer(self.rooms, self)
        self.matchmaker = play.Matchmaker()
        self.runner = jobs.JobRunner(hub, hub.config.workers if workers is None else workers)
        self.buckets: dict[str, TokenBucket] = {}

    # --- ciclo de vida --------------------------------------------------------------------------

    @contextlib.asynccontextmanager
    async def lifespan(self, app: Starlette) -> AsyncIterator[None]:
        self.runner.start()
        matcher = asyncio.create_task(self._matchmaking_loop())
        try:
            async with self.server.lifespan(app):
                yield
        finally:
            matcher.cancel()
            await asyncio.to_thread(self.runner.close)

    async def _matchmaking_loop(self) -> None:
        while True:
            await asyncio.sleep(0.5)
            with contextlib.suppress(Exception):
                self.match_groups()

    def match_groups(self) -> None:
        """Abre una sala para cada grupo ya formado y sienta en ella a sus jugadores."""
        now = self.server.now()
        self.matchmaker.expire(time.time())
        for group in self.matchmaker.groups(time.time()):
            game = self.catalog.get(group[0].game)
            if game is None:
                for t in group:
                    self.matchmaker.tickets.pop(t.id, None)
                continue
            room, _ = self.rooms.create(
                game, now=now, players=group[0].players, host_name="GameHub"
            )
            for seat, t in enumerate(group):
                p, token = self.rooms.join(
                    room, now=now, name=t.name, role="player", seat=seat, connected=False
                )
                p.account = t.account
                t.room, t.token, t.seat = room.code, token, seat
            self.server.flush(room)

    # --- autenticación --------------------------------------------------------------------------

    def cookie_account(self, secret: str | None) -> Account | None:
        return self.hub.session_account(secret) if secret else None

    def viewer(self, request: Request) -> Account | None:
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            account = self.hub.token_account(auth[7:].strip())
            if account is None:
                raise HubError(401, "bad_token", "el token no vale (¿revocado?)")
            return account
        if auth.startswith("Basic "):
            try:
                user, _, secret = base64.b64decode(auth[6:]).decode("utf-8").partition(":")
            except (ValueError, UnicodeDecodeError):
                raise HubError(401, "bad_credentials", "credenciales mal formadas") from None
            account = self.hub.credentials(user, secret)
            if account is None:
                raise HubError(401, "bad_credentials", "usuario o token incorrectos")
            return account
        account = self.cookie_account(request.cookies.get(acc.SESSION_COOKIE))
        if account is not None and request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            own = f"{request.url.scheme}://{request.url.netloc}"
            if origin is not None and origin != own and origin != self.hub.config.public_url:
                raise forbidden("petición desde otro sitio")
        return account

    def limited(self, request: Request) -> bool:
        key = request.client.host if request.client else "?"
        now = time.monotonic()
        bucket = self.buckets.get(key)
        if bucket is None:
            if len(self.buckets) > 10000:
                self.buckets.clear()
            bucket = self.buckets[key] = TokenBucket(API_RATE, API_BURST, now)
        return not bucket.take(now)

    # --- envoltorio de la API -------------------------------------------------------------------

    def api(self, fn: Handler, *, raw: bool = False) -> Callable[[Request], Awaitable[Response]]:
        async def endpoint(request: Request) -> Response:
            if self.limited(request):
                return _error(429, "rate_limited", "demasiadas peticiones: espera un poco")
            limit = int(self.hub.config.quotas.push_mb * 1024 * 1024) + 65536
            declared = request.headers.get("content-length")
            if declared and declared.isdigit() and int(declared) > limit:
                return _error(413, "too_large", "la petición es demasiado grande")
            data = await request.body()
            if len(data) > limit:
                return _error(413, "too_large", "la petición es demasiado grande")
            body: Any = None
            if data and not raw:
                try:
                    body = json.loads(data)
                except ValueError:
                    return _error(400, "bad_request", "el cuerpo no es JSON")

            def work() -> Any:
                ctx = Ctx(request, self.viewer(request), body, data)
                return fn(ctx)

            try:
                result = await asyncio.to_thread(work)
            except HubError as exc:
                return _error(exc.status, exc.code, exc.message)
            if isinstance(result, Response):
                return result
            return JSONResponse(result)

        return endpoint

    # --- cuentas y sesiones ---------------------------------------------------------------------

    def info(self, ctx: Ctx) -> dict[str, Any]:
        c = self.hub.config
        return {
            "name": c.name,
            "version": __version__,
            "public_url": c.public_url,
            "signup": c.signup,
            "terms_version": c.terms_version,
            "oauth": [{"name": p.name, "title": p.title} for p in c.oauth.values()],
            "web": self.web is not None,
        }

    def terms(self, ctx: Ctx) -> dict[str, Any]:
        return {"version": self.hub.config.terms_version, "text": read_terms(self.hub.config)}

    def _session_response(self, account: Account, status: int = 200) -> Response:
        response = JSONResponse({"user": self.hub.public_account(account, private=True)}, status)
        self._set_session(response, account)
        return response

    def _set_session(self, response: Response, account: Account) -> None:
        response.set_cookie(
            acc.SESSION_COOKIE,
            self.hub.new_session(account),
            max_age=acc.SESSION_DAYS * 86400,
            httponly=True,
            samesite="lax",
            secure=self.hub.config.secure_cookies,
        )

    def signup(self, ctx: Ctx) -> Response:
        account = self.hub.signup(
            ctx.field("name"),
            ctx.field("password"),
            email=ctx.field("email", required=False),
            display=ctx.field("display", required=False, default=""),
            terms=ctx.field("terms", required=False),
        )
        return self._session_response(account, 201)

    def login(self, ctx: Ctx) -> Response:
        account = self.hub.login(ctx.field("name"), ctx.field("password"))
        return self._session_response(account)

    def logout(self, ctx: Ctx) -> Response:
        secret = ctx.request.cookies.get(acc.SESSION_COOKIE)
        if secret:
            self.hub.end_session(secret)
        response = JSONResponse({"ok": True})
        response.delete_cookie(acc.SESSION_COOKIE)
        return response

    def token_login(self, ctx: Ctx) -> dict[str, Any]:
        """Usuario y contraseña a cambio de un token de API (para `gamehub login`)."""
        account = self.hub.login(ctx.field("name"), ctx.field("password"))
        _, token = self.hub.new_token(
            account, ctx.field("token_name", required=False, default="cli")
        )
        return {"token": token, "user": self.hub.public_account(account)}

    def session(self, ctx: Ctx) -> dict[str, Any]:
        """Quién mira (la web pregunta siempre, con o sin sesión)."""
        user = ctx.viewer
        return {"user": self.hub.public_account(user, private=True) if user else None}

    def me(self, ctx: Ctx) -> dict[str, Any]:
        return {"user": self.hub.public_account(ctx.user(), private=True)}

    def update_me(self, ctx: Ctx) -> dict[str, Any]:
        user = ctx.user()
        self.hub.update_profile(
            user,
            display=ctx.field("display", required=False),
            bio=ctx.field("bio", required=False),
        )
        return {"user": self.hub.public_account(self.hub.account_by_id(user["id"]), private=True)}

    def accept_terms(self, ctx: Ctx) -> dict[str, Any]:
        self.hub.accept_terms(ctx.user(), ctx.field("version"))
        return {"ok": True}

    def tokens(self, ctx: Ctx) -> dict[str, Any]:
        return {"tokens": self.hub.tokens(ctx.user())}

    def new_token(self, ctx: Ctx) -> Response:
        token_id, secret = self.hub.new_token(
            ctx.user(), ctx.field("name", required=False, default="token")
        )
        return JSONResponse({"id": token_id, "token": secret}, 201)

    def revoke_token(self, ctx: Ctx) -> dict[str, Any]:
        self.hub.revoke_token(ctx.user(), int(ctx.param("id")))
        return {"ok": True}

    def account(self, ctx: Ctx) -> dict[str, Any]:
        row = self.hub.require_account(ctx.param("name"))
        out = self.hub.public_account(row)
        out["repos"] = [
            self.hub.repo_json(r, ctx.viewer) for r in self.hub.list_repos(row, ctx.viewer)
        ]
        if row["kind"] == "org":
            out["members"] = self.hub.members(row)
            out["role"] = self.hub.role(row, ctx.viewer)
        else:
            out["orgs"] = [
                r["name"]
                for r in self.hub.db.all(
                    "SELECT a.name FROM members m JOIN accounts a ON a.id = m.org"
                    " WHERE m.account = ? ORDER BY a.name",
                    (row["id"],),
                )
            ]
        out["events"] = self.hub.events(account=row, limit=30) if row["kind"] == "user" else []
        out["can_write"] = self.hub.can_write_owner(row, ctx.viewer)
        return out

    def create_org(self, ctx: Ctx) -> Response:
        org = self.hub.create_org(
            ctx.field("name"), ctx.user(), ctx.field("display", required=False, default="")
        )
        return JSONResponse(self.hub.public_account(org), 201)

    def set_member(self, ctx: Ctx) -> dict[str, Any]:
        org = self.hub.require_account(ctx.param("org"))
        if org["kind"] != "org":
            raise not_found("no es una organización")
        role = (
            None
            if ctx.request.method == "DELETE"
            else ctx.field("role", required=False, default="member")
        )
        self.hub.set_member(org, ctx.user(), ctx.param("name"), role)
        return {"members": self.hub.members(org)}

    # --- OAuth ----------------------------------------------------------------------------------

    def _redirect_uri(self, request: Request, provider: str) -> str:
        base = self.hub.config.public_url or f"{request.url.scheme}://{request.url.netloc}"
        return f"{base}/auth/{provider}/callback"

    async def oauth_login(self, request: Request) -> Response:
        provider = self.hub.config.oauth.get(request.path_params["provider"])
        if provider is None:
            return PlainTextResponse("proveedor desconocido", 404)
        state = secrets.token_urlsafe(24)
        target = request.query_params.get("next", "/")
        if not target.startswith("/") or target.startswith("//"):
            target = "/"
        url = acc.authorize_url(provider, self._redirect_uri(request, provider.name), state)
        response = RedirectResponse(url, 302)
        cookie = json.dumps({"state": state, "next": target})
        response.set_cookie(
            "gh_oauth",
            cookie,
            max_age=600,
            httponly=True,
            samesite="lax",
            secure=self.hub.config.secure_cookies,
        )
        return response

    async def oauth_callback(self, request: Request) -> Response:
        provider = self.hub.config.oauth.get(request.path_params["provider"])
        if provider is None:
            return PlainTextResponse("proveedor desconocido", 404)
        try:
            saved = json.loads(request.cookies.get("gh_oauth", "{}"))
        except ValueError:
            saved = {}
        state = request.query_params.get("state")
        code = request.query_params.get("code")
        if not state or not code or not secrets.compare_digest(state, str(saved.get("state", ""))):
            return PlainTextResponse("la respuesta de OAuth no es válida (state)", 400)
        try:
            identity = await asyncio.to_thread(
                acc.oauth_identity,
                provider,
                code,
                self._redirect_uri(request, provider.name),
                self.fetch,
            )
            account = await asyncio.to_thread(self.hub.oauth_account, provider.name, identity)
        except (ValueError, OSError) as exc:
            return PlainTextResponse(f"no se pudo entrar con {provider.title}: {exc}", 502)
        except HubError as exc:
            return PlainTextResponse(exc.message, exc.status)
        response = RedirectResponse(saved.get("next") or "/", 302)
        response.delete_cookie("gh_oauth")
        await asyncio.to_thread(self._set_session, response, account)
        return response

    #: Las peticiones HTTP a los proveedores de OAuth (los tests ponen otra).
    fetch: acc.Fetch = staticmethod(acc.http_fetch)  # type: ignore[assignment]

    # --- repositorios ---------------------------------------------------------------------------

    def repo(self, ctx: Ctx) -> Repo:
        return self.hub.repo(ctx.param("owner"), ctx.param("name"), ctx.viewer)

    def templates(self, ctx: Ctx) -> dict[str, Any]:
        from gamehub import gametemplates

        return {"templates": gametemplates.templates(), "default": gametemplates.DEFAULT}

    def create_repo(self, ctx: Ctx) -> Response:
        user = ctx.user()
        files = ctx.field("files", dict, required=False) or {}
        template = ctx.field("template", required=False)
        if template and not files:
            files = _template_files(ctx.field("name"), template, ctx.field("title", required=False))
        repo = self.hub.create_repo(
            ctx.field("owner", required=False) or user["name"],
            ctx.field("name"),
            user,
            kind=ctx.field("kind", required=False, default="game"),
            description=ctx.field("description", required=False, default=""),
            files={str(k): str(v).encode("utf-8") for k, v in files.items()},
        )
        return JSONResponse(self._repo_out(ctx, repo), 201)

    def _repo_out(self, ctx: Ctx, repo: Repo) -> dict[str, Any]:
        out = self.hub.repo_json(repo, ctx.viewer)
        base = self.hub.config.public_url or f"{ctx.request.url.scheme}://{ctx.request.url.netloc}"
        out["clone_url"] = f"{base}/{out['full_name']}.git"
        out["empty"] = self.hub.git(repo).is_empty()
        out["open_pulls"] = self.hub.db.value(
            "SELECT count(*) AS n FROM pulls WHERE repo = ? AND state = 'open'", (repo["id"],)
        )
        return out

    def get_repo(self, ctx: Ctx) -> dict[str, Any]:
        return self._repo_out(ctx, self.repo(ctx))

    def update_repo(self, ctx: Ctx) -> dict[str, Any]:
        repo = self.hub.update_repo(
            self.repo(ctx),
            ctx.user(),
            description=ctx.field("description", required=False),
            default_branch=ctx.field("default_branch", required=False),
        )
        return self._repo_out(ctx, repo)

    def delete_repo(self, ctx: Ctx) -> dict[str, Any]:
        self.hub.delete_repo(self.repo(ctx), ctx.user())
        return {"ok": True}

    def fork(self, ctx: Ctx) -> Response:
        repo = self.hub.fork(
            self.repo(ctx),
            ctx.user(),
            owner_name=ctx.field("owner", required=False) if ctx.body else None,
            name=ctx.field("name", required=False) if ctx.body else None,
        )
        return JSONResponse(self._repo_out(ctx, repo), 201)

    def star(self, ctx: Ctx) -> dict[str, Any]:
        on = ctx.request.method == "PUT"
        return {"stars": self.hub.star(self.repo(ctx), ctx.user(), on), "starred": on}

    def branches(self, ctx: Ctx) -> dict[str, Any]:
        git = self.hub.git(self.repo(ctx))
        return {"branches": git.branches(), "tags": git.tags()}

    def commits(self, ctx: Ctx) -> dict[str, Any]:
        repo = self.repo(ctx)
        commit = self.hub.ref_commit(repo, ctx.query("ref"))
        limit = min(int(ctx.query("limit", "50") or 50), 200)
        return {"commits": self.hub.git(repo).log(commit, limit=limit, path=ctx.query("path"))}

    def tree(self, ctx: Ctx) -> dict[str, Any]:
        repo = self.repo(ctx)
        commit = self.hub.ref_commit(repo, ctx.query("ref"))
        path = (ctx.query("path") or "").strip("/")
        try:
            entries = self.hub.git(repo).ls(commit, path, recursive=ctx.query("recursive") == "1")
        except Exception as exc:
            raise not_found(str(exc)) from None
        return {"commit": commit, "path": path, "entries": entries}

    def file(self, ctx: Ctx) -> dict[str, Any]:
        repo = self.repo(ctx)
        commit = self.hub.ref_commit(repo, ctx.query("ref"))
        path = (ctx.query("path") or "").strip("/")
        data = self.hub.git(repo).read(commit, path)
        if data is None:
            raise not_found(f"no existe {path}")
        out: dict[str, Any] = {"commit": commit, "path": path, "size": len(data)}
        try:
            out["text"] = data.decode("utf-8")
        except UnicodeDecodeError:
            out["base64"] = base64.b64encode(data).decode()
        return out

    def raw_file(self, ctx: Ctx) -> Response:
        info = self.file(ctx)
        if "text" in info:
            return PlainTextResponse(info["text"])
        return Response(base64.b64decode(info["base64"]), media_type="application/octet-stream")

    def commit(self, ctx: Ctx) -> Response:
        repo = self.repo(ctx)
        changes = ctx.field("changes", dict)
        decoded: dict[str, bytes | None] = {}
        for path, value in changes.items():
            if value is None:
                decoded[str(path)] = None
            elif isinstance(value, str):
                decoded[str(path)] = value.encode("utf-8")
            elif isinstance(value, dict) and isinstance(value.get("base64"), str):
                decoded[str(path)] = base64.b64decode(value["base64"])
            else:
                raise bad(f"{path}: el contenido es un texto, {{base64}} o null")
        commit = self.hub.commit_files(
            repo,
            ctx.user(),
            ctx.field("branch", required=False, default=repo["default_branch"]),
            decoded,
            ctx.field("message", required=False, default=""),
            expected=ctx.field("expected", required=False),
            base=ctx.field("base", required=False),
        )
        return JSONResponse({"commit": commit}, 201)

    def compiled(self, ctx: Ctx) -> dict[str, Any]:
        """El juego de un commit (una rama, sin publicar): reglamento, diagrama, clasificación."""
        repo = self.repo(ctx)
        commit = self.hub.ref_commit(repo, ctx.query("ref"))
        return self._build_out(
            repo, registry.build(self.hub, repo, commit, model=True), ctx.query("lang") or "es"
        )

    def _build_out(self, repo: Repo, built: registry.Build, lang: str) -> dict[str, Any]:
        out: dict[str, Any] = {
            "commit": built.commit,
            "problems": built.problems,
            "entry": built.entry,
            "model": built.model,
            "games": sorted(built.games),
        }
        if built.ir is not None:
            from gamehub.analysis.classify import classify
            from gamehub.ir.hashing import rules_hash
            from gamehub.ir.interface import interface_hash
            from gamehub.render.rules import rules

            info = classify(built.ir)
            out.update(
                game=built.ir["game"]["id"],
                rules_hash=rules_hash(built.ir),
                interface_hash=interface_hash(built.ir),
                classification={"labels": info.labels(), **info.to_json()},
                rules=rules(built.ir, lang),
                meta=built.ir.get("meta", {}),
            )
        return out

    def events(self, ctx: Ctx) -> dict[str, Any]:
        return {"events": self.hub.events(repo=self.repo(ctx))}

    def family(self, ctx: Ctx) -> dict[str, Any]:
        return explore.family(self.hub, self.repo(ctx), ctx.viewer)

    # --- versiones ------------------------------------------------------------------------------

    def releases(self, ctx: Ctx) -> dict[str, Any]:
        repo = self.repo(ctx)
        return {
            "releases": [
                registry.release_json(self.hub, repo, r) for r in registry.releases(self.hub, repo)
            ]
        }

    def publish(self, ctx: Ctx) -> Response:
        repo = self.repo(ctx)
        ref = ctx.field("ref", required=False) if ctx.body else None
        version = ctx.field("version", required=False) if ctx.body else None
        if ctx.body and ctx.field("dry_run", bool, required=False, default=False):
            return JSONResponse(registry.plan(self.hub, repo, ref, version).to_json())
        row = registry.publish(
            self.hub,
            repo,
            ctx.user(),
            ref,
            version=version,
            notes=ctx.field("notes", required=False, default="") if ctx.body else "",
        )
        return JSONResponse(registry.release_json(self.hub, repo, row), 201)

    def _release(self, ctx: Ctx) -> tuple[Repo, dict[str, Any]]:
        repo = self.repo(ctx)
        return repo, registry.release(self.hub, repo, ctx.param("version"))

    def get_release(self, ctx: Ctx) -> dict[str, Any]:
        repo, row = self._release(ctx)
        out = registry.release_json(self.hub, repo, row)
        if row["interface_hash"]:
            out["pages"] = pages.compatible(self.hub, row["interface_hash"])
        return out

    def release_ir(self, ctx: Ctx) -> Response:
        _, row = self._release(ctx)
        if row["ir"] is None:
            raise not_found("esta versión no tiene juego")
        return Response(self.hub.blobs.get(row["ir"]), media_type="application/json")

    def release_view(self, ctx: Ctx) -> dict[str, Any]:
        """Reglamento, diagrama y clasificación de una versión publicada."""
        repo, row = self._release(ctx)
        built = registry.build(self.hub, repo, row["commit_id"], model=True)
        return self._build_out(repo, built, ctx.query("lang") or "es")

    def yank(self, ctx: Ctx) -> dict[str, Any]:
        repo = self.repo(ctx)
        on = ctx.field("yanked", bool, required=False, default=True) if ctx.body else True
        registry.yank(self.hub, repo, ctx.user(), ctx.param("version"), on)
        return {"ok": True}

    def resolve(self, ctx: Ctx) -> dict[str, Any]:
        repo = self.repo(ctx)
        row = registry.best_release(self.hub, repo, ctx.query("requirement") or "*")
        base = self.hub.config.public_url or f"{ctx.request.url.scheme}://{ctx.request.url.netloc}"
        return {
            "version": row["version"],
            "commit": row["commit_id"],
            "git": f"{base}/{self.hub.full_name(repo)}.git",
            "rules_hash": row["rules_hash"],
        }

    def ratings(self, ctx: Ctx) -> dict[str, Any]:
        repo = self.repo(ctx)
        row = registry.release(self.hub, repo, ctx.query("version") or "latest")
        if row["rules_hash"] is None:
            return {"ratings": [], "matches": []}
        return {
            "rules_hash": row["rules_hash"],
            "version": row["version"],
            "ratings": play.leaderboard(self.hub, row["rules_hash"]),
            "matches": play.recent_matches(self.hub, row["rules_hash"]),
        }

    # --- propuestas -----------------------------------------------------------------------------

    def pulls(self, ctx: Ctx) -> dict[str, Any]:
        repo = self.repo(ctx)
        rows = pulls.listing(self.hub, repo, ctx.query("state") or "open")
        return {"pulls": [pulls.pull_json(self.hub, p, ctx.viewer) for p in rows]}

    def open_pull(self, ctx: Ctx) -> Response:
        target = self.repo(ctx)
        source_name = ctx.field("source", required=False) or self.hub.full_name(target)
        owner, _, name = source_name.partition("/")
        source = self.hub.repo(owner, name, ctx.viewer)
        row = pulls.create(
            self.hub,
            target,
            ctx.user(),
            source=source,
            head=ctx.field("head"),
            base=ctx.field("base", required=False),
            title=ctx.field("title"),
            body=ctx.field("body", required=False, default=""),
        )
        return JSONResponse(pulls.pull_json(self.hub, row, ctx.viewer), 201)

    def _pull(self, ctx: Ctx) -> dict[str, Any]:
        return pulls.refresh(
            self.hub, pulls.get(self.hub, self.repo(ctx), int(ctx.param("number")))
        )

    def get_pull(self, ctx: Ctx) -> dict[str, Any]:
        row = self._pull(ctx)
        out = pulls.pull_json(self.hub, row, ctx.viewer)
        if row["balance_job"]:
            out["balance"] = jobs.job_json(self.hub, jobs.get(self.hub, row["balance_job"]))
        return out

    def pull_diff(self, ctx: Ctx) -> dict[str, Any]:
        return pulls.diffs(self.hub, self._pull(ctx))

    def merge_pull(self, ctx: Ctx) -> dict[str, Any]:
        row = pulls.merge(
            self.hub,
            self._pull(ctx),
            ctx.user(),
            ctx.field("message", required=False) if ctx.body else None,
        )
        return pulls.pull_json(self.hub, row, ctx.viewer)

    def close_pull(self, ctx: Ctx) -> dict[str, Any]:
        row = pulls.close(self.hub, self._pull(ctx), ctx.user())
        return pulls.pull_json(self.hub, row, ctx.viewer)

    def comment_pull(self, ctx: Ctx) -> Response:
        row = self._pull(ctx)
        pulls.comment(self.hub, row, ctx.user(), ctx.field("body"))
        return JSONResponse(
            pulls.pull_json(self.hub, pulls.get_by_id(self.hub, row["id"]), ctx.viewer), 201
        )

    # --- trabajos -------------------------------------------------------------------------------

    def repo_jobs(self, ctx: Ctx) -> dict[str, Any]:
        repo = self.repo(ctx)
        return {
            "jobs": [
                jobs.job_json(self.hub, j, result=False) for j in jobs.listing(self.hub, repo=repo)
            ]
        }

    def new_job(self, ctx: Ctx) -> Response:
        repo = self.repo(ctx)
        user = ctx.user()
        kind = ctx.field("kind")
        row = registry.release(self.hub, repo, ctx.field("version", required=False) or "latest")
        if row["ir"] is None:
            raise bad("esa versión no tiene juego")
        ir = self.hub.blobs.get_json(row["ir"])
        options = ctx.field("options", dict, required=False, default={})
        if kind == "analyze":
            payload: dict[str, Any] = {"ir": ir}
        elif kind == "balance":
            payload = {"ir": ir, "options": options}
        elif kind == "arena":
            payload = {
                "ir": ir,
                "entrants": [str(e) for e in ctx.field("entrants", list)],
                "games": int(options.get("games", 10)),
                "players": options.get("players"),
                "tournament": options.get("tournament", "round-robin"),
            }
        else:
            raise bad("los trabajos que se pueden pedir son analyze, balance y arena")
        job_id = jobs.enqueue(self.hub, kind, payload, account=user, repo=repo, release=row)
        return JSONResponse(jobs.job_json(self.hub, jobs.get(self.hub, job_id)), 201)

    def job(self, ctx: Ctx) -> dict[str, Any]:
        row = jobs.get(self.hub, int(ctx.param("id")))
        if row["repo"] is not None:
            repo = self.hub.repo_by_id(row["repo"])
            if not self.hub.can_see(repo, ctx.viewer):
                raise not_found("no existe ese trabajo")
        return jobs.job_json(self.hub, row)

    # --- Pages ----------------------------------------------------------------------------------

    def list_pages(self, ctx: Ctx) -> dict[str, Any]:
        return {"pages": pages.listing(self.hub, self.repo(ctx))}

    def publish_page(self, ctx: Ctx) -> Response:
        repo = self.repo(ctx)
        name = ctx.query("name")
        if not name:
            raise bad("falta ?name=")
        out = pages.publish(
            self.hub,
            repo,
            ctx.user(),
            name,
            ctx.raw,
            interface_hash=ctx.query("interface"),
            version=ctx.query("version"),
        )
        return JSONResponse(out, 201)

    def delete_page(self, ctx: Ctx) -> dict[str, Any]:
        pages.delete(self.hub, self.repo(ctx), ctx.user(), ctx.param("page"))
        return {"ok": True}

    async def serve_page(self, request: Request) -> Response:
        p = request.path_params

        def find() -> Path:
            repo = self.hub.repo(p["owner"], p["name"])
            return pages.file_path(self.hub, repo, p["page"], p.get("path", ""))

        try:
            path = await asyncio.to_thread(find)
        except HubError:
            return PlainTextResponse("no existe", 404)
        response = FileResponse(path)
        response.headers["Content-Security-Policy"] = (
            "sandbox allow-scripts allow-forms allow-popups allow-modals"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    async def page_redirect(self, request: Request) -> Response:
        return RedirectResponse(str(request.url.path) + "/", 301)

    # --- explorar -------------------------------------------------------------------------------

    def search(self, ctx: Ctx) -> dict[str, Any]:
        def flag(name: str) -> bool | None:
            value = ctx.query(name)
            return None if value in (None, "") else value in ("1", "true", "yes")

        def number(name: str) -> float | None:
            value = ctx.query(name)
            try:
                return float(value) if value not in (None, "") else None
            except ValueError:
                raise bad(f"{name} tiene que ser un número") from None

        players = number("players")
        return explore.search(
            self.hub,
            q=ctx.query("q") or "",
            players=int(players) if players is not None else None,
            chance=flag("chance"),
            perfect_information=flag("perfect_information"),
            simultaneous=flag("simultaneous"),
            zero_sum=flag("zero_sum"),
            max_branching=number("max_branching"),
            max_length=number("max_length"),
            tags=[t for t in (ctx.query("tags") or "").split(",") if t],
            kind=ctx.query("kind"),
            owner=ctx.query("owner"),
            sort=ctx.query("sort") or "stars",
            limit=int(number("limit") or 30),
            offset=int(number("offset") or 0),
            viewer=ctx.viewer,
        )

    def explore_page(self, ctx: Ctx) -> dict[str, Any]:
        popular = explore.search(self.hub, sort="stars", limit=12, viewer=ctx.viewer)["results"]
        recent = explore.search(self.hub, sort="recent", limit=12, viewer=ctx.viewer)["results"]
        return {
            "popular": popular,
            "recent": recent,
            "events": self.hub.events(limit=30),
            "matches": play.recent_matches(self.hub, limit=10),
        }

    # --- jugar ----------------------------------------------------------------------------------

    def matchmaking_join(self, ctx: Ctx) -> Response:
        user = ctx.user()
        ref = ctx.field("game")
        game = self.catalog.get(ref)
        if game is None:
            raise not_found(f"no existe el juego {ref}")
        exact = self.catalog.ref_of(game) or ref
        n = play.check_players(game, ctx.field("players", int, required=False))
        rating = play.rating_of(self.hub, game.rules_hash, user)
        ticket = self.matchmaker.join(exact, n, user, rating, time.time())
        return JSONResponse(self._ticket(ticket), 201)

    def matchmaking_get(self, ctx: Ctx) -> dict[str, Any]:
        return self._ticket(self.matchmaker.ticket(ctx.param("id"), ctx.user()))

    def matchmaking_leave(self, ctx: Ctx) -> dict[str, Any]:
        self.matchmaker.leave(ctx.param("id"), ctx.user())
        return {"ok": True}

    def _ticket(self, t: play.Ticket) -> dict[str, Any]:
        waiting = sum(
            1
            for o in self.matchmaker.tickets.values()
            if o.game == t.game and o.players == t.players and o.room is None
        )
        return {
            "id": t.id,
            "game": t.game,
            "players": t.players,
            "status": "matched" if t.room else "waiting",
            "waiting": waiting,
            "room": t.room,
            "token": t.token,
            "seat": t.seat,
            "since": t.since,
        }

    def ratings_by_hash(self, ctx: Ctx) -> dict[str, Any]:
        rules = ctx.param("hash")
        return {
            "ratings": play.leaderboard(self.hub, rules),
            "matches": play.recent_matches(self.hub, rules),
        }

    # --- moderación -----------------------------------------------------------------------------

    def report(self, ctx: Ctx) -> Response:
        target = ctx.field("target")
        kind, _, ident = target.partition(":")
        if kind == "repo" and "/" in ident:
            owner, _, name = ident.partition("/")
            target = f"repo:{self.hub.repo(owner, name, ctx.viewer)['id']}"
        elif kind == "account" and not ident.isdigit():
            target = f"account:{self.hub.require_account(ident)['id']}"
        report_id = self.hub.report(ctx.viewer, target, ctx.field("reason"))
        return JSONResponse({"id": report_id}, 201)

    def admin_reports(self, ctx: Ctx) -> dict[str, Any]:
        return {"reports": self.hub.reports(ctx.user(), ctx.query("status") or "open")}

    def admin_resolve(self, ctx: Ctx) -> dict[str, Any]:
        self.hub.resolve_report(
            ctx.user(),
            int(ctx.param("id")),
            ctx.field("status"),
            ctx.field("resolution", required=False, default=""),
        )
        return {"ok": True}

    def admin_repo(self, ctx: Ctx) -> dict[str, Any]:
        user = self.hub.require_admin(ctx.viewer)
        repo = self.hub.repo(ctx.param("owner"), ctx.param("name"), user)
        self.hub.moderate_repo(user, repo, ctx.field("hidden", bool))
        return {"ok": True}

    def admin_account(self, ctx: Ctx) -> dict[str, Any]:
        user = self.hub.require_admin(ctx.viewer)
        self.hub.suspend(
            user, self.hub.require_account(ctx.param("name")), ctx.field("suspended", bool)
        )
        return {"ok": True}

    # --- git ------------------------------------------------------------------------------------

    async def git_http(self, request: Request) -> Response:
        owner, name, rest = (request.path_params[k] for k in ("owner", "name", "rest"))
        service = request.query_params.get("service")
        if rest == "info/refs" and service in ("git-upload-pack", "git-receive-pack"):
            write = service == "git-receive-pack"
        elif rest in ("git-upload-pack", "git-receive-pack") and request.method == "POST":
            write = rest == "git-receive-pack"
        else:
            return PlainTextResponse("solo git por HTTP inteligente", 404)
        challenge = {"WWW-Authenticate": 'Basic realm="GameHub"'}

        def check() -> tuple[Repo, Account | None, dict[str, str] | None]:
            viewer = self.viewer(request)
            repo = self.hub.repo(owner, name, viewer)
            if write:
                if viewer is None:
                    raise HubError(401, "unauthenticated", "empujar necesita un token")
                if not self.hub.can_write(repo, viewer):
                    raise forbidden("no puedes escribir en este repositorio")
                if repo["size"] > self.hub.config.quotas.repo_mb * 1024 * 1024:
                    raise HubError(413, "quota", "el repositorio ya ocupa el máximo")
                return repo, viewer, self.hub.git(repo).all_refs()
            return repo, viewer, None

        try:
            repo, viewer, before = await asyncio.to_thread(check)
        except HubError as exc:
            headers = (
                challenge
                if exc.status == 401
                or (exc.status == 404 and "authorization" not in request.headers)
                else {}
            )
            return PlainTextResponse(
                exc.message, 401 if exc.status == 401 else exc.status, headers=headers
            )
        limit = int(self.hub.config.quotas.push_mb * 1024 * 1024)
        chunks: list[bytes] = []
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > limit:
                return PlainTextResponse("el push es demasiado grande", 413)
            chunks.append(chunk)
        body = b"".join(chunks)
        env = {
            "GIT_PROJECT_ROOT": str(self.hub.repos_dir),
            "PATH_INFO": f"/{repo['id']}.git/{rest}",
            "REQUEST_METHOD": request.method,
            "QUERY_STRING": request.url.query,
            "CONTENT_TYPE": request.headers.get("content-type", ""),
            "CONTENT_LENGTH": str(len(body)),
            "REMOTE_USER": viewer["name"] if viewer else "",
            "REMOTE_ADDR": request.client.host if request.client else "",
            "GIT_HTTP_EXPORT_ALL": "1",
        }
        if request.headers.get("content-encoding"):
            env["HTTP_CONTENT_ENCODING"] = request.headers["content-encoding"]
        if request.headers.get("git-protocol"):
            env["GIT_PROTOCOL"] = request.headers["git-protocol"]
        proc = await asyncio.create_subprocess_exec(
            "git",
            "http-backend",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=git_env(env),
        )
        out, _ = await proc.communicate(body)
        head, sep, payload = out.partition(b"\r\n\r\n")
        if not sep:
            head, _, payload = out.partition(b"\n\n")
        status = 200
        headers: dict[str, str] = {}
        for line in head.decode("latin-1").splitlines():
            key, _, value = line.partition(":")
            if key.lower() == "status":
                status = int(value.strip().split()[0])
            elif key:
                headers[key.strip()] = value.strip()
        if write and before is not None and rest == "git-receive-pack":
            await asyncio.to_thread(self.hub.pushed, repo, viewer, before)
        media = headers.pop("Content-Type", None)
        return Response(payload, status_code=status, headers=headers, media_type=media)

    # --- web ------------------------------------------------------------------------------------

    async def web_route(self, request: Request) -> Response:
        if self.web is None:
            return HTMLResponse(_NO_WEB, 404 if request.url.path != "/" else 200)
        path = request.path_params.get("path", "")
        if path and not path.startswith("api/"):
            candidate = (self.web / path).resolve()
            if candidate.is_relative_to(self.web.resolve()) and candidate.is_file():
                return FileResponse(candidate)
        if path.startswith("api/"):
            return _error(404, "not_found", "no existe esa ruta de la API")
        return FileResponse(self.web / "index.html", headers={"Cache-Control": "no-cache"})

    # --- rutas ----------------------------------------------------------------------------------

    def routes(self) -> list[BaseRoute]:
        a = self.api
        r = "/api/v1/repos/{owner}/{name}"
        s = self.server
        routes: list[BaseRoute] = [
            Route("/api/v1/hub", a(self.info)),
            Route("/api/v1/terms", a(self.terms)),
            Route("/api/v1/auth/signup", a(self.signup), methods=["POST"]),
            Route("/api/v1/auth/login", a(self.login), methods=["POST"]),
            Route("/api/v1/auth/logout", a(self.logout), methods=["POST"]),
            Route("/api/v1/auth/token", a(self.token_login), methods=["POST"]),
            Route("/api/v1/session", a(self.session)),
            Route("/api/v1/me", a(self.me), methods=["GET"]),
            Route("/api/v1/me", a(self.update_me), methods=["PATCH"]),
            Route("/api/v1/me/terms", a(self.accept_terms), methods=["POST"]),
            Route("/api/v1/me/tokens", a(self.tokens), methods=["GET"]),
            Route("/api/v1/me/tokens", a(self.new_token), methods=["POST"]),
            Route("/api/v1/me/tokens/{id:int}", a(self.revoke_token), methods=["DELETE"]),
            Route("/api/v1/accounts/{name}", a(self.account)),
            Route("/api/v1/orgs", a(self.create_org), methods=["POST"]),
            Route(
                "/api/v1/orgs/{org}/members/{name}", a(self.set_member), methods=["PUT", "DELETE"]
            ),
            Route("/api/v1/templates", a(self.templates)),
            Route("/api/v1/repos", a(self.create_repo), methods=["POST"]),
            Route(r, a(self.get_repo), methods=["GET"]),
            Route(r, a(self.update_repo), methods=["PATCH"]),
            Route(r, a(self.delete_repo), methods=["DELETE"]),
            Route(r + "/forks", a(self.fork), methods=["POST"]),
            Route(r + "/star", a(self.star), methods=["PUT", "DELETE"]),
            Route(r + "/branches", a(self.branches)),
            Route(r + "/commits", a(self.commits)),
            Route(r + "/tree", a(self.tree)),
            Route(r + "/file", a(self.file)),
            Route(r + "/raw", a(self.raw_file)),
            Route(r + "/files", a(self.commit), methods=["POST"]),
            Route(r + "/compiled", a(self.compiled)),
            Route(r + "/events", a(self.events)),
            Route(r + "/family", a(self.family)),
            Route(r + "/releases", a(self.releases), methods=["GET"]),
            Route(r + "/releases", a(self.publish), methods=["POST"]),
            Route(r + "/releases/{version}", a(self.get_release)),
            Route(r + "/releases/{version}/ir", a(self.release_ir)),
            Route(r + "/releases/{version}/view", a(self.release_view)),
            Route(r + "/releases/{version}/yank", a(self.yank), methods=["POST"]),
            Route(r + "/resolve", a(self.resolve)),
            Route(r + "/ratings", a(self.ratings)),
            Route(r + "/pulls", a(self.pulls), methods=["GET"]),
            Route(r + "/pulls", a(self.open_pull), methods=["POST"]),
            Route(r + "/pulls/{number:int}", a(self.get_pull)),
            Route(r + "/pulls/{number:int}/diff", a(self.pull_diff)),
            Route(r + "/pulls/{number:int}/merge", a(self.merge_pull), methods=["POST"]),
            Route(r + "/pulls/{number:int}/close", a(self.close_pull), methods=["POST"]),
            Route(r + "/pulls/{number:int}/comments", a(self.comment_pull), methods=["POST"]),
            Route(r + "/jobs", a(self.repo_jobs), methods=["GET"]),
            Route(r + "/jobs", a(self.new_job), methods=["POST"]),
            Route(r + "/pages", a(self.list_pages), methods=["GET"]),
            Route(r + "/pages", a(self.publish_page, raw=True), methods=["POST"]),
            Route(r + "/pages/{page}", a(self.delete_page), methods=["DELETE"]),
            Route("/api/v1/jobs/{id:int}", a(self.job)),
            Route("/api/v1/search", a(self.search)),
            Route("/api/v1/explore", a(self.explore_page)),
            Route("/api/v1/matchmaking", a(self.matchmaking_join), methods=["POST"]),
            Route("/api/v1/matchmaking/{id}", a(self.matchmaking_get), methods=["GET"]),
            Route("/api/v1/matchmaking/{id}", a(self.matchmaking_leave), methods=["DELETE"]),
            Route("/api/v1/ratings/{hash}", a(self.ratings_by_hash)),
            Route("/api/v1/reports", a(self.report), methods=["POST"]),
            Route("/api/v1/admin/reports", a(self.admin_reports)),
            Route("/api/v1/admin/reports/{id:int}", a(self.admin_resolve), methods=["POST"]),
            Route("/api/v1/admin/repos/{owner}/{name}", a(self.admin_repo), methods=["POST"]),
            Route("/api/v1/admin/accounts/{name}", a(self.admin_account), methods=["POST"]),
            # El servidor de partidas.
            Route("/api/v1/info", s.info),
            Route("/api/v1/rooms", s.list_rooms, methods=["GET"]),
            Route("/api/v1/rooms", s.create_room, methods=["POST"]),
            Route("/api/v1/rooms/{code}", s.room_info),
            Route("/api/v1/rooms/{code}/ir", s.room_ir),
            Route("/api/v1/rooms/{code}/qr.svg", s.room_qr),
            Route("/api/v1/games/{id:path}", s.game_ir),
            Route("/api/v1/matches", s.matches),
            Route("/api/v1/replays/{id}", s.replay),
            Route("/api/v1/replays/{id}/frames", s.replay_frames),
            WebSocketRoute("/ws", s.websocket),
            # OAuth, Pages y git.
            Route("/auth/{provider}/login", self.oauth_login),
            Route("/auth/{provider}/callback", self.oauth_callback),
            Route("/pages/{owner}/{name}/{page}", self.page_redirect),
            Route("/pages/{owner}/{name}/{page}/{path:path}", self.serve_page),
            Route("/{owner}/{name}.git/{rest:path}", self.git_http, methods=["GET", "POST"]),
            # La app web.
            Route("/{path:path}", self.web_route),
        ]
        return routes

    def app(self) -> Starlette:
        app = Starlette(routes=self.routes(), lifespan=self.lifespan)
        app.state.hub = self
        return app


def _template_files(name: str, template: str, title: str | None) -> dict[str, str]:
    """Un paquete nuevo a partir de una plantilla (`gamehub new --template`)."""
    from gamehub import gametemplates
    from gamehub.packages import Manifest, camel, manifest_toml

    if template not in gametemplates.ids():
        raise bad(f"plantilla desconocida: {template}")
    if not acc.valid_name(name):
        raise bad(f"nombre de repositorio no válido: {name!r}")
    text = gametemplates.render(
        template, title=title or name.replace("-", " ").capitalize(), game=camel(name)
    )
    manifest = Manifest(root=Path("."), name=name, license="CC-BY-4.0")
    return {f"{name}.game": text, "game.toml": manifest_toml(manifest)}


def _error(status: int, code: str, message: str) -> Response:
    return JSONResponse({"error": {"code": code, "message": message}}, status)


_NO_WEB = (
    "<!doctype html><meta charset=utf-8><title>GameHub</title><h1>GameHub</h1>"
    "<p>La API está en <code>/api/v1</code>. La app web no está compilada: ejecuta "
    "<code>pnpm build</code> en la raíz del repositorio.</p>"
)


def create_app(hub: Hub, *, web: Path | None = None, workers: int | None = None) -> Starlette:
    return HubApp(hub, web=web, workers=workers).app()
