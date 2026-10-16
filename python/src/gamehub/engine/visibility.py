# SPDX-License-Identifier: Apache-2.0
"""Visibilidad: políticas compiladas y redacción de valores para un observador.

Una política decide si el asiento `viewer` ve una ubicación. Atajos: `all`, `none`, `owner`
(el observador es el dueño de la ubicación per_player); o un predicado con `viewer`, `owner` e
`item_face_up` ligados. `viewer=None` es la vista omnisciente: lo ve todo; `viewer=PUBLIC` es un
espectador, que no ocupa ningún asiento: ve lo que la política permite a quien no es dueño de nada
(un predicado que no se puede evaluar para él, como `team[viewer]`, cuenta como falso).

Redacción de zonas (ADR-019):

- zona ordenada con tamaño visible → `{"size": n, "items": [valor | oculto por posición]}`
- bolsa con tamaño visible        → `{"size": n, "items": [solo los valores visibles]}`
- tamaño oculto                   → `{"items": [solo los visibles]}`, u oculta si no hay ninguno
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from gamehub.engine.env import PUBLIC, Env
from gamehub.engine.errors import RuleError
from gamehub.engine.expr import ExprCompiler, boolean
from gamehub.engine.values import HIDDEN, Type, Zone, to_json


class Policy:
    __slots__ = ("always", "never", "predicate")

    def __init__(
        self,
        *,
        always: bool = False,
        never: bool = False,
        predicate: Callable[[Env], bool] | None = None,
    ) -> None:
        self.always = always
        self.never = never
        self.predicate = predicate

    def allows(self, env: Env) -> bool:
        if env.viewer is None or self.always:
            return True
        if self.never:
            return False
        assert self.predicate is not None
        if env.viewer == PUBLIC:
            try:
                return self.predicate(env)
            except RuleError:
                return False
        return self.predicate(env)


ALL = Policy(always=True)
NONE = Policy(never=True)
OWNER = Policy(predicate=lambda env: env.viewer == env.owner)


def compile_policy(raw: Any, compiler: ExprCompiler, default: Policy = ALL) -> Policy:
    if raw is None:
        return default
    if raw == "all":
        return ALL
    if raw == "none":
        return NONE
    if raw == "owner":
        return OWNER
    expr = compiler.compile(raw["when"])
    return Policy(predicate=lambda env: boolean(expr(env), "visibilidad"))


def redact(value: Any, t: Type, policy: Policy, size_policy: Policy, env: Env) -> Any:
    """`value` (de tipo `t`) tal como lo ve `env.viewer`."""
    if t.kind == "per_player":
        return [
            redact(v, t.inner, policy, size_policy, env.replace(owner=s))
            for s, v in enumerate(value)
        ]
    if t.kind in ("zone", "bag"):
        return redact_zone(value, policy, size_policy, env)
    if t.kind == "list" and _holds_zones(t):
        # Una lista de zonas (las columnas de un solitario): cada una con su visibilidad.
        return [redact(v, t.inner, policy, size_policy, env) for v in value]
    return to_json(value) if policy.allows(env) else HIDDEN


def _holds_zones(t: Type) -> bool:
    while t.kind == "list":
        t = t.inner
    return t.kind in ("zone", "bag")


def redact_zone(zone: Zone, policy: Policy, size_policy: Policy, env: Env) -> Any:
    shown = [policy.allows(env.replace(face_up=item.face_up)) for item in zone.items]
    size_shown = size_policy.allows(env)
    if size_shown and zone.ordered:
        items = [
            to_json(i.value) if ok else HIDDEN for i, ok in zip(zone.items, shown, strict=True)
        ]
        return {"size": len(zone), "items": items}
    visible = [to_json(i.value) for i, ok in zip(zone.items, shown, strict=True) if ok]
    if size_shown:
        return {"size": len(zone), "items": visible}
    return {"items": visible} if visible else HIDDEN
