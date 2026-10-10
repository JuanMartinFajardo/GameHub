# SPDX-License-Identifier: Apache-2.0
"""Comprobador de Nomos y traducción a GameIR.

Una sola pasada por cada declaración: resuelve nombres, comprueba tipos y contextos, y produce
la IR resuelta a la vez (cada expresión devuelve su IR y su tipo). Los errores se informan con
posición; una expresión errónea tiene tipo `unknown`, que es compatible con todo, para no
encadenar errores.

Traducciones con azúcar (ver docs/wiki/lenguaje-game.md):
- `a + b + c` → `["add", a, b, c]` (lo mismo con `*`, `and`, `or`), salvo paréntesis explícitos.
- `-3` → `["const", -3]`; `0.5` → `["rat", 1, 2]`; `a..b` → `range`; `a..<b` → `range(a, b-1)`.
- Listas: `+` → `concat`, `-` → `difference`; `x in xs` → `contains`.
- `lv += e` → `assign(lv, add(lv, e))` (o `concat` en listas).
- Comprensiones → `map` / `filter` / `flat_map`; `sum(xs)` → `sum` con la variable `x`.
- `match` → `case` (el último caso se convierte en el valor por defecto si es exhaustivo).
- `deal` → bucles `for` de `move`; `x = roll(n)` → `roll`, `random(xs)` → `random_choice`.
"""

from __future__ import annotations

import difflib
import itertools
import json
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field, replace
from typing import Any

from gamehub.lang import ast
from gamehub.lang import types as T
from gamehub.lang.diagnostics import Diagnostics
from gamehub.lang.model import (
    ActionCall,
    CompiledGame,
    GameModel,
    Invariant,
    TestCase,
    TestStep,
)
from gamehub.lang.source import NO_SPAN, Span
from gamehub.lang.types import Ty
from gamehub.lang.ui import UiContext, check_ui

IR_VERSION = "0.1.0"
SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SEMVER = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z.-]+)?$")
META_TEXT = ("title", "description")
META_KEYS = ("id", "version", "title", "description", "authors", "license", "tags")
CONTEXT_VALUES = ("seats", "num_players", "actor", "viewer", "owner", "face_up")
RANDOM_CALLS = {"roll": "roll", "random": "random_choice", "sample": "sample"}
NODE_MEMBERS = {
    "decision": {"actor"},
    "simultaneous": {"actors"},
    "window": {"eligible", "mode", "order"},
    "chance": set(),
    "auto": set(),
    "phase": set(),
    "terminal": {"payoff", "rank"},
}
FLATTEN = {"add", "mul", "and", "or"}

Typed = tuple[Any, Ty]
ERROR: Typed = (["const", None], T.UNKNOWN)


def kebab(name: str) -> str:
    """`KuhnPoker` → `kuhn-poker` (id de juego por defecto)."""
    out = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "-", name)
    out = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", "-", out)
    return re.sub(r"[^a-z0-9]+", "-", out.lower()).strip("-")


# --- Ámbitos y contextos ------------------------------------------------------------------------


@dataclass(frozen=True)
class Binding:
    kind: str  # "local" | "arg"
    ty: Ty
    span: Span = NO_SPAN


class Scope:
    __slots__ = ("names", "parent")

    def __init__(self, parent: Scope | None = None) -> None:
        self.names: dict[str, Binding] = {}
        self.parent = parent

    def lookup(self, name: str) -> Binding | None:
        scope: Scope | None = self
        while scope is not None:
            if name in scope.names:
                return scope.names[name]
            scope = scope.parent
        return None

    def child(self) -> Scope:
        return Scope(self)

    def visible(self) -> Iterator[str]:
        scope: Scope | None = self
        while scope is not None:
            yield from scope.names
            scope = scope.parent


@dataclass(frozen=True)
class Ctx:
    """Qué está permitido donde se evalúa una expresión."""

    where: str
    reads_state: bool = True
    actor: bool = False
    visibility: bool = False
    owned: bool = False
    chance: bool = False
    test: bool = False
    params_upto: int | None = None  # en valores por defecto: solo los parámetros anteriores
    module: bool = False  # en una función de módulo: no se ven el estado ni las opciones del juego


@dataclass
class TypeInfo:
    decl: ast.EnumDecl | ast.StructDecl
    external: bool
    fields: dict[str, Ty] = field(default_factory=dict)


@dataclass
class FnInfo:
    decl: ast.FnDecl
    params: list[tuple[str, Ty]]
    returns: Ty
    external: bool
    ir: dict[str, Any] | None = None


@dataclass
class NodeInfo:
    decl: ast.NodeDecl
    parent: str | None


