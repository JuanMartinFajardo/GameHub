# SPDX-License-Identifier: Apache-2.0
"""El modelo de un documento para el Studio: el juego tal como lo dibujan el diagrama y los
formularios.

Sale del modelo del compilador (las declaraciones reunidas, y en una variante ya mezcladas con su
base), no de la IR: así cada expresión se enseña como está escrita y cada elemento sabe dónde está
en el texto. Las expresiones van como texto de Nomos (lo que se edita en un formulario) y las
posiciones, como desplazamientos en UTF-16 (los de las cadenas de JavaScript). Un elemento que
viene de otro archivo (el juego base de una variante) lleva `"local": false`: se ve, pero no se
edita desde aquí.
"""

from __future__ import annotations

from bisect import bisect_left
from typing import Any

from gamehub.lang import ast
from gamehub.lang.layout import render
from gamehub.lang.model import GameModel
from gamehub.lang.printer import Printer
from gamehub.lang.source import Source, Span
from gamehub.studio.edits import print_item


class Utf16:
    """Convierte desplazamientos de una cadena de Python (puntos de código) a UTF-16 y al revés
    (los caracteres fuera del plano básico, como muchos emojis, ocupan dos unidades en UTF-16)."""

    def __init__(self, text: str) -> None:
        self.astral = [i for i, ch in enumerate(text) if ord(ch) > 0xFFFF]

    def __call__(self, offset: int) -> int:
        return offset + bisect_left(self.astral, offset) if self.astral else offset

    def to_python(self, offset: int) -> int:
        if not self.astral:
            return offset
        # Tras k caracteres astrales, un desplazamiento UTF-16 u corresponde a u - k.
        k = 0
        while k < len(self.astral) and self.astral[k] + k < offset:
            k += 1
        return offset - k


def expr_text(e: ast.Expr | None) -> str | None:
    if e is None:
        return None
    return render(Printer().expr(e), 10_000).strip()


def block_text(e: ast.Expr) -> str:
    """Una expresión para un campo de varias líneas (un invariante, el cuerpo de una función):
    con el ancho normal del formateador, así que los bloques `{ let …; … }` salen en líneas."""
    return render(Printer().expr(e), 80).strip()


def type_text(t: ast.TypeExpr | None) -> str | None:
    return None if t is None else Printer().type(t)


def stmts_text(stmts: list[ast.Stmt] | None) -> str | None:
    if stmts is None:
        return None
    return "\n".join(print_item(s) for s in stmts)


def steps_text(steps: list[ast.TestStep]) -> str:
    return "\n".join(print_item(s) for s in steps)


def vis_text(v: ast.Visibility | None) -> str | None:
    if v is None:
        return None
    return expr_text(v.expr) if v.kind == "when" else v.kind


def text_value(t: ast.Text | None) -> str | dict[str, str] | None:
    return None if t is None else t.to_ir()


