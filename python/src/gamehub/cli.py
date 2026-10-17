# SPDX-License-Identifier: Apache-2.0
"""Línea de comandos `gamehub`."""

from __future__ import annotations

import argparse
import contextlib
import functools
import json
import os
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
    fuzz.add_argument(
        "--jobs", type=int, default=1, help="procesos en paralelo (0 = uno por núcleo)"
    )
    fuzz.add_argument(
        "--engine",
        choices=("python", "cpp"),
        default="python",
        help="motor: el de referencia o el núcleo C++ (las mismas partidas)",
    )
    _match_options(fuzz)
    fuzz.set_defaults(handler=_fuzz)

    differential = commands.add_parser(
        "differential",
        help="conformidad diferencial: el motor C++ contra el de referencia, paso a paso",
    )
    differential.add_argument("game", type=Path, metavar="JUEGO", help="archivo .game o .ir.json")
    differential.add_argument("--games", type=int, default=1000)
    differential.add_argument("--players", type=int)
    differential.add_argument("--max-steps", type=int, default=10_000)
    differential.add_argument(
        "--deep-every",
        type=int,
        default=10,
        metavar="K",
        help="una partida de cada K compara también vistas, eventos y acciones (0 = ninguna)",
    )
    differential.add_argument(
        "--jobs", type=int, default=1, help="procesos en paralelo (0 = uno por núcleo)"
    )
    _match_options(differential)
    differential.set_defaults(handler=_differential)

    bench = commands.add_parser(
        "bench", help="partidas aleatorias por segundo: motor de referencia contra núcleo C++"
    )
    bench.add_argument("game", type=Path, metavar="JUEGO", help="archivo .game o .ir.json")
    bench.add_argument("--games", type=int, default=200, help="partidas con el motor de Python")
    bench.add_argument(
        "--cpp-games", type=int, default=0, help="partidas con el C++ (0 = 100 veces más)"
    )
    bench.add_argument("--players", type=int)
    bench.add_argument("--max-steps", type=int, default=10_000)
    _match_options(bench)
    bench.set_defaults(handler=_bench)

    natives = commands.add_parser("natives", help="plugins nativos (WebAssembly) de la stdlib")
    natives_commands = natives.add_subparsers(dest="natives_command", required=True)
    natives_commands.add_parser("list", help="funciones nativas y su plugin").set_defaults(
        handler=_natives_list
    )
    natives_build = natives_commands.add_parser(
        "build", help="compila los .wat de stdlib/std/native a .wasm"
    )
    _check_or_write(natives_build)
    natives_build.set_defaults(handler=_natives_build)
    natives_check = natives_commands.add_parser(
        "check", help="compara cada plugin con su implementación de referencia"
    )
    natives_check.add_argument("--trials", type=int, default=2000)
    natives_check.add_argument("--seed", type=int, default=0)
    natives_check.set_defaults(handler=_natives_check)

    wasm = commands.add_parser(
        "wasm", help="el núcleo C++ en WebAssembly para el navegador (web/packages/engine)"
    )
    _check_or_write(wasm)
    wasm.add_argument("-v", "--verbose", action="store_true", help="enseña la compilación")
    wasm.set_defaults(handler=_wasm)

    perft = commands.add_parser(
        "perft", help="cuenta las secuencias de jugadas legales hasta una profundidad"
    )
    perft.add_argument("game", type=Path, metavar="JUEGO", help="archivo .game o .ir.json")
    perft.add_argument("--depth", type=int, default=3)
    perft.add_argument("--players", type=int)
    perft.add_argument(
        "--skip",
        action="append",
        default=[],
        metavar="ACCIÓN",
        help="acción que no cuenta como jugada (p. ej. claim_draw); se puede repetir",
    )
    perft.add_argument("--divide", action="store_true", help="el recuento por primera jugada")
    perft.add_argument(
        "--engine", choices=("python", "cpp"), default="python", help="motor (cpp = el núcleo C++)"
    )
    perft.add_argument(
        "--jobs", type=int, default=1, help="procesos en paralelo (0 = uno por núcleo)"
    )
    _match_options(perft)
    perft.set_defaults(handler=_perft)

    analyze = commands.add_parser(
        "analyze", help="teoría de juegos: viabilidad, soluciones, equilibrios, CFR, Grundy…"
    )
    analyze.add_argument(
        "game", type=Path, metavar="JUEGO", help="archivo .game, .ir.json o paquete"
    )
    analyze.add_argument("--players", type=int)
    for flag, text in (
        ("feasibility", "clasificación, tamaño (Knuth) y métodos recomendados"),
        ("count", "posiciones y partidas distintas (grafo de estados)"),
        ("solve", "solución exacta con información perfecta (alfa-beta / inducción hacia atrás)"),
        ("retrograde", "análisis retrógrado en C++ (deterministas de dos jugadores, con ciclos)"),
        ("tree", "forma extensiva: nodos y conjuntos de información"),
        ("normal-form", "forma normal con estrategias puras reducidas"),
        ("nash", "equilibrios de Nash (puros; mixtos y suma cero con dos jugadores)"),
        ("dominance", "eliminación iterada de estrategias dominadas"),
        ("correlated", "equilibrio correlado de máximo bienestar"),
        ("pareto", "óptimos de Pareto, bienestar social y precio de la anarquía"),
        ("sequence-form", "equilibrio exacto de dos jugadores de suma cero (forma de secuencias)"),
        ("grundy", "valor de Grundy y clase de resultado (juegos combinatorios)"),
        ("coop", "función característica, Shapley, núcleo, nucléolo y negociación de Nash"),
    ):
        analyze.add_argument(f"--{flag}", action="store_true", help=text)
    analyze.add_argument("--cfr", type=int, metavar="N", help="CFR+ con N iteraciones")
    analyze.add_argument("--vanilla", action="store_true", help="CFR clásico en vez de CFR+")
    analyze.add_argument(
        "--tournament",
        type=int,
        nargs="?",
        const=200,
        metavar="RONDAS",
        help="torneo de Axelrod sobre el juego de etapa (200 rondas por partida)",
    )
    analyze.add_argument("--noise", type=float, default=0.0, help="ruido del torneo (0–1)")
    analyze.add_argument(
        "--lp", choices=["auto", "exact", "highs"], default="auto", help="programación lineal"
    )
    analyze.add_argument("--max-nodes", type=int, default=1_000_000)
    analyze.add_argument(
        "--engine",
        choices=("auto", "cpp", "python"),
        default="auto",
        help="motor de la búsqueda exacta (auto = el núcleo C++ si está instalado)",
    )
    analyze.add_argument("--json", action="store_true", help="el informe en JSON")
    _match_options(analyze)
    analyze.set_defaults(handler=_analyze)

    export = commands.add_parser("export", help="exporta un juego a otros formatos (Gambit)")
    export.add_argument(
        "game", type=Path, metavar="JUEGO", help="archivo .game, .ir.json o paquete"
    )
    export.add_argument("--to", required=True, choices=["gambit-efg", "gambit-nfg"])
    export.add_argument("-o", "--output", type=Path, metavar="ARCHIVO")
    export.add_argument("--players", type=int)
    export.add_argument("--max-nodes", type=int, default=1_000_000)
    _match_options(export)
    export.set_defaults(handler=_export)

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

    sdk = commands.add_parser("sdk", help="SDK para interfaces propias")
    sdk_commands = sdk.add_subparsers(dest="sdk_command", required=True)
    sdk_ts = sdk_commands.add_parser(
        "ts", help="tipos de TypeScript de un juego: vista, acciones y opciones"
    )
    sdk_ts.add_argument("game", type=Path, metavar="JUEGO", help="paquete, .game o .ir.json")
    sdk_ts.add_argument("--name", help="juego si el archivo .game contiene varios")
    sdk_ts.add_argument("-o", "--output", type=Path, metavar="SALIDA.ts")
    sdk_ts.add_argument(
        "--check", action="store_true", help="falla si SALIDA.ts no está al día (para el CI)"
    )
    sdk_ts.set_defaults(handler=_sdk_ts)

    ui = commands.add_parser("ui", help="interfaces propias de los juegos")
    ui_commands = ui.add_subparsers(dest="ui_command", required=True)
    ui_new = ui_commands.add_parser(
        "new", help="crea una UI propia (React) para un juego, desde la plantilla"
    )
    ui_new.add_argument("game", type=Path, metavar="JUEGO", help="paquete del juego o su .game")
    ui_new.add_argument("--template", choices=["react"], default="react")
    ui_new.add_argument("--name", help="juego si el archivo .game contiene varios")
    ui_new.add_argument("--dir", type=Path, help="dónde crearla (por defecto, JUEGO/ui)")
    ui_new.set_defaults(handler=_ui_new)

    rules = commands.add_parser("rules", help="reglamento del juego en Markdown, generado")
    rules.add_argument("game", type=Path, metavar="JUEGO", help="archivo .game o .ir.json")
    rules.add_argument("--name", help="juego si el archivo .game contiene varios")
    rules.add_argument("--lang", default="es", help="idioma de los textos (por defecto, es)")
    rules.add_argument("-o", "--output", type=Path, metavar="SALIDA.md")
    rules.set_defaults(handler=_rules)

    lsp = commands.add_parser(
        "lsp", help="servidor de lenguaje de Nomos por la entrada estándar (para editores)"
    )
    lsp.set_defaults(handler=_lsp)

    studio = commands.add_parser(
        "studio", help="el Studio: editor visual de juegos (diagrama ↔ texto) y simulador"
    )
    studio.add_argument(
        "path",
        type=Path,
        nargs="?",
        default=Path("."),
        metavar="RUTA",
        help="directorio de trabajo o archivo .game que abrir (por defecto, el actual)",
    )
    studio.add_argument("--host", default="127.0.0.1", help="interfaz (por defecto, solo local)")
    studio.add_argument("--port", type=int, default=7421, help="puerto (por defecto, 7421)")
    studio.add_argument("--open", action="store_true", help="abre el navegador")
    studio.add_argument(
        "--no-token", action="store_true", help="sin token (solo para pruebas en tu máquina)"
    )
    studio.set_defaults(handler=_studio)

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
    new.add_argument(
        "--template",
        default="carrera",
        help="plantilla: vacio, carrera (por defecto), tablero, cartas, dados o matriz",
    )
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

    serve = commands.add_parser(
        "serve", help="servidor de partidas (salas por WebSocket) para la LAN o internet"
    )
    serve.add_argument(
        "games",
        nargs="*",
        type=Path,
        metavar="JUEGO",
        help="juegos que se pueden hospedar: .game, .ir.json o directorios (p. ej. games/)",
    )
    _server_options(serve)
    serve.add_argument("--allow-upload", action="store_true", help="admitir salas con IR subida")
    serve.set_defaults(handler=_serve)

    web = commands.add_parser("web", help="la app web para jugar")
    web_commands = web.add_subparsers(dest="web_command", required=True)
    web_export = web_commands.add_parser(
        "export",
        help="sitio estático sin servidor de partidas: se juega en el navegador (WebAssembly)",
    )
    web_export.add_argument("output", type=Path, metavar="DIR", help="directorio de salida")
    web_export.add_argument(
        "games",
        nargs="*",
        type=Path,
        metavar="JUEGO",
        help="juegos: .game, .ir.json o directorios (por defecto, el catálogo games/)",
    )
    web_export.add_argument("--server-name", default="GameHub", help="nombre visible")
    web_export.set_defaults(handler=_web_export)

    host = commands.add_parser(
        "host", help="abre una sala de un juego en la LAN y juega en ella desde la terminal"
    )
    host.add_argument("game", type=Path, metavar="JUEGO", help="archivo .game o .ir.json")
    host.add_argument("--name", help="juego a usar si el archivo .game contiene varios")
    host.add_argument("--player", help="tu nombre en la sala (por defecto, tu usuario)")
    host.add_argument("--players", type=int, help="nº de asientos (por defecto, el mínimo)")
    host.add_argument(
        "--param", action="append", default=[], metavar="NOMBRE=VALOR", help="opción del juego"
    )
    host.add_argument("--bots", type=int, default=0, help="bots del servidor en los últimos N")
    host.add_argument(
        "--clock", default="none", help="none, move:SEGUNDOS o match:SEGUNDOS+INCREMENTO"
    )
    host.add_argument(
        "--on-timeout", choices=["random", "pass", "bot", "forfeit"], default="random"
    )
    host.add_argument("--omniscient", action="store_true", help="los espectadores lo ven todo")
    host.add_argument("--delay", type=float, default=0, help="retardo de los espectadores (s)")
    host.add_argument("--private", action="store_true", help="no listar la sala")
    _server_options(host)
    host.add_argument("--no-play", action="store_true", help="solo servir la sala, sin jugar")
    host.add_argument("--no-mdns", action="store_true", help="no anunciarla en la LAN (mDNS)")
    host.add_argument("--no-qr", action="store_true", help="no mostrar el código QR")
    host.set_defaults(handler=_host)

    join = commands.add_parser("join", help="entra en una sala para jugar desde la terminal")
    join.add_argument("room", metavar="SALA", help="código (K7F-Q2P) o enlace de la sala")
    join.add_argument("--server", help="servidor (por defecto, se busca en este equipo y la LAN)")
    join.add_argument("--player", help="tu nombre en la sala (por defecto, tu usuario)")
    join.add_argument("--seat", type=int, help="asiento que quieres (1, 2…)")
    join.add_argument("--spectate", action="store_true", help="entrar como espectador")
    join.set_defaults(handler=_join)

    rooms = commands.add_parser("rooms", help="salas abiertas en los servidores de la LAN")
    rooms.add_argument("--server", help="mirar solo este servidor")
    rooms.add_argument("--timeout", type=float, default=2.0, help="segundos buscando (mDNS)")
    rooms.set_defaults(handler=_rooms)

    load = commands.add_parser("loadtest", help="prueba de carga del servidor de partidas")
    load.add_argument("game", type=Path, nargs="?", metavar="JUEGO", help=".game o .ir.json")
    load.add_argument("--server", help="servidor ya en marcha (por defecto, uno propio)")
    load.add_argument("--game-id", help="id del juego en ese servidor")
    load.add_argument("--rooms", type=int, default=100)
    load.add_argument("--players", type=int, default=2)
    load.add_argument("--matches", type=int, default=1, help="partidas seguidas por sala")
    load.add_argument("--seed", type=int, default=0)
    load.set_defaults(handler=_loadtest)

    bot = commands.add_parser("bot", help="bots que juegan en salas de un servidor de partidas")
    bot_commands = bot.add_subparsers(dest="bot_command", required=True)
    bot_run = bot_commands.add_parser("run", help="un bot entra en una sala y juega")
    bot_run.add_argument(
        "agent", metavar="AGENTE", help="random, first o un archivo .py con el agente"
    )
    bot_run.add_argument(
        "--room", required=True, metavar="SALA", help="código de sala (K7F-Q2P) o enlace"
    )
    bot_run.add_argument("--server", help="servidor si la sala va por código (por defecto, este)")
    bot_run.add_argument("--name", help="nombre visible del bot")
    bot_run.add_argument("--seat", type=int, help="asiento que ocupar (por defecto, el primero)")
    bot_run.add_argument(
        "--matches", type=int, default=1, help="partidas que jugar (0 = hasta que cierre la sala)"
    )
    bot_run.add_argument("--seed", type=int, help="semilla del agente (random)")
    bot_run.set_defaults(handler=_bot_run)

    protocol = commands.add_parser("protocol", help="protocolo de partidas (spec/protocol)")
    protocol_commands = protocol.add_subparsers(dest="protocol_command", required=True)
    types = protocol_commands.add_parser(
        "types", help="tipos de Python generados desde spec/protocol/v1/protocol.schema.json"
    )
    _check_or_write(types)
    types.set_defaults(handler=_protocol_types)
    return parser


