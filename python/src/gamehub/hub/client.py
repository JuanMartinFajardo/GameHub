# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cliente del hub para la CLI: la API REST (con el token de `gamehub login`) y git.

Las credenciales se guardan en `~/.config/gamehub/hub.toml` (o en `$GAMEHUB_CONFIG/hub.toml`),
legible solo por su dueño:

    default = "http://localhost:7430"

    [hubs."http://localhost:7430"]
    user = "juanma"
    token = "ghb_…"

El hub que se usa: el que se indica (`--hub`), si no `GAMEHUB_HUB` y si no el último con el que se
entró. Con git, el token viaja en una cabecera de esa orden (`http.extraHeader`), nunca en la URL
ni en la configuración del repositorio.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_PORT = 7430


class ClientError(Exception):
    """Una petición al hub que no salió bien (con su código, si el hub lo dio)."""

    def __init__(self, message: str, code: str | None = None, status: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


def config_path() -> Path:
    base = os.environ.get("GAMEHUB_CONFIG")
    return (Path(base) if base else Path.home() / ".config" / "gamehub") / "hub.toml"


def load_config() -> dict[str, Any]:
    path = config_path()
    if not path.is_file():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ClientError(f"{path}: {exc}") from None


def save_config(data: dict[str, Any]) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    if data.get("default"):
        lines.append(f"default = {json.dumps(data['default'])}")
    for url, entry in sorted(data.get("hubs", {}).items()):
        lines += ["", f"[hubs.{json.dumps(url)}]"]
        for key in ("user", "token"):
            if entry.get(key):
                lines.append(f"{key} = {json.dumps(entry[key])}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o600)


def normalize_url(url: str) -> str:
    url = url.strip().rstrip("/")
    if "://" not in url:
        url = "http://" + url
    parts = urllib.parse.urlsplit(url)
    if (
        parts.port is None
        and parts.scheme == "http"
        and parts.hostname in ("localhost", "127.0.0.1")
    ):
        url = f"{parts.scheme}://{parts.hostname}:{DEFAULT_PORT}{parts.path}"
    return url


def hub_url(explicit: str | None = None) -> str:
    url = explicit or os.environ.get("GAMEHUB_HUB") or load_config().get("default")
    if not url:
        raise ClientError("¿qué hub? Usa --hub URL, GAMEHUB_HUB o `gamehub login --hub URL`")
    return normalize_url(url)


def credentials(url: str) -> dict[str, str]:
    return load_config().get("hubs", {}).get(url, {})


class Hub:
    """Una conexión (sin estado) con un hub."""

    def __init__(self, url: str | None = None, token: str | None = None) -> None:
        self.url = hub_url(url)
        saved = credentials(self.url)
        self.token = token if token is not None else saved.get("token")
        self.user = saved.get("user")

    def request(
        self,
        method: str,
        path: str,
        body: Any = None,
        *,
        query: dict[str, Any] | None = None,
        auth: bool = True,
        headers: dict[str, str] | None = None,
    ) -> Any:
        url = self.url + "/api/v1" + path
        if query:
            url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
        data = None
        all_headers = {"Accept": "application/json", **(headers or {})}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            all_headers["Content-Type"] = "application/json"
        if auth and self.token:
            all_headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(url, data=data, headers=all_headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raise _error(exc) from None
        except urllib.error.URLError as exc:
            raise ClientError(f"no se puede conectar con {self.url}: {exc.reason}") from None
        return json.loads(raw) if raw else None

    def get(self, path: str, **query: Any) -> Any:
        return self.request("GET", path, query=query or None)

    def post(self, path: str, body: Any = None) -> Any:
        return self.request("POST", path, body if body is not None else {})

    def git_url(self, full_name: str) -> str:
        return f"{self.url}/{full_name}.git"

    def git(self, *args: str, cwd: Path | None = None) -> str:
        """Una orden de git contra el hub, con el token en una cabecera de esta orden."""
        extra: list[str] = []
        if self.token:
            basic = base64.b64encode(f"{self.user or 'token'}:{self.token}".encode()).decode()
            extra = ["-c", f"http.extraHeader=Authorization: Basic {basic}"]
        env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
        done = subprocess.run(
            ["git", *extra, *args], cwd=cwd, capture_output=True, text=True, env=env
        )
        if done.returncode != 0:
            lines = [ln for ln in done.stderr.strip().splitlines() if ln.strip()]
            raise ClientError(f"git {args[0]}: {lines[-1] if lines else done.returncode}")
        return done.stdout.strip()


def _error(exc: urllib.error.HTTPError) -> ClientError:
    try:
        data = json.loads(exc.read() or b"{}")
        err = data.get("error", {})
        return ClientError(err.get("message") or str(exc), err.get("code"), exc.code)
    except ValueError:
        return ClientError(f"el hub respondió {exc.code}", None, exc.code)


def login(url: str, user: str, password: str, token_name: str = "gamehub-cli") -> dict[str, str]:
    """Pide un token de API con usuario y contraseña y lo guarda como hub por defecto."""
    hub = Hub(url, token="")
    result = hub.request(
        "POST",
        "/auth/token",
        {"name": user, "password": password, "token_name": token_name},
        auth=False,
    )
    config = load_config()
    config.setdefault("hubs", {})[hub.url] = {
        "user": result["user"]["name"],
        "token": result["token"],
    }
    config["default"] = hub.url
    save_config(config)
    return {"url": hub.url, "user": result["user"]["name"]}


def save_token(url: str, user: str, token: str) -> None:
    config = load_config()
    config.setdefault("hubs", {})[normalize_url(url)] = {"user": user, "token": token}
    config["default"] = normalize_url(url)
    save_config(config)


def logout(url: str | None = None) -> str:
    config = load_config()
    target = hub_url(url)
    config.get("hubs", {}).pop(target, None)
    if config.get("default") == target:
        config.pop("default", None)
    save_config(config)
    return target


def resolve_dependency(
    full_name: str, requirement: str, *, registry: str | None = None
) -> dict[str, str]:
    """La versión más alta de `dueño/nombre` que cumple el requisito: {version, commit, git}."""
    hub = Hub(registry)
    return hub.get(f"/repos/{full_name}/resolve", requirement=requirement)
