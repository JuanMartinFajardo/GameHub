# SPDX-License-Identifier: Apache-2.0
"""Programación lineal para la teoría de juegos: un símplex EXACTO en racionales y, para los
problemas grandes, HiGHS (en coma flotante, si está instalado `highspy`).

    linprog(c, A_ub=…, b_ub=…, A_eq=…, b_eq=…, free=…, maximize=…)

minimiza (o maximiza) `c·x` con `A_ub x <= b_ub`, `A_eq x == b_eq` y `x >= 0` salvo las variables
de `free`, que no tienen cota. Los juegos pequeños (los que el motor de Python puede recorrer) dan
problemas pequeños, y la respuesta exacta vale más que la velocidad: el valor de Kuhn es -1/18, no
-0.0555555. El símplex es el de dos fases sobre una tabla densa con la regla de Dantzig, que pasa a
la de Bland tras varios pivotes degenerados seguidos (los programas de los juegos son muy
degenerados y Bland garantiza que no hay ciclos).
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Literal

Number = int | Fraction | float
Backend = Literal["auto", "exact", "highs"]

#: Tamaño (filas × columnas) a partir del cual `backend="auto"` usa HiGHS si está instalado.
EXACT_LIMIT = 60_000
#: Pivotes degenerados seguidos antes de pasar a la regla de Bland.
_DEGENERATE_STREAK = 8


class LPError(Exception):
    """El programa no se puede resolver con el backend pedido."""


@dataclass(frozen=True)
class LPResult:
    status: Literal["optimal", "infeasible", "unbounded"]
    #: Solución (racionales con el símplex exacto; `float` con HiGHS).
    x: tuple[Any, ...] | None = None
    value: Any = None
    backend: str = "exact"

    @property
    def ok(self) -> bool:
        return self.status == "optimal"


def highs_available() -> bool:
    try:
        import highspy  # noqa: F401
    except ImportError:
        return False
    return True


def linprog(
    c: Sequence[Number],
    *,
    A_ub: Sequence[Sequence[Number]] = (),
    b_ub: Sequence[Number] = (),
    A_eq: Sequence[Sequence[Number]] = (),
    b_eq: Sequence[Number] = (),
    free: Collection[int] = (),
    maximize: bool = False,
    backend: Backend = "auto",
) -> LPResult:
    n = len(c)
    for row in (*A_ub, *A_eq):
        if len(row) != n:
            raise LPError(f"cada fila necesita {n} coeficientes, no {len(row)}")
    if len(A_ub) != len(b_ub) or len(A_eq) != len(b_eq):
        raise LPError("cada fila necesita su término independiente")
    size = (len(A_ub) + len(A_eq) + 1) * (n + len(A_ub) + 1)
    if backend == "auto":
        backend = "highs" if size > EXACT_LIMIT and highs_available() else "exact"
    if backend == "highs":
        return _highs(c, A_ub, b_ub, A_eq, b_eq, free, maximize)
    return _exact(c, A_ub, b_ub, A_eq, b_eq, set(free), maximize)


# --- Símplex exacto ------------------------------------------------------------------------------


def _exact(
    c: Sequence[Number],
    A_ub: Sequence[Sequence[Number]],
    b_ub: Sequence[Number],
    A_eq: Sequence[Sequence[Number]],
    b_eq: Sequence[Number],
    free: set[int],
    maximize: bool,
) -> LPResult:
    n = len(c)
    # Columnas: las variables (las libres, partidas en x⁺ - x⁻), las holguras y las artificiales.
    columns: list[tuple[int, int]] = []  # (variable original, signo)
    for j in range(n):
        columns.append((j, 1))
        if j in free:
            columns.append((j, -1))
    nv = len(columns)
    m_ub, m_eq = len(A_ub), len(A_eq)
    m = m_ub + m_eq
    width = nv + m_ub
    rows: list[list[Fraction]] = []
    rhs: list[Fraction] = []
    for i, (coeffs, b) in enumerate([*zip(A_ub, b_ub, strict=True), *zip(A_eq, b_eq, strict=True)]):
        row = [Fraction(coeffs[j]) * s for j, s in columns] + [Fraction(0)] * m_ub
        if i < m_ub:
            row[nv + i] = Fraction(1)
        value = Fraction(b)
        if value < 0:
            row = [-x for x in row]
            value = -value
        rows.append(row)
        rhs.append(value)
    # Base inicial: la holgura de cada fila `<=` que la tenga con +1; si no, una artificial.
    basis: list[int] = []
    artificial: list[int] = []
    for i in range(m):
        if i < m_ub and rows[i][nv + i] == 1:
            basis.append(nv + i)
            continue
        col = width + len(artificial)
        artificial.append(col)
        basis.append(col)
    total = width + len(artificial)
    for i, row in enumerate(rows):
        row.extend([Fraction(0)] * len(artificial))
        if basis[i] >= width:
            row[basis[i]] = Fraction(1)
    tableau = _Tableau(rows, rhs, basis, total)
    if artificial:
        phase1 = [Fraction(0)] * width + [Fraction(1)] * len(artificial)
        tableau.optimize(phase1, allowed=total)
        if tableau.objective(phase1) != 0:
            return LPResult("infeasible")
        tableau.drive_out(width)
    sign = -1 if maximize else 1
    costs = [sign * Fraction(c[j]) * s for j, s in columns] + [Fraction(0)] * (total - nv)
    if not tableau.optimize(costs, allowed=width):
        return LPResult("unbounded")
    values = tableau.values()
    x = [Fraction(0)] * n
    for k, (j, s) in enumerate(columns):
        x[j] += s * values[k]
    objective = sum((Fraction(c[j]) * x[j] for j in range(n)), Fraction(0))
    return LPResult("optimal", tuple(x), objective, "exact")


class _Tableau:
    """Tabla del símplex: cada fila expresa una variable básica en función de las no básicas."""

    def __init__(
        self, rows: list[list[Fraction]], rhs: list[Fraction], basis: list[int], width: int
    ) -> None:
        self.rows = rows
        self.rhs = rhs
        self.basis = basis
        self.width = width

    def objective(self, costs: Sequence[Fraction]) -> Fraction:
        return sum((costs[b] * r for b, r in zip(self.basis, self.rhs, strict=True)), Fraction(0))

    def values(self) -> list[Fraction]:
        out = [Fraction(0)] * self.width
        for b, r in zip(self.basis, self.rhs, strict=True):
            out[b] = r
        return out

    def reduced_costs(self, costs: Sequence[Fraction], allowed: int) -> list[Fraction]:
        reduced = list(costs[:allowed])
        for b, row in zip(self.basis, self.rows, strict=True):
            cb = costs[b]
            if cb:
                for j in range(allowed):
                    if row[j]:
                        reduced[j] -= cb * row[j]
        return reduced

    def optimize(self, costs: Sequence[Fraction], allowed: int) -> bool:
        """Minimiza `costs·x` usando solo las columnas `< allowed` para entrar en la base.
        Devuelve False si el problema no está acotado."""
        reduced = self.reduced_costs(costs, allowed)
        streak = 0
        while True:
            bland = streak >= _DEGENERATE_STREAK
            entering = -1
            best = Fraction(0)
            for j, r in enumerate(reduced):
                if r < 0 and (bland or r < best):
                    entering, best = j, r
                    if bland:
                        break
            if entering < 0:
                return True
            leaving = -1
            ratio = Fraction(0)
            for i, row in enumerate(self.rows):
                a = row[entering]
                if a > 0:
                    q = self.rhs[i] / a
                    if (
                        leaving < 0
                        or q < ratio
                        or (q == ratio and self.basis[i] < self.basis[leaving])
                    ):
                        leaving, ratio = i, q
            if leaving < 0:
                return False
            streak = streak + 1 if ratio == 0 else 0
            self.pivot(leaving, entering)
            factor = reduced[entering]
            row = self.rows[leaving]
            for j in range(allowed):
                if row[j]:
                    reduced[j] -= factor * row[j]

    def pivot(self, r: int, col: int) -> None:
        row = self.rows[r]
        a = row[col]
        if a != 1:
            row[:] = [x / a for x in row]
            self.rhs[r] /= a
        nonzero = [j for j, x in enumerate(row) if x]
        for i, other in enumerate(self.rows):
            if i == r:
                continue
            f = other[col]
            if f:
                for j in nonzero:
                    other[j] -= f * row[j]
                self.rhs[i] -= f * self.rhs[r]
        self.basis[r] = col

    def drive_out(self, width: int) -> None:
        """Tras la fase 1: saca de la base las artificiales (a nivel 0) y quita las filas
        redundantes; luego descarta las columnas artificiales."""
        i = 0
        while i < len(self.rows):
            if self.basis[i] >= width:
                col = next((j for j in range(width) if self.rows[i][j]), -1)
                if col < 0:
                    del self.rows[i], self.rhs[i], self.basis[i]
                    continue
                self.pivot(i, col)
            i += 1
        for row in self.rows:
            del row[width:]
        self.width = width


# --- HiGHS ---------------------------------------------------------------------------------------


def _highs(
    c: Sequence[Number],
    A_ub: Sequence[Sequence[Number]],
    b_ub: Sequence[Number],
    A_eq: Sequence[Sequence[Number]],
    b_eq: Sequence[Number],
    free: Collection[int],
    maximize: bool,
) -> LPResult:
    try:
        import highspy
        import numpy as np
    except ImportError as exc:  # pragma: no cover - depende del entorno
        raise LPError("HiGHS no está instalado (pip install 'gamehub[analysis]')") from exc
    inf = highspy.kHighsInf
    n = len(c)
    lp = highspy.HighsLp()
    lp.num_col_ = n
    lp.num_row_ = len(A_ub) + len(A_eq)
    lp.col_cost_ = np.array([float(x) for x in c])
    lp.col_lower_ = np.array([-inf if j in free else 0.0 for j in range(n)])
    lp.col_upper_ = np.array([inf] * n)
    lp.row_lower_ = np.array([-inf] * len(A_ub) + [float(b) for b in b_eq])
    lp.row_upper_ = np.array([float(b) for b in b_ub] + [float(b) for b in b_eq])
    starts, index, values = [0], [], []
    for row in (*A_ub, *A_eq):
        for j, a in enumerate(row):
            if a:
                index.append(j)
                values.append(float(a))
        starts.append(len(index))
    lp.a_matrix_.format_ = highspy.MatrixFormat.kRowwise
    lp.a_matrix_.start_ = np.array(starts, dtype=np.int32)
    lp.a_matrix_.index_ = np.array(index, dtype=np.int32)
    lp.a_matrix_.value_ = np.array(values)
    lp.sense_ = highspy.ObjSense.kMaximize if maximize else highspy.ObjSense.kMinimize
    h = highspy.Highs()
    h.setOptionValue("output_flag", False)
    h.passModel(lp)
    h.run()
    status = h.getModelStatus()
    if status == highspy.HighsModelStatus.kInfeasible:
        return LPResult("infeasible", backend="highs")
    if status in (
        highspy.HighsModelStatus.kUnbounded,
        highspy.HighsModelStatus.kUnboundedOrInfeasible,
    ):
        return LPResult("unbounded", backend="highs")
    if status != highspy.HighsModelStatus.kOptimal:
        raise LPError(f"HiGHS no encontró el óptimo: {h.modelStatusToString(status)}")
    x = tuple(float(v) for v in h.getSolution().col_value)
    return LPResult("optimal", x, float(h.getInfo().objective_function_value), "highs")
