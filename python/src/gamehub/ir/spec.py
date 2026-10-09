# SPDX-License-Identifier: Apache-2.0
"""Localización y carga de los archivos de especificación (spec/ir/v0)."""

from __future__ import annotations

import json
import os
from functools import cache
from pathlib import Path
from typing import Any

SCHEMA_BASE_URI = "https://gamehub.invalid/spec/ir/v0/"
SCHEMA_NAMES = ("ir", "common", "type", "expr", "stmt")


def spec_dir() -> Path:
    """Directorio spec/ir/v0. Se puede forzar con GAMEHUB_SPEC_DIR (ruta a spec/)."""
    override = os.environ.get("GAMEHUB_SPEC_DIR")
    if override:
        return Path(override) / "ir" / "v0"
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "spec" / "ir" / "v0"
        if (candidate / "ops.json").is_file():
            return candidate
    raise FileNotFoundError("No se encuentra spec/ir/v0; define GAMEHUB_SPEC_DIR")


def examples_dir() -> Path:
    return spec_dir().parent / "examples"


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


@cache
def load_schema(name: str) -> dict[str, Any]:
    return load_json(spec_dir() / f"{name}.schema.json")
