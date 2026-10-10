# SPDX-License-Identifier: Apache-2.0
"""`gamehub ui new`: una UI propia de React para un juego, a partir de la plantilla
(`gamehub/templates/ui-react`).

La UI nace en `games/<juego>/ui`, dentro del monorepo: el workspace de pnpm (en la raíz)
incluye `games/*/ui`, así que tras `pnpm install` usa los paquetes de GameHub sin publicarlos, la
app web la registra sola y `pnpm dev` en su carpeta abre la app solo con ese juego. Trae los tipos
del juego (`src/game.ts`, de `gamehub sdk ts`) y un tablero inicial que enseña el estado y un
botón por acción legal, para cambiarlo a gusto.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any

from gamehub.packages import PackageError
from gamehub.render.typescript import game_types

TEMPLATES = ("react",)


def _text(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("es") or next(iter(value.values()), ""))
    return str(value or "")


def new_ui(game_dir: Path, ir: dict[str, Any], target: Path | None = None) -> Path:
    """Crea la UI del juego `ir` (cuyo paquete está en `game_dir`) en `target` (por defecto,
    `game_dir/ui`). Lanza `PackageError` si ya existe."""
    target = target or game_dir / "ui"
    if target.exists() and any(target.iterdir()):
        raise PackageError(f"{target} ya existe y no está vacío")
    values = {
        "__GAME_ID__": ir["game"]["id"],
        "__TITLE__": _text(ir.get("meta", {}).get("title")) or ir["game"]["id"],
        "__GAME_DIR__": game_dir.name,
    }
    template = resources.files("gamehub").joinpath("templates", "ui-react")
    _copy(template, target, values)
    (target / "src" / "game.ts").write_text(game_types(ir), encoding="utf-8")
    return target


def _copy(source: Any, target: Path, values: dict[str, str]) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for entry in source.iterdir():
        if entry.name in ("__pycache__", "node_modules"):
            continue
        if entry.is_dir():
            _copy(entry, target / entry.name, values)
            continue
        text = entry.read_text(encoding="utf-8")
        for key, value in values.items():
            text = text.replace(key, value)
        (target / entry.name).write_text(text, encoding="utf-8")


def in_workspace(target: Path) -> bool:
    """¿Está `target` donde el workspace de pnpm lo encuentra (`<repo>/games/<juego>/ui`)?"""
    target = target.resolve()
    return (
        target.name == "ui"
        and target.parent.parent.name == "games"
        and (target.parent.parent.parent / "pnpm-workspace.yaml").is_file()
    )
