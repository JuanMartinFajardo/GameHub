# SPDX-License-Identifier: Apache-2.0
"""El simulador del Studio: probar un juego mientras se diseña.

- Una **simulación** guarda la historia completa de estados (son inmutables): se puede volver a
  cualquier paso (viaje en el tiempo) y jugar desde ahí, como cualquier asiento; el azar se elige
  o se sortea.
- **Correr** avanza con jugadores automáticos (al azar o la primera acción) hasta el final, hasta
  un **punto de ruptura** (llegar a un nodo o que se cumpla una condición) o un máximo de pasos.
- **Partidas masivas** (playouts): estadísticas, errores de reglas y **cobertura** de reglas
  (cuántas veces se llega a cada nodo, se juega cada acción y se sigue cada transición).
- **Árbol** del juego desde un estado (para juegos pequeños) y **tamaño estimado** del árbol
  completo con el estimador de Knuth (paseos al azar ponderados por la inversa de su probabilidad).

Todo usa el motor de referencia; las trazas de transiciones salen de `gamehub.engine.state.TRACE`,
que no cambia la semántica.
"""

from __future__ import annotations

import math
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from fractions import Fraction
from itertools import islice
from typing import Any

from gamehub.engine import PASS, Action, Game, IllegalAction, State, Status
from gamehub.engine.errors import RuleError
from gamehub.engine.rng import STREAM_AGENT_BASE, STREAM_CHANCE, NotEnumerable, Pcg32
from gamehub.engine.state import TRACE
from gamehub.engine.values import to_json

#: Acciones legales que se enumeran por asiento (más: construcción progresiva).
LEGAL_LIMIT = 500
#: Resultados de azar que se enumeran para elegir a mano.
CHANCE_LIMIT = 200


class SimError(Exception):
    pass


@dataclass
class Step:
    """Lo que llevó de un estado al siguiente."""

    kind: str  # start | action | chance
    seat: int | None = None
    action: dict[str, Any] | None = None
    outcome: list[int] | None = None
    #: Transiciones seguidas y nodos alcanzados en el paso.
    trace: list[list[str]] = field(default_factory=list)
    nodes: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"kind": self.kind, "trace": self.trace, "nodes": self.nodes}
        if self.seat is not None:
            out["seat"] = self.seat
        if self.action is not None:
            out["action"] = self.action
        if self.outcome is not None:
            out["outcome"] = self.outcome
        return out


def _traced(run: Callable[[], State]) -> tuple[State, list[list[str]]]:
    trace: list[tuple[str, ...]] = []
    token = TRACE.set(trace)
    try:
        state = run()
    finally:
        TRACE.reset(token)
    return state, [list(k) for k in trace]


def _nodes_of(state: State) -> list[str]:
    return [e["node"] for e in state.events(None) if e.get("type") == "node"]


def action_json(action: Action) -> dict[str, Any]:
    return action.to_json()


class Condition:
    """Un punto de ruptura: llegar a un nodo o que se cumpla una expresión (ya compilada a la
    IR) sobre el estado."""

    def __init__(self, *, node: str | None = None, expr: Any = None, label: str = "") -> None:
        self.node = node
        self.expr = expr
        self.label = label or (node or "condición")

    def hit(self, state: State, step: Step) -> bool:
        if self.node is not None:
            return self.node in step.nodes
        try:
            return state.evaluate(self.expr) is True
        except RuleError:
            return False


