# SPDX-License-Identifier: Apache-2.0
"""Álgebra de documentos para maquetar texto (al estilo de Wadler y Prettier).

Un documento describe el texto con puntos de corte opcionales; `render` decide qué grupos caben
en una línea y cuáles se parten. Es lo que usa el formateador de Nomos.
"""

from __future__ import annotations

from collections.abc import Sequence
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


@dataclass(frozen=True)
class Hang(Doc):
    """`head body` en una línea si cabe; si no, `body` en la línea siguiente con `indent` más de
    sangría. Con `hug`, si `body` tampoco cabe entero en esa línea (o tiene saltos forzosos), se
    queda junto a `head` y se parte por dentro: así un `[`, `(` o `{` largo abre en la misma
    línea que el `=`."""

    head: Doc
    body: Doc
    indent: int
    hug: bool = False


@dataclass(frozen=True)
class Fill(Doc):
    """Relleno (el `fill` de Prettier): `parts` alterna contenidos y separadores, y cada
    separador salta de línea solo si el contenido siguiente ya no cabe en la actual."""

    parts: tuple[Doc, ...]


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


def fill(parts: list[Doc]) -> Doc:
    return Fill(tuple(parts))


def has_hardline(doc: Doc, memo: dict[int, bool] | None = None) -> bool:
    memo = {} if memo is None else memo
    key = id(doc)
    if key in memo:
        return memo[key]
    if isinstance(doc, Line):
        result = doc.hard
    elif isinstance(doc, Concat | Fill):
        result = any(has_hardline(p, memo) for p in doc.parts)
    elif isinstance(doc, Nest | Group):
        result = has_hardline(doc.doc, memo)
    elif isinstance(doc, Hang):
        result = has_hardline(doc.head, memo) or has_hardline(doc.body, memo)
    elif isinstance(doc, IfBreak):
        result = has_hardline(doc.broken, memo) or has_hardline(doc.flat, memo)
    else:
        result = False
    memo[key] = result
    return result


FLAT, BREAK = 0, 1


def _fits(
    doc: Doc,
    rest: list[tuple[int, int, Doc]],
    room: int,
    memo: dict[int, bool],
    must_be_flat: bool = False,
) -> bool:
    """¿Cabe `doc` en modo plano en `room` columnas, junto con lo que le sigue en `rest` hasta
    el primer salto de línea posible? Es el `fits` de Prettier: un grupo con un salto forzoso
    se mide partido (o no cabe, con `must_be_flat`)."""
    width = room
    stack: list[tuple[int, Doc]] = [(FLAT, doc)]
    rest_index = len(rest)
    while width >= 0:
        if not stack:
            if rest_index == 0:
                return True
            rest_index -= 1
            _, mode, d = rest[rest_index]
            stack.append((mode, d))
            continue
        mode, d = stack.pop()
        if isinstance(d, Text):
            width -= len(d.text)
        elif isinstance(d, Concat | Fill):
            stack.extend((mode, part) for part in reversed(d.parts))
        elif isinstance(d, Nest):
            stack.append((mode, d.doc))
        elif isinstance(d, Group):
            broken = has_hardline(d.doc, memo)
            if must_be_flat and broken:
                return False
            stack.append((BREAK if broken else mode, d.doc))
        elif isinstance(d, Line):
            if mode == BREAK or d.hard:
                return True
            if not d.soft:
                width -= 1
        elif isinstance(d, IfBreak):
            stack.append((mode, d.broken if mode == BREAK else d.flat))
        elif isinstance(d, Hang):
            stack.extend([(mode, d.body), (mode, Line()), (mode, d.head)])
    return False


def render(doc: Doc, width: int = 100) -> str:
    out: list[str] = []
    col = 0
    memo: dict[int, bool] = {}
    stack: list[tuple[int, int, Doc]] = [(0, BREAK, doc)]
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
            flat = mode == FLAT or (
                not has_hardline(d.doc, memo) and _fits(d.doc, stack, width - col, memo)
            )
            stack.append((indent, FLAT if flat else BREAK, d.doc))
        elif isinstance(d, Fill):
            _fill(d.parts, indent, mode, stack, width - col, memo)
        elif isinstance(d, Hang):
            _hang(d, indent, mode, stack, width, col, memo)
        elif isinstance(d, Line):
            if mode == FLAT and not d.hard:
                if not d.soft:
                    out.append(" ")
                    col += 1
            else:
                out.append("\n" + " " * indent)
                col = indent
        elif isinstance(d, IfBreak):
            stack.append((indent, mode, d.broken if mode == BREAK else d.flat))
    lines = "".join(out).split("\n")
    return "\n".join(line.rstrip() for line in lines)


def _fill(
    parts: Sequence[Doc],
    indent: int,
    mode: int,
    stack: list[tuple[int, int, Doc]],
    room: int,
    memo: dict[int, bool],
) -> None:
    """Coloca el primer contenido de un relleno y decide su separador: plano si el contenido
    siguiente también cabe en la línea; si no, salto. Cada medida incluye lo que sigue hasta el
    próximo salto posible: el texto del separador siguiente (el ` +` de `a + b`) o, al final,
    lo que venga tras el relleno."""
    if not parts:
        return
    content = parts[0]
    after = [(indent, BREAK, parts[1])] if len(parts) > 1 else stack
    content_mode = FLAT if _fits(content, after, room, memo, must_be_flat=True) else BREAK
    if len(parts) == 1:
        stack.append((indent, content_mode, content))
        return
    separator = parts[1]
    if len(parts) == 2:
        stack.extend([(indent, content_mode, separator), (indent, content_mode, content)])
        return
    pair = Concat((content, separator, parts[2]))
    after = [(indent, BREAK, parts[3])] if len(parts) > 3 else stack
    separator_mode = FLAT if _fits(pair, after, room, memo, must_be_flat=True) else BREAK
    stack.extend(
        [
            (indent, mode, Fill(tuple(parts[2:]))),
            (indent, separator_mode, separator),
            (indent, content_mode, content),
        ]
    )


def _hang(
    d: Hang,
    indent: int,
    mode: int,
    stack: list[tuple[int, int, Doc]],
    width: int,
    col: int,
    memo: dict[int, bool],
) -> None:
    one_line = Concat((d.head, Text(" "), d.body))
    if mode == FLAT or (
        not has_hardline(one_line, memo) and _fits(one_line, stack, width - col, memo)
    ):
        stack.append((indent, FLAT, one_line))
        return
    inner = indent + d.indent
    if d.hug and (has_hardline(d.body, memo) or not _fits(d.body, stack, width - inner, memo)):
        stack.append((indent, BREAK, one_line))
        return
    stack.extend([(inner, BREAK, d.body), (inner, BREAK, HARDLINE), (indent, BREAK, d.head)])
