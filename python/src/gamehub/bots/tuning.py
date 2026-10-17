# SPDX-License-Identifier: Apache-2.0
"""Ajuste de los pesos de una heurística (ADR-088): CMA-ES, SPSA y Texel.

- **CMA-ES** (Hansen) y **SPSA** (Spall) buscan los pesos que más ganan: cada evaluación juega
  `games` partidas espejo del bot con los pesos candidatos contra el mismo bot con los pesos de
  partida (o contra otro bot), en el núcleo C++. La función objetivo es ruidosa; los dos métodos
  lo admiten.
- **Texel** (ajuste por regresión logística): partidas de autojuego que guardan los rasgos de
  cada asiento en cada posición; los pesos son los que mejor predicen, con una sigmoide de la
  evaluación, si ese asiento acabó primero. No juega durante el ajuste: es mucho más rápido.

El resultado son pesos nuevos (`weights { … }`), que `write_weights` escribe en el `.game`; la
arena (con SPRT) dice si de verdad mejoran.
"""

from __future__ import annotations

import math
import os
import random
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any

from gamehub.bots.agents import parse_bot_spec
from gamehub.bots.heuristic import constant, find_heuristic

CANDIDATE = "{name}__candidate"


@dataclass
class TuneResult:
    heuristic: str
    method: str
    features: list[str]
    start: list[float]
    weights: list[float]
    score: float | None = None  # puntuación final contra los pesos de partida (CMA-ES, SPSA)
    history: list[tuple[int, float, list[float]]] = field(default_factory=list)

    def block(self) -> str:
        return (
            "weights { "
            + ", ".join(
                f"{f}: {_text(w)}" for f, w in zip(self.features, self.weights, strict=True)
            )
            + " }"
        )


def _text(w: float) -> str:
    r = round(w, 4)
    if r == int(r):
        return str(int(r))
    return f"{r:.4f}".rstrip("0")


def _rational(w: float) -> list[Any]:
    f = Fraction(round(w, 4)).limit_denominator(10_000)
    if f.denominator == 1:
        return ["const", f.numerator]
    return ["rat", f.numerator, f.denominator]


def with_weights(
    ir: dict[str, Any], name: str, weights: Sequence[float], as_name: str
) -> dict[str, Any]:
    """Una copia de la IR con la heurística `name` repetida como `as_name` y esos pesos."""
    h = find_heuristic(ir, name)
    copy = dict(h, name=as_name)
    copy["features"] = [
        {**{k: v for k, v in f.items() if k != "weight"}, "weight": _rational(w)}
        for f, w in zip(h.get("features", []), weights, strict=True)
    ]
    return {**ir, "heuristics": [*ir.get("heuristics", []), copy]}


def initial_weights(ir: dict[str, Any], name: str) -> tuple[list[str], list[float]]:
    h = find_heuristic(ir, name)
    features = h.get("features", [])
    if not features:
        raise ValueError(f"la heurística {h['name']} no tiene rasgos que ajustar")
    return [f["name"] for f in features], [
        float(constant(f["weight"])) if "weight" in f else 1.0 for f in features
    ]


# --- Partidas candidato contra base -------------------------------------------------------------


@dataclass
class Duel:
    """Juega el bot con unos pesos contra un rival y devuelve su proporción de primeros puestos
    (empates repartidos), con partidas espejo."""

    ir: dict[str, Any]
    heuristic: str
    bot: str
    opponent: str | None  # None = el mismo bot con los pesos de partida
    games: int
    num_players: int
    params: dict[str, Any]
    jobs: int
    seed: int = 0

    def score(self, weights: Sequence[float], round_seed: int) -> float:
        import gamehub_core  # pyright: ignore[reportMissingImports]

        name = CANDIDATE.format(name=self.heuristic)
        ir = with_weights(self.ir, self.heuristic, weights, name)
        candidate = {**parse_bot_spec(self.bot), "heuristic": name}
        rival = (
            parse_bot_spec(self.opponent)
            if self.opponent
            else {
                **parse_bot_spec(self.bot),
                "heuristic": self.heuristic,
            }
        )
        n = self.num_players
        jobs = [(seed, seat) for seed in range(self.games) for seat in range(n)]
        import json
        import threading

        local = threading.local()
        text = json.dumps(ir, ensure_ascii=False)

        def one(job: tuple[int, int]) -> float:
            seed, seat = job
            core = getattr(local, "core", None)
            if core is None:
                core = local.core = gamehub_core.Game(text)
            specs = [rival] * n
            specs[seat] = candidate
            r = gamehub_core.play_bots(
                core, n, self.params, specs, seed=self.seed + round_seed * 100_000 + seed
            )
            ranking = r.get("ranking")
            if not ranking:
                return 1 / n
            firsts = [k for k, x in enumerate(ranking) if x == 1]
            return 1 / len(firsts) if seat in firsts else 0.0

        with ThreadPoolExecutor(self.jobs) as pool:
            results = list(pool.map(one, jobs))
        return sum(results) / len(results)


