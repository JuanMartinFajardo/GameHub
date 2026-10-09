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
    play.add_argument("game", type=Path, metavar="JUEGO", help="archivo .game o .ir.json")
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
    fuzz.add_argument("game", type=Path, metavar="JUEGO", help="archivo .game o .ir.json")
    fuzz.add_argument("--games", type=int, default=1000)
    fuzz.add_argument("--players", type=int)
    fuzz.add_argument("--max-steps", type=int, default=10_000)
    fuzz.add_argument("--failures", type=Path, metavar="DIR", help="guarda un replay de cada fallo")
    _match_options(fuzz)
    fuzz.set_defaults(handler=_fuzz)

    replay = commands.add_parser("replay", help="re-simula y verifica un replay .ghr.json")
    replay.add_argument("file", type=Path, metavar="ARCHIVO.ghr.json")
    replay.add_argument(
        "--game",
        type=Path,
        metavar="JUEGO",
        help="archivo .game o .ir.json (por defecto, el ejemplo con ese id)",
    )
    replay.add_argument("--seat", type=int, help="mostrar la partida desde este asiento")
    replay.add_argument("--quiet", action="store_true", help="solo verificar")
    replay.set_defaults(handler=_replay)

    compile_ = commands.add_parser("compile", help="compila un archivo .game a GameIR (JSON)")
    compile_.add_argument("file", type=Path, metavar="ARCHIVO.game")
    compile_.add_argument("--name", help="juego a compilar si el archivo contiene varios")
    compile_.add_argument("-o", "--output", type=Path, metavar="SALIDA.ir.json")
    compile_.set_defaults(handler=_compile)

    decompile = commands.add_parser("decompile", help="convierte una GameIR (JSON) en texto Nomos")
    decompile.add_argument("file", type=Path, metavar="ARCHIVO.ir.json")
    decompile.add_argument("--name", help="nombre del juego (por defecto, a partir de su id)")
    decompile.add_argument("-o", "--output", type=Path, metavar="SALIDA.game")
    decompile.set_defaults(handler=_decompile)

    check_game = commands.add_parser(
        "check", help="comprueba archivos .game (sintaxis, nombres, tipos, flow)"
    )
    check_game.add_argument(
        "files", nargs="+", type=Path, metavar="RUTA", help="archivos .game o directorios"
    )
    check_game.add_argument("--format", choices=("text", "json"), default="text")
    check_game.set_defaults(handler=_check)

    viz = commands.add_parser("viz", help="diagrama del flow de un juego (Mermaid o Graphviz)")
    viz.add_argument("game", type=Path, metavar="JUEGO", help="archivo .game o .ir.json")
    viz.add_argument("--name", help="juego a dibujar si el archivo .game contiene varios")
    viz.add_argument("--format", choices=("mermaid", "dot"), default="mermaid")
    viz.add_argument(
        "-o", "--output", type=Path, metavar="SALIDA", help="archivo (.md envuelve el Mermaid)"
    )
    viz.set_defaults(handler=_viz)

    diff = commands.add_parser(
        "diff", help="diferencias semánticas entre dos versiones de un juego"
    )
    diff.add_argument(
        "versions",
        nargs=2,
        metavar=("A", "B"),
        help="dos archivos (.game o .ir.json), o REV1..REV2 y un archivo del repositorio git",
    )
    diff.add_argument("--name", help="juego si los archivos .game contienen varios")
    diff.add_argument("--format", choices=("text", "json"), default="text")
    diff.set_defaults(handler=_diff)

    rules = commands.add_parser("rules", help="reglamento del juego en Markdown, generado")
    rules.add_argument("game", type=Path, metavar="JUEGO", help="archivo .game o .ir.json")
    rules.add_argument("--name", help="juego si el archivo .game contiene varios")
    rules.add_argument("--lang", default="es", help="idioma de los textos (por defecto, es)")
    rules.add_argument("-o", "--output", type=Path, metavar="SALIDA.md")
    rules.set_defaults(handler=_rules)

    test = commands.add_parser("test", help="ejecuta los tests y los invariantes de archivos .game")
    test.add_argument(
        "files", nargs="+", type=Path, metavar="RUTA", help="archivos .game o directorios"
    )
    test.add_argument(
        "--playouts",
        type=int,
        default=20,
        metavar="N",
        help="partidas aleatorias en las que comprobar los invariantes (por defecto, 20)",
    )
    test.add_argument("--seed", type=int, default=0, help="semilla de la primera partida aleatoria")
    test.add_argument(
        "-k", "--select", metavar="TEXTO", help="solo los tests cuyo nombre lo contiene"
    )
    test.add_argument("--format", choices=("text", "json"), default="text")
    test.set_defaults(handler=_test)

    fmt = commands.add_parser("fmt", help="formatea archivos .game (formato canónico de Nomos)")
    fmt.add_argument(
        "files", nargs="*", type=Path, metavar="RUTA", help="archivos .game o directorios"
    )
    fmt.add_argument(
        "--stdin",
        action="store_true",
        help="formatea la entrada estándar y escribe el resultado en la salida (editores)",
    )
    fmt.add_argument("--check", action="store_true", help="no escribe; falla si alguno cambiaría")
    fmt.add_argument(
        "--diff", action="store_true", help="muestra las diferencias sin escribir (como --check)"
    )
    fmt.set_defaults(handler=_fmt)

    new = commands.add_parser("new", help="crea un paquete de juego (game.toml y un .game mínimo)")
    new.add_argument("name", metavar="NOMBRE", help="nombre del paquete: minúsculas y guiones")
    new.add_argument("--dir", type=Path, help="directorio (por defecto, ./NOMBRE)")
    new.add_argument("--author", action="append", default=[], help="autor (se puede repetir)")
    new.set_defaults(handler=_new)

    fetch = commands.add_parser("fetch", help="descarga las dependencias git y escribe game.lock")
    fetch.add_argument("dir", nargs="?", type=Path, default=Path("."), metavar="DIR")
    fetch.add_argument("--update", action="store_true", help="vuelve a resolver las versiones")
    fetch.set_defaults(handler=_fetch)

    clone = commands.add_parser("clone", help="clona un juego (repositorio git) y sus dependencias")
    clone.add_argument("source", metavar="URL")
    clone.add_argument("dir", nargs="?", type=Path, metavar="DIR")
    clone.set_defaults(handler=_clone)

    fork = commands.add_parser("fork", help="copia un juego para modificarlo, anotando su origen")
    fork.add_argument("source", metavar="ORIGEN", help="URL git o directorio de un paquete")
    fork.add_argument("dir", nargs="?", type=Path, metavar="DIR")
    fork.set_defaults(handler=_fork)

    conformance = commands.add_parser("conformance", help="trazas doradas de spec/conformance")
    _check_or_write(conformance)
    conformance.set_defaults(handler=_conformance)
    return parser


