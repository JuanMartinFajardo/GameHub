# SPDX-License-Identifier: Apache-2.0
"""Valoraciones de la arena (ADR-085): Elo, Glicko-2, TrueSkill y SPRT.

- **Elo**: el máximo de verosimilitud de Bradley-Terry sobre todos los resultados por parejas
  (empate = media victoria), centrado en 1500; no depende del orden de las partidas.
- **Glicko-2** (Glickman, 2012): una «ronda de valoración» por cada lote de partidas, con la
  desviación (RD) y la volatilidad de cada jugador.
- **TrueSkill** (Herbrich, Minka y Graepel, 2007) para n jugadores: propagación de esperanzas
  sobre la cadena de diferencias de rendimiento ordenada por la clasificación, con empates.
- **SPRT**: la prueba secuencial de Wald con el modelo trinomial (victoria, tablas, derrota) que
  usan cutechess y fishtest, para decidir si un bot supera a otro en al menos `elo1` puntos.

Una partida de n jugadores cuenta, para Elo y Glicko-2, como todas sus parejas: gana quien quedó
por delante (la clasificación del juego).
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

# --- Resultados por parejas ---------------------------------------------------------------------


@dataclass(frozen=True)
class Result:
    """Una partida: los jugadores por asiento y su clasificación (0 = primero; iguales =
    empate)."""

    players: tuple[str, ...]
    ranking: tuple[int, ...]

    def pairs(self) -> Iterable[tuple[str, str, float]]:
        """(a, b, puntos de a frente a b): 1 gana, 0.5 empata, 0 pierde."""
        for i in range(len(self.players)):
            for j in range(i + 1, len(self.players)):
                a, b = self.players[i], self.players[j]
                if a == b:
                    continue
                ri, rj = self.ranking[i], self.ranking[j]
                yield a, b, 1.0 if ri < rj else 0.5 if ri == rj else 0.0


def score_counts(results: Iterable[Result], a: str, b: str) -> tuple[int, int, int]:
    """Victorias, tablas y derrotas de `a` frente a `b`."""
    w = d = losses = 0
    for r in results:
        for x, y, s in r.pairs():
            if {x, y} != {a, b}:
                continue
            s = s if x == a else 1 - s
            if s == 1:
                w += 1
            elif s == 0:
                losses += 1
            else:
                d += 1
    return w, d, losses


# --- Elo -----------------------------------------------------------------------------------------


def elo(
    results: Iterable[Result], *, anchor: float = 1500.0, iterations: int = 500
) -> dict[str, float]:
    """Elo de máxima verosimilitud (Bradley-Terry, algoritmo MM de Hunter) con una pequeña
    regularización (una tabla virtual contra un jugador medio) para que no se vaya al infinito
    quien lo gana todo."""
    wins: dict[str, float] = {}
    games: dict[tuple[str, str], float] = {}
    names: set[str] = set()
    for r in results:
        for a, b, s in r.pairs():
            names |= {a, b}
            wins[a] = wins.get(a, 0.0) + s
            wins[b] = wins.get(b, 0.0) + 1 - s
            key = (a, b) if a < b else (b, a)
            games[key] = games.get(key, 0.0) + 1
    if not names:
        return {}
    strength = dict.fromkeys(names, 1.0)
    for _ in range(iterations):
        new: dict[str, float] = {}
        for i in names:
            denom = 1.0 / (strength[i] + 1.0)  # la tabla virtual contra fuerza 1
            for (a, b), n in games.items():
                if i in (a, b):
                    denom += n / (strength[a] + strength[b])
            new[i] = (wins.get(i, 0.0) + 0.5) / denom
        geo = math.exp(sum(math.log(v) for v in new.values()) / len(new))
        delta = max(abs(new[i] / geo - strength[i]) for i in names)
        strength = {i: new[i] / geo for i in names}
        if delta < 1e-10:
            break
    return {i: anchor + 400 * math.log10(strength[i]) for i in sorted(names)}


# --- Glicko-2 ------------------------------------------------------------------------------------

GLICKO_SCALE = 173.7178


@dataclass
class Glicko:
    rating: float = 1500.0
    rd: float = 350.0
    volatility: float = 0.06


def glicko2(
    periods: Iterable[Sequence[Result]], *, tau: float = 0.5, start: dict[str, Glicko] | None = None
) -> dict[str, Glicko]:
    """Glicko-2: cada elemento de `periods` es una ronda de valoración (las partidas que se
    juegan a la vez)."""
    players: dict[str, Glicko] = dict(start or {})
    for period in periods:
        games: dict[str, list[tuple[str, float]]] = {}
        for r in period:
            for a, b, s in r.pairs():
                games.setdefault(a, []).append((b, s))
                games.setdefault(b, []).append((a, 1 - s))
                players.setdefault(a, Glicko())
                players.setdefault(b, Glicko())
        updated: dict[str, Glicko] = {}
        for name, p in players.items():
            mu = (p.rating - 1500) / GLICKO_SCALE
            phi = p.rd / GLICKO_SCALE
            played = games.get(name)
            if not played:
                phi_star = math.sqrt(phi**2 + p.volatility**2)
                updated[name] = Glicko(p.rating, min(350.0, phi_star * GLICKO_SCALE), p.volatility)
                continue
            v_inv = 0.0
            delta_sum = 0.0
            for opp_name, s in played:
                o = players[opp_name]
                mu_j = (o.rating - 1500) / GLICKO_SCALE
                phi_j = o.rd / GLICKO_SCALE
                g = 1 / math.sqrt(1 + 3 * phi_j**2 / math.pi**2)
                e = 1 / (1 + math.exp(-g * (mu - mu_j)))
                v_inv += g**2 * e * (1 - e)
                delta_sum += g * (s - e)
            v = 1 / v_inv
            delta = v * delta_sum
            sigma = _volatility(phi, p.volatility, v, delta, tau)
            phi_star = math.sqrt(phi**2 + sigma**2)
            phi_new = 1 / math.sqrt(1 / phi_star**2 + 1 / v)
            mu_new = mu + phi_new**2 * delta_sum
            updated[name] = Glicko(mu_new * GLICKO_SCALE + 1500, phi_new * GLICKO_SCALE, sigma)
        players = updated
    return dict(sorted(players.items()))


def _volatility(phi: float, sigma: float, v: float, delta: float, tau: float) -> float:
    """El paso 5 de Glicko-2: la nueva volatilidad (método de Illinois)."""
    a = math.log(sigma**2)

    def f(x: float) -> float:
        ex = math.exp(x)
        return ex * (delta**2 - phi**2 - v - ex) / (2 * (phi**2 + v + ex) ** 2) - (x - a) / tau**2

    big_a = a
    if delta**2 > phi**2 + v:
        big_b = math.log(delta**2 - phi**2 - v)
    else:
        k = 1
        while f(a - k * tau) < 0:
            k += 1
        big_b = a - k * tau
    fa, fb = f(big_a), f(big_b)
    for _ in range(100):
        if abs(big_b - big_a) <= 1e-6:
            break
        c = big_a + (big_a - big_b) * fa / (fb - fa)
        fc = f(c)
        if fc * fb <= 0:
            big_a, fa = big_b, fb
        else:
            fa /= 2
        big_b, fb = c, fc
    return math.exp(big_a / 2)


# --- TrueSkill -----------------------------------------------------------------------------------

MU = 25.0
SIGMA = MU / 3
BETA = SIGMA / 2
TAU = SIGMA / 100
DRAW_PROBABILITY = 0.10


@dataclass
class Skill:
    mu: float = MU
    sigma: float = SIGMA

    @property
    def conservative(self) -> float:
        """μ − 3σ: lo que se puede asegurar que vale (la clasificación de TrueSkill)."""
        return self.mu - 3 * self.sigma


def _pdf(x: float) -> float:
    return math.exp(-x * x / 2) / math.sqrt(2 * math.pi)


def _cdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2))


def _ppf(p: float) -> float:
    """Inversa de la normal (bisección: solo se usa para el margen de empate)."""
    lo, hi = -10.0, 10.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if _cdf(mid) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _v_win(t: float, e: float) -> float:
    denom = _cdf(t - e)
    return _pdf(t - e) / denom if denom > 1e-300 else -t + e


def _w_win(t: float, e: float) -> float:
    v = _v_win(t, e)
    return v * (v + t - e)


def _v_draw(t: float, e: float) -> float:
    abs_t = abs(t)
    a, b = e - abs_t, -e - abs_t
    denom = _cdf(a) - _cdf(b)
    v = (_pdf(b) - _pdf(a)) / denom if denom > 1e-300 else a
    return -v if t < 0 else v


def _w_draw(t: float, e: float) -> float:
    abs_t = abs(t)
    a, b = e - abs_t, -e - abs_t
    denom = _cdf(a) - _cdf(b)
    if denom <= 1e-300:
        return 1.0
    v = _v_draw(abs_t, e)
    return v * v + (a * _pdf(a) - b * _pdf(b)) / denom


@dataclass
class _Gauss:
    """Una gaussiana en forma natural: pi = 1/σ², tau = μ/σ²."""

    pi: float = 0.0
    tau: float = 0.0

    @staticmethod
    def of(mu: float, sigma: float) -> _Gauss:
        pi = 1 / sigma**2
        return _Gauss(pi, pi * mu)

    @property
    def mu(self) -> float:
        return self.tau / self.pi if self.pi else 0.0

    @property
    def var(self) -> float:
        return 1 / self.pi if self.pi else math.inf

    def __mul__(self, o: _Gauss) -> _Gauss:
        return _Gauss(self.pi + o.pi, self.tau + o.tau)

    def __truediv__(self, o: _Gauss) -> _Gauss:
        return _Gauss(self.pi - o.pi, self.tau - o.tau)


def trueskill_rate(
    skills: Sequence[Skill],
    ranking: Sequence[int],
    *,
    beta: float = BETA,
    tau: float = TAU,
    draw_probability: float = DRAW_PROBABILITY,
    iterations: int = 30,
) -> list[Skill]:
    """Las habilidades nuevas tras una partida de n jugadores (uno por equipo) con su
    clasificación (0 = primero; iguales = empate)."""
    n = len(skills)
    if n < 2:
        return list(skills)
    order = sorted(range(n), key=lambda i: ranking[i])
    eps = _ppf((draw_probability + 1) / 2) * math.sqrt(2) * beta
    # Mensaje de cada jugador a su rendimiento: N(μ, σ² + τ² + β²).
    perf = [
        _Gauss.of(skills[i].mu, math.sqrt(skills[i].sigma ** 2 + tau**2 + beta**2)) for i in order
    ]
    # Mensajes de los factores de diferencia hacia cada rendimiento (izquierda y derecha).
    to_left = [_Gauss() for _ in range(n - 1)]  # factor k → rendimiento k
    to_right = [_Gauss() for _ in range(n - 1)]  # factor k → rendimiento k + 1
    trunc = [_Gauss() for _ in range(n - 1)]  # truncamiento k → diferencia k
    draws = [ranking[order[k]] == ranking[order[k + 1]] for k in range(n - 1)]

    def marginal(i: int) -> _Gauss:
        m = perf[i]
        if i > 0:
            m = m * to_right[i - 1]
        if i < n - 1:
            m = m * to_left[i]
        return m

    def update(k: int) -> float:
        a = marginal(k) / to_left[k]
        b = marginal(k + 1) / to_right[k]
        # La diferencia d = a − b que llega al truncamiento.
        d_mu, d_var = a.mu - b.mu, a.var + b.var
        incoming = _Gauss.of(d_mu, math.sqrt(d_var))
        sqrt_pi = math.sqrt(incoming.pi)
        t, e = incoming.tau / sqrt_pi, eps * sqrt_pi
        v, w = (_v_draw(t, e), _w_draw(t, e)) if draws[k] else (_v_win(t, e), _w_win(t, e))
        w = min(w, 1 - 1e-12)
        new_d = _Gauss(incoming.pi / (1 - w), (incoming.tau + sqrt_pi * v) / (1 - w))
        old = trunc[k]
        trunc[k] = new_d / incoming
        msg = trunc[k]
        # Del factor de diferencia a sus dos extremos: a = d + b, b = a − d.
        m_var = msg.var if msg.pi > 0 else math.inf
        if math.isfinite(m_var):
            to_left[k] = _Gauss.of(msg.mu + b.mu, math.sqrt(m_var + b.var))
            to_right[k] = _Gauss.of(a.mu - msg.mu, math.sqrt(m_var + a.var))
        return abs(trunc[k].pi - old.pi) + abs(trunc[k].tau - old.tau)

    for _ in range(iterations):
        change = 0.0
        for k in range(n - 1):
            change += update(k)
        for k in range(n - 2, -1, -1):
            change += update(k)
        if change < 1e-8:
            break
    out: list[Skill] = [Skill() for _ in range(n)]
    for pos, i in enumerate(order):
        chain = marginal(pos) / perf[pos]  # lo que dice la partida del rendimiento
        prior = _Gauss.of(skills[i].mu, math.sqrt(skills[i].sigma ** 2 + tau**2))
        if chain.pi <= 0:
            out[i] = Skill(prior.mu, math.sqrt(prior.var))
            continue
        likelihood = _Gauss.of(chain.mu, math.sqrt(chain.var + beta**2))
        post = prior * likelihood
        out[i] = Skill(post.mu, math.sqrt(post.var))
    return out


def trueskill(results: Iterable[Result], **options: Any) -> dict[str, Skill]:
    """TrueSkill tras todas las partidas, en orden (un jugador repetido en la misma partida
    cuenta una vez: la de su mejor puesto)."""
    skills: dict[str, Skill] = {}
    for r in results:
        best: dict[str, int] = {}
        for p, rank in zip(r.players, r.ranking, strict=True):
            best[p] = min(rank, best.get(p, rank))
        if len(best) < 2:
            continue
        names = list(best)
        new = trueskill_rate(
            [skills.get(p, Skill()) for p in names], [best[p] for p in names], **options
        )
        skills.update(zip(names, new, strict=True))
    return dict(sorted(skills.items()))


# --- SPRT ----------------------------------------------------------------------------------------


@dataclass
class Sprt:
    """La prueba secuencial: H0 = la diferencia es `elo0`, H1 = es `elo1` (en Elo logístico)."""

    elo0: float = 0.0
    elo1: float = 10.0
    alpha: float = 0.05
    beta: float = 0.05
    wins: int = 0
    draws: int = 0
    losses: int = 0
    history: list[float] = field(default_factory=list)

    @property
    def bounds(self) -> tuple[float, float]:
        return math.log(self.beta / (1 - self.alpha)), math.log((1 - self.beta) / self.alpha)

    def add(self, score: float) -> None:
        if score == 1:
            self.wins += 1
        elif score == 0:
            self.losses += 1
        else:
            self.draws += 1
        self.history.append(self.llr)

    @property
    def games(self) -> int:
        return self.wins + self.draws + self.losses

    @property
    def llr(self) -> float:
        """El logaritmo de la razón de verosimilitudes (aproximación normal de fishtest)."""
        n = self.games
        if n == 0 or self.wins + self.draws == 0 or self.losses + self.draws == 0:
            return 0.0
        w, d = self.wins / n, self.draws / n
        s = w + d / 2
        var = w + d / 4 - s * s
        if var <= 0:
            return 0.0
        s0 = 1 / (1 + 10 ** (-self.elo0 / 400))
        s1 = 1 / (1 + 10 ** (-self.elo1 / 400))
        return (s1 - s0) * (2 * s - s0 - s1) / (2 * var / n)

    @property
    def verdict(self) -> str | None:
        """ "H1" (es mejor), "H0" (no lo es) o None (seguir jugando)."""
        lower, upper = self.bounds
        if self.llr >= upper:
            return "H1"
        if self.llr <= lower:
            return "H0"
        return None


def elo_difference(score: float) -> float:
    """La diferencia de Elo que corresponde a una puntuación media (0 < score < 1)."""
    score = min(max(score, 1e-9), 1 - 1e-9)
    return -400 * math.log10(1 / score - 1)
