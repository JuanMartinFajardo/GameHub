# SPDX-License-Identifier: Apache-2.0
"""Cualquier juego de GameHub como un juego de OpenSpiel (`pyspiel`), para usar todo su catálogo
de algoritmos (CFR, explotabilidad, MCTS, aprendizaje por refuerzo…) sin reescribir el juego.

    game = to_openspiel(load_nomos(Path("games/kuhn-poker/kuhn-poker.game")))
    pyspiel.load_game(game.get_type().short_name)   # también queda registrado

OpenSpiel numera las acciones con enteros fijos (`num_distinct_actions`): al envolver el juego se
recorre su grafo de estados (información perfecta) o su árbol (imperfecta) y cada acción distinta
recibe un número; por eso solo se pueden envolver los juegos que caben en memoria. Los resultados
de azar se numeran en cada punto de azar (juntando los que llevan al mismo estado, como en
`build_tree`). Los asientos eligen uno tras otro también en los nodos simultáneos (los envíos son
ocultos). La cadena de estado de información es una clave con recuerdo perfecto de lo que el
asiento ha observado (vistas y eventos); la de observación, su vista actual.

Necesita `open_spiel` (`pip install 'gamehub[openspiel]'`).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

from gamehub.analysis.classify import classify
from gamehub.analysis.tree import (
    MAX_NODES,
    action_labels,
    build_tree,
    game_title,
    initial_state,
    merged_outcomes,
    state_graph,
)
from gamehub.engine.game import Game
from gamehub.engine.state import Action, State, Status
from gamehub.ir.hashing import canonical_json

_REGISTERED: dict[str, Any] = {}


def _action_key(action: Action) -> str:
    return canonical_json(action.to_json())


@dataclass
class _Spec:
    """Lo que OpenSpiel necesita saber del juego antes de jugarlo."""

    actions: list[Action] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    index: dict[str, int] = field(default_factory=dict)
    max_chance: int = 0
    min_utility: Fraction = Fraction(0)
    max_utility: Fraction = Fraction(0)
    utility_sum: Fraction | None = None
    max_length: int = 0
    chance: bool = False
    perfect_information: bool = True
    outcomes: dict[str, list[tuple[State, str, Fraction]]] = field(default_factory=dict)

    def add(self, action: Action, label: str) -> None:
        key = _action_key(action)
        if key not in self.index:
            self.index[key] = len(self.actions)
            self.actions.append(action)
            self.labels.append(label)

    def chance_outcomes(self, state: State) -> list[tuple[State, str, Fraction]]:
        key = state.digest()
        found = self.outcomes.get(key)
        if found is None:
            found = merged_outcomes(state)
            if len(self.outcomes) < 100_000:
                self.outcomes[key] = found
        return found


def _explore(root: State, max_nodes: int) -> _Spec:
    spec = _Spec(perfect_information=classify(root.game.ir).perfect_information)
    payoffs: list[tuple[Fraction, ...]] = []
    if spec.perfect_information:
        graph = state_graph(root, max_nodes=max_nodes)
        depth = [0] * graph.positions
        for i in graph.order:
            kind = graph.kinds[i]
            if kind == "terminal":
                payoffs.append(graph.payoffs[i])
                continue
            depth[i] = 1 + max(depth[c] for c in graph.children[i])
            if kind == "chance":
                spec.chance = True
                spec.max_chance = max(spec.max_chance, len(graph.children[i]))
                continue
            state = graph.states[i]
            actions = state.legal_actions(graph.players[i])
            for a, label in zip(actions, action_labels(actions), strict=True):
                spec.add(a, label)
        spec.max_length = depth[0]
    else:
        tree = build_tree(root, max_nodes=max_nodes, infosets=True)
        for node in tree.nodes:
            spec.max_length = max(spec.max_length, node.depth)
            if node.kind == "terminal":
                payoffs.append(node.payoffs)
            elif node.kind == "chance":
                spec.chance = True
                spec.max_chance = max(spec.max_chance, len(node.children))
        for info in tree.infosets:
            for a, label in zip(info.actions, info.labels, strict=True):
                spec.add(a, label)
    values = [u for p in payoffs for u in p]
    spec.min_utility, spec.max_utility = min(values), max(values)
    sums = {sum(p, Fraction(0)) for p in payoffs}
    spec.utility_sum = sums.pop() if len(sums) == 1 else None
    return spec


def _short_name(root: State, params: dict[str, Any] | None) -> str:
    ident = root.game.ir["game"]["id"].replace("-", "_")
    extra = hashlib.sha256(
        canonical_json(
            {"rules": root.game.rules_hash, "params": params or {}, "n": root.n}
        ).encode()
    ).hexdigest()[:10]
    return f"gamehub_{ident}_{extra}"


@dataclass(frozen=True)
class _Node:
    """El estado de GameHub y la clave de información de cada asiento. Es inmutable, así que
    copiarlo (OpenSpiel clona los estados con `deepcopy`) no copia nada."""

    state: State
    keys: tuple[str, ...]

    def __deepcopy__(self, memo: dict[int, Any]) -> _Node:
        return self

    def child(self, state: State) -> _Node:
        keys = tuple(
            hashlib.sha256((k + _observation(state, seat)).encode()).hexdigest()
            for seat, k in enumerate(self.keys)
        )
        return _Node(state, keys)


def _observation(state: State, seat: int) -> str:
    return canonical_json({"view": state.view(seat), "events": state.events(seat)})


def to_openspiel(
    game: Game | State,
    *,
    num_players: int | None = None,
    params: dict[str, Any] | None = None,
    max_nodes: int = MAX_NODES,
    numbering: str = "ir",
    engine: str = "auto",
) -> Any:
    """El juego envuelto como `pyspiel.Game` (y registrado con su `short_name`).

    Con `numbering="ir"` (por defecto) los números de acción salen de la IR sin explorar el juego
    (`gamehub.analysis.action_space`, ADR-079) y vale para cualquier juego del catálogo; con
    `"explore"`, se numeran explorando el grafo o el árbol (solo juegos pequeños, ADR-072).
    `engine`: "cpp" (el núcleo C++), "python" o "auto" (C++ si está instalado)."""
    if numbering == "ir":
        from gamehub.analysis.openspiel_ir import to_openspiel_ir

        return to_openspiel_ir(game, num_players=num_players, params=params, engine=engine)
    if numbering != "explore":
        raise ValueError(f"numeración desconocida: {numbering}")
    return _to_openspiel_explored(game, num_players=num_players, params=params, max_nodes=max_nodes)


def _to_openspiel_explored(
    game: Game | State,
    *,
    num_players: int | None = None,
    params: dict[str, Any] | None = None,
    max_nodes: int = MAX_NODES,
) -> Any:
    """La versión que numera las acciones explorando el juego (ADR-072)."""
    import numpy as np
    import pyspiel

    root = initial_state(game, num_players, params)
    name = _short_name(root, params) + "_x"
    if name in _REGISTERED:
        return _REGISTERED[name]()
    spec = _explore(root, max_nodes)
    n = root.n
    if spec.utility_sum == 0:
        utility = pyspiel.GameType.Utility.ZERO_SUM
    elif spec.utility_sum is not None:
        utility = pyspiel.GameType.Utility.CONSTANT_SUM
    else:
        utility = pyspiel.GameType.Utility.GENERAL_SUM
    game_type = pyspiel.GameType(
        short_name=name,
        long_name=f"GameHub: {game_title(game)}",
        dynamics=pyspiel.GameType.Dynamics.SEQUENTIAL,
        chance_mode=pyspiel.GameType.ChanceMode.EXPLICIT_STOCHASTIC
        if spec.chance
        else pyspiel.GameType.ChanceMode.DETERMINISTIC,
        information=pyspiel.GameType.Information.PERFECT_INFORMATION
        if spec.perfect_information
        else pyspiel.GameType.Information.IMPERFECT_INFORMATION,
        utility=utility,
        reward_model=pyspiel.GameType.RewardModel.TERMINAL,
        max_num_players=n,
        min_num_players=n,
        provides_information_state_string=True,
        provides_information_state_tensor=False,
        provides_observation_string=True,
        provides_observation_tensor=False,
        provides_factored_observation_string=False,
    )
    game_info = pyspiel.GameInfo(
        num_distinct_actions=len(spec.actions),
        max_chance_outcomes=spec.max_chance,
        num_players=n,
        min_utility=float(spec.min_utility),
        max_utility=float(spec.max_utility),
        utility_sum=None if spec.utility_sum is None else float(spec.utility_sum),
        max_game_length=max(spec.max_length, 1),
    )
    start = _Node(
        root,
        tuple(hashlib.sha256(_observation(root, s).encode()).hexdigest() for s in range(n)),
    )

    class WrappedState(pyspiel.State):
        def __init__(self, game: Any) -> None:
            super().__init__(game)
            self.node = start

        def current_player(self) -> int:
            state = self.node.state
            if state.is_terminal:
                return pyspiel.PlayerId.TERMINAL
            if state.status is Status.CHANCE:
                return pyspiel.PlayerId.CHANCE
            return state.active_seats[0]

        def _legal_actions(self, player: int) -> list[int]:
            state = self.node.state
            return sorted(spec.index[_action_key(a)] for a in state.legal_actions(player))

        def chance_outcomes(self) -> list[tuple[int, float]]:
            outcomes = spec.chance_outcomes(self.node.state)
            return [(i, float(p)) for i, (_, _, p) in enumerate(outcomes)]

        def _apply_action(self, action: int) -> None:
            state = self.node.state
            if state.status is Status.CHANCE:
                child = spec.chance_outcomes(state)[action][0]
            else:
                child = state.apply_action(state.active_seats[0], spec.actions[action])
            self.node = self.node.child(child)

        def _action_to_string(self, player: int, action: int) -> str:
            if player == pyspiel.PlayerId.CHANCE:
                outcomes = spec.chance_outcomes(self.node.state)
                return outcomes[action][1] if action < len(outcomes) else f"chance:{action}"
            return spec.labels[action]

        def is_terminal(self) -> bool:
            return self.node.state.is_terminal

        def returns(self) -> list[float]:
            payoffs = self.node.state.payoffs
            return [float(u) for u in payoffs] if payoffs is not None else [0.0] * n

        def __str__(self) -> str:
            return canonical_json(self.node.state.snapshot())

    class Observer:
        def __init__(self, iig_obs_type: Any = None, params: Any = None) -> None:
            self.perfect_recall = bool(iig_obs_type is not None and iig_obs_type.perfect_recall)
            self.tensor = np.zeros(0, np.float32)
            self.dict: dict[str, Any] = {}

        def set_from(self, state: Any, player: int) -> None:
            pass

        def string_from(self, state: Any, player: int) -> str:
            node: _Node = state.node
            if self.perfect_recall:
                return node.keys[player]
            return canonical_json(node.state.view(player))

    class WrappedGame(pyspiel.Game):
        def __init__(self, params: Any = None) -> None:
            super().__init__(game_type, game_info, params or {})

        def new_initial_state(self) -> Any:
            return WrappedState(self)

        def make_py_observer(self, iig_obs_type: Any = None, params: Any = None) -> Any:
            return Observer(iig_obs_type, params)

    pyspiel.register_game(game_type, WrappedGame)
    _REGISTERED[name] = WrappedGame
    return WrappedGame()
