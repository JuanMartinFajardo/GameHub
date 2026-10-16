# SPDX-License-Identifier: Apache-2.0
"""Juegos de información perfecta: se resuelven recorriendo sus estados.

- `backward_induction`: **inducción hacia atrás** sobre el grafo de estados: el equilibrio perfecto
  en subjuegos de cualquier número de jugadores, de suma cero o no, con azar (cada asiento
  maximiza su pago esperado; los empates se deshacen a favor de la primera acción). Da el valor
  de cada posición.
- `alphabeta`: **minimax con poda alfa-beta** y tabla de transposiciones (por huella del estado)
  para dos jugadores de suma constante; en los nodos de azar, la esperanza (*expectimax*). No
  necesita guardar todo el grafo, así que llega más lejos. Admite profundidad limitada con una
  función de evaluación (la usarán las heurísticas de la fase 9).
- `solve`: elige uno de los dos.

Los juegos con jugadas simultáneas u ocultas no se pueden resolver así (quien elige después
«vería» lo que eligió el otro): para ellos, la forma normal o CFR.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

from gamehub.analysis.classify import classify
from gamehub.analysis.nash import GameShapeError
from gamehub.analysis.tree import (
    MAX_NODES,
    StateGraph,
    action_labels,
    initial_state,
    state_graph,
)
from gamehub.engine.game import Game
from gamehub.engine.state import State, Status

INF = float("inf")


class ImperfectInformation(GameShapeError):
    def __init__(self) -> None:
        super().__init__(
            "el juego tiene información imperfecta o jugadas simultáneas: no se puede resolver "
            "por inducción hacia atrás (usa la forma normal o CFR)"
        )


def require_perfect_information(state: State) -> None:
    if not classify(state.game.ir).perfect_information:
        raise ImperfectInformation()


@dataclass
class Solution:
    #: Valor del juego para cada asiento (esperado, si hay azar).
    value: tuple[Fraction, ...]
    #: Las jugadas óptimas en la raíz (etiquetas), si en ella decide alguien.
    best: list[str]
    #: Variación principal: una partida con juego óptimo (las etiquetas de cada paso; en el
    #: azar, el resultado más probable).
    pv: list[str]
    #: Estados distintos evaluados.
    states: int
    method: str
    #: Con la inducción hacia atrás: el valor de cada estado (por huella).
    values: dict[str, tuple[Fraction, ...]] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "value": [str(v) for v in self.value],
            "best": self.best,
            "pv": self.pv,
            "states": self.states,
            "method": self.method,
        }


def solve(
    game: Game | State,
    *,
    num_players: int | None = None,
    params: dict[str, Any] | None = None,
    max_nodes: int = MAX_NODES,
) -> Solution:
    """Alfa-beta si el juego es de dos jugadores y suma constante; si no, inducción hacia atrás."""
    state = initial_state(game, num_players, params)
    require_perfect_information(state)
    if state.n == 2 and classify(state.game.ir).zero_sum is not False:
        try:
            return alphabeta(state, max_nodes=max_nodes)
        except NotConstantSum:
            pass
    return backward_induction(state, max_nodes=max_nodes)


# --- Inducción hacia atrás -----------------------------------------------------------------------


def backward_induction(
    game: Game | State | StateGraph,
    *,
    num_players: int | None = None,
    params: dict[str, Any] | None = None,
    max_nodes: int = MAX_NODES,
) -> Solution:
    if isinstance(game, StateGraph):
        graph = game
    else:
        state = initial_state(game, num_players, params)
        require_perfect_information(state)
        graph = state_graph(state, max_nodes=max_nodes)
    if graph.cyclic:
        raise GameShapeError(
            "el grafo de estados tiene ciclos: la inducción hacia atrás necesita un juego finito "
            "sin repeticiones (análisis retrógrado: fase 8)"
        )
    n = graph.num_players
    values: list[tuple[Fraction, ...]] = [()] * graph.positions
    choice = [-1] * graph.positions
    for i in graph.order:
        kind = graph.kinds[i]
        kids = graph.children[i]
        if kind == "terminal":
            values[i] = graph.payoffs[i]
        elif kind == "chance":
            values[i] = tuple(
                sum(
                    (p * values[c][k] for p, c in zip(graph.probs[i], kids, strict=True)),
                    Fraction(0),
                )
                for k in range(n)
            )
        else:
            seat = graph.players[i]
            best = max(range(len(kids)), key=lambda a: (values[kids[a]][seat], -a))
            choice[i] = best
            values[i] = values[kids[best]]
    root = 0
    best_moves: list[str] = []
    if graph.kinds[root] == "decision":
        seat = graph.players[root]
        top = values[root][seat]
        best_moves = [
            graph.labels[root][a]
            for a, c in enumerate(graph.children[root])
            if values[c][seat] == top
        ]
    pv: list[str] = []
    i = root
    while graph.kinds[i] != "terminal":
        if graph.kinds[i] == "chance":
            a = max(range(len(graph.children[i])), key=lambda k: (graph.probs[i][k], -k))
        else:
            a = choice[i]
        pv.append(graph.labels[i][a])
        i = graph.children[i][a]
    return Solution(
        value=values[root],
        best=best_moves,
        pv=pv,
        states=graph.positions,
        method="backward_induction",
        values={graph.states[k].digest(): v for k, v in enumerate(values)},
    )


# --- Alfa-beta -----------------------------------------------------------------------------------


class NotConstantSum(GameShapeError):
    def __init__(self) -> None:
        super().__init__("los pagos de los finales no suman siempre lo mismo")


_EXACT, _LOWER, _UPPER = 0, 1, 2


class _Search:
    def __init__(
        self,
        max_nodes: int,
        evaluate: Callable[[State], Any] | None,
    ) -> None:
        self.table: dict[str, tuple[Any, int, int, int]] = {}
        self.total: Any = None
        self.max_nodes = max_nodes
        self.evaluate = evaluate
        self.visited = 0

    def terminal(self, state: State) -> Any:
        payoffs: tuple[Any, ...] = state.payoffs or ()
        total = sum(Fraction(p) for p in payoffs)
        if self.total is None:
            self.total = total
        elif total != self.total:
            raise NotConstantSum()
        return Fraction(payoffs[0])

    def value(self, state: State, alpha: Any, beta: Any, depth: int | None) -> Any:
        if state.status is Status.TERMINAL:
            return self.terminal(state)
        if depth == 0:
            if self.evaluate is None:
                raise ValueError("con profundidad limitada hace falta una función de evaluación")
            return Fraction(self.evaluate(state))
        key = state.digest()
        entry = self.table.get(key)
        hint = -1
        if entry is not None:
            v, flag, stored, hint = entry
            if depth is None or stored < 0 or stored >= depth:
                if flag == _EXACT:
                    return v
                if flag == _LOWER and v >= beta:
                    return v
                if flag == _UPPER and v <= alpha:
                    return v
        self.visited += 1
        if self.visited > self.max_nodes:
            from gamehub.analysis.tree import TooLarge

            raise TooLarge("la búsqueda alfa-beta", self.max_nodes)
        down = None if depth is None else depth - 1
        if state.status is Status.CHANCE:
            v = sum(
                (
                    p * self.value(state.apply_chance(o), -INF, INF, down)
                    for o, p in state.chance_outcomes()
                ),
                Fraction(0),
            )
            self.table[key] = (v, _EXACT, -1 if depth is None else depth, -1)
            return v
        seat = state.active_seats[0]
        actions = state.legal_actions(seat)
        order = list(range(len(actions)))
        if 0 <= hint < len(actions):
            order.remove(hint)
            order.insert(0, hint)
        maximizing = seat == 0
        a0, b0 = alpha, beta
        best: Any = -INF if maximizing else INF
        best_index = order[0]
        for k in order:
            v = self.value(state.apply_action(seat, actions[k]), alpha, beta, down)
            if (maximizing and v > best) or (not maximizing and v < best):
                best, best_index = v, k
            if maximizing:
                alpha = max(alpha, v)
            else:
                beta = min(beta, v)
            if alpha >= beta:
                break
        flag = _EXACT
        if best <= a0:
            flag = _UPPER
        elif best >= b0:
            flag = _LOWER
        self.table[key] = (best, flag, -1 if depth is None else depth, best_index)
        return best


def alphabeta(
    game: Game | State,
    *,
    num_players: int | None = None,
    params: dict[str, Any] | None = None,
    max_depth: int | None = None,
    evaluate: Callable[[State], Any] | None = None,
    max_nodes: int = MAX_NODES,
) -> Solution:
    """Minimax con poda alfa-beta para dos jugadores de suma constante (el valor es el del
    asiento 0; el del 1 es la constante menos ese). `evaluate(state)` estima el valor para el
    asiento 0 cuando se agota `max_depth`."""
    state = initial_state(game, num_players, params)
    require_perfect_information(state)
    if state.n != 2:
        raise GameShapeError("alfa-beta es para dos jugadores (usa la inducción hacia atrás)")
    search = _Search(max_nodes, evaluate)
    v0 = search.value(state, -INF, INF, max_depth)
    best: list[str] = []
    if state.status is Status.DECISION:
        seat = state.active_seats[0]
        actions = state.legal_actions(seat)
        labels = action_labels(actions)
        down = None if max_depth is None else max_depth - 1
        for k, a in enumerate(actions):
            if search.value(state.apply_action(seat, a), -INF, INF, down) == v0:
                best.append(labels[k])
    pv = _principal_variation(state, search)
    total = search.total if search.total is not None else Fraction(0)
    return Solution(
        value=(v0, total - v0),
        best=best,
        pv=pv,
        states=len(search.table),
        method="alphabeta",
    )


def _principal_variation(state: State, search: _Search) -> list[str]:
    pv: list[str] = []
    seen: set[str] = set()
    while state.status is not Status.TERMINAL:
        key = state.digest()
        if key in seen:
            break
        seen.add(key)
        if state.status is Status.CHANCE:
            outcomes = state.chance_outcomes()
            outcome, _ = max(outcomes, key=lambda op: op[1])
            from gamehub.analysis.tree import chance_label

            child = state.apply_chance(outcome)
            pv.append(chance_label(child, outcome))
            state = child
            continue
        entry = search.table.get(key)
        if entry is None or entry[3] < 0:
            break
        seat = state.active_seats[0]
        actions = state.legal_actions(seat)
        pv.append(action_labels(actions)[entry[3]])
        state = state.apply_action(seat, actions[entry[3]])
    return pv
