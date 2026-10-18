# SPDX-License-Identifier: AGPL-3.0-or-later
"""El proceso hijo que ejecuta un trabajo del hub: lee su entrada (JSON) por la entrada estándar
y escribe el resultado (JSON) por la salida estándar.

No ve la base de datos ni el disco del hub: solo la IR y las opciones que le llegan. Corre con
límites de CPU, de memoria y de tiempo real (los pone el hub al lanzarlo) y solo con bots del
núcleo (ningún código ajeno).

    {"kind": "analyze", "ir": {…}}
    {"kind": "balance", "ir": {…}, "options": {…}}
    {"kind": "balance_ci", "old": {…}, "new": {…}, "options": {…}}
    {"kind": "arena", "ir": {…}, "entrants": ["greedy", "mcts:seconds=0.05"], "games": 10}
"""

from __future__ import annotations

import json
import sys
from typing import Any

#: Lo más que se puede pedir (los trabajos comparten máquina).
MAX_GAMES = 400
MAX_ENTRANTS = 8


def run(job: dict[str, Any]) -> dict[str, Any]:
    kind = job.get("kind")
    if kind == "analyze":
        return analyze(job["ir"])
    if kind == "balance":
        report = _balance(job["ir"], job.get("options", {}))
        return {"report": report.to_json(), "markdown": report.markdown()}
    if kind == "balance_ci":
        from gamehub.bots.balance import compare

        options = job.get("options", {})
        before = _balance(job["old"], options)
        after = _balance(job["new"], options)
        comparison = compare(before, after)
        return {
            "before": before.to_json(),
            "after": after.to_json(),
            "markdown": comparison.markdown(),
            "regressions": [vars(c) for c in comparison.regressions],
            "changes": [vars(c) for c in comparison.changes],
        }
    if kind == "arena":
        return arena(job)
    raise ValueError(f"tipo de trabajo desconocido: {kind}")


def analyze(ir: dict[str, Any]) -> dict[str, Any]:
    """Clasificación, tamaño estimado, ramificación, duración y recomendaciones."""
    from gamehub.analysis.feasibility import feasibility
    from gamehub.engine import Game

    result = feasibility(Game(ir), samples=200, budget=20.0, exact=True)
    return {"feasibility": result.to_json(), "lines": result.lines()}


def _balance(ir: dict[str, Any], options: dict[str, Any]) -> Any:
    from gamehub.bots.balance import BalanceOptions, balance
    from gamehub.engine import Game

    allowed = {"bot", "weak", "games", "num_players", "seed", "ladder_games", "kingmaking_games"}
    picked = {k: v for k, v in options.items() if k in allowed}
    picked["games"] = min(int(picked.get("games", 100)), MAX_GAMES)
    picked["ladder_games"] = min(int(picked.get("ladder_games", 30)), MAX_GAMES)
    picked["jobs"] = 1
    for key in ("bot", "weak"):
        if key in picked:
            _check_spec(picked[key])
    return balance(Game(ir), BalanceOptions(**picked))


def arena(job: dict[str, Any]) -> dict[str, Any]:
    from gamehub.bots.agents import parse_bot_spec
    from gamehub.bots.arena import run_arena
    from gamehub.bots.package import Entrant
    from gamehub.engine import Game

    specs = list(job.get("entrants", []))[:MAX_ENTRANTS]
    if len(specs) < 2:
        raise ValueError("la arena necesita al menos dos bots")
    entrants = []
    for text in specs:
        name, spec = text.split("=", 1) if "=" in text.split(":", 1)[0] else ("", text)
        _check_spec(spec)
        entrants.append(Entrant(name=name or spec, spec=parse_bot_spec(spec)))
    game = Game(job["ir"])
    result = run_arena(
        game,
        entrants,
        num_players=job.get("players"),
        tournament=job.get("tournament", "round-robin"),
        games=min(int(job.get("games", 10)), MAX_GAMES),
        seed=int(job.get("seed", 0)),
        jobs=1,
    )
    return {"arena": result.to_json(), "table": result.table()}


def _check_spec(spec: str) -> None:
    """Solo bots del núcleo: nada de rutas ni de código."""
    if "/" in spec or "\\" in spec or spec.endswith((".py", ".toml")):
        raise ValueError(f"en el hub solo juegan bots del núcleo: {spec}")


def main() -> None:
    job = json.loads(sys.stdin.read())
    try:
        out = {"ok": True, "result": run(job)}
    except Exception as exc:  # el error vuelve al hub como resultado del trabajo
        out = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    sys.stdout.write(json.dumps(out, ensure_ascii=False, default=str))
    sys.stdout.flush()


if __name__ == "__main__":
    main()