def _check_or_write(parser: argparse.ArgumentParser) -> None:
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="falla si están desactualizados")
    mode.add_argument("--write", action="store_true", help="los regenera")


def _match_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--name", help="juego a usar si el archivo .game contiene varios")
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

    game = _load_game(args.game, args.name)
    if args.seats:
        seats = [s.strip() for s in args.seats.split(",")]
    else:
        seats = ["human"] * (args.players or game.players[0])
    state = play_terminal(
        game, seats, seed=args.seed, params=_params(args.param), save_replay=args.save_replay
    )
    return 0 if state.is_terminal else 1


def _fuzz(args: argparse.Namespace) -> int:
    from gamehub.engine.match import fuzz
    from gamehub.engine.replay import record, save

    game = _load_game(args.game, args.name)
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
    from gamehub.engine import EngineError
    from gamehub.engine.replay import load, replay
    from gamehub.ir.spec import examples_dir

    data = load(args.file)
    game_path = args.game or examples_dir() / f"{data['game']['id']}.ir.json"
    game = _load_game(game_path, None)
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


def _load_game(path: Path, name: str | None) -> Any:
    """Un juego desde un archivo .game (compilándolo) o .ir.json."""
    from gamehub.engine import load_game

    if path.suffix == ".game":
        from gamehub.lang.compiler import load_nomos

        return load_nomos(path, name)
    return load_game(path)


