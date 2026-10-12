# SPDX-License-Identifier: Apache-2.0
"""El espacio de trabajo del Studio: un directorio con juegos.

Lista los archivos `.game` (y a qué paquete pertenecen), los lee y los guarda (sin salir nunca
del directorio), guarda la disposición del diagrama en el archivo hermano `<juego>.layout.json` y
consulta git para comparar con versiones anteriores.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gamehub.packages import MANIFEST, find_files, load_manifest

LAYOUT_SUFFIX = ".layout.json"
#: Tamaño máximo de un archivo que se guarda desde el Studio.
MAX_FILE = 2_000_000


class WorkspaceError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


@dataclass
class Workspace:
    root: Path

    def __post_init__(self) -> None:
        self.root = self.root.resolve()

    # --- rutas ----------------------------------------------------------------------------------

    def resolve(self, relative: str) -> Path:
        """La ruta absoluta de `relative`, comprobando que no sale del espacio de trabajo."""
        if not relative or "\0" in relative:
            raise WorkspaceError("ruta vacía o no válida")
        path = (self.root / relative).resolve()
        if path != self.root and self.root not in path.parents:
            raise WorkspaceError("la ruta sale del espacio de trabajo", 403)
        return path

    def relative(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()

    # --- archivos -------------------------------------------------------------------------------

    def files(self) -> list[dict[str, Any]]:
        out = []
        for path in find_files(self.root, ".game"):
            package = _package_of(path, self.root)
            entry: dict[str, Any] = {"path": self.relative(path), "name": path.stem}
            if package is not None:
                entry["package"] = package
            out.append(entry)
        return sorted(out, key=lambda e: e["path"])

    def read(self, relative: str) -> dict[str, Any]:
        path = self.resolve(relative)
        if path.suffix != ".game":
            raise WorkspaceError("solo se abren archivos .game")
        if not path.is_file():
            raise WorkspaceError(f"no existe {relative}", 404)
        text = path.read_text(encoding="utf-8")
        return {
            "path": self.relative(path),
            "uri": path.as_uri(),
            "text": text,
            "mtime": stamp(path),
            "layout": self.read_layout(relative),
        }

    def write(self, relative: str, text: str, expected_mtime: int | None = None) -> dict[str, Any]:
        path = self.resolve(relative)
        if path.suffix != ".game":
            raise WorkspaceError("solo se guardan archivos .game")
        if len(text.encode("utf-8")) > MAX_FILE:
            raise WorkspaceError("el archivo es demasiado grande")
        changed = path.exists() and stamp(path) != expected_mtime
        if expected_mtime is not None and changed:
            raise WorkspaceError("el archivo ha cambiado en el disco desde que se abrió", 409)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".game.tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
        return {"path": self.relative(path), "mtime": stamp(path)}

    def layout_path(self, relative: str) -> Path:
        path = self.resolve(relative)
        return path.with_name(path.stem + LAYOUT_SUFFIX)

    def read_layout(self, relative: str) -> dict[str, Any] | None:
        path = self.layout_path(relative)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def write_layout(self, relative: str, layout: dict[str, Any]) -> None:
        if not isinstance(layout, dict):
            raise WorkspaceError("la disposición tiene que ser un objeto")
        text = json.dumps(layout, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if len(text) > MAX_FILE:
            raise WorkspaceError("la disposición es demasiado grande")
        self.layout_path(relative).write_text(text, encoding="utf-8")

    # --- git ------------------------------------------------------------------------------------

    def git(self, *args: str) -> str | None:
        try:
            out = subprocess.run(
                ["git", *args],
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return out.stdout if out.returncode == 0 else None

    def history(self, relative: str, limit: int = 30) -> list[dict[str, str]]:
        path = self.resolve(relative)
        out = self.git("log", f"-{limit}", "--format=%H%x1f%cs%x1f%s", "--", str(path))
        if not out:
            return []
        commits = []
        for line in out.splitlines():
            rev, date, subject = [*line.split("\x1f"), "", ""][:3]
            commits.append({"rev": rev, "date": date, "subject": subject})
        return commits

    def show(self, relative: str, rev: str) -> str:
        if not rev or not all(c.isalnum() or c in "~^._-/" for c in rev):
            raise WorkspaceError("revisión no válida")
        path = self.resolve(relative)
        top = self.git("rev-parse", "--show-toplevel")
        if top is None:
            raise WorkspaceError("el espacio de trabajo no está en un repositorio git")
        inside = path.relative_to(Path(top.strip()).resolve()).as_posix()
        text = self.git("show", f"{rev}:{inside}")
        if text is None:
            raise WorkspaceError(f"{relative} no existe en {rev}", 404)
        return text


def stamp(path: Path) -> int:
    """La hora de la última modificación en microsegundos: la versión del archivo que se manda a
    la app (en nanosegundos no cabe exacta en un número de JavaScript y nunca coincidiría)."""
    return path.stat().st_mtime_ns // 1000


def _package_of(path: Path, root: Path) -> str | None:
    for parent in [path.parent, *path.parent.parents]:
        if (parent / MANIFEST).is_file():
            try:
                return load_manifest(parent).name
            except Exception:
                return None
        if parent == root:
            break
    return None
