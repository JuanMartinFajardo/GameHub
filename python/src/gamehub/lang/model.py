# SPDX-License-Identifier: Apache-2.0
"""Modelo de un juego antes de comprobarlo: todas sus declaraciones reunidas (las del propio
juego, las de primer nivel del archivo y las importadas) y el resultado de la compilación."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from gamehub.lang import ast
from gamehub.lang.source import NO_SPAN, Span


@dataclass
class External:
    """Declaración de módulo (enum, struct o fn de primer nivel, propia o importada). Solo
    llega a la IR si el juego la usa."""

    decl: ast.EnumDecl | ast.StructDecl | ast.FnDecl
    module: str  # "" = el propio archivo


@dataclass
class GameModel:
    name: str
    decl: ast.GameDecl
    meta: list[ast.MetaEntry] = field(default_factory=list)
    players: ast.PlayersDecl | None = None
    params: list[ast.ParamDecl] = field(default_factory=list)
    asserts: list[ast.AssertDecl] = field(default_factory=list)
    types: list[ast.EnumDecl | ast.StructDecl] = field(default_factory=list)
    state: list[ast.StateVar] = field(default_factory=list)
    functions: list[ast.FnDecl] = field(default_factory=list)
    start: ast.StartDecl | None = None
    nodes: list[ast.NodeDecl] = field(default_factory=list)
    tests: list[ast.TestDecl] = field(default_factory=list)
    invariants: list[ast.InvariantDecl] = field(default_factory=list)
    externals: list[External] = field(default_factory=list)
    flow_span: Span = NO_SPAN


# --- Resultado ----------------------------------------------------------------------------------


@dataclass
class ActionCall:
    """Acción escrita en un test: nombre, argumentos (expresiones de la IR) y asiento."""

    name: str
    args: list[Any]
    seat: int | None
    span: Span


@dataclass
class TestStep:
    kind: str
    span: Span
    value: Any = None
    actions: list[ActionCall] = field(default_factory=list)
    entries: dict[str, Any] = field(default_factory=dict)
    target: Any = None


@dataclass
class TestCase:
    name: str
    steps: list[TestStep]
    span: Span


@dataclass
class Invariant:
    label: str
    expr: Any
    span: Span


@dataclass
class CompiledGame:
    """Un juego compilado: su IR (lista para el motor) y lo que no forma parte de las reglas
    (tests e invariantes)."""

    name: str
    ir: dict[str, Any]
    tests: list[TestCase] = field(default_factory=list)
    invariants: list[Invariant] = field(default_factory=list)
    span: Span = NO_SPAN