def _compile(args: argparse.Namespace) -> int:
    from gamehub.lang.compiler import compile_file
    from gamehub.lang.diagnostics import print_diagnostics

    result = compile_file(args.file)
    print_diagnostics(result.diagnostics.sorted())
    if not result.ok:
        return 1
    try:
        game = result.game(args.name)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    from gamehub.ir.jsonfmt import dumps

    text = dumps(game.ir)
    if args.output is None:
        sys.stdout.write(text)
    else:
        args.output.write_text(text, encoding="utf-8")
        print(f"✓ {args.output}", file=sys.stderr)
    return 0


def _decompile(args: argparse.Namespace) -> int:
    from gamehub.ir import check_file
    from gamehub.ir.spec import load_json
    from gamehub.lang.decompile import decompile_text

    problems = check_file(args.file)
    if problems:
        for problem in problems:
            print(f"✗ {problem}", file=sys.stderr)
        return 1
    text = decompile_text(load_json(args.file), args.name)
    if args.output is None:
        sys.stdout.write(text)
    else:
        args.output.write_text(text, encoding="utf-8")
        print(f"✓ {args.output}", file=sys.stderr)
    return 0


def _check(args: argparse.Namespace) -> int:
    from gamehub.analysis import classify
    from gamehub.ir.hashing import rules_hash
    from gamehub.lang.compiler import compile_file
    from gamehub.lang.diagnostics import print_diagnostics

    failed = 0
    report: list[dict[str, Any]] = []
    for path in _game_files(args.files):
        result = compile_file(path)
        diagnostics = result.diagnostics.sorted()
        if args.format == "json":
            report.extend(d.to_json() for d in diagnostics)
        else:
            print_diagnostics(diagnostics, sys.stdout)
        if not result.ok:
            failed += 1
            if args.format == "text":
                errors = len(result.diagnostics.errors)
                print(f"✗ {path}: {errors} error{'es' if errors != 1 else ''}")
            continue
        if args.format == "text":
            warnings = len(result.diagnostics.warnings)
            note = f" · {warnings} aviso{'s' if warnings != 1 else ''}" if warnings else ""
            for name, game in result.games.items():
                print(f"✓ {path}: {name} ({rules_hash(game.ir)[:19]}…){note}")
                print(f"    {' · '.join(classify(game.ir).labels())}")
            if not result.games:
                count = len(result.file.declarations)
                print(
                    f"✓ {path}: módulo con {count} declaraci{'ones' if count != 1 else 'ón'}{note}"
                )
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if failed else 0


def _viz(args: argparse.Namespace) -> int:
    from gamehub.render.viz import dot, mermaid

    ir = _game_ir(args.game, args.name)
    if ir is None:
        return 1
    text = mermaid(ir) if args.format == "mermaid" else dot(ir)
    if args.output is not None and args.output.suffix == ".md" and args.format == "mermaid":
        text = f"```mermaid\n{text}```\n"
    _emit(text, args.output)
    return 0


def _diff(args: argparse.Namespace) -> int:
    from gamehub.render.diff import diff, format_diff

    first, second = args.versions
    if ".." in first and not Path(first).exists():
        old_rev, new_rev = first.split("..", 1)
        path = Path(second)
        old = _game_ir_at(path, old_rev or "HEAD", args.name)
        new = _game_ir_at(path, new_rev, args.name) if new_rev else _game_ir(path, args.name)
    else:
        old, new = _game_ir(Path(first), args.name), _game_ir(Path(second), args.name)
    if old is None or new is None:
        return 1
    result = diff(old, new)
    if args.format == "json":
        report = {
            "same_rules": result.same_rules,
            "old_hash": result.old_hash,
            "new_hash": result.new_hash,
            "changes": [c.to_json() for c in result.changes],
        }
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        sys.stdout.write(format_diff(result))
    return 0