# --- CMA-ES --------------------------------------------------------------------------------------


def _jacobi(a: list[list[float]]) -> tuple[list[float], list[list[float]]]:
    """Valores y vectores propios (en columnas) de una matriz simétrica pequeña."""
    n = len(a)
    a = [row[:] for row in a]
    v = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    for _ in range(100):
        off = sum(a[i][j] ** 2 for i in range(n) for j in range(n) if i != j)
        if off < 1e-20:
            break
        for p in range(n):
            for q in range(p + 1, n):
                if abs(a[p][q]) < 1e-30:
                    continue
                theta = (a[q][q] - a[p][p]) / (2 * a[p][q])
                t = math.copysign(1, theta) / (abs(theta) + math.sqrt(theta * theta + 1))
                c = 1 / math.sqrt(t * t + 1)
                s = t * c
                for k in range(n):
                    akp, akq = a[k][p], a[k][q]
                    a[k][p], a[k][q] = c * akp - s * akq, s * akp + c * akq
                for k in range(n):
                    apk, aqk = a[p][k], a[q][k]
                    a[p][k], a[q][k] = c * apk - s * aqk, s * apk + c * aqk
                for k in range(n):
                    vkp, vkq = v[k][p], v[k][q]
                    v[k][p], v[k][q] = c * vkp - s * vkq, s * vkp + c * vkq
    return [a[i][i] for i in range(n)], v


class Cmaes:
    """(μ/μ_w, λ)-CMA-ES de Hansen (la versión de «The CMA Evolution Strategy: A Tutorial»),
    minimizando."""

    def __init__(
        self, x0: Sequence[float], sigma: float, *, popsize: int | None = None, seed: int = 0
    ) -> None:
        self.n = n = len(x0)
        self.mean = list(x0)
        self.sigma = sigma
        self.lam = popsize or 4 + int(3 * math.log(max(n, 1)))
        self.mu = self.lam // 2
        raw = [math.log(self.mu + 0.5) - math.log(i + 1) for i in range(self.mu)]
        total = sum(raw)
        self.w = [x / total for x in raw]
        self.mueff = 1 / sum(x * x for x in self.w)
        self.cc = (4 + self.mueff / n) / (n + 4 + 2 * self.mueff / n)
        self.cs = (self.mueff + 2) / (n + self.mueff + 5)
        self.c1 = 2 / ((n + 1.3) ** 2 + self.mueff)
        self.cmu = min(
            1 - self.c1, 2 * (self.mueff - 2 + 1 / self.mueff) / ((n + 2) ** 2 + self.mueff)
        )
        self.damps = 1 + 2 * max(0.0, math.sqrt((self.mueff - 1) / (n + 1)) - 1) + self.cs
        self.pc = [0.0] * n
        self.ps = [0.0] * n
        self.C = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
        self.B = [row[:] for row in self.C]
        self.D = [1.0] * n
        self.chi = math.sqrt(n) * (1 - 1 / (4 * n) + 1 / (21 * n * n))
        self.evals = 0
        self.rng = random.Random(seed)

    def ask(self) -> list[list[float]]:
        out = []
        for _ in range(self.lam):
            z = [self.rng.gauss(0, 1) for _ in range(self.n)]
            y = [sum(self.B[i][j] * self.D[j] * z[j] for j in range(self.n)) for i in range(self.n)]
            out.append([m + self.sigma * yi for m, yi in zip(self.mean, y, strict=True)])
        return out

    def _inv_sqrt_c(self, v: Sequence[float]) -> list[float]:
        n = self.n
        t = [sum(self.B[i][j] * v[i] for i in range(n)) / self.D[j] for j in range(n)]
        return [sum(self.B[i][j] * t[j] for j in range(n)) for i in range(n)]

    def tell(self, xs: Sequence[Sequence[float]], values: Sequence[float]) -> None:
        n = self.n
        self.evals += len(xs)
        order = sorted(range(len(xs)), key=lambda k: values[k])
        best = [xs[k] for k in order[: self.mu]]
        old = self.mean
        self.mean = [sum(self.w[i] * best[i][j] for i in range(self.mu)) for j in range(n)]
        step = [(m - o) / self.sigma for m, o in zip(self.mean, old, strict=True)]
        inv = self._inv_sqrt_c(step)
        k = math.sqrt(self.cs * (2 - self.cs) * self.mueff)
        self.ps = [(1 - self.cs) * p + k * x for p, x in zip(self.ps, inv, strict=True)]
        norm_ps = math.sqrt(sum(x * x for x in self.ps))
        hsig = norm_ps / math.sqrt(
            1 - (1 - self.cs) ** (2 * self.evals / self.lam)
        ) / self.chi < 1.4 + 2 / (n + 1)
        kc = math.sqrt(self.cc * (2 - self.cc) * self.mueff)
        self.pc = [
            (1 - self.cc) * p + (kc * s if hsig else 0.0)
            for p, s in zip(self.pc, step, strict=True)
        ]
        art = [[(best[i][j] - old[j]) / self.sigma for j in range(n)] for i in range(self.mu)]
        for a in range(n):
            for b in range(n):
                rank_one = self.pc[a] * self.pc[b] + (
                    0 if hsig else self.cc * (2 - self.cc) * self.C[a][b]
                )
                rank_mu = sum(self.w[i] * art[i][a] * art[i][b] for i in range(self.mu))
                self.C[a][b] = (
                    (1 - self.c1 - self.cmu) * self.C[a][b]
                    + self.c1 * rank_one
                    + self.cmu * rank_mu
                )
        self.sigma *= math.exp((self.cs / self.damps) * (norm_ps / self.chi - 1))
        values_, vectors = _jacobi(self.C)
        self.D = [math.sqrt(max(v, 1e-20)) for v in values_]
        self.B = vectors


