# SPDX-License-Identifier: Apache-2.0
"""Los análisis en el núcleo C++ (F8), con los mismos resultados que sus versiones en Python:

- `perft`: secuencias de jugadas legales (ajedrez: *perft(5)* = 4.865.609 en segundos).
- `alphabeta`: alfa-beta exacta con tabla de transposiciones de claves de 128 bits (el hash
  estructural del estado), expectimax en el azar; devuelve una `Solution` como
  `gamehub.analysis.search.alphabeta`.
- `retrograde`: análisis retrógrado de juegos deterministas de dos jugadores con ciclos o sin ellos
  (lo que la inducción hacia atrás no admite).
- `cfr`: el mismo árbol y el mismo CFR/CFR+ que `gamehub.analysis.cfr` (mismas claves de los
  conjuntos de información y mismas operaciones: la misma estrategia).
- `mcts`: UCT con partidas aleatorias (n jugadores, azar muestreado).

Necesitan `gamehub-core` (`available()`).
"""

from __future__ import annotations

from fractions import Fraction
from typing import Any

from gamehub.analysis.search import Solution, require_perfect_information
from gamehub.analysis.tree import action_labels, chance_label, initial_state
from gamehub.engine.core import CoreGame, CoreState, available, core_game
from gamehub.engine.game import Game
from gamehub.engine.state import State

__all__ = [
    "alphabeta",
    "available",
    "cfr",
    "mccfr",
    "mcts",
    "perft",
    "retrograde",
    "solve_wdl",
]


def _core() -> Any:
    from gamehub.engine import core

    return core._require()


def _root(
    game: Game | State | CoreGame | CoreState,
    num_players: int | None = None,
    params: dict[str, Any] | None = None,
) -> CoreState:
    if isinstance(game, CoreState):
        return game
    if isinstance(game, State):
        raise ValueError("los análisis en C++ empiezan desde el estado inicial de un juego")
    engine = game if isinstance(game, CoreGame) else core_game(game)
    return engine.new_state(num_players, params, events=False, history=False)


def perft(
    game: Game | CoreGame | CoreState,
    depth: int,
    skip: list[str] | tuple[str, ...] = (),
    *,
    num_players: int | None = None,
    params: dict[str, Any] | None = None,
) -> int:
    return _core().perft(_root(game, num_players, params).core, depth, list(skip))


def alphabeta(
    game: Game | State,
    *,
    num_players: int | None = None,
    params: dict[str, Any] | None = None,
    max_nodes: int = 100_000_000,
) -> Solution:
    """Como `gamehub.analysis.search.alphabeta` (sin profundidad limitada), en C++."""
    reference = initial_state(game, num_players, params)
    require_perfect_information(reference)
    if not isinstance(game, Game):
        raise ValueError("alfa-beta en C++ resuelve un juego desde su estado inicial")
    root = _root(game, num_players, params)
    result = _core().alphabeta(root.core, max_nodes)
    value = Fraction(*result["value"])
    total = Fraction(*result["total"])
    best: list[str] = []
    if root.status.value == "decision":
        labels = action_labels(root.legal_actions(root.active_seats[0]))
        best = [labels[k] for k in result["best"]]
    pv: list[str] = []
    state: Any = core_game(game).new_state(num_players, params)  # con eventos, para las etiquetas
    for step in result["pv"]:
        kind, _, index = step.partition(":")
        k = int(index)
        if kind == "chance":
            outcome = state.chance_outcomes()[k][0]
            child = state.apply_chance(outcome)
            pv.append(chance_label(child, outcome))  # type: ignore[arg-type]
            state = child
        else:
            seat = state.active_seats[0]
            actions = state.legal_actions(seat)
            pv.append(action_labels(actions)[k])
            state = state.apply_action(seat, actions[k])
    return Solution(
        value=(value, total - value),
        best=best,
        pv=pv,
        states=result["states"],
        method="alphabeta_cpp",
    )


def retrograde(
    game: Game,
    *,
    num_players: int | None = None,
    params: dict[str, Any] | None = None,
    max_positions: int = 50_000_000,
) -> dict[str, Any]:
    """El resultado con juego óptimo de quien empieza (1 gana, 0 tablas, -1 pierde), cuántas
    posiciones hay y cuántas se ganan, empatan o pierden para quien decide en ellas."""
    reference = initial_state(game, num_players, params)
    require_perfect_information(reference)
    return dict(_core().retrograde(_root(game, num_players, params).core, max_positions))


def cfr(
    game: Game,
    iterations: int,
    *,
    plus: bool = True,
    measure_every: int = 0,
    num_players: int | None = None,
    params: dict[str, Any] | None = None,
    max_nodes: int = 10_000_000,
) -> dict[str, Any]:
    """CFR/CFR+ en C++ sobre la forma extensiva: la política media por conjunto de información
    (en el orden de `build_tree`, con sus claves), su explotabilidad y la convergencia."""
    root = core_game(game).new_state(num_players, params)
    return dict(_core().cfr(root.core, iterations, plus, measure_every, max_nodes))


def solve_wdl(
    game: Game,
    *,
    num_players: int | None = None,
    params: dict[str, Any] | None = None,
    table_bits: int = 24,
    threads: int = 1,
    max_nodes: int | None = None,
    max_seconds: float = 0.0,
) -> dict[str, Any]:
    """Ganar (1), empatar (0) o perder (-1) para el asiento 0, con búsquedas de ventana nula, una
    tabla de transposiciones de 2^table_bits entradas y la heurística de historia (sin
    conocimiento del juego); con `threads` > 1, Lazy SMP."""
    import json

    reference = initial_state(game, num_players, params)
    require_perfect_information(reference)
    native = _core().Game(json.dumps(game.ir, ensure_ascii=False))
    return dict(
        _core().solve_wdl(
            native,
            reference.n,
            params or {},
            table_bits,
            threads,
            max_nodes if max_nodes is not None else 2**63,
            max_seconds,
        )
    )


def mccfr(
    game: Game,
    iterations: int,
    *,
    sampling: str = "external",
    seed: int = 0,
    epsilon: float = 0.6,
    exploitability: bool = False,
    num_players: int | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """MCCFR sin construir el árbol (`sampling` "external" u "outcome"): la estrategia media de
    cada conjunto de información visitado (con las claves de `build_tree`) y, si se pide y el
    árbol cabe, su explotabilidad."""
    root = core_game(game).new_state(num_players, params)
    return dict(_core().mccfr(root.core, iterations, sampling, seed, epsilon, exploitability))


def mcts(
    state: CoreState, simulations: int, *, c: float = 1.4, seed: int = 0, max_seconds: float = 0
) -> dict[str, Any]:
    """UCT desde una decisión: visitas y valor medio de cada acción legal y la más visitada
    (`max_seconds` > 0: para también al pasar ese tiempo)."""
    result = dict(_core().mcts(state.core, simulations, c, seed, max_seconds=max_seconds))
    node = state.node
    result["actions"] = [
        state.game.action_from_json(node, state.game.core.action_to_json(a))
        for a in result["actions"]
    ]
    return result


def solve_available() -> bool:
    return available()
