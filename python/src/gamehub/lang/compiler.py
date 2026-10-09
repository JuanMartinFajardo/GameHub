# SPDX-License-Identifier: Apache-2.0
"""Compilación de archivos `.game`: análisis sintáctico, reunión de declaraciones, comprobación
de tipos y traducción a GameIR, y validación final de la IR con `gamehub.ir.check`."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from gamehub.analysis.lint import lint
from gamehub.ir import check as check_ir
from gamehub.lang import ast
from gamehub.lang.checker import Checker
from gamehub.lang.diagnostics import CompileError, Diagnostics
from gamehub.lang.model import CompiledGame, External, GameModel
from gamehub.lang.modules import Imported, Loader
from gamehub.lang.parser import parse
from gamehub.lang.source import Source, Span

if TYPE_CHECKING:
    from gamehub.engine.game import Game


@dataclass
class CompileResult:
    source: Source
    file: ast.File
    diagnostics: Diagnostics
    games: dict[str, CompiledGame] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.diagnostics.has_errors

    def game(self, name: str | None = None) -> CompiledGame:
        """El juego compilado (el único del archivo, o el indicado). Lanza `CompileError` si la
        compilación tuvo errores."""
        if not self.ok:
            raise CompileError(self.diagnostics)
        if name is None:
            if len(self.games) != 1:
                names = ", ".join(self.games) or "ninguno"
                raise ValueError(
                    f"{self.source.name} contiene varios juegos ({names}): indica cuál"
                    if self.games
                    else f"{self.source.name} no contiene ningún juego"
                )
            return next(iter(self.games.values()))
        if name not in self.games:
            raise ValueError(f"{self.source.name} no contiene el juego {name}")
        return self.games[name]


def compile_source(source: Source) -> CompileResult:
    diagnostics = Diagnostics()
    tree = parse(source, diagnostics)
    result = CompileResult(source, tree, diagnostics)
    if diagnostics.has_errors:
        return result
    imported = Loader(diagnostics).root_imports(tree, source)
    if diagnostics.has_errors:
        return result
    models: dict[str, GameModel] = {}
    for item in tree.items:
        if isinstance(item, ast.GameDecl):
            model = collect(tree, item, diagnostics, imported)
            compiled = Checker(model, diagnostics).run()
            result.games[item.name] = compiled
            models[item.name] = model
        elif isinstance(item, ast.GameAlias):
            diagnostics.error(
                "E501", "los combinadores de juegos aún no están disponibles", item.span
            )
    if not tree.games:
        check_module(tree, diagnostics, imported)
    if diagnostics.has_errors:
        return result
    for name, compiled in result.games.items():
        problems = check_ir(compiled.ir)
        for problem in problems:
            diagnostics.error(
                "E900",
                f"error interno del compilador: la IR generada no es válida: {problem}",
                compiled.span,
                help="esto es un fallo de GameHub, no de tu juego: por favor, infórmalo",
            )
        if not problems:
            warn(compiled, models[name], diagnostics)
    return result


def warn(compiled: CompiledGame, model: GameModel, diagnostics: Diagnostics) -> None:
    """Avisos de los análisis estáticos (`gamehub.analysis.lint`), situados en el texto."""
    spans = source_map(model)
    for finding in lint(compiled.ir, _test_exprs(compiled)):
        where = finding.where
        span = None
        while where and span is None:
            span = spans.get(where)
            where = _enclosing(where)
        diagnostics.warning(finding.code, finding.message, span or compiled.span, help=finding.help)


def _enclosing(where: tuple[str, ...]) -> tuple[str, ...]:
    """El elemento que contiene a otro (para situar un aviso si no hay posición exacta)."""
    match where:
        case ("action_transition", node, action, _):
            return ("action", node, action)
        case ("transition", node, _) | ("action", node, _):
            return ("node", node)
    return ()


def _test_exprs(compiled: CompiledGame) -> Iterator[object]:
    """Expresiones de los tests e invariantes: también cuentan como usos de las declaraciones."""
    for inv in compiled.invariants:
        yield inv.expr
    for case in compiled.tests:
        for step in case.steps:
            for value in (step.value, step.target, *step.entries.values()):
                if isinstance(value, list):
                    yield value
            for call in step.actions:
                yield from call.args


def source_map(model: GameModel) -> dict[tuple[str, ...], Span]:
    """Posición en el texto de cada elemento de la IR al que puede referirse un aviso (el
    nombre del nodo, la acción, la variable…)."""
    spans: dict[tuple[str, ...], Span] = {}
    for p in model.params:
        spans[("param", p.name)] = _name_span(p.span, p.name)
    for v in model.state:
        spans[("var", v.name)] = _name_span(v.span, v.name)
    for f in model.functions:
        spans[("function", f.name)] = _name_span(f.span, f.name)
    for t in model.types:
        spans[("type", t.name)] = _name_span(t.span, t.name)

    def visit(nodes: list[ast.NodeDecl]) -> None:
        for node in nodes:
            spans[("node", node.name)] = _name_span(node.span, node.name)
            i = 0
            for member in node.members:
                if isinstance(member, ast.Transition):
                    spans[("transition", node.name, str(i))] = member.span
                    i += 1
                elif isinstance(member, ast.ActionDecl):
                    key = ("action", node.name, member.name)
                    spans[key] = _name_span(member.span, member.name)
                    for j, t in enumerate(member.transitions):
                        spans[("action_transition", node.name, member.name, str(j))] = t.span
                elif isinstance(member, ast.NodeDecl):
                    visit([member])

    visit(model.nodes)
    return spans


def _name_span(span: Span, name: str) -> Span:
    """El trozo de `span` donde aparece `name` como palabra (o `span` si no aparece)."""
    source = span.source
    if source is None:
        return span
    match = re.compile(rf"\b{re.escape(name)}\b").search(source.text, span.start, span.end)
    if match is None:
        return span
    return Span(source, match.start(), match.end())


def compile_file(path: Path) -> CompileResult:
    return compile_source(Source.from_path(path))


def compile_text(text: str, name: str = "<texto>") -> CompileResult:
    return compile_source(Source(name, text))


def load_nomos(path: Path, game: str | None = None) -> Game:
    """Compila un `.game` y devuelve el juego listo para el motor."""
    from gamehub.engine.game import Game

    return Game(compile_file(path).game(game).ir)


# --- Reunión de declaraciones -------------------------------------------------------------------


def collect(
    tree: ast.File,
    game: ast.GameDecl,
    diagnostics: Diagnostics,
    imported: list[Imported] | None = None,
) -> GameModel:
    model = GameModel(name=game.name, decl=game)
    model.externals = externals(tree, game.items, diagnostics, imported or [])
    if game.extends is not None:
        diagnostics.error(
            "E501", "la herencia de juegos (extends) aún no está disponible", game.span
        )
    for item in game.items:
        add_item(model, item, diagnostics)
    return model


def externals(
    tree: ast.File, local: list[ast.Item], diagnostics: Diagnostics, imported: list[Imported]
) -> list[External]:
    """Declaraciones de módulo de un juego: las de primer nivel del archivo y las importadas.
    Una declaración del archivo o del juego no puede llamarse como una importada."""
    out: list[External] = []
    by_name = {item.name: item for item in imported}
    for item in tree.items:
        if isinstance(item, ast.EnumDecl | ast.StructDecl | ast.FnDecl):
            out.append(External(item, ""))
    for item in [*tree.items, *local]:
        if isinstance(item, ast.EnumDecl | ast.StructDecl | ast.FnDecl) and item.name in by_name:
            clash = by_name.pop(item.name)
            diagnostics.error(
                "E202",
                f"`{item.name}` choca con el importado de {clash.module}",
                item.span,
                help="cambia el nombre o no lo importes",
            )
    out.extend(External(item.decl, item.module) for item in by_name.values())
    return out


def check_module(tree: ast.File, diagnostics: Diagnostics, imported: list[Imported]) -> None:
    """Un archivo sin juegos es un módulo: se comprueban sus tipos y funciones."""
    if not any(isinstance(i, ast.EnumDecl | ast.StructDecl | ast.FnDecl) for i in tree.items):
        return
    decl = ast.GameDecl(name="<módulo>")
    model = GameModel(name="<módulo>", decl=decl)
    model.externals = externals(tree, [], diagnostics, imported)
    Checker(model, diagnostics).check_module()


def add_item(model: GameModel, item: ast.Item, diagnostics: Diagnostics) -> None:
    match item:
        case ast.MetaBlock(entries=entries):
            model.meta.extend(entries)
        case ast.PlayersDecl():
            if model.players is not None:
                diagnostics.error("E210", "'players' declarado dos veces", item.span)
            model.players = item
        case ast.ParamsBlock(items=items):
            for p in items:
                if isinstance(p, ast.ParamDecl):
                    model.params.append(p)
                elif isinstance(p, ast.AssertDecl):
                    model.asserts.append(p)
        case ast.EnumDecl() | ast.StructDecl():
            model.types.append(item)
        case ast.StateBlock(vars=variables):
            model.state.extend(variables)
        case ast.FnDecl():
            model.functions.append(item)
        case ast.FlowBlock(items=items):
            if model.flow_span.source is not None:
                diagnostics.error("E405", "'flow' declarado dos veces", item.span)
            model.flow_span = item.span
            for flow_item in items:
                if isinstance(flow_item, ast.StartDecl):
                    if model.start is not None:
                        diagnostics.error("E405", "el flow tiene dos 'start'", flow_item.span)
                    model.start = flow_item
                elif isinstance(flow_item, ast.NodeDecl):
                    model.nodes.append(flow_item)
        case ast.TestDecl():
            model.tests.append(item)
        case ast.InvariantDecl():
            model.invariants.append(item)
        case ast.OverrideDecl() | ast.RemoveDecl() | ast.ExtendNode():
            diagnostics.error(
                "E502",
                "override, remove y extend solo se usan en un juego que extiende otro "
                "(game Variante extends Base { … })",
                item.span,
            )
        case _:
            diagnostics.error("E110", "declaración no válida dentro de un juego", item.span)
