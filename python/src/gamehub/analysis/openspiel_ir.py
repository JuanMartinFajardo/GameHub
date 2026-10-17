# SPDX-License-Identifier: Apache-2.0
"""Cualquier juego como juego de OpenSpiel **sin explorarlo** (F8, ADR-079).

- Las acciones llevan los números globales calculados desde la IR (`action_space`): ajedrez tiene
  20.481, Hold'em con 2 jugadores 1.205. `legal_actions` los devuelve ordenados.
- El azar se presenta exacto de una de dos formas, según el punto de azar: si sus resultados se
  pueden enumerar (como mucho `ENUMERATE_LIMIT` sorteos) y caben en `max_chance_outcomes`, como
  la lista de resultados distintos (juntando los que llevan al mismo estado, como `build_tree`);
  si no (barajar 52 cartas), **sorteo a sorteo**: cada sorteo del punto de azar es un nodo de azar
  de OpenSpiel con sus opciones y probabilidades, y el estado del juego avanza al completarse.
- Los estados son los del núcleo C++ si está instalado (o los del motor de referencia), inmutables:
  clonar un estado de OpenSpiel no copia nada.
- El estado de información de cada asiento es una clave con recuerdo perfecto de lo que ha
  observado (SHA-256 encadenado de su vista y sus eventos en cada paso); la observación, su vista.
- `max_chance_outcomes`, `max_game_length` y los pagos extremos salen del análisis estático
  cuando se puede (cotas del azar y de los pagos) y, si no, de partidas de prueba (estimaciones).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

from gamehub.analysis.action_space import action_space, chance_bound, payoff_bounds
from gamehub.analysis.classify import classify
from gamehub.engine.errors import NotEnumerable
from gamehub.engine.game import Game
from gamehub.engine.rng import STREAM_AGENT_BASE, STREAM_CHANCE, Pcg32
from gamehub.engine.state import State
from gamehub.ir.hashing import canonical_json

#: Sorteos como mucho para enumerar un punto de azar (si no, se presenta sorteo a sorteo).
ENUMERATE_LIMIT = 4096
#: Partidas de prueba para estimar lo que el análisis estático no acota (y su tiempo máximo:
#: se juegan al menos `MIN_PROBES`).
PROBES = 64
MIN_PROBES = 8
PROBE_SECONDS = 3.0
#: Estados y segundos como mucho para calcular la longitud máxima exacta de una partida.
LONGEST_BUDGET = 50_000
LONGEST_SECONDS = 2.0

_REGISTERED: dict[str, Any] = {}


# --- Motores -----------------------------------------------------------------------------------


class _Engine:
    """Lo que el envoltorio necesita de un motor (el C++ o el de referencia)."""

    def __init__(self, game: Game, n: int, given: dict[str, Any], engine: str) -> None:
        from gamehub.engine import core

        self.cpp = engine == "cpp" or (engine == "auto" and core.available())
        root_py = game.new_state(n, given)
        params = {k: v for k, v in root_py.params.items() if k != "num_players"}
        self.space = action_space(game.ir, n, params)
        self.n = n
        self.ir = game.ir
        self.params = params
        self.root: Any
        if self.cpp:
            cg = core.CoreGame(game.ir, check=False)
            self.core_game = cg
            self.cspace = core._require().ActionSpace(cg.core, self.space.to_json())
            self.root = cg.new_state(n, given).core
        else:
            self.root = root_py

    # Consultas sobre estados (del núcleo: `gamehub_core.State`; del de referencia: `State`).
    def status(self, s: Any) -> str:
        return s.status if self.cpp else s.status.value

    def player(self, s: Any) -> int:
        return s.active_seats[0]

    def legal(self, s: Any, seat: int) -> list[int]:
        if self.cpp:
            return sorted(self.cspace.legal_ids(s, seat))
        return sorted(self.space.encode(s.node, a) for a in s.legal_actions(seat))

    def apply(self, s: Any, seat: int, number: int) -> Any:
        if self.cpp:
            action = self.cspace.decode(s, number)
            if action is None:
                raise ValueError(f"la acción {number} no existe en este nodo")
            return s.apply_action(seat, action)
        return s.apply_action(seat, self.space.decode(s.node, number))

    def label(self, s: Any, number: int) -> str:
        action = self.space.decode(s.node, number)
        return str(action)

    def returns(self, s: Any) -> list[float]:
        payoffs = s.payoffs
        if payoffs is None:
            return [0.0] * self.n
        return [float(Fraction(p)) if isinstance(p, str) else float(p) for p in payoffs]

    def outcomes(self, s: Any) -> list[tuple[Any, Fraction]]:
        """Los resultados distintos del punto de azar (lanza NotEnumerable si son demasiados)."""
        raw = s.chance_outcomes(ENUMERATE_LIMIT)
        groups: dict[tuple[str, str], list[Any]] = {}
        for outcome, p in raw:
            prob = Fraction(*p) if self.cpp else p
            child = s.apply_chance(outcome)
            key = (self.snapshot(child), canonical_json(child.events(None)))
            if key in groups:
                groups[key][1] += prob
            else:
                groups[key] = [child, prob]
        return [(child, prob) for child, prob in groups.values()]

    def next_draw(self, s: Any, prefix: tuple[int, ...]) -> tuple[int, list[Fraction]] | None:
        if self.cpp:
            found = s.next_draw(prefix)
            if found is None:
                return None
            n, probs = found
            return n, [Fraction(a, b) for a, b in probs]
        from gamehub.engine.rng import ScriptedDraws, _NeedDraw

        draws = ScriptedDraws(prefix)
        try:
            s._tx(draws).run_chance()
        except _NeedDraw as need:
            return need.n, list(need.probs or ())
        return None

    def apply_outcome(self, s: Any, outcome: tuple[int, ...]) -> Any:
        return s.apply_chance(outcome)

    def snapshot(self, s: Any) -> str:
        return s.snapshot_text() if self.cpp else canonical_json(s.snapshot())

    def observation(self, s: Any, seat: int) -> str:
        if self.cpp:
            return s.observation_digest(seat)
        data = canonical_json({"view": s.view(seat), "events": s.events(seat)})
        return hashlib.sha256(data.encode()).hexdigest()

    def view_text(self, s: Any, seat: int) -> str:
        return s.view_text(seat) if self.cpp else canonical_json(s.view(seat))


# --- Nodos -------------------------------------------------------------------------------------


@dataclass
class _Node:
    """Un estado de OpenSpiel: el estado del juego, los sorteos ya hechos de un punto de azar
    presentado sorteo a sorteo, y la clave de información de cada asiento. Inmutable."""

    state: Any
    prefix: tuple[int, ...] | None
    keys: tuple[str, ...]
    #: Las opciones de azar ya calculadas y si son sorteos sueltos (si no, resultados enteros).
    _chance: list[tuple[Any, Fraction]] | None = field(default=None, compare=False)
    _split: bool = field(default=False, compare=False)

    def __deepcopy__(self, memo: dict[int, Any]) -> _Node:
        return self


def _chain(keys: tuple[str, ...], engine: _Engine, child: Any) -> tuple[str, ...]:
    return tuple(
        hashlib.sha256((k + engine.observation(child, seat)).encode()).hexdigest()
        for seat, k in enumerate(keys)
    )


# --- Estimaciones ------------------------------------------------------------------------------


@dataclass
class _Probe:
    max_outcomes: int = 0
    max_length: int = 0
    min_payoff: float | None = None
    max_payoff: float | None = None


def _probe(engine: _Engine, max_chance: int, games: int = PROBES) -> _Probe:
    import time

    probe = _Probe()
    started = time.perf_counter()
    for seed in range(games):
        if seed >= MIN_PROBES and time.perf_counter() - started > PROBE_SECONDS:
            break
        s: Any = engine.root
        chance = Pcg32(seed, STREAM_CHANCE)
        agents = [Pcg32(seed, STREAM_AGENT_BASE + k) for k in range(engine.n)]
        length = 0
        while engine.status(s) != "terminal" and length < 100_000:
            if engine.status(s) == "chance":
                try:
                    count = len(engine.outcomes(s))
                    probe.max_outcomes = max(probe.max_outcomes, count)
                    split = count > max_chance
                except NotEnumerable:
                    split = True
                if split:
                    prefix: tuple[int, ...] = ()
                    while (draw := engine.next_draw(s, prefix)) is not None:
                        prefix = (*prefix, chance.below(draw[0]))
                        length += 1
                    s = engine.apply_outcome(s, prefix)
                else:
                    if engine.cpp:
                        outcome, chance.state = s.sample_chance(chance.state, chance.inc)
                    else:
                        outcome = s.sample_chance(chance)
                    s = engine.apply_outcome(s, outcome)
                    length += 1
            else:
                seat = engine.player(s)
                legal = engine.legal(s, seat)
                s = engine.apply(s, seat, legal[agents[seat].below(len(legal))])
                length += 1
        probe.max_length = max(probe.max_length, length)
        for p in engine.returns(s):
            probe.min_payoff = p if probe.min_payoff is None else min(probe.min_payoff, p)
            probe.max_payoff = p if probe.max_payoff is None else max(probe.max_payoff, p)
    return probe


def _longest(engine: _Engine, max_chance: int, budget: int = LONGEST_BUDGET) -> int | None:
    """La longitud máxima exacta (en pasos de OpenSpiel) si el grafo de estados cabe en el
    presupuesto y no tiene ciclos; si no, None."""
    import time

    memo: dict[str, int] = {}
    on_path: set[str] = set()
    deadline = time.perf_counter() + LONGEST_SECONDS

    def children(s: Any) -> list[tuple[Any, int]] | None:
        if engine.status(s) == "terminal":
            return []
        if engine.status(s) == "chance":
            try:
                outs = engine.outcomes(s)
            except NotEnumerable:
                return None
            if len(outs) > max_chance:
                return None
            return [(child, 1) for child, _ in outs]
        seat = engine.player(s)
        return [(engine.apply(s, seat, a), 1) for a in engine.legal(s, seat)]

    import sys

    sys.setrecursionlimit(max(sys.getrecursionlimit(), 20_000))

    def depth(s: Any) -> int | None:
        key = engine.snapshot(s)
        if key in memo:
            return memo[key]
        if key in on_path or len(memo) >= budget or time.perf_counter() > deadline:
            return None
        kids = children(s)
        if kids is None:
            return None
        on_path.add(key)
        best = 0
        for child, cost in kids:
            d = depth(child)
            if d is None:
                return None
            best = max(best, cost + d)
        on_path.discard(key)
        memo[key] = best
        return best

    try:
        return depth(engine.root)
    except RecursionError:
        return None


# --- El juego de OpenSpiel ---------------------------------------------------------------------


def _short_name(game: Game, n: int, params: dict[str, Any]) -> str:
    ident = game.ir["game"]["id"].replace("-", "_")
    extra = hashlib.sha256(
        canonical_json({"rules": game.rules_hash, "params": params, "n": n}).encode()
    ).hexdigest()[:10]
    return f"gamehub_{ident}_{extra}"


def to_openspiel_ir(
    game: Game | State,
    *,
    num_players: int | None = None,
    params: dict[str, Any] | None = None,
    engine: str = "auto",
) -> Any:
    import numpy as np
    import pyspiel

    if isinstance(game, State):
        raise ValueError("con numeración desde la IR se envuelve el juego, no un estado")
    n = num_players or game.players[0]
    given = dict(params or {})
    name = _short_name(game, n, given)
    if name in _REGISTERED:
        return _REGISTERED[name]()
    eng = _Engine(game, n, given, engine)
    static_chance = chance_bound(game.ir, n, eng.params) or 0
    probe = _probe(eng, max_chance=max(static_chance, 1))
    max_chance = max(static_chance, probe.max_outcomes, 1)
    lo, hi = payoff_bounds(game.ir, n, eng.params)
    min_utility = float(lo) if lo is not None else (probe.min_payoff or 0.0)
    max_utility = float(hi) if hi is not None else (probe.max_payoff or 0.0)
    exact_length = _longest(eng, max_chance)
    max_length = exact_length if exact_length is not None else max(2 * probe.max_length, 1)
    info = classify(game.ir)
    zero_sum = info.zero_sum is True
    game_type = pyspiel.GameType(
        short_name=name,
        long_name=f"GameHub: {game.title}",
        dynamics=pyspiel.GameType.Dynamics.SEQUENTIAL,
        chance_mode=pyspiel.GameType.ChanceMode.EXPLICIT_STOCHASTIC
        if info.chance
        else pyspiel.GameType.ChanceMode.DETERMINISTIC,
        information=pyspiel.GameType.Information.PERFECT_INFORMATION
        if info.perfect_information
        else pyspiel.GameType.Information.IMPERFECT_INFORMATION,
        utility=pyspiel.GameType.Utility.ZERO_SUM
        if zero_sum
        else pyspiel.GameType.Utility.GENERAL_SUM,
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
        num_distinct_actions=eng.space.size,
        max_chance_outcomes=max_chance,
        num_players=n,
        min_utility=min_utility,
        max_utility=max_utility,
        utility_sum=0.0 if zero_sum else None,
        max_game_length=max(max_length, 1),
    )
    root = eng.root
    start = _Node(
        root,
        None,
        tuple(hashlib.sha256(eng.observation(root, s).encode()).hexdigest() for s in range(n)),
    )

    def chance_options(node: _Node) -> list[tuple[Any, Fraction]]:
        """Las opciones del nodo de azar: (estado hijo, probabilidad) o, sorteo a sorteo,
        (sorteo, probabilidad)."""
        if node._chance is not None:
            return node._chance
        options: list[tuple[Any, Fraction]] | None = None
        if node.prefix is None:
            try:
                merged = eng.outcomes(node.state)
                if len(merged) <= max_chance:
                    options = merged
            except NotEnumerable:
                pass
        if options is None:
            draw = eng.next_draw(node.state, node.prefix or ())
            assert draw is not None
            count, probs = draw
            weights = probs if probs else [Fraction(1, count)] * count
            options = [(d, p) for d, p in enumerate(weights) if p > 0]
            if len(weights) > max_chance:
                raise ValueError(f"un sorteo de {count} opciones supera max_chance_outcomes")
            node._split = True
        node._chance = options
        return options

    class WrappedState(pyspiel.State):
        def __init__(self, game: Any) -> None:
            super().__init__(game)
            self.node = start

        def current_player(self) -> int:
            node = self.node
            if node.prefix is not None:
                return pyspiel.PlayerId.CHANCE
            status = eng.status(node.state)
            if status == "terminal":
                return pyspiel.PlayerId.TERMINAL
            if status == "chance":
                return pyspiel.PlayerId.CHANCE
            return eng.player(node.state)

        def _legal_actions(self, player: int) -> list[int]:
            return eng.legal(self.node.state, player)

        def chance_outcomes(self) -> list[tuple[int, float]]:
            options = chance_options(self.node)
            if self.node._split:
                return [(d, float(p)) for d, p in options]
            return [(i, float(p)) for i, (_, p) in enumerate(options)]

        def _apply_action(self, action: int) -> None:
            node = self.node
            if self.current_player() == pyspiel.PlayerId.CHANCE:
                options = chance_options(node)
                if node._split:
                    prefix = (*(node.prefix or ()), action)
                    if eng.next_draw(node.state, prefix) is not None:
                        self.node = _Node(node.state, prefix, node.keys)
                        return
                    child = eng.apply_outcome(node.state, prefix)
                else:
                    child = options[action][0]
            else:
                child = eng.apply(node.state, eng.player(node.state), action)
            self.node = _Node(child, None, _chain(node.keys, eng, child))

        def _action_to_string(self, player: int, action: int) -> str:
            if player == pyspiel.PlayerId.CHANCE:
                return f"chance:{action}"
            return eng.label(self.node.state, action)

        def is_terminal(self) -> bool:
            return self.node.prefix is None and eng.status(self.node.state) == "terminal"

        def returns(self) -> list[float]:
            return eng.returns(self.node.state) if self.is_terminal() else [0.0] * n

        def __str__(self) -> str:
            text = eng.snapshot(self.node.state)
            if self.node.prefix:
                text += " +" + json.dumps(list(self.node.prefix))
            return text

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
            return eng.view_text(node.state, player)

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