def _server_options(parser: argparse.ArgumentParser) -> None:
    from gamehub.server import DEFAULT_PORT

    parser.add_argument("--host", default="0.0.0.0", help="interfaz (por defecto, todas)")
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT, help=f"(por defecto {DEFAULT_PORT})"
    )
    parser.add_argument(
        "--db",
        help="base de datos SQLite de las partidas (por defecto ~/.local/share/gamehub/"
        "server.sqlite3; ':memory:' para no guardar nada)",
    )
    parser.add_argument("--server-name", default="GameHub", help="nombre visible del servidor")
    parser.add_argument(
        "--no-web", action="store_true", help="no servir la app web (jugar en el navegador)"
    )
    parser.add_argument("--open", action="store_true", help="abrir el navegador al arrancar")


def _web_export(args: argparse.Namespace) -> int:
    from gamehub.engine.core_wasm import repo_root
    from gamehub.server.catalog import Catalog, CatalogError
    from gamehub.server.export import ExportError, export_site
    from gamehub.server.webapp import web_dir

    web = web_dir()
    if web is None:
        print("error: no está la app compilada (pnpm build en la raíz)", file=sys.stderr)
        return 1
    paths = args.games or [repo_root() / "games"]
    try:
        catalog = Catalog.load(paths)
        count = export_site(args.output, catalog, web=web, name=args.server_name)
    except (CatalogError, ExportError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"✓ {args.output}: la app y {count} juegos, para servir como archivos estáticos")
    return 0


