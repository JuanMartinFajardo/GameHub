# SPDX-License-Identifier: Apache-2.0
"""Hash de reglas: SHA-256 del JSON canónico de la IR, sin metadatos ni documentación.

Dos documentos que solo difieren en orden de claves, espacios, `meta`, campos `doc` o mensajes
de las restricciones tienen el mismo hash: describen exactamente las mismas reglas.

La canonicalización coincide con RFC 8785 (JCS) en el subconjunto de JSON que usa la IR
(objetos, listas, cadenas, enteros, booleanos y null; claves ASCII): claves ordenadas, sin
espacios, UTF-8 sin escapar. Los números en coma flotante no están permitidos.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> str:
    _reject_floats(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def strip_cosmetic(doc: dict[str, Any]) -> dict[str, Any]:
    """Copia del documento sin `meta`, sin campos `doc`, sin `message` en `constraints` y sin
    valores por defecto explícitos (listas vacías, visibilidad `all`).

    No entra en las S-expresiones (listas que empiezan por una cadena): un campo llamado `doc`
    dentro de un literal de struct o de un evento forma parte de las reglas.
    """
    stripped = {
        k: _strip(v) for k, v in doc.items() if k not in ("meta", "doc") and not _is_default(k, v)
    }
    if "constraints" in stripped:
        stripped["constraints"] = [
            {k: v for k, v in c.items() if k != "message"} for c in stripped["constraints"]
        ]
    return stripped


def rules_hash(doc: dict[str, Any]) -> str:
    digest = hashlib.sha256(canonical_json(strip_cosmetic(doc)).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


#: Claves cuyo valor por defecto no cambia las reglas: se omiten antes de calcular el hash.
_DEFAULTS = {"visibility": "all", "size_visibility": "all"}


def _is_default(key: str, value: Any) -> bool:
    return value == [] or _DEFAULTS.get(key) == value


def _strip(node: Any) -> Any:
    if isinstance(node, dict):
        return {k: _strip(v) for k, v in node.items() if k != "doc" and not _is_default(k, v)}
    if isinstance(node, list):
        if node and isinstance(node[0], str):
            return node
        return [_strip(item) for item in node]
    return node


def _reject_floats(value: Any) -> None:
    if isinstance(value, float):
        raise TypeError(f"la IR no admite números en coma flotante: {value!r}")
    if isinstance(value, dict):
        for item in value.values():
            _reject_floats(item)
    elif isinstance(value, list):
        for item in value:
            _reject_floats(item)