class Simulation:
    def __init__(
        self,
        game: Game,
        *,
        players: int | None = None,
        params: dict[str, Any] | None = None,
        seed: int = 0,
    ) -> None:
        self.game = game
        self.players = players or game.players[0]
        self.params = dict(params or {})
        self.seed = seed
        self.rng = Pcg32(seed, STREAM_CHANCE)
        self.agents = [Pcg32(seed, STREAM_AGENT_BASE + s) for s in range(self.players)]
        state, trace = _traced(lambda: game.new_state(self.players, self.params))
        self.states: list[State] = [state]
        self.steps: list[Step] = [Step("start", trace=trace, nodes=_nodes_of(state))]
        self.error: dict[str, Any] | None = None

    # --- historia -------------------------------------------------------------------------------

    def state(self, index: int | None = None) -> State:
        i = len(self.states) - 1 if index is None else index
        if not 0 <= i < len(self.states):
            raise SimError(f"no hay paso {i}")
        return self.states[i]

    def _push(self, index: int, state: State, step: Step) -> int:
        del self.states[index + 1 :]
        del self.steps[index + 1 :]
        self.states.append(state)
        self.steps.append(step)
        self.error = None
        return len(self.states) - 1

    def act(self, index: int, seat: int, data: dict[str, Any]) -> int:
        state = self.state(index)
        try:
            action = state.decode_action(seat, data)
            reason = state.illegal_reason(seat, action)
            if reason is not None:
                raise SimError(f"jugada ilegal: {reason}")
            new, trace = _traced(lambda: state.apply_action(seat, action))
        except (IllegalAction, ValueError, KeyError, TypeError) as exc:
            raise SimError(f"jugada no válida: {exc}") from None
        except RuleError as exc:
            self.error = {"message": str(exc), "node": state.node, "index": index}
            raise SimError(f"error de reglas: {exc}") from None
        step = Step("action", seat, action_json(action), trace=trace, nodes=_nodes_of(new))
        return self._push(index, new, step)

    def chance(self, index: int, outcome: list[int] | None = None) -> int:
        state = self.state(index)
        if state.status is not Status.CHANCE:
            raise SimError("aquí no hay azar que resolver")
        try:
            chosen = tuple(outcome) if outcome is not None else state.sample_chance(self.rng)
            new, trace = _traced(lambda: state.apply_chance(chosen))
        except IllegalAction as exc:
            raise SimError(f"resultado de azar no válido: {exc}") from None
        except RuleError as exc:
            self.error = {"message": str(exc), "node": state.node, "index": index}
            raise SimError(f"error de reglas: {exc}") from None
        step = Step("chance", outcome=list(chosen), trace=trace, nodes=_nodes_of(new))
        return self._push(index, new, step)

    def auto_step(self, index: int, policies: dict[int, str]) -> int:
        """Un paso automático: el azar se sortea y el primer asiento que puede jugar elige con su
        política (`random` o `first`)."""
        state = self.state(index)
        if state.status is Status.CHANCE:
            return self.chance(index)
        if state.status is Status.TERMINAL:
            raise SimError("la partida ha terminado")
        seat = state.active_seats[0]
        legal = state.legal_actions(seat)
        if not legal:
            raise SimError(f"el asiento {seat} no tiene jugadas")
        policy = policies.get(seat, "random")
        action = legal[0] if policy == "first" else legal[self.agents[seat].below(len(legal))]
        return self.act(index, seat, action_json(action))

    def run(
        self,
        index: int,
        *,
        policies: dict[int, str] | None = None,
        breakpoints: list[Condition] | None = None,
        max_steps: int = 10_000,
        stop_at_humans: set[int] | None = None,
    ) -> tuple[int, str, str | None]:
        """Avanza solo hasta el final, un punto de ruptura, un asiento humano o `max_steps`.
        Devuelve el paso al que llegó, por qué paró (`end`, `breakpoint`, `human`, `limit`,
        `error`) y la etiqueta del punto de ruptura."""
        current = index
        humans = stop_at_humans or set()
        for _ in range(max_steps):
            state = self.state(current)
            if state.status is Status.TERMINAL:
                return current, "end", None
            if state.status is Status.DECISION and humans & set(state.active_seats):
                return current, "human", None
            try:
                current = self.auto_step(current, policies or {})
            except SimError:
                if self.error is not None:
                    return current, "error", None
                raise
            for bp in breakpoints or []:
                if bp.hit(self.states[current], self.steps[current]):
                    return current, "breakpoint", bp.label
        return current, "limit", None

    def reload(self, game: Game) -> int:
        """Cambia las reglas y repite la historia con las nuevas mientras se pueda. Devuelve
        cuántos pasos se conservaron."""
        old_steps = self.steps[1:]
        self.game = game
        state, trace = _traced(lambda: game.new_state(self.players, self.params))
        self.states = [state]
        self.steps = [Step("start", trace=trace, nodes=_nodes_of(state))]
        self.error = None
        kept = 0
        for step in old_steps:
            try:
                if step.kind == "chance" and step.outcome is not None:
                    self.chance(len(self.states) - 1, step.outcome)
                elif step.kind == "action" and step.seat is not None and step.action is not None:
                    self.act(len(self.states) - 1, step.seat, step.action)
                else:
                    break
            except SimError:
                break
            kept += 1
        return kept

    # --- vistas ---------------------------------------------------------------------------------

    def snapshot(self, index: int, seats: list[int] | None = None) -> dict[str, Any]:
        state = self.state(index)
        seats = list(range(self.players)) if seats is None else seats
        out: dict[str, Any] = {
            "index": index,
            "length": len(self.states),
            "status": state.status.value,
            "node": state.node,
            "path": _path(state),
            "active": list(state.active_seats),
            "omniscient": state.view(None),
            "views": {str(s): state.view(s) for s in seats},
            "public": state.view(-1),
            "events": {str(s): state.events(s) for s in seats},
            "allEvents": state.events(None),
            "step": self.steps[index].to_json(),
            "legal": {str(s): self.legal(state, s) for s in state.active_seats},
            "error": self.error if self.error and self.error.get("index") == index else None,
        }
        if state.status is Status.CHANCE:
            out["chance"] = self.chance_options(state)
        if state.payoffs is not None:
            out["payoffs"] = [to_json(p) for p in state.payoffs]
            out["ranking"] = list(state.ranking() or [])
        return out

    def legal(self, state: State, seat: int) -> dict[str, Any]:
        found = list(islice(state.iter_legal_actions(seat), LEGAL_LIMIT + 1))
        if len(found) > LEGAL_LIMIT:
            return {"kind": "progressive", "names": list(state.options(seat))}
        return {"kind": "enumerated", "actions": [action_json(a) for a in found]}

    def options(
        self, index: int, seat: int, name: str | None, args: dict[str, Any] | None
    ) -> list[Any]:
        state = self.state(index)
        if name is None:
            return list(state.options(seat))
        if name == PASS.name:
            return []
        typed = self.game.decode_arguments(state.node, name, args or {})
        return [to_json(v) for v in state.options(seat, name, typed)]

    def chance_options(self, state: State) -> dict[str, Any]:
        try:
            outcomes = state.chance_outcomes(CHANCE_LIMIT)
        except NotEnumerable:
            return {"enumerable": False}
        return {
            "enumerable": True,
            "outcomes": [
                {"outcome": list(o), "probability": str(p), "value": float(p)} for o, p in outcomes
            ],
        }

    def timeline(self) -> list[dict[str, Any]]:
        out = []
        for i, (state, step) in enumerate(zip(self.states, self.steps, strict=True)):
            out.append(
                {"index": i, "node": state.node, "status": state.status.value, **step.to_json()}
            )
        return out


