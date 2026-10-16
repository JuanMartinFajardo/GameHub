# SPDX-License-Identifier: Apache-2.0
"""Análisis de un documento abierto en el editor: árbol, compilación, índice de símbolos y
conversión de posiciones entre el texto (Python) y el cliente (líneas y columnas del LSP)."""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from lsprotocol import types
from pygls.workspace.position_codec import PositionCodec, ServerTextPosition

from gamehub.lang import ast
from gamehub.lang.compiler import CompileResult, compile_source
from gamehub.lang.diagnostics import Diagnostics
from gamehub.lang.parser import parse
from gamehub.lang.source import Source, Span
from gamehub.lang.symbols import SymbolIndex


def uri_to_path(uri: str) -> Path | None:
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return None
    return Path(unquote(parsed.path))


def path_to_uri(path: Path) -> str:
    return path.resolve().as_uri()


class Positions:
    """Convierte desplazamientos del texto en posiciones del LSP (línea y columna en las unidades
    que use el cliente, UTF-16 por defecto) y al revés."""

    def __init__(self, text: str, codec: PositionCodec | None = None) -> None:
        self.text = text
        self.codec = codec or PositionCodec()
        self.lines = text.splitlines(keepends=True) or [""]
        self.starts = [0]
        for line in self.lines:
            self.starts.append(self.starts[-1] + len(line))

    def position(self, offset: int) -> types.Position:
        offset = max(0, min(offset, len(self.text)))
        line = max(0, bisect_right(self.starts, offset) - 1)
        if line >= len(self.lines):
            line = len(self.lines) - 1
        column = offset - self.starts[line]
        return self.codec.position_to_client_units(self.lines, ServerTextPosition(line, column))

    def range(self, start: int, end: int) -> types.Range:
        return types.Range(self.position(start), self.position(end))

    def span(self, span: Span) -> types.Range:
        return self.range(span.start, span.end)

    def offset(self, position: types.Position) -> int:
        if position.line >= len(self.lines):
            return len(self.text)
        server = self.codec.position_from_client_units(self.lines, position)
        return min(self.starts[server.line] + server.character, len(self.text))


@dataclass
class Analysis:
    """Lo que se sabe de una versión de un documento."""

    uri: str
    version: int | None
    source: Source
    tree: ast.File
    #: El parser no encontró errores (si los hay, no se compila: `result` es None).
    syntax_ok: bool
    parse_diagnostics: Diagnostics
    result: CompileResult | None
    index: SymbolIndex
    positions: Positions
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def diagnostics(self) -> Diagnostics:
        return self.result.diagnostics if self.result is not None else self.parse_diagnostics

    @property
    def text(self) -> str:
        return self.source.text

    @property
    def name(self) -> str:
        return self.source.name


def analyze(
    uri: str, text: str, version: int | None = None, codec: PositionCodec | None = None
) -> Analysis:
    path = uri_to_path(uri)
    source = Source(str(path) if path is not None else uri, text, path)
    diagnostics = Diagnostics()
    tree = parse(source, diagnostics)
    index = SymbolIndex()
    result: CompileResult | None = None
    if not diagnostics.has_errors:
        result = compile_source(source, index=index, schema=False)
        tree = result.file
    return Analysis(
        uri=uri,
        version=version,
        source=source,
        tree=tree,
        syntax_ok=not diagnostics.has_errors,
        parse_diagnostics=diagnostics,
        result=result,
        index=index,
        positions=Positions(text, codec),
    )
