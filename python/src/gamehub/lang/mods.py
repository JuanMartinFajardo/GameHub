# SPDX-License-Identifier: Apache-2.0
"""Mods: `game Variante extends Base { … }`.

La variante empieza siendo una copia de la base (su modelo: meta sin `id` ni `version`,
jugadores, parámetros, tipos, estado, funciones y flow; los tests y los invariantes no se
heredan) y después se aplican sus elementos en orden:

- declaraciones nuevas (parámetros, variables, tipos, funciones, nodos): no pueden llamarse
  como una de la base (para eso está `override`);
- `override fn|enum|struct|<nodo>|params|state …`: reemplaza por nombre (también nodos dentro de
  fases); si `override params` trae algún `assert`, sustituyen a todas las restricciones de la
  base (un `params` normal las añade);
- `remove node|fn|state|param|enum|struct X` y `remove action Nodo.accion`;
- `extend node X { … }`: añade acciones (al final) y transiciones (delante de las de la base,
  para que tengan prioridad sobre su transición final sin condición);
- `meta` mezcla sus campos con los heredados; `players` y el `start` del flow reemplazan.

La base no cambia: los nodos modificados se copian.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable

from gamehub.lang import ast, ui
from gamehub.lang.diagnostics import Diagnostics
from gamehub.lang.model import External, GameModel
from gamehub.lang.source import Span


def derive(
    base: GameModel,
    decl: ast.GameDecl,
    externals: list[External],
    diagnostics: Diagnostics,
) -> GameModel:
    m = GameModel(name=decl.name, decl=decl)
    m.meta = [e for e in base.meta if e.key not in ("id", "version")]
    m.players = base.players
    m.params = list(base.params)
    m.asserts = list(base.asserts)
    m.types = list(base.types)
    m.state = list(base.state)
    m.functions = list(base.functions)
    m.start = base.start
    m.nodes = list(base.nodes)
    m.ui = list(base.ui)
    m.flow_span = base.flow_span
    seen = {id(x.decl) for x in base.externals}
    m.externals = [*base.externals, *(x for x in externals if id(x.decl) not in seen)]
    _Mod(m, diagnostics).apply(decl.items)
    return m


class _Mod:
    def __init__(self, model: GameModel, diagnostics: Diagnostics) -> None:
        self.m = model
        self.diagnostics = diagnostics

    def error(self, message: str, span: Span, help: str | None = None) -> None:
        self.diagnostics.error("E505", message, span, help=help)

    def apply(self, items: list[ast.Item]) -> None:
        for item in items:
            match item:
                case ast.MetaBlock(entries=entries):
                    keys = {e.key for e in entries}
                    self.m.meta = [e for e in self.m.meta if e.key not in keys] + list(entries)
                case ast.PlayersDecl():
                    self.m.players = item
                case ast.ParamsBlock(items=params):
                    for p in params:
                        if isinstance(p, ast.ParamDecl):
                            if self.new(p.name, self.m.params, "el parámetro", p.span):
                                self.m.params.append(p)
                        elif isinstance(p, ast.AssertDecl):
                            self.m.asserts.append(p)
                case ast.EnumDecl() | ast.StructDecl():
                    if self.new(item.name, self.m.types, "el tipo", item.span):
                        self.m.types.append(item)
                case ast.FnDecl():
                    if self.new(item.name, self.m.functions, "la función", item.span):
                        self.m.functions.append(item)
                case ast.StateBlock(vars=variables):
                    for v in variables:
                        if self.new(v.name, self.m.state, "la variable", v.span):
                            self.m.state.append(v)
                case ast.FlowBlock(items=flow_items):
                    self.flow(flow_items)
                case ast.TestDecl():
                    self.m.tests.append(item)
                case ast.InvariantDecl():
                    self.m.invariants.append(item)
                case ast.UiBlock(entries=entries):
                    self.m.ui = ui.merge(self.m.ui, entries)
                case ast.OverrideDecl(item=inner):
                    self.override(inner, item.span)
                case ast.RemoveDecl():
                    self.remove(item)
                case ast.ExtendNode():
                    self.extend(item)
                case _:
                    self.diagnostics.error(
                        "E110", "declaración no válida dentro de un juego", item.span
                    )

    def new(self, name: str, existing: list, what: str, span: Span) -> bool:  # type: ignore[type-arg]
        if any(x.name == name for x in existing):
            self.error(
                f"{what} `{name}` ya existe en el juego base",
                span,
                help="para cambiarlo usa override; para quitarlo, remove",
            )
            return False
        return True

    # --- flow -----------------------------------------------------------------------------------

    def flow(self, items: list[ast.Item]) -> None:
        for item in items:
            if isinstance(item, ast.StartDecl):
                self.m.start = item
            elif isinstance(item, ast.NodeDecl):
                if _find(self.m.nodes, item.name) is not None:
                    self.error(
                        f"el nodo `{item.name}` ya existe en el juego base",
                        item.span,
                        help=f"para cambiarlo usa override {item.kind} {item.name} {{ … }}",
                    )
                    continue
                self.m.nodes.append(item)

    # --- override, remove, extend ---------------------------------------------------------------

    def override(self, inner: ast.Item, span: Span) -> None:
        match inner:
            case ast.FnDecl():
                self.replace(self.m.functions, inner, "función")
            case ast.EnumDecl() | ast.StructDecl():
                self.replace(self.m.types, inner, "tipo")
            case ast.NodeDecl():
                if not self.edit_node(inner.name, lambda _: inner):
                    self.missing("el nodo", inner.name, inner.span)
            case ast.ParamsBlock(items=params):
                asserts = [p for p in params if isinstance(p, ast.AssertDecl)]
                if asserts:
                    self.m.asserts = asserts  # sustituyen a las restricciones de la base
                for p in params:
                    if isinstance(p, ast.ParamDecl):
                        self.replace(self.m.params, p, "parámetro")
            case ast.StateBlock(vars=variables):
                for v in variables:
                    self.replace(self.m.state, v, "variable")
            case _:
                self.error("no se puede usar override con esto", span)

    def replace(self, items: list, new: ast.Item, what: str) -> None:  # type: ignore[type-arg]
        name = new.name  # type: ignore[attr-defined]
        for i, old in enumerate(items):
            if old.name == name:
                items[i] = new
                return
        self.missing(f"{_article(what)} {what}", name, new.span)

    def missing(self, what: str, name: str, span: Span) -> None:
        self.error(f"{what} `{name}` no existe en el juego base", span)

    def remove(self, item: ast.RemoveDecl) -> None:
        kind, path = item.kind, item.path
        if kind == "action":
            if len(path) != 2:
                self.error("indica el nodo y la acción: remove action Nodo.accion", item.span)
                return
            node_name, action = path

            def drop(node: ast.NodeDecl) -> ast.NodeDecl:
                members = [
                    m
                    for m in node.members
                    if not (isinstance(m, ast.ActionDecl) and m.name == action)
                ]
                if len(members) == len(node.members):
                    self.missing("la acción", f"{node_name}.{action}", item.span)
                return dataclasses.replace(node, members=members)

            if not self.edit_node(node_name, drop):
                self.missing("el nodo", node_name, item.span)
            return
        if len(path) != 1:
            self.error(f"remove {kind} lleva un solo nombre", item.span)
            return
        name = path[0]
        if kind == "node":
            if not self.edit_node(name, lambda _: None):
                self.missing("el nodo", name, item.span)
            return
        tables = {
            "fn": (self.m.functions, "la función"),
            "state": (self.m.state, "la variable"),
            "param": (self.m.params, "el parámetro"),
            "enum": (self.m.types, "el tipo"),
            "struct": (self.m.types, "el tipo"),
        }
        table, what = tables[kind]
        kept = [x for x in table if x.name != name]
        if len(kept) == len(table):
            self.missing(what, name, item.span)
        table[:] = kept

    def extend(self, item: ast.ExtendNode) -> None:
        def add(node: ast.NodeDecl) -> ast.NodeDecl:
            actions: list[ast.Item] = []
            transitions: list[ast.Item] = []
            for member in item.members:
                if isinstance(member, ast.ActionDecl):
                    actions.append(member)
                elif isinstance(member, ast.Transition):
                    transitions.append(member)
                else:
                    self.error(
                        "extend node solo añade acciones y transiciones",
                        member.span,
                        help=f"para cambiar otros miembros usa override {node.kind} {node.name}",
                    )
            members: list[ast.Item] = []
            placed = False
            for member in node.members:
                if isinstance(member, ast.Transition) and not placed:
                    members.extend(transitions)
                    placed = True
                members.append(member)
            if not placed:
                members.extend(transitions)
            last_action = max(
                (i for i, m in enumerate(members) if isinstance(m, ast.ActionDecl)), default=-1
            )
            members[last_action + 1 : last_action + 1] = actions
            return dataclasses.replace(node, members=members)

        if not self.edit_node(item.name, add):
            self.missing("el nodo", item.name, item.span)

    def edit_node(self, name: str, change: Callable[[ast.NodeDecl], ast.NodeDecl | None]) -> bool:
        """Cambia (o quita, si `change` devuelve None) el nodo `name`, esté donde esté, copiando
        las fases que lo contienen. Devuelve si lo encontró."""
        new_nodes, found = _edit(self.m.nodes, name, change)
        self.m.nodes = new_nodes
        return found


def _edit(
    nodes: list[ast.NodeDecl], name: str, change: Callable[[ast.NodeDecl], ast.NodeDecl | None]
) -> tuple[list[ast.NodeDecl], bool]:
    out: list[ast.NodeDecl] = []
    found = False
    for node in nodes:
        if found:
            out.append(node)
            continue
        if node.name == name:
            found = True
            replaced = change(node)
            if replaced is not None:
                out.append(replaced)
            continue
        if node.kind == "phase":
            children = [m for m in node.members if isinstance(m, ast.NodeDecl)]
            new_children, inside = _edit(children, name, change)
            if inside:
                found = True
                rebuilt = iter(new_children)
                members: list[ast.Item] = []
                originals = {id(c) for c in children}
                for m in node.members:
                    if id(m) in originals:
                        continue
                    members.append(m)
                # Los hijos van donde estaban (los nodos de una fase se escriben juntos).
                first = next(
                    (i for i, m in enumerate(node.members) if id(m) in originals), len(members)
                )
                members[first:first] = list(rebuilt)
                out.append(dataclasses.replace(node, members=members))
                continue
        out.append(node)
    return out, found


def _find(nodes: list[ast.NodeDecl], name: str) -> ast.NodeDecl | None:
    for node in nodes:
        if node.name == name:
            return node
        if node.kind == "phase":
            inner = _find([m for m in node.members if isinstance(m, ast.NodeDecl)], name)
            if inner is not None:
                return inner
    return None


def _article(what: str) -> str:
    return "la" if what in ("función", "variable") else "el"
