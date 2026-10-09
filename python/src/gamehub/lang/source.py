# SPDX-License-Identifier: Apache-2.0
"""Textos fuente y posiciones (spans) dentro de ellos."""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, eq=False)
class Source:
    """Un archivo `.game` (o un texto suelto). `name` es lo que se muestra en los diagnósticos."""

    name: str
    text: str
    path: Path | None = None
    _line_starts: tuple[int, ...] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        starts = [0]
        for i, ch in enumerate(self.text):
            if ch == "\n":
                starts.append(i + 1)
        object.__setattr__(self, "_line_starts", tuple(starts))

    @staticmethod
    def from_path(path: Path, name: str | None = None) -> Source:
        text = path.read_text(encoding="utf-8")
        return Source(name or str(path), text, path)

    def location(self, offset: int) -> tuple[int, int]:
        """(línea, columna), ambas desde 1. La columna cuenta caracteres, no bytes."""
        line = bisect_right(self._line_starts, offset) - 1
        return line + 1, offset - self._line_starts[line] + 1

    def line_text(self, line: int) -> str:
        """Texto de la línea `line` (desde 1), sin el salto de línea."""
        start = self._line_starts[line - 1]
        end = self._line_starts[line] - 1 if line < len(self._line_starts) else len(self.text)
        return self.text[start:end].rstrip("\r")

    @property
    def line_count(self) -> int:
        return len(self._line_starts)


@dataclass(frozen=True, slots=True)
class Span:
    """Intervalo semiabierto [start, end) de desplazamientos en un `Source`."""

    source: Source | None
    start: int
    end: int

    def to(self, other: Span) -> Span:
        """Span desde el inicio de este hasta el final de `other`."""
        return Span(self.source, self.start, max(self.end, other.end))

    @property
    def line(self) -> int:
        return self.source.location(self.start)[0] if self.source else 0

    @property
    def end_line(self) -> int:
        if self.source is None:
            return 0
        return self.source.location(max(self.start, self.end - 1))[0]

    def __str__(self) -> str:
        if self.source is None:
            return "<sin posición>"
        line, col = self.source.location(self.start)
        return f"{self.source.name}:{line}:{col}"


#: Span vacío para nodos sintetizados (descompilador, mods, combinadores).
NO_SPAN = Span(None, 0, 0)
