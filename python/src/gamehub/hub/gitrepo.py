# SPDX-License-Identifier: AGPL-3.0-or-later
"""Los repositorios git del hub: uno *bare* por repositorio, manejado con el `git` del sistema.

El hub no reinventa git: los clientes clonan y empujan con git normal (HTTP inteligente, servido
por `git http-backend`) y el propio hub hace sus operaciones con las órdenes de bajo nivel de git
(`commit-tree`, `merge-tree`, `update-ref`…), sin copia de trabajo: editar archivos desde la web,
traer la rama de una propuesta, fusionarla o exportar el árbol de una versión para compilarla.

Las órdenes se ejecutan sin la configuración global ni la del sistema de quien arranca el hub
(una firma GPG obligatoria o unos hooks propios no deben colarse en el servidor).
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import tarfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: Variables de entorno de cada orden: git sin configuración ajena y sin preguntar nada.
BASE_ENV = {
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_TERMINAL_PROMPT": "0",
    "LC_ALL": "C",
}


#: El hook que protege lo que solo cambia el hub (sus propias órdenes no pasan por él).
PRE_RECEIVE = """#!/bin/sh
status=0
while read old new ref; do
  case "$ref" in
    refs/tags/v[0-9]*|refs/pull/*)
      echo "GameHub: $ref la pone el hub (publica versiones con gamehub publish)" >&2
      status=1 ;;
  esac
done
exit $status
"""


class GitError(Exception):
    """Una orden de git que falló (o un conflicto al fusionar)."""

    def __init__(self, message: str, *, conflict: bool = False) -> None:
        super().__init__(message)
        self.conflict = conflict


def git_env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(BASE_ENV)
    if extra:
        env.update(extra)
    return env


def run_git(
    *args: str,
    cwd: Path | None = None,
    input: bytes | None = None,
    env: Mapping[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    try:
        done = subprocess.run(
            ["git", *args], cwd=cwd, input=input, env=git_env(env), capture_output=True
        )
    except FileNotFoundError:
        raise GitError("el hub necesita git y no está instalado") from None
    if check and done.returncode != 0:
        detail = done.stderr.decode("utf-8", "replace").strip().splitlines()
        raise GitError(f"git {args[0]}: {detail[-1] if detail else done.returncode}")
    return done


@dataclass(frozen=True)
class Author:
    name: str
    email: str

    def env(self, when: int | None = None) -> dict[str, str]:
        env = {
            "GIT_AUTHOR_NAME": self.name,
            "GIT_AUTHOR_EMAIL": self.email,
            "GIT_COMMITTER_NAME": self.name,
            "GIT_COMMITTER_EMAIL": self.email,
        }
        if when is not None:
            env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = f"{when} +0000"
        return env


class GitRepo:
    def __init__(self, path: Path) -> None:
        self.path = path

    # --- crear ----------------------------------------------------------------------------------

    @classmethod
    def init(cls, path: Path, branch: str = "main") -> GitRepo:
        path.parent.mkdir(parents=True, exist_ok=True)
        run_git("init", "--quiet", "--bare", f"--initial-branch={branch}", str(path))
        repo = cls(path)
        repo.configure()
        return repo

    @classmethod
    def fork(cls, source: GitRepo, path: Path) -> GitRepo:
        """Una copia del repositorio (ramas y etiquetas; no las de las propuestas)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        run_git("clone", "--quiet", "--bare", "--no-hardlinks", str(source.path), str(path))
        repo = cls(path)
        repo.configure()
        # El clon apunta a su origen: el hub no lo necesita (las propuestas traen las ramas).
        repo.git("remote", "remove", "origin", check=False)
        return repo

    def configure(self) -> None:
        for key, value in (
            ("http.receivepack", "true"),
            ("receive.fsckObjects", "true"),
            ("gc.auto", "0"),
            ("core.logAllRefUpdates", "false"),
        ):
            self.git("config", key, value)
        # Las referencias de las propuestas y las etiquetas de versión (v1.2.3) las pone el hub:
        # un push no puede crearlas, moverlas ni borrarlas.
        self.git("config", "receive.hideRefs", "refs/pull")
        hook = self.path / "hooks" / "pre-receive"
        hook.parent.mkdir(exist_ok=True)
        hook.write_text(PRE_RECEIVE, encoding="utf-8")
        hook.chmod(0o755)

    def delete(self) -> None:
        shutil.rmtree(self.path, ignore_errors=True)

    # --- órdenes --------------------------------------------------------------------------------

    def git(
        self,
        *args: str,
        input: bytes | None = None,
        env: Mapping[str, str] | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[bytes]:
        return run_git(f"--git-dir={self.path}", *args, input=input, env=env, check=check)

    def text(self, *args: str, env: Mapping[str, str] | None = None) -> str:
        return self.git(*args, env=env).stdout.decode("utf-8", "replace").strip()

    # --- leer -----------------------------------------------------------------------------------

    def resolve(self, ref: str) -> str | None:
        """El commit de una rama, etiqueta o commit (abreviado o no); None si no existe."""
        if ref.startswith("-"):
            return None
        done = self.git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", check=False)
        if done.returncode != 0:
            return None
        return done.stdout.decode().strip() or None

    def refs(self, prefix: str) -> dict[str, str]:
        out = self.text(
            "for-each-ref", "--format=%(refname)%00%(*objectname)%00%(objectname)", prefix
        )
        refs: dict[str, str] = {}
        for line in out.splitlines():
            name, peeled, obj = line.split("\0")
            refs[name.removeprefix(prefix)] = peeled or obj
        return refs

    def branches(self) -> dict[str, str]:
        return self.refs("refs/heads/")

    def tags(self) -> dict[str, str]:
        return self.refs("refs/tags/")

    def all_refs(self) -> dict[str, str]:
        return self.refs("refs/")

    def is_empty(self) -> bool:
        return not self.branches()

    def read(self, commit: str, path: str) -> bytes | None:
        done = self.git("cat-file", "blob", f"{commit}:{path}", check=False)
        return done.stdout if done.returncode == 0 else None

    def ls(self, commit: str, path: str = "", *, recursive: bool = False) -> list[dict[str, Any]]:
        """Las entradas de un directorio (o todos los archivos, con `recursive`)."""
        target = f"{commit}:{path}" if path else commit
        args = ["ls-tree", "-z", "--long"]
        if recursive:
            args.append("-r")
        done = self.git(*args, target, check=False)
        if done.returncode != 0:
            raise GitError(f"no existe {path or '/'} en {commit[:12]}")
        entries = []
        for item in done.stdout.decode("utf-8", "replace").split("\0"):
            if not item:
                continue
            meta, name = item.split("\t", 1)
            mode, kind, obj, size = meta.split()
            full = f"{path.rstrip('/')}/{name}" if path else name
            entries.append(
                {
                    "name": name.rsplit("/", 1)[-1],
                    "path": full,
                    "type": "dir" if kind == "tree" else "file",
                    "size": None if size == "-" else int(size),
                    "mode": mode,
                    "id": obj,
                }
            )
        entries.sort(key=lambda e: (e["type"] != "dir", e["path"]))
        return entries

    def log(self, ref: str, *, limit: int = 50, path: str | None = None) -> list[dict[str, Any]]:
        fmt = "%H%x00%P%x00%an%x00%ae%x00%at%x00%s%x00%b%x1e"
        args = ["log", f"--format={fmt}", f"--max-count={limit}", ref]
        if path:
            args += ["--", path]
        done = self.git(*args, check=False)
        if done.returncode != 0:
            return []
        commits = []
        for record in done.stdout.decode("utf-8", "replace").split("\x1e"):
            record = record.strip("\n")
            if not record:
                continue
            sha, parents, name, email, at, subject, body = record.split("\0")
            commits.append(
                {
                    "id": sha,
                    "parents": parents.split(),
                    "author": name,
                    "email": email,
                    "time": int(at),
                    "subject": subject,
                    "body": body.strip(),
                }
            )
        return commits

    def merge_base(self, a: str, b: str) -> str | None:
        done = self.git("merge-base", a, b, check=False)
        if done.returncode != 0:
            return None
        return done.stdout.decode().strip() or None

    def is_ancestor(self, a: str, b: str) -> bool:
        return self.git("merge-base", "--is-ancestor", a, b, check=False).returncode == 0

    def diff(self, a: str, b: str) -> tuple[str, list[dict[str, Any]]]:
        """El diff unificado de `a` a `b` y sus estadísticas por archivo."""
        patch = self.git("diff", "--no-color", "--no-ext-diff", "-M", a, b).stdout
        stats = []
        numstat = self.text("diff", "--numstat", "-M", "-z", a, b)
        parts = numstat.split("\0")
        i = 0
        while i < len(parts):
            if not parts[i]:
                i += 1
                continue
            added, removed, path = parts[i].split("\t", 2)
            if path == "":  # renombrado: vienen el origen y el destino en las dos siguientes
                path = f"{parts[i + 1]} → {parts[i + 2]}"
                i += 2
            stats.append(
                {
                    "path": path,
                    "added": None if added == "-" else int(added),
                    "removed": None if removed == "-" else int(removed),
                }
            )
            i += 1
        return patch.decode("utf-8", "replace"), stats

    def export(self, commit: str, dest: Path) -> None:
        """El árbol de un commit, escrito en `dest` (sin `.git`)."""
        data = self.git("archive", "--format=tar", commit).stdout
        dest.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(data)) as tar:
            tar.extractall(dest, filter="data")

    def size(self) -> int:
        return sum(f.stat().st_size for f in self.path.rglob("*") if f.is_file())

    # --- escribir -------------------------------------------------------------------------------

    def update_ref(self, ref: str, new: str, old: str | None = None) -> None:
        """Mueve una referencia; con `old`, solo si sigue donde estaba (si no, `GitError`)."""
        args = ["update-ref", ref, new]
        if old is not None:
            args.append(old)
        done = self.git(*args, check=False)
        if done.returncode != 0:
            raise GitError(f"{ref} ha cambiado mientras tanto: vuelve a intentarlo")

    def create_ref(self, ref: str, new: str) -> None:
        """Crea una referencia que no existe (una etiqueta de versión, p. ej.)."""
        self.update_ref(ref, new, "0" * 40)

    def delete_ref(self, ref: str) -> None:
        self.git("update-ref", "-d", ref, check=False)

    def fetch(self, other: GitRepo, src: str, dst: str) -> str:
        """Trae `src` de otro repositorio del hub a la referencia `dst`; devuelve su commit."""
        self.git("fetch", "--quiet", "--no-tags", str(other.path), f"+{src}:{dst}")
        commit = self.resolve(dst)
        assert commit is not None
        return commit

    def commit_files(
        self,
        branch: str,
        changes: Mapping[str, bytes | None],
        message: str,
        author: Author,
        *,
        expected: str | None = None,
        when: int | None = None,
    ) -> str:
        """Un commit en `branch` que escribe (o borra, con None) los archivos de `changes`.
        `expected` es el commit sobre el que se editó: si la rama se movió, `GitError`."""
        parent = self.resolve(f"refs/heads/{branch}")
        if expected is not None and parent != expected:
            raise GitError(
                f"la rama {branch} ha cambiado mientras editabas: recarga", conflict=True
            )
        index = self.path / f"index.{os.getpid()}.{id(changes)}"
        env = {"GIT_INDEX_FILE": str(index)}
        try:
            if parent:
                self.git("read-tree", parent, env=env)
            else:
                self.git("read-tree", "--empty", env=env)
            for path, content in changes.items():
                clean = _clean_path(path)
                if content is None:
                    self.git("update-index", "--force-remove", "--", clean, env=env)
                    continue
                blob = (
                    self.git("hash-object", "-w", "--stdin", input=content).stdout.decode().strip()
                )
                self.git("update-index", "--add", "--cacheinfo", f"100644,{blob},{clean}", env=env)
            tree = self.text("write-tree", env=env)
        finally:
            index.unlink(missing_ok=True)
        if parent and tree == self.text("rev-parse", f"{parent}^{{tree}}"):
            raise GitError("no hay cambios que guardar")
        args = ["commit-tree", tree, "-m", message]
        if parent:
            args[2:2] = ["-p", parent]
        commit = self.text(*args, env=author.env(when))
        self.update_ref(f"refs/heads/{branch}", commit, parent or "0" * 40)
        return commit

    def merge(
        self, branch: str, head: str, message: str, author: Author, *, when: int | None = None
    ) -> str:
        """Fusiona el commit `head` en `branch`: avance rápido si se puede; si no, un commit de
        fusión (sin copia de trabajo, con `merge-tree`). Un conflicto es `GitError(conflict)`."""
        tip = self.resolve(f"refs/heads/{branch}")
        if tip is None:
            raise GitError(f"no existe la rama {branch}")
        if self.is_ancestor(head, tip):
            raise GitError("no hay nada que fusionar: la rama ya contiene esos cambios")
        if self.is_ancestor(tip, head):
            self.update_ref(f"refs/heads/{branch}", head, tip)
            return head
        done = self.git("merge-tree", "--write-tree", "--name-only", tip, head, check=False)
        lines = done.stdout.decode("utf-8", "replace").splitlines()
        if done.returncode == 1:
            files = [
                ln for ln in lines[1:] if ln and not ln.startswith(("Auto-merging", "CONFLICT"))
            ]
            raise GitError(
                "hay conflictos en " + ", ".join(sorted(set(files))[:10] or ["varios archivos"]),
                conflict=True,
            )
        if done.returncode != 0:
            raise GitError("git merge-tree: " + done.stderr.decode().strip())
        tree = lines[0].strip()
        commit = self.text(
            "commit-tree", tree, "-p", tip, "-p", head, "-m", message, env=author.env(when)
        )
        self.update_ref(f"refs/heads/{branch}", commit, tip)
        return commit


def _clean_path(path: str) -> str:
    parts = [p for p in path.replace("\\", "/").split("/") if p not in ("", ".")]
    if not parts or any(p == ".." or p == ".git" for p in parts):
        raise GitError(f"ruta no válida: {path!r}")
    return "/".join(parts)