def _game_ir_at(path: Path, rev: str, name: str | None) -> dict[str, Any] | None:
    """La IR de un archivo tal como estaba en una revisión de git."""
    import subprocess

    done = subprocess.run(
        ["git", "-C", str(path.parent), "show", f"{rev}:./{path.name}"],
        capture_output=True,
        text=True,
    )
    if done.returncode != 0:
        print(f"error: git show {rev}:{path}: {done.stderr.strip()}", file=sys.stderr)
        return None
    if path.suffix != ".game":
        return json.loads(done.stdout)
    from gamehub.lang.compiler import compile_source
    from gamehub.lang.diagnostics import print_diagnostics
    from gamehub.lang.source import Source

    result = compile_source(Source(f"{path}@{rev}", done.stdout, path))
    if not result.ok:
        print_diagnostics(result.diagnostics.sorted())
        return None
    try:
        return result.game(name).ir
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return None


def _rules(args: argparse.Namespace) -> int:
    from gamehub.render.rules import rules

    ir = _game_ir(args.game, args.name)
    if ir is None:
        return 1
    _emit(rules(ir, args.lang), args.output)
    return 0


def _game_ir(path: Path, name: str | None) -> dict[str, Any] | None:
    """La IR de un juego: compilando un .game (con sus diagnósticos si falla) o leyendo un
    .ir.json válido."""
    if path.suffix == ".game":
        from gamehub.lang.compiler import compile_file
        from gamehub.lang.diagnostics import print_diagnostics

        result = compile_file(path)
        if not result.ok:
            print_diagnostics(result.diagnostics.sorted())
            return None
        try:
            return result.game(name).ir
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return None
    from gamehub.ir import check

    with path.open(encoding="utf-8") as f:
        ir = json.load(f)
    problems = check(ir)
    if problems:
        for problem in problems:
            print(f"✗ {problem}", file=sys.stderr)
        return None
    return ir


def _emit(text: str, output: Path | None) -> None:
    if output is None:
        sys.stdout.write(text)
    else:
        output.write_text(text, encoding="utf-8")
        print(f"escrito: {output}", file=sys.stderr)


def _test(args: argparse.Namespace) -> int:
    from gamehub.lang.compiler import compile_file
    from gamehub.lang.diagnostics import render, use_color
    from gamehub.lang.testing import GameTester, show_value

    color = args.format == "text" and use_color(sys.stdout)
    passed = failed = 0
    report: list[dict[str, Any]] = []

    def show(text: str = "") -> None:
        if args.format == "text":
            print(text)

    for path in _game_files(args.files):
        result = compile_file(path)
        if not result.ok:
            failed += 1
            errors = result.diagnostics.sorted()
            report.append({"file": str(path), "errors": [d.to_json() for d in errors]})
            for d in errors:
                show(render(d, color=color) + "\n")
            show(f"✗ {path}: no compila")
            continue
        for name, compiled in result.games.items():
            game_report = GameTester(compiled).run_all(args.playouts, args.seed, args.select)
            entry: dict[str, Any] = {"file": str(path), "game": name, "tests": []}
            report.append(entry)
            show(f"{path} · {name}")
            for t in game_report.tests:
                entry["tests"].append(
                    {"name": t.name, "ok": t.ok}
                    | ({"failure": t.failure.to_json()} if t.failure else {})
                )
                passed += t.ok
                failed += not t.ok
                show(f"  {'✓' if t.ok else '✗'} {t.name}")
                if t.failure is not None:
                    show(_indent(render(t.failure, color=color), 4) + "\n")
            playouts = game_report.playouts
            count = game_report.invariants
            if args.playouts:
                entry["playouts"] = {
                    "invariants": count,
                    "playouts": playouts.playouts,
                    "states": playouts.states,
                    "ok": playouts.failure is None,
                    "payoff_sums": sorted(str(x) for x in playouts.payoff_sums),
                } | ({"failure": playouts.failure.to_json()} if playouts.failure else {})
                what = (
                    f"{count} invariante{'s' if count != 1 else ''} en"
                    if count
                    else "sin errores en"
                )
                if playouts.failure is None:
                    passed += 1
                    show(
                        f"  ✓ {what} {playouts.playouts} partidas aleatorias "
                        f"({playouts.states} estados)"
                    )
                    if len(playouts.payoff_sums) == 1:
                        total = show_value(next(iter(playouts.payoff_sums)))
                        show(f"    los pagos suman siempre {total}")
                else:
                    failed += 1
                    show(f"  ✗ partidas aleatorias{' (invariantes)' if count else ''}")
                    show(_indent(render(playouts.failure, color=color), 4) + "\n")
            if not game_report.tests and not game_report.invariants and not args.playouts:
                show("  (sin tests ni invariantes)")
    if args.format == "json":
        summary = {"passed": passed, "failed": failed, "results": report}
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        total = passed + failed
        print(
            f"\n{total} {_plural(total, 'comprobación', 'comprobaciones')}: "
            f"{passed} {_plural(passed, 'correcta', 'correctas')}, "
            f"{failed} {_plural(failed, 'fallida', 'fallidas')}"
        )
    return 1 if failed else 0


