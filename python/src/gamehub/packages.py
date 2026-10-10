# SPDX-License-Identifier: Apache-2.0
"""Paquetes de juegos: `game.toml` (manifiesto), `game.lock` (commits exactos de las
dependencias git) y la caché donde se descargan.

    [game]
    name = "iterated-pd"              # nombre del paquete (minúsculas y guiones)
    version = "0.1.0"
    entry = "iterated-pd.game"        # archivo principal (por defecto, <name>.game)
    license = "CC-BY-4.0"             # opcional
    authors = ["…"]                   # opcional
    forked_from = "url@commit"        # lo escribe `gamehub fork`

    [dependencies]
    prisoners-dilemma = { path = "../prisoners-dilemma" }
    cartas = { git = "https://…", rev = "v1.0" }   # rev: rama, etiqueta o commit (opcional)

Un `import nombre.…` busca primero en la biblioteca estándar (`std`), después entre las
dependencias del paquete al que pertenece el archivo (por `nombre` o con guiones en lugar de
guiones bajos) y por último junto al archivo. `import dep.{X}` lee el archivo principal de la
dependencia; `import dep.sub.{X}`, `sub.game` dentro de ella.

`gamehub fetch` descarga las dependencias git (también las de las dependencias) en la caché
(`~/.cache/gamehub/git`, o `GAMEHUB_CACHE`) y escribe `game.lock` con el commit de cada una; si
el lock ya existe, se usan sus commits (compilaciones reproducibles) salvo con `--update`.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

MANIFEST = "game.toml"
LOCK = "game.lock"
NAME = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")


class PackageError(Exception):
    """Manifiesto, lock o dependencia inválidos o inaccesibles."""


@dataclass
class Dependency:
    name: str
    path: str | None = None
    git: str | None = None
    rev: str | None = None


@dataclass
class Manifest:
    root: Path
    name: str
    version: str = "0.1.0"
    entry: str | None = None
    license: str | None = None
    authors: list[str] = field(default_factory=list)
    forked_from: str | None = None
    dependencies: dict[str, Dependency] = field(default_factory=dict)

    @property
    def entry_path(self) -> Path:
        return self.root / (self.entry or f"{self.name}.game")

    def dependency(self, module: str) -> Dependency | None:
        """La dependencia a la que se refiere la primera parte de un `import`."""
        return self.dependencies.get(module) or self.dependencies.get(module.replace("_", "-"))


@dataclass(frozen=True)
class Locked:
    name: str
    git: str
    rev: str | None
    commit: str


# --- manifiesto ---------------------------------------------------------------------------------


#: Directorios que no se recorren al buscar juegos: dependencias y salidas de las UIs web
#: (`ui/node_modules`, `ui/dist`), cachés y carpetas ocultas (`.git`, `.venv`…).
SKIPPED_DIRS = frozenset({"node_modules", "dist", "build", "__pycache__"})


def find_files(root: Path, *suffixes: str) -> list[Path]:
    """Los archivos bajo `root` que acaban en alguno de `suffixes` (ordenados), sin entrar en
    `SKIPPED_DIRS` ni en carpetas ocultas."""
    found: list[Path] = []
    for folder, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIPPED_DIRS and not d.startswith(".")]
        found.extend(Path(folder) / f for f in files if f.endswith(suffixes))
    return sorted(found)


def load_manifest(root: Path) -> Manifest:
    path = root / MANIFEST
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise PackageError(f"no se puede leer {path}: {exc}") from None
    except tomllib.TOMLDecodeError as exc:
        raise PackageError(f"{path}: TOML no válido: {exc}") from None
    game = data.get("game")
    if not isinstance(game, dict) or not isinstance(game.get("name"), str):
        raise PackageError(f'{path}: falta [game] con name = "…"')
    name = game["name"]
    if not NAME.match(name):
        raise PackageError(f"{path}: nombre de paquete no válido: {name!r} (minúsculas y guiones)")
    manifest = Manifest(
        root=root,
        name=name,
        version=_text(game, "version", path) or "0.1.0",
        entry=_text(game, "entry", path),
        license=_text(game, "license", path),
        authors=list(game.get("authors", [])),
        forked_from=_text(game, "forked_from", path),
    )
    deps = data.get("dependencies", {})
    if not isinstance(deps, dict):
        raise PackageError(f"{path}: [dependencies] tiene que ser una tabla")
    for dep_name, spec in deps.items():
        if not isinstance(spec, dict) or ("path" in spec) == ("git" in spec):
            raise PackageError(f'{path}: la dependencia {dep_name} necesita path = "…" o git = "…"')
        manifest.dependencies[dep_name] = Dependency(
            dep_name, path=spec.get("path"), git=spec.get("git"), rev=spec.get("rev")
        )
    return manifest


def _text(table: dict[str, object], key: str, path: Path) -> str | None:
    value = table.get(key)
    if value is not None and not isinstance(value, str):
        raise PackageError(f"{path}: {key} tiene que ser un texto")
    return value


def find_manifest(path: Path) -> Manifest | None:
    """El manifiesto del paquete al que pertenece un archivo (subiendo directorios)."""
    for directory in [path.resolve().parent, *path.resolve().parent.parents]:
        if (directory / MANIFEST).is_file():
            return load_manifest(directory)
    return None


def manifest_toml(m: Manifest) -> str:
    lines = ["[game]", f"name = {_q(m.name)}", f"version = {_q(m.version)}"]
    if m.entry:
        lines.append(f"entry = {_q(m.entry)}")
    if m.license:
        lines.append(f"license = {_q(m.license)}")
    if m.authors:
        lines.append(f"authors = [{', '.join(_q(a) for a in m.authors)}]")
    if m.forked_from:
        lines.append(f"forked_from = {_q(m.forked_from)}")
    if m.dependencies:
        lines += ["", "[dependencies]"]
        for dep in m.dependencies.values():
            parts = [f"path = {_q(dep.path)}"] if dep.path is not None else []
            if dep.git is not None:
                parts.append(f"git = {_q(dep.git)}")
            if dep.rev is not None:
                parts.append(f"rev = {_q(dep.rev)}")
            lines.append(f"{_key(dep.name)} = {{ {', '.join(parts)} }}")
    return "\n".join(lines) + "\n"


def save_manifest(m: Manifest) -> None:
    (m.root / MANIFEST).write_text(manifest_toml(m), encoding="utf-8")


def _q(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _key(name: str) -> str:
    return name if re.match(r"^[A-Za-z0-9_-]+$", name) else _q(name)


# --- lock y caché -------------------------------------------------------------------------------


def load_lock(root: Path) -> dict[str, Locked]:
    path = root / LOCK
    if not path.is_file():
        return {}
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise PackageError(f"{path}: TOML no válido: {exc}") from None
    return {
        p["name"]: Locked(p["name"], p["git"], p.get("rev"), p["commit"])
        for p in data.get("package", [])
    }


def save_lock(root: Path, entries: dict[str, Locked]) -> None:
    lines = ["# Generado por `gamehub fetch`: no lo edites a mano.", "version = 1"]
    for entry in sorted(entries.values(), key=lambda e: e.name):
        lines += ["", "[[package]]", f"name = {_q(entry.name)}", f"git = {_q(entry.git)}"]
        if entry.rev is not None:
            lines.append(f"rev = {_q(entry.rev)}")
        lines.append(f"commit = {_q(entry.commit)}")
    (root / LOCK).write_text("\n".join(lines) + "\n", encoding="utf-8")


def cache_dir() -> Path:
    override = os.environ.get("GAMEHUB_CACHE")
    base = Path(override) if override else Path.home() / ".cache" / "gamehub"
    return base / "git"


def checkout_dir(url: str, commit: str) -> Path:
    return cache_dir() / hashlib.sha256(url.encode()).hexdigest()[:16] / commit


def dependency_root(manifest: Manifest, dep: Dependency, lock: dict[str, Locked]) -> Path:
    """Directorio de una dependencia (para git, su copia en la caché según el lock)."""
    if dep.path is not None:
        return (manifest.root / dep.path).resolve()
    assert dep.git is not None
    locked = lock.get(dep.name)
    if locked is None or locked.git != dep.git:
        raise PackageError(f"la dependencia {dep.name} no está descargada: ejecuta `gamehub fetch`")
    root = checkout_dir(dep.git, locked.commit)
    if not root.is_dir():
        raise PackageError(
            f"la dependencia {dep.name} no está en la caché: ejecuta `gamehub fetch`"
        )
    return root


def fetch(manifest: Manifest, *, update: bool = False) -> dict[str, Locked]:
    """Descarga las dependencias git (y las de estas) y escribe `game.lock`."""
    previous = {} if update else load_lock(manifest.root)
    resolved: dict[str, Locked] = {}
    pending = [manifest]
    seen: set[Path] = set()
    while pending:
        current = pending.pop()
        if current.root in seen:
            continue
        seen.add(current.root)
        for dep in current.dependencies.values():
            if dep.git is None:
                root = (current.root / (dep.path or ".")).resolve()
            else:
                locked = previous.get(dep.name)
                if locked is None or locked.git != dep.git or locked.rev != dep.rev:
                    locked = Locked(dep.name, dep.git, dep.rev, _resolve_commit(dep))
                other = resolved.get(dep.name)
                if other is not None and other != locked:
                    raise PackageError(f"dos dependencias distintas se llaman {dep.name}")
                resolved[dep.name] = locked
                root = _checkout(locked)
            if (root / MANIFEST).is_file():
                pending.append(load_manifest(root))
    save_lock(manifest.root, resolved)
    return resolved


def _git(*args: str, cwd: Path | None = None) -> str:
    try:
        done = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
    except FileNotFoundError:
        raise PackageError("hace falta git y no está instalado") from None
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip().splitlines()[-1] if exc.stderr.strip() else str(exc)
        raise PackageError(f"git {' '.join(args[:2])}: {detail}") from None
    return done.stdout.strip()


def _resolve_commit(dep: Dependency) -> str:
    assert dep.git is not None
    mirror = cache_dir() / hashlib.sha256(dep.git.encode()).hexdigest()[:16] / "mirror"
    if mirror.is_dir():
        _git("fetch", "--quiet", "--tags", "origin", cwd=mirror)
    else:
        mirror.parent.mkdir(parents=True, exist_ok=True)
        _git("clone", "--quiet", "--no-checkout", dep.git, str(mirror))
    rev = dep.rev or "HEAD"
    for candidate in (f"origin/{rev}", rev):
        try:
            return _git("rev-parse", "--verify", f"{candidate}^{{commit}}", cwd=mirror)
        except PackageError:
            continue
    raise PackageError(f"{dep.name}: no existe la versión {rev!r} en {dep.git}")


def _checkout(locked: Locked) -> Path:
    root = checkout_dir(locked.git, locked.commit)
    if root.is_dir():
        return root
    mirror = root.parent / "mirror"
    if not mirror.is_dir():
        _resolve_commit(Dependency(locked.name, git=locked.git, rev=locked.commit))
    tmp = root.with_name(root.name + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    _git("clone", "--quiet", "--shared", str(mirror), str(tmp))
    _git("checkout", "--quiet", "--detach", locked.commit, cwd=tmp)
    shutil.rmtree(tmp / ".git")
    tmp.rename(root)
    return root


# --- crear, clonar y bifurcar -------------------------------------------------------------------


def camel(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("-"))


TEMPLATE = """// {title}
// Juego creado con `gamehub new`: una carrera hasta la meta. Cámbialo a tu gusto.
// Referencia del lenguaje: docs/wiki/lenguaje-game.md

