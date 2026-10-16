# SPDX-License-Identifier: Apache-2.0
"""Soluciones de juegos en forma normal, en aritmética exacta.

- Equilibrios de Nash: en estrategias puras (n jugadores); mixtos de dos jugadores por
  **enumeración de soportes** (todos, si el juego es no degenerado) y por **Lemke–Howson** (uno
  por cada etiqueta inicial, con la regla lexicográfica, que no cicla en juegos degenerados).
- **Suma cero** (o constante) de dos jugadores: valor y estrategias maximin por programación lineal.
- **Dominancia** iterada: estricta o débil, por estrategias puras o mixtas.
- **Equilibrio correlado** (programación lineal), **Pareto**, óptimo **social** (utilitarista o
  igualitario) y **precio de la anarquía / de la estabilidad**.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Literal

from gamehub.analysis.lp import Backend, linprog
from gamehub.analysis.normal_form import Mixed, MixedProfile, NormalForm, Profile


class GameShapeError(ValueError):
    """El método no se aplica a este juego (número de jugadores, suma no constante…)."""


# --- Equilibrios puros ---------------------------------------------------------------------------


def best_responses(nf: NormalForm, player: int, profile: Sequence[int]) -> list[int]:
    """Las estrategias puras de `player` que maximizan su pago contra el resto de `profile`."""
    values = [nf.payoffs[nf.deviate(profile, player, s)][player] for s in range(nf.shape[player])]
    best = max(values)
    return [s for s, v in enumerate(values) if v == best]


def is_best_response(nf: NormalForm, player: int, profile: Sequence[int]) -> bool:
    return profile[player] in best_responses(nf, player, profile)


def pure_equilibria(nf: NormalForm) -> list[Profile]:
    return [
        p for p in nf.profiles() if all(is_best_response(nf, k, p) for k in range(nf.num_players))
    ]


def pure_as_mixed(nf: NormalForm, profile: Sequence[int]) -> MixedProfile:
    return tuple(
        tuple(Fraction(1 if t == s else 0) for t in range(nf.shape[k]))
        for k, s in enumerate(profile)
    )


def is_equilibrium(nf: NormalForm, profile: MixedProfile, tol: Any = 0) -> bool:
    """Ningún jugador gana más de `tol` desviándose a una estrategia pura."""
    payoffs = nf.expected(profile)
    return all(
        max(nf.strategy_values(k, profile)) <= payoffs[k] + tol for k in range(nf.num_players)
    )


# --- Dos jugadores: enumeración de soportes ------------------------------------------------------


def _two_players(nf: NormalForm) -> tuple[list[list[Fraction]], list[list[Fraction]]]:
    if nf.num_players != 2:
        raise GameShapeError("este método es para juegos de dos jugadores")
    return nf.matrix(0), nf.matrix(1)


def support_enumeration(nf: NormalForm, *, max_support: int | None = None) -> list[MixedProfile]:
    """Todos los equilibrios con soportes del mismo tamaño (todos los del juego si es no
    degenerado), exactos."""
    a, b = _two_players(nf)
    m, n = nf.shape
    found: list[MixedProfile] = []
    top = min(m, n) if max_support is None else min(m, n, max_support)
    for k in range(1, top + 1):
        for rows in itertools.combinations(range(m), k):
            for cols in itertools.combinations(range(n), k):
                y = _indifferent([[a[i][j] for j in cols] for i in rows])
                if y is None:
                    continue
                x = _indifferent([[b[i][j] for i in rows] for j in cols])
                if x is None:
                    continue
                xs = _spread(x[0], rows, m)
                ys = _spread(y[0], cols, n)
                u, v = y[1], x[1]
                if any(
                    sum(a[i][j] * ys[j] for j in range(n)) > u for i in range(m) if i not in rows
                ):
                    continue
                if any(
                    sum(b[i][j] * xs[i] for i in range(m)) > v for j in range(n) if j not in cols
                ):
                    continue
                profile = (tuple(xs), tuple(ys))
                if profile not in found:
                    found.append(profile)
    return found


def _indifferent(matrix: list[list[Fraction]]) -> tuple[list[Fraction], Fraction] | None:
    """La mezcla (con soporte completo, positiva) de las columnas que deja indiferentes a todas
    las filas: resuelve `M q = u·1`, `Σq = 1`. None si no hay una única o no es positiva."""
    k = len(matrix[0])
    system = [[*row, Fraction(-1)] for row in matrix]
    system.append([Fraction(1)] * k + [Fraction(0)])
    rhs = [Fraction(0)] * len(matrix) + [Fraction(1)]
    solution = solve_linear(system, rhs)
    if solution is None or any(q <= 0 for q in solution[:k]):
        return None
    return solution[:k], solution[k]


def _spread(values: Sequence[Fraction], support: Sequence[int], size: int) -> list[Fraction]:
    out = [Fraction(0)] * size
    for s, q in zip(support, values, strict=True):
        out[s] = q
    return out


def solve_linear(matrix: list[list[Fraction]], rhs: list[Fraction]) -> list[Fraction] | None:
    """Resuelve un sistema cuadrado por eliminación de Gauss en racionales (None si es
    singular)."""
    n = len(matrix)
    if any(len(row) != n for row in matrix):
        return None
    m = [[Fraction(x) for x in row] + [Fraction(r)] for row, r in zip(matrix, rhs, strict=True)]
    for col in range(n):
        pivot = next((r for r in range(col, n) if m[r][col] != 0), None)
        if pivot is None:
            return None
        m[col], m[pivot] = m[pivot], m[col]
        p = m[col][col]
        m[col] = [x / p for x in m[col]]
        for r in range(n):
            if r != col and m[r][col] != 0:
                f = m[r][col]
                m[r] = [x - f * y for x, y in zip(m[r], m[col], strict=True)]
    return [m[r][n] for r in range(n)]


# --- Dos jugadores: Lemke–Howson -----------------------------------------------------------------


def lemke_howson(nf: NormalForm, label: int = 0) -> MixedProfile:
    """Un equilibrio por el algoritmo de Lemke–Howson, soltando la etiqueta `label` (las `m`
    primeras son las estrategias del jugador 0; las `n` siguientes, las del 1)."""
    a, b = _two_players(nf)
    m, n = nf.shape
    if not 0 <= label < m + n:
        raise ValueError(f"la etiqueta debe estar entre 0 y {m + n - 1}")
    low = min(min(min(r) for r in a), min(min(r) for r in b))
    shift = 1 - low if low <= 0 else Fraction(0)
    # P (del jugador 0): s_j + Σ_i B'[i][j] x_i = 1. Etiquetas: x_i → i, s_j → m + j.
    p = _LHTableau(
        [[b[i][j] + shift for i in range(m)] for j in range(n)],
        variables=list(range(m)),
        slacks=[m + j for j in range(n)],
    )
    # Q (del jugador 1): r_i + Σ_j A'[i][j] y_j = 1. Etiquetas: y_j → m + j, r_i → i.
    q = _LHTableau(
        [[a[i][j] + shift for j in range(n)] for i in range(m)],
        variables=[m + j for j in range(n)],
        slacks=list(range(m)),
    )
    current, other = (p, q) if label < m else (q, p)
    entering = label
    for _ in range(10_000):
        leaving = current.pivot(entering)
        if leaving == label:
            break
        entering = leaving
        current, other = other, current
    else:  # pragma: no cover - la regla lexicográfica no cicla
        raise RuntimeError("Lemke–Howson no termina")
    x = [p.value(i) for i in range(m)]
    y = [q.value(m + j) for j in range(n)]
    sx, sy = sum(x), sum(y)
    return tuple(v / sx for v in x), tuple(v / sy for v in y)


def lemke_howson_all(nf: NormalForm, labels: Sequence[int] | None = None) -> list[MixedProfile]:
    """Los equilibrios distintos que se alcanzan soltando cada una de las etiquetas (o las de
    `labels`)."""
    found: list[MixedProfile] = []
    for label in range(sum(nf.shape)) if labels is None else labels:
        eq = lemke_howson(nf, label)
        if eq not in found:
            found.append(eq)
    return found


class _LHTableau:
    """Tabla de Lemke–Howson indexada por etiquetas: cada fila expresa una variable básica."""

    def __init__(self, coeffs: list[list[Fraction]], variables: list[int], slacks: list[int]):
        self.labels = sorted([*variables, *slacks])
        self.col = {label: k for k, label in enumerate(self.labels)}
        width = len(self.labels)
        self.rows: list[list[Fraction]] = []
        self.rhs: list[Fraction] = []
        for r, row in enumerate(coeffs):
            line = [Fraction(0)] * width
            for v, c in zip(variables, row, strict=True):
                line[self.col[v]] = Fraction(c)
            line[self.col[slacks[r]]] = Fraction(1)
            self.rows.append(line)
            self.rhs.append(Fraction(1))
        self.basis = list(slacks)
        self.slack_cols = [self.col[s] for s in slacks]

    def pivot(self, entering: int) -> int:
        c = self.col[entering]
        best: int | None = None
        best_key: tuple[Fraction, ...] = ()
        for r, row in enumerate(self.rows):
            if row[c] > 0:
                key = (self.rhs[r] / row[c], *(row[s] / row[c] for s in self.slack_cols))
                if best is None or key < best_key:
                    best, best_key = r, key
        if best is None:  # pragma: no cover - imposible con pagos positivos
            raise RuntimeError("Lemke–Howson: rayo no acotado")
        row = self.rows[best]
        pv = row[c]
        self.rows[best] = row = [x / pv for x in row]
        self.rhs[best] /= pv
        for r, other in enumerate(self.rows):
            if r != best and other[c]:
                f = other[c]
                self.rows[r] = [x - f * y for x, y in zip(other, row, strict=True)]
                self.rhs[r] -= f * self.rhs[best]
        leaving = self.basis[best]
        self.basis[best] = entering
        return leaving

    def value(self, label: int) -> Fraction:
        for r, b in enumerate(self.basis):
            if b == label:
                return self.rhs[r]
        return Fraction(0)


# --- Suma cero -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class ZeroSumSolution:
    #: Valor del juego para el jugador 0 (el de filas).
    value: Any
    strategies: MixedProfile


def zero_sum(nf: NormalForm, *, backend: Backend = "auto") -> ZeroSumSolution:
    """Valor y estrategias maximin de un juego de dos jugadores de suma constante."""
    a, _ = _two_players(nf)
    if not nf.is_constant_sum():
        raise GameShapeError("el juego no es de suma constante")
    x, v = _maximin(a, backend)
    # El jugador 1 minimiza lo que cobra el 0: maximin de -Aᵀ.
    at = [[-a[i][j] for i in range(len(a))] for j in range(len(a[0]))]
    y, _ = _maximin(at, backend)
    return ZeroSumSolution(v, (x, y))


def _maximin(a: list[list[Fraction]], backend: Backend) -> tuple[Mixed, Any]:
    m, n = len(a), len(a[0])
    # Variables: x_0..x_{m-1} >= 0 y v libre (la última). Max v con v <= Σ_i x_i a[i][j].
    c = [0] * m + [1]
    a_ub = [[-a[i][j] for i in range(m)] + [1] for j in range(n)]
    result = linprog(
        c,
        A_ub=a_ub,
        b_ub=[0] * n,
        A_eq=[[1] * m + [0]],
        b_eq=[1],
        free=[m],
        maximize=True,
        backend=backend,
    )
    assert result.x is not None
    return tuple(result.x[:m]), result.x[m]


# --- Dominancia ----------------------------------------------------------------------------------


@dataclass
class Dominance:
    #: Estrategias que sobreviven, de cada jugador (índices del juego original).
    remaining: list[list[int]]
    #: Eliminaciones en orden: (jugador, estrategia, la que la domina o "mixta").
    steps: list[tuple[int, int, int | str]] = field(default_factory=list)

    def reduced(self, nf: NormalForm) -> NormalForm:
        return nf.restrict(self.remaining)


def iterated_dominance(
    nf: NormalForm, *, weak: bool = False, mixed: bool = False, backend: Backend = "auto"
) -> Dominance:
    """Elimina estrategias dominadas hasta que no queda ninguna. Con `weak`, la dominancia débil
    (el resultado depende del orden: se elimina de una en una, por jugador y por índice); con
    `mixed`, también las dominadas (estrictamente) por una estrategia mixta."""
    alive = [list(range(k)) for k in nf.shape]
    result = Dominance(alive)
    changed = True
    while changed:
        changed = False
        for player in range(nf.num_players):
            for s in list(alive[player]):
                by = _dominator(nf, alive, player, s, weak, mixed, backend)
                if by is None:
                    continue
                alive[player].remove(s)
                result.steps.append((player, s, by))
                changed = True
                if weak:
                    break
            if changed and weak:
                break
    return result


def _dominator(
    nf: NormalForm,
    alive: list[list[int]],
    player: int,
    s: int,
    weak: bool,
    mixed: bool,
    backend: Backend,
) -> int | str | None:
    others = [alive[k] if k != player else [0] for k in range(nf.num_players)]
    contexts = list(itertools.product(*others))

    def u(t: int, ctx: tuple[int, ...]) -> Fraction:
        return nf.payoffs[nf.deviate(ctx, player, t)][player]

    mine = [u(s, ctx) for ctx in contexts]
    for t in alive[player]:
        if t == s:
            continue
        theirs = [u(t, ctx) for ctx in contexts]
        diffs = [b - a for a, b in zip(mine, theirs, strict=True)]
        if all(d > 0 for d in diffs) or (weak and all(d >= 0 for d in diffs) and any(diffs)):
            return t
    if not mixed:
        return None
    candidates = [t for t in alive[player] if t != s]
    if len(candidates) < 2:
        return None
    # Max ε con Σ_t σ_t u(t, ctx) >= u(s, ctx) + ε para todo ctx; σ en el símplex.
    k = len(candidates)
    c = [0] * k + [1]
    a_ub = [[-u(t, ctx) for t in candidates] + [1] for ctx in contexts]
    b_ub = [-x for x in mine]
    res = linprog(
        c,
        A_ub=a_ub,
        b_ub=b_ub,
        A_eq=[[1] * k + [0]],
        b_eq=[1],
        free=[k],
        maximize=True,
        backend=backend,
    )
    return "mixta" if res.ok and res.value is not None and res.value > 0 else None


# --- Equilibrio correlado ------------------------------------------------------------------------


def correlated_equilibrium(
    nf: NormalForm,
    *,
    objective: Literal["welfare", "none"] = "welfare",
    backend: Backend = "auto",
) -> dict[Profile, Any]:
    """Una distribución sobre perfiles puros de la que nadie quiere desviarse al recibir su
    recomendación; con `objective="welfare"`, la que maximiza la suma de los pagos esperados."""
    profiles = list(nf.profiles())
    index = {p: k for k, p in enumerate(profiles)}
    a_ub: list[list[Any]] = []
    for player in range(nf.num_players):
        for rec in range(nf.shape[player]):
            for dev in range(nf.shape[player]):
                if dev == rec:
                    continue
                row = [Fraction(0)] * len(profiles)
                for p in profiles:
                    if p[player] == rec:
                        gain = (
                            nf.payoffs[nf.deviate(p, player, dev)][player] - nf.payoffs[p][player]
                        )
                        row[index[p]] = gain
                a_ub.append(row)
    c = [sum(nf.payoffs[p]) if objective == "welfare" else 0 for p in profiles]
    res = linprog(
        c,
        A_ub=a_ub,
        b_ub=[0] * len(a_ub),
        A_eq=[[1] * len(profiles)],
        b_eq=[1],
        maximize=True,
        backend=backend,
    )
    assert res.x is not None
    return {p: q for p, q in zip(profiles, res.x, strict=True) if q}


# --- Eficiencia ----------------------------------------------------------------------------------


def pareto_dominates(u: Sequence[Any], v: Sequence[Any]) -> bool:
    """`u` domina en Pareto a `v`: nadie está peor y alguien está mejor."""
    return all(a >= b for a, b in zip(u, v, strict=True)) and any(
        a > b for a, b in zip(u, v, strict=True)
    )


def pareto_optimal(nf: NormalForm) -> list[Profile]:
    """Los perfiles puros cuyos pagos no domina en Pareto ningún otro perfil puro."""
    payoffs = nf.payoffs
    return [
        p
        for p in nf.profiles()
        if not any(pareto_dominates(payoffs[q], payoffs[p]) for q in nf.profiles())
    ]


def pareto_dominators(nf: NormalForm, profile: Sequence[int]) -> list[Profile]:
    """Los perfiles puros que dominan en Pareto a `profile`."""
    u = nf.payoffs[tuple(profile)]
    return [q for q in nf.profiles() if pareto_dominates(nf.payoffs[q], u)]


def welfare(payoffs: Sequence[Any], kind: Literal["utilitarian", "egalitarian"]) -> Any:
    return sum(payoffs) if kind == "utilitarian" else min(payoffs)


def social_optimum(
    nf: NormalForm, kind: Literal["utilitarian", "egalitarian"] = "utilitarian"
) -> tuple[Any, list[Profile]]:
    """El mayor bienestar alcanzable con un perfil puro (suma de pagos o el pago del que menos
    cobra) y los perfiles que lo alcanzan."""
    values = {p: welfare(nf.payoffs[p], kind) for p in nf.profiles()}
    best = max(values.values())
    return best, [p for p, v in values.items() if v == best]


#: Pares de soportes como máximo para que `equilibria` use la enumeración de soportes.
SUPPORT_PAIRS_LIMIT = 20_000
#: Etiquetas de cada jugador desde las que se lanza Lemke–Howson en los juegos grandes.
LH_LABELS = 4


def support_pairs(m: int, n: int) -> int:
    return sum(math.comb(m, k) * math.comb(n, k) for k in range(1, min(m, n) + 1))


def equilibria(nf: NormalForm) -> list[MixedProfile]:
    """Los equilibrios que se pueden calcular con exactitud: con dos jugadores, los puros, los de
    Lemke–Howson y, si el juego es pequeño, todos los de la enumeración de soportes; con más, los
    puros."""
    if nf.num_players == 2:
        small = support_pairs(*nf.shape) <= SUPPORT_PAIRS_LIMIT
        found = support_enumeration(nf) if small else []
        m, n = nf.shape
        # En los juegos grandes, Lemke–Howson desde unas pocas etiquetas de cada jugador.
        labels = None if m + n <= 2 * LH_LABELS else [*range(LH_LABELS), *range(m, m + LH_LABELS)]
        for eq in [
            *(pure_as_mixed(nf, p) for p in pure_equilibria(nf)),
            *lemke_howson_all(nf, labels),
        ]:
            if eq not in found:
                found.append(eq)
        return found
    return [pure_as_mixed(nf, p) for p in pure_equilibria(nf)]


def price_of_anarchy(
    nf: NormalForm, found: Sequence[MixedProfile] | None = None
) -> Fraction | None:
    """Bienestar óptimo / bienestar del peor equilibrio (utilitarista). None si algún bienestar
    no es positivo (el cociente no tiene sentido) o no hay equilibrios."""
    return _price(nf, found, worst=True)


def price_of_stability(
    nf: NormalForm, found: Sequence[MixedProfile] | None = None
) -> Fraction | None:
    """Bienestar óptimo / bienestar del mejor equilibrio (utilitarista)."""
    return _price(nf, found, worst=False)


def _price(nf: NormalForm, found: Sequence[MixedProfile] | None, worst: bool) -> Any:
    found = equilibria(nf) if found is None else found
    if not found:
        return None
    optimum, _ = social_optimum(nf)
    values = [sum(nf.expected(eq)) for eq in found]
    target = min(values) if worst else max(values)
    if optimum <= 0 or target <= 0:
        return None
    return optimum / target
