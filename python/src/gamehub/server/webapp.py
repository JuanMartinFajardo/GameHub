# SPDX-License-Identifier: Apache-2.0
"""La app web para jugar en el navegador (`web/apps/play`), servida por el servidor de partidas.

Se busca, por orden: `GAMEHUB_WEB_DIR`; la copia que viaja dentro del paquete instalado
(`gamehub/webapp`, la pone ahí la construcción de la rueda); la compilación del repositorio
(`web/apps/play/dist`, tras `pnpm -C web build`). Sin ella, el servidor funciona igual, con
unas páginas mínimas en vez de la app.

Las rutas de la app (`/`, `/r/CÓDIGO`, `/replay/ID`, `/local/JUEGO`, `/kit`) devuelven su
`index.html`; el resto de archivos, tal cual.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Rutas de la propia app (enrutado en el navegador): todas sirven index.html.
APP_ROUTES = ("/", "/r/{code}", "/replay/{id}", "/local/{game}", "/kit", "/new/{game}")


def web_dir() -> Path | None:
    """El directorio de la app web compilada (con su index.html), o None si no hay."""
    env = os.environ.get("GAMEHUB_WEB_DIR")
    if env:
        path = Path(env)
        return path if (path / "index.html").is_file() else None
    for parent in Path(__file__).resolve().parents:
        for candidate in (parent / "webapp", parent / "web" / "apps" / "play" / "dist"):
            if (candidate / "index.html").is_file():
                return candidate
    return None
