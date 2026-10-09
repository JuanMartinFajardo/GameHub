# SPDX-License-Identifier: Apache-2.0
"""Recorridos genéricos de la GameIR guiados por el catálogo de operadores (`ops.json`): las
subexpresiones de cada operador y los bloques de cada sentencia salen de los tipos de sus
argumentos, así que los análisis no tienen que conocer los 87 operadores uno a uno."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from gamehub.ir.catalog import OpSpec, load_catalog


def _args(spec: OpSpec, args: list[Any]) -> Iterator[tuple[str, Any]]:
    yield from zip(spec.kinds_for(len(args)), args, strict=False)


def _arg_exprs(spec: OpSpec, args: list[Any]) -> Iterator[Any]:
    catalog = load_catalog()
    for kind, value in _args(spec, args):
        match kind:
            case "e" | "l":
                yield value
            case "cases":
                for cond, result in value:
                    yield cond
                    yield result
            case "fields":
                yield from value.values()
            case "sel":
                yield from _arg_exprs(catalog.selectors[value[0]], value[1:])
            case "vis":
                if isinstance(value, dict) and "when" in value:
                    yield value["when"]


def children(e: Any) -> Iterator[Any]:
    """Subexpresiones directas de una expresión."""
    yield from _arg_exprs(load_catalog().expressions[e[0]], e[1:])


def walk(e: Any) -> Iterator[Any]:
    """La expresión y todas sus subexpresiones (en preorden)."""
    stack = [e]
    while stack:
        node = stack.pop()
        yield node
        stack.extend(reversed(list(children(node))))


def stmt_exprs(stmt: list[Any]) -> Iterator[Any]:
    """Expresiones de una sentencia, sin entrar en sus bloques anidados."""
    yield from _arg_exprs(load_catalog().statements[stmt[0]], stmt[1:])


def stmt_blocks(stmt: list[Any]) -> Iterator[list[Any]]:
    """Bloques anidados de una sentencia (las ramas de `if`, el cuerpo de `for`)."""
    for kind, value in _args(load_catalog().statements[stmt[0]], stmt[1:]):
        if kind == "block" and value is not None:
            yield value


def walk_block(block: list[Any]) -> Iterator[list[Any]]:
    """Todas las sentencias de un bloque, también las anidadas."""
    for stmt in block:
        yield stmt
        for inner in stmt_blocks(stmt):
            yield from walk_block(inner)


def block_exprs(block: list[Any]) -> Iterator[Any]:
    """Todas las expresiones (con sus subexpresiones) de un bloque."""
    for stmt in walk_block(block):
        for e in stmt_exprs(stmt):
            yield from walk(e)


def is_random(stmt: list[Any]) -> bool:
    return stmt[0] in load_catalog().chance_statements


# --- el flow ------------------------------------------------------------------------------------


def all_nodes(ir: dict[str, Any]) -> Iterator[tuple[dict[str, Any], str | None]]:
    """Cada nodo del flow (también los de las fases) con la fase que lo contiene."""

    def visit(nodes: list[dict[str, Any]], parent: str | None) -> Iterator[Any]:
        for node in nodes:
            yield node, parent
            if node["kind"] == "phase":
                yield from visit(node.get("nodes", []), node["id"])

    yield from visit(ir["flow"]["nodes"], None)


def node_blocks(node: dict[str, Any]) -> Iterator[list[Any]]:
    """Bloques de efectos de un nodo: los suyos, los de sus acciones y transiciones."""
    for key in ("effects", "resolve", "on_enter", "on_exit"):
        if node.get(key):
            yield node[key]
    for action in node.get("actions", []):
        if action.get("effects"):
            yield action["effects"]
        for t in action.get("transitions", []):
            if t.get("effects"):
                yield t["effects"]
    for t in node.get("transitions", []):
        if t.get("effects"):
            yield t["effects"]


def node_exprs(node: dict[str, Any]) -> Iterator[Any]:
    """Todas las expresiones de un nodo (sin los nodos hijos de una fase)."""
    for key in ("actor", "actors", "eligible", "order", "payoff", "rank"):
        if key in node:
            yield from walk(node[key])
    for block in node_blocks(node):
        yield from block_exprs(block)
    for action in node.get("actions", []):
        for p in action.get("params", []):
            yield from walk(p["domain"])
        if "requires" in action:
            yield from walk(action["requires"])
        for t in action.get("transitions", []):
            if "when" in t:
                yield from walk(t["when"])
    for t in node.get("transitions", []):
        if "when" in t:
            yield from walk(t["when"])


def game_exprs(ir: dict[str, Any]) -> Iterator[Any]:
    """Todas las expresiones de la IR: parámetros, estado, funciones y flow."""
    for p in ir.get("params", []):
        yield from walk(p["default"])
    for c in ir.get("constraints", []):
        yield from walk(c["expr"])
    for v in ir.get("state", []):
        yield from walk(v["init"])
        for key in ("visibility", "size_visibility"):
            vis = v.get(key)
            if isinstance(vis, dict) and "when" in vis:
                yield from walk(vis["when"])
    for f in ir.get("functions", []):
        yield from walk(f["body"])
    yield from block_exprs(ir["flow"].get("setup", []))
    for node, _ in all_nodes(ir):
        yield from node_exprs(node)
