# SPDX-License-Identifier: AGPL-3.0-or-later
"""Configuración del hub (`hub.toml`, opcional; todo tiene un valor por defecto).

name = "GameHub"
public_url = "https://hub.example.org"    # la dirección con la que lo ven los demás
database = "postgresql://hub@localhost/hub"  # por defecto, SQLite en el directorio de datos
signup = true                             # registro con contraseña abierto
admins = ["juanma"]                       # cuentas con permisos de moderación

[quotas]
repos = 100                 # repositorios por cuenta
repo_mb = 50                # tamaño de un repositorio
push_mb = 20                # tamaño de un push
jobs_per_day = 50           # trabajos (análisis, balance, arena) por cuenta y día
concurrent_jobs = 2
job_seconds = 600           # tiempo real máximo de un trabajo
job_cpu_seconds = 300
job_memory_mb = 1024
pages_mb = 20               # tamaño de una interfaz publicada (Pages)

[oauth.github]              # proveedores de OAuth: github, google o uno genérico
client_id = "…"
client_secret = "…"

[oauth.mi-sso]
authorize_url = "https://sso.example.org/authorize"
token_url = "https://sso.example.org/token"
userinfo_url = "https://sso.example.org/userinfo"
client_id = "…"
client_secret = "…"
scope = "openid profile email"
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: Versión de las condiciones de uso por defecto (cambiarla obliga a aceptarlas de nuevo).
TERMS_VERSION = "2026-10-18"


@dataclass(frozen=True)
class Quotas:
    repos: int = 100
    repo_mb: float = 50
    push_mb: float = 20
    jobs_per_day: int = 50
    concurrent_jobs: int = 2
    job_seconds: float = 600
    job_cpu_seconds: int = 300
    job_memory_mb: int = 1024
    pages_mb: float = 20


@dataclass(frozen=True)
class OAuthProvider:
    name: str
    title: str
    authorize_url: str
    token_url: str
    userinfo_url: str
    client_id: str
    client_secret: str
    scope: str = ""
    #: Campos de la respuesta de `userinfo`: identificador, nombre de usuario, nombre visible y
    #: correo.
    id_field: str = "id"
    login_field: str = "login"
    name_field: str = "name"
    email_field: str = "email"


#: Proveedores conocidos: basta con `client_id` y `client_secret`.
KNOWN_PROVIDERS: dict[str, dict[str, str]] = {
    "github": {
        "title": "GitHub",
        "authorize_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "userinfo_url": "https://api.github.com/user",
        "scope": "read:user user:email",
    },
    "google": {
        "title": "Google",
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "userinfo_url": "https://openidconnect.googleapis.com/v1/userinfo",
        "scope": "openid profile email",
        "id_field": "sub",
        "login_field": "email",
    },
}


@dataclass(frozen=True)
class HubConfig:
    data: Path
    name: str = "GameHub"
    public_url: str | None = None
    database: str | None = None
    signup: bool = True
    admins: tuple[str, ...] = ()
    quotas: Quotas = field(default_factory=Quotas)
    oauth: dict[str, OAuthProvider] = field(default_factory=dict)
    terms_version: str = TERMS_VERSION
    #: Procesos que ejecutan trabajos a la vez (0: ninguno; los trabajos esperan en la cola).
    workers: int = 1
    #: Cookies solo por HTTPS (actívalo detrás de un proxy con TLS).
    secure_cookies: bool = False

    @property
    def database_url(self) -> str:
        return self.database or f"sqlite://{self.data / 'hub.db'}"

    @classmethod
    def load(cls, data: Path, path: Path | None = None, **overrides: Any) -> HubConfig:
        raw: dict[str, Any] = {}
        if path is not None:
            try:
                raw = tomllib.loads(path.read_text(encoding="utf-8"))
            except (OSError, tomllib.TOMLDecodeError) as exc:
                raise ValueError(f"{path}: {exc}") from None
        quotas = Quotas(**raw.pop("quotas", {}))
        oauth = {name: _provider(name, spec) for name, spec in raw.pop("oauth", {}).items()}
        raw.update({k: v for k, v in overrides.items() if v is not None})
        if "admins" in raw:
            raw["admins"] = tuple(raw["admins"])
        return cls(data=data, quotas=quotas, oauth=oauth, **raw)


def _provider(name: str, spec: dict[str, Any]) -> OAuthProvider:
    merged = {**KNOWN_PROVIDERS.get(name, {}), **spec}
    merged.setdefault("title", name)
    missing = [
        k
        for k in ("authorize_url", "token_url", "userinfo_url", "client_id", "client_secret")
        if not merged.get(k)
    ]
    if missing:
        raise ValueError(f"[oauth.{name}]: falta {', '.join(missing)}")
    return OAuthProvider(name=name, **merged)
