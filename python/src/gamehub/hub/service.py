# SPDX-License-Identifier: AGPL-3.0-or-later
"""El hub como servicio: cuentas, organizaciones, permisos, repositorios, forks, archivos,
estrellas, actividad y moderación, sobre la base de datos, el almacén de objetos y git.

Sin HTTP: la app (`gamehub.hub.app`) traduce peticiones a llamadas de aquí y los `HubError` a
respuestas. Las versiones, las propuestas, los trabajos, el juego en línea y las Pages viven en
sus propios módulos, que reciben un `Hub`.

Permisos: el dueño de un repositorio (una cuenta) o los miembros de su organización escriben en
él; los dueños de la organización, además, lo administran; los administradores del hub moderan
(ocultan repositorios, suspenden cuentas). Un repositorio oculto solo lo ven su dueño y los
administradores.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from gamehub.hub import accounts as acc
from gamehub.hub.blobs import BlobStore
from gamehub.hub.config import HubConfig
from gamehub.hub.db import Database, Row
from gamehub.hub.gitrepo import Author, GitError, GitRepo
from gamehub.packages import MANIFEST

Account = Row
Repo = Row


class HubError(Exception):
    """Un error que llega al cliente: estado HTTP, código estable y mensaje."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def not_found(what: str = "no existe") -> HubError:
    return HubError(404, "not_found", what)


def forbidden(what: str = "no tienes permiso para hacerlo") -> HubError:
    return HubError(403, "forbidden", what)


def bad(what: str) -> HubError:
    return HubError(400, "bad_request", what)


