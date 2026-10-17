# SPDX-License-Identifier: Apache-2.0
"""Trazas doradas de conformidad (`spec/conformance/<juego>/seed-<n>.ghr.json`).

Son replays de partidas con agentes aleatorios y semillas fijas, con la huella del estado en
cada paso. Cualquier motor (el de referencia tras un cambio, el core C++, WASM) debe
reproducirlas exactamente.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from gamehub.engine.errors import EngineError
from gamehub.engine.game import load_game
from gamehub.engine.match import RandomAgent, play_match
from gamehub.engine.replay import record, replay
from gamehub.ir.spec import examples_dir

#: (juego, nº de jugadores, semillas)
CASES: list[tuple[str, int, tuple[int, ...]]] = [
    ("tictactoe", 2, (1, 2, 3)),
    ("prisoners-dilemma", 2, (1, 2)),
    ("rock-paper-scissors", 2, (1, 2)),
    ("nim", 2, (1, 2, 3)),
    ("kuhn-poker", 2, (1, 2, 3, 4)),
    ("mentiroso", 3, (1, 2)),
]


def conformance_dir() -> Path:
    return examples_dir().parent.parent / "conformance"


def build() -> dict[Path, dict[str, Any]]:
    traces: dict[Path, dict[str, Any]] = {}
    for name, n, seeds in CASES:
        game = load_game(examples_dir() / f"{name}.ir.json")
        for seed in seeds:
            agents = [RandomAgent(seed, s) for s in range(n)]
            result = play_match(game, agents, seed=seed, num_players=n)
            traces[conformance_dir() / name / f"seed-{seed}.ghr.json"] = record(
                result.state, seed, game=game
            )
    return traces


def render(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n"


def sync(*, write: bool) -> list[str]:
    """Comprueba (o regenera) las trazas. Devuelve la lista de problemas."""
    problems: list[str] = []
    for path, data in build().items():
        text = render(data)
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current == text:
            continue
        if write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        else:
            problems.append(f"{path.name} de {path.parent.name}: desactualizada o ausente")
    return problems


def verify_all() -> list[str]:
    """Re-simula todas las trazas guardadas con el motor de referencia y, si está instalado, con
    el núcleo C++ (F8): las trazas son el contrato entre los motores."""
    from gamehub.engine.core import available, core_game

    problems: list[str] = []
    for path in sorted(conformance_dir().glob("*/*.ghr.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        game = load_game(examples_dir() / f"{path.parent.name}.ir.json")
        engines: list[tuple[str, Any]] = [("", game)]
        if available():
            engines.append(("C++: ", core_game(game)))
        for label, engine in engines:
            try:
                replay(engine, data)
            except EngineError as exc:
                problems.append(f"{label}{path.parent.name}/{path.name}: {exc}")
    return problems
