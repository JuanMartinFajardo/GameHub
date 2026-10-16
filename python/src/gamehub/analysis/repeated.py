# SPDX-License-Identifier: Apache-2.0
"""Juegos repetidos: torneos al estilo de Axelrod (1980) y su simulación ecológica.

El juego de etapa es una forma normal de dos jugadores (p. ej. `normal_form` del dilema del
prisionero). Las estrategias clásicas usan la convención del dilema: la estrategia 0 es
«cooperar» y la 1, «traicionar» (`actions` cambia cuáles son). Cada estrategia es un pequeño
autómata que ve la historia de la partida.

- `tournament`: todos contra todos (incluida cada una contra sí misma, como en el torneo de
  Axelrod), `rounds` rondas por partida, con ruido opcional (cada jugada se cambia con
  probabilidad `noise`) y azar reproducible (PCG32 con `seed`).
- `ecological`: la simulación ecológica del libro de Axelrod: la proporción de cada estrategia en
  la población crece con lo que cobra contra la población actual.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

from gamehub.analysis.nash import GameShapeError
from gamehub.analysis.normal_form import NormalForm
from gamehub.engine.rng import Pcg32

C, D = 0, 1

#: (mis jugadas, sus jugadas, generador) → mi jugada (C o D).
Rule = Callable[[list[int], list[int], Pcg32], int]


@dataclass(frozen=True)
class Strategy:
    name: str
    rule: Rule
    description: str = ""


def _chance(rng: Pcg32, p: Fraction) -> bool:
    """Cierto con probabilidad `p` (racional, exacta con PCG32)."""
    return rng.below(p.denominator) < p.numerator


def _tft(mine: list[int], theirs: list[int], rng: Pcg32) -> int:
    return theirs[-1] if theirs else C


def _tf2t(mine: list[int], theirs: list[int], rng: Pcg32) -> int:
    return D if theirs[-2:] == [D, D] else C


def _stft(mine: list[int], theirs: list[int], rng: Pcg32) -> int:
    return theirs[-1] if theirs else D


def _grim(mine: list[int], theirs: list[int], rng: Pcg32) -> int:
    return D if D in theirs else C


def _pavlov(mine: list[int], theirs: list[int], rng: Pcg32) -> int:
    if not mine:
        return C
    return mine[-1] if mine[-1] == theirs[-1] else 1 - mine[-1]


def _joss(mine: list[int], theirs: list[int], rng: Pcg32) -> int:
    move = _tft(mine, theirs, rng)
    return D if move == C and _chance(rng, Fraction(1, 10)) else move


def _generous(mine: list[int], theirs: list[int], rng: Pcg32) -> int:
    move = _tft(mine, theirs, rng)
    return C if move == D and _chance(rng, Fraction(1, 3)) else move


CLASSIC: tuple[Strategy, ...] = (
    Strategy("ALLC", lambda m, t, r: C, "siempre coopera"),
    Strategy("ALLD", lambda m, t, r: D, "siempre traiciona"),
    Strategy("TFT", _tft, "ojo por ojo: coopera y luego copia la última jugada del otro"),
    Strategy("TF2T", _tf2t, "solo traiciona tras dos traiciones seguidas"),
    Strategy("STFT", _stft, "ojo por ojo desconfiado: empieza traicionando"),
    Strategy("GRIM", _grim, "coopera hasta la primera traición; luego, siempre traiciona"),
    Strategy("PAVLOV", _pavlov, "si ganó repite, si perdió cambia (win-stay, lose-shift)"),
    Strategy("GTFT", _generous, "ojo por ojo generoso: perdona 1 de cada 3 traiciones"),
    Strategy("JOSS", _joss, "ojo por ojo que traiciona por sorpresa el 10 % de las veces"),
    Strategy("RANDOM", lambda m, t, r: r.below(2), "coopera o traiciona al 50 %"),
    Strategy("ALT", lambda m, t, r: len(m) % 2, "alterna: coopera, traiciona, coopera…"),
)


def classic(*names: str) -> list[Strategy]:
    """Las estrategias clásicas con esos nombres (todas si no se da ninguno)."""
    if not names:
        return list(CLASSIC)
    by_name = {s.name: s for s in CLASSIC}
    unknown = [n for n in names if n not in by_name]
    if unknown:
        raise KeyError(f"estrategias desconocidas: {', '.join(unknown)}")
    return [by_name[n] for n in names]


@dataclass
class TournamentResult:
    names: list[str]
    rounds: int
    repetitions: int
    #: Pago medio por ronda de la estrategia i contra la j.
    scores: list[list[Fraction]]
    #: Proporción de rondas en que la estrategia i coopera contra la j.
    cooperation: list[list[Fraction]] = field(default_factory=list)

    @property
    def averages(self) -> list[Fraction]:
        """Pago medio por ronda de cada estrategia contra todas (incluida ella misma)."""
        k = len(self.names)
        return [sum(row, Fraction(0)) / k for row in self.scores]

    def ranking(self) -> list[tuple[str, Fraction]]:
        return sorted(zip(self.names, self.averages, strict=True), key=lambda x: -x[1])

    def to_json(self) -> dict[str, Any]:
        return {
            "names": self.names,
            "rounds": self.rounds,
            "repetitions": self.repetitions,
            "scores": [[float(x) for x in row] for row in self.scores],
            "cooperation": [[float(x) for x in row] for row in self.cooperation],
            "ranking": [{"name": n, "score": float(s)} for n, s in self.ranking()],
        }

    def _repr_html_(self) -> str:
        from gamehub.analysis.widgets import tournament_html

        return tournament_html(self)


def play(
    stage: NormalForm,
    a: Strategy,
    b: Strategy,
    rounds: int,
    *,
    noise: Fraction = Fraction(0),
    rng: Pcg32 | None = None,
    actions: tuple[Sequence[int], Sequence[int]] = ((C, D), (C, D)),
) -> tuple[Fraction, Fraction, int, int]:
    """Una partida repetida: los pagos totales de cada uno y cuántas veces cooperó cada uno."""
    rng = rng or Pcg32(0)
    ha: list[int] = []
    hb: list[int] = []
    total_a = total_b = Fraction(0)
    for _ in range(rounds):
        x = a.rule(ha, hb, rng)
        y = b.rule(hb, ha, rng)
        if noise and _chance(rng, noise):
            x = 1 - x
        if noise and _chance(rng, noise):
            y = 1 - y
        ha.append(x)
        hb.append(y)
        u = stage.payoffs[(actions[0][x], actions[1][y])]
        total_a += u[0]
        total_b += u[1]
    return total_a, total_b, ha.count(C), hb.count(C)


def tournament(
    stage: NormalForm,
    strategies: Sequence[Strategy] | None = None,
    *,
    rounds: int = 200,
    repetitions: int = 1,
    noise: Fraction | float = 0,
    seed: int = 0,
    actions: tuple[Sequence[int], Sequence[int]] | None = None,
) -> TournamentResult:
    if stage.num_players != 2:
        raise GameShapeError("el juego de etapa tiene que ser de dos jugadores")
    if actions is None:
        if any(k < 2 for k in stage.shape):
            raise GameShapeError("cada jugador necesita al menos dos estrategias")
        actions = ((C, D), (C, D))
    strategies = list(strategies or CLASSIC)
    noise = Fraction(noise).limit_denominator(10_000)
    k = len(strategies)
    totals = [[Fraction(0)] * k for _ in range(k)]
    coop = [[Fraction(0)] * k for _ in range(k)]
    stream = 0
    for i in range(k):
        for j in range(i, k):
            for _ in range(repetitions):
                stream += 1
                ua, ub, ca, cb = play(
                    stage,
                    strategies[i],
                    strategies[j],
                    rounds,
                    noise=noise,
                    rng=Pcg32(seed, stream),
                    actions=actions,
                )
                if i == j:
                    # Contra sí misma: cuenta la media de los dos lados.
                    totals[i][i] += (ua + ub) / 2
                    coop[i][i] += Fraction(ca + cb, 2)
                else:
                    totals[i][j] += ua
                    totals[j][i] += ub
                    coop[i][j] += ca
                    coop[j][i] += cb
    games = rounds * repetitions
    return TournamentResult(
        names=[s.name for s in strategies],
        rounds=rounds,
        repetitions=repetitions,
        scores=[[x / games for x in row] for row in totals],
        cooperation=[[x / games for x in row] for row in coop],
    )


def ecological(result: TournamentResult, generations: int = 100) -> list[list[float]]:
    """La proporción de cada estrategia en cada generación (la primera, a partes iguales): cada
    una se reproduce en proporción a lo que cobra contra la población. Los pagos se desplazan para
    que sean positivos."""
    k = len(result.names)
    low = min(min(row) for row in result.scores)
    shift = 1 - low if low <= 0 else 0
    scores = [[float(x + shift) for x in row] for row in result.scores]
    shares = [1.0 / k] * k
    history = [shares[:]]
    for _ in range(generations):
        fitness = [sum(scores[i][j] * shares[j] for j in range(k)) for i in range(k)]
        mean = sum(f * s for f, s in zip(fitness, shares, strict=True))
        shares = [s * f / mean for s, f in zip(shares, fitness, strict=True)]
        history.append(shares[:])
    return history
