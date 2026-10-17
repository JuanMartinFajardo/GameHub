# SPDX-License-Identifier: Apache-2.0
"""Exportación estática de la app para jugar (F8): la app web compilada y la IR de cada juego
como archivos, sin servidor de partidas.

Se juega en el dispositivo (personas que se pasan el turno y bots) con el núcleo C++ en
WebAssembly (`@gamehub/engine`); no hay salas en línea, y `api/v1/info` lo dice (`offline`). El
directorio se sirve con cualquier servidor de archivos estáticos **en la raíz** de un dominio
(GitHub Pages, Netlify, `python -m http.server`…): cada ruta de la app tiene su copia de
`index.html` y `404.html` cubre las demás.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from gamehub import __version__
from gamehub.protocol import VERSION
from gamehub.server.catalog import Catalog

#: Lo que dice que un directorio es una exportación (se puede sobrescribir).
MARK = Path("api") / "v1" / "info"


class ExportError(Exception):
    pass


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    path.write_text(text, encoding="utf-8")


def export_site(out: Path, catalog: Catalog, *, web: Path, name: str = "GameHub") -> int:
    """Escribe el sitio en `out` (vacío, inexistente o una exportación anterior). Devuelve el
    número de juegos."""
    if out.exists() and any(out.iterdir()) and not (out / MARK).is_file():
        raise ExportError(f"{out} no está vacío ni es una exportación anterior")
    if not (web / "index.html").is_file():
        raise ExportError(f"{web} no tiene la app compilada (pnpm build en la raíz)")
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(web, out)
    index = (out / "index.html").read_text(encoding="utf-8")
    api = out / "api" / "v1"
    games = sorted(catalog.games.values(), key=lambda g: g.id)
    _write_json(
        out / MARK,
        {
            "name": name,
            "version": __version__,
            "protocol": VERSION,
            "upload": False,
            "games": catalog.info(),
            "rooms": 0,
            "offline": True,
        },
    )
    _write_json(api / "rooms", {"rooms": []})
    _write_json(api / "matches", {"matches": []})
    for game in games:
        _write_json(api / "games" / game.id, game.ir)
        page = out / "local" / game.id / "index.html"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(index, encoding="utf-8")
    (out / "404.html").write_text(index, encoding="utf-8")
    return len(games)
