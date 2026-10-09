# SPDX-License-Identifier: Apache-2.0
"""Problemas encontrados al validar un documento GameIR."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class Problem:
    """Un error localizado. `path` usa segmentos separados por '/' (p. ej. 'flow/nodes/0/actor')."""

    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.path or '/'}: {self.message}"