def _store(db: str | None) -> Any:
    from gamehub.server import default_db
    from gamehub.server.store import MemoryStore, SqliteStore

    if db == ":memory:":
        return MemoryStore()
    return SqliteStore(Path(db) if db else default_db())


def _serve(args: argparse.Namespace) -> int:
    import asyncio

    from gamehub.server.catalog import Catalog, CatalogError
    from gamehub.server.lan import base_url
    from gamehub.server.rooms import Rooms
    from gamehub.server.serve import running, until_stopped
    from gamehub.server.webapp import web_dir

    try:
        catalog = Catalog.load(args.games)
    except CatalogError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    store = _store(args.db)
    rooms = Rooms(catalog, store, allow_upload=args.allow_upload, name=args.server_name)
    web = None if args.no_web else web_dir()

    async def main() -> None:
        async with running(rooms, args.host, args.port, web=web) as (_, server):
            url = base_url(args.host, server.port)
            print(f"Servidor de partidas en {url}", flush=True)
            if web is not None:
                print(f"  app web: {url} (abre el enlace en un navegador)")
                if args.open:
                    import webbrowser

                    webbrowser.open(url)
            elif not args.no_web:
                print("  sin app web: compílala con `pnpm build` en la raíz (ver web/README.md)")
            games = ", ".join(sorted(catalog.games)) or "ninguno"
            print(f"  juegos: {games}" + (" · admite subir juegos" if args.allow_upload else ""))
            where = getattr(store, "path", None)
            print(f"  partidas guardadas en {where}" if where else "  partidas solo en memoria")
            recovered = getattr(store, "recovered", 0)
            if recovered:
                print(f"  {recovered} partida(s) a medias de la última vez, cerradas como anuladas")
            print("  Ctrl+C para parar", flush=True)
            await until_stopped()
        print("Servidor parado.")

    try:
        asyncio.run(main())
    except OSError as exc:
        print(f"error: no se puede abrir el servidor en el puerto {args.port}: {exc}")
        return 1
    finally:
        store.close()
    return 0


