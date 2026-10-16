# SPDX-License-Identifier: Apache-2.0
"""Azar reproducible: PCG32 y fuentes de sorteos.

Toda sentencia aleatoria se reduce a una secuencia de **sorteos** enteros:

- `roll(n)`            → un sorteo uniforme `uniform(n)`; el valor asignado es sorteo + 1.
- `random_choice(xs)`  → `uniform(len(xs))` sobre los elementos en orden canónico.
- `shuffle(zona)`      → Fisher–Yates: para i = n-1 … 1, j = `uniform(i+1)` e intercambio (i, j).
- `sample(dist)`       → `weighted(probabilidades)`.

El **resultado** de un nodo de azar es la tupla de sorteos que consumen sus efectos. Así el mismo
nodo puede (a) muestrearse con un RNG, (b) reproducirse desde un replay o (c) enumerarse con sus
probabilidades exactas para los algoritmos de teoría de juegos.

El RNG es PCG32 (XSH-RR 64/32, O'Neill 2014), idéntico a `pcg32_srandom_r` / `pcg32_random_r`
/ `pcg32_boundedrand_r` de la implementación de referencia en C, para que otros motores (C++, WASM)
reproduzcan exactamente las mismas partidas.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from fractions import Fraction
from typing import Protocol

from gamehub.engine.errors import IllegalAction, NotEnumerable, RuleError

MASK32 = (1 << 32) - 1
MASK64 = (1 << 64) - 1
PCG_MULT = 6364136223846793005

#: Flujos (secuencias independientes) de PCG32 por propósito.
STREAM_CHANCE = 1
STREAM_SERVER = 2  # decisiones del servidor de partidas (p. ej. jugada al vencer un plazo)
STREAM_AGENT_BASE = 1000  # + asiento


class Pcg32:
    __slots__ = ("inc", "state")

    def __init__(self, seed: int, stream: int = STREAM_CHANCE) -> None:
        self.state = 0
        self.inc = ((stream << 1) | 1) & MASK64
        self.next_u32()
        self.state = (self.state + (seed & MASK64)) & MASK64
        self.next_u32()

    def next_u32(self) -> int:
        old = self.state
        self.state = (old * PCG_MULT + self.inc) & MASK64
        xorshifted = (((old >> 18) ^ old) >> 27) & MASK32
        rot = old >> 59
        return ((xorshifted >> rot) | (xorshifted << ((-rot) & 31))) & MASK32

    def below(self, n: int) -> int:
        """Entero uniforme en [0, n), sin sesgo (rechazo, como `pcg32_boundedrand_r`)."""
        if not 0 < n <= 1 << 32:
            raise ValueError(f"cota fuera de rango: {n}")
        threshold = ((1 << 32) - n) % n
        while True:
            r = self.next_u32()
            if r >= threshold:
                return r % n


class Draws(Protocol):
    """Fuente de sorteos para las sentencias aleatorias."""

    def uniform(self, n: int) -> int: ...

    def weighted(self, probs: Sequence[Fraction]) -> int: ...


class RngDraws:
    """Sorteos desde un RNG, registrando la secuencia (el resultado del nodo de azar)."""

    def __init__(self, rng: Pcg32) -> None:
        self.rng = rng
        self.taken: list[int] = []

    def uniform(self, n: int) -> int:
        _check_bound(n)
        d = self.rng.below(n)
        self.taken.append(d)
        return d

    def weighted(self, probs: Sequence[Fraction]) -> int:
        denominator = math.lcm(*(p.denominator for p in probs))
        if denominator > 1 << 32:
            raise RuleError(f"denominador de probabilidad demasiado grande: {denominator}")
        r = self.rng.below(denominator)
        acc = 0
        for i, p in enumerate(probs):
            acc += p.numerator * (denominator // p.denominator)
            if r < acc:
                self.taken.append(i)
                return i
        raise RuleError("las probabilidades no suman 1")


class ScriptedDraws:
    """Reproduce una secuencia fija de sorteos (replays, `apply_chance`)."""

    def __init__(self, draws: Sequence[int]) -> None:
        self.draws = tuple(draws)
        self.pos = 0

    def _next(self, n: int) -> int:
        if self.pos >= len(self.draws):
            raise _NeedDraw(n)
        d = self.draws[self.pos]
        if isinstance(d, bool) or not isinstance(d, int) or not 0 <= d < n:
            raise IllegalAction(f"sorteo {d!r} fuera de rango [0, {n})")
        self.pos += 1
        return d

    def uniform(self, n: int) -> int:
        _check_bound(n)
        return self._next(n)

    def weighted(self, probs: Sequence[Fraction]) -> int:
        try:
            i = self._next(len(probs))
        except _NeedDraw:
            raise _NeedDraw(len(probs), tuple(probs)) from None
        if probs[i] == 0:
            raise IllegalAction(f"sorteo {i} con probabilidad 0")
        return i

    def finished(self) -> bool:
        return self.pos == len(self.draws)


class ProbabilityDraws(ScriptedDraws):
    """Reproduce un resultado y calcula su probabilidad exacta."""

    def __init__(self, draws: Sequence[int]) -> None:
        super().__init__(draws)
        self.probability = Fraction(1)

    def uniform(self, n: int) -> int:
        d = super().uniform(n)
        self.probability /= n
        return d

    def weighted(self, probs: Sequence[Fraction]) -> int:
        i = super().weighted(probs)
        self.probability *= probs[i]
        return i


class _NeedDraw(Exception):
    def __init__(self, n: int, probs: tuple[Fraction, ...] | None = None) -> None:
        super().__init__(n)
        self.n = n
        self.probs = probs

    def options(self) -> list[tuple[int, Fraction]]:
        if self.probs is None:
            return [(i, Fraction(1, self.n)) for i in range(self.n)]
        return [(i, p) for i, p in enumerate(self.probs) if p > 0]


Outcome = tuple[int, ...]


def replay_outcome(run: Callable[[ScriptedDraws], None], outcome: Sequence[int]) -> None:
    """Ejecuta un bloque aleatorio forzando exactamente los sorteos de `outcome`."""
    draws = ScriptedDraws(outcome)
    try:
        run(draws)
    except _NeedDraw:
        raise IllegalAction(f"resultado de azar incompleto: {tuple(outcome)}") from None
    if not draws.finished():
        raise IllegalAction(f"resultado de azar con sorteos de más: {tuple(outcome)}")


def enumerate_outcomes(
    run: Callable[[ScriptedDraws], None], limit: int = 100_000
) -> list[tuple[Outcome, Fraction]]:
    """Todos los resultados (secuencias de sorteos) de un bloque aleatorio con su probabilidad.

    `run` ejecuta el bloque con la fuente de sorteos dada. Se exploran los prefijos por
    re-ejecución; si hay más de `limit` resultados se lanza `NotEnumerable`.
    """
    results: list[tuple[Outcome, Fraction]] = []
    pending: list[tuple[Outcome, Fraction]] = [((), Fraction(1))]
    while pending:
        prefix, prob = pending.pop()
        draws = ScriptedDraws(prefix)
        try:
            run(draws)
        except _NeedDraw as need:
            if len(results) + len(pending) + need.n > limit:
                raise NotEnumerable(f"más de {limit} resultados de azar") from None
            pending.extend(((*prefix, d), prob * p) for d, p in need.options())
            continue
        results.append((prefix, prob))
    results.sort()
    return results


def _check_bound(n: int) -> None:
    if n <= 0:
        raise RuleError("sorteo sobre un conjunto vacío")
