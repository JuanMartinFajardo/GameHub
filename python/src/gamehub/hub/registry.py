# SPDX-License-Identifier: AGPL-3.0-or-later
"""El registro de versiones del hub: publicar, el versionado automático y las dependencias.

Publicar una versión es compilar el paquete en un commit (con sus dependencias del hub resueltas
sin red), guardar su IR en el almacén de objetos, calcular sus hashes y su clasificación, poner la
etiqueta `vX.Y.Z` en el repositorio y registrarla. Una versión publicada no cambia nunca (como
mucho se retira con `yank`: deja de elegirse para dependencias nuevas, pero sigue jugándose).

**Versionado automático** (ADR-091): comparando con la versión anterior, un cambio incompatible de
la interfaz exige subir la versión mayor; un cambio de reglas o una ampliación de la interfaz, la
menor; lo demás, el parche (en 0.y.z, un nivel menos, como en Cargo). Sin versión explícita, el
hub elige la siguiente; con una que no basta, se niega y dice cuál haría falta.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from gamehub.analysis.classify import classify
from gamehub.hub.service import Account, Hub, HubError, Repo, bad, forbidden, not_found
from gamehub.ir.hashing import rules_hash
from gamehub.ir.interface import change_level, compare, interface_hash
from gamehub.lang.diagnostics import render
from gamehub.packages import (
    HUB_RESOLVER,
    MANIFEST,
    Dependency,
    Manifest,
    PackageError,
    load_manifest,
)
from gamehub.semver import Level, Requirement, Version, VersionError, allowed

Release = dict[str, Any]


@dataclass
class Build:
    """Un paquete compilado en un commit."""

    commit: str
    manifest: Manifest | None = None
    ir: dict[str, Any] | None = None
    #: Los juegos del archivo principal (por nombre de juego) y el elegido.
    games: dict[str, dict[str, Any]] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)
    #: El modelo del Studio del archivo principal (para el diagrama), si se pidió.
    model: dict[str, Any] | None = None
    entry: str | None = None
    source: str | None = None

    @property
    def ok(self) -> bool:
        return not self.problems


#: Compilaciones recientes por (repositorio, commit, con modelo): compilar cuesta.
_BUILDS: OrderedDict[tuple[int, str, bool], Build] = OrderedDict()
_BUILDS_MAX = 64


def build(hub: Hub, repo: Repo, commit: str, *, model: bool = False) -> Build:
    key = (repo["id"], commit, model)
    cached = _BUILDS.get(key)
    if cached is not None:
        _BUILDS.move_to_end(key)
        return cached
    result = _build(hub, repo, commit, model=model)
    _BUILDS[key] = result
    while len(_BUILDS) > _BUILDS_MAX:
        _BUILDS.popitem(last=False)
    return result


def _build(hub: Hub, repo: Repo, commit: str, *, model: bool) -> Build:
    from gamehub.lang.compiler import compile_file

    out = Build(commit)
    with tempfile.TemporaryDirectory(dir=hub.tmp_dir) as tmp:
        root = Path(tmp) / "package"
        hub.git(repo).export(commit, root)
        if not (root / MANIFEST).is_file():
            out.problems.append(f"falta {MANIFEST}: no es un paquete de GameHub")
            return out
        try:
            manifest = load_manifest(root)
        except PackageError as exc:
            out.problems.append(str(exc).replace(str(root) + "/", ""))
            return out
        out.manifest = manifest
        for dep in manifest.dependencies.values():
            if dep.git is not None:
                out.problems.append(
                    f"la dependencia {dep.name} es de git: en el hub, usa una del hub "
                    f'(hub = "dueño/nombre") o una ruta dentro del repositorio'
                )
            elif dep.path is not None and not (root / dep.path).resolve().is_relative_to(root):
                out.problems.append(
                    f"la dependencia {dep.name} apunta fuera del repositorio ({dep.path})"
                )
        if out.problems:
            return out
        entry = manifest.entry_path
        if not entry.is_file():
            out.problems.append(f"no existe el archivo principal {entry.name}")
            return out
        out.entry = str(entry.relative_to(root))
        out.source = entry.read_text(encoding="utf-8")
        token = HUB_RESOLVER.set(lambda dep: _resolve_local(hub, dep))
        try:
            result = compile_file(entry)
        except PackageError as exc:
            out.problems.append(str(exc))
            return out
        finally:
            HUB_RESOLVER.reset(token)
        if not result.ok:
            out.problems += [
                render(d).replace(str(root) + "/", "") for d in result.diagnostics.errors
            ][:20]
            return out
        out.games = {name: g.ir for name, g in result.games.items()}
        out.ir = _main_game(manifest, out.games)
        if model:
            from gamehub.studio.model import document_model

            out.model = document_model(result.source, result.file, result.models)
    return out


def _main_game(manifest: Manifest, games: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    if not games:
        return None
    if len(games) == 1:
        return next(iter(games.values()))
    for ir in games.values():
        if ir["game"]["id"] == manifest.name:
            return ir
    return next(iter(games.values()))


def _resolve_local(hub: Hub, dep: Dependency) -> Path:
    """Una dependencia del hub resuelta en el propio hub: el árbol de la versión elegida."""
    assert dep.hub is not None
    owner, name = dep.hub.split("/", 1)
    try:
        repo = hub.repo(owner, name)
        release = best_release(hub, repo, dep.version or "*")
    except HubError as exc:
        raise PackageError(f"{dep.name}: {exc.message}") from None
    dest = hub.config.data / "cache" / "deps" / f"{repo['id']}-{release['commit_id']}"
    if not dest.is_dir():
        tmp = dest.with_name(dest.name + f".tmp{id(dep)}")
        shutil.rmtree(tmp, ignore_errors=True)
        hub.git(repo).export(release["commit_id"], tmp)
        try:
            tmp.rename(dest)
        except OSError:
            shutil.rmtree(tmp, ignore_errors=True)  # otro hilo llegó antes
    return dest


# --- versiones ----------------------------------------------------------------------------------

_ORDER = "major DESC, minor DESC, patch DESC, pre = '' DESC, pre DESC"


def releases(hub: Hub, repo: Repo, *, include_yanked: bool = True) -> list[Release]:
    rows = hub.db.all(
        f"SELECT * FROM releases WHERE repo = ?{'' if include_yanked else ' AND yanked = 0'}"
        f" ORDER BY {_ORDER}",
        (repo["id"],),
    )
    # El orden de las previas en SQL es aproximado: el de semver manda.
    return sorted(rows, key=lambda r: Version.parse(r["version"]).key(), reverse=True)


def release(hub: Hub, repo: Repo, version: str) -> Release:
    if version == "latest":
        found = releases(hub, repo, include_yanked=False)
        if not found:
            raise not_found(f"{hub.full_name(repo)} no tiene versiones publicadas")
        return found[0]
    row = hub.db.one(
        "SELECT * FROM releases WHERE repo = ? AND version = ?",
        (repo["id"], version.removeprefix("v")),
    )
    if row is None:
        raise not_found(f"{hub.full_name(repo)} no tiene la versión {version}")
    return row


def best_release(hub: Hub, repo: Repo, requirement: str) -> Release:
    try:
        req = Requirement.parse(requirement)
    except VersionError as exc:
        raise bad(str(exc)) from None
    candidates = releases(hub, repo, include_yanked=False)
    for row in candidates:
        if req.matches(Version.parse(row["version"])):
            return row
    raise not_found(f"ninguna versión de {hub.full_name(repo)} cumple {requirement}")


def release_ir(hub: Hub, row: Release) -> dict[str, Any] | None:
    return hub.blobs.get_json(row["ir"]) if row["ir"] else None


def game_ref(hub: Hub, repo: Repo, row: Release) -> str:
    """El identificador con el que se juega una versión: dueño/nombre@versión."""
    return f"{hub.full_name(repo)}@{row['version']}"


def release_json(hub: Hub, repo: Repo, row: Release) -> dict[str, Any]:
    publisher = hub.db.one("SELECT name FROM accounts WHERE id = ?", (row["publisher"],))
    deps = hub.db.all(
        "SELECT d.requirement, r.id FROM dependencies d JOIN repos r ON r.id = d.repo"
        " WHERE d.release = ?",
        (row["id"],),
    )
    return {
        "repo": hub.full_name(repo),
        "version": row["version"],
        "ref": game_ref(hub, repo, row),
        "commit": row["commit_id"],
        "level": row["level"],
        "game": row["game"],
        "title": row["title"],
        "rules_hash": row["rules_hash"],
        "interface_hash": row["interface_hash"],
        "properties": json.loads(row["properties"]),
        "manifest": json.loads(row["manifest"]),
        "dependencies": [
            {"repo": hub.full_name(hub.repo_by_id(d["id"])), "requirement": d["requirement"]}
            for d in deps
        ],
        "notes": row["notes"],
        "publisher": publisher["name"] if publisher else None,
        "yanked": bool(row["yanked"]),
        "created": row["created"],
    }


# --- publicar -----------------------------------------------------------------------------------


@dataclass
class Plan:
    """Lo que pasaría al publicar un commit (sin publicar nada)."""

    commit: str
    build: Build
    previous: Release | None
    level: Level | None
    version: Version | None
    changes: list[dict[str, Any]]
    problems: list[str]

    def to_json(self) -> dict[str, Any]:
        return {
            "commit": self.commit,
            "previous": self.previous["version"] if self.previous else None,
            "level": self.level,
            "version": str(self.version) if self.version else None,
            "interface_changes": self.changes,
            "rules_hash": rules_hash(self.build.ir) if self.build.ir else None,
            "problems": self.problems,
        }


def plan(hub: Hub, repo: Repo, ref: str | None, version: str | None = None) -> Plan:
    commit = hub.ref_commit(repo, ref)
    built = build(hub, repo, commit)
    problems = list(built.problems)
    existing = releases(hub, repo)
    previous = existing[0] if existing else None
    level: Level | None = None
    changes: list[dict[str, Any]] = []
    wanted: Version | None = None
    if version is not None:
        try:
            wanted = Version.parse(version)
        except VersionError as exc:
            problems.append(str(exc))
    if built.ok and repo["kind"] == "game" and built.ir is None:
        problems.append("el archivo principal no define ningún juego (¿es una librería?)")
    if not problems:
        if previous is None:
            level = "major"
            start = wanted or _manifest_version(built) or Version(0, 1, 0)
            wanted = start
        else:
            old_ir = release_ir(hub, previous)
            if old_ir is not None and built.ir is not None:
                level = change_level(old_ir, built.ir)
                changes = [c.to_json() for c in compare(old_ir, built.ir)]
            else:
                level = "minor"  # una librería: no se analiza su interfaz
            if level is None:
                if hub.git(repo).text("rev-parse", f"{commit}^{{tree}}") == hub.git(repo).text(
                    "rev-parse", f"{previous['commit_id']}^{{tree}}"
                ):
                    problems.append(
                        f"nada que publicar: es lo mismo que la versión {previous['version']}"
                    )
                level = "patch"
            prev = Version.parse(previous["version"])
            if wanted is None:
                wanted = prev.bump(level)
            elif any(Version.parse(r["version"]).key() == wanted.key() for r in existing):
                problems.append(f"la versión {wanted} ya está publicada")
            elif not allowed(prev, wanted, level):
                problems.append(
                    f"el cambio desde {prev} es de nivel {_level_text(level)}: la versión tiene "
                    f"que ser al menos {prev.bump(level)}"
                )
    return Plan(commit, built, previous, level, wanted, changes, problems)


def _level_text(level: Level) -> str:
    return {
        "major": "mayor (la interfaz cambia de forma incompatible)",
        "minor": "menor (cambian las reglas o la interfaz se amplía)",
        "patch": "parche (solo textos, presentación o heurísticas)",
    }[level]


def _manifest_version(built: Build) -> Version | None:
    if built.manifest is None:
        return None
    try:
        return Version.parse(built.manifest.version)
    except VersionError:
        return None


def publish(
    hub: Hub,
    repo: Repo,
    by: Account,
    ref: str | None = None,
    *,
    version: str | None = None,
    notes: str = "",
) -> Release:
    if not hub.can_write(repo, by):
        raise forbidden("no puedes publicar versiones de este repositorio")
    p = plan(hub, repo, ref, version)
    if p.problems:
        raise HubError(422, "invalid", "; ".join(p.problems))
    assert p.version is not None and p.build.manifest is not None
    git = hub.git(repo)
    tag = f"refs/tags/v{p.version}"
    current = git.resolve(tag)
    if current is not None and current != p.commit:
        raise HubError(409, "tag", f"la etiqueta v{p.version} ya existe y apunta a otro commit")
    ir = p.build.ir
    properties: dict[str, Any] = {"files": len(git.ls(p.commit, recursive=True))}
    columns: dict[str, Any] = {}
    if ir is not None:
        info = classify(ir)
        properties.update(info.to_json())
        properties["labels"] = info.labels()
        properties["interface_hash"] = interface_hash(ir)
        meta = ir.get("meta", {})
        title = meta.get("title")
        columns = {
            "title": (title.get("en") or next(iter(title.values()), ""))
            if isinstance(title, dict)
            else (title or ""),
            "tags": "," + ",".join(meta.get("tags", [])) + "," if meta.get("tags") else "",
            "min_players": info.min_players,
            "max_players": info.max_players,
            "chance": int(info.chance),
            "perfect_information": int(info.perfect_information),
            "simultaneous": int(info.simultaneous),
            "zero_sum": None if info.zero_sum is None else int(info.zero_sum),
        }
    manifest_json = _manifest_json(p.build.manifest)
    with hub.db.transaction():
        release_id = hub.db.insert(
            "INSERT INTO releases (repo, version, major, minor, patch, pre, commit_id, level, game,"
            " title, rules_hash, interface_hash, ir, manifest, properties, tags, min_players,"
            " max_players, chance, perfect_information, simultaneous, zero_sum, notes, publisher,"
            " created) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,"
            " ?, ?, ?)",
            (
                repo["id"],
                str(p.version),
                p.version.major,
                p.version.minor,
                p.version.patch,
                ".".join(map(str, p.version.pre)),
                p.commit,
                p.level if p.previous else None,
                ir["game"]["id"] if ir else None,
                columns.get("title") or p.build.manifest.name,
                rules_hash(ir) if ir else None,
                interface_hash(ir) if ir else None,
                hub.blobs.put_json(ir) if ir else None,
                json.dumps(manifest_json, ensure_ascii=False),
                json.dumps(properties, ensure_ascii=False),
                columns.get("tags", ""),
                columns.get("min_players"),
                columns.get("max_players"),
                columns.get("chance"),
                columns.get("perfect_information"),
                columns.get("simultaneous"),
                columns.get("zero_sum"),
                notes[:5000],
                by["id"],
                hub.now(),
            ),
        )
        for dep in p.build.manifest.dependencies.values():
            if dep.hub is None:
                continue
            owner, name = dep.hub.split("/", 1)
            target = hub.repo(owner, name)
            hub.db.execute(
                "INSERT INTO dependencies (release, repo, requirement) VALUES (?, ?, ?)",
                (release_id, target["id"], dep.version or "*"),
            )
        if current is None:
            git.create_ref(tag, p.commit)
    row = hub.db.one("SELECT * FROM releases WHERE id = ?", (release_id,))
    assert row is not None
    hub.event(repo, by, "published", {"version": row["version"], "level": row["level"]})
    hub.emit("published", repo, row)
    return row


def _manifest_json(m: Manifest) -> dict[str, Any]:
    return {
        "name": m.name,
        "version": m.version,
        "entry": m.entry,
        "license": m.license,
        "authors": m.authors,
        "forked_from": m.forked_from,
        "dependencies": {
            d.name: {k: v for k, v in vars(d).items() if v is not None and k != "name"}
            for d in m.dependencies.values()
        },
    }


def yank(hub: Hub, repo: Repo, by: Account, version: str, yanked: bool = True) -> None:
    if not hub.can_admin(repo, by):
        raise forbidden("solo quien administra el repositorio puede retirar versiones")
    row = release(hub, repo, version)
    hub.db.execute("UPDATE releases SET yanked = ? WHERE id = ?", (int(yanked), row["id"]))
    hub.event(repo, by, "yanked" if yanked else "unyanked", {"version": row["version"]})


def dependents(hub: Hub, repo: Repo) -> list[dict[str, Any]]:
    """Los repositorios que dependen de este (en alguna de sus versiones)."""
    rows = hub.db.all(
        "SELECT DISTINCT r.id FROM dependencies d JOIN releases v ON v.id = d.release"
        " JOIN repos r ON r.id = v.repo WHERE d.repo = ?",
        (repo["id"],),
    )
    return [{"repo": hub.full_name(hub.repo_by_id(r["id"]))} for r in rows]
