# SPDX-License-Identifier: Apache-2.0
"""Minimización del arrepentimiento contrafactual (CFR) tabular sobre la forma extensiva.

`CFR(tree)` mantiene, para cada conjunto de información, el arrepentimiento acumulado de cada
acción y la suma de las estrategias jugadas; la estrategia media converge a un equilibrio de Nash
en los juegos de dos jugadores de suma cero (y la explotabilidad lo mide). Con `plus=True`,
**CFR+** (Tammelin, 2014): los arrepentimientos acumulados no bajan de 0 (*regret matching+*) y la
media pondera cada iteración por su número; converge mucho más deprisa. Las actualizaciones son
alternas (un asiento por pasada) y en coma flotante: la exactitud la da la forma de secuencias.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from gamehub.analysis.policy import Policy, exploitability
from gamehub.analysis.tree import GameTree

_TERMINAL, _CHANCE, _DECISION = 0, 1, 2


@dataclass
class Convergence:
    #: (iteración, explotabilidad de la estrategia media) en los puntos medidos.
    points: list[tuple[int, float]] = field(default_factory=list)


class CFR:
    def __init__(self, tree: GameTree, *, plus: bool = False) -> None:
        self.tree = tree
        self.plus = plus
        self.iteration = 0
        nodes = tree.nodes
        self.kind = [
            _TERMINAL if n.kind == "terminal" else _CHANCE if n.kind == "chance" else _DECISION
            for n in nodes
        ]
        self.children = [n.children for n in nodes]
        self.player = [n.player for n in nodes]
        self.infoset = [n.infoset for n in nodes]
        self.probs = [[float(p) for p in n.probs] for n in nodes]
        self.payoffs = [tuple(float(u) for u in n.payoffs) for n in nodes]
        sizes = [len(s.actions) for s in tree.infosets]
        self.regret = [[0.0] * k for k in sizes]
        self.strategy_sum = [[0.0] * k for k in sizes]
        self.convergence = Convergence()

    def current(self, infoset: int) -> list[float]:
        """Estrategia actual por *regret matching*."""
        regrets = self.regret[infoset]
        positive = [r if r > 0 else 0.0 for r in regrets]
        total = sum(positive)
        if total > 0:
            return [r / total for r in positive]
        return [1.0 / len(regrets)] * len(regrets)

    def run(self, iterations: int, *, measure_every: int = 0) -> Convergence:
        """Ejecuta `iterations` iteraciones; con `measure_every`, anota la explotabilidad de la
        estrategia media cada tantas (y al final)."""
        for _ in range(iterations):
            self.iteration += 1
            for player in range(self.tree.num_players):
                sigma = [self.current(i) for i in range(len(self.regret))]
                self._traverse(0, player, 1.0, 1.0, sigma)
                if self.plus:
                    for s in self.tree.infosets:
                        if s.player == player:
                            self.regret[s.id] = [r if r > 0 else 0.0 for r in self.regret[s.id]]
            if measure_every and (
                self.iteration % measure_every == 0 or self.iteration == iterations
            ):
                self.convergence.points.append(
                    (self.iteration, float(exploitability(self.tree, self.average())))
                )
        return self.convergence

    def _traverse(
        self, h: int, player: int, pi_i: float, pi_o: float, sigma: list[list[float]]
    ) -> float:
        kind = self.kind[h]
        if kind == _TERMINAL:
            return self.payoffs[h][player]
        children = self.children[h]
        if kind == _CHANCE:
            return sum(
                p * self._traverse(c, player, pi_i, pi_o * p, sigma)
                for c, p in zip(children, self.probs[h], strict=True)
            )
        info = self.infoset[h]
        strategy = sigma[info]
        if self.player[h] != player:
            return sum(
                q * self._traverse(c, player, pi_i, pi_o * q, sigma)
                for c, q in zip(children, strategy, strict=True)
                if q > 0
            )
        values = [
            self._traverse(c, player, pi_i * q, pi_o, sigma)
            for c, q in zip(children, strategy, strict=True)
        ]
        v = sum(q * x for q, x in zip(strategy, values, strict=True))
        regret = self.regret[info]
        for a, x in enumerate(values):
            regret[a] += pi_o * (x - v)
        weight = pi_i * (self.iteration if self.plus else 1)
        if weight:
            acc = self.strategy_sum[info]
            for a, q in enumerate(strategy):
                acc[a] += weight * q
        return v

    def average(self) -> Policy:
        """La estrategia media (la que converge al equilibrio)."""
        out: Policy = {}
        for i, acc in enumerate(self.strategy_sum):
            total = sum(acc)
            out[i] = [x / total for x in acc] if total > 0 else [1.0 / len(acc)] * len(acc)
        return out


def solve_cfr(
    tree: GameTree, iterations: int, *, plus: bool = True, measure_every: int = 0
) -> tuple[Policy, Convergence]:
    solver = CFR(tree, plus=plus)
    convergence = solver.run(iterations, measure_every=measure_every)
    return solver.average(), convergence