def _plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


def _indent(text: str, n: int) -> str:
    return "\n".join(" " * n + line if line else line for line in text.splitlines())


def _fmt(args: argparse.Namespace) -> int:
    import difflib

    from gamehub.lang.diagnostics import CompileError, print_diagnostics
    from gamehub.lang.printer import format_source
    from gamehub.lang.source import Source

    if args.stdin:
        try:
            sys.stdout.write(format_source(Source("<entrada>", sys.stdin.read())))
        except CompileError as exc:
            print_diagnostics(exc.diagnostics.sorted())
            return 1
        return 0
    if not args.files:
        print("error: indica archivos .game o directorios (o --stdin)", file=sys.stderr)
        return 2
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
        elif not args.diff:
            path.write_text(formatted, encoding="utf-8")
            print(f"formateado: {path}")
    if failed:
        return 1
    return 1 if (args.check or args.diff) and changed else 0


# --- paquetes ------------------------------------------------------------------------------------


def _new(args: argparse.Namespace) -> int:
    from gamehub.packages import PackageError, new_package

    root = args.dir or Path(args.name)
    try:
        manifest = new_package(root, args.name, authors=args.author)
    except PackageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"✓ creado {root}/ con {manifest.entry_path.name} y game.toml")
    print(f"  pruébalo: gamehub test {root}  ·  juégalo: gamehub play {manifest.entry_path}")
    return 0


def _fetch(args: argparse.Namespace) -> int:
    from gamehub.packages import PackageError, fetch, load_manifest

    try:
        locked = fetch(load_manifest(args.dir), update=args.update)
    except PackageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for entry in sorted(locked.values(), key=lambda e: e.name):
        print(f"✓ {entry.name} {entry.rev or 'HEAD'} → {entry.commit[:12]}")
    print(f"game.lock: {len(locked)} dependencia{'s' if len(locked) != 1 else ''} git")
    return 0


def _clone(args: argparse.Namespace) -> int:
    from gamehub.packages import PackageError, clone

    root = args.dir or Path(_repo_name(args.source))
    try:
        manifest = clone(args.source, root)
    except PackageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    what = f"el paquete {manifest.name}" if manifest else "el repositorio (sin game.toml)"
    print(f"✓ clonado {what} en {root}/")
    return 0


def _fork(args: argparse.Namespace) -> int:
    from gamehub.packages import PackageError, fork

    root = args.dir or Path(_repo_name(args.source) + "-fork")
    try:
        manifest = fork(args.source, root)
    except PackageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"✓ {manifest.name} copiado en {root}/ (forked_from = {manifest.forked_from})")
    return 0


def _repo_name(source: str) -> str:
    name = source.rstrip("/").rsplit("/", 1)[-1].rsplit(":", 1)[-1]
    return name.removesuffix(".git") or "juego"


def _conformance(args: argparse.Namespace) -> int:
    from gamehub.engine.conformance import sync, verify_all

    problems = sync(write=args.write) + verify_all()
    for problem in problems:
        print(f"✗ {problem}")
    if not problems:
        print("✓ trazas de conformidad al día y reproducibles")
    return 1 if problems else 0
