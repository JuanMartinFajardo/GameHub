# SPDX-License-Identifier: Apache-2.0
"""Los comandos de la Fase 9: `gamehub heuristics`, `arena`, `sprt`, `balance`, `tune` y
`solve` (la definición de sus opciones está en `gamehub.cli`)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _say(text: str) -> None:
    print(text, file=sys.stderr, flush=True)


def _game(args: argparse.Namespace) -> Any:
    from gamehub.cli import _load_game

    return _load_game(args.game, getattr(args, "name", None))


def _params(args: argparse.Namespace) -> dict[str, Any]:
    from gamehub.cli import _params as parse

    return parse(args.param)


def _need_core() -> bool:
    from gamehub.engine.core import available

    if not available():
        print("error: hace falta el núcleo C++ (pip install 'gamehub[core]')", file=sys.stderr)
        return False
    return True


# --- heuristics ----------------------------------------------------------------------------------


def heuristics(args: argparse.Namespace) -> int:
    from gamehub.bots.heuristic import Heuristic, constant
    from gamehub.ir.hashing import heuristic_hash

    game = _game(args)
    found = game.ir.get("heuristics", [])
    if not found:
        print(f"{game.id} no tiene heurísticas")
        return 1
    state = None
    if args.evaluate:
        state = game.new_state(args.players, _params(args))
    for h in found:
        print(f"heuristic {h['name']}  {heuristic_hash(game.ir, h['name'])}")
        for f in h.get("features", []):
            weight = constant(f["weight"]) if "weight" in f else 1
            print(f"  feature {f['name']}  (peso {weight})")
        print(
            f"  {len(h.get('prefer', []))} reglas prefer · {len(h.get('order', []))} reglas order"
        )
        if state is not None and h.get("features"):
            ev = Heuristic(game, h["name"])
            for seat in range(state.n):
                values = ev.feature_values(state, seat)
                shown = ", ".join(f"{k}={v}" for k, v in values.items())
                print(f"  estado inicial, asiento {seat}: {shown} → {ev.evaluate(state, seat)}")
    return 0


# --- arena ---------------------------------------------------------------------------------------


def arena(args: argparse.Namespace) -> int:
    from gamehub.bots.arena import load_history, run_arena, save_history
    from gamehub.bots.package import BotPackageError, load_entrant

    if not _need_core():
        return 2
    game = _game(args)
    try:
        entrants = [load_entrant(text) for text in args.bots]
    except (BotPackageError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    done = [0]

    def progress(record: Any) -> None:
        done[0] += 1
        if done[0] % 10 == 0 and not args.quiet:
            _say(f"{done[0]} partidas")

    try:
        result = run_arena(
            game,
            entrants,
            num_players=args.players,
            params=_params(args),
            tournament=args.tournament,
            games=args.games,
            mirror=not args.no_mirror,
            rounds=args.rounds,
            seed=args.seed,
            jobs=args.jobs,
            max_steps=args.max_steps,
            progress=progress,
        )
    except (BotPackageError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    history = load_history(args.db, result.rules_hash) if args.db else []
    if args.format == "json":
        print(json.dumps(result.to_json(history), ensure_ascii=False, indent=2))
    else:
        print(result.table(history))
    if args.db:
        save_history(args.db, result)
        added = len(result.matches)
        _say(f"{added} partidas añadidas a {args.db} (reglas {result.rules_hash[:19]}…)")
    return 0


# --- sprt ----------------------------------------------------------------------------------------


def sprt(args: argparse.Namespace) -> int:
    from gamehub.bots.arena import run_arena
    from gamehub.bots.package import load_entrant
    from gamehub.bots.ratings import Sprt, elo_difference

    if not _need_core():
        return 2
    game = _game(args)
    a, b = load_entrant(args.a), load_entrant(args.b)
    if a.name == b.name:
        b.name += " (B)"
    test = Sprt(args.elo0, args.elo1, args.alpha, args.beta)
    seed = args.seed
    while test.verdict is None and test.games < args.max_games:
        result = run_arena(
            game,
            [a, b],
            num_players=2,
            params=_params(args),
            games=args.batch,
            mirror=True,
            seed=seed,
            jobs=args.jobs,
        )
        seed += args.batch
        for m in result.matches:
            if not m.ok:
                continue
            seat = m.players.index(a.name)
            mine, theirs = m.ranking[seat], m.ranking[1 - seat]
            test.add(1.0 if mine < theirs else 0.5 if mine == theirs else 0.0)
        score = (test.wins + test.draws / 2) / max(1, test.games)
        _say(
            f"{test.games} partidas: +{test.wins} ={test.draws} -{test.losses} "
            f"({elo_difference(score):+.0f} Elo) · LLR {test.llr:.2f} "
            f"[{test.bounds[0]:.2f}, {test.bounds[1]:.2f}]"
        )
    verdict = test.verdict
    if verdict == "H1":
        print(f"H1: {a.name} es mejor que {b.name} en al menos {args.elo1:g} Elo")
    elif verdict == "H0":
        print(f"H0: {a.name} no es mejor que {b.name} en {args.elo1:g} Elo")
    else:
        print(f"sin decisión tras {test.games} partidas (LLR {test.llr:.2f})")
    return 0 if verdict == "H1" else 1


# --- balance -------------------------------------------------------------------------------------


def balance(args: argparse.Namespace) -> int:
    from gamehub.bots.balance import DEFAULT_LADDER, BalanceOptions, balance, compare

    if not _need_core():
        return 2
    from gamehub.cli import split_seats

    options = BalanceOptions(
        bot=args.bot,
        weak=args.weak,
        games=args.games,
        num_players=args.players,
        params=_params(args),
        seed=args.seed,
        jobs=args.jobs,
        ladder=split_seats(args.ladder) if args.ladder else DEFAULT_LADDER,
        ladder_games=args.ladder_games,
        kingmaking_games=args.kingmaking,
        heuristic=args.heuristic,
    )
    say = None if args.quiet else _say
    game = _game(args)
    report = balance(game, options, progress=say)
    if args.against is None:
        if args.format == "json":
            print(json.dumps(report.to_json(), ensure_ascii=False, indent=2, default=str))
        else:
            print(report.markdown(), end="")
        return 0
    from gamehub.cli import _load_game

    old = _load_game(args.against, None)
    if say is not None:
        say(f"la otra versión: {args.against}")
    before = balance(old, options, progress=say)
    comparison = compare(before, report)
    if args.format == "json":
        print(
            json.dumps(
                {
                    "before": before.to_json(),
                    "after": report.to_json(),
                    "changes": [c.__dict__ for c in comparison.changes],
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )
    else:
        print(comparison.markdown(), end="")
    return 1 if comparison.regressions and args.fail_on_regression else 0


# --- tune ----------------------------------------------------------------------------------------


def tune(args: argparse.Namespace) -> int:
    from gamehub.bots.heuristic import find_heuristic
    from gamehub.bots.tuning import (
        Duel,
        TuneResult,
        initial_weights,
        texel_positions,
        tune_cmaes,
        tune_spsa,
        tune_texel,
        write_weights,
    )

    if not _need_core():
        return 2
    game = _game(args)
    h = find_heuristic(game.ir, args.heuristic)["name"]
    features, start = initial_weights(game.ir, h)
    n = args.players or game.players[0]
    say = None if args.quiet else _say
    result = TuneResult(h, args.method, features, start, list(start))
    jobs = args.jobs or 0
    if args.method == "texel":
        positions = texel_positions(
            game.ir, h, args.bot, args.games, n, _params(args), seed=args.seed, jobs=jobs or None
        )
        if say:
            say(f"{len(positions)} posiciones de {args.games} partidas")
        result.weights, loss = tune_texel(
            positions, start, epochs=args.iterations * 30, progress=say
        )
        if say:
            say(f"error cuadrático medio final: {loss:.5f}")
    else:
        import os

        duel = Duel(
            game.ir,
            h,
            args.bot,
            args.opponent,
            args.games,
            n,
            _params(args),
            jobs or max(1, (os.cpu_count() or 2) - 1),
            args.seed,
        )
        if args.method == "cmaes":
            result.weights, result.history = tune_cmaes(
                duel, start, generations=args.iterations, seed=args.seed, progress=say
            )
        else:
            result.weights, result.history = tune_spsa(
                duel, start, iterations=args.iterations, seed=args.seed, progress=say
            )
        result.score = duel.score(result.weights, 999)
        if say:
            say(f"pesos finales contra los de partida: {result.score:.3f} de primeros puestos")
    print(result.block())
    if args.write:
        path = args.game if args.game.suffix == ".game" else None
        if path is None:
            print("error: --write necesita el archivo .game", file=sys.stderr)
            return 2
        write_weights(path, h, dict(zip(features, result.weights, strict=True)))
        _say(f"escrito en {path}")
    return 0


# --- solve ---------------------------------------------------------------------------------------


def solve(args: argparse.Namespace) -> int:
    from gamehub.analysis.cpp import solve_wdl

    if not _need_core():
        return 2
    game = _game(args)
    moves = json.loads(args.moves) if args.moves else []
    if isinstance(moves, dict):
        moves = [moves]
    r = solve_wdl(
        game,
        num_players=args.players,
        params=_params(args),
        table_bits=args.table_bits,
        threads=args.threads,
        max_seconds=args.max_seconds,
        heuristic=args.heuristic,
        moves=moves,
    )
    names = {1: "gana el asiento 0", 0: "tablas", -1: "gana el asiento 1"}
    print(
        f"{names[r['outcome']]} · {r['nodes']:,} nodos · {r['seconds']:.1f} s · "
        f"{r['nodes'] / max(r['seconds'], 1e-9):,.0f} nodos/s".replace(",", ".")
    )
    return 0


def bot_package_entry(spec: str) -> str:
    """Para `gamehub bot run`: un paquete de bot de Python se ejecuta con su archivo."""
    from gamehub.bots.package import BotPackageError, load_bot_package

    path = Path(spec)
    if not (path.is_dir() or path.name == "bot.toml"):
        return spec
    entrant = load_bot_package(path)
    if entrant.python is None:
        raise BotPackageError(
            f"{entrant.name} es un bot del núcleo ({(entrant.spec or {}).get('kind')}): juega en "
            "proceso; en una sala, ponlo como bot del servidor (/bot)"
        )
    return str(entrant.python)
