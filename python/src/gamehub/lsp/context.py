# SPDX-License-Identifier: Apache-2.0
"""Dónde está el cursor: en qué bloque (juego, flow, nodo, acción, sentencias…), qué hay antes
en la línea y qué palabra se está escribiendo. Lo usan el autocompletado y la ayuda de firmas.

Se calcula con los tokens del texto hasta el cursor, sin analizarlo: así funciona también
mientras se escribe, con el texto a medias y lleno de errores.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from gamehub.lang.diagnostics import Diagnostics
from gamehub.lang.lexer import Token, tokenize
from gamehub.lang.parser import NODE_KINDS
from gamehub.lang.source import Source

_STATEMENT_BLOCKS = ("on_enter", "on_exit", "resolve")

#: Tras estos tokens, un salto de línea no acaba la línea: la expresión sigue en la siguiente.
_CONTINUES = frozenset(
    {
        "and", "or", "not", "in", "+", "-", "*", "/", "%", "div", "==", "!=", "<", "<=", ">",
        ">=", "=", "+=", "-=", "*=", "when", "requires", ":", ",", "=>", "if", "else", "..",
        "..<",
    }
)  # fmt: skip


@dataclass
class Context:
    #: Bloques abiertos, del más externo al más interno: "game", "flow", "node:decision",
    #: "action", "stmts", "state", "params", "meta", "ui", "test", "struct", "enum", "expr".
    blocks: list[str] = field(default_factory=list)
    #: Nombre de cada bloque abierto, si lo tiene (el juego, el nodo, la acción…).
    names: list[str | None] = field(default_factory=list)
    #: La palabra que se está escribiendo y dónde empieza.
    prefix: str = ""
    prefix_start: int = 0
    #: Tokens de la línea antes de la palabra.
    before: list[Token] = field(default_factory=list)
    #: Paréntesis y corchetes abiertos en la línea: (token que abre, tokens previos a él).
    parens: list[tuple[Token, list[Token]]] = field(default_factory=list)
    #: El cursor está tras `@` (una anotación a medio escribir).
    annotation: bool = False
    #: Dónde empieza la declaración que contiene el cursor (la función, el nodo, la acción, el
    #: test…): los locales visibles se buscan a partir de ahí.
    scope_start: int = 0

    @property
    def block(self) -> str:
        return self.blocks[-1] if self.blocks else "file"

    @property
    def line_start(self) -> bool:
        return not self.before and not self.parens and not self.annotation

    def last(self, k: int = 1) -> list[str]:
        """Los k últimos tokens de la línea (su tipo: palabra clave, signo o "ident")."""
        return [t.kind for t in self.before[-k:]]

    def last_text(self) -> str | None:
        return self.before[-1].text if self.before else None

    def inside(self, kind: str) -> bool:
        return any(b == kind or b.startswith(kind + ":") for b in self.blocks)

    def node_kind(self) -> str | None:
        for b in reversed(self.blocks):
            if b.startswith("node:"):
                return b.split(":", 1)[1]
        return None

    def in_phase(self) -> bool:
        return any(b == "node:phase" for b in self.blocks[:-1]) or (
            self.blocks[-1:] == ["node:phase"]
        )


def _block_kind(header: list[Token]) -> tuple[str, str | None]:
    """Qué bloque abre un `{` según lo que lo precede en su línea."""
    if not header:
        return "expr", None
    first = header[0]
    kinds = [t.kind for t in header]
    words = [t.text for t in header]
    if first.kind == "override" and len(header) > 1:
        return _block_kind(header[1:])
    if first.kind == "annotation":
        rest = [t for t in header if t.kind not in ("annotation",)]
        return _block_kind(rest)
    match first.kind:
        case "game":
            return "game", header[1].text if len(header) > 1 else None
        case "flow" | "state" | "params" | "meta":
            return first.kind, None
        case "struct" | "enum":
            return first.kind, header[1].text if len(header) > 1 else None
        case "test":
            return "test", None
        case "action":
            return "action", header[1].text if len(header) > 1 else None
        case "->" | "start" | "if" | "else" | "for":
            return "stmts", None
        case "fn":
            return "expr", header[1].text if len(header) > 1 else None
        case "extend":
            return "node:decision", header[-1].text if header[-1].kind == "ident" else None
    if first.kind in NODE_KINDS:
        return f"node:{first.kind}", header[1].text if len(header) > 1 else None
    if first.kind == "ident" and first.text == "ui" and len(header) == 1:
        return "ui", None
    if first.kind == "ident" and first.text in _STATEMENT_BLOCKS and len(header) == 1:
        return "stmts", None
    if "else" in kinds or (words and words[-1] in ("else",)):
        return "stmts", None
    return "expr", None


def context_at(text: str, offset: int) -> Context:
    offset = max(0, min(offset, len(text)))
    start = offset
    while start > 0 and (text[start - 1].isalnum() or text[start - 1] == "_"):
        start -= 1
    ctx = Context(prefix=text[start:offset], prefix_start=start)
    if start > 0 and text[start - 1] == "@":
        ctx.annotation = True
        start -= 1
    tokens = tokenize(Source("<contexto>", text[:start]), Diagnostics())
    stack: list[tuple[str, str | None, int]] = []
    line: list[Token] = []
    parens: list[tuple[Token, list[Token]]] = []
    for tok in tokens:
        if tok.kind == "eof":
            break
        if tok.kind in ("newline", ";"):
            if tok.kind == "newline" and (
                tok.span.start >= start or (line and line[-1].kind in _CONTINUES)
            ):
                continue  # el salto que el lexer añade al final, o una línea que sigue
            line = []
            parens = []
            continue
        if tok.kind == "{":
            kind, name = _block_kind(line)
            opened = line[0].span.start if line else tok.span.start
            stack.append((kind, name, _line_start(text, opened)))
            line = []
            parens = []
            continue
        if tok.kind == "}":
            if stack:
                stack.pop()
            line = []
            parens = []
            continue
        if tok.kind in ("(", "["):
            parens.append((tok, list(line)))
        elif tok.kind in (")", "]") and parens:
            parens.pop()
        line.append(tok)
    ctx.blocks = [k for k, _, _ in stack]
    ctx.names = [n for _, n, _ in stack]
    ctx.before = line
    ctx.parens = parens
    ctx.scope_start = _line_start(text, start)
    if line and line[0].kind in ("fn", "invariant"):
        ctx.scope_start = _line_start(text, line[0].span.start)
    else:
        for kind, _, where in reversed(stack):
            if kind.startswith("node:") or kind in ("action", "test"):
                ctx.scope_start = where
                break
    return ctx


def _line_start(text: str, offset: int) -> int:
    return text.rfind("\n", 0, offset) + 1