def tune_cmaes(
    duel: Duel,
    start: Sequence[float],
    *,
    generations: int = 10,
    sigma: float | None = None,
    seed: int = 0,
    progress: Callable[[str], None] | None = None,
) -> tuple[list[float], list[tuple[int, float, list[float]]]]:
    scale = sigma or max(0.1, 0.5 * max(abs(x) for x in start))
    es = Cmaes(start, scale, seed=seed)
    history = []
    for g in range(generations):
        xs = es.ask()
        scores = [duel.score(x, g) for x in xs]
        es.tell(xs, [-s for s in scores])
        best = max(range(len(xs)), key=scores.__getitem__)
        history.append((g, scores[best], list(xs[best])))
        if progress is not None:
            progress(f"generación {g + 1}: mejor {scores[best]:.3f} · media actual {_fmt(es.mean)}")
    return list(es.mean), history


# --- SPSA ----------------------------------------------------------------------------------------


def tune_spsa(
    duel: Duel,
    start: Sequence[float],
    *,
    iterations: int = 20,
    a: float | None = None,
    c: float | None = None,
    seed: int = 0,
    progress: Callable[[str], None] | None = None,
) -> tuple[list[float], list[tuple[int, float, list[float]]]]:
    """SPSA (Spall, 1998) maximizando la puntuación: dos evaluaciones por iteración, con una
    perturbación ±c de signo aleatorio en todos los pesos a la vez."""
    rng = random.Random(seed)
    theta = list(start)
    size = max(0.1, max(abs(x) for x in start))
    c = c or 0.2 * size
    a = a or 0.5 * size
    history = []
    for k in range(iterations):
        ak = a / (k + 1 + 0.1 * iterations) ** 0.602
        ck = c / (k + 1) ** 0.101
        delta = [rng.choice((-1.0, 1.0)) for _ in theta]
        plus = [t + ck * d for t, d in zip(theta, delta, strict=True)]
        minus = [t - ck * d for t, d in zip(theta, delta, strict=True)]
        yp, ym = duel.score(plus, 2 * k), duel.score(minus, 2 * k + 1)
        g = [(yp - ym) / (2 * ck * d) for d in delta]
        theta = [t + ak * gi for t, gi in zip(theta, g, strict=True)]
        history.append((k, (yp + ym) / 2, list(theta)))
        if progress is not None:
            progress(f"iteración {k + 1}: {yp:.3f} / {ym:.3f} · pesos {_fmt(theta)}")
    return theta, history


# --- Texel ---------------------------------------------------------------------------------------


def texel_positions(
    ir: dict[str, Any],
    heuristic: str,
    bot: str,
    games: int,
    num_players: int,
    params: dict[str, Any],
    *,
    seed: int = 0,
    jobs: int | None = None,
) -> list[tuple[list[float], float]]:
    """(rasgos de un asiento en una posición, resultado de ese asiento: 1 primero, 1/k si lo
    comparte, 0 si no) de partidas de autojuego."""
    import json
    import threading

    import gamehub_core  # pyright: ignore[reportMissingImports]

    n = num_players
    text = json.dumps(ir, ensure_ascii=False)
    local = threading.local()
    spec = parse_bot_spec(bot)
    count = len(find_heuristic(ir, heuristic).get("features", []))

    def one(g: int) -> list[tuple[list[float], float]]:
        core = getattr(local, "core", None)
        if core is None:
            core = local.core = gamehub_core.Game(text)
        r = gamehub_core.play_bots(
            core, n, params, [spec] * n, seed=seed + g, trace=True, eval=heuristic, features=True
        )
        ranking = r.get("ranking")
        if not ranking:
            return []
        firsts = [k for k, x in enumerate(ranking) if x == 1]
        out = []
        for st in r["trace"]:
            values = st[3]
            if len(values) != n * count:
                continue
            for s in range(n):
                y = 1 / len(firsts) if s in firsts else 0.0
                out.append((list(values[s * count : (s + 1) * count]), y))
        return out

    with ThreadPoolExecutor(jobs or max(1, (os.cpu_count() or 2) - 1)) as pool:
        return [p for chunk in pool.map(one, range(games)) for p in chunk]


