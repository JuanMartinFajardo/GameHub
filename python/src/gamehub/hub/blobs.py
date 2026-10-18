# SPDX-License-Identifier: AGPL-3.0-or-later
"""Almacén de objetos del hub: contenido direccionado por su SHA-256 (las IR de las versiones,
las entradas de los trabajos, los archivos de las Pages).

En disco, `objetos/ab/cdef…`, escritos de forma atómica. Un mismo contenido se guarda una sola
vez; la interfaz (`put`, `get`, `has`, `size`) es la de un almacén S3, que puede sustituirlo
cuando el hub se aloje fuera (pregunta 14).
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from gamehub.ir.hashing import canonical_json


class BlobStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        if len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
            raise KeyError(key)
        return self.root / key[:2] / key[2:]

    def put(self, data: bytes) -> str:
        key = hashlib.sha256(data).hexdigest()
        path = self._path(key)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=path.parent)
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp, path)
        return key

    def put_json(self, value: Any) -> str:
        return self.put(canonical_json(value).encode("utf-8"))

    def get(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError:
            raise KeyError(key) from None

    def get_json(self, key: str) -> Any:
        return json.loads(self.get(key))

    def has(self, key: str) -> bool:
        try:
            return self._path(key).is_file()
        except KeyError:
            return False

    def size(self, key: str) -> int:
        return self._path(key).stat().st_size
