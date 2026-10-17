# SPDX-License-Identifier: Apache-2.0
"""Partidas en la terminal: humanos (hot-seat) y bots en el mismo dispositivo."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gamehub.console.render import action_text, event_text, view_text
from gamehub.engine.events import Event
from gamehub.engine.game import Game
from gamehub.engine.match import Agent, FirstAgent, Observation, RandomAgent
from gamehub.engine.replay import record, save
from gamehub.engine.rng import STREAM_CHANCE, Pcg32
from gamehub.engine.state import Action, State, Status

SEAT_KINDS = ("human", "random", "first")
PAGE = 30


class Quit(Exception):  # señal de abandono, no un error
    """El jugador humano ha pedido salir."""


@dataclass
class ConsoleIO:
    read: Callable[[str], str] = input
    write: Callable[[str], None] = print


class Chooser:
    """Elección de una opción entre muchas, línea a línea: por número cuando caben en una página,
    o filtrando con palabras. La comparten `gamehub play` y el cliente de red (`gamehub join`),
    que recibe las líneas cuando llegan en vez de pedirlas."""

    def __init__(self, options: Sequence[Any], label: Callable[[Any], str] = str) -> None:
        self.options = list(options)
        self.texts = [label(o) for o in self.options]
        self.candidates = list(range(len(self.options)))

    def menu(self) -> tuple[list[str], str]:
        """Líneas que mostrar y el texto de la pregunta."""
        if len(self.candidates) <= PAGE:
            lines = [f"  {i:>3}. {self.texts[idx]}" for i, idx in enumerate(self.candidates, 1)]
            return lines, "Elige un número (o escribe palabras para filtrar, 'q' para salir): "
        lines = [f"  {len(self.candidates)} acciones posibles: escribe palabras para filtrar"]
        return lines, "Filtro (o 'q' para salir): "

    def feed(self, answer: str) -> tuple[Any, str | None]:
        """Procesa una respuesta: devuelve `(opción elegida o None, aviso o None)`. Lanza `Quit`
        si se pide salir."""
        answer = answer.strip()
        if answer.lower() in ("q", "salir"):
            raise Quit
        if not answer:
            self.candidates = list(range(len(self.options)))
            return None, None
        if answer.isdigit() and len(self.candidates) <= PAGE:
            i = int(answer) - 1
            if 0 <= i < len(self.candidates):
                return self.options[self.candidates[i]], None
            return None, "  Número fuera de rango."
        words = answer.lower().split()
        narrowed = [i for i in self.candidates if all(w in self.texts[i].lower() for w in words)]
        if not narrowed:
            return None, "  Ninguna acción coincide; se mantiene la lista anterior."
        self.candidates = narrowed
        return None, None


def choose(legal: Sequence[Action], io: ConsoleIO) -> Action:
    """Elección de una acción: por número, o filtrando con palabras cuando hay muchas."""
    chooser = Chooser(legal, action_text)
    while True:
        lines, prompt = chooser.menu()
        for line in lines:
            io.write(line)
        try:
            answer = io.read(prompt)
        except EOFError:
            raise Quit from None
        chosen, notice = chooser.feed(answer)
        if notice is not None:
            io.write(notice)
        if chosen is not None:
            return chosen


def make_agents(seats: Sequence[str], seed: int, game: Game | None = None) -> dict[int, Agent]:
    """Los agentes de los asientos que no son humanos: `random`, `first` o un bot del núcleo con
    sus opciones (`alphabeta:seconds=1`, F9)."""
    agents: dict[int, Agent] = {}
    for seat, kind in enumerate(seats):
        if kind == "random":
            agents[seat] = RandomAgent(seed, seat)
        elif kind == "first":
            agents[seat] = FirstAgent()
        elif kind != "human":
            from gamehub.bots.agents import BotSpecError, make_bot

            if game is None:
                raise ValueError(f"tipo de asiento desconocido: {kind}")
            try:
                agents[seat] = make_bot(game, kind, seat, seed)
            except BotSpecError as exc:
                raise ValueError(f"{exc} (usa {', '.join(SEAT_KINDS)} o un bot)") from None
    return agents


def play_terminal(
    game: Game,
    seats: Sequence[str],
    *,
    seed: int = 0,
    params: dict[str, Any] | None = None,
    io: ConsoleIO | None = None,
    save_replay: Path | None = None,
) -> State:
    io = io or ConsoleIO()
    n = len(seats)
    agents = make_agents(seats, seed, game)
    humans = [s for s, kind in enumerate(seats) if kind == "human"]
    state = game.new_state(n, params)
    chance = Pcg32(seed, STREAM_CHANCE)
    io.write(f"{game.title} · {n} jugadores · asientos: {', '.join(seats)} · semilla {seed}")
    last_human: int | None = None
    try:
        while not state.is_terminal:
            if state.status is Status.CHANCE:
                state = state.apply_chance(state.sample_chance(chance))
                _show_events(state, humans, io)
                continue
            seat = state.active_seats[0]
            legal = state.legal_actions(seat)
            if seat in humans:
                if len(humans) > 1 and last_human is not None and last_human != seat:
                    io.write("\n" * 40)
                    try:
                        io.read(f"Turno del asiento {seat}. Pasa el dispositivo y pulsa Enter… ")
                    except EOFError:
                        raise Quit from None
                last_human = seat
                io.write("")
                io.write(view_text(game, state.view(seat), seat=seat))
                action = choose(legal, io)
            else:
                action = agents[seat].act(Observation(state, seat), legal)
            state = state.apply_action(seat, action)
            _show_events(state, humans, io)
    except Quit:
        io.write("Partida abandonada.")
        return state
    io.write("")
    io.write(view_text(game, state.view(None), seat=None))
    if save_replay is not None:
        save(record(state, seed, game=game), save_replay)
        io.write(f"Replay guardado en {save_replay}")
    return state


def _show_events(state: State, humans: Sequence[int], io: ConsoleIO) -> None:
    """Muestra lo que todos los humanos presentes ven igual (con un solo humano, lo suyo)."""
    for event in state.step.events:
        payload = _common_view(event, humans)
        if payload is not None:
            text = event_text(payload)
            if text is not None:
                io.write(f"  · {text}")


def _common_view(event: Event, humans: Sequence[int]) -> dict[str, Any] | None:
    if not humans:
        return event.full
    seen = [event.for_seat(h) for h in humans]
    first = seen[0]
    if first is None or any(s != first for s in seen[1:]):
        return None
    return first
