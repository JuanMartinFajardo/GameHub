# SPDX-License-Identifier: Apache-2.0
"""Índice de símbolos de un archivo Nomos: qué declara cada nombre, dónde se usa y de qué tipo es
cada expresión.

Lo rellena el comprobador mientras resuelve nombres (si se le pasa un `SymbolIndex`), así que sabe
exactamente a qué se refiere cada aparición: una variable de estado, el parámetro de una acción,
un valor de enumerado, el campo de un struct, un nodo… Lo usan el servidor de lenguaje (ir a la
definición, referencias, renombrar, hover) y el Studio.

Claves de los símbolos:

- `state:x`, `param:x`, `fn:f`, `type:T`, `node:N`, `game:G`: declaraciones del juego.
- `value:T.V`, `field:S.f`: un valor de enumerado y un campo de struct.
- `action:a`, `aparam:a.p`: una acción y uno de sus parámetros. Van por nombre, como los nombran
  los tests y las pistas, aunque la acción esté en varios nodos.
- `local:archivo:posición`: un `let`, una variable de comprensión o de bucle, un parámetro de
  función.
- `builtin:f`, `context:x`: una función predefinida y un nombre de contexto (`actor`, `seats`…).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from gamehub.lang.source import Span

#: Clases de símbolo que se pueden renombrar (los predefinidos y los de contexto, no).
RENAMABLE = frozenset(
    {"state", "param", "fn", "type", "value", "field", "node", "action", "aparam", "local", "game"}
)


@dataclass
class Symbol:
    key: str
    kind: str
    name: str
    decls: list[Span] = field(default_factory=list)
    #: Tipo o firma en Nomos (`board: Grid[3, 3] of Mark?`, `fn wins(m: Mark) -> Bool`).
    detail: str = ""
    doc: str | None = None


@dataclass(frozen=True)
class Occurrence:
    """Una aparición de un símbolo en el texto: su declaración (`decl`) o un uso."""

    span: Span
    key: str
    decl: bool = False


def local_key(span: Span) -> str:
    source = span.source.name if span.source is not None else ""
    return f"local:{source}:{span.start}"


def _where(span: Span) -> tuple[str, int, int]:
    return (span.source.name if span.source is not None else "", span.start, span.end)


class SymbolIndex:
    def __init__(self) -> None:
        self.symbols: dict[str, Symbol] = {}
        self.occurrences: list[Occurrence] = []
        #: (posición, tipo) de cada expresión comprobada, para el hover.
        self.typed: list[tuple[Span, str]] = []
        self._seen: set[tuple[tuple[str, int, int], str]] = set()
        self._typed_seen: set[tuple[str, int, int]] = set()

    # --- registro (lo llama el comprobador) -----------------------------------------------------

    def define(
        self,
        key: str,
        kind: str,
        name: str,
        span: Span | None,
        detail: str = "",
        doc: str | None = None,
    ) -> Symbol:
        symbol = self.symbols.get(key)
        if symbol is None:
            symbol = self.symbols[key] = Symbol(key, kind, name, [], detail, doc)
        else:
            symbol.detail = symbol.detail or detail
            symbol.doc = symbol.doc or doc
        if span is not None and span.source is not None:
            where = (_where(span), key)
            if where not in self._seen:
                self._seen.add(where)
                symbol.decls.append(span)
                self.occurrences.append(Occurrence(span, key, decl=True))
        return symbol

    def ref(self, span: Span | None, key: str) -> None:
        if span is None or span.source is None:
            return
        where = (_where(span), key)
        if where in self._seen:
            return
        self._seen.add(where)
        self.occurrences.append(Occurrence(span, key))

    def expr_type(self, span: Span, ty: object) -> None:
        if span.source is None:
            return
        where = _where(span)
        if where in self._typed_seen:
            return
        self._typed_seen.add(where)
        self.typed.append((span, str(ty)))

    def merge(self, other: SymbolIndex) -> None:
        """Junta el índice de otro juego del mismo archivo."""
        for key, symbol in other.symbols.items():
            mine = self.define(key, symbol.kind, symbol.name, None, symbol.detail, symbol.doc)
            for span in symbol.decls:
                if span not in mine.decls:
                    mine.decls.append(span)
        for occ in other.occurrences:
            where = (_where(occ.span), occ.key)
            if where not in self._seen:
                self._seen.add(where)
                self.occurrences.append(occ)
        for span, ty in other.typed:
            self.expr_type(span, ty)

    # --- consultas ------------------------------------------------------------------------------

    def at(self, source: str, offset: int) -> Occurrence | None:
        """La aparición más ajustada que contiene `offset` (con el final incluido, para que el
        cursor justo detrás de un nombre también cuente)."""
        best: Occurrence | None = None
        for occ in self.occurrences:
            span = occ.span
            if span.source is None or span.source.name != source:
                continue
            if span.start <= offset <= span.end and (
                best is None or span.end - span.start < best.span.end - best.span.start
            ):
                best = occ
        return best

    def of(self, key: str, source: str | None = None) -> list[Occurrence]:
        """Todas las apariciones de un símbolo (declaraciones primero), opcionalmente solo las de
        un archivo, en orden de posición."""
        found = [
            o
            for o in self.occurrences
            if o.key == key
            and (source is None or (o.span.source is not None and o.span.source.name == source))
        ]
        return sorted(found, key=lambda o: (not o.decl, _where(o.span)))

    def type_at(self, source: str, offset: int) -> tuple[Span, str] | None:
        """El tipo de la expresión más ajustada que contiene `offset`."""
        best: tuple[Span, str] | None = None
        for span, ty in self.typed:
            if span.source is None or span.source.name != source:
                continue
            if span.start <= offset < span.end and (
                best is None or span.end - span.start < best[0].end - best[0].start
            ):
                best = (span, ty)
        return best