class _Projector:
    def __init__(self, source: Source) -> None:
        self.source = source
        self.utf16 = Utf16(source.text)

    def local(self, span: Span) -> bool:
        return span.source is not None and span.source.name == self.source.name

    def span(self, span: Span) -> list[int] | None:
        if not self.local(span):
            return None
        return [self.utf16(span.start), self.utf16(span.end)]

    def full_span(self, item: ast.Item) -> list[int] | None:
        """Con la documentación y los comentarios que lo preceden."""
        start = item.span.start
        if item.trivia.leading:
            start = min(start, item.trivia.leading[0].span.start)
        if item.doc is not None and item.doc.span.source is not None:
            start = min(start, item.doc.span.start)
        end = item.span.end
        if item.trivia.trailing is not None:
            end = max(end, item.trivia.trailing.span.end)
        return self.span(Span(item.span.source, start, end))

    def base(self, item: ast.Item, name_index: int | None = 0) -> dict[str, Any]:
        out: dict[str, Any] = {"span": self.span(item.span), "local": self.local(item.span)}
        if name_index is not None and item.name_spans:
            out["nameSpan"] = self.span(item.name_span(name_index))
        if item.doc is not None:
            out["doc"] = text_value(item.doc)
        return out

    # --- juego ----------------------------------------------------------------------------------

    def game(self, model: GameModel) -> dict[str, Any]:
        out: dict[str, Any] = {
            "name": model.name,
            "extends": model.decl.extends,
            "span": self.span(model.decl.span),
            "meta": {e.key: _meta_value(e.value) for e in model.meta},
            "players": self.players(model.players),
            "params": [self.param(p) for p in model.params],
            "asserts": [
                {
                    **self.base(a, None),
                    "expr": expr_text(a.expr),
                    "message": text_value(a.message),
                }
                for a in model.asserts
            ],
            "types": [self.type_decl(t) for t in model.types],
            "state": [self.state_var(v) for v in model.state],
            "functions": [self.function(f) for f in model.functions],
            "externals": [
                {"name": x.decl.name, "kind": _decl_kind(x.decl), "module": x.module}
                for x in model.externals
            ],
            "flow": self.flow(model),
            "ui": [
                {
                    **self.base(e, None),
                    "target": _ui_target(e),
                    "hints": render(Printer().i_UiEntry(e), 10_000).split(": ", 1)[1],
                }
                for e in model.ui
            ],
            "tests": [
                {**self.base(t, None), "name": t.name, "body": steps_text(t.steps)}
                for t in model.tests
            ],
            "invariants": [
                {**self.base(i, None), "expr": block_text(i.expr)} for i in model.invariants
            ],
        }
        return out

    def players(self, players: ast.PlayersDecl | None) -> dict[str, Any] | None:
        if players is None:
            return None
        return {"min": players.min, "max": players.max, "local": self.local(players.span)}

    def param(self, p: ast.ParamDecl) -> dict[str, Any]:
        return {
            **self.base(p),
            "name": p.name,
            "type": type_text(p.type),
            "default": expr_text(p.default),
        }

    def type_decl(self, t: ast.EnumDecl | ast.StructDecl) -> dict[str, Any]:
        if isinstance(t, ast.EnumDecl):
            return {**self.base(t), "kind": "enum", "name": t.name, "values": list(t.values)}
        return {
            **self.base(t),
            "kind": "struct",
            "name": t.name,
            "fields": [{"name": f.name, "type": type_text(f.type)} for f in t.fields],
        }

    def state_var(self, v: ast.StateVar) -> dict[str, Any]:
        return {
            **self.base(v),
            "name": v.name,
            "type": type_text(v.type),
            "init": expr_text(v.init),
            "visibility": vis_text(v.visibility),
            "sizeVisibility": vis_text(v.size_visibility),
        }

    def function(self, f: ast.FnDecl) -> dict[str, Any]:
        return {
            **self.base(f),
            "name": f.name,
            "params": [{"name": p.name, "type": type_text(p.type)} for p in f.params],
            "returns": type_text(f.returns),
            "body": block_text(f.body),
        }

    # --- flow -----------------------------------------------------------------------------------

    def flow(self, model: GameModel) -> dict[str, Any]:
        nodes: list[dict[str, Any]] = []

        def visit(items: list[ast.NodeDecl], parent: str | None) -> None:
            for node in items:
                nodes.append(self.node(node, parent))
                if node.kind == "phase":
                    visit([m for m in node.members if isinstance(m, ast.NodeDecl)], node.name)

        visit(model.nodes, None)
        start = model.start
        return {
            "span": self.span(model.flow_span) if model.flow_span.source is not None else None,
            "start": (
                {
                    "target": start.target,
                    "setup": stmts_text(start.setup),
                    "span": self.span(start.span),
                    "local": self.local(start.span),
                }
                if start is not None
                else None
            ),
            "nodes": nodes,
        }

    def node(self, node: ast.NodeDecl, parent: str | None) -> dict[str, Any]:
        out: dict[str, Any] = {
            **self.base(node),
            "id": node.name,
            "kind": node.kind,
            "parent": parent,
            "fullSpan": self.full_span(node),
            "members": {},
            "lets": [],
            "blocks": {},
            "effects": None,
            "actions": [],
            "transitions": [],
        }
        effects: list[ast.Stmt] = []
        transitions: list[ast.Transition] = []
        for m in node.members:
            match m:
                case ast.Member():
                    out["members"][m.key] = expr_text(m.value)
                case ast.LetMember():
                    out["lets"].append({"name": m.name, "value": expr_text(m.value)})
                case ast.BlockMember():
                    out["blocks"][m.key] = stmts_text(m.body)
                case ast.ActionDecl():
                    out["actions"].append(self.action(m))
                case ast.Transition():
                    transitions.append(m)
                case ast.StartDecl():
                    out["start"] = {"target": m.target, "span": self.span(m.span)}
                case ast.NodeDecl():
                    out.setdefault("children", []).append(m.name)
                case ast.Stmt():
                    effects.append(m)
        if node.kind in ("chance", "auto"):
            out["effects"] = stmts_text(effects)
        out["transitions"] = [self.transition(t, i) for i, t in enumerate(transitions)]
        return out

    def action(self, a: ast.ActionDecl) -> dict[str, Any]:
        return {
            **self.base(a),
            "name": a.name,
            "params": [
                {
                    "name": p.name,
                    "type": type_text(p.type),
                    "domain": expr_text(p.domain),
                    "visibility": vis_text(p.visibility),
                    "sizeVisibility": vis_text(p.size_visibility),
                }
                for p in a.params
            ],
            "requires": expr_text(a.requires),
            "effects": stmts_text(a.effects) if a.effects else None,
            "visibility": vis_text(a.visibility),
            "transitions": [self.transition(t, i) for i, t in enumerate(a.transitions)],
        }

    def transition(self, t: ast.Transition, index: int) -> dict[str, Any]:
        return {
            **self.base(t),
            "index": index,
            "target": t.target,
            "when": expr_text(t.when),
            "effects": stmts_text(t.effects) if t.effects else None,
        }


