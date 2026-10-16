# SPDX-License-Identifier: Apache-2.0
"""*Perft*: cuántas secuencias de jugadas legales hay hasta una profundidad dada.

Es la prueba clásica de los generadores de jugadas del ajedrez (los valores de referencia de
las posiciones conocidas están publicados), pero vale para cualquier juego: comprueba que el
motor y las reglas generan exactamente las jugadas que deben. Cada nivel es una jugada del
primer asiento que puede actuar (como en `play_match`); los puntos de azar no cuentan como
nivel, sino que se suman todos sus resultados. Los finales antes de la profundidad pedida no
suman nada.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Sequence
from concurrent.futures import ProcessPoolExecutor
from typing import Any

from gamehub.engine.game import Game
from gamehub.engine.state import Action, State, Status


def moves(state: State, skip: Collection[str] = ()) -> list[tuple[int, Action]]:
    """Las jugadas que cuenta `perft` en `state`: las del primer asiento activo, sin las
    acciones cuyo nombre está en `skip` (p. ej. reclamar tablas)."""
    seat = state.active_seats[0]
    return [(seat, a) for a in state.legal_actions(seat) if a.name not in skip]


def perft(state: State, depth: int, skip: Collection[str] = ()) -> int:
    if state.is_terminal:
        return 0
    if state.status is Status.CHANCE:
        return sum(perft(state.apply_chance(o), depth, skip) for o, _ in state.chance_outcomes())
    if depth == 0:
        return 1
    found = moves(state, skip)
    if depth == 1:
        return len(found)
    return sum(perft(state.apply_action(s, a), depth - 1, skip) for s, a in found)


def divide(state: State, depth: int, skip: Collection[str] = ()) -> list[tuple[Action, int]]:
    """El recuento de `perft` separado por la primera jugada (para encontrar una discrepancia
    con un generador de referencia)."""
    return [(a, perft(state.apply_action(s, a), depth - 1, skip)) for s, a in moves(state, skip)]


# --- En varios procesos --------------------------------------------------------------------------

_worker: dict[str, Any] = {}


def _init(loader: Callable[[], Game], num_players: int | None, params: dict[str, Any]) -> None:
    _worker["game"] = loader()
    _worker["players"] = num_players
    _worker["params"] = params


def _subtree(path: Sequence[tuple[int, dict[str, Any]]], depth: int, skip: Sequence[str]) -> int:
    game: Game = _worker["game"]
    state = _advance(game.new_state(_worker["players"], _worker["params"]), path)
    return perft(state, depth, skip)


def _advance(state: State, path: Sequence[tuple[int, dict[str, Any]]]) -> State:
    for seat, data in path:
        state = state.apply_action(seat, state.decode_action(seat, data))
    return state


def perft_parallel(
    loader: Callable[[], Game],
    depth: int,
    *,
    jobs: int,
    skip: Collection[str] = (),
    num_players: int | None = None,
    params: dict[str, Any] | None = None,
) -> int:
    """`perft` desde el estado inicial, repartido entre `jobs` procesos. `loader` carga el juego
    en cada proceso (tiene que poder enviarse a otro proceso: una función de módulo o un
    `functools.partial`). Reparte los subárboles de los dos primeros niveles."""
    params = dict(params or {})
    game = loader()
    root = game.new_state(num_players, params)
    if depth <= 2 or jobs <= 1 or root.status is not Status.DECISION:
        return perft(root, depth, skip)
    tasks: list[list[tuple[int, dict[str, Any]]]] = []
    for s1, a1 in moves(root, skip):
        child = root.apply_action(s1, a1)
        if child.status is not Status.DECISION:
            tasks.append([(s1, a1.to_json())])
            continue
        tasks.extend([(s1, a1.to_json()), (s2, a2.to_json())] for s2, a2 in moves(child, skip))
    with ProcessPoolExecutor(jobs, initializer=_init, initargs=(loader, num_players, params)) as ex:
        futures = [ex.submit(_subtree, path, depth - len(path), list(skip)) for path in tasks]
        return sum(f.result() for f in futures)