class Checker:
    def __init__(self, model: GameModel, diagnostics: Diagnostics) -> None:
        self.model = model
        self.diagnostics = diagnostics
        self.types: dict[str, TypeInfo] = {}
        self.enum_values: dict[str, list[str]] = {}
        self.params: dict[str, tuple[Ty, int]] = {}
        self.state: dict[str, Ty] = {}
        self.functions: dict[str, FnInfo] = {}
        self.nodes: dict[str, NodeInfo] = {}
        self.owner = "game"
        self.refs: dict[str, set[str]] = {"game": set()}
        self.calls: dict[str, set[str]] = {}
        self.actions: dict[str, list[ast.ActionDecl]] = {}
        self.action_params: dict[str, dict[str, list[Ty]]] = {}
        self.in_module = False

    # --- utilidades -----------------------------------------------------------------------------

    def error(
        self, code: str, message: str, span: Span, label: str = "", help: str | None = None
    ) -> Typed:
        self.diagnostics.error(code, message, span, label, help=help)
        return ERROR

    def warning(self, code: str, message: str, span: Span, help: str | None = None) -> None:
        self.diagnostics.warning(code, message, span, help=help)

    def suggest(self, name: str, candidates: Iterator[str] | list[str]) -> str | None:
        close = difflib.get_close_matches(name, list(candidates), n=1, cutoff=0.7)
        return f"¿quisiste decir `{close[0]}`?" if close else None

    def use(self, name: str) -> None:
        self.refs.setdefault(self.owner, set()).add(name)

    def expect(self, typed: Typed, want: Ty, span: Span, what: str = "") -> Any:
        ir, ty = typed
        if not T.assignable(ty, want):
            self.error(
                "E301",
                f"tipos incompatibles{': ' + what if what else ''}: se esperaba `{want}`, "
                f"se encontró `{ty}`",
                span,
                f"esto es `{ty}`",
            )
        return ir

    def global_names(self) -> list[str]:
        """Nombres que un local no puede ocultar. Dentro de una función de módulo, el estado y
        las opciones del juego no existen, así que sus nombres quedan libres."""
        game = [] if self.in_module else [*self.state, *self.params]
        return [*game, *self.functions, *self.types, *self.enum_values, *CONTEXT_VALUES]

    # --- programa -------------------------------------------------------------------------------

    def run(self) -> CompiledGame:
        m = self.model
        self.declare_types()
        self.declare_params()
        self.declare_state()
        self.declare_functions()
        self.collect_nodes()
        params_ir, constraints_ir = self.check_params()
        state_ir = self.check_state()
        self.check_functions()
        flow_ir = self.check_flow()
        tests = [self.check_test(t) for t in m.tests]
        invariants = [self.check_invariant(i) for i in m.invariants]
        self.check_recursion()
        ir = self.assemble(params_ir, constraints_ir, state_ir, flow_ir)
        return CompiledGame(m.name, ir, tests, invariants, m.decl.span)

    def check_module(self) -> None:
        """Comprueba un módulo sin juego: sus tipos y sus funciones."""
        self.declare_types()
        self.declare_functions()
        self.check_functions()
        self.check_recursion()

    def assemble(
        self,
        params_ir: list[dict[str, Any]],
        constraints_ir: list[dict[str, Any]],
        state_ir: list[dict[str, Any]],
        flow_ir: dict[str, Any],
    ) -> dict[str, Any]:
        m = self.model
        used = self.reachable()
        game_id, version, meta = self.meta()
        players = m.players
        if players is None:
            self.error(
                "E210",
                f"el juego {m.name} no declara cuántos jugadores admite",
                m.decl.span,
                help="añade, por ejemplo, 'players 2' o 'players 2..4'",
            )
            lo, hi = 1, 1
        else:
            lo, hi = players.min, players.max
            if lo < 1 or hi < lo:
                self.error("E210", f"rango de jugadores inválido: {lo}..{hi}", players.span)
        ir: dict[str, Any] = {
            "ir_version": IR_VERSION,
            "game": {"id": game_id, "version": version},
        }
        if meta:
            ir["meta"] = meta
        ir["players"] = {"min": lo, "max": hi}
        if params_ir:
            ir["params"] = params_ir
        if constraints_ir:
            ir["constraints"] = constraints_ir
        types_ir = [
            self.type_decl_ir(info)
            for info in self.ordered_types()
            if not info.external or info.decl.name in used
        ]
        if types_ir:
            ir["types"] = types_ir
        ir["state"] = state_ir
        functions_ir = [
            info.ir
            for info in self.ordered_functions()
            if info.ir is not None and (not info.external or info.decl.name in used)
        ]
        if functions_ir:
            ir["functions"] = functions_ir
        ir["flow"] = flow_ir
        emitted = {t["name"] for t in types_ir}
        ui_ir = self.check_ui(emitted)
        if ui_ir:
            ir["ui"] = ui_ir
        return ir

    def check_ui(self, emitted_types: set[str]) -> dict[str, Any]:
        structs = {
            name: info.fields
            for name, info in self.types.items()
            if isinstance(info.decl, ast.StructDecl)
        }
        actions = {name: dict(self.action_params.get(name, {})) for name in self.actions}
        ctx = UiContext(
            state=dict(self.state),
            params=set(self.params),
            enums=dict(self.enum_values_by_type()),
            structs=structs,
            actions=actions,
            nodes=set(self.nodes),
            emitted_types=emitted_types,
        )
        return check_ui(self.model.ui, ctx, self.diagnostics)

    def enum_values_by_type(self) -> dict[str, list[str]]:
        return {
            name: list(info.decl.values)
            for name, info in self.types.items()
            if isinstance(info.decl, ast.EnumDecl)
        }

    def ordered_types(self) -> list[TypeInfo]:
        externals = [i for i in self.types.values() if i.external]
        local = [i for i in self.types.values() if not i.external]
        return externals + local

    def ordered_functions(self) -> list[FnInfo]:
        externals = [i for i in self.functions.values() if i.external]
        local = [i for i in self.functions.values() if not i.external]
        return externals + local

    def reachable(self) -> set[str]:
        """Tipos y funciones alcanzables desde el juego (las declaraciones de módulo que no se
        usan no llegan a la IR)."""
        roots = {"game"}
        roots |= {name for name, info in self.types.items() if not info.external}
        roots |= {name for name, info in self.functions.items() if not info.external}
        seen: set[str] = set()
        stack = list(roots)
        while stack:
            name = stack.pop()
            if name in seen:
                continue
            seen.add(name)
            stack.extend(self.refs.get(name, ()))
        return seen

    def meta(self) -> tuple[str, str, dict[str, Any]]:
        m = self.model
        game_id = kebab(m.name)
        version = "0.1.0"
        meta: dict[str, Any] = {}
        seen: set[str] = set()
        for entry in m.meta:
            key, value = entry.key, entry.value
            if key in seen:
                self.error("E210", f"campo de meta repetido: {key}", entry.span)
            seen.add(key)
            if key not in META_KEYS:
                self.error(
                    "E210",
                    f"campo de meta desconocido: {key}",
                    entry.span,
                    help=f"se admiten: {', '.join(META_KEYS)}",
                )
                continue
            if key in ("id", "version", "license"):
                if not isinstance(value, ast.Text) or not isinstance(value.value, str):
                    self.error("E210", f"meta.{key} debe ser un texto simple", entry.span)
                    continue
                if key == "id":
                    game_id = value.value
                    if not SLUG.match(game_id):
                        self.error(
                            "E210",
                            f"id de juego inválido: {game_id!r}",
                            entry.span,
                            help="minúsculas, cifras y guiones: por ejemplo kuhn-poker",
                        )
                elif key == "version":
                    version = value.value
                    if not SEMVER.match(version):
                        self.error(
                            "E210",
                            f"versión inválida: {version!r} (se espera semver, p. ej. 1.0.0)",
                            entry.span,
                        )
                else:
                    meta[key] = value.value
            elif key in META_TEXT:
                if not isinstance(value, ast.Text):
                    self.error("E210", f"meta.{key} debe ser un texto", entry.span)
                    continue
                meta[key] = value.to_ir()
            else:
                if not isinstance(value, list):
                    self.error("E210", f"meta.{key} debe ser una lista de textos", entry.span)
                    continue
                if key == "tags" and len(set(value)) != len(value):
                    self.error("E210", "etiquetas repetidas en meta.tags", entry.span)
                meta[key] = list(value)
        if not SLUG.match(game_id):
            self.error(
                "E210",
                f"no se puede derivar un id válido del nombre {m.name}",
                m.decl.span,
                help='indica uno en meta: id: "mi-juego"',
            )
        return game_id, version, meta

    # --- declaraciones --------------------------------------------------------------------------

    def declare_global(self, name: str, span: Span, what: str) -> bool:
        """Registra un nombre global; informa si choca con otro."""
        if name in CONTEXT_VALUES:
            self.error("E206", f"`{name}` es un nombre reservado del lenguaje", span)
            return False
        clashes = [
            ("una variable de estado", self.state),
            ("un parámetro", self.params),
            ("una función", self.functions),
            ("un tipo", self.types),
            ("un valor de enumerado", self.enum_values),
        ]
        for label, table in clashes:
            if name in table:
                self.error("E202", f"{what} `{name}` choca con {label} del mismo nombre", span)
                return False
        return True

    def declare_types(self) -> None:
        m = self.model
        decls: list[tuple[ast.EnumDecl | ast.StructDecl, bool]] = []
        for x in m.externals:
            if isinstance(x.decl, ast.EnumDecl | ast.StructDecl):
                decls.append((x.decl, True))
        decls += [(d, False) for d in m.types]
        for decl, external in decls:
            if decl.name in self.types:
                if external and self.types[decl.name].external:
                    continue
                self.error("E202", f"tipo duplicado: {decl.name}", decl.span)
                continue
            if decl.name in T.PRIMITIVES or decl.name in ("List", "Set", "Map", "Zone", "Bag"):
                self.error("E206", f"`{decl.name}` es un tipo predefinido", decl.span)
                continue
            self.types[decl.name] = TypeInfo(decl, external)
        for name, info in self.types.items():
            if isinstance(info.decl, ast.EnumDecl):
                if len(set(info.decl.values)) != len(info.decl.values):
                    self.error("E202", f"valores repetidos en el enumerado {name}", info.decl.span)
                for value in info.decl.values:
                    if value in self.types:
                        self.error(
                            "E202", f"el valor {value} de {name} choca con un tipo", info.decl.span
                        )
                    self.enum_values.setdefault(value, []).append(name)
        for name, info in self.types.items():
            if isinstance(info.decl, ast.StructDecl):
                self.owner = name
                for f in info.decl.fields:
                    if f.name in info.fields:
                        self.error("E202", f"campo repetido en {name}: {f.name}", f.span)
                    info.fields[f.name] = self.resolve_type(f.type)
                self.owner = "game"

    def type_decl_ir(self, info: TypeInfo) -> dict[str, Any]:
        decl = info.decl
        out: dict[str, Any]
        if isinstance(decl, ast.EnumDecl):
            out = {"kind": "enum", "name": decl.name, "values": list(decl.values)}
        else:
            out = {
                "kind": "struct",
                "name": decl.name,
                "fields": [{"name": k, "type": T.to_ir(v)} for k, v in info.fields.items()],
            }
        if decl.doc is not None:
            out["doc"] = decl.doc.to_ir()
        return out

    def resolve_type(self, t: ast.TypeExpr) -> Ty:
        match t:
            case ast.TName(name=name):
                if name in T.PRIMITIVES:
                    return Ty(name)
                if name in self.types:
                    self.use(name)
                    info = self.types[name]
                    return T.enum_(name) if isinstance(info.decl, ast.EnumDecl) else T.struct_(name)
                if name in ("List", "Set", "Zone", "Bag", "Map"):
                    self.error("E301", f"`{name}` necesita sus tipos: {name}<…>", t.span)
                    return T.UNKNOWN
                self.error(
                    "E201",
                    f"tipo desconocido: {name}",
                    t.span,
                    help=self.suggest(name, [*T.PRIMITIVES, *self.types]),
                )
                return T.UNKNOWN
            case ast.TOption(inner=inner):
                return T.option(self.resolve_type(inner))
            case ast.TGeneric(name=name, args=args):
                arity = {"List": 1, "Set": 1, "Zone": 1, "Bag": 1, "Map": 2}
                if name not in arity:
                    self.error(
                        "E201",
                        f"tipo genérico desconocido: {name}",
                        t.span,
                        help="se admiten List<T>, Set<T>, Map<K, V>, Zone<T> y Bag<T>",
                    )
                    return T.UNKNOWN
                if len(args) != arity[name]:
                    self.error("E301", f"{name} lleva {arity[name]} tipo(s)", t.span)
                    return T.UNKNOWN
                resolved = [self.resolve_type(a) for a in args]
                if name == "Map":
                    return T.map_(*resolved)
                return Ty(name.lower(), args=(resolved[0],))
            case ast.TTuple(items=items):
                return T.tuple_(*(self.resolve_type(i) for i in items))
            case ast.TPerPlayer(inner=inner):
                return T.per_player(self.resolve_type(inner))
            case ast.TGrid(width=w, height=h, inner=inner):
                for dim in (w, h):
                    if isinstance(dim, str) and dim not in self.params:
                        self.error("E201", f"parámetro desconocido en la dimensión: {dim}", t.span)
                    elif isinstance(dim, int) and dim < 1:
                        self.error("E301", "las dimensiones de una rejilla son positivas", t.span)
                return T.grid(w, h, self.resolve_type(inner))
        self.error("E301", "tipo no válido", t.span)
        return T.UNKNOWN

    def declare_params(self) -> None:
        for i, p in enumerate(self.model.params):
            if p.name == "num_players":
                self.error("E206", "`num_players` es un parámetro predefinido", p.span)
                continue
            if not self.declare_global(p.name, p.span, "el parámetro"):
                continue
            self.params[p.name] = (T.UNKNOWN, i)
        for p in self.model.params:
            if p.name in self.params:
                self.params[p.name] = (self.resolve_type(p.type), self.params[p.name][1])

    def declare_state(self) -> None:
        for var in self.model.state:
            if not self.declare_global(var.name, var.span, "la variable"):
                continue
            self.state[var.name] = self.resolve_type(var.type)

    def declare_functions(self) -> None:
        from gamehub.lang.builtins import BUILTINS

        m = self.model
        decls: list[tuple[ast.FnDecl, bool]] = [
            (x.decl, True) for x in m.externals if isinstance(x.decl, ast.FnDecl)
        ]
        decls += [(f, False) for f in m.functions]
        for decl, external in decls:
            if decl.name in self.functions and external and self.functions[decl.name].external:
                continue
            if decl.name in BUILTINS or decl.name in RANDOM_CALLS or decl.name == "at":
                self.error(
                    "E206", f"`{decl.name}` es una función predefinida del lenguaje", decl.span
                )
                continue
            if not self.declare_global(decl.name, decl.span, "la función"):
                continue
            self.owner = decl.name
            params: list[tuple[str, Ty]] = []
            for p in decl.params:
                if p.name in (n for n, _ in params):
                    self.error("E202", f"parámetro repetido: {p.name}", p.span)
                params.append((p.name, self.resolve_type(p.type)))
            self.functions[decl.name] = FnInfo(
                decl, params, self.resolve_type(decl.returns), external
            )
            self.owner = "game"

    # --- parámetros, restricciones y estado -----------------------------------------------------

    def check_params(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        params_ir: list[dict[str, Any]] = []
        for i, p in enumerate(self.model.params):
            if p.name not in self.params:
                continue
            ty = self.params[p.name][0]
            ctx = Ctx("el valor por defecto de un parámetro", reads_state=False, params_upto=i)
            default = self.expect(self.expr(p.default, Scope(), ctx, ty), ty, p.default.span)
            out: dict[str, Any] = {"name": p.name, "type": T.to_ir(ty), "default": default}
            if p.doc is not None:
                out["doc"] = p.doc.to_ir()
            params_ir.append(out)
        constraints: list[dict[str, Any]] = []
        for a in self.model.asserts:
            ctx = Ctx("una restricción de parámetros", reads_state=False)
            expr = self.expect(self.expr(a.expr, Scope(), ctx, T.BOOL), T.BOOL, a.expr.span)
            out = {"expr": expr}
            if a.message is not None:
                out["message"] = a.message.to_ir()
            constraints.append(out)
        return params_ir, constraints

    def check_state(self) -> list[dict[str, Any]]:
        state_ir: list[dict[str, Any]] = []
        for var in self.model.state:
            if var.name not in self.state:
                continue
            ty = self.state[var.name]
            per_player = ty.kind == "per_player"
            target = ty.inner if per_player else ty
            ctx = Ctx("la inicialización del estado", reads_state=False, owned=per_player)
            if var.init is None:
                init = self.zero(target, var.span)
            elif target.kind == "grid":
                init = self.grid_init(var.init, target, ctx)
            else:
                init = self.expect(self.expr(var.init, Scope(), ctx, target), target, var.init.span)
            out: dict[str, Any] = {"name": var.name, "type": T.to_ir(ty), "init": init}
            if var.visibility is not None:
                out["visibility"] = self.visibility(var.visibility, per_player, f"{var.name}")
            if var.size_visibility is not None:
                if target.kind not in ("zone", "bag"):
                    self.warning(
                        "W101",
                        "@size_visible solo tiene efecto en zonas y bolsas",
                        var.size_visibility.span,
                    )
                out["size_visibility"] = self.visibility(
                    var.size_visibility, per_player, f"{var.name}"
                )
            if var.doc is not None:
                out["doc"] = var.doc.to_ir()
            state_ir.append(out)
        return state_ir

    def grid_init(self, e: ast.Expr, t: Ty, ctx: Ctx) -> Any:
        """Una rejilla se inicializa con un valor (todas las casillas) o con una lista de filas."""
        ir, ty = self.expr(e, Scope(), ctx, t.inner)
        rows = T.list_(T.list_(t.inner))
        if not (T.assignable(ty, t.inner) or T.assignable(ty, rows)):
            self.error(
                "E301",
                f"una rejilla se inicializa con un `{t.inner}` o con una lista de filas",
                e.span,
                f"esto es `{ty}`",
            )
        return ir

    def zero(self, t: Ty, span: Span) -> Any:
        """Valor inicial por defecto de un tipo."""
        match t.kind:
            case "Bool":
                return ["const", False]
            case "Int" | "Real" | "Seat":
                return ["const", 0]
            case "Text":
                return ["const", ""]
            case "Cell":
                return ["cell", ["const", 0], ["const", 0]]
            case "option" | "unknown":
                return ["const", None]
            case "list" | "set" | "map" | "zone" | "bag":
                return ["list"]
            case "per_player" | "grid":
                return self.zero(t.inner, span)
            case "tuple":
                return ["tuple", *(self.zero(a, span) for a in t.args)]
            case "enum":
                info = self.types[t.name]
                assert isinstance(info.decl, ast.EnumDecl)
                return ["enum", t.name, info.decl.values[0]]
            case "struct":
                info = self.types[t.name]
                return ["struct", t.name, {k: self.zero(v, span) for k, v in info.fields.items()}]
        self.error("E301", f"no hay valor por defecto para `{t}`: indica uno con '='", span)
        return ["const", None]

    def visibility(self, vis: ast.Visibility, owned: bool, what: str) -> Any:
        if vis.kind == "owner" and not owned:
            self.error(
                "E301",
                "@visible(owner) solo tiene sentido en variables per_player y en parámetros de "
                "acción",
                vis.span,
                help="para ocultarlo a todos usa @visible(none)",
            )
        if vis.kind != "when":
            return vis.kind
        assert vis.expr is not None
        ctx = Ctx(f"la visibilidad de {what}", visibility=True, owned=True)
        expr = self.expect(self.expr(vis.expr, Scope(), ctx, T.BOOL), T.BOOL, vis.expr.span)
        return {"when": expr}

    # --- funciones ------------------------------------------------------------------------------

    def check_functions(self) -> None:
        for name, info in self.functions.items():
            self.owner = name
            self.in_module = info.external
            scope = Scope()
            for pname, pty in info.params:
                self.bind(scope, pname, "arg", pty, info.decl.span)
            ctx = Ctx(f"la función {name}")
            if info.external:
                ctx = replace(ctx, reads_state=False, module=True)
            body = self.expect(
                self.expr(info.decl.body, scope, ctx, info.returns),
                info.returns,
                info.decl.body.span,
                f"resultado de {name}",
            )
            out: dict[str, Any] = {
                "name": name,
                "params": [[p, T.to_ir(t)] for p, t in info.params],
                "returns": T.to_ir(info.returns),
                "body": body,
            }
            if info.decl.doc is not None:
                out["doc"] = info.decl.doc.to_ir()
            info.ir = out
        self.owner = "game"
        self.in_module = False

    def check_recursion(self) -> None:
        visiting: set[str] = set()
        done: set[str] = set()

        def visit(name: str, trail: list[str]) -> None:
            if name in done:
                return
            if name in visiting:
                cycle = " → ".join([*trail[trail.index(name) :], name])
                info = self.functions[name]
                self.error(
                    "E208",
                    f"recursión no permitida: {cycle}",
                    info.decl.span,
                    help="las expresiones de Nomos son totales; usa comprensiones (all, sum…)",
                )
                return
            visiting.add(name)
            for callee in sorted(self.calls.get(name, ())):
                visit(callee, [*trail, name])
            visiting.discard(name)
            done.add(name)

        for name in sorted(self.calls):
            visit(name, [])

    def bind(self, scope: Scope, name: str, kind: str, ty: Ty, span: Span) -> None:
        if name in self.global_names() and name != "_":
            self.error(
                "E204",
                f"`{name}` oculta un nombre global del juego",
                span,
                help="usa otro nombre para la variable local",
            )
        scope.names[name] = Binding(kind, ty, span)

    # --- flow -----------------------------------------------------------------------------------

    def collect_nodes(self) -> None:
        def walk(nodes: list[ast.NodeDecl], parent: str | None) -> None:
            for node in nodes:
                if node.name in self.nodes:
                    self.error("E401", f"nodo duplicado: {node.name}", node.span)
                    continue
                self.nodes[node.name] = NodeInfo(node, parent)
                if node.kind == "phase":
                    walk([m for m in node.members if isinstance(m, ast.NodeDecl)], node.name)
                for member in node.members:
                    if isinstance(member, ast.ActionDecl):
                        self.actions.setdefault(member.name, []).append(member)

        walk(self.model.nodes, None)

    def check_flow(self) -> dict[str, Any]:
        m = self.model
        flow: dict[str, Any] = {}
        top = {n.name for n in m.nodes}
        if m.flow_span.source is None and not m.nodes:
            self.error(
                "E405",
                f"el juego {m.name} no tiene flow",
                m.decl.span,
                help="añade flow { start -> Nodo … } con los nodos de la partida",
            )
            return {"start": "Start", "nodes": []}
        if m.start is None:
            self.error(
                "E405",
                "el flow no tiene nodo inicial",
                m.flow_span if m.flow_span is not NO_SPAN else m.decl.span,
                help="añade 'start -> Nodo' dentro de flow { … }",
            )
            start = m.nodes[0].name if m.nodes else "Start"
        else:
            start = m.start.target
            if start not in top:
                self.error(
                    "E405",
                    f"el nodo inicial no existe en el nivel superior del flow: {start}",
                    m.start.span,
                    help=self.suggest(start, list(top)),
                )
            if m.start.setup is not None:
                ctx = Ctx("la preparación (start)", chance=True)
                setup = self.stmts(m.start.setup, Scope(), ctx)
                if setup:
                    flow["setup"] = setup
        flow["start"] = start
        if not m.nodes:
            self.error("E401", "el flow no tiene nodos", m.flow_span)
        flow["nodes"] = [self.node(n, in_phase=False) for n in m.nodes]
        return flow

    def node(self, node: ast.NodeDecl, in_phase: bool) -> dict[str, Any]:
        kind = node.kind
        out: dict[str, Any] = {"id": node.name, "kind": kind}
        if node.doc is not None:
            out["doc"] = node.doc.to_ir()
        members: dict[str, ast.Member] = {}
        lets: list[ast.LetMember] = []
        actions: list[ast.ActionDecl] = []
        transitions: list[ast.Transition] = []
        blocks: dict[str, ast.BlockMember] = {}
        effects: list[ast.Stmt] = []
        children: list[ast.NodeDecl] = []
        starts: list[ast.StartDecl] = []
        for member in node.members:
            match member:
                case ast.Member(key=key):
                    if key not in NODE_MEMBERS[kind]:
                        allowed = ", ".join(sorted(NODE_MEMBERS[kind])) or "ninguno"
                        self.error(
                            "E402",
                            f"'{key}' no es un miembro de un nodo {kind}",
                            member.span,
                            help=f"miembros de {kind}: {allowed}",
                        )
                    elif key in members:
                        self.error("E402", f"'{key}' repetido", member.span)
                    else:
                        members[key] = member
                case ast.LetMember():
                    lets.append(member)
                case ast.ActionDecl():
                    actions.append(member)
                case ast.Transition():
                    transitions.append(member)
                case ast.BlockMember(key=key):
                    allowed_blocks = {"simultaneous": {"resolve"}, "phase": {"on_enter", "on_exit"}}
                    if key not in allowed_blocks.get(kind, set()):
                        self.error("E402", f"'{key}' no se permite en un nodo {kind}", member.span)
                    elif key in blocks:
                        self.error("E402", f"'{key}' repetido", member.span)
                    else:
                        blocks[key] = member
                case ast.StartDecl():
                    starts.append(member)
                case ast.NodeDecl():
                    children.append(member)
                case ast.Stmt():
                    effects.append(member)
        if actions and kind not in ("decision", "simultaneous", "window"):
            self.error("E402", f"un nodo {kind} no tiene acciones", actions[0].span)
        if children and kind != "phase":
            self.error("E402", "solo una fase contiene otros nodos", children[0].span)
        if starts and kind != "phase":
            self.error("E402", "'start' solo va en el flow o en una fase", starts[0].span)
        if effects and kind not in ("chance", "auto"):
            self.error("E402", f"un nodo {kind} no tiene efectos sueltos", effects[0].span)
        if lets and kind != "terminal":
            self.error("E402", "'let' como miembro solo va en un terminal", lets[0].span)

        def required(key: str) -> ast.Member | None:
            if key not in members:
                self.error("E402", f"al nodo {kind} {node.name} le falta '{key}:'", node.span)
                return None
            return members[key]

        base = Ctx(f"el nodo {node.name}")
        match kind:
            case "decision":
                actor = required("actor")
                if actor is not None:
                    out["actor"] = self.expect(
                        self.expr(actor.value, Scope(), base, T.SEAT), T.SEAT, actor.value.span
                    )
                out["actions"] = self.actions_ir(actions, node, in_phase)
                tctx = replace(base, actor=True)
                out_t = self.transitions(transitions, tctx, in_phase, Scope())
                if out_t:
                    out["transitions"] = out_t
                elif not all(a.transitions for a in actions):
                    self.error(
                        "E404",
                        f"el nodo {node.name} no tiene salida",
                        node.span,
                        help="añade transiciones al nodo ('-> Destino') o a todas sus acciones",
                    )
            case "simultaneous":
                actors = required("actors")
                if actors is not None:
                    out["actors"] = self.seat_list(actors.value, base)
                out["actions"] = self.actions_ir(actions, node, in_phase)
                for a in actions:
                    if a.transitions:
                        self.error(
                            "E406",
                            "en un nodo simultáneo las acciones se resuelven juntas: las "
                            "transiciones van en el nodo",
                            a.transitions[0].span,
                        )
                if "resolve" in blocks:
                    resolve = self.stmts(blocks["resolve"].body, Scope(), base)
                    if resolve:
                        out["resolve"] = resolve
                out_t = self.transitions(transitions, base, in_phase, Scope())
                if not out_t:
                    self.error(
                        "E404", f"el nodo simultáneo {node.name} necesita transiciones", node.span
                    )
                out["transitions"] = out_t
            case "window":
                eligible = required("eligible")
                if eligible is not None:
                    out["eligible"] = self.seat_list(eligible.value, base)
                mode = required("mode")
                if mode is not None:
                    value = mode.value
                    if isinstance(value, ast.Name) and value.name in (
                        "priority",
                        "collect",
                        "race",
                    ):
                        out["mode"] = value.name
                    else:
                        self.error(
                            "E402",
                            "mode debe ser priority, collect o race",
                            value.span,
                        )
                        out["mode"] = "priority"
                if "order" in members:
                    out["order"] = self.seat_list(members["order"].value, base)
                for a in actions:
                    if a.name == "pass":
                        self.error(
                            "E406",
                            "'pass' está reservado: en una ventana pasar es implícito",
                            a.span,
                        )
                out["actions"] = self.actions_ir(actions, node, in_phase)
                out_t = self.transitions(transitions, base, in_phase, Scope())
                if not out_t:
                    self.error(
                        "E404",
                        f"la ventana {node.name} necesita transiciones (todos pueden pasar)",
                        node.span,
                    )
                out["transitions"] = out_t
            case "chance" | "auto":
                ctx = replace(base, chance=kind == "chance")
                block = self.stmts(effects, Scope(), ctx)
                if block or kind == "chance":
                    out["effects"] = block
                # Los `let` de los efectos no se ven en las transiciones (como en el motor).
                out_t = self.transitions(transitions, base, in_phase, Scope())
                if not out_t:
                    self.error(
                        "E404", f"el nodo {kind} {node.name} necesita una transición", node.span
                    )
                out["transitions"] = out_t
            case "phase":
                names = {c.name for c in children}
                if len(starts) != 1:
                    self.error(
                        "E405",
                        f"la fase {node.name} necesita exactamente un 'start -> Nodo'",
                        node.span,
                    )
                    out["start"] = children[0].name if children else node.name
                else:
                    out["start"] = starts[0].target
                    if starts[0].setup is not None:
                        self.error(
                            "E405",
                            "una fase no tiene preparación: usa on_enter { … }",
                            starts[0].span,
                        )
                    if starts[0].target not in names:
                        self.error(
                            "E405",
                            f"el inicio de la fase no es uno de sus nodos: {starts[0].target}",
                            starts[0].span,
                        )
                if not children:
                    self.error("E401", f"la fase {node.name} no tiene nodos", node.span)
                for key in ("on_enter", "on_exit"):
                    if key in blocks:
                        body = self.stmts(blocks[key].body, Scope(), base)
                        if body:
                            out[key] = body
                out["nodes"] = [self.node(c, in_phase=True) for c in children]
                out_t = self.transitions(transitions, base, in_phase, Scope())
                if out_t:
                    out["transitions"] = out_t
                elif any(_exits(c) for c in children):
                    self.error(
                        "E404",
                        f"un nodo de la fase {node.name} sale con '-> exit' pero la fase no tiene "
                        "transiciones",
                        node.span,
                    )
            case "terminal":
                if transitions:
                    self.error("E402", "un terminal no tiene transiciones", transitions[0].span)
                payoff = required("payoff")
                if payoff is not None:
                    out["payoff"] = self.with_lets(lets, payoff.value, T.PAYOFF, base)
                if "rank" in members:
                    out["rank"] = self.with_lets(lets, members["rank"].value, T.list_(T.INT), base)
        return out

    def with_lets(self, lets: list[ast.LetMember], value: ast.Expr, want: Ty, ctx: Ctx) -> Any:
        scope = Scope()
        bound: list[tuple[str, Any]] = []
        for let in lets:
            ir, ty = self.expr(let.value, scope, ctx)
            scope = scope.child()
            self.bind(scope, let.name, "local", ty, let.span)
            bound.append((let.name, ir))
        result = self.expect(self.expr(value, scope, ctx, want), want, value.span)
        for name, ir in reversed(bound):
            result = ["let", name, ir, result]
        return result

    def seat_list(self, e: ast.Expr, ctx: Ctx) -> Any:
        return self.expect(self.expr(e, Scope(), ctx), T.list_(T.SEAT), e.span)

    def actions_ir(
        self, actions: list[ast.ActionDecl], node: ast.NodeDecl, in_phase: bool
    ) -> list[dict[str, Any]]:
        if not actions:
            self.error("E402", f"el nodo {node.name} no tiene acciones", node.span)
        seen: set[str] = set()
        result = []
        for a in actions:
            if a.name in seen:
                self.error("E406", f"acción repetida en {node.name}: {a.name}", a.span)
            seen.add(a.name)
            result.append(self.action(a, in_phase))
        return result

    def action(self, a: ast.ActionDecl, in_phase: bool) -> dict[str, Any]:
        out: dict[str, Any] = {"name": a.name}
        if a.doc is not None:
            out["doc"] = a.doc.to_ir()
        ctx = Ctx(f"la acción {a.name}", actor=True)
        scope = Scope()
        params: list[dict[str, Any]] = []
        for p in a.params:
            if scope.lookup(p.name) is not None:
                self.error("E202", f"parámetro repetido: {p.name}", p.span)
            ty, domain = self.action_domain(p, scope, ctx)
            self.action_params.setdefault(a.name, {}).setdefault(p.name, []).append(ty)
            param: dict[str, Any] = {"name": p.name, "type": T.to_ir(ty), "domain": domain}
            if p.visibility is not None:
                param["visibility"] = self.visibility(p.visibility, True, p.name)
            if p.size_visibility is not None:
                param["size_visibility"] = self.visibility(p.size_visibility, True, p.name)
            params.append(param)
            scope = scope.child()
            self.bind(scope, p.name, "arg", ty, p.span)
        if params:
            out["params"] = params
        if a.requires is not None:
            out["requires"] = self.expect(
                self.expr(a.requires, scope, ctx, T.BOOL), T.BOOL, a.requires.span
            )
        effects = self.stmts(a.effects or [], scope.child(), ctx)
        if effects:
            out["effects"] = effects
        if a.visibility is not None:
            out["visibility"] = self.visibility(a.visibility, True, a.name)
        # Las transiciones de la acción ven sus parámetros, no los `let` de sus efectos.
        transitions = self.transitions(a.transitions, ctx, in_phase, scope)
        if transitions:
            out["transitions"] = transitions
        return out

    def action_domain(self, p: ast.ActionParam, scope: Scope, ctx: Ctx) -> tuple[Ty, Any]:
        declared = self.resolve_type(p.type) if p.type is not None else None
        if p.domain is not None:
            ir, coll = self.expr(p.domain, scope, ctx)
            item = T.elem(coll)
            if item is None:
                self.error(
                    "E305",
                    f"el dominio de {p.name} debe ser una colección finita, no `{coll}`",
                    p.domain.span,
                )
                item = T.UNKNOWN
            if declared is not None:
                if not T.assignable(item, declared):
                    self.error(
                        "E301",
                        f"el dominio de {p.name} contiene `{item}`, no `{declared}`",
                        p.domain.span,
                    )
                return declared, ir
            if T.contains_unknown(item) and not item.is_unknown:
                self.error(
                    "E305",
                    f"no se puede deducir el tipo de {p.name}: indica uno ({p.name}: Tipo in …)",
                    p.span,
                )
            return item, ir
        assert declared is not None
        if declared.kind == "enum":
            self.use(declared.name)
            return declared, ["enum_values", declared.name]
        if declared.kind == "Bool":
            return declared, ["list", ["const", False], ["const", True]]
        self.error(
            "E305",
            f"el parámetro {p.name}: {declared} necesita un dominio finito",
            p.span,
            help=f"por ejemplo: {p.name} in 1..6  ·  {p.name} in cells(board)",
        )
        return declared, ["list"]

    def transitions(
        self, transitions: list[ast.Transition], ctx: Ctx, in_phase: bool, scope: Scope
    ) -> list[dict[str, Any]]:
        result = []
        for k, t in enumerate(transitions):
            out: dict[str, Any] = {}
            if t.target == "exit":
                if not in_phase:
                    self.error("E403", "'-> exit' solo se permite dentro de una fase", t.span)
                out["to"] = "$exit"
            else:
                if t.target not in self.nodes:
                    self.error(
                        "E401",
                        f"nodo desconocido: {t.target}",
                        t.span,
                        help=self.suggest(t.target, list(self.nodes)),
                    )
                out["to"] = t.target
            if t.when is not None:
                out["when"] = self.expect(
                    self.expr(t.when, scope, ctx, T.BOOL), T.BOOL, t.when.span
                )
            elif k != len(transitions) - 1:
                self.error(
                    "E403",
                    "transición sin condición antes de otras: las siguientes serían inalcanzables",
                    t.span,
                    help="la transición sin 'when' va la última",
                )
            if t.effects:
                out["effects"] = self.stmts(t.effects, scope.child(), ctx)
            if t.doc is not None:
                out["doc"] = t.doc.to_ir()
            result.append(out)
        return result

    # --- sentencias -----------------------------------------------------------------------------

    def stmts(self, stmts: list[ast.Stmt], scope: Scope, ctx: Ctx) -> list[Any]:
        out: list[Any] = []
        for s in stmts:
            out.extend(self.stmt(s, scope, ctx))
        return out

    def stmt(self, s: ast.Stmt, scope: Scope, ctx: Ctx) -> list[Any]:
        match s:
            case ast.LetStmt(name=name, value=value):
                ir, ty = self.expr(value, scope, ctx)
                self.bind(scope, name, "local", ty, s.span)
                return [["let", name, ir]]
            case ast.Assign():
                return [self.assign(s, scope, ctx)]
            case ast.IfStmt(cond=cond, then=then, other=other):
                c = self.expect(self.expr(cond, scope, ctx, T.BOOL), T.BOOL, cond.span)
                then_ir = self.stmts(then, scope.child(), ctx)
                if other is None:
                    return [["if", c, then_ir]]
                return [["if", c, then_ir, self.stmts(other, scope.child(), ctx)]]
            case ast.ForStmt(var=var, iter=iterable, body=body):
                coll_ir, coll = self.expr(iterable, scope, ctx)
                item = self.iterable(coll, iterable.span)
                inner = scope.child()
                self.bind(inner, var, "local", item, s.span)
                return [["for", var, coll_ir, self.stmts(body, inner, ctx)]]
            case ast.MoveStmt():
                return [self.move(s, scope, ctx)]
            case ast.FlipStmt(selector=sel, zone=zone_e, face=face):
                zone_ir, zone_ty = self.lvalue(zone_e, scope, ctx)
                self.zone_type(zone_ty, zone_e.span)
                sel_ir = self.selector(sel, zone_ty, scope, ctx)
                face_e = face.inner if isinstance(face, ast.Paren) else face
                face_ir = self.expect(self.expr(face_e, scope, ctx, T.BOOL), T.BOOL, face.span)
                return [["flip", zone_ir, sel_ir, face_ir]]
            case ast.ShuffleStmt(zone=zone_e):
                self.require_chance(ctx, "shuffle", s.span)
                zone_ir, zone_ty = self.lvalue(zone_e, scope, ctx)
                if zone_ty.kind == "bag":
                    self.error("E302", "no se puede barajar una bolsa: no tiene orden", zone_e.span)
                elif zone_ty.kind != "zone" and not zone_ty.is_unknown:
                    self.error("E301", f"shuffle espera una Zone, no `{zone_ty}`", zone_e.span)
                return [["shuffle", zone_ir]]
            case ast.DealStmt():
                return [self.deal(s, scope, ctx)]
            case ast.RevealStmt(value=value, to=to, label=label):
                v_ir, _ = self.expr(value, scope, ctx)
                if to is None:
                    seats: Any = ["seats"]
                else:
                    seats_ir, seats_ty = self.expr(to, scope, ctx)
                    if T.assignable(seats_ty, T.SEAT) and seats_ty.kind != "list":
                        seats = ["list", seats_ir]
                    else:
                        seats = self.expect((seats_ir, seats_ty), T.list_(T.SEAT), to.span)
                out: list[Any] = ["reveal", v_ir, seats]
                if label is not None:
                    out.append(label.to_ir())
                return [out]
            case ast.EmitStmt(name=name, fields=fields, visibility=vis):
                names = [k for k, _ in fields]
                if len(set(names)) != len(names):
                    self.error("E202", "campos repetidos en emit", s.span)
                payload = {k: self.expr(v, scope, ctx)[0] for k, v in fields}
                out = ["emit", name, payload]
                if vis is not None:
                    out.append(self.visibility(vis, True, f"el evento {name}"))
                return [out]
            case ast.RewardStmt(amount=amount, seat=seat_e):
                seat_ir = self.expect(self.expr(seat_e, scope, ctx), T.SEAT, seat_e.span)
                amount_ir = self.expect(self.expr(amount, scope, ctx), T.REAL, amount.span)
                return [["reward", seat_ir, amount_ir]]
            case ast.FailStmt(message=message):
                return [["fail", message.to_ir()]]
        self.error("E110", "sentencia no válida", s.span)
        return []

    def require_chance(self, ctx: Ctx, what: str, span: Span) -> None:
        if not ctx.chance:
            self.error(
                "E306",
                f"'{what}' es aleatorio: solo se permite en nodos chance y en start {{ … }}",
                span,
                help="el azar es explícito: mueve esta sentencia a un nodo chance",
            )

    def assign(self, s: ast.Assign, scope: Scope, ctx: Ctx) -> Any:
        value = s.value
        if (
            s.op == "="
            and isinstance(value, ast.Call)
            and value.func in RANDOM_CALLS
            and (value.func != "random" or len(value.args) == 1)
        ):
            return self.random_assign(s, value, scope, ctx)
        target_ir, target_ty = self.lvalue(s.target, scope, ctx)
        if s.op == "=":
            v = self.expect(self.expr(value, scope, ctx, target_ty), target_ty, value.span)
            return ["assign", target_ir, v]
        v_ir, v_ty = self.expr(value, scope, ctx)
        if target_ty.kind == "list" or (target_ty.kind in ("set", "zone", "bag") and s.op != "*="):
            if s.op == "*=":
                self.error("E302", "'*=' no se aplica a colecciones", s.span)
                return ["assign", target_ir, target_ir]
            op = "concat" if s.op == "+=" else "difference"
            if target_ty.kind != "list":
                self.error(
                    "E302",
                    f"'{s.op}' en `{target_ty}`: usa move para mover elementos entre zonas",
                    s.span,
                )
            if not T.assignable(v_ty, T.list_(target_ty.inner)):
                return self.error(
                    "E301",
                    f"'{s.op}' en una lista necesita otra lista de `{target_ty.inner}`, "
                    f"no `{v_ty}`",
                    value.span,
                    help=f"por ejemplo: xs {s.op} [x]",
                )[0]
            return ["assign", target_ir, [op, target_ir, v_ir]]
        op = {"+=": "add", "-=": "sub", "*=": "mul"}[s.op]
        if not (target_ty.is_numeric or target_ty.is_unknown):
            return self.error("E302", f"'{s.op}' necesita un número, no `{target_ty}`", s.span)[0]
        result_ty = T.join(target_ty, v_ty) or T.UNKNOWN
        if not v_ty.is_numeric and not v_ty.is_unknown:
            self.error("E301", f"'{s.op}' necesita un número, no `{v_ty}`", value.span)
        elif not T.assignable(result_ty, target_ty):
            self.error(
                "E301",
                f"el resultado es `{result_ty}` y la variable es `{target_ty}`",
                s.span,
            )
        return ["assign", target_ir, [op, target_ir, v_ir]]

    def random_assign(self, s: ast.Assign, call: ast.Call, scope: Scope, ctx: Ctx) -> Any:
        self.require_chance(ctx, f"{call.func}(…)", call.span)
        target_ir, target_ty = self.lvalue(s.target, scope, ctx)
        op = RANDOM_CALLS[call.func]
        if len(call.args) != 1:
            return self.error("E207", f"{call.func} recibe un argumento", call.span)[0]
        arg = call.args[0]
        if op == "roll":
            n = self.expect(self.expr(arg, scope, ctx, T.INT), T.INT, arg.span)
            if not T.assignable(T.INT, target_ty):
                self.error("E301", f"roll da un Int; la variable es `{target_ty}`", s.span)
            return ["roll", target_ir, n]
        if op == "random_choice":
            coll_ir, coll = self.expr(arg, scope, ctx)
            item = self.iterable(coll, arg.span)
            if not T.assignable(item, target_ty):
                self.error(
                    "E301", f"random da un `{item}`; la variable es `{target_ty}`", call.span
                )
            return ["random_choice", target_ir, coll_ir]
        dist_ir, dist = self.expr(arg, scope, ctx)
        item = T.elem(dist)
        ok = (
            dist.kind == "list"
            and item is not None
            and item.kind == "tuple"
            and len(item.args) == 2
            and T.assignable(item.args[1], T.REAL)
        )
        if not ok and not dist.is_unknown:
            self.error(
                "E301",
                f"sample espera una lista de pares (valor, probabilidad), no `{dist}`",
                arg.span,
                help="por ejemplo: sample([(Sun, 1/2), (Rain, 1/2)])",
            )
        elif (
            item is not None and item.kind == "tuple" and not T.assignable(item.args[0], target_ty)
        ):
            self.error(
                "E301", f"sample da un `{item.args[0]}`; la variable es `{target_ty}`", call.span
            )
        return ["sample", target_ir, dist_ir]

    def lvalue(self, e: ast.Expr, scope: Scope, ctx: Ctx) -> Typed:
        match e:
            case ast.Paren(inner=inner):
                return self.lvalue(inner, scope, ctx)
            case ast.Name(name=name):
                if name in self.state:
                    if scope.lookup(name) is not None:
                        return self.error("E307", f"`{name}` es una variable local", e.span)
                    return ["var", name], self.state[name]
                return self.error(
                    "E307",
                    f"solo se puede modificar el estado; `{name}` no es una variable de estado",
                    e.span,
                    help=self.suggest(name, list(self.state)),
                )
            case ast.Index(target=target, index=index):
                base_ir, base_ty = self.lvalue(target, scope, ctx)
                return self.index_typed(base_ir, base_ty, index, scope, ctx, e.span)
            case ast.Field(target=target, name=name):
                base_ir, base_ty = self.lvalue(target, scope, ctx)
                return self.field_typed(base_ir, base_ty, name, e.span)
        return self.error(
            "E307",
            "solo se puede modificar el estado: una variable, un índice o un campo",
            e.span,
        )

    def zone_type(self, ty: Ty, span: Span) -> Ty:
        if ty.kind in ("zone", "bag"):
            return ty.inner
        if not ty.is_unknown:
            self.error("E301", f"se esperaba una Zone o una Bag, no `{ty}`", span)
        return T.UNKNOWN

    def selector(self, sel: ast.Selector, zone_ty: Ty, scope: Scope, ctx: Ctx) -> Any:
        item = zone_ty.inner if zone_ty.kind in ("zone", "bag") else T.UNKNOWN
        if sel.kind == "all":
            return ["all"]
        assert sel.expr is not None
        if sel.kind in ("top", "bottom", "at"):
            if zone_ty.kind == "bag":
                self.error(
                    "E302",
                    f"'{sel.kind}' necesita una zona ordenada: las bolsas no tienen orden",
                    sel.span,
                    help="en una bolsa usa 'all' o los valores concretos",
                )
            n = self.expect(self.expr(sel.expr, scope, ctx, T.INT), T.INT, sel.expr.span)
            return [sel.kind, n]
        ir, ty = self.expr(sel.expr, scope, ctx, item)
        if T.assignable(ty, item):
            return ["value", ir]
        many = T.elem(ty)
        if many is not None and T.assignable(many, item):
            return ["values", ir]
        self.error(
            "E301",
            f"se esperaba un `{item}` o una lista de `{item}`, no `{ty}`",
            sel.expr.span,
        )
        return ["value", ir]

    def move(self, s: ast.MoveStmt, scope: Scope, ctx: Ctx) -> Any:
        src_ir, src_ty = self.lvalue(s.source, scope, ctx)
        dst_ir, dst_ty = self.lvalue(s.dest, scope, ctx)
        src_item = self.zone_type(src_ty, s.source.span)
        dst_item = self.zone_type(dst_ty, s.dest.span)
        if not T.assignable(src_item, dst_item):
            self.error(
                "E301",
                f"no se pueden mover `{src_item}` a una zona de `{dst_item}`",
                s.span,
            )
        out = ["move", src_ir, dst_ir, self.selector(s.selector, src_ty, scope, ctx)]
        if s.position is not None:
            if dst_ty.kind == "bag":
                self.error("E302", "una bolsa no tiene arriba ni abajo", s.span)
            out.append(s.position)
        return out

    def deal(self, s: ast.DealStmt, scope: Scope, ctx: Ctx) -> Any:
        src_ir, src_ty = self.lvalue(s.source, scope, ctx)
        if src_ty.kind == "bag":
            self.error(
                "E302",
                "se reparte desde una zona ordenada (un mazo), no desde una bolsa",
                s.source.span,
            )
        src_item = self.zone_type(src_ty, s.source.span)
        hands_ir, hands_ty = self.lvalue(s.dest, scope, ctx)
        if hands_ty.kind != "per_player" and not hands_ty.is_unknown:
            return self.error(
                "E301",
                f"'deal … to each' necesita una zona por jugador (per_player), no `{hands_ty}`",
                s.dest.span,
            )[0]
        hand_ty = hands_ty.inner if hands_ty.kind == "per_player" else T.UNKNOWN
        hand_item = self.zone_type(hand_ty, s.dest.span)
        if not T.assignable(src_item, hand_item):
            self.error(
                "E301", f"no se pueden repartir `{src_item}` a manos de `{hand_item}`", s.span
            )
        taken = _locals_in(src_ir) | _locals_in(hands_ir)
        top1 = ["top", ["const", 1]]
        if s.count is None:
            i = _fresh("i", taken)
            last = ["sub", ["size", src_ir], ["const", 1]]
            who = ["mod", ["local", i], ["param", "num_players"]]
            body = [["move", src_ir, ["index", hands_ir, who], top1]]
            return ["for", i, ["range", ["const", 0], last], body]
        count_ir = self.expect(self.expr(s.count, scope, ctx, T.INT), T.INT, s.count.span)
        seat = _fresh("s", taken)
        each = [
            "for",
            seat,
            ["seats"],
            [["move", src_ir, ["index", hands_ir, ["local", seat]], top1]],
        ]
        if isinstance(s.count, ast.IntLit) and s.count.value == 1:
            return each
        k = _fresh("k", taken | {seat})
        return ["for", k, ["range", ["const", 1], count_ir], [each]]

    # --- expresiones ----------------------------------------------------------------------------

    def iterable(self, ty: Ty, span: Span) -> Ty:
        item = T.elem(ty)
        if item is None:
            self.error("E303", f"no se puede recorrer un `{ty}`", span)
            return T.UNKNOWN
        return item

    def expr(self, e: ast.Expr, scope: Scope, ctx: Ctx, expected: Ty | None = None) -> Typed:
        method = getattr(self, "e_" + type(e).__name__, None)
        if method is None:
            return self.error("E110", f"expresión no válida: {type(e).__name__}", e.span)
        return method(e, scope, ctx, expected)

    def e_Paren(self, e: ast.Paren, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
        return self.expr(e.inner, scope, ctx, expected)

    def e_IntLit(self, e: ast.IntLit, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
        return ["const", e.value], T.INT

    def e_DecimalLit(self, e: ast.DecimalLit, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
        return ["rat", e.value.numerator, e.value.denominator], T.REAL

    def e_StrLit(self, e: ast.StrLit, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
        return ["const", e.value], T.TEXT

    def e_BoolLit(self, e: ast.BoolLit, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
        return ["const", e.value], T.BOOL

    def e_NoneLit(self, e: ast.NoneLit, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
        if expected is not None and expected.kind == "option":
            return ["const", None], expected
        return ["const", None], T.NONE

    def e_Name(self, e: ast.Name, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
        name = e.name
        binding = scope.lookup(name)
        if binding is not None:
            return [binding.kind, name], binding.ty
        if ctx.test and name in ("payoff", "active"):
            return ["local", name], T.PAYOFF if name == "payoff" else T.list_(T.SEAT)
        if ctx.module and (name in self.state or name in self.params):
            what = "el estado" if name in self.state else "las opciones"
            return self.error(
                "E205",
                f"una función de módulo no ve {what} del juego (`{name}`)",
                e.span,
                help="pásalo como argumento",
            )
        if name in self.state:
            if not ctx.reads_state:
                return self.error(
                    "E205",
                    f"en {ctx.where} no se puede leer el estado (`{name}`)",
                    e.span,
                    help="aquí solo se pueden usar parámetros y constantes",
                )
            return ["var", name], self.state[name]
        if name in self.params:
            ty, index = self.params[name]
            if ctx.params_upto is not None and index >= ctx.params_upto:
                return self.error(
                    "E205",
                    f"el parámetro `{name}` se declara después: un valor por defecto solo puede "
                    "usar parámetros anteriores",
                    e.span,
                )
            return ["param", name], ty
        match name:
            case "num_players":
                return ["param", "num_players"], T.INT
            case "seats":
                return ["seats"], T.list_(T.SEAT)
            case "actor":
                if not ctx.actor:
                    return self.error(
                        "E205",
                        "'actor' solo existe en acciones y en transiciones de nodos decision",
                        e.span,
                    )
                return ["actor"], T.SEAT
            case "viewer" | "face_up":
                if not ctx.visibility:
                    return self.error(
                        "E205", f"'{name}' solo existe en políticas de visibilidad", e.span
                    )
                if name == "viewer":
                    return ["viewer"], T.SEAT
                return ["item_face_up"], T.BOOL
            case "owner":
                if not ctx.owned:
                    return self.error(
                        "E205",
                        "'owner' solo existe en la visibilidad y en la inicialización per_player",
                        e.span,
                    )
                return ["owner"], T.SEAT
        if name in self.enum_values:
            owners = self.enum_values[name]
            if expected is not None and expected.kind == "enum" and expected.name in owners:
                owners = [expected.name]
            elif expected is not None and expected.kind == "option":
                inner = expected.inner
                if inner.kind == "enum" and inner.name in owners:
                    owners = [inner.name]
            if len(owners) > 1:
                options = ", ".join(f"{o}.{name}" for o in owners)
                return self.error(
                    "E203",
                    f"`{name}` es ambiguo: existe en varios enumerados",
                    e.span,
                    help=f"escribe uno de: {options}",
                )
            self.use(owners[0])
            return ["enum", owners[0], name], T.enum_(owners[0])
        if name in self.functions:
            return self.error("E201", f"`{name}` es una función: llámala con {name}(…)", e.span)
        if name in self.types:
            return self.error(
                "E201",
                f"`{name}` es un tipo, no un valor",
                e.span,
                help=f"para sus valores usa {name}.values" if name in self.types else None,
            )
        if name in self.nodes:
            return self.error(
                "E201", f"`{name}` es un nodo; para saber si está activo usa at({name})", e.span
            )
        candidates = [
            *scope.visible(),
            *self.state,
            *self.params,
            *CONTEXT_VALUES,
            *self.enum_values,
        ]
        return self.error(
            "E201",
            f"nombre desconocido: `{name}`",
            e.span,
            "no está declarado",
            help=self.suggest(name, candidates),
        )

    def e_Unary(self, e: ast.Unary, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
        if e.op == "not":
            x = self.expect(self.expr(e.operand, scope, ctx, T.BOOL), T.BOOL, e.operand.span)
            return ["not", x], T.BOOL
        operand = e.operand
        if isinstance(operand, ast.IntLit):
            return ["const", -operand.value], T.INT
        if isinstance(operand, ast.DecimalLit):
            v = -operand.value
            return ["rat", v.numerator, v.denominator], T.REAL
        ir, ty = self.expr(operand, scope, ctx)
        if not (ty.is_numeric or ty.is_unknown):
            return self.error("E302", f"el signo '-' necesita un número, no `{ty}`", e.span)
        return ["neg", ir], (T.INT if ty.kind == "Seat" else ty)

    def e_Binary(self, e: ast.Binary, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
        op = e.op
        if op in ("and", "or"):
            args = self.flatten(
                e,
                op,
                scope,
                ctx,
                lambda x: (self.expect(self.expr(x, scope, ctx, T.BOOL), T.BOOL, x.span), T.BOOL),
            )
            return [op, *args], T.BOOL
        if op in ("==", "!="):
            left_ir, left = self.expr(e.left, scope, ctx)
            right_ir, right = self.expr(e.right, scope, ctx, left)
            if not T.comparable(left, right):
                self.error(
                    "E301",
                    f"no se puede comparar `{left}` con `{right}`",
                    e.span,
                    help=_compare_help(left, right),
                )
            return ["eq" if op == "==" else "ne", left_ir, right_ir], T.BOOL
        if op in ("<", "<=", ">", ">="):
            left_ir, left = self.expr(e.left, scope, ctx)
            right_ir, right = self.expr(e.right, scope, ctx, left)
            if not T.ordered(left, right):
                self.error(
                    "E302",
                    f"no se puede ordenar `{left}` y `{right}`",
                    e.span,
                    help="se ordenan números, textos y valores de un mismo enumerado",
                )
            name = {"<": "lt", "<=": "le", ">": "gt", ">=": "ge"}[op]
            return [name, left_ir, right_ir], T.BOOL
        if op in ("in", "not in"):
            coll_ir, coll = self.expr(e.right, scope, ctx)
            item_ir, item = self.expr(e.left, scope, ctx, T.elem(coll))
            if coll.kind == "Text":
                self.expect((item_ir, item), T.TEXT, e.left.span)
            else:
                inner = self.iterable(coll, e.right.span)
                if not T.comparable(item, inner):
                    self.error("E301", f"`{item}` nunca está en una colección de `{inner}`", e.span)
            contains = ["contains", coll_ir, item_ir]
            return (contains if op == "in" else ["not", contains]), T.BOOL
        return self.arithmetic(e, scope, ctx, expected)

    def flatten(
        self,
        e: ast.Binary,
        op: str,
        scope: Scope,
        ctx: Ctx,
        each: Callable[[ast.Expr], Typed],
    ) -> list[Any]:
        """Operandos de una cadena `a op b op c` sin paréntesis (asociativa por la izquierda)."""
        chain: list[ast.Expr] = [e.right]
        left = e.left
        while isinstance(left, ast.Binary) and left.op == e.op:
            chain.append(left.right)
            left = left.left
        chain.append(left)
        return [each(x)[0] for x in reversed(chain)]

    def arithmetic(self, e: ast.Binary, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
        op = e.op
        left_ir, left = self.expr(e.left, scope, ctx, expected if op in ("+", "-") else None)
        if op in ("+", "-") and left.kind in ("list", "set"):
            right_ir, right = self.expr(e.right, scope, ctx, left)
            if op == "+":
                if left.kind != "list" or not T.assignable(right, T.list_(left.inner)):
                    return self.error(
                        "E302",
                        f"'+' une listas del mismo tipo; no se puede `{left}` + `{right}`",
                        e.span,
                        help="para añadir un elemento: xs + [x] o append(xs, x)",
                    )
                return ["concat", left_ir, right_ir], left
            if T.elem(right) is None:
                return self.error("E302", f"'-' resta una colección, no `{right}`", e.right.span)
            return ["difference", left_ir, right_ir], T.list_(left.inner)
        right_ir, right = self.expr(e.right, scope, ctx)
        for side, ty in ((e.left, left), (e.right, right)):
            if not (ty.is_numeric or ty.is_unknown):
                return self.error(
                    "E302",
                    f"'{op}' necesita números; `{ty}` no lo es",
                    side.span,
                    help="'+' y '-' también funcionan entre listas" if op in "+-" else None,
                )
        result = T.join(left, right) or T.UNKNOWN
        if result.kind == "Seat":
            result = T.INT
        match op:
            case "+" | "*":
                name = "add" if op == "+" else "mul"
                # a + b + c → ["add", a, b, c], salvo que haya paréntesis: (a + b) + c
                if _same_op(e.left, op) and isinstance(left_ir, list) and left_ir[0] == name:
                    return [*left_ir, right_ir], result
                return [name, left_ir, right_ir], result
            case "-":
                return ["sub", left_ir, right_ir], result
            case "/":
                return ["div", left_ir, right_ir], T.REAL
            case "div":
                self.integers(left, right, "div", e.span)
                return ["idiv", left_ir, right_ir], T.INT
            case "%":
                self.integers(left, right, "%", e.span)
                return ["mod", left_ir, right_ir], T.INT
        return self.error("E302", f"operador desconocido: {op}", e.span)

    def integers(self, left: Ty, right: Ty, op: str, span: Span) -> None:
        for ty in (left, right):
            if ty.kind == "Real":
                self.error("E302", f"'{op}' trabaja con enteros, no con `Real`", span)
                return

    def e_RangeExpr(self, e: ast.RangeExpr, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
        lo = self.expect(self.expr(e.lo, scope, ctx, T.INT), T.INT, e.lo.span)
        hi = self.expect(self.expr(e.hi, scope, ctx, T.INT), T.INT, e.hi.span)
        if not e.inclusive:
            hi = ["sub", hi, ["const", 1]]
        return ["range", lo, hi], T.list_(T.INT)

    def e_IfExpr(self, e: ast.IfExpr, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
        cond = self.expect(self.expr(e.cond, scope, ctx, T.BOOL), T.BOOL, e.cond.span)
        then_ir, then = self.expr(e.then, scope, ctx, expected)
        other_ir, other = self.expr(e.other, scope, ctx, expected or then)
        result = T.join(then, other)
        if result is None:
            return self.error(
                "E301",
                f"las dos ramas del if tienen tipos incompatibles: `{then}` y `{other}`",
                e.span,
            )
        return ["if", cond, then_ir, other_ir], result

    def e_Call(self, e: ast.Call, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
        from gamehub.lang.builtins import BUILTINS

        if e.func == "at":
            if len(e.args) != 1 or not isinstance(e.args[0], ast.Name):
                return self.error("E207", "at(Nodo) recibe el nombre de un nodo", e.span)
            node = e.args[0].name
            if node not in self.nodes:
                return self.error(
                    "E401",
                    f"nodo desconocido: {node}",
                    e.args[0].span,
                    help=self.suggest(node, list(self.nodes)),
                )
            return ["at", node], T.BOOL
        if e.func in RANDOM_CALLS:
            return self.error(
                "E306",
                f"{e.func}(…) es aleatorio: solo puede ser el lado derecho de una asignación "
                "en un nodo chance",
                e.span,
                help=f"por ejemplo: x = {e.func}(…)",
            )
        if e.func in self.functions:
            info = self.functions[e.func]
            self.use(e.func)
            if self.owner in self.functions:
                self.calls.setdefault(self.owner, set()).add(e.func)
            if len(e.args) != len(info.params):
                return self.error(
                    "E207",
                    f"{e.func} espera {len(info.params)} argumento(s) y recibe {len(e.args)}",
                    e.span,
                )
            args = [
                self.expect(self.expr(a, scope, ctx, pty), pty, a.span, f"argumento {pname}")
                for a, (pname, pty) in zip(e.args, info.params, strict=True)
            ]
            return ["call", e.func, *args], info.returns
        builtin = BUILTINS.get(e.func)
        if builtin is None:
            candidates = [*self.functions, *BUILTINS]
            return self.error(
                "E207",
                f"función desconocida: {e.func}",
                e.span,
                help=self.suggest(e.func, candidates),
            )
        return builtin(self, e, scope, ctx, expected)

    def e_Aggregate(self, e: ast.Aggregate, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
        from gamehub.lang.builtins import aggregate

        return aggregate(self, e.func, e.var, e.coll, e.body, scope, ctx, e.span)

    def e_Index(self, e: ast.Index, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
        base_ir, base_ty = self.expr(e.target, scope, ctx)
        return self.index_typed(base_ir, base_ty, e.index, scope, ctx, e.span)

    def index_typed(
        self, base_ir: Any, base: Ty, index: ast.Expr, scope: Scope, ctx: Ctx, span: Span
    ) -> Typed:
        kind = base.kind
        if kind == "unknown":
            return ["index", base_ir, self.expr(index, scope, ctx)[0]], T.UNKNOWN
        if kind == "list":
            key = self.expect(self.expr(index, scope, ctx, T.INT), T.INT, index.span)
            return ["index", base_ir, key], base.inner
        if kind == "per_player":
            key = self.expect(self.expr(index, scope, ctx, T.SEAT), T.SEAT, index.span)
            return ["index", base_ir, key], base.inner
        if kind == "map":
            k = base.args[0]
            key = self.expect(self.expr(index, scope, ctx, k), k, index.span)
            return ["index", base_ir, key], base.args[1]
        if kind == "grid":
            key = self.expect(self.expr(index, scope, ctx, T.CELL), T.CELL, index.span)
            return ["index", base_ir, key], base.inner
        if kind == "Cell":  # una casilla es el par (fila, columna)
            base, kind = T.tuple_(T.INT, T.INT), "tuple"
        if kind == "tuple":
            if not isinstance(index, ast.IntLit) or not 0 <= index.value < len(base.args):
                return self.error(
                    "E301",
                    f"una tupla se indexa con un entero constante entre 0 y {len(base.args) - 1}",
                    index.span,
                )
            return ["index", base_ir, ["const", index.value]], base.args[index.value]
        if kind in ("zone", "bag"):
            return self.error(
                "E302",
                f"no se indexa una {kind}: usa items(z)[i] o top(z)",
                span,
            )
        return self.error("E302", f"no se puede indexar un `{base}`", span)

    def e_Slice(self, e: ast.Slice, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
        base_ir, base = self.expr(e.target, scope, ctx)
        if base.kind != "list" and not base.is_unknown:
            hint = "usa items(z)[a:b]" if base.kind in ("zone", "bag") else None
            return self.error(
                "E302", f"solo se pueden cortar listas, no `{base}`", e.span, help=hint
            )
        lo = (
            self.expect(self.expr(e.lo, scope, ctx, T.INT), T.INT, e.lo.span)
            if e.lo is not None
            else ["const", 0]
        )
        hi = (
            self.expect(self.expr(e.hi, scope, ctx, T.INT), T.INT, e.hi.span)
            if e.hi is not None
            else ["len", base_ir]
        )
        return ["slice", base_ir, lo, hi], base

    def e_Field(self, e: ast.Field, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
        target = e.target
        if (
            isinstance(target, ast.Name)
            and target.name in self.types
            and scope.lookup(target.name) is None
        ):
            info = self.types[target.name]
            self.use(target.name)
            if not isinstance(info.decl, ast.EnumDecl):
                return self.error(
                    "E209", f"{target.name} es un struct: no tiene valores con nombre", e.span
                )
            if e.name == "values":
                return ["enum_values", target.name], T.list_(T.enum_(target.name))
            if e.name not in info.decl.values:
                return self.error(
                    "E209",
                    f"{target.name} no tiene el valor {e.name}",
                    e.span,
                    help=self.suggest(e.name, info.decl.values),
                )
            return ["enum", target.name, e.name], T.enum_(target.name)
        base_ir, base = self.expr(target, scope, ctx)
        return self.field_typed(base_ir, base, e.name, e.span)

    def field_typed(self, base_ir: Any, base: Ty, name: str, span: Span) -> Typed:
        if base.is_unknown:
            return ["field", base_ir, name], T.UNKNOWN
        if base.kind != "struct":
            return self.error("E209", f"`{base}` no tiene campos", span)
        fields = self.types[base.name].fields
        if name not in fields:
            return self.error(
                "E209",
                f"{base.name} no tiene el campo {name}",
                span,
                help=self.suggest(name, list(fields)),
            )
        return ["field", base_ir, name], fields[name]

    def e_ListLit(self, e: ast.ListLit, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
        hint = T.elem(expected) if expected is not None else None
        items: list[Any] = []
        item_ty = hint if hint is not None and not e.items else T.UNKNOWN
        for x in e.items:
            ir, ty = self.expr(x, scope, ctx, hint)
            joined = T.join(item_ty, ty)
            if joined is None:
                self.error(
                    "E301",
                    f"elementos de tipos incompatibles en la lista: `{item_ty}` y `{ty}`",
                    x.span,
                )
            else:
                item_ty = joined
            items.append(ir)
        if hint is not None and T.assignable(item_ty, hint):
            item_ty = hint if not hint.is_unknown else item_ty
        return ["list", *items], T.list_(item_ty)

    def e_TupleLit(self, e: ast.TupleLit, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
        hints: list[Ty | None] = [None] * len(e.items)
        if expected is not None and expected.kind == "tuple" and len(expected.args) == len(e.items):
            hints = list(expected.args)
        typed = [self.expr(x, scope, ctx, h) for x, h in zip(e.items, hints, strict=True)]
        return ["tuple", *(ir for ir, _ in typed)], T.tuple_(*(ty for _, ty in typed))

    def e_Comprehension(
        self, e: ast.Comprehension, scope: Scope, ctx: Ctx, expected: Ty | None
    ) -> Typed:
        return self.comprehension(e.element, e.clauses, scope, ctx)

    def comprehension(
        self, element: ast.Expr, clauses: list[ast.CompFor], scope: Scope, ctx: Ctx
    ) -> Typed:
        clause = clauses[0]
        coll_ir, coll = self.expr(clause.iter, scope, ctx)
        item = self.iterable(coll, clause.iter.span)
        inner = scope.child()
        self.bind(inner, clause.var, "local", item, clause.span)
        if clause.conds:
            conds = [
                self.expect(self.expr(c, inner, ctx, T.BOOL), T.BOOL, c.span) for c in clause.conds
            ]
            cond = conds[0] if len(conds) == 1 else ["and", *conds]
            coll_ir = ["filter", clause.var, coll_ir, cond]
        if len(clauses) == 1:
            if clause.conds and isinstance(element, ast.Name) and element.name == clause.var:
                return coll_ir, T.list_(item)
            body_ir, body = self.expr(element, inner, ctx)
            return ["map", clause.var, coll_ir, body_ir], T.list_(body)
        rest_ir, rest = self.comprehension(element, clauses[1:], inner, ctx)
        return ["flat_map", clause.var, coll_ir, rest_ir], rest

    def e_StructLit(self, e: ast.StructLit, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
        info = self.types.get(e.type_name)
        if info is None or not isinstance(info.decl, ast.StructDecl):
            return self.error(
                "E209",
                f"struct desconocido: {e.type_name}",
                e.span,
                help=self.suggest(
                    e.type_name,
                    [n for n, i in self.types.items() if isinstance(i.decl, ast.StructDecl)],
                ),
            )
        self.use(e.type_name)
        given = [k for k, _ in e.fields]
        missing = [f for f in info.fields if f not in given]
        extra = [f for f in given if f not in info.fields]
        if missing or extra or len(set(given)) != len(given):
            detail = []
            if missing:
                detail.append("faltan " + ", ".join(missing))
            if extra:
                detail.append("sobran " + ", ".join(extra))
            return self.error(
                "E209",
                f"{e.type_name} necesita exactamente los campos {', '.join(info.fields)}"
                + (f" ({'; '.join(detail)})" if detail else ""),
                e.span,
            )
        fields = {
            k: self.expect(self.expr(v, scope, ctx, info.fields[k]), info.fields[k], v.span, k)
            for k, v in e.fields
        }
        return ["struct", e.type_name, fields], T.struct_(e.type_name)

    def e_LetBlock(self, e: ast.LetBlock, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
        inner = scope
        bound: list[tuple[str, Any]] = []
        for name, value in e.lets:
            ir, ty = self.expr(value, inner, ctx)
            inner = inner.child()
            self.bind(inner, name, "local", ty, value.span)
            bound.append((name, ir))
        result_ir, result = self.expr(e.result, inner, ctx, expected)
        for name, ir in reversed(bound):
            result_ir = ["let", name, ir, result_ir]
        return result_ir, result

    def e_CaseExpr(self, e: ast.CaseExpr, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
        arms: list[list[Any]] = []
        result: Ty = T.UNKNOWN
        for cond, value in e.arms:
            c = self.expect(self.expr(cond, scope, ctx, T.BOOL), T.BOOL, cond.span)
            v_ir, v = self.expr(value, scope, ctx, expected)
            result = self.join_arm(result, v, value.span)
            arms.append([c, v_ir])
        d_ir, d = self.expr(e.default, scope, ctx, expected)
        result = self.join_arm(result, d, e.default.span)
        return ["case", arms, d_ir], result

    def join_arm(self, acc: Ty, ty: Ty, span: Span) -> Ty:
        joined = T.join(acc, ty)
        if joined is None:
            self.error("E301", f"los casos tienen tipos incompatibles: `{acc}` y `{ty}`", span)
            return acc
        return joined

    def e_MatchExpr(self, e: ast.MatchExpr, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
        subject = e.subject
        while isinstance(subject, ast.Paren):
            subject = subject.inner
        if isinstance(subject, ast.TupleLit):
            parts = [self.expr(x, scope, ctx) for x in subject.items]
            whole: Typed | None = None
        else:
            whole = self.expr(subject, scope, ctx)
            ir, ty = whole
            if ty.kind == "tuple":
                parts = [(["index", ir, ["const", i]], t) for i, t in enumerate(ty.args)]
            else:
                parts = [whole]
        width = len(parts)
        conds: list[Any | None] = []
        keys: list[list[str | None]] = []
        result: Ty = T.UNKNOWN
        values: list[Any] = []
        for pattern, value in e.arms:
            cond, key = self.pattern(pattern, parts, width, scope, ctx)
            conds.append(cond)
            keys.append(key)
            v_ir, v = self.expr(value, scope, ctx, expected)
            result = self.join_arm(result, v, value.span)
            values.append(v_ir)
        for i, cond in enumerate(conds[:-1]):
            if cond is None:
                self.error(
                    "E304",
                    "este caso cubre todo: los siguientes son inalcanzables",
                    e.arms[i][0].span,
                )
                return ["case", [], values[i]], result
        if conds[-1] is not None:
            missing = self.uncovered(parts, keys)
            if missing is not None:
                return self.error(
                    "E304",
                    f"match no exhaustivo: falta el caso {missing}",
                    e.span,
                    help="añade ese caso o un caso final '_ => …'",
                )
        arms = [[c, v] for c, v in zip(conds[:-1], values[:-1], strict=True)]
        return ["case", arms, values[-1]], result

    def pattern(
        self, p: ast.Pattern, parts: list[Typed], width: int, scope: Scope, ctx: Ctx
    ) -> tuple[Any | None, list[str | None]]:
        """Condición de un patrón (None si siempre se cumple) y su clave por componente (None
        = comodín; si no, el JSON del valor) para comprobar la exhaustividad."""
        if isinstance(p, ast.PWild):
            return None, [None] * width
        items: list[ast.Pattern]
        if isinstance(p, ast.PTuple):
            items = p.items
            if len(items) != width:
                self.error(
                    "E301", f"el patrón tiene {len(items)} componentes y el valor {width}", p.span
                )
                return None, [None] * width
        elif width != 1:
            self.error("E301", f"se esperaba un patrón de {width} componentes", p.span)
            return None, [None] * width
        else:
            items = [p]
        conds: list[Any] = []
        key: list[str | None] = []
        for (part_ir, part_ty), item in zip(parts, items, strict=True):
            if isinstance(item, ast.PWild):
                key.append(None)
                continue
            if not isinstance(item, ast.PValue):
                self.error("E301", "los patrones anidados solo admiten valores y _", item.span)
                key.append(None)
                continue
            v_ir, v_ty = self.expr(item.value, scope, ctx, part_ty)
            if not _is_constant(v_ir):
                self.error("E301", "un patrón debe ser un valor constante", item.span)
            if not T.comparable(part_ty, v_ty):
                self.error("E301", f"el patrón es `{v_ty}` y el valor `{part_ty}`", item.span)
            conds.append(["eq", part_ir, v_ir])
            key.append(json.dumps(v_ir, sort_keys=True))
        if not conds:
            return None, key
        return (conds[0] if len(conds) == 1 else ["and", *conds]), key

    def uncovered(self, parts: list[Typed], keys: list[list[str | None]]) -> str | None:
        """Primer caso no cubierto por los patrones (None si son exhaustivos)."""
        domains: list[list[tuple[str | None, str]]] = []
        for _, ty in parts:
            values = self.finite_values(ty)
            if values is None:
                domains.append([(None, "_")])  # dominio infinito: solo lo cubre un comodín
            else:
                domains.append(values)
        total = 1
        for d in domains:
            total *= len(d)
        if total > 10_000:
            return None
        for combo in itertools.product(*domains):
            covered = any(
                all(
                    k is None or (v is not None and k == v)
                    for k, (v, _) in zip(key, combo, strict=True)
                )
                for key in keys
            )
            if not covered:
                shown = [label for _, label in combo]
                return shown[0] if len(shown) == 1 else "(" + ", ".join(shown) + ")"
        return None

    def finite_values(self, ty: Ty) -> list[tuple[str | None, str]] | None:
        def key(ir: Any) -> str:
            return json.dumps(ir, sort_keys=True)

        if ty.kind == "Bool":
            return [(key(["const", v]), "true" if v else "false") for v in (False, True)]
        if ty.kind == "enum":
            info = self.types.get(ty.name)
            if info is None or not isinstance(info.decl, ast.EnumDecl):
                return None
            return [(key(["enum", ty.name, v]), v) for v in info.decl.values]
        if ty.kind == "option":
            inner = self.finite_values(ty.inner)
            if inner is None:
                return None
            return [(key(["const", None]), "none"), *inner]
        return None

    # --- tests e invariantes --------------------------------------------------------------------

    def check_invariant(self, inv: ast.InvariantDecl) -> Invariant:
        ctx = Ctx("un invariante")
        expr = self.expect(self.expr(inv.expr, Scope(), ctx, T.BOOL), T.BOOL, inv.expr.span)
        label = inv.doc.value if inv.doc is not None and isinstance(inv.doc.value, str) else ""
        if inv.doc is not None and isinstance(inv.doc.value, dict):
            label = next(iter(inv.doc.value.values()))
        return Invariant(label, expr, inv.span)

    def check_test(self, test: ast.TestDecl) -> TestCase:
        ctx = Ctx(f"el test {test.name!r}", test=True)
        const = Ctx("los parámetros de un test", reads_state=False)
        steps: list[TestStep] = []
        configured: set[str] = set()
        started = False
        for step in test.steps:
            out = TestStep(step.kind, step.span)
            if step.kind in ("players", "params", "seed"):
                if started:
                    self.error(
                        "E601",
                        f"'{step.kind}' configura la partida: va al principio del test",
                        step.span,
                        help="pon players, params y seed antes del primer paso",
                    )
                elif step.kind in configured:
                    self.error("E601", f"'{step.kind}' repetido en el test", step.span)
                configured.add(step.kind)
            else:
                started = True
            match step.kind:
                case "players" | "seed":
                    assert isinstance(step.value, ast.IntLit)
                    out.value = step.value.value
                    players = self.model.players
                    if (
                        step.kind == "players"
                        and players is not None
                        and not players.min <= out.value <= players.max
                    ):
                        allowed = (
                            str(players.min)
                            if players.min == players.max
                            else f"de {players.min} a {players.max}"
                        )
                        self.error(
                            "E602",
                            f"el juego admite {allowed} jugadores, no {out.value}",
                            step.value.span,
                        )
                case "params":
                    for name, value in step.entries:
                        if name not in self.params:
                            self.error(
                                "E201",
                                f"parámetro desconocido: {name}",
                                value.span,
                                help=self.suggest(name, list(self.params)),
                            )
                            continue
                        ty = self.params[name][0]
                        out.entries[name] = self.expect(
                            self.expr(value, Scope(), const, ty), ty, value.span
                        )
                case "play" | "legal" | "illegal":
                    out.actions = [self.action_call(a, ctx) for a in step.actions]
                case "chance":
                    if step.where is not None:
                        out.target = self.expect(
                            self.expr(step.where, Scope(), ctx, T.BOOL), T.BOOL, step.where.span
                        )
                    else:
                        assert step.value is not None
                        out.value = self.expect(
                            self.expr(step.value, Scope(), const, T.list_(T.INT)),
                            T.list_(T.INT),
                            step.value.span,
                        )
                case "expect":
                    assert step.value is not None
                    out.value = self.expect(
                        self.expr(step.value, Scope(), ctx, T.BOOL), T.BOOL, step.value.span
                    )
                case "set":
                    assert step.target is not None and step.value is not None
                    target_ir, target_ty = self.lvalue(step.target, Scope(), ctx)
                    out.target = target_ir
                    out.value = self.expect(
                        self.expr(step.value, Scope(), ctx, target_ty), target_ty, step.value.span
                    )
            steps.append(out)
        return TestCase(test.name, steps, test.span)

    def action_call(self, a: ast.ActionLit, ctx: Ctx) -> ActionCall:
        seat = a.seat.value if isinstance(a.seat, ast.IntLit) else None
        decls = self.actions.get(a.name, [])
        if a.name == "pass":
            if a.args:
                self.error("E207", "pass() no lleva argumentos", a.span)
            return ActionCall("pass", [], seat, a.span)
        if not decls:
            self.error(
                "E201",
                f"acción desconocida: {a.name}",
                a.span,
                help=self.suggest(a.name, list(self.actions)),
            )
            return ActionCall(a.name, [], seat, a.span)
        decl = decls[0]
        if len(a.args) != len(decl.params):
            self.error(
                "E207",
                f"{a.name} tiene {len(decl.params)} parámetro(s) y recibe {len(a.args)}",
                a.span,
            )
        args = [self.expr(x, Scope(), ctx)[0] for x in a.args]
        return ActionCall(a.name, args, seat, a.span)


# --- utilidades ---------------------------------------------------------------------------------


def _exits(node: ast.NodeDecl) -> bool:
    for m in node.members:
        if isinstance(m, ast.Transition) and m.target == "exit":
            return True
        if isinstance(m, ast.ActionDecl) and any(t.target == "exit" for t in m.transitions):
            return True
    return False


def _same_op(e: ast.Expr, op: str) -> bool:
    return isinstance(e, ast.Binary) and e.op == op


def _locals_in(ir: Any) -> set[str]:
    found: set[str] = set()

    def walk(x: Any) -> None:
        if isinstance(x, list):
            if len(x) == 2 and x[0] == "local" and isinstance(x[1], str):
                found.add(x[1])
            for y in x:
                walk(y)
        elif isinstance(x, dict):
            for y in x.values():
                walk(y)

    walk(ir)
    return found


def _fresh(base: str, taken: set[str]) -> str:
    if base not in taken:
        return base
    for i in itertools.count(2):
        name = f"{base}{i}"
        if name not in taken:
            return name
    raise AssertionError


def _is_constant(ir: Any) -> bool:
    if not isinstance(ir, list) or not ir:
        return False
    head = ir[0]
    if head in ("const", "enum", "rat"):
        return True
    if head in ("tuple", "list"):
        return all(_is_constant(x) for x in ir[1:])
    return False


def _compare_help(left: Ty, right: Ty) -> str | None:
    if {left.kind, right.kind} & {"zone", "bag"} and "list" in (left.kind, right.kind):
        return "una zona no es una lista: compara items(z) o usa size(z)"
    return None