game {camel} {{
  meta {{
    title: "{title}"
    version: "0.1.0"
  }}
  players 2

  params {{
    /// A cuánto hay que llegar
    target: Int = 10
    assert target >= 1, "la meta tiene que ser al menos 1"
  }}

  state {{
    total: Int = 0
    turn: Seat = 0
  }}

  flow {{
    start -> Play

    /// Por turnos, cada jugador suma 1 o 2; quien llega exactamente a la meta gana.
    decision Play {{
      actor: turn
      action add(n in 1..2) requires total + n <= target {{ total += n }}
      -> End when total == target
      -> Play {{ turn = next(turn) }}
    }}

    terminal End {{ payoff: win_loss(turn, 1, -1) }}
  }}

  test "quien llega a la meta gana" {{
    params {{ target: 3 }}
    play add(2), add(1)
    expect at(End) and payoff == [-1, 1]
  }}

  invariant total <= target
}}
"""


def new_package(root: Path, name: str, *, authors: list[str] | None = None) -> Manifest:
    """Crea un paquete con su manifiesto y un juego mínimo que compila y pasa su test."""
    if not NAME.match(name):
        raise PackageError(f"nombre no válido: {name!r} (minúsculas, números y guiones)")
    if root.exists() and any(root.iterdir()):
        raise PackageError(f"{root} ya existe y no está vacío")
    root.mkdir(parents=True, exist_ok=True)
    title = name.replace("-", " ").capitalize()
    game = TEMPLATE.format(title=title, camel=camel(name))
    (root / f"{name}.game").write_text(game, encoding="utf-8")
    manifest = Manifest(root=root, name=name, authors=authors or [], license="CC-BY-4.0")
    save_manifest(manifest)
    return manifest


def clone(source: str, root: Path) -> Manifest | None:
    """Clona un repositorio git y descarga sus dependencias (si es un paquete)."""
    if root.exists() and any(root.iterdir()):
        raise PackageError(f"{root} ya existe y no está vacío")
    _git("clone", "--quiet", source, str(root))
    if not (root / MANIFEST).is_file():
        return None
    manifest = load_manifest(root)
    fetch(manifest)
    return manifest


def fork(source: str, root: Path) -> Manifest:
    """Copia un paquete (repositorio git o directorio) y anota de dónde viene: con git, el
    remoto original pasa a llamarse `upstream` y `forked_from` lleva el commit."""
    local = Path(source)
    if local.is_dir() and not (local / ".git").exists():
        if root.exists() and any(root.iterdir()):
            raise PackageError(f"{root} ya existe y no está vacío")
        shutil.copytree(local, root, dirs_exist_ok=True)
        origin = str(local.resolve())
    else:
        clone(source, root)
        commit = _git("rev-parse", "HEAD", cwd=root)
        _git("remote", "rename", "origin", "upstream", cwd=root)
        origin = f"{source}@{commit}"
    if not (root / MANIFEST).is_file():
        raise PackageError(f"{source} no es un paquete de juego: falta {MANIFEST}")
    manifest = load_manifest(root)
    manifest.forked_from = origin
    save_manifest(manifest)
    return manifest
