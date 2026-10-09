# SPDX-License-Identifier: Apache-2.0
"""Álgebra de documentos para maquetar texto (al estilo de Wadler y Prettier).

Un documento describe el texto con puntos de corte opcionales; `render` decide qué grupos caben
en una línea y cuáles se parten. Es lo que usa el formateador de Nomos.
"""

from __future__ import annotations

from dataclasses import dataclass


class Doc:
    pass


@dataclass(frozen=True)
class Text(Doc):
    text: str


@dataclass(frozen=True)
class Concat(Doc):
    parts: tuple[Doc, ...]


@dataclass(frozen=True)
class Nest(Doc):
    indent: int
    doc: Doc


@dataclass(frozen=True)
class Group(Doc):
    doc: Doc


@dataclass(frozen=True)
class Line(Doc):
    """Salto opcional: en un grupo plano es un espacio (o nada si `soft`); `hard` siempre salta
    y obliga a partir los grupos que lo contienen."""

    soft: bool = False
    hard: bool = False


@dataclass(frozen=True)
class IfBreak(Doc):
    broken: Doc
    flat: Doc


NIL = Text("")
LINE = Line()
SOFTLINE = Line(soft=True)
HARDLINE = Line(hard=True)


def text(s: str) -> Doc:
    return Text(s)


def concat(*parts: Doc | str) -> Doc:
    flat: list[Doc] = []
    for p in parts:
        if isinstance(p, str):
            if p:
                flat.append(Text(p))
        elif isinstance(p, Concat):
            flat.extend(p.parts)
        elif p != NIL:
            flat.append(p)
    if len(flat) == 1:
        return flat[0]
    return Concat(tuple(flat))


def nest(indent: int, *parts: Doc | str) -> Doc:
    return Nest(indent, concat(*parts))


def group(*parts: Doc | str) -> Doc:
    return Group(concat(*parts))


def join(separator: Doc | str, docs: list[Doc]) -> Doc:
    parts: list[Doc | str] = []
    for i, d in enumerate(docs):
        if i:
            parts.append(separator)
        parts.append(d)
    return concat(*parts)


def has_hardline(doc: Doc, memo: dict[int, bool] | None = None) -> bool:
    memo = {} if memo is None else memo
    key = id(doc)
    if key in memo:
        return memo[key]
    if isinstance(doc, Line):
        result = doc.hard
    elif isinstance(doc, Concat):
        result = any(has_hardline(p, memo) for p in doc.parts)
    elif isinstance(doc, Nest | Group):
        result = has_hardline(doc.doc, memo)
    elif isinstance(doc, IfBreak):
        result = has_hardline(doc.broken, memo) or has_hardline(doc.flat, memo)
    else:
        result = False
    memo[key] = result
    return result


def _flat_width(doc: Doc, limit: int) -> int:
    """Ancho del documento en modo plano (deja de contar al superar `limit`)."""
    width = 0
    stack = [doc]
    while stack and width <= limit:
        d = stack.pop()
        if isinstance(d, Text):
            width += len(d.text)
        elif isinstance(d, Concat):
            stack.extend(reversed(d.parts))
        elif isinstance(d, Nest | Group):
            stack.append(d.doc)
        elif isinstance(d, Line):
            if d.hard:
                return limit + 1
            width += 0 if d.soft else 1
        elif isinstance(d, IfBreak):
            stack.append(d.flat)
    return width


def render(doc: Doc, width: int = 100) -> str:
    out: list[str] = []
    col = 0
    memo: dict[int, bool] = {}
    flat_mode, break_mode = 0, 1
    stack: list[tuple[int, int, Doc]] = [(0, break_mode, doc)]
    while stack:
        indent, mode, d = stack.pop()
        if isinstance(d, Text):
            out.append(d.text)
            col += len(d.text)
        elif isinstance(d, Concat):
            for part in reversed(d.parts):
                stack.append((indent, mode, part))
        elif isinstance(d, Nest):
            stack.append((indent + d.indent, mode, d.doc))
        elif isinstance(d, Group):
            room = width - col
            fits = not has_hardline(d.doc, memo) and _flat_width(d.doc, room) <= room
            if mode == flat_mode or fits:
                stack.append((indent, flat_mode, d.doc))
            else:
                stack.append((indent, break_mode, d.doc))
        elif isinstance(d, Line):
            if mode == flat_mode and not d.hard:
                if not d.soft:
                    out.append(" ")
                    col += 1
            else:
                out.append("\n" + " " * indent)
                col = indent
        elif isinstance(d, IfBreak):
            stack.append((indent, mode, d.broken if mode == break_mode else d.flat))
    lines = "".join(out).split("\n")
    return "\n".join(line.rstrip() for line in lines)
