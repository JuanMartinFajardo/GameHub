# SPDX-License-Identifier: Apache-2.0
"""Drivers: el bucle de partida vive fuera del motor (ADR-004).

- `Agent`: interfaz de un jugador automático en proceso (los agentes en proceso son código de
  confianza; los bots remotos solo reciben JSON por el protocolo).
- `play_match`: juega una partida completa con agentes; el azar sale de PCG32(semilla).
- `fuzz`: muchas partidas aleatorias para encontrar errores de reglas.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Protocol

from gamehub.engine.errors import RuleError
from gamehub.engine.game import Game
from gamehub.engine.rng import STREAM_AGENT_BASE, STREAM_CHANCE, Pcg32
from gamehub.engine.state import Action, State, Status


class Observation:
    """Lo que un agente puede mirar en su turno (calculado bajo demanda)."""

    def __init__(self, state: State, seat: int) -> None:
        self._state = state
        self.seat = seat

    @property
    def view(self) -> dict[str, Any]:
        return self._state.view(self.seat)

    @property
    def events(self) -> list[dict[str, Any]]:
        return self._state.events(self.seat)


class Agent(Protocol):
    def act(self, observation: Observation, legal: Sequence[Action]) -> Action: ...


class RandomAgent:
    """Elige uniformemente entre las acciones legales (reproducible con su semilla)."""

    def __init__(self, seed: int = 0, seat: int = 0) -> None:
        self.rng = Pcg32(seed, STREAM_AGENT_BASE + seat)

    def act(self, observation: Observation, legal: Sequence[Action]) -> Action:
        return legal[self.rng.below(len(legal))]


class FirstAgent:
    """Siempre la primera acción legal (determinista; útil en tests)."""

    def act(self, observation: Observation, legal: Sequence[Action]) -> Action:
        return legal[0]


@dataclass
class MatchResult:
    state: State
    steps: int
    truncated: bool = False

    @property
    def payoffs(self) -> tuple[Any, ...] | None:
        return self.state.payoffs


def play_match(
    game: Game,
    agents: Mapping[int, Agent] | Sequence[Agent],
    *,
    seed: int = 0,
    num_players: int | None = None,
    params: dict[str, Any] | None = None,
    max_steps: int = 100_000,
    on_step: Callable[[State], None] | None = None,
) -> MatchResult:
    """Juega hasta un nodo terminal (o `max_steps`). Si varios asientos pueden actuar a la vez,
    se les pregunta en el orden de `active_seats`."""
    state = game.new_state(num_players, params)
    chance = Pcg32(seed, STREAM_CHANCE)
    steps = 0
    while not state.is_terminal:
        if steps >= max_steps:
            return MatchResult(state, steps, truncated=True)
        if state.status is Status.CHANCE:
            state = state.apply_chance(state.sample_chance(chance))
        else:
            seat = state.active_seats[0]
            action = agents[seat].act(Observation(state, seat), state.legal_actions(seat))
            state = state.apply_action(seat, action)
        steps += 1
        if on_step is not None:
            on_step(state)
    return MatchResult(state, steps)


@dataclass
class FuzzReport:
    games: int = 0
    completed: int = 0
    truncated: int = 0
    errors: list[tuple[int, str]] = field(default_factory=list)
    total_steps: int = 0
    payoff_sums: list[Fraction] = field(default_factory=list)
    seconds: float = 0.0

    @property
    def mean_steps(self) -> float:
        return self.total_steps / self.games if self.games else 0.0

    @property
    def mean_payoffs(self) -> list[float]:
        return [float(p / self.completed) for p in self.payoff_sums] if self.completed else []


def fuzz(
    game: Game,
    games: int,
    *,
    seed: int = 0,
    num_players: int | None = None,
    params: dict[str, Any] | None = None,
    max_steps: int = 10_000,
    on_error: Callable[[int, State | None, RuleError], None] | None = None,
) -> FuzzReport:
    """Partidas con agentes aleatorios; la partida i usa la semilla `seed + i`."""
    report = FuzzReport()
    started = time.perf_counter()
    n = num_players or game.players[0]
    report.payoff_sums = [Fraction(0)] * n
    for i in range(games):
        match_seed = seed + i
        agents = [RandomAgent(match_seed, s) for s in range(n)]
        tracker = _LastState()
        report.games += 1
        try:
            result = play_match(
                game,
                agents,
                seed=match_seed,
                num_players=n,
                params=params,
                max_steps=max_steps,
                on_step=tracker.update,
            )
        except RuleError as exc:
            report.errors.append((match_seed, str(exc)))
            if on_error is not None:
                on_error(match_seed, tracker.state, exc)
            continue
        report.total_steps += result.steps
        if result.truncated:
            report.truncated += 1
            continue
        report.completed += 1
        assert result.payoffs is not None
        report.payoff_sums = [
            a + b for a, b in zip(report.payoff_sums, result.payoffs, strict=True)
        ]
    report.seconds = time.perf_counter() - started
    return report


class _LastState:
    """Recuerda el último estado alcanzado (para informar de errores con su historial)."""

    def __init__(self) -> None:
        self.state: State | None = None

    def update(self, state: State) -> None:
        self.state = state
