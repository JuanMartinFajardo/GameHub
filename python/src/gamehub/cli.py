# SPDX-License-Identifier: Apache-2.0
"""Línea de comandos `gamehub`."""

from __future__ import annotations

import argparse
from pathlib import Path

from gamehub import __version__
from gamehub.ir import check_file
from gamehub.ir.catalog import sync_schemas


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gamehub", description="Herramientas de GameHub.")
    parser.add_argument("--version", action="version", version=f"gamehub {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    ir = commands.add_parser("ir", help="operaciones sobre la GameIR")
    ir_commands = ir.add_subparsers(dest="ir_command", required=True)
    check = ir_commands.add_parser(
        "check", help="valida archivos .ir.json (esquema y buena formación)"
    )
    check.add_argument("files", nargs="+", type=Path, metavar="ARCHIVO")
    schemas = ir_commands.add_parser("schemas", help="esquemas generados desde spec/ir/v0/ops.json")
    mode = schemas.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="falla si están desactualizados")
    mode.add_argument("--write", action="store_true", help="los regenera")

    args = parser.parse_args(argv)
    match (args.command, args.ir_command):
        case ("ir", "check"):
            return _ir_check(args.files)
        case ("ir", "schemas"):
            return sync_schemas(write=args.write)
    parser.error("comando desconocido")


def _ir_check(files: list[Path]) -> int:
    failed = 0
    for path in files:
        problems = check_file(path)
        if problems:
            failed += 1
            print(f"✗ {path} ({len(problems)} problema{'s' if len(problems) != 1 else ''})")
            for problem in problems:
                print(f"    {problem}")
        else:
            print(f"✓ {path}")
    return 1 if failed else 0
