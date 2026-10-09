# SPDX-License-Identifier: Apache-2.0
"""Compilación de archivos `.game`: análisis sintáctico, reunión de declaraciones, comprobación
de tipos y traducción a GameIR, y validación final de la IR con `gamehub.ir.check`."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from gamehub.ir import check as check_ir
from gamehub.lang import ast
from gamehub.lang.checker import Checker
from gamehub.lang.diagnostics import CompileError, Diagnostics
from gamehub.lang.model import CompiledGame, External, GameModel
from gamehub.lang.parser import parse
from gamehub.lang.source import Source

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
    for item in tree.items:
        if isinstance(item, ast.GameDecl):
            model = collect(tree, item, diagnostics)
            compiled = Checker(model, diagnostics).run()
            result.games[item.name] = compiled
        elif isinstance(item, ast.GameAlias):
            diagnostics.error(
                "E501", "los combinadores de juegos aún no están disponibles", item.span
            )
    if not diagnostics.has_errors:
        for compiled in result.games.values():
            for problem in check_ir(compiled.ir):
                diagnostics.error(
                    "E900",
                    f"error interno del compilador: la IR generada no es válida: {problem}",
                    compiled.span,
                    help="esto es un fallo de GameHub, no de tu juego: por favor, infórmalo",
                )
    return result


def compile_file(path: Path) -> CompileResult:
    return compile_source(Source.from_path(path))


def compile_text(text: str, name: str = "<texto>") -> CompileResult:
    return compile_source(Source(name, text))


def load_nomos(path: Path, game: str | None = None) -> Game:
    """Compila un `.game` y devuelve el juego listo para el motor."""
    from gamehub.engine.game import Game

    return Game(compile_file(path).game(game).ir)


# --- Reunión de declaraciones -------------------------------------------------------------------


def collect(tree: ast.File, game: ast.GameDecl, diagnostics: Diagnostics) -> GameModel:
    model = GameModel(name=game.name, decl=game)
    for item in tree.items:
        if isinstance(item, ast.EnumDecl | ast.StructDecl | ast.FnDecl):
            model.externals.append(External(item, ""))
    if game.extends is not None:
        diagnostics.error(
            "E501", "la herencia de juegos (extends) aún no está disponible", game.span
        )
    for item in game.items:
        add_item(model, item, diagnostics)
    return model


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
