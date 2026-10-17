# SPDX-License-Identifier: Apache-2.0
"""Bots de terceros en un proceso aparte (ADR-086).

Un bot escrito en Python (un archivo `.py` con `make_agent`, una clase `Agent` o `act`, como los
de `gamehub bot run`) no corre en el proceso de la arena: corre en un proceso hijo con

- límites del sistema operativo: tiempo de CPU (`RLIMIT_CPU`), memoria (`RLIMIT_AS`, donde el
  sistema lo admite), archivos abiertos y sin archivos de volcado;
- un entorno vacío (solo `PATH` y `PYTHONPATH` para encontrar `gamehub`) y el directorio del bot
  como directorio de trabajo;
- un plazo por jugada: si no contesta a tiempo (o se cae, o elige una acción ilegal), el proceso
  se mata y el asiento sigue con jugadas al azar hasta el final de la partida; el fallo queda
  anotado.

El hijo solo recibe lo que vería por la red: su asiento, su vista y sus eventos (JSON por la
entrada estándar, una línea por mensaje), y contesta con el índice de la acción elegida.
"""

from __future__ import annotations

import json
import os
import selectors
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from gamehub.engine.rng import STREAM_AGENT_BASE, Pcg32
from gamehub.engine.state import Action


@dataclass
class Limits:
    seconds_per_move: float = 2.0
    cpu_seconds: int = 600
    memory_mb: int = 1024


@dataclass
class SandboxReport:
    moves: int = 0
    failures: list[str] = field(default_factory=list)


class SandboxedAgent:
    """Un agente de un archivo `.py` en un proceso hijo con límites."""

    def __init__(
        self,
        path: Path,
        ir: dict[str, Any],
        seat: int,
        *,
        limits: Limits | None = None,
        seed: int = 0,
    ) -> None:
        self.path = path.resolve()
        self.seat = seat
        self.limits = limits or Limits()
        self.report = SandboxReport()
        self.fallback: Pcg32 | None = None
        self.seed = seed
        self.proc: subprocess.Popen[str] | None = None
        self._start(ir)

    # --- proceso --------------------------------------------------------------------------------

    def _start(self, ir: dict[str, Any]) -> None:
        import gamehub

        root = str(Path(gamehub.__file__).resolve().parents[1])
        env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": root, "PYTHONHASHSEED": "0"}
        self.proc = subprocess.Popen(
            [sys.executable, "-c", _CHILD, str(self.path), str(self.seat)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            cwd=self.path.parent,
            env=env,
            preexec_fn=_limiter(self.limits) if os.name == "posix" else None,
        )
        self._send({"type": "start", "ir": ir})
        reply = self._receive(max(10.0, self.limits.seconds_per_move))
        if reply is None or reply.get("type") != "ready":
            self._fail(f"no arranca: {reply}")

    def _send(self, message: dict[str, Any]) -> bool:
        if self.proc is None or self.proc.stdin is None:
            return False
        try:
            self.proc.stdin.write(json.dumps(message) + "\n")
            self.proc.stdin.flush()
            return True
        except (BrokenPipeError, OSError):
            return False

    def _receive(self, timeout: float) -> dict[str, Any] | None:
        if self.proc is None or self.proc.stdout is None:
            return None
        sel = selectors.DefaultSelector()
        sel.register(self.proc.stdout, selectors.EVENT_READ)
        ready = sel.select(timeout)
        sel.close()
        if not ready:
            return None
        line = self.proc.stdout.readline()
        if not line:
            return None
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return None

    def _fail(self, reason: str) -> None:
        self.report.failures.append(reason)
        self.close()
        self.fallback = Pcg32(self.seed, STREAM_AGENT_BASE + self.seat)

    def close(self) -> None:
        if self.proc is not None:
            if self.proc.poll() is None:
                self.proc.kill()
            self.proc.wait()
            self.proc = None

    def __del__(self) -> None:  # pragma: no cover - limpieza
        self.close()

    # --- Agent ----------------------------------------------------------------------------------

    def act(self, observation: Any, legal: Sequence[Action]) -> Action:
        self.report.moves += 1
        if self.fallback is None:
            sent = self._send(
                {
                    "type": "act",
                    "seat": self.seat,
                    "view": observation.view,
                    "events": observation.events,
                    "legal": [a.to_json() for a in legal],
                }
            )
            reply = self._receive(self.limits.seconds_per_move) if sent else None
            index = reply.get("index") if isinstance(reply, dict) else None
            if isinstance(index, int) and 0 <= index < len(legal):
                return legal[index]
            self._fail(
                "sin respuesta a tiempo" if reply is None else f"respuesta no válida: {reply}"
            )
        assert self.fallback is not None
        return legal[self.fallback.below(len(legal))]

    def end(self, result: Any) -> None:
        self._send({"type": "end", "result": result})


def _limiter(limits: Limits) -> Any:
    def apply() -> None:  # pragma: no cover - corre en el hijo
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (limits.cpu_seconds, limits.cpu_seconds + 5))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        try:
            mem = limits.memory_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
        except (ValueError, OSError):
            pass  # macOS no admite RLIMIT_AS
        os.setsid()

    return apply


# El proceso hijo: carga el agente y contesta por la salida estándar.
_CHILD = r"""
import json, sys
from pathlib import Path
from gamehub.client.agent import RemoteObservation, load_agent
from gamehub.engine.game import Game
path, seat = Path(sys.argv[1]), int(sys.argv[2])
factory = load_agent(str(path))
agent = None
game = None
out = sys.stdout
sys.stdout = sys.stderr  # lo que imprima el bot no estropea el canal
for line in sys.stdin:
    msg = json.loads(line)
    if msg["type"] == "start":
        game = Game(msg["ir"])
        agent = factory(game, seat)
        out.write(json.dumps({"type": "ready"}) + "\n"); out.flush()
    elif msg["type"] == "act":
        node = msg["view"].get("node")
        legal = [game.decode_action(node, a) for a in msg["legal"]]
        obs = RemoteObservation(msg["seat"], msg["view"], msg["events"], None, game)
        chosen = agent.act(obs, legal)
        index = next(i for i, a in enumerate(legal) if a == chosen)
        out.write(json.dumps({"index": index}) + "\n"); out.flush()
    elif msg["type"] == "end":
        hook = getattr(agent, "end", None)
        if hook is not None:
            hook(msg["result"])
"""
