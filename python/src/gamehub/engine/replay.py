# SPDX-License-Identifier: Apache-2.0
"""Replays (`.ghr.json`): reproducción exacta de una partida y verificación paso a paso.

Formato `gamehub-replay/0.1`:

    {
      "format": "gamehub-replay/0.1",
      "game": {"id": …, "version": …, "rules_hash": "sha256:…"},
      "num_players": 3, "params": {…}, "seed": 7,
      "steps": [{"chance": [sorteos…]}, {"seat": 0, "action": {"name": …, "args": {…}}}, …],
      "digests": ["…", …],          # huella del estado tras la preparación y tras cada paso
      "result": {"node": "End", "payoffs": [1, 0, 0]}
    }

Los sorteos de azar se guardan explícitamente: un replay no depende del RNG, aunque `seed`
permite comprobar además que el azar salió de PCG32 con esa semilla.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from gamehub.engine.errors import EngineError
from gamehub.engine.game import Game
from gamehub.engine.state import State
from gamehub.engine.values import to_json

FORMAT = "gamehub-replay/0.1"


class ReplayMismatch(EngineError):
    """Al re-simular, el estado no coincide con el registrado."""


def record(state: State, seed: int | None = None, *, game: Game | None = None) -> dict[str, Any]:
    """Replay de la partida que lleva hasta `state`."""
    states = state.path()
    root = states[0]
    defn = root.game
    ir = game.ir if game is not None else defn.ir
    steps: list[dict[str, Any]] = []
    for st in states[1:]:
        step = st.step
        if step.kind == "chance":
            steps.append({"chance": list(step.outcome or ())})
        else:
            assert step.action is not None
            steps.append({"seat": step.seat, "action": step.action.to_json()})
    params = {k: to_json(v) for k, v in root.params.items() if k != "num_players"}
    data: dict[str, Any] = {
        "format": FORMAT,
        "game": {
            "id": ir["game"]["id"],
            "version": ir["game"]["version"],
            "rules_hash": defn.rules_hash,
        },
        "num_players": root.n,
        "params": params,
        "seed": seed,
        "steps": steps,
        "digests": [st.digest() for st in states],
    }
    if state.is_terminal:
        assert state.payoffs is not None
        data["result"] = {"node": state.node, "payoffs": [to_json(p) for p in state.payoffs]}
    return data


def replay(game: Game, data: dict[str, Any], *, verify: bool = True) -> State:
    """Re-simula un replay. Con `verify`, comprueba el hash de reglas y la huella de cada paso."""
    if data.get("format") != FORMAT:
        raise ReplayMismatch(f"formato desconocido: {data.get('format')!r}")
    if verify and data["game"]["rules_hash"] != game.rules_hash:
        raise ReplayMismatch("el replay es de otra versión de las reglas (hash distinto)")
    state = game.new_state(data["num_players"], data.get("params") or {})
    digests = data.get("digests") if verify else None
    _check(state, digests, 0)
    for i, step in enumerate(data["steps"], start=1):
        if "chance" in step:
            state = state.apply_chance(tuple(step["chance"]))
        else:
            seat = step["seat"]
            state = state.apply_action(seat, state.decode_action(seat, step["action"]))
        _check(state, digests, i)
    if verify and "result" in data:
        payoffs = [to_json(p) for p in state.payoffs] if state.payoffs is not None else None
        if payoffs != data["result"]["payoffs"]:
            raise ReplayMismatch(f"pagos distintos: {payoffs} ≠ {data['result']['payoffs']}")
    return state


def _check(state: State, digests: list[str] | None, i: int) -> None:
    if digests is None:
        return
    if i >= len(digests) or digests[i] != state.digest():
        raise ReplayMismatch(f"el estado diverge del registrado en el paso {i}")


def save(data: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
