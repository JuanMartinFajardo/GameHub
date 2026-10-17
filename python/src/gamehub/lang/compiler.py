# SPDX-License-Identifier: Apache-2.0
"""Compilación de archivos `.game`: análisis sintáctico, reunión de declaraciones, comprobación
de tipos y traducción a GameIR, y validación final de la IR con `gamehub.ir.check`."""

from __future__ import annotations

import difflib
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from gamehub.analysis.lint import lint
from gamehub.ir import check as check_ir
from gamehub.ir import wellformed_problems
from gamehub.lang import ast, combinators
from gamehub.lang.checker import Checker, kebab
from gamehub.lang.combinators import COMBINATORS
from gamehub.lang.diagnostics import CompileError, Diagnostics
from gamehub.lang.model import CompiledGame, External, GameModel
from gamehub.lang.mods import derive
from gamehub.lang.modules import Imported, Loader
from gamehub.lang.parser import parse
from gamehub.lang.source import Source, Span
from gamehub.lang.symbols import SymbolIndex

if TYPE_CHECKING:
    from gamehub.engine.game import Game


@dataclass
class CompileResult:
    source: Source
    file: ast.File
    diagnostics: Diagnostics
    games: dict[str, CompiledGame] = field(default_factory=dict)
    #: Modelo (declaraciones reunidas, antes de comprobar) de cada juego con cuerpo del archivo,
    #: también si la comprobación falló; las variantes ya mezcladas con su base.
    models: dict[str, GameModel] = field(default_factory=dict)
    #: En un archivo sin juegos (un módulo), la IR de sus tipos y funciones.
    module: dict[str, Any] | None = None

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


def compile_source(
    source: Source, *, index: SymbolIndex | None = None, schema: bool = True
) -> CompileResult:
    """Compila un texto Nomos. Con `index`, el comprobador anota en él los símbolos (para el
    servidor de lenguaje). `schema=False` valida la IR generada solo por su buena formación, sin
    el JSON Schema, que es lo más lento (el editor compila a cada cambio)."""
    diagnostics = Diagnostics()
    tree = parse(source, diagnostics)
    result = CompileResult(source, tree, diagnostics)
    if diagnostics.has_errors:
        return result
    imported = Loader(diagnostics).root_imports(tree, source)
    if diagnostics.has_errors:
        return result
    games = _Games(tree, diagnostics, imported, index)
    for item in tree.games:
        compiled = games.compiled(item.name, item.span)
        if compiled is not None:
            result.games[item.name] = compiled
    result.models = {name: model for name, model in games.models.items() if name in games.local}
    if not tree.games:
        result.module = check_module(tree, diagnostics, imported, index)
    if diagnostics.has_errors:
        return result
    for name, compiled in result.games.items():
        problems = check_ir(compiled.ir) if schema else wellformed_problems(compiled.ir)
        for problem in problems:
            diagnostics.error(
                "E900",
                f"error interno del compilador: la IR generada no es válida: {problem}",
                compiled.span,
                help="esto es un fallo de GameHub, no de tu juego: por favor, infórmalo",
            )
        model = games.models.get(name)
        if not problems and model is not None:
            warn(compiled, model, diagnostics)
    return result