def _path(state: State) -> list[str]:
    if state.node is None:
        return []
    node = state.game.nodes[state.node]
    return [*node.ancestors, node.id]


# --- Partidas masivas y cobertura -----------------------------------------------------------------


@dataclass
class Coverage:
    nodes: Counter[str] = field(default_factory=Counter)
    actions: Counter[str] = field(default_factory=Counter)  # "nodo.acción"
    transitions: Counter[str] = field(default_factory=Counter)  # "node/N/i" o "action/N/a/i"

    def add_step(
        self, state: State, trace: list[tuple[str, ...]], action: Action | None, node: str | None
    ) -> None:
        for e in state.events(None):
            if e.get("type") == "node":
                self.nodes[e["node"]] += 1
        for key in trace:
            self.transitions["/".join(key)] += 1
        if action is not None and node is not None and action.name != PASS.name:
            self.actions[f"{node}.{action.name}"] += 1

    def to_json(self) -> dict[str, Any]:
        return {
            "nodes": dict(self.nodes),
            "actions": dict(self.actions),
            "transitions": dict(self.transitions),
        }


def playouts(
    game: Game,
    *,
    games: int = 100,
    players: int | None = None,
    params: dict[str, Any] | None = None,
    seed: int = 0,
    max_steps: int = 10_000,
    time_limit: float = 10.0,
    should_stop: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Partidas al azar: resultados, longitudes, errores de reglas y cobertura."""
    n = players or game.players[0]
    coverage = Coverage()
    lengths: list[int] = []
    totals = [Fraction(0)] * n
    wins = [0] * n
    draws = 0
    errors: list[dict[str, Any]] = []
    finished = truncated = 0
    started = time.perf_counter()
    played = 0
    for g in range(games):
        if time.perf_counter() - started > time_limit or (should_stop and should_stop()):
            break
        played += 1
        rng = Pcg32(seed + g, STREAM_CHANCE)
        agents = Pcg32(seed + g, STREAM_AGENT_BASE)
        trace: list[tuple[str, ...]] = []
        token = TRACE.set(trace)
        try:
            state = game.new_state(n, params or {})
            coverage.add_step(state, trace, None, None)
            steps = 0
            while not state.is_terminal and steps < max_steps:
                trace.clear()
                if state.status is Status.CHANCE:
                    state = state.apply_chance(state.sample_chance(rng))
                    coverage.add_step(state, trace, None, None)
                else:
                    seat = state.active_seats[0]
                    legal = state.legal_actions(seat)
                    action = legal[agents.below(len(legal))]
                    node = state.node
                    state = state.apply_action(seat, action)
                    coverage.add_step(state, trace, action, node)
                steps += 1
        except RuleError as exc:
            if len(errors) < 20:
                errors.append({"game": g, "message": str(exc), "node": getattr(exc, "node", None)})
            continue
        finally:
            TRACE.reset(token)
        if state.is_terminal and state.payoffs is not None:
            finished += 1
            lengths.append(steps)
            for s, p in enumerate(state.payoffs):
                totals[s] += Fraction(p)
            ranking = state.ranking() or []
            if ranking and all(r == 1 for r in ranking):
                draws += 1  # todos primeros: un empate, no una victoria de cada uno
            else:
                for s, r in enumerate(ranking):
                    if r == 1:
                        wins[s] += 1
        else:
            truncated += 1
    return {
        "games": played,
        "finished": finished,
        "truncated": truncated,
        "errors": errors,
        "errorCount": played - finished - truncated,
        "length": _stats(lengths),
        "payoffMean": [float(t / finished) if finished else None for t in totals],
        "winRate": [w / finished if finished else None for w in wins],
        "drawRate": draws / finished if finished else None,
        "coverage": coverage.to_json(),
        "seconds": round(time.perf_counter() - started, 3),
    }


def _stats(values: list[int]) -> dict[str, Any]:
    if not values:
        return {"min": None, "max": None, "mean": None}
    return {"min": min(values), "max": max(values), "mean": sum(values) / len(values)}


# --- Árbol del juego y tamaño ---------------------------------------------------------------------


def children(state: State, limit: int = 200) -> list[dict[str, Any]]:
    """Los sucesores de un estado: una jugada de cada asiento activo o un resultado de azar."""
    out: list[dict[str, Any]] = []
    if state.status is Status.TERMINAL:
        return out
    if state.status is Status.CHANCE:
        try:
            outcomes = state.chance_outcomes(limit)
        except NotEnumerable:
            return [{"kind": "chance", "label": f"más de {limit} resultados", "truncated": True}]
        for o, p in outcomes:
            out.append({"kind": "chance", "outcome": list(o), "probability": str(p)})
        return out
    for seat in state.active_seats:
        for action in islice(state.iter_legal_actions(seat), limit):
            out.append({"kind": "action", "seat": seat, "action": action_json(action)})
    return out[:limit]


def follow(state: State, choice: dict[str, Any]) -> State:
    if choice["kind"] == "chance":
        return state.apply_chance(tuple(choice["outcome"]))
    action = state.decode_action(choice["seat"], choice["action"])
    return state.apply_action(choice["seat"], action)


def tree(state: State, path: list[int], *, limit: int = 200) -> dict[str, Any]:
    """El nodo del árbol al que se llega desde `state` siguiendo `path` (índices de hijos), con
    sus hijos (sin expandir)."""
    current = state
    for i in path:
        options = children(current, limit)
        if not 0 <= i < len(options) or options[i].get("truncated"):
            raise SimError("camino no válido en el árbol")
        current = follow(current, options[i])
    info: dict[str, Any] = {
        "path": path,
        "node": current.node,
        "status": current.status.value,
        "active": list(current.active_seats),
        "children": children(current, limit),
    }
    if current.payoffs is not None:
        info["payoffs"] = [to_json(p) for p in current.payoffs]
    return info


def count_tree(state: State, *, budget: int = 200_000, time_limit: float = 3.0) -> dict[str, Any]:
    """Cuenta el árbol completo desde `state` (juegos pequeños): estados, finales y profundidad.
    `complete: False` si se pasó del presupuesto de estados o de tiempo."""
    seen = 0
    terminals = 0
    depth = 0
    deadline = time.perf_counter() + time_limit
    stack: list[tuple[State, int]] = [(state, 0)]
    while stack:
        current, d = stack.pop()
        seen += 1
        depth = max(depth, d)
        if seen > budget or (seen % 1000 == 0 and time.perf_counter() > deadline):
            return {"complete": False, "states": seen, "terminals": terminals, "depth": depth}
        if current.is_terminal:
            terminals += 1
            continue
        for choice in children(current, 10_000):
            if choice.get("truncated"):
                return {"complete": False, "states": seen, "terminals": terminals, "depth": depth}
            stack.append((follow(current, choice), d + 1))
    return {"complete": True, "states": seen, "terminals": terminals, "depth": depth}


def estimate_size(
    game: Game,
    *,
    players: int | None = None,
    params: dict[str, Any] | None = None,
    samples: int = 200,
    seed: int = 0,
    max_steps: int = 10_000,
    time_limit: float = 5.0,
) -> dict[str, Any]:
    """Tamaño estimado del árbol del juego (número de estados) con el estimador de Knuth: en un
    paseo al azar, cada estado cuenta como 1/P(llegar a él); la media sobre muchos paseos es un
    estimador sin sesgo. Devuelve log10 del tamaño (los árboles crecen deprisa) y la longitud y el
    factor de ramificación medios."""
    n = players or game.players[0]
    totals: list[float] = []  # log10 de la estimación de cada paseo
    lengths: list[int] = []
    branching: list[int] = []
    started = time.perf_counter()
    for k in range(samples):
        if time.perf_counter() - started > time_limit:
            break
        rng = Pcg32(seed + k, STREAM_CHANCE)
        agents = Pcg32(seed + k, STREAM_AGENT_BASE)
        state = game.new_state(n, params or {})
        weight = 0.0  # log10 de 1/P(camino)
        log_terms = [0.0]
        steps = 0
        try:
            while not state.is_terminal and steps < max_steps:
                if state.status is Status.CHANCE:
                    outcome = state.sample_chance(rng)
                    p = state.outcome_probability(outcome)
                    weight += -math.log10(p) if p > 0 else 0.0
                    state = state.apply_chance(outcome)
                else:
                    seat = state.active_seats[0]
                    legal = state.legal_actions(seat)
                    branching.append(len(legal))
                    weight += math.log10(len(legal))
                    state = state.apply_action(seat, legal[agents.below(len(legal))])
                log_terms.append(weight)
                steps += 1
        except RuleError:
            continue
        top = max(log_terms)
        total = top + math.log10(sum(10 ** (t - top) for t in log_terms))
        totals.append(total)
        lengths.append(steps)
    if not totals:
        return {"samples": 0}
    top = max(totals)
    mean = top + math.log10(sum(10 ** (t - top) for t in totals) / len(totals))
    return {
        "samples": len(totals),
        "log10States": round(mean, 2),
        "states": _scientific(mean),
        "meanLength": sum(lengths) / len(lengths),
        "meanBranching": (sum(branching) / len(branching)) if branching else None,
        "seconds": round(time.perf_counter() - started, 3),
    }


def _scientific(log10: float) -> str:
    if log10 < 6:
        return f"{round(10**log10):,}".replace(",", " ")
    exponent = math.floor(log10)
    mantissa = 10 ** (log10 - exponent)
    return f"{mantissa:.1f}·10^{exponent}"
