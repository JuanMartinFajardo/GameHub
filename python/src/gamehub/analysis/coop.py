# SPDX-License-Identifier: Apache-2.0
"""Juegos cooperativos en forma de función característica: `v(C)` es lo que la coalición `C` se
puede asegurar por sí sola.

- `characteristic_function(nf)`: la función derivada de un juego en forma normal: lo que `C` se
  garantiza (la suma de los pagos de sus miembros) coordinando sus estrategias, aunque los demás
  jueguen en su contra (su valor maximin, por programación lineal; von Neumann y Morgenstern).
- `shapley` (exacto), `banzhaf`, `core` (un punto del núcleo, o None si está vacío), `least_core`,
  `nucleolus` (Schmeidler, por programas lineales sucesivos) y `nash_bargaining` (la solución de
  negociación de Nash de dos jugadores sobre la envolvente convexa de los pagos).
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from gamehub.analysis.lp import Backend, linprog
from gamehub.analysis.nash import GameShapeError, zero_sum
from gamehub.analysis.normal_form import NormalForm

Coalition = frozenset[int]


@dataclass
class Coalitional:
    n: int
    #: Valor de cada coalición (todas, la vacía con 0).
    values: dict[Coalition, Fraction]
    players: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.players:
            self.players = tuple(f"Asiento {i}" for i in range(self.n))
        self.values.setdefault(frozenset(), Fraction(0))

    @staticmethod
    def from_function(n: int, v: Callable[[Coalition], Any]) -> Coalitional:
        return Coalitional(n, {c: Fraction(v(c)) for c in coalitions(n)})

    def v(self, coalition: Iterable[int]) -> Fraction:
        return self.values[frozenset(coalition)]

    @property
    def grand(self) -> Fraction:
        return self.v(range(self.n))

    def is_superadditive(self) -> bool:
        cs = list(coalitions(self.n))
        return all(
            self.values[a | b] >= self.values[a] + self.values[b]
            for a in cs
            for b in cs
            if not a & b
        )

    def is_convex(self) -> bool:
        cs = list(coalitions(self.n))
        return all(
            self.values[a | b] + self.values[a & b] >= self.values[a] + self.values[b]
            for a in cs
            for b in cs
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "players": list(self.players),
            "values": [
                {"coalition": sorted(c), "value": str(v)}
                for c, v in sorted(self.values.items(), key=lambda cv: (len(cv[0]), sorted(cv[0])))
            ],
        }


def coalitions(n: int) -> Iterable[Coalition]:
    """Todas las coaliciones, de menor a mayor tamaño."""
    for k in range(n + 1):
        for c in itertools.combinations(range(n), k):
            yield frozenset(c)


def characteristic_function(nf: NormalForm, *, backend: Backend = "auto") -> Coalitional:
    n = nf.num_players
    values: dict[Coalition, Fraction] = {frozenset(): Fraction(0)}
    everyone = frozenset(range(n))
    values[everyone] = Fraction(max(sum(u) for u in nf.payoffs.values()))
    for coalition in coalitions(n):
        if not coalition or coalition == everyone:
            continue
        members = sorted(coalition)
        rest = sorted(everyone - coalition)
        mine = list(itertools.product(*(range(nf.shape[i]) for i in members)))
        theirs = list(itertools.product(*(range(nf.shape[i]) for i in rest)))

        matrix = [
            [sum(nf.payoffs[_joint(n, members, a, rest, b)][i] for i in members) for b in theirs]
            for a in mine
        ]
        values[coalition] = Fraction(
            zero_sum(NormalForm.from_matrices(matrix), backend=backend).value
        )
    return Coalitional(n, values, nf.players)


def _joint(
    n: int, members: list[int], a: tuple[int, ...], rest: list[int], b: tuple[int, ...]
) -> tuple[int, ...]:
    """El perfil en que los de `members` juegan `a` y los de `rest`, `b`."""
    profile = [0] * n
    for i, s in zip(members, a, strict=True):
        profile[i] = s
    for i, s in zip(rest, b, strict=True):
        profile[i] = s
    return tuple(profile)


def shapley(cf: Coalitional) -> tuple[Fraction, ...]:
    """φᵢ = Σ_{S ⊆ N∖{i}} |S|! (n−|S|−1)! / n! · (v(S ∪ {i}) − v(S))."""
    n = cf.n
    weights = [
        Fraction(math.factorial(k) * math.factorial(n - k - 1), math.factorial(n)) for k in range(n)
    ]
    out = []
    for i in range(n):
        total = Fraction(0)
        for s in coalitions(n):
            if i in s:
                continue
            total += weights[len(s)] * (cf.values[s | {i}] - cf.values[s])
        out.append(total)
    return tuple(out)


def banzhaf(cf: Coalitional, *, normalized: bool = False) -> tuple[Fraction, ...]:
    """Contribución marginal media de cada jugador sobre las 2ⁿ⁻¹ coaliciones de los demás (con
    `normalized`, repartida para que sume 1)."""
    n = cf.n
    raw = []
    for i in range(n):
        total = sum(
            (cf.values[s | {i}] - cf.values[s] for s in coalitions(n) if i not in s), Fraction(0)
        )
        raw.append(total / 2 ** (n - 1))
    if normalized:
        whole = sum(raw)
        return tuple(r / whole for r in raw) if whole else tuple(raw)
    return tuple(raw)


def in_core(cf: Coalitional, x: Sequence[Any]) -> bool:
    if sum(x) != cf.grand:
        return False
    return all(sum(x[i] for i in c) >= v for c, v in cf.values.items())


def least_core(cf: Coalitional, *, backend: Backend = "auto") -> tuple[Fraction, tuple[Any, ...]]:
    """El menor ε tal que hay un reparto con x(C) ≥ v(C) − ε para toda coalición propia, y uno de
    esos repartos. El núcleo no está vacío si y solo si ε ≤ 0."""
    n = cf.n
    proper = [c for c in coalitions(n) if c and len(c) < n]
    # Variables: x_0..x_{n-1} libres y ε libre. Min ε con -x(C) - ε <= -v(C).
    c = [0] * n + [1]
    a_ub = [[-1 if i in coal else 0 for i in range(n)] + [-1] for coal in proper]
    b_ub = [-cf.values[coal] for coal in proper]
    res = linprog(
        c,
        A_ub=a_ub,
        b_ub=b_ub,
        A_eq=[[1] * n + [0]],
        b_eq=[cf.grand],
        free=range(n + 1),
        backend=backend,
    )
    assert res.x is not None
    return res.x[n], tuple(res.x[:n])


def core(cf: Coalitional, *, backend: Backend = "auto") -> tuple[Any, ...] | None:
    """Un reparto del núcleo (eficiente y que ninguna coalición mejora por su cuenta), o None si
    el núcleo está vacío."""
    eps, x = least_core(cf, backend=backend)
    return x if eps <= 0 else None


def nucleolus(cf: Coalitional) -> tuple[Fraction, ...]:
    """El nucléolo (sobre las imputaciones): el reparto que maximiza lexicográficamente los
    excesos x(C) − v(C) de menor a mayor. Programas lineales sucesivos en aritmética exacta."""
    n = cf.n
    singles = sum(cf.v([i]) for i in range(n))
    if singles > cf.grand:
        raise GameShapeError("no hay imputaciones: Σ v({i}) > v(N)")
    pending = [c for c in coalitions(n) if c and len(c) < n]
    fixed: list[tuple[Coalition, Fraction]] = []

    def row(coal: Coalition) -> list[int]:
        return [1 if i in coal else 0 for i in range(n)]

    def constraints(
        extra_eps: Fraction | None,
    ) -> tuple[list[list[Any]], list[Any], list[list[Any]], list[Any]]:
        # Variables: x (n, libres) y ε (libre).
        a_ub: list[list[Any]] = []
        b_ub: list[Any] = []
        for coal in pending:
            # ε - x(C) <= -v(C)
            a_ub.append([-k for k in row(coal)] + [1])
            b_ub.append(-cf.values[coal])
        for i in range(n):  # imputación: x_i >= v({i})
            a_ub.append([-1 if j == i else 0 for j in range(n)] + [0])
            b_ub.append(-cf.v([i]))
        a_eq: list[list[Any]] = [[1] * n + [0]]
        b_eq: list[Any] = [cf.grand]
        for coal, e in fixed:
            a_eq.append([*row(coal), 0])
            b_eq.append(e + cf.values[coal])
        if extra_eps is not None:
            a_eq.append([0] * n + [1])
            b_eq.append(extra_eps)
        return a_ub, b_ub, a_eq, b_eq

    x: tuple[Any, ...] = ()
    while pending:
        a_ub, b_ub, a_eq, b_eq = constraints(None)
        res = linprog(
            [0] * n + [1],
            A_ub=a_ub,
            b_ub=b_ub,
            A_eq=a_eq,
            b_eq=b_eq,
            free=range(n + 1),
            maximize=True,
            backend="exact",
        )
        assert res.x is not None
        eps = res.x[n]
        x = res.x[:n]
        a_ub, b_ub, a_eq, b_eq = constraints(eps)
        tight = []
        for coal in pending:
            # ¿Puede el exceso de C superar ε manteniendo todo lo demás?
            probe = linprog(
                [*row(coal), 0],
                A_ub=a_ub,
                b_ub=b_ub,
                A_eq=a_eq,
                b_eq=b_eq,
                free=range(n + 1),
                maximize=True,
                backend="exact",
            )
            if probe.value is not None and probe.value - cf.values[coal] <= eps:
                tight.append(coal)
        if not tight:  # pragma: no cover - la teoría garantiza al menos una
            break
        for coal in tight:
            pending.remove(coal)
            fixed.append((coal, eps))
        if _determined(n, [c for c, _ in fixed]):
            break
    return tuple(x)


def _determined(n: int, fixed: list[Coalition]) -> bool:
    """¿Fijan las coaliciones (con la eficiencia) un único reparto? (rango n)."""
    rows = [[Fraction(1)] * n] + [[Fraction(1 if i in c else 0) for i in range(n)] for c in fixed]
    rank = 0
    cols = list(range(n))
    m = [r[:] for r in rows]
    for col in cols:
        pivot = next((r for r in range(rank, len(m)) if m[r][col] != 0), None)
        if pivot is None:
            continue
        m[rank], m[pivot] = m[pivot], m[rank]
        for r in range(len(m)):
            if r != rank and m[r][col] != 0:
                f = m[r][col] / m[rank][col]
                m[r] = [a - f * b for a, b in zip(m[r], m[rank], strict=True)]
        rank += 1
    return rank == n


# --- Negociación de Nash -------------------------------------------------------------------------


@dataclass(frozen=True)
class Bargaining:
    #: Pagos acordados.
    payoffs: tuple[Fraction, Fraction]
    #: Punto de desacuerdo.
    disagreement: tuple[Fraction, Fraction]


def nash_bargaining(nf: NormalForm, disagreement: Sequence[Any] | None = None) -> Bargaining | None:
    """Maximiza (u₀ − d₀)(u₁ − d₁) sobre la envolvente convexa de los pagos de los perfiles puros
    (los jugadores pueden sortear entre perfiles). `disagreement` por defecto: lo que cada uno se
    garantiza solo (su valor maximin). None si nada mejora el desacuerdo para los dos."""
    if nf.num_players != 2:
        raise GameShapeError("la negociación de Nash es de dos jugadores")
    if disagreement is None:
        d0 = zero_sum(NormalForm.from_matrices(nf.matrix(0))).value
        d1 = zero_sum(
            NormalForm.from_matrices([list(r) for r in zip(*nf.matrix(1), strict=True)])
        ).value
        d = (Fraction(d0), Fraction(d1))
    else:
        d = (Fraction(disagreement[0]), Fraction(disagreement[1]))
    points = sorted({(u[0], u[1]) for u in nf.payoffs.values()})
    hull = _convex_hull(points)
    edges = (
        list(zip(hull, hull[1:] + hull[:1], strict=True)) if len(hull) > 1 else [(hull[0], hull[0])]
    )
    best: tuple[Fraction, tuple[Fraction, Fraction]] | None = None
    for p, q in edges:
        a, b = p[0] - d[0], q[0] - p[0]
        c, e = p[1] - d[1], q[1] - p[1]
        candidates = [Fraction(0), Fraction(1)]
        if b * e != 0:
            t = -(b * c + a * e) / (2 * b * e)
            if 0 <= t <= 1:
                candidates.append(t)
        for t in candidates:
            u0, u1 = a + b * t, c + e * t
            if u0 < 0 or u1 < 0:
                continue
            product = u0 * u1
            if best is None or product > best[0]:
                best = (product, (u0 + d[0], u1 + d[1]))
    if best is None or best[0] <= 0:
        return None
    return Bargaining(best[1], d)


def _convex_hull(points: list[tuple[Fraction, Fraction]]) -> list[tuple[Fraction, Fraction]]:
    """Envolvente convexa (cadena monótona de Andrew), en sentido antihorario."""
    if len(points) <= 2:
        return points

    def cross(o: tuple[Any, Any], a: tuple[Any, Any], b: tuple[Any, Any]) -> Any:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[Fraction, Fraction]] = []
    for p in points:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[tuple[Fraction, Fraction]] = []
    for p in reversed(points):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]