def document_model(
    source: Source,
    tree: ast.File,
    models: dict[str, GameModel] | None = None,
    *,
    game: str | None = None,
) -> dict[str, Any]:
    """El modelo del documento. `models`, los del compilador (si compiló hasta reunir las
    declaraciones); si no, se reúnen las del propio archivo, sin importaciones."""
    projector = _Projector(source)
    games = [
        {
            "name": g.name,
            "kind": "alias" if isinstance(g, ast.GameAlias) else "game",
            "extends": getattr(g, "extends", None),
            "span": projector.span(g.span),
        }
        for g in tree.games
    ]
    decls = [g for g in tree.games if isinstance(g, ast.GameDecl)]
    chosen = next((g for g in decls if g.name == game), decls[0] if decls else None)
    out: dict[str, Any] = {"games": games, "game": None}
    if chosen is None:
        return out
    model = (models or {}).get(chosen.name)
    if model is None:
        from gamehub.lang.compiler import collect
        from gamehub.lang.diagnostics import Diagnostics

        model = collect(tree, chosen, Diagnostics()) if chosen.extends is None else None
    if model is None:
        return out
    out["game"] = projector.game(model)
    return out


def _meta_value(value: Any) -> Any:
    if isinstance(value, ast.Text):
        return value.to_ir()
    if isinstance(value, list):
        return list(value)
    return value


def _decl_kind(decl: ast.Item) -> str:
    if isinstance(decl, ast.EnumDecl):
        return "enum"
    if isinstance(decl, ast.StructDecl):
        return "struct"
    return "fn"


def _ui_target(entry: ast.UiEntry) -> str:
    match entry.target:
        case "action":
            return "action " + ".".join(entry.path)
        case "node":
            return "node " + entry.path[0]
        case "seats":
            return "seats"
    return entry.path[0]
