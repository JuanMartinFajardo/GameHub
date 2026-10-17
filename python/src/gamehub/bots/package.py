# SPDX-License-Identifier: Apache-2.0
"""Paquetes de bots (ADR-086): un directorio con `bot.toml`.

```toml
[bot]
name = "c4-profundo"            # minúsculas y guiones
version = "1.0.0"
game = "connect-four"           # el id del juego
rules = "sha256:…"              # opcional: el hash de reglas para el que se escribió
kind = "alphabeta"              # random, first, greedy, alphabeta, mcts, ismcts, pimc o python
heuristic = "Threats"           # opcional: una heurística del juego
entry = "agent.py"              # kind = "python": el agente (make_agent, Agent o act)

[options]                       # opciones del bot (seconds, depth, iterations…)
seconds = 0.2

[limits]                        # kind = "python": límites del proceso
seconds_per_move = 2.0
cpu_seconds = 600
memory_mb = 1024
```

Los bots de los tipos del núcleo son de confianza (los ejecuta GameHub); los de `kind = "python"`
corren en un proceso aparte con límites (`gamehub.bots.sandbox`). Un bot se identifica en la
arena por `nombre@versión`.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from gamehub.bots.agents import BOT_KINDS, bot_label, parse_bot_spec
from gamehub.bots.sandbox import Limits

NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class BotPackageError(ValueError):
    """Un `bot.toml` que no se puede usar."""


@dataclass
class Entrant:
    """Un participante de la arena: un bot del núcleo (`spec`) o uno de Python en su proceso
    (`python`)."""

    name: str
    spec: dict[str, Any] | None = None
    python: Path | None = None
    limits: Limits = field(default_factory=Limits)
    game: str | None = None
    rules: str | None = None

    @property
    def is_core(self) -> bool:
        """¿Juega en el núcleo C++ (todos los tipos predefinidos, también random y first)?"""
        return self.spec is not None

    def check(self, game_id: str, rules_hash: str) -> None:
        """Comprueba que el bot es para este juego (y estas reglas, si las fija)."""
        if self.game is not None and self.game != game_id:
            raise BotPackageError(f"{self.name} es un bot de {self.game}, no de {game_id}")
        if self.rules is not None and self.rules != rules_hash:
            raise BotPackageError(
                f"{self.name} se escribió para otras reglas ({self.rules[:19]}…, no "
                f"{rules_hash[:19]}…)"
            )


def load_bot_package(path: Path) -> Entrant:
    toml = path / "bot.toml" if path.is_dir() else path
    if not toml.is_file():
        raise BotPackageError(f"{path}: no hay bot.toml")
    try:
        data = tomllib.loads(toml.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise BotPackageError(f"{toml}: {exc}") from exc
    bot = data.get("bot")
    if not isinstance(bot, dict):
        raise BotPackageError(f"{toml}: falta la sección [bot]")
    name = bot.get("name")
    if not isinstance(name, str) or not NAME.match(name):
        raise BotPackageError(f"{toml}: name tiene que ir en minúsculas y con guiones")
    version = str(bot.get("version", "0.1.0"))
    kind = bot.get("kind", "python")
    if kind not in (*BOT_KINDS, "python"):
        raise BotPackageError(f"{toml}: kind desconocido: {kind}")
    limits_data = data.get("limits", {})
    limits = Limits(
        seconds_per_move=float(limits_data.get("seconds_per_move", Limits.seconds_per_move)),
        cpu_seconds=int(limits_data.get("cpu_seconds", Limits.cpu_seconds)),
        memory_mb=int(limits_data.get("memory_mb", Limits.memory_mb)),
    )
    entrant = Entrant(
        name=f"{name}@{version}",
        limits=limits,
        game=bot.get("game"),
        rules=bot.get("rules"),
    )
    if kind == "python":
        entry = toml.parent / str(bot.get("entry", "agent.py"))
        if not entry.is_file():
            raise BotPackageError(f"{toml}: no existe {entry.name}")
        entrant.python = entry
    else:
        spec: dict[str, Any] = {"kind": kind, **data.get("options", {})}
        if "heuristic" in bot:
            spec["heuristic"] = bot["heuristic"]
        entrant.spec = parse_bot_spec(spec)
    return entrant


def load_entrant(text: str) -> Entrant:
    """Un participante desde la línea de comandos: un paquete (directorio o `bot.toml`), un
    archivo `.py` (en su proceso, con los límites por defecto) o un tipo del núcleo con opciones
    (`alphabeta:seconds=0.5`). `nombre=…` le pone nombre: `fuerte=alphabeta:depth=6`."""
    name = None
    if "=" in text.split(":", 1)[0]:
        name, text = text.split("=", 1)
    path = Path(text)
    if path.is_dir() or path.name == "bot.toml":
        entrant = load_bot_package(path)
    elif path.suffix == ".py":
        if not path.is_file():
            raise BotPackageError(f"no existe {path}")
        entrant = Entrant(name=path.stem, python=path)
    else:
        spec = parse_bot_spec(text)
        entrant = Entrant(name=bot_label(spec), spec=spec)
    if name:
        entrant.name = name
    return entrant
