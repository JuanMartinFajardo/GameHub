# SPDX-License-Identifier: Apache-2.0
"""Compilador de sentencias (efectos) de la IR a funciones Python (`Env → None`).

Las sentencias modifican `env.ctx.store` en sitio (el `State` que se construye después es
inmutable) y añaden eventos a `env.ctx.events`. Las sentencias aleatorias consumen sorteos de
`env.ctx.draws`, que solo existe al ejecutar un nodo de azar o la preparación.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction
from typing import TYPE_CHECKING, Any

from gamehub.engine.env import Env
from gamehub.engine.errors import RuleError
from gamehub.engine.events import Event
from gamehub.engine.expr import Compiled, ExprCompiler, boolean, index_value, iterate, num, seat
from gamehub.engine.values import (
    HIDDEN,
    Grid,
    MapValue,
    SetValue,
    StructValue,
    Type,
    Zone,
    ZoneItem,
    norm_num,
    to_json,
)
from gamehub.engine.visibility import ALL, Policy, compile_policy

if TYPE_CHECKING:
    from gamehub.engine.game import VarDef

Runner = Callable[[Env], None]


# --- Lvalues -----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LValue:
    """Ubicación modificable: lectura, escritura, tipo estático y localización para eventos
    (variable raíz y, si el camino atraviesa un per_player, el asiento dueño)."""

    get: Compiled
    set: Callable[[Env, Any], None]
    locate: Callable[[Env], tuple[str, int | None]]
    type: Type


def _with_index(container: Any, key: Any, value: Any) -> Any:
    if isinstance(container, tuple):
        index_value(container, key)  # comprueba el rango
        return (*container[:key], value, *container[key + 1 :])
    if isinstance(container, Grid):
        return container.set(key, value)
    if isinstance(container, MapValue):
        return container.set(key, value)
    raise RuleError(f"no se puede asignar por índice en {container!r}")


def coerce(v: Any, t: Type) -> Any:
    """Adapta un valor al tipo declarado (listas → zonas, bolsas o conjuntos; racionales)."""
    match t.kind:
        case "zone" | "bag":
            ordered = t.kind == "zone"
            if isinstance(v, Zone):
                return v if v.ordered == ordered else Zone(v.items, ordered).normalized()
            return Zone.of(iterate(v), ordered=ordered)
        case "set":
            return v if isinstance(v, SetValue) else SetValue.of(iterate(v))
        case "map":
            return v if isinstance(v, MapValue) else MapValue.of(iterate(v))
        case "per_player" | "list":
            if t.inner.kind in ("zone", "bag", "set", "map", "per_player", "list", "option"):
                return tuple(coerce(x, t.inner) for x in v)
            return v
        case "option":
            return None if v is None else coerce(v, t.inner)
        case "prim":
            return norm_num(v) if t.name == "Real" else v
    return v


# --- Selectores de elementos de zona -----------------------------------------------------------


def _zone(v: Any) -> Zone:
    if not isinstance(v, Zone):
        raise RuleError(f"se esperaba una zona o bolsa, no {v!r}")
    return v


def _ordered(z: Zone, what: str) -> None:
    if not z.ordered:
        raise RuleError(f"'{what}' necesita una zona ordenada; las bolsas no tienen orden")


Selector = Callable[[Env, Zone], list[int]]


def compile_selector(sel: list[Any], c: ExprCompiler) -> Selector:
    kind = sel[0]
    arg = c.compile(sel[1]) if len(sel) > 1 else None

    def select(env: Env, z: Zone) -> list[int]:
        size = len(z)
        match kind:
            case "all":
                return list(range(size))
            case "top" | "bottom":
                assert arg is not None
                k = num(arg(env), kind)
                _ordered(z, kind)
                if not 0 <= k <= size:
                    raise RuleError(f"'{kind} {k}' en una zona de {size} elementos")
                return list(range(k)) if kind == "top" else list(range(size - k, size))
            case "at":
                assert arg is not None
                i = num(arg(env), "at")
                _ordered(z, "at")
                if not 0 <= i < size:
                    raise RuleError(f"posición {i} fuera de una zona de {size} elementos")
                return [i]
            case "value" | "values":
                assert arg is not None
                wanted = [arg(env)] if kind == "value" else list(iterate(arg(env), kind))
                chosen: list[int] = []
                for v in wanted:
                    i = next(
                        (i for i, it in enumerate(z.items) if it.value == v and i not in chosen),
                        None,
                    )
                    if i is None:
                        raise RuleError(f"no hay {v!r} en la zona")
                    chosen.append(i)
                return chosen
        raise RuleError(f"selector desconocido: {kind}")

    return select


# --- Compilador de sentencias ------------------------------------------------------------------


class StmtCompiler:
    def __init__(self, exprs: ExprCompiler, variables: dict[str, VarDef]) -> None:
        self.exprs = exprs
        self.variables = variables

    def block(self, stmts: list[Any]) -> Runner:
        compiled = [self.stmt(s) for s in stmts]
        if not compiled:
            return lambda env: None

        def run(env: Env) -> None:
            scope = env.child()
            for s in compiled:
                s(scope)

        return run

    def lvalue(self, e: list[Any]) -> LValue:
        op = e[0]
        if op == "var":
            name = e[1]
            i = self.exprs.var_index[name]

            def set_var(env: Env, v: Any) -> None:
                env.ctx.store[i] = v

            return LValue(
                get=lambda env: env.ctx.store[i],
                set=set_var,
                locate=lambda env: (name, None),
                type=self.variables[name].type,
            )
        base = self.lvalue(e[1])
        if op == "index":
            key = self.exprs.compile(e[2])
            per_player = base.type.kind == "per_player"
            inner = base.type.args[1] if base.type.kind == "map" else base.type.inner

            def set_index(env: Env, v: Any) -> None:
                base.set(env, _with_index(base.get(env), key(env), v))

            def locate_index(env: Env) -> tuple[str, int | None]:
                root, owner = base.locate(env)
                return root, (key(env) if per_player else owner)

            return LValue(
                get=lambda env: index_value(base.get(env), key(env)),
                set=set_index,
                locate=locate_index,
                type=inner,
            )
        if op == "field":
            name = e[2]
            fields = dict(self.exprs.types.structs[base.type.name])

            def get_field(env: Env) -> Any:
                value = base.get(env)
                assert isinstance(value, StructValue)
                return value.get(name)

            def set_field(env: Env, v: Any) -> None:
                value = base.get(env)
                assert isinstance(value, StructValue)
                base.set(env, value.replace(name, v))

            return LValue(get_field, set_field, base.locate, fields[name])
        raise RuleError(f"no es una ubicación modificable: {op}")

    def stmt(self, s: list[Any]) -> Runner:
        op, args = s[0], s[1:]
        method = getattr(self, f"_{op}", None)
        if method is None:
            raise NotImplementedError(f"sentencia sin implementar: {op}")
        return method(*args)

    # --- Sentencias básicas ---------------------------------------------------------------------

    def _assign(self, target: list[Any], value_e: list[Any]) -> Runner:
        lv, value = self.lvalue(target), self.exprs.compile(value_e)
        return lambda env: lv.set(env, coerce(value(env), lv.type))

    def _let(self, name: str, value_e: list[Any]) -> Runner:
        value = self.exprs.compile(value_e)

        def run(env: Env) -> None:
            env.locals[name] = value(env)

        return run

    def _if(self, cond_e: list[Any], then: list[Any], other: list[Any] | None = None) -> Runner:
        cond, then_r, other_r = (
            self.exprs.compile(cond_e),
            self.block(then),
            self.block(other or []),
        )

        def run(env: Env) -> None:
            if boolean(cond(env), "if"):
                then_r(env)
            else:
                other_r(env)

        return run

    def _for(self, name: str, coll_e: list[Any], body: list[Any]) -> Runner:
        coll, body_r = self.exprs.compile(coll_e), self.block(body)

        def run(env: Env) -> None:
            for x in iterate(coll(env), "for"):
                body_r(env.bind(name, x))

        return run

    def _fail(self, text: Any) -> Runner:
        message = text if isinstance(text, str) else next(iter(text.values()))

        def run(env: Env) -> None:
            raise RuleError(message)

        return run

    # --- Zonas ----------------------------------------------------------------------------------

    def _policies(self, root: str) -> tuple[Policy, Policy]:
        var = self.variables[root]
        return var.policy, var.size_policy

    def _move(self, src_e: list[Any], dst_e: list[Any], sel: list[Any], pos: str = "top") -> Runner:
        src, dst = self.lvalue(src_e), self.lvalue(dst_e)
        select = compile_selector(sel, self.exprs)

        def run(env: Env) -> None:
            ctx = env.ctx
            zone = _zone(src.get(env))
            chosen = select(env, zone)
            moved = [zone.items[i] for i in chosen]
            src_loc = src.locate(env)
            before = _sightings(env, src_loc, moved, self._policies(src_loc[0]))
            keep = set(chosen)
            src.set(env, zone.with_items(it for i, it in enumerate(zone.items) if i not in keep))
            target = _zone(dst.get(env))
            items = (*moved, *target.items) if pos == "top" else (*target.items, *moved)
            dst.set(env, coerce(target.with_items(items), dst.type))
            dst_loc = dst.locate(env)
            after = _sightings(env, dst_loc, moved, self._policies(dst_loc[0]))
            values = [to_json(it.value) for it in moved]
            full = {
                "type": "move",
                "from": _loc_json(src_loc),
                "to": _loc_json(dst_loc),
                "count": len(moved),
                "items": values,
            }
            seen: list[dict[str, Any] | None] = []
            for s in range(ctx.n):
                (size_a, items_a), (size_b, items_b) = before[s], after[s]
                if not (size_a or size_b):
                    seen.append(None)
                    continue
                shown = [
                    v if a or b else HIDDEN
                    for v, a, b in zip(values, items_a, items_b, strict=True)
                ]
                seen.append({**full, "items": shown})
            ctx.events.append(Event(full, tuple(seen)))

        return run

    def _flip(self, target_e: list[Any], sel: list[Any], face_e: list[Any]) -> Runner:
        target, face = self.lvalue(target_e), self.exprs.compile(face_e)
        select = compile_selector(sel, self.exprs)

        def run(env: Env) -> None:
            zone = _zone(target.get(env))
            chosen = set(select(env, zone))
            up = boolean(face(env), "flip")
            items = (
                ZoneItem(it.value, up) if i in chosen else it for i, it in enumerate(zone.items)
            )
            target.set(env, zone.with_items(items))
            payload = {
                "type": "flip",
                "zone": _loc_json(target.locate(env)),
                "count": len(chosen),
                "face_up": up,
            }
            env.ctx.events.append(Event.public(payload, env.ctx.n))

        return run

    # --- Azar -----------------------------------------------------------------------------------

    def _shuffle(self, target_e: list[Any]) -> Runner:
        target = self.lvalue(target_e)

        def run(env: Env) -> None:
            zone = _zone(target.get(env))
            _ordered(zone, "shuffle")
            items = list(zone.items)
            draws = _draws(env)
            for i in range(len(items) - 1, 0, -1):
                j = draws.uniform(i + 1)
                items[i], items[j] = items[j], items[i]
            target.set(env, zone.with_items(items))
            payload = {"type": "shuffle", "zone": _loc_json(target.locate(env))}
            env.ctx.events.append(Event.public(payload, env.ctx.n))

        return run

    def _roll(self, target_e: list[Any], sides_e: list[Any]) -> Runner:
        target, sides = self.lvalue(target_e), self.exprs.compile(sides_e)
        return lambda env: target.set(env, _draws(env).uniform(num(sides(env), "roll")) + 1)

    def _random_choice(self, target_e: list[Any], coll_e: list[Any]) -> Runner:
        target, coll = self.lvalue(target_e), self.exprs.compile(coll_e)

        def run(env: Env) -> None:
            items = iterate(coll(env), "random_choice")
            target.set(env, coerce(items[_draws(env).uniform(len(items))], target.type))

        return run

    def _sample(self, target_e: list[Any], dist_e: list[Any]) -> Runner:
        target, dist = self.lvalue(target_e), self.exprs.compile(dist_e)

        def run(env: Env) -> None:
            pairs = iterate(dist(env), "sample")
            probs = [Fraction(num(p[1], "sample")) for p in pairs]
            if any(p < 0 for p in probs) or sum(probs) != 1:
                raise RuleError(f"distribución inválida en 'sample': {probs}")
            choice = pairs[_draws(env).weighted(probs)][0]
            target.set(env, coerce(choice, target.type))

        return run

    # --- Eventos --------------------------------------------------------------------------------

    def _reveal(self, value_e: list[Any], seats_e: list[Any], label: Any = None) -> Runner:
        value, seats = self.exprs.compile(value_e), self.exprs.compile(seats_e)

        def run(env: Env) -> None:
            n = env.ctx.n
            to = {seat(s, n, "reveal") for s in iterate(seats(env), "reveal")}
            payload: dict[str, Any] = {"type": "reveal", "value": to_json(value(env))}
            if label is not None:
                payload["label"] = label
            env.ctx.events.append(
                Event(payload, tuple(payload if s in to else None for s in range(n)))
            )

        return run

    def _emit(self, name: str, fields: dict[str, Any], vis: Any = None) -> Runner:
        compiled = {k: self.exprs.compile(v) for k, v in fields.items()}
        policy = compile_policy(vis, self.exprs, default=ALL)

        def run(env: Env) -> None:
            payload = {
                "type": "emit",
                "name": name,
                "fields": {k: to_json(f(env)) for k, f in compiled.items()},
            }
            seen = tuple(
                payload if policy.allows(Env(env.ctx, viewer=s, owner=env.actor)) else None
                for s in range(env.ctx.n)
            )
            env.ctx.events.append(Event(payload, seen))

        return run

    def _reward(self, seat_e: list[Any], amount_e: list[Any]) -> Runner:
        who, amount = self.exprs.compile(seat_e), self.exprs.compile(amount_e)

        def run(env: Env) -> None:
            payload = {
                "type": "reward",
                "seat": seat(who(env), env.ctx.n, "reward"),
                "amount": to_json(num(amount(env), "reward")),
            }
            env.ctx.events.append(Event.public(payload, env.ctx.n))

        return run


# --- Utilidades --------------------------------------------------------------------------------


def _draws(env: Env) -> Any:
    if env.ctx.draws is None:
        raise RuleError("sentencia aleatoria fuera de un nodo de azar")
    return env.ctx.draws


def _loc_json(loc: tuple[str, int | None]) -> dict[str, Any]:
    root, owner = loc
    return {"var": root} if owner is None else {"var": root, "seat": owner}


def _sightings(
    env: Env,
    loc: tuple[str, int | None],
    items: list[ZoneItem],
    policies: tuple[Policy, Policy],
) -> list[tuple[bool, list[bool]]]:
    """Para cada asiento: ¿ve el tamaño de la zona? ¿y cada elemento movido?"""
    policy, size_policy = policies
    owner = loc[1]
    result = []
    for s in range(env.ctx.n):
        probe = Env(env.ctx, viewer=s, owner=owner)
        seen_items = [policy.allows(probe.replace(face_up=it.face_up)) for it in items]
        result.append((size_policy.allows(probe), seen_items))
    return result
