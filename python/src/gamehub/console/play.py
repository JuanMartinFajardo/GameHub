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


def choose(legal: Sequence[Action], io: ConsoleIO) -> Action:
    """Elección de una acción: por número, o filtrando con palabras cuando hay muchas."""
    texts = [action_text(a).lower() for a in legal]
    candidates = list(range(len(legal)))
    while True:
        if len(candidates) <= PAGE:
            for i, idx in enumerate(candidates, start=1):
                io.write(f"  {i:>3}. {action_text(legal[idx])}")
            prompt = "Elige un número (o escribe palabras para filtrar, 'q' para salir): "
        else:
            io.write(f"  {len(candidates)} acciones posibles: escribe palabras para filtrar")
            prompt = "Filtro (o 'q' para salir): "
        try:
            answer = io.read(prompt).strip()
        except EOFError:
            raise Quit from None
        if answer.lower() in ("q", "salir"):
            raise Quit
        if not answer:
            candidates = list(range(len(legal)))
            continue
        if answer.isdigit() and len(candidates) <= PAGE:
            i = int(answer) - 1
            if 0 <= i < len(candidates):
                return legal[candidates[i]]
            io.write("  Número fuera de rango.")
            continue
        words = answer.lower().split()
        narrowed = [i for i in candidates if all(w in texts[i] for w in words)]
        if narrowed:
            candidates = narrowed
        else:
            io.write("  Ninguna acción coincide; se mantiene la lista anterior.")


def make_agents(seats: Sequence[str], seed: int) -> dict[int, Agent]:
    agents: dict[int, Agent] = {}
    for seat, kind in enumerate(seats):
        if kind == "random":
            agents[seat] = RandomAgent(seed, seat)
        elif kind == "first":
            agents[seat] = FirstAgent()
        elif kind != "human":
            raise ValueError(f"tipo de asiento desconocido: {kind} (usa {', '.join(SEAT_KINDS)})")
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
    agents = make_agents(seats, seed)
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
