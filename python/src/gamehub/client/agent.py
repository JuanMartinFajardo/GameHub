# SPDX-License-Identifier: Apache-2.0
"""Bots por la red: la misma interfaz `Agent` que en proceso (`act(observation, legal)`), pero
jugando en una sala de un servidor de partidas.

Un agente remoto recibe una `RemoteObservation` (`seat`, `view`, `events`, `clock`, `game`) con los
mismos nombres que la `Observation` del motor, y las acciones legales ya decodificadas con los
tipos del juego (`Action`). Así un agente escrito para `play_match` o la arena juega igual contra
personas en red. Ganchos opcionales: `reset(observation)` al empezar cada partida,
`observe(observation)` en cada actualización en que no le toca y `end(result)` al terminar.

Un `act` síncrono se ejecuta en un hilo para que la conexión siga atendiendo mientras piensa.
"""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import secrets
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast, overload

from gamehub.client.connection import Client, ClientError
from gamehub.engine import Action, Game
from gamehub.engine.match import FirstAgent, RandomAgent

#: Crea un agente para un asiento de un juego.
AgentFactory = Callable[[Game, int], Any]


@dataclass
class RemoteObservation:
    seat: int
    view: dict[str, Any]
    events: list[dict[str, Any]]
    clock: float | None
    game: Game


class AgentLoadError(Exception):
    """El archivo del agente no define un agente utilizable."""


def load_agent(spec: str, *, seed: int | None = None) -> AgentFactory:
    """Fábrica de agentes desde `random`, `first` o un archivo `.py` que define (por orden de
    preferencia) `make_agent(game, seat)`, una clase `Agent` (con `game` y `seat` si los acepta)
    o una función `act(observation, legal)`."""
    if spec in ("random", "first"):
        chosen = secrets.randbits(32) if seed is None else seed
        if spec == "random":
            return lambda game, seat: RandomAgent(chosen, seat)
        return lambda game, seat: FirstAgent()
    path = Path(spec)
    if path.suffix != ".py" or not path.is_file():
        raise AgentLoadError(f"{spec}: se esperaba random, first o un archivo .py")
    module = _import(path)
    make = getattr(module, "make_agent", None)
    if callable(make):
        return make
    cls = getattr(module, "Agent", None)
    if inspect.isclass(cls):
        build = cast(Callable[..., Any], cls)
        takes_args = len(inspect.signature(cls).parameters) >= 2
        return lambda game, seat: build(game, seat) if takes_args else build()
    act = getattr(module, "act", None)
    if callable(act):
        return lambda game, seat: _FunctionAgent(act)
    raise AgentLoadError(
        f"{spec}: define make_agent(game, seat), una clase Agent o act(obs, legal)"
    )


def _import(path: Path) -> Any:
    name = f"gamehub_agent_{path.stem.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AgentLoadError(f"{path}: no se puede importar")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class _FunctionAgent:
    def __init__(self, act: Callable[..., Any]) -> None:
        self._act = act

    def act(self, observation: Any, legal: list[Action]) -> Any:
        return self._act(observation, legal)


class LegalActions(Sequence[Action]):
    """Las acciones legales de un turno, decodificadas con los tipos del juego a medida que se
    piden: un agente que elige una entre miles (Mentiroso) no paga por decodificarlas todas."""

    def __init__(self, game: Game, node: str, raw: list[dict[str, Any]]) -> None:
        self.game = game
        self.node = node
        self.raw = raw
        self.decoded: dict[int, Action] = {}

    def __len__(self) -> int:
        return len(self.raw)

    @overload
    def __getitem__(self, index: int) -> Action: ...

    @overload
    def __getitem__(self, index: slice) -> list[Action]: ...

    def __getitem__(self, index: int | slice) -> Action | list[Action]:
        if isinstance(index, slice):
            return [self[i] for i in range(*index.indices(len(self.raw)))]
        if index < 0:
            index += len(self.raw)
        found = self.decoded.get(index)
        if found is None:
            found = self.decoded[index] = self.game.decode_action(self.node, self.raw[index])
        return found


