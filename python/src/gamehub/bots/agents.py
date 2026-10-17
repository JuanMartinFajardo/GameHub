# SPDX-License-Identifier: Apache-2.0
"""Los bots del núcleo C++ con la interfaz `Agent` (ADR-084).

    agent = make_bot(game, "alphabeta:seconds=0.5", seat=0, seed=7)
    play_match(game, [agent, make_bot(game, "greedy", seat=1)], seed=3)

Tipos: `random` y `first` (los del motor de referencia), `greedy` (reglas de prioridad y una
jugada adelante), `alphabeta` (minimax paranoico con la evaluación de la heurística), `mcts`
(UCT de bucle abierto con simulaciones guiadas por la heurística), `ismcts` (MCTS de conjuntos de
información: una determinización por simulación) y `pimc` (varias determinizaciones, cada una
resuelta con alfa-beta —o MCTS si la heurística no evalúa— y la media de los valores).

Opciones (`tipo:clave=valor,…`): `heuristic` (nombre, o `none`), `seconds` (por jugada), `depth`,
`iterations`, `c`, `samples`, `greedy`, `max_rollout`, `chance_samples`.

Los bots juegan en proceso con el estado real, pero solo usan lo que ve su asiento: con
información oculta deciden sobre determinizaciones (`gamehub_core.determinize`). Con el motor de
referencia, el agente reproduce la partida en C++ paso a paso (las trazas de los dos motores son
idénticas, ADR-078).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from gamehub.engine.core import CoreGame, CoreState, core_game
from gamehub.engine.game import Game
from gamehub.engine.match import FirstAgent, RandomAgent
from gamehub.engine.state import Action, State
from gamehub.engine.values import to_json

#: Bots del núcleo C++.
SEARCH_KINDS = ("greedy", "alphabeta", "mcts", "ismcts", "pimc")
#: Todos los tipos de bot.
BOT_KINDS = ("random", "first", *SEARCH_KINDS)

_INT_OPTIONS = ("depth", "iterations", "samples", "max_rollout", "chance_samples")
_FLOAT_OPTIONS = ("seconds", "c", "greedy")


class BotSpecError(ValueError):
    """Una descripción de bot que no se entiende."""


def parse_bot_spec(spec: str | dict[str, Any]) -> dict[str, Any]:
    """`"alphabeta:depth=4,heuristic=Threats"` → `{"kind": "alphabeta", "depth": 4, …}`."""
    if isinstance(spec, dict):
        out = dict(spec)
        if out.get("kind") not in BOT_KINDS:
            raise BotSpecError(f"bot desconocido: {out.get('kind')!r}")
        return out
    kind, _, rest = spec.partition(":")
    kind = kind.strip()
    if kind not in BOT_KINDS:
        raise BotSpecError(f"bot desconocido: {kind!r} (hay: {', '.join(BOT_KINDS)})")
    out: dict[str, Any] = {"kind": kind}
    for part in filter(None, (p.strip() for p in rest.split(","))):
        key, eq, value = part.partition("=")
        key, value = key.strip(), value.strip()
        if not eq:
            raise BotSpecError(f"se esperaba clave=valor: {part!r}")
        try:
            if key in _INT_OPTIONS:
                out[key] = int(value)
            elif key in _FLOAT_OPTIONS:
                out[key] = float(value)
            elif key == "heuristic":
                out[key] = None if value == "none" else value
            else:
                raise BotSpecError(f"opción de bot desconocida: {key}")
        except ValueError as e:
            raise BotSpecError(f"valor no válido para {key}: {value!r}") from e
    return out


def bot_label(spec: str | dict[str, Any]) -> str:
    """Una descripción corta y estable del bot (`alphabeta:depth=4`)."""
    parsed = parse_bot_spec(spec)
    options = ",".join(f"{k}={parsed[k]}" for k in sorted(parsed) if k not in ("kind", "seed"))
    return parsed["kind"] + (f":{options}" if options else "")


class CoreBot:
    """Un bot del núcleo C++ como `Agent` (`act(observation, legal)`)."""

    def __init__(
        self, game: Game | CoreGame, spec: str | dict[str, Any], seat: int, seed: int = 0
    ) -> None:
        self.game = game
        self.core_game = game if isinstance(game, CoreGame) else core_game(game)
        self.spec = parse_bot_spec(spec)
        options = {k: v for k, v in self.spec.items() if k != "seed"}
        options["seed"] = int(self.spec.get("seed", 0)) + seed
        self.seat = seat
        self.bot = self.core_game.core_bot(options, seat)
        self._mirror: tuple[list[Any], Any] | None = None  # (pasos aplicados, estado C++)

    @property
    def stats(self) -> dict[str, Any]:
        return dict(self.bot.stats)

    def act(self, observation: Any, legal: Sequence[Action]) -> Action:
        state = getattr(observation, "_state", None)
        if state is None:
            raise RuntimeError(
                "los bots de búsqueda juegan en proceso (necesitan el estado de la partida)"
            )
        chosen = self.bot.act(self._core_state(state))
        data = self.core_game.core.action_to_json(chosen)
        for action in legal:
            if action.to_json() == data:
                return action
        raise RuntimeError(f"el bot eligió una acción que no está entre las legales: {data}")

    def _core_state(self, state: State | CoreState) -> Any:
        if isinstance(state, CoreState):
            return state.core
        # Motor de referencia: la misma partida en C++, aplicando solo los pasos nuevos.
        steps = state.history()
        if self._mirror is not None:
            done, current = self._mirror
            if len(done) <= len(steps) and all(a is b for a, b in zip(done, steps, strict=False)):
                for step in steps[len(done) :]:
                    current = self._apply(current, step)
                self._mirror = (steps, current)
                return current
        params = {k: to_json(v) for k, v in state.params.items() if k != "num_players"}
        current = self.core_game.core.new_state(state.n, params)
        for step in steps:
            current = self._apply(current, step)
        self._mirror = (steps, current)
        return current

    def _apply(self, current: Any, step: Any) -> Any:
        match step.kind:
            case "start":
                return current
            case "chance":
                return current.apply_chance(list(step.outcome))
            case "action":
                action = current.decode_action(step.action.to_json())
                return current.apply_action(step.seat, action)
        raise RuntimeError(f"no se puede reproducir un paso {step.kind!r} en C++")


def make_bot(game: Game | CoreGame, spec: str | dict[str, Any], seat: int, seed: int = 0) -> Any:
    """Un agente para `seat`: `random` y `first` del motor de referencia; el resto, del núcleo
    C++."""
    parsed = parse_bot_spec(spec)
    if parsed["kind"] == "random":
        return RandomAgent(seed + int(parsed.get("seed", 0)), seat)
    if parsed["kind"] == "first":
        return FirstAgent()
    return CoreBot(game, parsed, seat, seed)