class Hub:
    def __init__(self, config: HubConfig, db: Database | None = None) -> None:
        self.config = config
        config.data.mkdir(parents=True, exist_ok=True)
        self.db = db or Database.open(config.database_url)
        self.blobs = BlobStore(config.data / "objects")
        self.repos_dir = config.data / "repos"
        self.tmp_dir = config.data / "tmp"
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        #: Lo que hacen los demás módulos al ocurrir algo (p. ej. encolar el análisis de una
        #: versión nueva): nombre del suceso -> funciones.
        self.listeners: dict[str, list[Any]] = {}

    @staticmethod
    def now() -> float:
        return time.time()

    def close(self) -> None:
        self.db.close()

    def on(self, event: str, fn: Any) -> None:
        self.listeners.setdefault(event, []).append(fn)

    def emit(self, event: str, *args: Any) -> None:
        for fn in self.listeners.get(event, []):
            fn(*args)

    # --- cuentas --------------------------------------------------------------------------------

    def account(self, name: str) -> Account | None:
        return self.db.one("SELECT * FROM accounts WHERE name = ?", (name.lower(),))

    def account_by_id(self, account_id: int) -> Account:
        row = self.db.one("SELECT * FROM accounts WHERE id = ?", (account_id,))
        if row is None:
            raise not_found("no existe esa cuenta")
        return row

    def require_account(self, name: str) -> Account:
        row = self.account(name)
        if row is None:
            raise not_found(f"no existe la cuenta {name}")
        return row

    def _new_account(
        self,
        name: str,
        kind: str,
        *,
        display: str = "",
        email: str | None = None,
        password: str | None = None,
        terms: str | None = None,
    ) -> Account:
        problem = acc.check_name(name, "nombre de cuenta")
        if problem:
            raise bad(problem)
        if self.account(name) is not None:
            raise HubError(409, "taken", f"el nombre {name} ya está cogido")
        admin = 1 if name in self.config.admins and kind == "user" else 0
        account_id = self.db.insert(
            "INSERT INTO accounts (name, kind, display, email, password, admin, terms, created)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (name, kind, display or name, email, password, admin, terms, self.now()),
        )
        return self.account_by_id(account_id)

    def signup(
        self,
        name: str,
        password: str,
        *,
        email: str | None = None,
        display: str = "",
        terms: str | None = None,
    ) -> Account:
        if not self.config.signup:
            raise forbidden("el registro con contraseña está cerrado en este hub")
        if terms != self.config.terms_version:
            raise HubError(400, "terms", "hay que aceptar las condiciones de uso")
        problem = acc.password_problem(password)
        if problem:
            raise bad(problem)
        return self._new_account(
            name,
            "user",
            display=display,
            email=email,
            password=acc.hash_password(password),
            terms=terms,
        )

    def login(self, name: str, password: str) -> Account:
        row = self.account(name)
        if (
            row is None
            or row["kind"] != "user"
            or not acc.check_password(password, row["password"])
        ):
            raise HubError(401, "bad_credentials", "usuario o contraseña incorrectos")
        if row["suspended"]:
            raise forbidden("esta cuenta está suspendida")
        return row

    def accept_terms(self, account: Account, version: str) -> None:
        if version != self.config.terms_version:
            raise bad("esa no es la versión vigente de las condiciones")
        self.db.execute("UPDATE accounts SET terms = ? WHERE id = ?", (version, account["id"]))

    def update_profile(self, account: Account, *, display: str | None, bio: str | None) -> None:
        if display is not None:
            self.db.execute(
                "UPDATE accounts SET display = ? WHERE id = ?", (display[:80], account["id"])
            )
        if bio is not None:
            self.db.execute("UPDATE accounts SET bio = ? WHERE id = ?", (bio[:500], account["id"]))

    def oauth_account(self, provider: str, identity: dict[str, str]) -> Account:
        """La cuenta de una identidad de OAuth (se crea la primera vez, con un nombre libre
        parecido al del proveedor)."""
        found = self.db.one(
            "SELECT account FROM identities WHERE provider = ? AND subject = ?",
            (provider, identity["subject"]),
        )
        if found is not None:
            row = self.account_by_id(found["account"])
            if row["suspended"]:
                raise forbidden("esta cuenta está suspendida")
            return row
        base = acc.suggest_name(identity["login"] or identity["name"])
        name, n = base, 1
        while self.account(name) is not None or name in acc.RESERVED:
            n += 1
            name = f"{base[:35]}-{n}"
        with self.db.transaction():
            row = self._new_account(
                name, "user", display=identity["name"], email=identity["email"] or None
            )
            self.db.execute(
                "INSERT INTO identities (provider, subject, account) VALUES (?, ?, ?)",
                (provider, identity["subject"], row["id"]),
            )
        return row

    def public_account(self, row: Account, *, private: bool = False) -> dict[str, Any]:
        out: dict[str, Any] = {
            "name": row["name"],
            "kind": row["kind"],
            "display": row["display"],
            "bio": row["bio"],
            "created": row["created"],
        }
        if row["admin"]:
            out["admin"] = True
        if row["suspended"]:
            out["suspended"] = True
        if private:
            out["email"] = row["email"]
            out["terms"] = row["terms"]
            out["terms_current"] = row["terms"] == self.config.terms_version
            out["orgs"] = [
                r["name"]
                for r in self.db.all(
                    "SELECT a.name FROM members m JOIN accounts a ON a.id = m.org"
                    " WHERE m.account = ? ORDER BY a.name",
                    (row["id"],),
                )
            ]
        return out

    # --- sesiones y tokens ----------------------------------------------------------------------

    def new_session(self, account: Account) -> str:
        secret = acc.new_secret()
        now = self.now()
        self.db.execute(
            "INSERT INTO sessions (hash, account, created, expires) VALUES (?, ?, ?, ?)",
            (acc.secret_hash(secret), account["id"], now, now + acc.SESSION_DAYS * 86400),
        )
        return secret

    def session_account(self, secret: str) -> Account | None:
        row = self.db.one(
            "SELECT a.* FROM sessions s JOIN accounts a ON a.id = s.account"
            " WHERE s.hash = ? AND s.expires > ?",
            (acc.secret_hash(secret), self.now()),
        )
        return None if row is None or row["suspended"] else row

    def end_session(self, secret: str) -> None:
        self.db.execute("DELETE FROM sessions WHERE hash = ?", (acc.secret_hash(secret),))

    def new_token(self, account: Account, name: str) -> tuple[int, str]:
        secret = acc.new_secret(acc.TOKEN_PREFIX)
        token_id = self.db.insert(
            "INSERT INTO tokens (account, name, hash, created) VALUES (?, ?, ?, ?)",
            (account["id"], (name or "token")[:60], acc.secret_hash(secret), self.now()),
        )
        return token_id, secret

    def token_account(self, secret: str) -> Account | None:
        h = acc.secret_hash(secret)
        row = self.db.one(
            "SELECT a.*, t.id AS token_id FROM tokens t JOIN accounts a ON a.id = t.account"
            " WHERE t.hash = ?",
            (h,),
        )
        if row is None or row["suspended"]:
            return None
        self.db.execute(
            "UPDATE tokens SET used = ? WHERE id = ?", (self.now(), row.pop("token_id"))
        )
        return row

    def tokens(self, account: Account) -> list[dict[str, Any]]:
        return self.db.all(
            "SELECT id, name, created, used FROM tokens WHERE account = ? ORDER BY id",
            (account["id"],),
        )

    def revoke_token(self, account: Account, token_id: int) -> None:
        if not self.db.execute(
            "DELETE FROM tokens WHERE id = ? AND account = ?", (token_id, account["id"])
        ):
            raise not_found("no existe ese token")

    def credentials(self, user: str, secret: str) -> Account | None:
        """La cuenta de unas credenciales de git (HTTP Basic): un token o la contraseña."""
        if secret.startswith(acc.TOKEN_PREFIX):
            return self.token_account(secret)
        try:
            return self.login(user, secret)
        except HubError:
            return None

    # --- organizaciones -------------------------------------------------------------------------

    def create_org(self, name: str, owner: Account, display: str = "") -> Account:
        if owner["kind"] != "user":
            raise bad("solo una persona puede crear una organización")
        with self.db.transaction():
            org = self._new_account(name, "org", display=display)
            self.db.execute(
                "INSERT INTO members (org, account, role) VALUES (?, ?, 'owner')",
                (org["id"], owner["id"]),
            )
        return org

    def role(self, org: Account, account: Account | None) -> str | None:
        if account is None:
            return None
        row = self.db.one(
            "SELECT role FROM members WHERE org = ? AND account = ?", (org["id"], account["id"])
        )
        return row["role"] if row else None

    def members(self, org: Account) -> list[dict[str, Any]]:
        return self.db.all(
            "SELECT a.name, a.display, m.role FROM members m JOIN accounts a ON a.id = m.account"
            " WHERE m.org = ? ORDER BY m.role DESC, a.name",
            (org["id"],),
        )

    def set_member(self, org: Account, by: Account, name: str, role: str | None) -> None:
        """Añade, cambia (`role`) o quita (`None`) a un miembro; solo los dueños."""
        if self.role(org, by) != "owner" and not by["admin"]:
            raise forbidden("solo los dueños de la organización gestionan sus miembros")
        member = self.require_account(name)
        if member["kind"] != "user":
            raise bad("una organización no puede ser miembro de otra")
        if role not in (None, "owner", "member"):
            raise bad("el papel es owner o member")
        with self.db.transaction():
            self.db.execute(
                "DELETE FROM members WHERE org = ? AND account = ?", (org["id"], member["id"])
            )
            if role is not None:
                self.db.execute(
                    "INSERT INTO members (org, account, role) VALUES (?, ?, ?)",
                    (org["id"], member["id"], role),
                )
            owners = self.db.value(
                "SELECT count(*) AS n FROM members WHERE org = ? AND role = 'owner'", (org["id"],)
            )
            if not owners:
                raise bad("una organización necesita al menos un dueño")

    # --- permisos -------------------------------------------------------------------------------

    def owner_of(self, repo: Repo) -> Account:
        return self.account_by_id(repo["owner"])

    def can_write_owner(self, owner: Account, account: Account | None) -> bool:
        """¿Puede `account` crear o escribir repositorios de `owner`?"""
        if account is None or account["suspended"]:
            return False
        if owner["id"] == account["id"]:
            return True
        return owner["kind"] == "org" and self.role(owner, account) is not None

    def can_write(self, repo: Repo, account: Account | None) -> bool:
        return self.can_write_owner(self.owner_of(repo), account)

    def can_admin(self, repo: Repo, account: Account | None) -> bool:
        if account is None or account["suspended"]:
            return False
        if account["admin"]:
            return True
        owner = self.owner_of(repo)
        return owner["id"] == account["id"] or self.role(owner, account) == "owner"

    def can_see(self, repo: Repo, account: Account | None) -> bool:
        if not repo["hidden"]:
            return True
        return account is not None and (account["admin"] or self.can_write(repo, account))

    # --- repositorios ---------------------------------------------------------------------------

    def repo(self, owner: str, name: str, viewer: Account | None = None) -> Repo:
        row = self.db.one(
            "SELECT r.* FROM repos r JOIN accounts a ON a.id = r.owner"
            " WHERE a.name = ? AND r.name = ?",
            (owner.lower(), name.lower()),
        )
        if row is None or not self.can_see(row, viewer):
            raise not_found(f"no existe el repositorio {owner}/{name}")
        return row

    def repo_by_id(self, repo_id: int) -> Repo:
        row = self.db.one("SELECT * FROM repos WHERE id = ?", (repo_id,))
        if row is None:
            raise not_found("no existe ese repositorio")
        return row

    def full_name(self, repo: Repo) -> str:
        return f"{self.owner_of(repo)['name']}/{repo['name']}"

    def git(self, repo: Repo) -> GitRepo:
        return GitRepo(self.repos_dir / f"{repo['id']}.git")

    def _check_repo_quota(self, owner: Account) -> None:
        count = self.db.value("SELECT count(*) AS n FROM repos WHERE owner = ?", (owner["id"],))
        if count >= self.config.quotas.repos:
            raise HubError(
                429, "quota", f"{owner['name']} ya tiene {count} repositorios (el máximo)"
            )

    def create_repo(
        self,
        owner_name: str,
        name: str,
        by: Account,
        *,
        kind: str = "game",
        description: str = "",
        files: dict[str, bytes] | None = None,
    ) -> Repo:
        """Un repositorio nuevo; con `files`, su primer commit (si no, vacío: se llena con un
        `git push`)."""
        owner = self.require_account(owner_name)
        if not self.can_write_owner(owner, by):
            raise forbidden(f"no puedes crear repositorios en {owner['name']}")
        if not acc.valid_name(name):
            raise bad(f"nombre de repositorio no válido: {name!r} (minúsculas, números y guiones)")
        if kind not in ("game", "library"):
            raise bad("el tipo de repositorio es game o library")
        self._check_repo_quota(owner)
        now = self.now()
        try:
            repo_id = self.db.insert(
                "INSERT INTO repos (owner, name, kind, description, created, updated)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (owner["id"], name, kind, description[:300], now, now),
            )
        except Exception as exc:
            if "UNIQUE" in str(exc).upper() or "duplicate" in str(exc).lower():
                raise HubError(409, "taken", f"{owner['name']}/{name} ya existe") from None
            raise
        repo = self.repo_by_id(repo_id)
        git = GitRepo.init(self.git(repo).path)
        if files:
            git.commit_files("main", files, "Primera versión", self.author(by))
            self._refresh_size(repo)
        self.event(repo, by, "created", {})
        return self.repo_by_id(repo_id)

    def author(self, account: Account) -> Author:
        email = account["email"] or f"{account['name']}@users.gamehub.invalid"
        return Author(account["display"] or account["name"], email)

    def fork(
        self, repo: Repo, by: Account, *, owner_name: str | None = None, name: str | None = None
    ) -> Repo:
        owner = self.require_account(owner_name or by["name"])
        if not self.can_write_owner(owner, by):
            raise forbidden(f"no puedes crear repositorios en {owner['name']}")
        name = name or str(repo["name"])
        if not acc.valid_name(name):
            raise bad(f"nombre de repositorio no válido: {name!r} (minúsculas, números y guiones)")
        self._check_repo_quota(owner)
        if self.db.one("SELECT id FROM repos WHERE owner = ? AND name = ?", (owner["id"], name)):
            raise HubError(409, "taken", f"{owner['name']}/{name} ya existe")
        now = self.now()
        repo_id = self.db.insert(
            "INSERT INTO repos (owner, name, kind, description, parent, default_branch, created,"
            " updated) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                owner["id"],
                name,
                repo["kind"],
                repo["description"],
                repo["id"],
                repo["default_branch"],
                now,
                now,
            ),
        )
        fork = self.repo_by_id(repo_id)
        try:
            GitRepo.fork(self.git(repo), self.git(fork).path)
        except GitError:
            self.db.execute("DELETE FROM repos WHERE id = ?", (repo_id,))
            raise
        self._refresh_size(fork)
        self.event(fork, by, "forked", {"from": self.full_name(repo)})
        self.event(repo, by, "fork", {"to": self.full_name(fork)})
        return self.repo_by_id(repo_id)

    def update_repo(
        self, repo: Repo, by: Account, *, description: str | None, default_branch: str | None
    ) -> Repo:
        if not self.can_admin(repo, by):
            raise forbidden("solo quien administra el repositorio puede cambiarlo")
        if description is not None:
            self.db.execute(
                "UPDATE repos SET description = ? WHERE id = ?", (description[:300], repo["id"])
            )
        if default_branch is not None:
            if default_branch not in self.git(repo).branches():
                raise bad(f"no existe la rama {default_branch}")
            self.db.execute(
                "UPDATE repos SET default_branch = ? WHERE id = ?", (default_branch, repo["id"])
            )
        return self.repo_by_id(repo["id"])

    def delete_repo(self, repo: Repo, by: Account) -> None:
        if not self.can_admin(repo, by):
            raise forbidden("solo quien administra el repositorio puede borrarlo")
        if self.db.value("SELECT count(*) AS n FROM releases WHERE repo = ?", (repo["id"],)):
            raise HubError(
                409,
                "has_releases",
                "tiene versiones publicadas (otros pueden depender de ellas): ocúltalo en su lugar",
            )
        with self.db.transaction():
            self.db.execute("UPDATE repos SET parent = NULL WHERE parent = ?", (repo["id"],))
            for table, column in (
                ("stars", "repo"),
                ("events", "repo"),
                ("pages", "repo"),
                ("jobs", "repo"),
            ):
                self.db.execute(f"DELETE FROM {table} WHERE {column} = ?", (repo["id"],))
            pulls = [
                p["id"]
                for p in self.db.all(
                    "SELECT id FROM pulls WHERE repo = ? OR source = ?", (repo["id"], repo["id"])
                )
            ]
            for pull_id in pulls:
                self.db.execute("DELETE FROM comments WHERE pull = ?", (pull_id,))
                self.db.execute("UPDATE jobs SET pull = NULL WHERE pull = ?", (pull_id,))
                self.db.execute("DELETE FROM pulls WHERE id = ?", (pull_id,))
            self.db.execute("DELETE FROM repos WHERE id = ?", (repo["id"],))
        self.git(repo).delete()

    def _refresh_size(self, repo: Repo) -> int:
        size = self.git(repo).size()
        self.db.execute(
            "UPDATE repos SET size = ?, updated = ? WHERE id = ?", (size, self.now(), repo["id"])
        )
        return size

    def repo_json(self, repo: Repo, viewer: Account | None = None) -> dict[str, Any]:
        owner = self.owner_of(repo)
        parent = self.repo_by_id(repo["parent"]) if repo["parent"] else None
        latest = self.db.one(
            "SELECT version, title, rules_hash, game, created FROM releases"
            " WHERE repo = ? AND yanked = 0 ORDER BY major DESC, minor DESC, patch DESC,"
            " pre = '' DESC, pre DESC LIMIT 1",
            (repo["id"],),
        )
        forks = self.db.value("SELECT count(*) AS n FROM repos WHERE parent = ?", (repo["id"],))
        starred = viewer is not None and bool(
            self.db.one(
                "SELECT 1 AS x FROM stars WHERE account = ? AND repo = ?",
                (viewer["id"], repo["id"]),
            )
        )
        return {
            "owner": owner["name"],
            "owner_kind": owner["kind"],
            "name": repo["name"],
            "full_name": f"{owner['name']}/{repo['name']}",
            "kind": repo["kind"],
            "description": repo["description"],
            "parent": self.full_name(parent) if parent and self.can_see(parent, viewer) else None,
            "default_branch": repo["default_branch"],
            "stars": repo["stars"],
            "forks": forks,
            "size": repo["size"],
            "hidden": bool(repo["hidden"]),
            "created": repo["created"],
            "updated": repo["updated"],
            "latest": latest,
            "starred": starred,
            "can_write": self.can_write(repo, viewer),
            "can_admin": self.can_admin(repo, viewer),
        }

    def list_repos(self, owner: Account, viewer: Account | None) -> list[Repo]:
        rows = self.db.all(
            "SELECT * FROM repos WHERE owner = ? ORDER BY updated DESC", (owner["id"],)
        )
        return [r for r in rows if self.can_see(r, viewer)]

    def star(self, repo: Repo, account: Account, on: bool) -> int:
        with self.db.transaction():
            exists = self.db.one(
                "SELECT 1 AS x FROM stars WHERE account = ? AND repo = ?",
                (account["id"], repo["id"]),
            )
            if on and not exists:
                self.db.execute(
                    "INSERT INTO stars (account, repo) VALUES (?, ?)", (account["id"], repo["id"])
                )
            elif not on and exists:
                self.db.execute(
                    "DELETE FROM stars WHERE account = ? AND repo = ?",
                    (account["id"], repo["id"]),
                )
            count = self.db.value("SELECT count(*) AS n FROM stars WHERE repo = ?", (repo["id"],))
            self.db.execute("UPDATE repos SET stars = ? WHERE id = ?", (count, repo["id"]))
        return int(count)

    # --- archivos -------------------------------------------------------------------------------

    def ref_commit(self, repo: Repo, ref: str | None) -> str:
        git = self.git(repo)
        commit = git.resolve(ref or repo["default_branch"])
        if commit is None:
            if git.is_empty():
                raise HubError(404, "empty", "el repositorio está vacío")
            raise not_found(f"no existe {ref}")
        return commit

    def commit_files(
        self,
        repo: Repo,
        by: Account,
        branch: str,
        changes: dict[str, bytes | None],
        message: str,
        *,
        expected: str | None = None,
        base: str | None = None,
    ) -> str:
        """Un commit hecho desde la web. `base`: la rama de la que sale `branch` si no existe."""
        if not self.can_write(repo, by):
            raise forbidden("no puedes escribir en este repositorio")
        if not changes:
            raise bad("no hay cambios")
        total = sum(len(v) for v in changes.values() if v is not None)
        if total > self.config.quotas.push_mb * 1024 * 1024:
            raise HubError(413, "too_large", "los archivos son demasiado grandes")
        git = self.git(repo)
        if git.resolve(f"refs/heads/{branch}") is None and base is not None:
            start = self.ref_commit(repo, base)
            git.create_ref(f"refs/heads/{branch}", start)
        try:
            commit = git.commit_files(
                branch,
                changes,
                message.strip() or "Cambios desde la web",
                self.author(by),
                expected=expected,
            )
        except GitError as exc:
            raise HubError(409 if exc.conflict else 400, "git", str(exc)) from None
        self._refresh_size(repo)
        self.event(repo, by, "commit", {"branch": branch, "commit": commit, "message": message})
        return commit

    def pushed(self, repo: Repo, by: Account | None, before: dict[str, str]) -> None:
        """Tras un `git push`: actualiza el tamaño y anota qué referencias cambiaron."""
        after = self.git(repo).all_refs()
        changed = {
            ref: {"old": before.get(ref), "new": after.get(ref)}
            for ref in sorted(set(before) | set(after))
            if before.get(ref) != after.get(ref) and not ref.startswith("pull/")
        }
        self._refresh_size(repo)
        if changed:
            self.event(repo, by, "pushed", {"refs": changed})
            self.emit("pushed", repo, changed)

    def manifest_at(self, repo: Repo, commit: str) -> dict[str, Any] | None:
        import tomllib

        raw = self.git(repo).read(commit, MANIFEST)
        if raw is None:
            return None
        try:
            return tomllib.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, tomllib.TOMLDecodeError):
            return None

    # --- actividad ------------------------------------------------------------------------------

    def event(self, repo: Repo | None, by: Account | None, kind: str, data: dict[str, Any]) -> None:
        self.db.execute(
            "INSERT INTO events (repo, account, kind, data, created) VALUES (?, ?, ?, ?, ?)",
            (
                repo["id"] if repo else None,
                by["id"] if by else None,
                kind,
                json.dumps(data, ensure_ascii=False),
                self.now(),
            ),
        )

    def events(
        self, *, repo: Repo | None = None, account: Account | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        where, params = [], []
        if repo is not None:
            where.append("e.repo = ?")
            params.append(repo["id"])
        if account is not None:
            where.append("e.account = ?")
            params.append(account["id"])
        rows = self.db.all(
            "SELECT e.*, a.name AS who FROM events e LEFT JOIN accounts a ON a.id = e.account"
            + (" WHERE " + " AND ".join(where) if where else "")
            + " ORDER BY e.id DESC LIMIT ?",
            (*params, limit),
        )
        out = []
        for r in rows:
            item = {
                "kind": r["kind"],
                "who": r["who"],
                "data": json.loads(r["data"]),
                "time": r["created"],
            }
            if r["repo"] is not None and repo is None:
                target = self.db.one("SELECT * FROM repos WHERE id = ?", (r["repo"],))
                if target is None or target["hidden"]:
                    continue
                item["repo"] = self.full_name(target)
            out.append(item)
        return out

    # --- moderación -----------------------------------------------------------------------------

    def report(self, by: Account | None, target: str, reason: str) -> int:
        kind, _, ident = target.partition(":")
        if kind not in ("repo", "account", "pull") or not ident.isdigit():
            raise bad("el objetivo es repo:ID, account:ID o pull:ID")
        if not reason.strip():
            raise bad("explica el motivo")
        return self.db.insert(
            "INSERT INTO reports (reporter, target, reason, status, created)"
            " VALUES (?, ?, ?, 'open', ?)",
            (by["id"] if by else None, target, reason.strip()[:2000], self.now()),
        )

    def reports(self, by: Account, status: str = "open") -> list[dict[str, Any]]:
        self.require_admin(by)
        rows = self.db.all(
            "SELECT r.*, a.name AS reporter_name FROM reports r"
            " LEFT JOIN accounts a ON a.id = r.reporter WHERE r.status = ? ORDER BY r.id",
            (status,),
        )
        out = []
        for r in rows:
            kind, _, ident = r["target"].partition(":")
            label = r["target"]
            if kind == "repo":
                found = self.db.one("SELECT * FROM repos WHERE id = ?", (int(ident),))
                label = self.full_name(found) if found else label
            elif kind == "account":
                found = self.db.one("SELECT name FROM accounts WHERE id = ?", (int(ident),))
                label = found["name"] if found else label
            out.append(
                {
                    "id": r["id"],
                    "target": r["target"],
                    "label": label,
                    "reason": r["reason"],
                    "reporter": r["reporter_name"],
                    "status": r["status"],
                    "resolution": r["resolution"],
                    "created": r["created"],
                }
            )
        return out

    def require_admin(self, account: Account | None) -> Account:
        if account is None or not account["admin"]:
            raise forbidden("solo para la moderación del hub")
        return account

    def resolve_report(self, by: Account, report_id: int, status: str, resolution: str) -> None:
        self.require_admin(by)
        if status not in ("resolved", "dismissed"):
            raise bad("el estado es resolved o dismissed")
        if not self.db.execute(
            "UPDATE reports SET status = ?, resolution = ?, resolver = ? WHERE id = ?",
            (status, resolution[:2000], by["id"], report_id),
        ):
            raise not_found("no existe esa denuncia")

    def moderate_repo(self, by: Account, repo: Repo, hidden: bool) -> None:
        self.require_admin(by)
        self.db.execute("UPDATE repos SET hidden = ? WHERE id = ?", (int(hidden), repo["id"]))
        self.event(repo, by, "hidden" if hidden else "unhidden", {})

    def suspend(self, by: Account, target: Account, suspended: bool) -> None:
        self.require_admin(by)
        if target["id"] == by["id"]:
            raise bad("no puedes suspenderte a ti")
        with self.db.transaction():
            self.db.execute(
                "UPDATE accounts SET suspended = ? WHERE id = ?", (int(suspended), target["id"])
            )
            if suspended:
                self.db.execute("DELETE FROM sessions WHERE account = ?", (target["id"],))


def read_terms(config: HubConfig) -> str:
    """El texto de las condiciones de uso: `terms.md` en el directorio de datos o el de
    serie."""
    custom = config.data / "terms.md"
    if custom.is_file():
        return custom.read_text(encoding="utf-8")
    return (Path(__file__).parent / "terms.md").read_text(encoding="utf-8")
