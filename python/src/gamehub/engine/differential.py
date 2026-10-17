# SPDX-License-Identifier: Apache-2.0
"""Conformidad diferencial: el motor C++ contra el de referencia, paso a paso (ADR-078).

Cada partida se juega a la vez en los dos motores con los mismos agentes aleatorios (PCG32, las
mismas semillas que `fuzz`) y se compara, en cada paso:

- la huella del estado (SHA-256 de la instantánea canónica: almacén, nodo, envíos y pagos),
- el estado (azar, decisión o terminal), los asientos activos y los pagos,
- el resultado de azar sorteado con el mismo generador y las acciones legales (cuántas y la
  elegida),
- y, en las partidas "profundas" (una de cada `deep_every`), además todas las acciones legales,
  las vistas y los eventos de cada asiento, del espectador y omniscientes, los resultados de azar
  con sus probabilidades (si se pueden enumerar) y el puesto final.

Un error de reglas (`RuleError`) en un motor tiene que darse en el mismo paso en el otro.
"""

from __future__ import annotations

import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from gamehub.engine.env import PUBLIC
from gamehub.engine.errors import NotEnumerable, RuleError
from gamehub.engine.game import Game
from gamehub.engine.rng import STREAM_AGENT_BASE, STREAM_CHANCE, Pcg32
from gamehub.engine.state import Status

#: Resultados de azar como mucho para compararlos enumerados (las barajas no se enumeran).
ENUMERATE_LIMIT = 2_000


@dataclass
class DiffReport:
    games: int = 0
    steps: int = 0
    deep_games: int = 0
    rule_errors: int = 0  # partidas que acabaron en el mismo error de reglas en los dos motores
    truncated: int = 0
    differences: list[tuple[int, int, str]] = field(default_factory=list)  # (semilla, paso, qué)
    seconds: float = 0.0

    def merge(self, other: DiffReport) -> None:
        self.games += other.games
        self.steps += other.steps
        self.deep_games += other.deep_games
        self.rule_errors += other.rule_errors
        self.truncated += other.truncated
        self.differences.extend(other.differences)


class _Mismatch(Exception):
    pass


def _check(cond: bool, what: str) -> None:
    if not cond:
        raise _Mismatch(what)


def _compare_state(py: Any, cc: Any, deep: bool) -> None:
    _check(py.status is cc.status, f"estado {py.status.value} ≠ {cc.status.value}")
    _check(tuple(py.active_seats) == tuple(cc.active_seats), "asientos activos distintos")
    _check(py.digest() == cc.digest(), "huella distinta")
    if py.payoffs is not None or cc.payoffs is not None:
        _check(py.payoffs == cc.payoffs, f"pagos {py.payoffs} ≠ {cc.payoffs}")
    if not deep:
        return
    for seat in (*range(py.n), None, PUBLIC):
        _check(py.view(seat) == cc.view(seat), f"vista distinta para {seat}")
        _check(py.events(seat) == cc.events(seat), f"eventos distintos para {seat}")
    for seat in py.active_seats:
        legal_py = [a.to_json() for a in py.legal_actions(seat)]
        legal_cc = cc.core.legal_actions_json(seat)
        _check(legal_py == legal_cc, f"acciones legales distintas para {seat}")
    if py.status is Status.CHANCE:
        try:
            outcomes_py = py.chance_outcomes(ENUMERATE_LIMIT)
        except NotEnumerable:
            outcomes_py = None
        try:
            outcomes_cc = cc.chance_outcomes(ENUMERATE_LIMIT)
        except NotEnumerable:
            outcomes_cc = None
        _check(outcomes_py == outcomes_cc, "resultados de azar distintos")
    if py.is_terminal:
        _check(py.ranking() == cc.ranking(), "puestos distintos")