def _say(text: str) -> None:
    """Imprime y vacía la salida: los comandos de red escriben a la vez que esperan, y con la
    salida redirigida (una tubería) el búfer retendría las líneas."""
    print(text, flush=True)


def _player_name(given: str | None) -> str:
    if given:
        return given
    import getpass

    with contextlib.suppress(Exception):
        return getpass.getuser().capitalize()[:32]
    return "Anónimo"


def _clock(text: str) -> dict[str, Any]:
    kind, _, rest = text.partition(":")
    try:
        if kind == "none" and not rest:
            return {"kind": "none"}
        if kind == "move":
            return {"kind": "move", "seconds": float(rest)}
        if kind == "match":
            initial, _, increment = rest.partition("+")
            return {"kind": "match", "initial": float(initial), "increment": float(increment or 0)}
    except ValueError:
        pass
    raise SystemExit(f"reloj no válido: {text} (none, move:30 o match:300+5)")


def _host(args: argparse.Namespace) -> int:
    import asyncio

    from gamehub.client import ClientError
    from gamehub.client.play import host
    from gamehub.client.terminal import stdin_lines
    from gamehub.server.webapp import web_dir

    game = _load_game(args.game, args.name)
    settings = {
        "clock": _clock(args.clock),
        "on_timeout": args.on_timeout,
        "spectator_view": "omniscient" if args.omniscient else "public",
        "spectator_delay": args.delay,
        "private": args.private,
    }
    store = _store(args.db)

    async def main() -> int:
        return await host(
            game,
            player=_player_name(args.player),
            lines=None if args.no_play else stdin_lines(),
            out=_say,
            store=store,
            listen=args.host,
            port=args.port,
            players=args.players,
            params=_params(args.param),
            settings=settings,
            bots=args.bots,
            mdns=not args.no_mdns,
            qr=not args.no_qr,
            web=None if args.no_web else web_dir(),
            open_browser=args.open,
        )

    try:
        return asyncio.run(main())
    except ClientError as exc:
        print(f"error: {exc.message}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: no se puede abrir el servidor en el puerto {args.port}: {exc}")
        return 1
    finally:
        store.close()


