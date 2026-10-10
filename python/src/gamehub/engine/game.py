# SPDX-License-Identifier: Apache-2.0
"""Compilación de un documento GameIR a una definición ejecutable (`GameDef`) y el objeto
público `Game`, punto de entrada para crear partidas."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from gamehub.engine.env import Ctx, Env
from gamehub.engine.errors import InvalidParams, RuleError
from gamehub.engine.expr import (
    Compiled,
    ExprCompiler,
    boolean,
    is_sub_multiset,
    iterate,
    num,
)
from gamehub.engine.stmt import Runner, StmtCompiler, coerce
from gamehub.engine.values import EnumValue, Grid, Type, TypeTable, sort_key
from gamehub.engine.visibility import ALL, Policy, compile_policy
from gamehub.ir import check
from gamehub.ir.hashing import rules_hash
from gamehub.ir.spec import load_json

if TYPE_CHECKING:
    from gamehub.engine.state import Action, State

Member = Callable[[Env, Any], tuple[bool, Any]]


@dataclass(frozen=True)
class VarDef:
    name: str
    index: int
    type: Type
    init: Compiled
    policy: Policy
    size_policy: Policy


@dataclass(frozen=True)
class ParamDef:
    name: str
    type: Type
    default: Compiled


@dataclass(frozen=True)
class FunctionDef:
    name: str
    params: tuple[str, ...]
    body: Compiled


@dataclass(frozen=True)
class ActionParam:
    name: str
    type: Type
    domain: Compiled
    member: Member
    policy: Policy
    size_policy: Policy


@dataclass(frozen=True)
class TransitionDef:
    to: str
    when: Compiled | None
    effects: Runner


@dataclass(frozen=True)
class ActionDef:
    name: str
    params: tuple[ActionParam, ...]
    requires: Compiled | None
    effects: Runner
    transitions: tuple[TransitionDef, ...]
    policy: Policy


@dataclass(frozen=True)
class NodeDef:
    id: str
    kind: str
    ancestors: tuple[str, ...]
    transitions: tuple[TransitionDef, ...] = ()
    actions: tuple[ActionDef, ...] = ()
    actor: Compiled | None = None  # decision
    actors: Compiled | None = None  # simultaneous
    resolve: Runner | None = None  # simultaneous
    eligible: Compiled | None = None  # window
    order: Compiled | None = None  # window
    mode: str = ""  # window
    effects: Runner | None = None  # chance / auto
    start: str = ""  # phase
    on_enter: Runner | None = None  # phase
    on_exit: Runner | None = None  # phase
    payoff: Compiled | None = None  # terminal
    rank: Compiled | None = None  # terminal
    actions_by_name: dict[str, ActionDef] = field(default_factory=dict)

    @property
    def parent(self) -> str | None:
        return self.ancestors[-1] if self.ancestors else None


class GameDef:
    """La IR compilada: tipos, variables, funciones y nodos listos para ejecutar."""

    def __init__(self, ir: dict[str, Any]) -> None:
        self.ir = ir
        self.rules_hash = rules_hash(ir)
        self.min_players = ir["players"]["min"]
        self.max_players = ir["players"]["max"]
        self.types = TypeTable(ir.get("types", []))
        state = ir.get("state", [])
        self.var_index = {v["name"]: i for i, v in enumerate(state)}
        self.exprs = ExprCompiler(self.types, self.var_index)
        self.functions = {
            f["name"]: FunctionDef(
                f["name"], tuple(p[0] for p in f["params"]), self.exprs.compile(f["body"])
            )
            for f in ir.get("functions", [])
        }
        self.vars = [
            VarDef(
                name=v["name"],
                index=i,
                type=self.types.parse(v["type"]),
                init=self.exprs.compile(v["init"]),
                policy=compile_policy(v.get("visibility"), self.exprs),
                size_policy=compile_policy(v.get("size_visibility"), self.exprs),
            )
            for i, v in enumerate(state)
        ]
        self.vars_by_name = {v.name: v for v in self.vars}
        self.params = [
            ParamDef(p["name"], self.types.parse(p["type"]), self.exprs.compile(p["default"]))
            for p in ir.get("params", [])
        ]
        self.constraints = [
            (self.exprs.compile(c["expr"]), _text(c.get("message")) or "restricción incumplida")
            for c in ir.get("constraints", [])
        ]
        self.stmts = StmtCompiler(self.exprs, self.vars_by_name)
        flow = ir["flow"]
        self.start = flow["start"]
        self.setup = self.stmts.block(flow.get("setup", []))
        self.setup_is_random = _has_chance(flow.get("setup", []))
        self.nodes: dict[str, NodeDef] = {}
        self._compile_nodes(flow["nodes"], ())

    # --- nodos ----------------------------------------------------------------------------------

    def _compile_nodes(self, nodes: list[dict[str, Any]], ancestors: tuple[str, ...]) -> None:
        for raw in nodes:
            node = self._node(raw, ancestors)
            self.nodes[node.id] = node
            if raw["kind"] == "phase":
                self._compile_nodes(raw["nodes"], (*ancestors, raw["id"]))

    def _node(self, raw: dict[str, Any], ancestors: tuple[str, ...]) -> NodeDef:
        c, s = self.exprs, self.stmts
        actions = tuple(self._action(a) for a in raw.get("actions", []))
        optional = {
            "actor": c.compile,
            "actors": c.compile,
            "eligible": c.compile,
            "order": c.compile,
            "payoff": c.compile,
            "rank": c.compile,
            "resolve": s.block,
            "effects": s.block,
            "on_enter": s.block,
            "on_exit": s.block,
        }
        compiled = {key: fn(raw[key]) for key, fn in optional.items() if key in raw}
        return NodeDef(
            id=raw["id"],
            kind=raw["kind"],
            ancestors=ancestors,
            transitions=self._transitions(raw.get("transitions", [])),
            actions=actions,
            mode=raw.get("mode", ""),
            start=raw.get("start", ""),
            actions_by_name={a.name: a for a in actions},
            **compiled,
        )

    def _transitions(self, raw: list[dict[str, Any]]) -> tuple[TransitionDef, ...]:
        return tuple(
            TransitionDef(
                to=t["to"],
                when=self.exprs.compile(t["when"]) if "when" in t else None,
                effects=self.stmts.block(t.get("effects", [])),
            )
            for t in raw
        )

    def _action(self, raw: dict[str, Any]) -> ActionDef:
        params = tuple(
            ActionParam(
                name=p["name"],
                type=self.types.parse(p["type"]),
                domain=self.exprs.compile(p["domain"]),
                member=self._member(p["domain"]),
                policy=compile_policy(p.get("visibility"), self.exprs),
                size_policy=compile_policy(p.get("size_visibility"), self.exprs),
            )
            for p in raw.get("params", [])
        )
        return ActionDef(
            name=raw["name"],
            params=params,
            requires=self.exprs.compile(raw["requires"]) if "requires" in raw else None,
            effects=self.stmts.block(raw.get("effects", [])),
            transitions=self._transitions(raw.get("transitions", [])),
            policy=compile_policy(raw.get("visibility"), self.exprs, default=ALL),
        )

    def _member(self, domain: list[Any]) -> Member:
        """Pertenencia al dominio sin enumerarlo cuando es posible. Devuelve (¿pertenece?,
        valor canónico)."""
        op, args = domain[0], domain[1:]
        if op == "subsets":
            coll, lo, hi = (self.exprs.compile(a) for a in args)

            def member_subsets(env: Env, v: Any) -> tuple[bool, Any]:
                if not isinstance(v, tuple):
                    return False, v
                ok = num(lo(env), "subsets") <= len(v) <= num(hi(env), "subsets")
                ok = ok and is_sub_multiset(v, iterate(coll(env), "subsets"))
                return ok, tuple(sorted(v, key=sort_key))

            return member_subsets
        if op == "range":
            lo, hi = (self.exprs.compile(a) for a in args)
            return lambda env, v: (
                isinstance(v, int) and not isinstance(v, bool) and lo(env) <= v <= hi(env),
                v,
            )
        if op == "enum_values":
            type_name = args[0]
            return lambda env, v: (isinstance(v, EnumValue) and v.type == type_name, v)
        compiled = self.exprs.compile(domain)
        return lambda env, v: (v in iterate(compiled(env), "dominio"), v)

    # --- estado inicial -------------------------------------------------------------------------

    def initial_values(self, n: int, given: dict[str, Any]) -> dict[str, Any]:
        """Valores de los parámetros (JSON → valor), con valores por defecto y restricciones."""
        if not self.min_players <= n <= self.max_players:
            raise InvalidParams(
                f"este juego admite de {self.min_players} a {self.max_players} jugadores, no {n}"
            )
        known = {p.name for p in self.params}
        unknown = set(given) - known
        if unknown:
            raise InvalidParams(f"parámetros desconocidos: {sorted(unknown)}")
        values: dict[str, Any] = {"num_players": n}
        env = Env(Ctx(self, [], values, n))
        for p in self.params:
            if p.name in given:
                try:
                    values[p.name] = coerce(self.types.decode(given[p.name], p.type), p.type)
                except ValueError as exc:
                    raise InvalidParams(f"parámetro {p.name}: {exc}") from None
            else:
                values[p.name] = coerce(p.default(env), p.type)
        for expr, message in self.constraints:
            if not boolean(expr(env), "restricción"):
                raise InvalidParams(message)
        return values

    def initial_store(self, n: int, params: dict[str, Any]) -> list[Any]:
        ctx = Ctx(self, [], params, n)
        store: list[Any] = []
        for var in self.vars:
            if var.type.kind == "per_player":
                store.append(
                    tuple(
                        self._initial(var.init(Env(ctx, owner=s)), var.type.inner, params)
                        for s in range(n)
                    )
                )
            else:
                store.append(self._initial(var.init(Env(ctx)), var.type, params))
        return store

    def _initial(self, value: Any, t: Type, params: dict[str, Any]) -> Any:
        if t.kind != "grid":
            return coerce(value, t)
        w, h = (d if isinstance(d, int) else params[d] for d in t.dims)
        is_rows = (
            isinstance(value, tuple)
            and len(value) == h
            and all(isinstance(r, tuple) and len(r) == w for r in value)
            and t.inner.kind not in ("list", "tuple")
        )
        if is_rows:
            cells = tuple(coerce(x, t.inner) for row in value for x in row)
            return Grid(w, h, cells)
        return Grid.filled(w, h, coerce(value, t.inner))


class Game:
    """Un juego cargado desde su IR. Crea partidas con `new_state`."""

    def __init__(self, ir: dict[str, Any]) -> None:
        problems = check(ir)
        if problems:
            listing = "\n  ".join(str(p) for p in problems[:20])
            raise RuleError(f"la IR no es válida:\n  {listing}")
        self.ir = ir
        self.defn = GameDef(ir)

    @property
    def id(self) -> str:
        return self.ir["game"]["id"]

    @property
    def version(self) -> str:
        return self.ir["game"]["version"]

    @property
    def title(self) -> str:
        return _text(self.ir.get("meta", {}).get("title")) or self.id

    @property
    def rules_hash(self) -> str:
        return self.defn.rules_hash

    @property
    def players(self) -> tuple[int, int]:
        return self.defn.min_players, self.defn.max_players

    def new_state(
        self, num_players: int | None = None, params: dict[str, Any] | None = None
    ) -> State:
        from gamehub.engine.state import State

        return State.initial(self.defn, num_players or self.defn.min_players, params or {})

    def decode_action(self, node: str | None, data: dict[str, Any]) -> Action:
        """Acción del nodo `node` desde JSON, sin necesidad de un estado: la usan los clientes,
        que solo conocen su vista (el nodo actual va en ella)."""
        from gamehub.engine.state import decode_action

        return decode_action(self.defn, node, data)


def load_game(source: str | Path | dict[str, Any]) -> Game:
    """Carga un juego desde un archivo .ir.json o desde un documento ya leído."""
    ir = source if isinstance(source, dict) else load_json(Path(source))
    return Game(ir)


def _text(value: Any) -> str | None:
    if value is None or isinstance(value, str):
        return value
    return value.get("es") or next(iter(value.values()), None)


def _has_chance(block: list[Any]) -> bool:
    def walk(node: Any) -> bool:
        if isinstance(node, list):
            if node and node[0] in ("shuffle", "roll", "random_choice", "sample"):
                return True
            return any(walk(x) for x in node)
        return False

    return walk(block)
