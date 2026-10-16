# SPDX-License-Identifier: Apache-2.0
"""Forma de secuencias (Koller, Megiddo y von Stengel, 1996): el equilibrio EXACTO de un juego de
dos jugadores de suma constante con información imperfecta, con un programa lineal del tamaño del
árbol (no de la forma normal, que crece exponencialmente).

Cada asiento elige un *plan de realización* `x`: la probabilidad con que juega cada secuencia de
sus propias acciones (`x[∅] = 1` y, en cada conjunto de información, la suma de sus extensiones es
la secuencia que lleva a él). El pago es bilineal, `xᵀ A y`, con `A[σ₁][σ₂]` = suma, sobre los
finales a los que llevan esas dos secuencias, de la probabilidad del azar por el pago. El asiento
0 resuelve `max fᵀq` con `Fᵀq <= Aᵀx`, `E x = e`, `x >= 0` (el dual de la mejor respuesta del 1),
y el 1, el programa simétrico.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from gamehub.analysis.lp import Backend, linprog
from gamehub.analysis.nash import GameShapeError
from gamehub.analysis.policy import Policy
from gamehub.analysis.tree import GameTree


@dataclass(frozen=True)
class SequenceFormSolution:
    #: Valor del juego para el asiento 0.
    value: Any
    #: Política de equilibrio de cada asiento (sus conjuntos de información).
    policies: tuple[Policy, Policy]

    @property
    def policy(self) -> Policy:
        return {**self.policies[0], **self.policies[1]}


class _Sequences:
    """Las secuencias de un asiento: 0 = vacía; luego (conjunto, acción) en orden."""

    def __init__(self, tree: GameTree, player: int) -> None:
        self.infosets = tree.infosets_of(player)
        self.index: dict[tuple[int, int] | None, int] = {None: 0}
        for s in self.infosets:
            for a in range(len(s.actions)):
                self.index[(s.id, a)] = len(self.index)

    def __len__(self) -> int:
        return len(self.index)

    def constraints(self) -> list[list[int]]:
        """Filas de E (o F): la raíz y una por conjunto de información."""
        rows = [[0] * len(self) for _ in range(len(self.infosets) + 1)]
        rows[0][0] = 1
        for r, s in enumerate(self.infosets, start=1):
            rows[r][self.index[s.parent]] = -1
            for a in range(len(s.actions)):
                rows[r][self.index[(s.id, a)]] = 1
        return rows

    def behavioral(self, plan: tuple[Any, ...]) -> Policy:
        policy: Policy = {}
        for s in self.infosets:
            parent = plan[self.index[s.parent]]
            k = len(s.actions)
            if parent > 0:
                policy[s.id] = [plan[self.index[(s.id, a)]] / parent for a in range(k)]
            else:
                policy[s.id] = [Fraction(1, k)] * k
        return policy


def sequence_form(tree: GameTree, *, backend: Backend = "auto") -> SequenceFormSolution:
    if tree.num_players != 2:
        raise GameShapeError("la forma de secuencias es para juegos de dos jugadores")
    terminals = tree.terminals()
    if len({sum(tree.nodes[z].payoffs) for z in terminals}) > 1:
        raise GameShapeError("el juego no es de suma constante (prueba con CFR)")
    s1, s2 = _Sequences(tree, 0), _Sequences(tree, 1)
    a: dict[tuple[int, int], Fraction] = {}
    for z in terminals:
        last = tree.sequences(z)
        node = tree.nodes[z]
        key = (s1.index[last[0]], s2.index[last[1]])
        a[key] = a.get(key, Fraction(0)) + node.chance_reach * node.payoffs[0]
    e, f = s1.constraints(), s2.constraints()
    n1, n2 = len(s1), len(s2)
    # Asiento 0: variables x (n1, >= 0) y q (filas de F, libres). Max q[0].
    rows_f = len(f)
    c = [0] * n1 + [1] + [0] * (rows_f - 1)
    a_ub = []
    for j in range(n2):
        row: list[Any] = [-a.get((i, j), 0) for i in range(n1)]
        row += [f[r][j] for r in range(rows_f)]
        a_ub.append(row)
    a_eq = [[*row, *([0] * rows_f)] for row in e]
    b_eq = [1] + [0] * (len(e) - 1)
    res0 = linprog(
        c,
        A_ub=a_ub,
        b_ub=[0] * n2,
        A_eq=a_eq,
        b_eq=b_eq,
        free=range(n1, n1 + rows_f),
        maximize=True,
        backend=backend,
    )
    # Asiento 1: variables y (n2, >= 0) y p (filas de E, libres). Min p[0] con Eᵀp >= A y.
    rows_e = len(e)
    c1 = [0] * n2 + [1] + [0] * (rows_e - 1)
    a_ub1 = []
    for i in range(n1):
        row = [a.get((i, j), 0) for j in range(n2)]
        row += [-e[r][i] for r in range(rows_e)]
        a_ub1.append(row)
    a_eq1 = [[*row, *([0] * rows_e)] for row in f]
    b_eq1 = [1] + [0] * (len(f) - 1)
    res1 = linprog(
        c1,
        A_ub=a_ub1,
        b_ub=[0] * n1,
        A_eq=a_eq1,
        b_eq=b_eq1,
        free=range(n2, n2 + rows_e),
        backend=backend,
    )
    if res0.x is None or res1.x is None:  # pragma: no cover - siempre hay equilibrio
        raise GameShapeError("el programa lineal no tiene solución")
    x = res0.x[:n1]
    y = res1.x[:n2]
    return SequenceFormSolution(res0.value, (s1.behavioral(x), s2.behavioral(y)))
