# SPDX-License-Identifier: Apache-2.0
"""Línea de comandos `gamehub`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from gamehub import __version__
from gamehub.ir import check_file
from gamehub.ir.catalog import sync_schemas


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    from gamehub.engine.errors import InvalidParams, RuleError

    try:
        return args.handler(args)
    except KeyboardInterrupt:
        print("\nInterrumpido.", file=sys.stderr)
        return 130
    except (InvalidParams, RuleError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gamehub", description="Herramientas de GameHub.")
    parser.add_argument("--version", action="version", version=f"gamehub {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    ir = commands.add_parser("ir", help="operaciones sobre la GameIR")
    ir_commands = ir.add_subparsers(dest="ir_command", required=True)
    check = ir_commands.add_parser(
        "check", help="valida archivos .ir.json (esquema y buena formación)"
    )
    check.add_argument("files", nargs="+", type=Path, metavar="ARCHIVO")
    check.set_defaults(handler=_ir_check)
    schemas = ir_commands.add_parser("schemas", help="esquemas generados desde spec/ir/v0/ops.json")
    _check_or_write(schemas)
    schemas.set_defaults(handler=lambda a: sync_schemas(write=a.write))

    play = commands.add_parser("play", help="jugar en la terminal (hot-seat y bots)")
    play.add_argument("game", type=Path, metavar="JUEGO.ir.json")
    play.add_argument(
        "--seats", help="tipo de cada asiento: human, random o first (p. ej. human,random)"
    )
    play.add_argument(
        "--players", type=int, help="nº de jugadores (todos humanos si no se indica --seats)"
    )
    play.add_argument("--save-replay", type=Path, metavar="ARCHIVO.ghr.json")
    _match_options(play)
    play.set_defaults(handler=_play)

    fuzz = commands.add_parser("fuzz", help="partidas aleatorias en busca de errores de reglas")
    fuzz.add_argument("game", type=Path, metavar="JUEGO.ir.json")
    fuzz.add_argument("--games", type=int, default=1000)
    fuzz.add_argument("--players", type=int)
    fuzz.add_argument("--max-steps", type=int, default=10_000)
    fuzz.add_argument("--failures", type=Path, metavar="DIR", help="guarda un replay de cada fallo")
    _match_options(fuzz)
    fuzz.set_defaults(handler=_fuzz)

    replay = commands.add_parser("replay", help="re-simula y verifica un replay .ghr.json")
    replay.add_argument("file", type=Path, metavar="ARCHIVO.ghr.json")
    replay.add_argument(
        "--game", type=Path, metavar="JUEGO.ir.json", help="por defecto, el ejemplo con ese id"
    )
    replay.add_argument("--seat", type=int, help="mostrar la partida desde este asiento")
    replay.add_argument("--quiet", action="store_true", help="solo verificar")
    replay.set_defaults(handler=_replay)

    fmt = commands.add_parser("fmt", help="formatea archivos .game (formato canónico de Nomos)")
    fmt.add_argument(
        "files", nargs="+", type=Path, metavar="RUTA", help="archivos .game o directorios"
    )
    fmt.add_argument("--check", action="store_true", help="no escribe; falla si alguno cambiaría")
    fmt.add_argument("--diff", action="store_true", help="muestra las diferencias")
    fmt.set_defaults(handler=_fmt)

    conformance = commands.add_parser("conformance", help="trazas doradas de spec/conformance")
    _check_or_write(conformance)
    conformance.set_defaults(handler=_conformance)
    return parser


def _check_or_write(parser: argparse.ArgumentParser) -> None:
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="falla si están desactualizados")
    mode.add_argument("--write", action="store_true", help="los regenera")


def _match_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--param", action="append", default=[], metavar="NOMBRE=VALOR", help="parámetro del juego"
    )


def _params(raw: list[str]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for item in raw:
        name, sep, value = item.partition("=")
        if not sep:
            raise SystemExit(f"parámetro mal formado (usa NOMBRE=VALOR): {item}")
        try:
            params[name] = json.loads(value)
        except json.JSONDecodeError:
            params[name] = value
    return params


# --- ir ----------------------------------------------------------------------------------------


def _ir_check(args: argparse.Namespace) -> int:
    failed = 0
    for path in args.files:
        problems = check_file(path)
        if problems:
            failed += 1
            print(f"✗ {path} ({len(problems)} problema{'s' if len(problems) != 1 else ''})")
            for problem in problems:
                print(f"    {problem}")
        else:
            print(f"✓ {path}")
    return 1 if failed else 0


# --- motor -------------------------------------------------------------------------------------


def _play(args: argparse.Namespace) -> int:
    from gamehub.console.play import play_terminal
    from gamehub.engine import load_game

    game = load_game(args.game)
    if args.seats:
        seats = [s.strip() for s in args.seats.split(",")]
    else:
        seats = ["human"] * (args.players or game.players[0])
    state = play_terminal(
        game, seats, seed=args.seed, params=_params(args.param), save_replay=args.save_replay
    )
    return 0 if state.is_terminal else 1


def _fuzz(args: argparse.Namespace) -> int:
    from gamehub.engine import load_game
    from gamehub.engine.match import fuzz
    from gamehub.engine.replay import record, save

    game = load_game(args.game)
    if args.failures:
        args.failures.mkdir(parents=True, exist_ok=True)

    def on_error(seed: int, state: Any, exc: Exception) -> None:
        if args.failures is not None and state is not None:
            data = record(state, seed, game=game)
            data["error"] = str(exc)
            save(data, args.failures / f"fallo-semilla-{seed}.ghr.json")

    report = fuzz(
        game,
        args.games,
        seed=args.seed,
        num_players=args.players,
        params=_params(args.param),
        max_steps=args.max_steps,
        on_error=on_error,
    )
    rate = report.games / report.seconds if report.seconds else 0.0
    print(f"{game.title}: {report.games} partidas en {report.seconds:.1f} s ({rate:.0f}/s)")
    errors = len(report.errors)
    print(f"  completas: {report.completed} · truncadas: {report.truncated} · errores: {errors}")
    print(f"  pasos medios: {report.mean_steps:.1f}")
    if report.completed:
        print("  pago medio por asiento: " + ", ".join(f"{p:+.4f}" for p in report.mean_payoffs))
    for seed, message in report.errors[:10]:
        print(f"  ✗ semilla {seed}: {message}")
    return 1 if report.errors else 0


def _replay(args: argparse.Namespace) -> int:
    from gamehub.console.render import event_text
    from gamehub.engine import EngineError, load_game
    from gamehub.engine.replay import load, replay
    from gamehub.ir.spec import examples_dir

    data = load(args.file)
    game_path = args.game or examples_dir() / f"{data['game']['id']}.ir.json"
    game = load_game(game_path)
    try:
        final = replay(game, data)
    except EngineError as exc:
        print(f"✗ {args.file}: {exc}")
        return 1
    if not args.quiet:
        for i, state in enumerate(final.path()):
            lines = [event_text(e) for e in state.events(args.seat)]
            shown = [ln for ln in lines if ln]
            if shown:
                print(f"[{i}] " + " | ".join(shown))
    payoffs = ", ".join(str(p) for p in (final.payoffs or ()))
    print(f"✓ {args.file}: {len(data['steps'])} pasos verificados · pagos: {payoffs or '—'}")
    return 0


# --- lenguaje ----------------------------------------------------------------------------------


def _game_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(sorted(path.rglob("*.game")))
        else:
            files.append(path)
    return files


def _fmt(args: argparse.Namespace) -> int:
    import difflib

    from gamehub.lang.diagnostics import CompileError, print_diagnostics
    from gamehub.lang.printer import format_source
    from gamehub.lang.source import Source

    changed = failed = 0
    for path in _game_files(args.files):
        try:
            source = Source.from_path(path)
        except OSError as exc:
            print(f"✗ {path}: no se puede leer: {exc}", file=sys.stderr)
            failed += 1
            continue
        try:
            formatted = format_source(source)
        except CompileError as exc:
            print_diagnostics(exc.diagnostics.sorted())
            failed += 1
            continue
        if formatted == source.text:
            continue
        changed += 1
        if args.diff:
            sys.stdout.writelines(
                difflib.unified_diff(
                    source.text.splitlines(keepends=True),
                    formatted.splitlines(keepends=True),
                    f"{path} (original)",
                    f"{path} (formateado)",
                )
            )
        if args.check:
            print(f"✗ {path}: sin formatear")
        else:
            path.write_text(formatted, encoding="utf-8")
            print(f"formateado: {path}")
    if failed:
        return 1
    return 1 if args.check and changed else 0


def _conformance(args: argparse.Namespace) -> int:
    from gamehub.engine.conformance import sync, verify_all

    problems = sync(write=args.write) + verify_all()
    for problem in problems:
        print(f"✗ {problem}")
    if not problems:
        print("✓ trazas de conformidad al día y reproducibles")
    return 1 if problems else 0
