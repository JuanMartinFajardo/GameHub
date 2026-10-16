# SPDX-License-Identifier: Apache-2.0
"""Teoría de juegos combinatorios: Sprague–Grundy y clases de resultado.

- `grundy`: el **valor de Grundy** (nimber) de una posición de un juego imparcial con la convención
  normal (quien no puede mover pierde: quien hace la última jugada gana): el *mex* de los valores
  de sus opciones. La posición es P (pierde quien mueve) si y solo si vale 0, y el valor de una
  suma de juegos es el XOR de los valores (`nim_sum`). Se comprueba que el juego cumple la
  convención normal en cada final; los juegos *misère* no la cumplen.
- `outcome_class`: N (gana quien mueve) o P (gana el otro) —o D si puede acabar en empate— con
  juego perfecto, en cualquier juego de dos jugadores de información perfecta.
- `partizan_class`: L, R, N o P de un juego partisano, a partir de las dos posiciones de salida
  (mueve primero Left o mueve primero Right).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from gamehub.analysis.nash import GameShapeError
from gamehub.analysis.search import alphabeta, require_perfect_information
from gamehub.analysis.tree import MAX_NODES, TooLarge, action_labels, initial_state
from gamehub.engine.game import Game
from gamehub.engine.state import State, Status


def mex(values: Iterable[int]) -> int:
    """El menor natural que no está en `values` (*minimum excludant*)."""
    seen = set(values)
    k = 0
    while k in seen:
        k += 1
    return k


def nim_sum(values: Iterable[int]) -> int:
    out = 0
    for v in values:
        out ^= v
    return out


class NotNormalPlay(GameShapeError):
    pass


@dataclass(frozen=True)
class GrundyResult:
    value: int
    #: Cada jugada desde la posición y el valor de Grundy de la posición a la que lleva; las
    #: ganadoras son las que llevan a 0.
    moves: list[tuple[str, int]]
    states: int

    @property
    def winning_moves(self) -> list[str]:
        return [label for label, g in self.moves if g == 0]

    def to_json(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "outcome": "P" if self.value == 0 else "N",
            "moves": [{"move": m, "grundy": g} for m, g in self.moves],
            "winning": self.winning_moves,
            "states": self.states,
        }


def grundy(
    game: Game | State,
    *,
    num_players: int | None = None,
    params: dict[str, Any] | None = None,
    max_nodes: int = MAX_NODES,
) -> GrundyResult:
    state = initial_state(game, num_players, params)
    require_perfect_information(state)
    if state.n != 2:
        raise GameShapeError("Sprague–Grundy es para juegos de dos jugadores")
    memo: dict[str, int] = {}

    def value(s: State) -> int:
        if s.status is Status.TERMINAL:
            return 0
        if s.status is Status.CHANCE:
            raise GameShapeError("Sprague–Grundy es para juegos sin azar")
        key = s.digest()
        cached = memo.get(key)
        if cached is not None:
            return cached
        if len(memo) >= max_nodes:
            raise TooLarge("el cálculo de Grundy", max_nodes)
        seat = s.active_seats[0]
        options = []
        for a in s.legal_actions(seat):
            child = s.apply_action(seat, a)
            if child.status is Status.TERMINAL:
                _check_normal_play(child, seat)
            options.append(value(child))
        out = mex(options)
        memo[key] = out
        return out

    if state.status is Status.TERMINAL:
        return GrundyResult(0, [], 0)
    seat = state.active_seats[0]
    actions = state.legal_actions(seat)
    labels = action_labels(actions)
    moves = []
    for label, a in zip(labels, actions, strict=True):
        child = state.apply_action(seat, a)
        if child.status is Status.TERMINAL:
            _check_normal_play(child, seat)
        moves.append((label, value(child)))
    return GrundyResult(mex(g for _, g in moves), moves, len(memo) + 1)


def _check_normal_play(final: State, mover: int) -> None:
    payoffs = final.payoffs or ()
    other = 1 - mover
    if not Fraction(payoffs[mover]) > Fraction(payoffs[other]):
        raise NotNormalPlay(
            "el juego no sigue la convención normal (quien hace la última jugada tiene que "
            "ganar): los valores de Grundy no se aplican (¿es misère?)"
        )


def grundy_table(
    game: Game,
    param: str,
    values: Sequence[Any],
    *,
    params: dict[str, Any] | None = None,
) -> list[tuple[Any, int]]:
    """El valor de Grundy de la posición inicial para cada valor de un parámetro (p. ej. el
    tamaño de un montón)."""
    base = dict(params or {})
    return [(v, grundy(game, params={**base, param: v}).value) for v in values]


def outcome_class(
    game: Game | State,
    *,
    num_players: int | None = None,
    params: dict[str, Any] | None = None,
    max_nodes: int = MAX_NODES,
) -> str:
    """N si gana quien mueve, P si gana el otro, D si con juego perfecto se empata."""
    state = initial_state(game, num_players, params)
    if state.status is not Status.DECISION:
        raise GameShapeError("la posición tiene que ser de decisión")
    mover = state.active_seats[0]
    value = alphabeta(state, max_nodes=max_nodes).value
    if value[mover] > value[1 - mover]:
        return "N"
    if value[mover] < value[1 - mover]:
        return "P"
    return "D"


def partizan_class(left_first: State, right_first: State, *, left: int = 0) -> str:
    """L (gana Left empiece quien empiece), R, N (gana quien empieza) o P (gana el segundo), a
    partir de la misma posición con cada jugador a la salida. `left` es el asiento de Left."""

    def winner(state: State) -> int | None:
        v = alphabeta(state).value
        return 0 if v[0] > v[1] else 1 if v[1] > v[0] else None

    a, b = winner(left_first), winner(right_first)
    if a is None or b is None:
        raise GameShapeError("con empates no hay clase de resultado L/R/N/P")
    right = 1 - left
    if a == left and b == left:
        return "L"
    if a == right and b == right:
        return "R"
    if a == left and b == right:
        return "N"
    return "P"
