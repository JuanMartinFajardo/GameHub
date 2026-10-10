# SPDX-License-Identifier: Apache-2.0
"""JSON legible para la IR: cada valor en una línea si cabe en el ancho; si no, se parte en
varias líneas. Las S-expresiones cortas quedan compactas (`["var", "turn"]`)."""

from __future__ import annotations

import json
from typing import Any


def dumps(value: Any, width: int = 100) -> str:
    return _dump(value, 0, width) + "\n"


def _dump(value: Any, indent: int, width: int) -> str:
    flat = json.dumps(value, ensure_ascii=False, separators=(", ", ": "))
    if indent + len(flat) <= width or not isinstance(value, dict | list) or not value:
        return flat
    pad = " " * (indent + 2)
    if isinstance(value, dict):
        items = [
            f"{pad}{json.dumps(k, ensure_ascii=False)}: {_dump(v, indent + 2, width)}"
            for k, v in value.items()
        ]
        return "{\n" + ",\n".join(items) + "\n" + " " * indent + "}"
    items = [pad + _dump(v, indent + 2, width) for v in value]
    return "[\n" + ",\n".join(items) + "\n" + " " * indent + "]"
