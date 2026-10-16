# SPDX-License-Identifier: Apache-2.0
"""Estrategias de comportamiento sobre la forma extensiva: valor esperado, mejor respuesta y
explotabilidad.

Una política (`Policy`) da, para cada conjunto de información, la probabilidad de cada acción.
La aritmética es la de los números que se le den: racionales (resultados exactos, p. ej. con la
forma de secuencias) o `float` (CFR).

- `expected_values`: el pago esperado de cada asiento si todos siguen la política.
- `best_response`: la mejor respuesta pura de un asiento contra la política de los demás y lo que
  cobra con ella. Con recuerdo perfecto basta un recorrido: en cada conjunto se elige la acción
  que maximiza la suma, sobre sus nodos, de la probabilidad de llegar a ellos por el azar y los
  demás por el valor de seguir desde allí; los conjuntos posteriores del mismo asiento solo
  dependen de esa elección, así que no hay ciclos.
- `nash_conv` = Σ (mejor respuesta − valor de la política) y `exploitability` = nash_conv / n (la
  convención de OpenSpiel). Son 0 exactamente en un equilibrio de Nash.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from gamehub.analysis.tree import GameTree

Policy = dict[int, list[Any]]


def uniform_policy(tree: GameTree) -> Policy:
    return {s.id: [Fraction(1, len(s.actions))] * len(s.actions) for s in tree.infosets}


def pure_policy(tree: GameTree, choices: dict[int, int]) -> Policy:
    return {
        s.id: [Fraction(1 if a == choices.get(s.id, 0) else 0) for a in range(len(s.actions))]
        for s in tree.infosets
    }


def merge(tree: GameTree, policies: list[Policy]) -> Policy:
    """Una política conjunta: la de cada asiento sale de `policies[asiento]`."""
    return {s.id: policies[s.player][s.id] for s in tree.infosets}


def expected_values(tree: GameTree, policy: Policy) -> tuple[Any, ...]:
    n = tree.num_players
    totals: list[Any] = [0] * n
    stack: list[tuple[int, Any]] = [(0, 1)]
    nodes = tree.nodes
    while stack:
        h, reach = stack.pop()
        if not reach:
            continue
        node = nodes[h]
        if node.kind == "terminal":
            for k in range(n):
                totals[k] += reach * node.payoffs[k]
        elif node.kind == "chance":
            stack.extend((c, reach * p) for c, p in zip(node.children, node.probs, strict=True))
        else:
            probs = policy[node.infoset]
            stack.extend((c, reach * q) for c, q in zip(node.children, probs, strict=True))
    return tuple(totals)


@dataclass(frozen=True)
class BestResponse:
    player: int
    value: Any
    #: La acción elegida en cada conjunto de información del asiento.
    choices: dict[int, int]


def best_response(tree: GameTree, policy: Policy, player: int) -> BestResponse:
    nodes = tree.nodes
    # Probabilidad de llegar a cada nodo por el azar y los demás asientos.
    reach: list[Any] = [0] * len(nodes)
    reach[0] = 1
    for h, node in enumerate(nodes):  # los padres van antes que los hijos (preorden)
        if node.kind == "terminal" or not reach[h]:
            continue
        if node.kind == "chance":
            weights = node.probs
        elif node.player == player:
            weights = [1] * len(node.children)
        else:
            weights = policy[node.infoset]
        for c, w in zip(node.children, weights, strict=True):
            reach[c] = reach[h] * w
    values: dict[int, Any] = {}
    choices: dict[int, int] = {}

    def choose(infoset: int) -> int:
        if infoset not in choices:
            info = tree.infosets[infoset]
            scores = [
                sum((reach[h] * value(nodes[h].children[a]) for h in info.nodes), Fraction(0))
                for a in range(len(info.actions))
            ]
            choices[infoset] = max(range(len(scores)), key=lambda a: (scores[a], -a))
        return choices[infoset]

    def value(h: int) -> Any:
        cached = values.get(h)
        if cached is not None:
            return cached
        node = nodes[h]
        if node.kind == "terminal":
            out: Any = node.payoffs[player]
        elif node.kind == "chance":
            out = sum(
                (p * value(c) for c, p in zip(node.children, node.probs, strict=True)),
                Fraction(0),
            )
        elif node.player == player:
            out = value(node.children[choose(node.infoset)])
        else:
            probs = policy[node.infoset]
            out = sum(
                (q * value(c) for c, q in zip(node.children, probs, strict=True) if q),
                Fraction(0),
            )
        values[h] = out
        return out

    total = value(0)
    for info in tree.infosets_of(player):  # también los conjuntos que la respuesta no alcanza
        choose(info.id)
    return BestResponse(player, total, dict(choices))


def nash_conv(tree: GameTree, policy: Policy) -> Any:
    on_policy = expected_values(tree, policy)
    return sum(
        (best_response(tree, policy, k).value - on_policy[k] for k in range(tree.num_players)),
        Fraction(0),
    )


def exploitability(tree: GameTree, policy: Policy) -> Any:
    return nash_conv(tree, policy) / tree.num_players


def policy_json(tree: GameTree, policy: Policy) -> list[dict[str, Any]]:
    """La política por conjuntos de información, para mostrarla (las probabilidades en texto)."""
    return [
        {
            "infoset": s.id,
            "player": s.player,
            "description": s.description,
            "actions": s.labels,
            "probs": [_number(q) for q in policy[s.id]],
        }
        for s in tree.infosets
    ]


def _number(q: Any) -> str | float:
    return str(q) if isinstance(q, Fraction | int) else round(float(q), 6)
