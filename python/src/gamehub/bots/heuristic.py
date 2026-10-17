# SPDX-License-Identifier: Apache-2.0
"""Heurísticas (ADR-083): el conocimiento del juego que no es una regla, evaluado con el motor de
referencia.

Una heurística de la IR (`heuristics`, la sección `heuristic Nombre { … }` de Nomos) tiene:

- **rasgos** (`feature`): números que miden un estado desde el asiento `me`; la **evaluación** es
  su suma ponderada (`weights`, 1 si falta), exacta;
- **reglas de prioridad** (`prefer accion(p) when …`): la primera que cumple una acción le da su
  prioridad (0 la más alta);
- **orden** (`order accion(p) by …`): la puntuación de una acción (mayor = antes; 0 si no tiene).

La clave de una acción es `(prioridad, puntuación)`: los bots de reglas eligen la mejor, las
búsquedas exploran en ese orden y MCTS la usa en sus simulaciones. El núcleo C++ evalúa lo mismo
(`gamehub_core`, comprobado contra esta implementación en los tests).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from gamehub.engine.env import Ctx, Env
from gamehub.engine.game import Game, GameDef
from gamehub.engine.state import Action, State
from gamehub.ir.hashing import heuristic_hash

#: Prioridad de una acción que no cumple ninguna regla `prefer`.
NO_PRIORITY = 1 << 30

Compiled = Callable[[Env], Any]


@dataclass(frozen=True)
class Feature:
    name: str
    weight: Fraction
    body: Compiled


@dataclass(frozen=True)
class Rule:
    params: tuple[str, ...]
    expr: Compiled


def heuristic_names(ir: dict[str, Any]) -> list[str]:
    return [h["name"] for h in ir.get("heuristics", [])]


def find_heuristic(ir: dict[str, Any], name: str | None = None) -> dict[str, Any]:
    """La heurística `name` del juego (la primera si no se da)."""
    found = ir.get("heuristics", [])
    if not found:
        raise KeyError(f"el juego {ir['game']['id']} no tiene heurísticas")
    if name is None:
        return found[0]
    for h in found:
        if h["name"] == name:
            return h
    names = ", ".join(h["name"] for h in found)
    raise KeyError(f"el juego {ir['game']['id']} no tiene la heurística {name} (tiene: {names})")


def constant(expr: Any) -> Fraction:
    """El valor de un peso (`["const", n]` o `["rat", n, d]`)."""
    if expr[0] == "const":
        return Fraction(expr[1])
    return Fraction(expr[1], expr[2])


class Heuristic:
    """Una heurística de un juego, para estados del motor de referencia."""

    def __init__(self, game: Game, name: str | None = None) -> None:
        ir = game.ir
        h = find_heuristic(ir, name)
        self.name: str = h["name"]
        self.hash = heuristic_hash(ir, self.name)
        # Las funciones propias de la heurística se compilan junto a las del juego, en una
        # definición aparte: las de las reglas no cambian.
        functions = [*ir.get("functions", []), *h.get("functions", [])]
        self.defn = GameDef({**ir, "functions": functions}) if h.get("functions") else game.defn
        compile_ = self.defn.exprs.compile
        self.features = [
            Feature(
                f["name"],
                constant(f["weight"]) if "weight" in f else Fraction(1),
                compile_(f["body"]),
            )
            for f in h.get("features", [])
        ]
        self.prefer: dict[str, list[tuple[int, Rule]]] = {}
        for rank, rule in enumerate(h.get("prefer", [])):
            self.prefer.setdefault(rule["action"], []).append(
                (rank, Rule(tuple(rule["params"]), compile_(rule["when"])))
            )
        self.order: dict[str, list[Rule]] = {}
        for rule in h.get("order", []):
            self.order.setdefault(rule["action"], []).append(
                Rule(tuple(rule["params"]), compile_(rule["key"]))
            )

    # --- evaluación -----------------------------------------------------------------------------

    def _env(self, state: State, args: dict[str, Any]) -> Env:
        ctx = Ctx(self.defn, state.store, state.params, state.n, state._path(), memo={})
        return Env(ctx, args=args)

    def feature_values(self, state: State, seat: int) -> dict[str, Any]:
        env = self._env(state, {"me": seat})
        return {f.name: f.body(env) for f in self.features}

    def evaluate(self, state: State, seat: int) -> Fraction:
        """Suma ponderada de los rasgos desde `seat` (exacta)."""
        env = self._env(state, {"me": seat})
        return sum((f.weight * f.body(env) for f in self.features), Fraction(0))

    def _args(self, rule: Rule, seat: int, action: Action) -> dict[str, Any]:
        args = {"me": seat}
        for name, (_, value) in zip(rule.params, action.args, strict=True):
            args[name] = value
        return args

    def priority(self, state: State, seat: int, action: Action) -> int:
        """Índice de la primera regla `prefer` que cumple la acción (`NO_PRIORITY` si ninguna)."""
        for rank, rule in self.prefer.get(action.name, ()):
            if rule.expr(self._env(state, self._args(rule, seat, action))):
                return rank
        return NO_PRIORITY

    def score(self, state: State, seat: int, action: Action) -> Fraction:
        """Suma de las claves `order` de la acción (0 si no tiene)."""
        total = Fraction(0)
        for rule in self.order.get(action.name, ()):
            total += rule.expr(self._env(state, self._args(rule, seat, action)))
        return total

    def key(self, state: State, seat: int, action: Action) -> tuple[int, Fraction]:
        """Clave de orden de una acción: menor = mejor (`(prioridad, -puntuación)`)."""
        return self.priority(state, seat, action), -self.score(state, seat, action)

    def ordered(self, state: State, seat: int, actions: Sequence[Action]) -> list[Action]:
        """Las acciones de mejor a peor (estable: a igual clave, el orden legal)."""
        keys = [self.key(state, seat, a) for a in actions]
        return [actions[i] for i in sorted(range(len(actions)), key=keys.__getitem__)]
