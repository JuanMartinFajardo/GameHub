# SPDX-License-Identifier: Apache-2.0
"""GameIR: representación intermedia canónica de los juegos (ver docs/wiki/ir.md)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from gamehub.ir.problems import Problem
from gamehub.ir.schema import schema_problems
from gamehub.ir.spec import load_json
from gamehub.ir.wellformed import wellformed_problems

__all__ = ["Problem", "check", "check_file", "schema_problems", "wellformed_problems"]


def check(doc: Any) -> list[Problem]:
    """Valida un documento: primero el esquema y, si lo cumple, la buena formación."""
    problems = schema_problems(doc)
    if problems:
        return problems
    return wellformed_problems(doc)


def check_file(path: Path) -> list[Problem]:
    try:
        doc = load_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        return [Problem("", f"no se puede leer: {exc}")]
    return check(doc)
