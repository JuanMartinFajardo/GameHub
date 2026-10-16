# SPDX-License-Identifier: Apache-2.0
"""Análisis de trozos sueltos de Nomos: una expresión, un tipo, unas sentencias, los miembros de
un nodo… Los usa el Studio cuando se escribe en un formulario (la condición de una transición,
los efectos de una acción) para convertir el texto en el trozo de árbol que va en su sitio.

Los bloques se analizan envolviéndolos en `{ … }` con el mismo parser que los archivos, así que
admiten lo mismo (comentarios incluidos, que se conservan). Las posiciones de los errores se dan
relativas al trozo.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from gamehub.lang import ast
from gamehub.lang.diagnostics import Diagnostics
from gamehub.lang.lexer import Comment, tokenize
from gamehub.lang.parser import NODE_KINDS, ParseError, Parser
from gamehub.lang.source import Source

#: Prefijo con el que se envuelven los bloques (para corregir las posiciones de los errores).
_OPEN = "{\n"


@dataclass(frozen=True)
class FragmentError:
    message: str
    #: Posición en el trozo (desde 0) y longitud del texto señalado.
    offset: int
    length: int
    help: str | None = None

    def to_json(self) -> dict[str, object]:
        out: dict[str, object] = {
            "message": self.message,
            "offset": self.offset,
            "length": self.length,
        }
        if self.help:
            out["help"] = self.help
        return out


class FragmentSyntaxError(Exception):
    """El trozo no se puede analizar; `errors` dice por qué y dónde."""

    def __init__(self, what: str, errors: list[FragmentError]) -> None:
        self.what = what
        self.errors = errors
        first = errors[0].message if errors else "error de sintaxis"
        super().__init__(f"{what}: {first}")


def _errors(diagnostics: Diagnostics, shift: int, size: int) -> list[FragmentError]:
    out: list[FragmentError] = []
    for d in diagnostics.errors:
        span = d.span
        if span is None:
            out.append(FragmentError(d.message, 0, 0, d.help))
            continue
        start = min(max(span.start - shift, 0), size)
        end = min(max(span.end - shift, start), size)
        out.append(FragmentError(d.message, start, end - start, d.help))
    return out


def _parse[T](text: str, what: str, run: Callable[[Parser], T], *, wrap: bool) -> T:
    diagnostics = Diagnostics()
    body = f"{_OPEN}{text}\n}}" if wrap else text
    tokens = tokenize(Source(f"<{what}>", body), diagnostics)
    parser = Parser(tokens, diagnostics)
    result: T | None = None
    try:
        result = run(parser)
        parser.skip_newlines()
        if not parser.at("eof"):
            parser.fail(f"sobra texto: {parser.peek().text!r}")
    except ParseError:
        pass
    if diagnostics.has_errors or result is None:
        raise FragmentSyntaxError(what, _errors(diagnostics, len(_OPEN) if wrap else 0, len(text)))
    return result


def expression(text: str) -> ast.Expr:
    """Una expresión (`wins(mark(turn))`). Puede ocupar varias líneas."""
    if not text.strip():
        raise FragmentSyntaxError("la expresión", [FragmentError("falta la expresión", 0, 0)])

    def run(p: Parser) -> ast.Expr:
        p.skip_newlines()
        return p.value()

    return _parse(text, "la expresión", run, wrap=False)


def type_expr(text: str) -> ast.TypeExpr:
    """Un tipo (`Grid[3, 3] of Mark?`)."""
    if not text.strip():
        raise FragmentSyntaxError("el tipo", [FragmentError("falta el tipo", 0, 0)])

    def run(p: Parser) -> ast.TypeExpr:
        p.skip_newlines()
        return p.type_expr()

    return _parse(text, "el tipo", run, wrap=False)


def visibility(text: str) -> ast.Visibility:
    """Lo que va dentro de `@visible(…)`: `all`, `none`, `owner` o una condición."""
    word = text.strip()
    if word in ("all", "none", "owner"):
        return ast.Visibility(word)
    return ast.Visibility("when", expression(text))


def statements(text: str) -> tuple[list[ast.Stmt], list[Comment]]:
    """Sentencias, una por línea (los efectos de una acción, un `on_enter`…), y los comentarios
    que quedan tras la última."""
    if not text.strip():
        return [], []
    items, end = _block(text, "las sentencias", lambda p: p.stmt())
    return [s for s in items if isinstance(s, ast.Stmt)], end


def node_members(text: str, kind: str) -> tuple[list[ast.Item], list[Comment]]:
    """Miembros de un nodo del tipo dado: `actor: …`, acciones, transiciones, sentencias…"""
    if kind not in NODE_KINDS:
        raise ValueError(f"tipo de nodo desconocido: {kind}")
    return _block(text, "el nodo", lambda p: p.node_member(kind))


def flow_items(text: str) -> tuple[list[ast.Item], list[Comment]]:
    """Nodos y `start` (lo que va dentro de `flow { … }` o de una fase)."""
    return _block(text, "el flow", lambda p: p.flow_item())


def game_items(text: str) -> tuple[list[ast.Item], list[Comment]]:
    """Declaraciones de un juego (`enum`, `state { … }`, `fn`, `flow { … }`…)."""
    return _block(text, "el juego", lambda p: p.game_item())


def action_body(text: str) -> tuple[list[ast.Item], list[Comment]]:
    """El cuerpo de una acción: sentencias y, al final, sus transiciones."""
    return _block(text, "la acción", lambda p: p.action_body_item())


def test_steps(text: str) -> tuple[list[ast.TestStep], list[Comment]]:
    """Los pasos de un test (`play …`, `expect …`…), uno por línea, y los comentarios que quedan
    tras el último."""
    if not text.strip():
        return [], []
    items, end = _block(text, "el test", lambda p: p.test_step())
    return [s for s in items if isinstance(s, ast.TestStep)], end


def ui_entries(text: str) -> tuple[list[ast.UiEntry], list[Comment]]:
    """Entradas de `ui { … }` (`board: grid, label("Tablero")`)."""
    items, end = _block(text, "las pistas", lambda p: p.ui_entry())
    return [e for e in items if isinstance(e, ast.UiEntry)], end


def _block(
    text: str, what: str, parse_one: Callable[[Parser], ast.Item | None]
) -> tuple[list[ast.Item], list[Comment]]:
    def run(p: Parser) -> tuple[list[ast.Item], list[Comment]]:
        items, end = p.block(lambda: parse_one(p))
        return items, p.claim(end)

    return _parse(text, what, run, wrap=True)
