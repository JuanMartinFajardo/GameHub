# SPDX-License-Identifier: Apache-2.0
"""Diagnósticos (errores y avisos) con posición, al estilo de `rustc`:

    error[E301]: tipos incompatibles: se esperaba `Int`, se encontró `Bool`
      --> tictactoe.game:12:18
       |
    12 |     turn: Seat = true
       |                  ^^^^ esto es `Bool`
       |
       = ayuda: …

Los códigos se agrupan por familia: E1xx léxico y sintaxis, E2xx nombres y declaraciones,
E3xx tipos, E4xx estructura del flow, E5xx módulos y paquetes, E6xx tests; W… avisos.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TextIO

from gamehub.lang.source import Span


class Severity(Enum):
    ERROR = "error"
    WARNING = "aviso"
    NOTE = "nota"


@dataclass(frozen=True)
class Label:
    span: Span
    message: str = ""
    primary: bool = True


@dataclass
class Diagnostic:
    severity: Severity
    code: str
    message: str
    labels: list[Label] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    help: str | None = None

    @property
    def span(self) -> Span | None:
        for label in self.labels:
            if label.primary:
                return label.span
        return None

    def with_label(self, span: Span, message: str = "") -> Diagnostic:
        self.labels.append(Label(span, message, primary=False))
        return self

    def with_note(self, note: str) -> Diagnostic:
        self.notes.append(note)
        return self

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "severity": "error" if self.severity is Severity.ERROR else "warning",
            "code": self.code,
            "message": self.message,
        }
        span = self.span
        if span is not None and span.source is not None:
            line, col = span.source.location(span.start)
            end_line, end_col = span.source.location(max(span.start, span.end))
            out.update(
                file=span.source.name,
                line=line,
                column=col,
                end_line=end_line,
                end_column=end_col,
            )
        if self.notes:
            out["notes"] = list(self.notes)
        if self.help:
            out["help"] = self.help
        return out

    def __str__(self) -> str:
        return render(self, color=False)


class Diagnostics:
    """Colección de diagnósticos de una compilación."""

    def __init__(self) -> None:
        self.items: list[Diagnostic] = []

    def add(self, diagnostic: Diagnostic) -> Diagnostic:
        self.items.append(diagnostic)
        return diagnostic

    def error(
        self, code: str, message: str, span: Span, label: str = "", *, help: str | None = None
    ) -> Diagnostic:
        return self.add(Diagnostic(Severity.ERROR, code, message, [Label(span, label)], help=help))

    def warning(
        self, code: str, message: str, span: Span, label: str = "", *, help: str | None = None
    ) -> Diagnostic:
        return self.add(
            Diagnostic(Severity.WARNING, code, message, [Label(span, label)], help=help)
        )

    def extend(self, other: Diagnostics) -> None:
        self.items.extend(other.items)

    @property
    def errors(self) -> list[Diagnostic]:
        return [d for d in self.items if d.severity is Severity.ERROR]

    @property
    def warnings(self) -> list[Diagnostic]:
        return [d for d in self.items if d.severity is Severity.WARNING]

    @property
    def has_errors(self) -> bool:
        return any(d.severity is Severity.ERROR for d in self.items)

    def sorted(self) -> list[Diagnostic]:
        def key(d: Diagnostic) -> tuple[str, int, int]:
            span = d.span
            if span is None or span.source is None:
                return ("", 0, 0)
            return (span.source.name, span.start, 0 if d.severity is Severity.ERROR else 1)

        return sorted(self.items, key=key)

    def __iter__(self) -> Iterator[Diagnostic]:
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)


class CompileError(Exception):
    """La compilación produjo errores; `diagnostics` los contiene todos."""

    def __init__(self, diagnostics: Diagnostics) -> None:
        self.diagnostics = diagnostics
        errors = diagnostics.errors
        first = str(errors[0]) if errors else "error de compilación"
        more = f"\n(y {len(errors) - 1} errores más)" if len(errors) > 1 else ""
        super().__init__(first + more)


# --- Presentación -------------------------------------------------------------------------------

_COLORS = {
    Severity.ERROR: "\x1b[1;31m",
    Severity.WARNING: "\x1b[1;33m",
    Severity.NOTE: "\x1b[1;36m",
}
_BLUE = "\x1b[1;34m"
_BOLD = "\x1b[1m"
_RESET = "\x1b[0m"


def use_color(stream: TextIO) -> bool:
    return stream.isatty() and "NO_COLOR" not in os.environ


def render(d: Diagnostic, *, color: bool = False) -> str:
    def paint(text: str, code: str) -> str:
        return f"{code}{text}{_RESET}" if color else text

    head = paint(f"{d.severity.value}[{d.code}]", _COLORS[d.severity])
    lines = [f"{head}{paint(': ' + d.message, _BOLD) if color else ': ' + d.message}"]
    labelled = [lb for lb in d.labels if lb.span.source is not None]
    if labelled:
        primary = next((lb for lb in labelled if lb.primary), labelled[0])
        source = primary.span.source
        assert source is not None
        width = len(str(max(lb.span.end_line for lb in labelled)))
        gutter = " " * width
        lines.append(f"{gutter}{paint('-->', _BLUE)} {primary.span}")
        lines.append(f"{gutter} {paint('|', _BLUE)}")
        shown: list[int] = []
        for label in sorted(labelled, key=lambda lb: (lb.span.line, lb.span.start)):
            if label.span.source is not source:
                continue
            line = label.span.line
            text, col_start, col_end = _excerpt(label)
            if line not in shown:
                if shown and line > shown[-1] + 1:
                    lines.append(paint("...", _BLUE))
                number = str(line).rjust(width)
                lines.append(f"{paint(number, _BLUE)} {paint('|', _BLUE)} {text}")
                shown.append(line)
            marker = ("^" if label.primary else "-") * max(1, col_end - col_start)
            marker_color = _COLORS[d.severity] if label.primary else _BLUE
            message = f" {label.message}" if label.message else ""
            underline = paint(marker + message, marker_color)
            lines.append(f"{gutter} {paint('|', _BLUE)} {' ' * col_start}{underline}")
        for label in labelled:
            if label.span.source is not source:
                lines.append(f"{gutter} {paint('=', _BLUE)} nota: también en {label.span}")
    elif d.labels:
        lines.append(f"  --> {d.labels[0].span}")
    for note in d.notes:
        lines.append(f"{' ' * 2} {paint('=', _BLUE)} nota: {note}")
    if d.help:
        lines.append(f"{' ' * 2} {paint('=', _BLUE)} ayuda: {d.help}")
    return "\n".join(lines)


def _excerpt(label: Label) -> tuple[str, int, int]:
    """Línea del span (tabuladores expandidos) y columnas [inicio, fin) a subrayar."""
    span = label.span
    source = span.source
    assert source is not None
    line, col = source.location(span.start)
    raw = source.line_text(line)
    end_line, end_col = source.location(max(span.start, span.end))
    stop = end_col - 1 if end_line == line else len(raw)
    prefix = raw[: col - 1].expandtabs(4)
    middle = raw[col - 1 : stop].expandtabs(4)
    text = raw.expandtabs(4)
    start = len(prefix)
    return text, start, start + max(len(middle), 1)


def print_diagnostics(items: list[Diagnostic], stream: TextIO | None = None) -> None:
    out = stream or sys.stderr
    color = use_color(out)
    for d in items:
        print(render(d, color=color), file=out)
        print(file=out)