class _Games:
    """Los juegos que puede usar un archivo (los suyos y los importados), compilados bajo
    demanda: `extends` y los combinadores necesitan su base antes."""

    def __init__(
        self,
        tree: ast.File,
        diagnostics: Diagnostics,
        imported: list[Imported],
        index: SymbolIndex | None = None,
    ) -> None:
        self.tree = tree
        self.diagnostics = diagnostics
        self.imported = imported
        self.index = index
        self.local = {g.name: g for g in tree.games}
        self.foreign: dict[str, ast.GameDecl | ast.GameAlias] = {}
        for item in imported:
            if isinstance(item.decl, ast.GameDecl | ast.GameAlias):
                if item.name in self.local:
                    diagnostics.error(
                        "E202",
                        f"el juego `{item.name}` choca con el importado de {item.module}",
                        self.local[item.name].span,
                    )
                else:
                    self.foreign[item.name] = item.decl
        self.models: dict[str, GameModel] = {}
        self.results: dict[str, CompiledGame | None] = {}
        self.visiting: list[str] = []

    def decl(self, name: str, span: Span) -> ast.GameDecl | ast.GameAlias | None:
        decl = self.local.get(name) or self.foreign.get(name)
        if decl is None:
            known = [*self.local, *self.foreign]
            close = difflib.get_close_matches(name, known, n=1, cutoff=0.7)
            self.diagnostics.error(
                "E201",
                f"juego desconocido: {name}",
                span,
                help=f"¿quisiste decir `{close[0]}`?" if close else "impórtalo con import",
            )
        return decl

    def enter(self, name: str, span: Span) -> bool:
        if name in self.visiting:
            chain = " → ".join([*self.visiting[self.visiting.index(name) :], name])
            self.diagnostics.error("E505", f"un juego no puede basarse en sí mismo: {chain}", span)
            return False
        self.visiting.append(name)
        return True

    def compiled(self, name: str, span: Span) -> CompiledGame | None:
        if name in self.results:
            return self.results[name]
        decl = self.decl(name, span)
        if decl is None or not self.enter(name, span):
            return None
        try:
            if isinstance(decl, ast.GameAlias):
                result = self.combine(decl)
            else:
                model = self.model_of(decl)
                result = (
                    Checker(model, self.diagnostics, self.index).run()
                    if model is not None
                    else None
                )
        finally:
            self.visiting.pop()
        self.results[name] = result
        return result

    def model(self, name: str, span: Span) -> GameModel | None:
        """Modelo (sin comprobar) de un juego, para extenderlo."""
        if name in self.models:
            return self.models[name]
        decl = self.decl(name, span)
        if decl is None:
            return None
        if isinstance(decl, ast.GameAlias):
            compiled = self.compiled(name, span)
            if compiled is None:
                return None
            # Un combinador solo existe como IR: se descompila para poder extenderlo.
            from gamehub.lang.decompile import decompile

            game = decompile(compiled.ir, name).items[0]
            assert isinstance(game, ast.GameDecl)
            return collect(ast.File(items=[game]), game, self.diagnostics)
        if not self.enter(name, span):
            return None
        try:
            return self.model_of(decl)
        finally:
            self.visiting.pop()

    def model_of(self, decl: ast.GameDecl) -> GameModel | None:
        if decl.name in self.models:
            return self.models[decl.name]
        if decl.extends is None:
            model: GameModel | None = collect(self.tree, decl, self.diagnostics, self.imported)
        else:
            base = self.model(decl.extends, decl.span)
            if base is None:
                return None
            externals_ = externals(self.tree, decl.items, self.diagnostics, self.imported)
            model = derive(base, decl, externals_, self.diagnostics)
        if model is not None:
            self.models[decl.name] = model
        return model

    def combine(self, alias: ast.GameAlias) -> CompiledGame | None:
        if alias.combinator not in COMBINATORS:
            self.diagnostics.error(
                "E506",
                f"combinador desconocido: {alias.combinator}",
                alias.span,
                help="se admiten repeat(Juego, rounds: n, payoff: sum|mean) y "
                "best_of(Juego, rounds: n)",
            )
            return None
        allowed = {"rounds", "payoff"} if alias.combinator == "repeat" else {"rounds"}
        rounds: int | None = None
        payoff = "sum"
        for key, value in alias.args:
            if key not in allowed:
                self.diagnostics.error(
                    "E506",
                    f"{alias.combinator} no tiene el argumento `{key}`",
                    value.span,
                    help="argumentos: " + ", ".join(sorted(allowed)),
                )
            elif key == "rounds":
                if isinstance(value, ast.IntLit) and value.value >= 1:
                    rounds = value.value
                else:
                    self.diagnostics.error(
                        "E506", "rounds tiene que ser un entero positivo", value.span
                    )
            elif isinstance(value, ast.Name) and value.name in ("sum", "mean"):
                payoff = value.name
            else:
                self.diagnostics.error("E506", "payoff es sum o mean", value.span)
        if rounds is None:
            if not any(key == "rounds" for key, _ in alias.args):
                self.diagnostics.error(
                    "E506", f"{alias.combinator} necesita rounds: <número de rondas>", alias.span
                )
            return None
        base = self.compiled(alias.base, alias.span)
        if base is None:
            return None
        ir = combinators.apply(alias.combinator, base.ir, kebab(alias.name), rounds, payoff)
        return CompiledGame(alias.name, ir, [], [], alias.span)


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
    for item in game.items:
        add_item(model, item, diagnostics)
    return model


def externals(
    tree: ast.File, local: list[ast.Item], diagnostics: Diagnostics, imported: list[Imported]
) -> list[External]:
    """Declaraciones de módulo de un juego: las de primer nivel del archivo y las importadas.
    Una declaración del archivo o del juego no puede llamarse como una importada."""
    out: list[External] = []
    by_name = {
        item.name: item
        for item in imported
        if isinstance(item.decl, ast.EnumDecl | ast.StructDecl | ast.FnDecl)
    }
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
    for item in by_name.values():
        decl = item.decl
        assert isinstance(decl, ast.EnumDecl | ast.StructDecl | ast.FnDecl)
        out.append(External(decl, item.module))
    return out


def check_module(
    tree: ast.File,
    diagnostics: Diagnostics,
    imported: list[Imported],
    index: SymbolIndex | None = None,
) -> dict[str, Any] | None:
    """Un archivo sin juegos es un módulo: se comprueban sus tipos y funciones (y se devuelve su
    IR)."""
    if not any(isinstance(i, ast.EnumDecl | ast.StructDecl | ast.FnDecl) for i in tree.items):
        return None
    decl = ast.GameDecl(name="<módulo>")
    model = GameModel(name="<módulo>", decl=decl)
    model.externals = externals(tree, [], diagnostics, imported)
    return Checker(model, diagnostics, index).check_module()


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
        case ast.UiBlock(entries=entries):
            model.ui.extend(entries)
        case ast.HeuristicDecl():
            if any(h.name == item.name for h in model.heuristics):
                diagnostics.error(
                    "E202", f"la heurística `{item.name}` ya está declarada", item.name_span()
                )
            else:
                model.heuristics.append(item)
        case ast.OverrideDecl() | ast.RemoveDecl() | ast.ExtendNode():
            diagnostics.error(
                "E502",
                "override, remove y extend solo se usan en un juego que extiende otro "
                "(game Variante extends Base { … })",
                item.span,
            )
        case _:
            diagnostics.error("E110", "declaración no válida dentro de un juego", item.span)