def _join(args: argparse.Namespace) -> int:
    import asyncio

    from gamehub.client import ClientError
    from gamehub.client.play import join
    from gamehub.client.terminal import stdin_lines

    async def main() -> int:
        return await join(
            args.room,
            server=args.server,
            player=_player_name(args.player),
            role="spectator" if args.spectate else "player",
            seat=None if args.seat is None else args.seat - 1,
            lines=stdin_lines(),
            out=_say,
        )

    try:
        return asyncio.run(main())
    except ClientError as exc:
        print(f"error: {exc.message}", file=sys.stderr)
        return 1


def _rooms(args: argparse.Namespace) -> int:
    import asyncio

    from gamehub.client.play import list_rooms

    return asyncio.run(list_rooms(server=args.server, timeout=args.timeout, out=_say))


def _loadtest(args: argparse.Namespace) -> int:
    import asyncio

    from gamehub.server.catalog import Catalog
    from gamehub.server.loadtest import run_load
    from gamehub.server.rooms import Limits, Rooms
    from gamehub.server.run import ServerThread
    from gamehub.server.store import MemoryStore

    def load(url: str, game_id: str) -> int:
        print(f"Prueba de carga: {args.rooms} salas de {game_id} con {args.players} bots cada una…")
        report = asyncio.run(
            run_load(
                url,
                game_id,
                rooms=args.rooms,
                players=args.players,
                matches=args.matches,
                seed=args.seed,
            )
        )
        print(report.summary())
        return 0 if not report.failures and report.matches == args.rooms * args.matches else 1

    if args.server:
        if not args.game_id:
            raise SystemExit("con --server hace falta --game-id")
        return load(args.server, args.game_id)
    if args.game is None:
        raise SystemExit("indica el juego (archivo .game o .ir.json) o --server y --game-id")
    game = _load_game(args.game, None)
    limits = Limits(max_rooms=max(1000, args.rooms), rate=1000, burst=1000)
    rooms = Rooms(Catalog([game]), MemoryStore(), limits=limits)
    with ServerThread(rooms) as server:
        return load(server.url, game.id)


def _bot_run(args: argparse.Namespace) -> int:
    import asyncio

    from gamehub.client import AgentLoadError, AgentRunner, Client, ClientError, load_agent
    from gamehub.client.play import resolve
    from gamehub.engine import Game

    try:
        factory = load_agent(args.agent, seed=args.seed)
    except AgentLoadError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    name = args.name or f"Bot {Path(args.agent).stem}"
    matches = args.matches or None

    async def main() -> list[dict[str, Any]]:
        server, code = await resolve(args.room, args.server, _say)
        async with Client(server, name=name, kind="bot", legal_limit=20_000) as client:
            joined = await client.join(code, seat=args.seat)
            seat = joined["session"]["seat"]
            _say(f"{name} en la sala {code} ({server}), asiento {seat}")
            game = Game(await client.room_ir())
            runner = AgentRunner(client, factory, game, matches=matches, log=_say)
            return await runner.run()

    try:
        results = asyncio.run(main())
    except ClientError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for result in results:
        payoffs = result["payoffs"]
        shown = ", ".join(str(p) for p in payoffs) if payoffs is not None else "—"
        _say(f"partida {result['match']['number']}: {result['reason']} · pagos: {shown}")
    return 0


def _protocol_types(args: argparse.Namespace) -> int:
    from gamehub.protocol.codegen import sync_types

    return sync_types(write=args.write)


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


def _jobs(value: int) -> int:
    return value if value > 0 else (os.cpu_count() or 1)


