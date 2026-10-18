# SPDX-License-Identifier: AGPL-3.0-or-later
"""Credenciales del hub: contraseñas, sesiones del navegador, tokens de API y OAuth.

- **Contraseñas**: scrypt (de la biblioteca estándar) con sal; nunca se guardan en claro.
- **Sesiones**: una cookie `gh_session` con un secreto aleatorio; en la base de datos, solo su
  SHA-256 (si se filtra la base, las sesiones no sirven).
- **Tokens de API** (`ghb_…`): para la CLI y para git (`git push` con el token como contraseña);
  también se guardan solo como hash.
- **OAuth 2** (código de autorización con `state`): GitHub, Google o cualquier proveedor con
  `authorize_url`, `token_url` y `userinfo_url`.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from gamehub.hub.config import OAuthProvider

#: Nombres de cuenta y de repositorio: minúsculas, números y guiones (como los paquetes).
NAME = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")
#: Nombres que no pueden ser cuentas: chocan con rutas del hub o confunden.
RESERVED = frozenset(
    {
        "about", "admin", "api", "assets", "auth", "explore", "favicon", "help", "hub", "kit",
        "local", "login", "logout", "new", "pages", "r", "replay", "search", "settings",
        "signup", "static", "std", "terms", "ws", "gamehub", "root", "system", "play",
    }
)  # fmt: skip

SESSION_COOKIE = "gh_session"
SESSION_DAYS = 30
TOKEN_PREFIX = "ghb_"


def valid_name(name: str) -> bool:
    return 2 <= len(name) <= 39 and NAME.match(name) is not None


def check_name(name: str, what: str = "nombre") -> str | None:
    """Por qué no vale un nombre de cuenta o de repositorio (None si vale)."""
    if not valid_name(name):
        return f"{what} no válido: {name!r} (2 a 39 minúsculas, números y guiones)"
    if name in RESERVED:
        return f"{what} reservado: {name!r}"
    return None


# --- contraseñas --------------------------------------------------------------------------------

_SCRYPT = {"n": 2**14, "r": 8, "p": 1}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, dklen=32, **_SCRYPT)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def check_password(password: str, stored: str | None) -> bool:
    if not stored or not stored.startswith("scrypt$"):
        return False
    _, salt, digest = stored.split("$")
    got = hashlib.scrypt(password.encode("utf-8"), salt=base64.b64decode(salt), dklen=32, **_SCRYPT)
    return hmac.compare_digest(got, base64.b64decode(digest))


def password_problem(password: str) -> str | None:
    if len(password) < 8:
        return "la contraseña necesita al menos 8 caracteres"
    if len(password) > 256:
        return "la contraseña es demasiado larga"
    return None


# --- sesiones y tokens --------------------------------------------------------------------------


def new_secret(prefix: str = "") -> str:
    return prefix + secrets.token_urlsafe(30)


def secret_hash(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


# --- OAuth --------------------------------------------------------------------------------------

#: Cómo hace el hub sus peticiones HTTP a los proveedores (los tests ponen uno falso):
#: (método, URL, cabeceras, cuerpo) -> JSON de la respuesta.
Fetch = Callable[[str, str, dict[str, str], bytes | None], dict[str, Any]]


def http_fetch(method: str, url: str, headers: dict[str, str], body: bytes | None) -> Any:
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def authorize_url(provider: OAuthProvider, redirect_uri: str, state: str) -> str:
    query = {
        "client_id": provider.client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "state": state,
    }
    if provider.scope:
        query["scope"] = provider.scope
    sep = "&" if "?" in provider.authorize_url else "?"
    return provider.authorize_url + sep + urllib.parse.urlencode(query)


def oauth_identity(
    provider: OAuthProvider, code: str, redirect_uri: str, fetch: Fetch = http_fetch
) -> dict[str, str]:
    """Cambia el código por un token y pide quién es: {subject, login, name, email}."""
    body = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": provider.client_id,
            "client_secret": provider.client_secret,
        }
    ).encode()
    token = fetch(
        "POST",
        provider.token_url,
        {"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
        body,
    )
    access = token.get("access_token") if isinstance(token, dict) else None
    if not isinstance(access, str):
        raise ValueError(f"{provider.title} no dio un token de acceso")
    info = fetch(
        "GET",
        provider.userinfo_url,
        {"Accept": "application/json", "Authorization": f"Bearer {access}"},
        None,
    )
    if not isinstance(info, dict) or info.get(provider.id_field) in (None, ""):
        raise ValueError(f"{provider.title} no dijo quién eres")
    login = str(info.get(provider.login_field) or "")
    return {
        "subject": str(info[provider.id_field]),
        "login": login.split("@")[0],
        "name": str(info.get(provider.name_field) or login),
        "email": str(info.get(provider.email_field) or ""),
    }


def suggest_name(login: str) -> str:
    """Un nombre de cuenta válido a partir del de otro servicio (`Juan_Martín` → `juan-mart-n`)."""
    text = re.sub(r"[^a-z0-9]+", "-", login.lower()).strip("-")
    text = re.sub(r"^[0-9-]+", "", text)
    text = text[:39].strip("-")
    return text if valid_name(text) and text not in RESERVED else "jugador"
