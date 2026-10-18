# SPDX-License-Identifier: AGPL-3.0-or-later
"""Un hub de verdad para los tests: en un hilo, en 127.0.0.1 y un puerto libre, con sus datos en
un directorio temporal. Los trabajos no corren solos (`workers=0`): el test los ejecuta con
`run_jobs()` cuando quiere."""

from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from gamehub.hub import jobs
from gamehub.hub.app import HubApp
from gamehub.hub.config import HubConfig, Quotas
from gamehub.hub.service import Hub
from gamehub.server.run import Server, config

ROOT = Path(__file__).resolve().parents[2]


def postgres_url() -> str | None:
    """Con `GAMEHUB_TEST_POSTGRES` (una base de datos de pruebas, que se vacía), los hubs de los
    tests usan PostgreSQL en vez de SQLite."""
    url = os.environ.get("GAMEHUB_TEST_POSTGRES")
    if not url:
        return None
    import psycopg

    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
    return url


class HubThread:
    def __init__(self, data: Path, *, web: Path | None = None, **options: Any) -> None:
        options.setdefault("admins", ("mod",))
        options.setdefault("database", postgres_url())
        options.setdefault("quotas", Quotas(jobs_per_day=20, concurrent_jobs=5))
        self.hub = Hub(HubConfig(data=data, workers=0, **options))
        self.app = HubApp(self.hub, web=web, workers=0)
        self.server = Server(config(self.app.app(), "127.0.0.1", 0))
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self) -> HubThread:
        self.thread.start()
        for _ in range(1000):
            if self.server.started:
                return self
            if not self.thread.is_alive():
                break
            threading.Event().wait(0.01)
        raise OSError("el hub no ha arrancado")

    def __exit__(self, *exc: object) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)
        self.hub.close()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.port}"

    def run_jobs(self) -> int:
        return jobs.run_pending(self.hub)

    def user(self, name: str, password: str = "contraseña-segura") -> User:
        """Una cuenta nueva con su token de API."""
        api = User(self.url, None)
        api.call(
            "POST",
            "/auth/signup",
            {"name": name, "password": password, "terms": self.hub.config.terms_version},
        )
        token = api.call(
            "POST", "/auth/token", {"name": name, "password": password, "token_name": "tests"}
        )["token"]
        return User(self.url, token, name)


class ApiError(Exception):
    def __init__(self, status: int, body: dict[str, Any]) -> None:
        super().__init__(f"{status}: {body}")
        self.status = status
        self.code = body.get("error", {}).get("code")
        self.body = body


class User:
    """Peticiones a la API como una cuenta (o anónimas, sin token)."""

    def __init__(self, url: str, token: str | None, name: str = "") -> None:
        self.url = url
        self.token = token
        self.name = name

    def call(
        self,
        method: str,
        path: str,
        body: Any = None,
        *,
        raw: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        h = {"Accept": "application/json", **(headers or {})}
        if body is not None:
            h["Content-Type"] = "application/json"
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(
            self.url + "/api/v1" + path, data=data, headers=h, method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                text = response.read()
                if response.headers.get("content-type", "").startswith("application/json"):
                    return json.loads(text) if text else None
                return text.decode("utf-8")
        except urllib.error.HTTPError as exc:
            payload = exc.read()
            try:
                parsed = json.loads(payload)
            except ValueError:
                parsed = {"text": payload.decode("utf-8", "replace")}
            raise ApiError(exc.code, parsed) from None

    def get(self, path: str) -> Any:
        return self.call("GET", path)

    def post(self, path: str, body: Any = None) -> Any:
        return self.call("POST", path, body if body is not None else {})


def package_files(game: str) -> dict[str, str]:
    """Los archivos de texto de un paquete del catálogo (sin las UIs propias)."""
    root = ROOT / "games" / game
    out = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if (
            path.is_file()
            and rel.parts[0] not in ("ui", "node_modules")
            and path.suffix
            in (
                ".game",
                ".toml",
                ".md",
                ".json",
            )
        ):
            out[str(rel)] = path.read_text(encoding="utf-8")
    return out
