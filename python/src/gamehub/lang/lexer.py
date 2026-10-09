# SPDX-License-Identifier: Apache-2.0
"""Análisis léxico de Nomos.

- Los saltos de línea separan elementos, salvo dentro de `( … )` y `[ … ]` (como en Python).
  Dentro de `{ … }` vuelven a contar, aunque las llaves estén dentro de paréntesis.
- Los comentarios (`// …`, `/* … */`) y los comentarios de documentación (`/// …`) no son
  tokens: se adjuntan como *trivia* al token siguiente, para que el formateador los conserve y
  el parser asocie la documentación a la declaración que sigue.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

from gamehub.lang.diagnostics import Diagnostics
from gamehub.lang.source import Source, Span

KEYWORDS = frozenset(
    {
        "action",
        "and",
        "assert",
        "auto",
        "case",
        "chance",
        "deal",
        "decision",
        "div",
        "else",
        "emit",
        "enum",
        "exit",
        "extend",
        "extends",
        "fail",
        "false",
        "flip",
        "flow",
        "fn",
        "for",
        "game",
        "if",
        "import",
        "in",
        "invariant",
        "let",
        "match",
        "meta",
        "move",
        "none",
        "not",
        "or",
        "override",
        "params",
        "phase",
        "players",
        "remove",
        "requires",
        "reveal",
        "reward",
        "shuffle",
        "simultaneous",
        "start",
        "state",
        "struct",
        "terminal",
        "test",
        "true",
        "when",
        "window",
    }
)

#: Signos de puntuación, de más largo a más corto (se reconoce el más largo posible).
PUNCTUATION = (
    "..<",
    "->",
    "=>",
    "==",
    "!=",
    "<=",
    ">=",
    "+=",
    "-=",
    "*=",
    "..",
    "{",
    "}",
    "(",
    ")",
    "[",
    "]",
    ",",
    ":",
    ";",
    ".",
    "=",
    "<",
    ">",
    "+",
    "-",
    "*",
    "/",
    "%",
    "?",
)

_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "0": "\0"}
_BLANK_AFTER = re.compile(r"[ \t\r\f]*\n[ \t\r\f]*\n")


@dataclass(frozen=True, slots=True)
class Comment:
    """Comentario. `kind`: "line" (`//`), "block" (`/* */`) o "doc" (`///`). `own_line`: empieza
    en una línea sin código delante (si no, es un comentario al final de una línea de código).
    `blank_before`/`blank_after`: hay una línea en blanco justo antes/después (el formateador
    las conserva)."""

    kind: str
    text: str
    span: Span
    own_line: bool
    blank_before: bool = False
    blank_after: bool = False

    @property
    def body(self) -> str:
        """Texto sin los delimitadores (`///`, `//`, `/* */`)."""
        if self.kind == "doc":
            rest = self.text[3:]
            return rest[1:] if rest.startswith(" ") else rest
        if self.kind == "line":
            return self.text[2:]
        return self.text[2:-2]


@dataclass(slots=True)
class Token:
    """`kind`: "ident", "int", "decimal", "string", "annotation", "newline", "eof", o el propio
    texto de la palabra clave o del signo de puntuación."""

    kind: str
    text: str
    span: Span
    value: Any = None
    leading: list[Comment] = field(default_factory=list)

    def __repr__(self) -> str:
        return f"Token({self.kind!r}, {self.text!r})"


def tokenize(source: Source, diagnostics: Diagnostics) -> list[Token]:
    return _Lexer(source, diagnostics).run()


class _Lexer:
    def __init__(self, source: Source, diagnostics: Diagnostics) -> None:
        self.source = source
        self.text = source.text
        self.diagnostics = diagnostics
        self.pos = 0
        self.tokens: list[Token] = []
        self.pending: list[Comment] = []
        self.brackets: list[str] = []
        self.last_line = 0  # línea del último token emitido (no salto de línea)

    def span(self, start: int, end: int | None = None) -> Span:
        return Span(self.source, start, self.pos if end is None else end)

    def emit(self, kind: str, start: int, value: Any = None) -> None:
        """Añade un token. Los comentarios pendientes pasan al siguiente token que no sea un
        salto de línea."""
        if kind == "newline":
            self.tokens.append(Token(kind, "\n", self.span(start), value))
            return
        token = Token(kind, self.text[start : self.pos], self.span(start), value, self.pending)
        self.pending = []
        self.tokens.append(token)
        self.last_line = self.source.location(max(start, self.pos - 1))[0]

    def newline_counts(self) -> bool:
        return not self.brackets or self.brackets[-1] == "{"

    def run(self) -> list[Token]:
        text = self.text
        n = len(text)
        while self.pos < n:
            ch = text[self.pos]
            start = self.pos
            if ch == "\n":
                self.pos += 1
                if self.newline_counts() and self.tokens and self.tokens[-1].kind != "newline":
                    self.emit("newline", start)
                continue
            if ch in " \t\r\f﻿":
                self.pos += 1
                continue
            if text.startswith("//", self.pos):
                self.line_comment()
                continue
            if text.startswith("/*", self.pos):
                self.block_comment()
                continue
            if ch.isdigit():
                self.number()
                continue
            if ch.isalpha() or ch == "_":
                self.word()
                continue
            if ch == '"':
                self.string()
                continue
            if ch == "@":
                self.pos += 1
                if self.pos < n and (text[self.pos].isalpha() or text[self.pos] == "_"):
                    while self.pos < n and (text[self.pos].isalnum() or text[self.pos] == "_"):
                        self.pos += 1
                    self.emit("annotation", start, text[start + 1 : self.pos])
                else:
                    self.diagnostics.error(
                        "E101", "se esperaba el nombre de una anotación tras '@'", self.span(start)
                    )
                continue
            for punct in PUNCTUATION:
                if text.startswith(punct, self.pos):
                    self.pos += len(punct)
                    self.bracket(punct)
                    self.emit(punct, start)
                    break
            else:
                self.pos += 1
                self.diagnostics.error(
                    "E101",
                    f"carácter inesperado: {ch!r}",
                    self.span(start),
                    help="'!' solo existe en '!=' (la negación es 'not')" if ch == "!" else None,
                )
        if self.tokens and self.tokens[-1].kind != "newline":
            self.emit("newline", self.pos)
        self.emit("eof", self.pos)
        return self.tokens

    def bracket(self, punct: str) -> None:
        if punct in "([{":
            self.brackets.append(punct)
        elif punct in ")]}" and self.brackets:
            self.brackets.pop()

    def own_line(self, start: int) -> bool:
        if not self.tokens:
            return True
        line = self.source.location(start)[0]
        last = self.tokens[-1]
        if last.kind == "newline":
            return True
        return line > self.last_line

    def line_comment(self) -> None:
        start = self.pos
        end = self.text.find("\n", start)
        self.pos = len(self.text) if end < 0 else end
        raw = self.text[start : self.pos].rstrip()
        kind = "doc" if raw.startswith("///") and not raw.startswith("////") else "line"
        self.pending.append(self.comment(kind, raw, start))

    def block_comment(self) -> None:
        start = self.pos
        end = self.text.find("*/", start + 2)
        if end < 0:
            self.pos = len(self.text)
            self.diagnostics.error("E102", "comentario /* sin cerrar", self.span(start, start + 2))
            return
        self.pos = end + 2
        self.pending.append(self.comment("block", self.text[start : self.pos], start))

    def comment(self, kind: str, raw: str, start: int) -> Comment:
        return Comment(
            kind,
            raw,
            self.span(start),
            self.own_line(start),
            blank_before=_blank_before(self.text, start),
            blank_after=_BLANK_AFTER.match(self.text, self.pos) is not None,
        )

    def number(self) -> None:
        start = self.pos
        text = self.text
        n = len(text)
        while self.pos < n and (text[self.pos].isdigit() or text[self.pos] == "_"):
            self.pos += 1
        if self.pos + 1 < n and text[self.pos] == "." and text[self.pos + 1].isdigit():
            self.pos += 1
            while self.pos < n and (text[self.pos].isdigit() or text[self.pos] == "_"):
                self.pos += 1
            literal = text[start : self.pos].replace("_", "")
            self.emit("decimal", start, Fraction(literal))
        else:
            literal = text[start : self.pos].replace("_", "")
            self.emit("int", start, int(literal))
        if self.pos < n and (text[self.pos].isalpha() or text[self.pos] == "_"):
            bad = self.pos
            while self.pos < n and (text[self.pos].isalnum() or text[self.pos] == "_"):
                self.pos += 1
            self.diagnostics.error(
                "E101", "un número no puede ir seguido de letras", self.span(bad)
            )

    def word(self) -> None:
        start = self.pos
        text = self.text
        n = len(text)
        while self.pos < n and (text[self.pos].isalnum() or text[self.pos] == "_"):
            self.pos += 1
        word = text[start : self.pos]
        self.emit(word if word in KEYWORDS else "ident", start, word)

    def string(self) -> None:
        start = self.pos
        text = self.text
        n = len(text)
        self.pos += 1
        chars: list[str] = []
        while True:
            if self.pos >= n or text[self.pos] == "\n":
                self.diagnostics.error("E103", "texto sin cerrar", self.span(start))
                break
            ch = text[self.pos]
            if ch == '"':
                self.pos += 1
                break
            if ch == "\\":
                esc_start = self.pos
                self.pos += 1
                if self.pos >= n:
                    continue
                code = text[self.pos]
                if code in _ESCAPES:
                    chars.append(_ESCAPES[code])
                    self.pos += 1
                elif code == "u" and text.startswith("{", self.pos + 1):
                    close = text.find("}", self.pos)
                    digits = text[self.pos + 2 : close] if close > 0 else ""
                    try:
                        chars.append(chr(int(digits, 16)))
                    except ValueError:
                        self.diagnostics.error(
                            "E103", "escape \\u{…} inválido", self.span(esc_start, close + 1)
                        )
                    self.pos = close + 1 if close > 0 else self.pos + 1
                else:
                    self.pos += 1
                    self.diagnostics.error(
                        "E103",
                        f"escape desconocido: \\{code}",
                        self.span(esc_start),
                        help='se admiten \\n, \\t, \\r, \\", \\\\, \\0 y \\u{…}',
                    )
                continue
            chars.append(ch)
            self.pos += 1
        self.emit("string", start, "".join(chars))


def _blank_before(text: str, start: int) -> bool:
    """¿Hay una línea en blanco justo antes de `start`?"""
    newlines = 0
    for i in range(start - 1, -1, -1):
        ch = text[i]
        if ch == "\n":
            newlines += 1
            if newlines == 2:
                return True
        elif ch not in " \t\r\f":
            return False
    return False