def tune_texel(
    positions: Sequence[tuple[Sequence[float], float]],
    start: Sequence[float],
    *,
    epochs: int = 300,
    rate: float = 0.05,
    progress: Callable[[str], None] | None = None,
) -> tuple[list[float], float]:
    """Minimiza el error cuadrático medio entre el resultado y sigmoid(Σ wᵢ·rasgoᵢ) con Adam
    (los rasgos se escalan por su desviación para que el paso valga para todos)."""
    if not positions:
        raise ValueError("no hay posiciones (¿las partidas terminan?)")
    m = len(start)
    scale = []
    for j in range(m):
        col = [p[0][j] for p in positions]
        mean = sum(col) / len(col)
        sd = math.sqrt(sum((x - mean) ** 2 for x in col) / len(col))
        scale.append(sd if sd > 1e-12 else 1.0)
    w = [start[j] * scale[j] for j in range(m)]  # pesos sobre rasgos escalados
    mom = [0.0] * m
    vel = [0.0] * m
    loss = 0.0
    for epoch in range(1, epochs + 1):
        grad = [0.0] * m
        loss = 0.0
        for x, y in positions:
            z = sum(w[j] * x[j] / scale[j] for j in range(m))
            p = 1 / (1 + math.exp(-max(-60.0, min(60.0, z))))
            err = p - y
            loss += err * err
            k = 2 * err * p * (1 - p)
            for j in range(m):
                grad[j] += k * x[j] / scale[j]
        loss /= len(positions)
        for j in range(m):
            g = grad[j] / len(positions)
            mom[j] = 0.9 * mom[j] + 0.1 * g
            vel[j] = 0.999 * vel[j] + 0.001 * g * g
            mh = mom[j] / (1 - 0.9**epoch)
            vh = vel[j] / (1 - 0.999**epoch)
            w[j] -= rate * mh / (math.sqrt(vh) + 1e-8)
        if progress is not None and epoch % 50 == 0:
            progress(f"época {epoch}: error {loss:.5f}")
    return [w[j] / scale[j] for j in range(m)], loss


def _fmt(xs: Sequence[float]) -> str:
    return "[" + ", ".join(f"{x:.3f}" for x in xs) + "]"


# --- Escribir los pesos en el .game -------------------------------------------------------------


def write_weights(path: Path, heuristic: str, weights: dict[str, float]) -> None:
    """Pone `weights { … }` en la heurística del archivo (lo crea o lo reemplaza) y lo formatea."""
    from gamehub.lang import ast
    from gamehub.lang.diagnostics import CompileError, Diagnostics
    from gamehub.lang.parser import parse
    from gamehub.lang.printer import format_file
    from gamehub.lang.source import Source

    source = Source.from_path(path)
    diagnostics = Diagnostics()
    tree = parse(source, diagnostics)
    if diagnostics.has_errors:
        raise CompileError(diagnostics)
    found = None
    for item in tree.items:
        if isinstance(item, ast.GameDecl):
            for member in item.items:
                if isinstance(member, ast.HeuristicDecl) and member.name == heuristic:
                    found = member
    if found is None:
        raise KeyError(f"{path} no declara la heurística {heuristic}")

    def literal(w: float) -> ast.Expr:
        f = Fraction(_text(abs(w)))
        inner: ast.Expr = (
            ast.IntLit(int(f)) if f.denominator == 1 else ast.DecimalLit(f, _text(abs(w)))
        )
        return ast.Unary("-", inner) if w < 0 else inner

    entries = [ast.WeightEntry(name=k, value=literal(v)) for k, v in weights.items()]
    block = ast.WeightsBlock(entries=entries)
    for k, member in enumerate(found.items):
        if isinstance(member, ast.WeightsBlock):
            block.trivia = member.trivia
            block.doc = member.doc
            found.items[k] = block
            break
    else:
        last_feature = max(
            (k for k, m in enumerate(found.items) if isinstance(m, ast.FeatureDecl)), default=-1
        )
        found.items.insert(last_feature + 1, block)
    path.write_text(format_file(tree), encoding="utf-8")