class AgentRunner:
    """Juega con un agente en la sala de `client` (ya unido a ella): se declara listo, responde
    cuando le toca y encadena partidas hasta jugar `matches` (o hasta que se cierre la sala)."""

    def __init__(
        self,
        client: Client,
        factory: AgentFactory,
        game: Game,
        *,
        matches: int | None = 1,
        seed: str | None = None,
        log: Callable[[str], None] | None = None,
    ) -> None:
        self.client = client
        self.factory = factory
        self.game = game
        self.matches = matches
        self.seed = seed
        self.log = log or (lambda text: None)
        self.results: list[dict[str, Any]] = []
        self.agent: Any = None
        self._ready_sent = False
        self._acted: tuple[str, int] | None = None  # (partida, seq) de la última jugada enviada

    async def run(self) -> list[dict[str, Any]]:
        await self._maybe_ready()
        async for msg in self.client:
            kind, data = msg["type"], msg["data"]
            if kind in ("room", "welcome", "joined"):
                await self._maybe_ready()
            elif kind == "match_start":
                self._ready_sent = False
                seat = data["seat"]
                self.agent = self.factory(self.game, seat) if seat is not None else None
                await self._hook("reset", self._observation(seat, None))
            elif kind == "update":
                await self._on_update(data)
            elif kind == "match_end":
                self.results.append(data)
                await self._hook("end", data)
                if self.matches is not None and len(self.results) >= self.matches:
                    await self.client.leave()
                    break
            elif kind == "rejected":
                self.log(f"jugada rechazada ({data['reason']}): {data['detail']}")
            elif kind == "error":
                self.log(f"error del servidor ({data['code']}): {data['message']}")
                if data["code"] in ("not_allowed", "invalid_token") and self.client.session is None:
                    break
        return self.results

    async def _maybe_ready(self) -> None:
        room, seat = self.client.room, self.client.seat
        if room is None or seat is None or room["status"] != "lobby" or self._ready_sent:
            return
        if self.matches is not None and len(self.results) >= self.matches:
            return
        info = self.client.seat_info(seat)
        if info is not None and not info["ready"]:
            self._ready_sent = True
            await self.client.ready(True, self.seed)

    async def _on_update(self, data: dict[str, Any]) -> None:
        seat = self.client.seat
        if seat is None or self.agent is None:
            return
        observation = self._observation(seat, data)
        if "legal" not in data:
            await self._hook("observe", observation)
            return
        match = self.client.match
        turn = ((match or {}).get("match", {}).get("id", ""), data["seq"])
        if turn == self._acted:
            return  # la misma actualización otra vez (al reconectar): ya se jugó
        node = data["view"]["node"]
        try:
            legal = data["legal"]
            if legal["kind"] == "enumerated":
                raw = legal["actions"]
            else:
                raw = await self._progressive(node, legal["names"])
            actions = LegalActions(self.game, node, raw)
            act = self.agent.act
            if inspect.iscoroutinefunction(act):
                chosen = await act(observation, actions)
            else:
                chosen = await asyncio.to_thread(act, observation, actions)
            await self.client.act(chosen, seq=data["seq"])
        except ClientError as exc:
            # Sin conexión: al volver, el servidor reenvía el estado y se decide de nuevo.
            self.log(f"no se ha podido jugar ({exc.code}): {exc.message}")
            return
        self._acted = turn

    async def _progressive(self, node: str, names: list[str]) -> list[dict[str, Any]]:
        """Todas las acciones legales construyéndolas con `query_actions` (para agentes que las
        necesitan enumeradas cuando el servidor las da progresivas)."""
        found: list[dict[str, Any]] = []
        for name in names:
            if name == "pass":
                found.append({"name": "pass", "args": {}})
                continue
            params = [p.name for p in self.game.defn.nodes[node].actions_by_name[name].params]
            await self._extend(name, params, {}, found)
        return found

    async def _extend(
        self, name: str, params: list[str], args: dict[str, Any], found: list[dict[str, Any]]
    ) -> None:
        if len(args) == len(params):
            found.append({"name": name, "args": dict(args)})
            return
        for value in await self.client.query_actions(name, args):
            await self._extend(name, params, {**args, params[len(args)]: value}, found)

    def _observation(self, seat: int | None, data: dict[str, Any] | None) -> RemoteObservation:
        update = data or self.client.update or {}
        clocks = update.get("clocks")
        clock = None
        if clocks is not None and seat is not None:
            remaining = clocks["remaining_ms"][seat]
            clock = None if remaining is None else remaining / 1000
        return RemoteObservation(
            seat=seat if seat is not None else -1,
            view=update.get("view", {}),
            events=update.get("events", []),
            clock=clock,
            game=self.game,
        )

    async def _hook(self, name: str, arg: Any) -> None:
        hook = getattr(self.agent, name, None)
        if hook is None:
            return
        result = hook(arg)
        if inspect.isawaitable(result):
            await result
