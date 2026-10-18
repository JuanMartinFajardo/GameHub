# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pages: interfaces de juego (apps web estáticas) alojadas por el hub.

Una Page es un `.tar.gz` con un `index.html` (la compilación de una UI propia, `gamehub ui …`) que
se publica en un repositorio, ligada a un **hash de interfaz**: el juego de una versión la puede
usar si su interfaz es la misma. El hub la sirve en `/pages/dueño/juego/nombre/`.

Es código ajeno: se sirve con `Content-Security-Policy: sandbox` (un origen opaco, sin las cookies
ni el almacenamiento del hub) y, si se configura `pages_url`, desde otro dominio.
"""

from __future__ import annotations

import io
import shutil
import tarfile
from pathlib import Path, PurePosixPath
from typing import Any

from gamehub.hub import registry
from gamehub.hub.accounts import valid_name
from gamehub.hub.service import Account, Hub, HubError, Repo, bad, forbidden, not_found

MAX_FILES = 2000


def publish(
    hub: Hub,
    repo: Repo,
    by: Account,
    name: str,
    archive: bytes,
    *,
    interface_hash: str | None = None,
    version: str | None = None,
) -> dict[str, Any]:
    if not hub.can_write(repo, by):
        raise forbidden("no puedes publicar interfaces en este repositorio")
    if not valid_name(name):
        raise bad(f"nombre de interfaz no válido: {name!r}")
    if len(archive) > hub.config.quotas.pages_mb * 1024 * 1024:
        raise HubError(413, "too_large", "la interfaz es demasiado grande")
    if interface_hash is None:
        release = registry.release(hub, repo, version or "latest")
        interface_hash = release["interface_hash"]
        if interface_hash is None:
            raise bad("esa versión no tiene juego: indica el hash de interfaz")
    files = _members(archive)
    key = hub.blobs.put(archive)
    size = sum(m.size for m, _ in files)
    with hub.db.transaction():
        old = hub.db.one("SELECT id FROM pages WHERE repo = ? AND name = ?", (repo["id"], name))
        if old is not None:
            hub.db.execute(
                "UPDATE pages SET interface_hash = ?, archive = ?, files = ?, size = ?,"
                " publisher = ?, created = ? WHERE id = ?",
                (interface_hash, key, len(files), size, by["id"], hub.now(), old["id"]),
            )
            page_id = old["id"]
        else:
            page_id = hub.db.insert(
                "INSERT INTO pages (repo, name, interface_hash, archive, files, size, publisher,"
                " created) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (repo["id"], name, interface_hash, key, len(files), size, by["id"], hub.now()),
            )
    _extract(hub, page_id, archive, files)
    hub.event(repo, by, "page", {"name": name, "interface_hash": interface_hash})
    row = hub.db.one("SELECT * FROM pages WHERE id = ?", (page_id,))
    assert row is not None
    return page_json(hub, repo, row)


def _members(archive: bytes) -> list[tuple[tarfile.TarInfo, str]]:
    """Los archivos del paquete con su ruta final (sin la carpeta común, si la hay)."""
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:*") as tar:
            everything = tar.getmembers()
    except tarfile.TarError:
        raise bad("la interfaz tiene que ser un .tar.gz") from None
    for m in everything:
        if not (m.isfile() or m.isdir()):
            raise bad(f"{m.name}: solo se admiten archivos y carpetas")
    members = [m for m in everything if m.isfile()]
    if not members or len(members) > MAX_FILES:
        raise bad("la interfaz está vacía o tiene demasiados archivos")
    paths = []
    for m in members:
        p = PurePosixPath(m.name)
        if p.is_absolute() or ".." in p.parts:
            raise bad(f"ruta no válida: {m.name}")
        paths.append(PurePosixPath(*[part for part in p.parts if part != "."]))
    prefix: PurePosixPath | None = None
    if not any(len(p.parts) == 1 for p in paths) and len({p.parts[0] for p in paths}) == 1:
        prefix = PurePosixPath(paths[0].parts[0])
    out = [
        (m, str(p.relative_to(prefix) if prefix else p))
        for m, p in zip(members, paths, strict=True)
    ]
    if not any(path == "index.html" for _, path in out):
        raise bad("la interfaz necesita un index.html")
    return out


def _dir(hub: Hub, page_id: int) -> Path:
    return hub.config.data / "pages" / str(page_id)


def _extract(
    hub: Hub, page_id: int, archive: bytes, files: list[tuple[tarfile.TarInfo, str]]
) -> None:
    dest = _dir(hub, page_id)
    tmp = dest.with_name(dest.name + ".new")
    shutil.rmtree(tmp, ignore_errors=True)
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:*") as tar:
        for member, path in files:
            source = tar.extractfile(member)
            if source is None:
                continue
            target = tmp / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read())
    shutil.rmtree(dest, ignore_errors=True)
    tmp.rename(dest)


def listing(hub: Hub, repo: Repo) -> list[dict[str, Any]]:
    rows = hub.db.all("SELECT * FROM pages WHERE repo = ? ORDER BY name", (repo["id"],))
    return [page_json(hub, repo, r) for r in rows]


def page_json(hub: Hub, repo: Repo, row: dict[str, Any]) -> dict[str, Any]:
    versions = [
        r["version"]
        for r in hub.db.all(
            "SELECT version FROM releases WHERE repo = ? AND interface_hash = ? AND yanked = 0",
            (repo["id"], row["interface_hash"]),
        )
    ]
    return {
        "name": row["name"],
        "repo": hub.full_name(repo),
        "interface_hash": row["interface_hash"],
        "files": row["files"],
        "size": row["size"],
        "versions": versions,
        "url": f"/pages/{hub.full_name(repo)}/{row['name']}/",
        "created": row["created"],
    }


def compatible(hub: Hub, interface_hash: str) -> list[dict[str, Any]]:
    """Las interfaces (de cualquier repositorio) que sirven para un hash de interfaz."""
    rows = hub.db.all(
        "SELECT p.* FROM pages p JOIN repos r ON r.id = p.repo"
        " WHERE p.interface_hash = ? AND r.hidden = 0 ORDER BY p.created DESC",
        (interface_hash,),
    )
    return [page_json(hub, hub.repo_by_id(r["repo"]), r) for r in rows]


def file_path(hub: Hub, repo: Repo, name: str, path: str) -> Path:
    row = hub.db.one("SELECT id FROM pages WHERE repo = ? AND name = ?", (repo["id"], name))
    if row is None:
        raise not_found("no existe esa interfaz")
    root = _dir(hub, row["id"]).resolve()
    target = (root / path).resolve() if path else root / "index.html"
    if not target.is_relative_to(root):
        raise not_found("no existe")
    if target.is_dir():
        target = target / "index.html"
    if not target.is_file():
        # Una app de una página: las rutas que no son archivos sirven su index.html.
        target = root / "index.html"
    return target


def delete(hub: Hub, repo: Repo, by: Account, name: str) -> None:
    if not hub.can_write(repo, by):
        raise forbidden("no puedes borrar interfaces de este repositorio")
    row = hub.db.one("SELECT id FROM pages WHERE repo = ? AND name = ?", (repo["id"], name))
    if row is None:
        raise not_found("no existe esa interfaz")
    hub.db.execute("DELETE FROM pages WHERE id = ?", (row["id"],))
    shutil.rmtree(_dir(hub, row["id"]), ignore_errors=True)