def _fuzz(args: argparse.Namespace) -> int:
    from gamehub.engine.match import fuzz, fuzz_parallel

    game = _load_game(args.game, args.name)
    if args.failures:
        args.failures.mkdir(parents=True, exist_ok=True)
    jobs = _jobs(args.jobs)
    if args.engine == "cpp":
        from gamehub.engine.core import core_fuzz

        report = core_fuzz(
            game,
            args.games,
            seed=args.seed,
            num_players=args.players,
            params=_params(args.param),
            max_steps=args.max_steps,
            jobs=jobs,
        )
        if args.failures:
            # El replay de cada fallo, con el motor de referencia (falla en el mismo paso).
            for seed, _ in report.errors:
                fuzz(
                    game,
                    1,
                    seed=seed,
                    num_players=args.players,
                    params=_params(args.param),
                    max_steps=args.max_steps,
                    on_error=_save_failure(game, args.failures),
                )
    elif jobs > 1:
        report = fuzz_parallel(
            functools.partial(_load_game, args.game.resolve(), args.name),
            args.games,
            jobs=jobs,
            seed=args.seed,
            num_players=args.players,
            params=_params(args.param),
            max_steps=args.max_steps,
            failures=args.failures,
        )
    else:
        report = fuzz(
            game,
            args.games,
            seed=args.seed,
            num_players=args.players,
            params=_params(args.param),
            max_steps=args.max_steps,
            on_error=_save_failure(game, args.failures),
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


def _differential(args: argparse.Namespace) -> int:
    from gamehub.engine.differential import diff, diff_parallel

    game = _load_game(args.game, args.name)
    jobs = _jobs(args.jobs)
    options: dict[str, Any] = {
        "num_players": args.players,
        "params": _params(args.param),
        "max_steps": args.max_steps,
        "deep_every": args.deep_every,
    }
    if jobs > 1:
        loader = functools.partial(_load_game, args.game.resolve(), args.name)
        report = diff_parallel(loader, args.games, jobs=jobs, seed=args.seed, **options)
    else:
        report = diff(game, args.games, seed=args.seed, **options)
    rate = report.games / report.seconds if report.seconds else 0.0
    print(
        f"{game.title}: {report.games} partidas ({report.deep_games} a fondo), "
        f"{report.steps} pasos comparados en {report.seconds:.1f} s ({rate:.0f}/s)"
    )
    print(
        f"  errores de reglas en los dos motores: {report.rule_errors} · "
        f"truncadas: {report.truncated} · diferencias: {len(report.differences)}"
    )
    for seed, step, what in report.differences[:10]:
        print(f"  ✗ semilla {seed}, paso {step}: {what}")
    if not report.differences:
        print("  ✓ los dos motores coinciden en todos los pasos")
    return 1 if report.differences else 0


def _bench(args: argparse.Namespace) -> int:
    from gamehub.engine.core import core_fuzz
    from gamehub.engine.match import fuzz

    game = _load_game(args.game, args.name)
    options: dict[str, Any] = {
        "seed": args.seed,
        "num_players": args.players,
        "params": _params(args.param),
        "max_steps": args.max_steps,
    }
    py = fuzz(game, args.games, **options)
    same = core_fuzz(game, args.games, **options)
    identical = (
        same.payoff_sums == py.payoff_sums
        and same.total_steps == py.total_steps
        and len(same.errors) == len(py.errors)
    )
    cpp_games = args.cpp_games or args.games * 100
    cpp = core_fuzz(game, cpp_games, **options)
    py_rate = py.games / py.seconds if py.seconds else 0.0
    cpp_rate = cpp.games / cpp.seconds if cpp.seconds else 0.0
    print(f"{game.title} (partidas aleatorias por segundo, un hilo)")
    steps = f"{py.mean_steps:.1f} pasos"
    print(f"  motor de referencia: {py_rate:12.1f} /s  ({py.games} partidas, {steps})")
    print(f"  núcleo C++:          {cpp_rate:12.1f} /s  ({cpp.games} partidas)")
    if py_rate:
        print(f"  aceleración: ×{cpp_rate / py_rate:.1f}")
    mark = "✓" if identical else "✗"
    print(f"  {mark} las {args.games} primeras partidas dan los mismos pasos y pagos en los dos")
    return 0 if identical else 1


def _save_failure(game: Any, failures: Path | None) -> Any:
    from gamehub.engine.match import save_failure

    if failures is None:
        return None
    return lambda seed, state, exc: save_failure(game, failures, seed, state, exc)


def _natives_list(args: argparse.Namespace) -> int:
    from gamehub.engine import natives

    if not natives.wasm_available():
        print(
            "aviso: wasmtime no está instalado (pip install 'gamehub[wasm]'): "
            "se usará la implementación de referencia"
        )
    for native_id, path in natives.stdlib_natives().items():
        plugin = natives.find_module(native_id)
        where = plugin.name if plugin is not None else "sin plugin (solo la referencia)"
        print(f"{native_id}  ({path.name})  →  {where}")
    return 0


def _natives_build(args: argparse.Namespace) -> int:
    from gamehub.engine import natives

    stale = natives.build(write=args.write)
    if args.write:
        print(f"escritos: {', '.join(stale)}" if stale else "los .wasm ya estaban al día")
        return 0
    if stale:
        print(f"✗ desactualizados: {', '.join(stale)} (gamehub natives build --write)")
        return 1
    print("✓ los .wasm están al día")
    return 0


def _natives_check(args: argparse.Namespace) -> int:
    from gamehub.engine import natives

    failed = 0
    for native_id in natives.stdlib_natives():
        problems = natives.compare_with_reference(native_id, args.trials, args.seed)
        if problems:
            failed += 1
            print(f"✗ {native_id}: {len(problems)} diferencias")
            for problem in problems:
                print(f"    {problem}")
        else:
            print(f"✓ {native_id}: {args.trials} entradas al azar, iguales que la referencia")
    return 1 if failed else 0


def _wasm(args: argparse.Namespace) -> int:
    from gamehub.engine import core_wasm

    if args.write:
        out = core_wasm.build(verbose=args.verbose)
        print(f"✓ núcleo compilado en {out}")
        return 0
    problems = core_wasm.check()
    for problem in problems:
        print(f"✗ {problem} (gamehub wasm --write)")
    if not problems:
        print("✓ el núcleo WebAssembly está al día")
    return 1 if problems else 0


def _perft(args: argparse.Namespace) -> int:
    import time

    from gamehub.analysis.perft import divide, perft, perft_parallel

    game = _load_game(args.game, args.name)
    params = _params(args.param)
    started = time.perf_counter()
    if args.engine == "cpp":
        from gamehub.analysis import cpp

        total = cpp.perft(game, args.depth, args.skip, num_players=args.players, params=params)
        seconds = time.perf_counter() - started
        print(f"perft({args.depth}) = {total}  ({seconds:.1f} s, núcleo C++)")
        return 0
    if args.divide:
        state = game.new_state(args.players, params)
        total = 0
        for action, count in divide(state, args.depth, args.skip):
            print(f"{action}: {count}")
            total += count
    elif _jobs(args.jobs) > 1:
        total = perft_parallel(
            functools.partial(_load_game, args.game.resolve(), args.name),
            args.depth,
            jobs=_jobs(args.jobs),
            skip=args.skip,
            num_players=args.players,
            params=params,
        )
    else:
        total = perft(game.new_state(args.players, params), args.depth, args.skip)
    seconds = time.perf_counter() - started
    print(f"perft({args.depth}) = {total}  ({seconds:.1f} s)")
    return 0


def _analyze(args: argparse.Namespace) -> int:
    from gamehub.analysis.report import ANALYSES, Options, analyze, report_lines

    game = _load_game(args.game, args.name)
    wanted = [name for name in ANALYSES if getattr(args, name, False) is True]
    if args.cfr:
        wanted.append("cfr")
    if args.tournament:
        wanted.append("tournament")
    options = Options(
        cfr_iterations=args.cfr or 1000,
        cfr_plus=not args.vanilla,
        tournament_rounds=args.tournament or 200,
        tournament_noise=args.noise,
        max_nodes=args.max_nodes,
        lp=args.lp,
        seed=args.seed,
        engine=args.engine,
    )
    report = analyze(
        game,
        wanted or ["auto"],
        num_players=args.players,
        params=_params(args.param),
        options=options,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("\n".join(report_lines(report)))
    return 1 if any(name in report["errors"] for name in wanted) else 0


def _export(args: argparse.Namespace) -> int:
    from gamehub.analysis.export import to_efg, to_nfg
    from gamehub.analysis.normal_form import normal_form
    from gamehub.analysis.tree import TreeError, build_tree

    game = _load_game(args.game, args.name)
    state = game.new_state(args.players, _params(args.param))
    try:
        tree = build_tree(state, max_nodes=args.max_nodes, infosets=True)
        tree.title = game.title
        text = to_efg(tree) if args.to == "gambit-efg" else to_nfg(normal_form(tree))
    except TreeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    _emit(text, args.output)
    return 0


def _replay(args: argparse.Namespace) -> int:
    from gamehub.console.render import event_text
    from gamehub.engine import EngineError
    from gamehub.engine.replay import load, replay
    from gamehub.ir.spec import examples_dir

    data = load(args.file)
    game_path = args.game or examples_dir() / f"{data['game']['id']}.ir.json"
    game = _load_game(game_path, None)
    fair = data.get("fairness")
    try:
        if isinstance(fair, dict) and "server_seed" in fair:
            from gamehub.engine.fairness import verify

            final = verify(game, data)
        else:
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
    if isinstance(fair, dict) and "server_seed" in fair:
        print("✓ azar verificado: la semilla revelada cumple el compromiso y produce cada sorteo")
    return 0


# --- lenguaje ----------------------------------------------------------------------------------


def _game_files(paths: list[Path]) -> list[Path]:
    from gamehub.packages import find_files

    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(find_files(path, ".game"))
        else:
            files.append(path)
    return files


def _load_game(path: Path, name: str | None) -> Any:
    """Un juego desde un archivo .game (compilándolo), un .ir.json o un paquete (su archivo
    principal, según `game.toml`)."""
    from gamehub.engine import load_game

    if path.is_dir():
        from gamehub.packages import MANIFEST, PackageError, load_manifest

        if not (path / MANIFEST).is_file():
            raise SystemExit(f"{path} no es un paquete de juego (falta {MANIFEST})")
        try:
            path = load_manifest(path).entry_path
        except PackageError as exc:
            raise SystemExit(str(exc)) from None
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


def _package_game(path: Path) -> Path:
    """El archivo del juego: el mismo, o el principal de un paquete (según su game.toml)."""
    if not path.is_dir():
        return path
    from gamehub.packages import MANIFEST, PackageError, load_manifest

    if not (path / MANIFEST).is_file():
        raise SystemExit(f"{path} no es un paquete de juego (falta {MANIFEST})")
    try:
        return load_manifest(path).entry_path
    except PackageError as exc:
        raise SystemExit(f"error: {exc}") from None


def _sdk_ts(args: argparse.Namespace) -> int:
    from gamehub.render.typescript import game_types

    ir = _game_ir(_package_game(args.game), args.name)
    if ir is None:
        return 1
    text = game_types(ir)
    if args.check:
        if args.output is None:
            print("error: --check necesita -o SALIDA.ts", file=sys.stderr)
            return 2
        current = args.output.read_text(encoding="utf-8") if args.output.exists() else None
        if current != text:
            print(
                f"{args.output} no está al día → gamehub sdk ts {args.game} -o {args.output}",
                file=sys.stderr,
            )
            return 1
        print(f"✓ {args.output}")
        return 0
    _emit(text, args.output)
    return 0


def _ui_new(args: argparse.Namespace) -> int:
    from gamehub.packages import PackageError
    from gamehub.uitemplate import in_workspace, new_ui

    entry = _package_game(args.game)
    ir = _game_ir(entry, args.name)
    if ir is None:
        return 1
    game_dir = args.game if args.game.is_dir() else entry.parent
    try:
        target = new_ui(game_dir, ir, args.dir)
    except PackageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"✓ UI propia de {ir['game']['id']} creada en {target}")
    if not in_workspace(target):
        print(
            "  aviso: fuera de <repo>/games/<juego>/ui el workspace de pnpm no la encuentra;"
            " añade su carpeta a pnpm-workspace.yaml"
        )
    print("  Siguientes pasos, desde la raíz del repositorio:")
    print("    pnpm install                                # la enlaza con los paquetes de GameHub")
    print("    cd python && uv run gamehub serve ../games  # servidor de partidas (otra terminal)")
    print(f"    cd {target} && pnpm dev   # http://localhost:5174")
    print("  y edita src/Board.tsx (los tipos del juego están en src/game.ts).")
    return 0


def _studio(args: argparse.Namespace) -> int:
    import asyncio
    import os
    from urllib.parse import quote

    from gamehub.packages import MANIFEST
    from gamehub.server.run import start, stop
    from gamehub.server.serve import until_stopped
    from gamehub.studio.server import LOCAL_HOSTS, WS_MAX_SIZE, create_app, new_token, studio_dir
    from gamehub.studio.workspace import Workspace

    target = args.path.resolve()
    if not target.exists():
        print(f"error: no existe {args.path}", file=sys.stderr)
        return 1
    open_file = None
    root = target
    if target.is_file():
        root = target.parent
        for parent in [target.parent, *target.parent.parents]:
            if (parent / MANIFEST).is_file():
                root = parent.parent if parent.parent != parent else parent
                break
        open_file = target.relative_to(root).as_posix()
    token = None if args.no_token else (os.environ.get("GAMEHUB_STUDIO_TOKEN") or new_token())
    local = args.host in LOCAL_HOSTS
    web = studio_dir()
    app = create_app(
        Workspace(root),
        token=token,
        web=web,
        hosts=LOCAL_HOSTS if local else None,
        open_file=open_file,
    )

    async def main() -> None:
        server, task = await start(app, args.host, args.port, ws_max_size=WS_MAX_SIZE)
        try:
            shown = "127.0.0.1" if args.host in ("127.0.0.1", "0.0.0.0", "::") else args.host
            query = [f"token={token}"] if token else []
            if open_file:
                query.append(f"file={quote(open_file)}")
            url = f"http://{shown}:{server.port}/" + (f"?{'&'.join(query)}" if query else "")
            print(f"GameHub Studio · {root}")
            print(f"  ábrelo en: {url}", flush=True)
            if web is None:
                print("  (falta la app web: compílala con `pnpm install && pnpm build` en la raíz)")
            if not local:
                print(
                    "  aviso: escucha fuera de esta máquina; cualquiera con el enlace puede editar"
                )
            print("  Ctrl+C para parar", flush=True)
            if args.open:
                import webbrowser

                webbrowser.open(url)
            await until_stopped()
        finally:
            await stop(server, task)
        print("Studio parado.")

    try:
        asyncio.run(main())
    except OSError as exc:
        print(
            f"error: no se puede abrir el Studio en el puerto {args.port}: {exc}", file=sys.stderr
        )
        return 1
    return 0


def _lsp(args: argparse.Namespace) -> int:
    from gamehub.lsp.server import run_stdio

    run_stdio()
    return 0


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
        manifest = new_package(root, args.name, authors=args.author, template=args.template)
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
