# SPDX-License-Identifier: Apache-2.0
"""Plantillas de juego para empezar (`gamehub new --template`, «Nuevo juego» del Studio).

Cada plantilla es un `.game` en `templates/games/` con `__TITLE__` y `__GAME__` en lugar del
título y del nombre del juego; `templates.json` dice su título y su descripción (es/en). Todas
compilan y pasan sus tests (lo comprueba la batería de tests).
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

DIR = Path(__file__).parent / "templates" / "games"
DEFAULT = "carrera"


@cache
def templates() -> list[dict[str, Any]]:
    return json.loads((DIR / "templates.json").read_text(encoding="utf-8"))


def ids() -> list[str]:
    return [t["id"] for t in templates()]


def render(template: str, *, title: str, game: str) -> str:
    if template not in ids():
        raise KeyError(f"plantilla desconocida: {template} (hay {', '.join(ids())})")
    text = (DIR / f"{template}.game").read_text(encoding="utf-8")
    return text.replace("__TITLE__", title).replace("__GAME__", game)