def compare_match(
    game: Game,
    core: Any,
    seed: int,
    *,
    num_players: int | None = None,
    params: dict[str, Any] | None = None,
    max_steps: int = 10_000,
    deep: bool = False,
) -> tuple[int, str | None, bool, bool]:
    """Juega una partida en los dos motores. Devuelve (pasos, diferencia o None, ¿error de reglas
    en ambos?, ¿truncada?)."""
    n = num_players or game.players[0]
    chance_py, chance_cc = Pcg32(seed, STREAM_CHANCE), Pcg32(seed, STREAM_CHANCE)
    agents = [Pcg32(seed, STREAM_AGENT_BASE + s) for s in range(n)]
    steps = 0

    def both(run_py: Any, run_cc: Any, *args: Any) -> tuple[Any, Any, bool]:
        """Lo mismo en los dos motores: los dos dan un resultado o los dos un RuleError."""
        try:
            a = run_py(*args)
        except RuleError as exc:
            try:
                run_cc(*args)
            except RuleError:
                return None, None, True
            raise _Mismatch(f"solo el motor de referencia falla: {exc}") from None
        try:
            b = run_cc(*args)
        except RuleError as exc:
            raise _Mismatch(f"solo el motor C++ falla: {exc}") from None
        return a, b, False

    try:
        py, cc, err = both(game.new_state, core.new_state, n, params)
        if err:
            return steps, None, True, False
        _compare_state(py, cc, deep)
        while not py.is_terminal:
            if steps >= max_steps:
                return steps, None, False, True
            if py.status is Status.CHANCE:
                # El mismo generador en los dos: cada motor sortea desde el mismo estado.
                chance_cc.state, chance_cc.inc = chance_py.state, chance_py.inc
                o_py, o_cc, err = both(
                    lambda: py.sample_chance(chance_py),  # noqa: B023 (se llama aquí mismo)
                    lambda: cc.sample_chance(chance_cc),  # noqa: B023
                )
                if err:
                    return steps, None, True, False
                _check(chance_py.state == chance_cc.state, "el azar consume otros sorteos")
                _check(tuple(o_py) == tuple(o_cc), f"azar {o_py} ≠ {o_cc}")
                py, cc, err = both(py.apply_chance, cc.apply_chance, o_py)
            else:
                seat = py.active_seats[0]
                legal = py.legal_actions(seat)
                _check(cc.count_legal(seat) == len(legal), "número de acciones legales distinto")
                k = agents[seat].below(len(legal))
                action = legal[k]
                if deep or len(legal) < 64:
                    _check(cc.legal_actions(seat)[k] == action, "acción elegida distinta")
                py, cc, err = both(py.apply_action, cc.apply_action, seat, action)
            steps += 1
            if err:
                return steps, None, True, False
            _compare_state(py, cc, deep)
    except _Mismatch as exc:
        return steps, str(exc), False, False
    return steps, None, False, False


def diff(
    game: Game,
    games: int,
    *,
    seed: int = 0,
    num_players: int | None = None,
    params: dict[str, Any] | None = None,
    max_steps: int = 10_000,
    deep_every: int = 10,
) -> DiffReport:
    """Partidas `seed … seed + games - 1` en los dos motores; una de cada `deep_every`, a fondo."""
    from gamehub.engine.core import core_game

    core = core_game(game)
    report = DiffReport()
    started = time.perf_counter()
    for i in range(games):
        s = seed + i
        deep = deep_every > 0 and s % deep_every == 0
        steps, problem, rule_error, truncated = compare_match(
            game,
            core,
            s,
            num_players=num_players,
            params=params,
            max_steps=max_steps,
            deep=deep,
        )
        report.games += 1
        report.deep_games += deep
        report.steps += steps
        report.rule_errors += rule_error
        report.truncated += truncated
        if problem is not None:
            report.differences.append((s, steps, problem))
    report.seconds = time.perf_counter() - started
    return report


_worker: dict[str, Any] = {}


def _init_worker(loader: Any) -> None:
    _worker["game"] = loader()


def _diff_chunk(seed: int, games: int, kwargs: dict[str, Any]) -> DiffReport:
    return diff(_worker["game"], games, seed=seed, **kwargs)


def diff_parallel(
    loader: Any, games: int, *, jobs: int, seed: int = 0, **kwargs: Any
) -> DiffReport:
    """`diff` repartido entre procesos (las mismas partidas y el mismo informe)."""
    started = time.perf_counter()
    size = max(1, min(500, games // (jobs * 8) or 1))
    starts = range(seed, seed + games, size)
    total = DiffReport()
    with ProcessPoolExecutor(jobs, initializer=_init_worker, initargs=(loader,)) as ex:
        futures = [ex.submit(_diff_chunk, s, min(size, seed + games - s), kwargs) for s in starts]
        for f in futures:
            total.merge(f.result())
    total.differences.sort()
    total.seconds = time.perf_counter() - started
    return total
