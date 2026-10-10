# SPDX-License-Identifier: Apache-2.0
"""Interfaces propias: tipos de TypeScript de cada juego (`gamehub sdk ts`) y la plantilla de UI
(`gamehub ui new`)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from gamehub.cli import main
from gamehub.lang.compiler import load_nomos
from gamehub.packages import load_manifest
from gamehub.render.typescript import game_types
from gamehub.uitemplate import in_workspace, new_ui

ROOT = Path(__file__).resolve().parents[2]
GAMES = sorted(p.parent for p in (ROOT / "games").glob("*/game.toml"))
UIS = sorted(p.parent.parent for p in (ROOT / "games").glob("*/ui/src/game.ts"))
BIOME = ROOT / "node_modules" / ".bin" / "biome"


def ir_of(package: Path) -> dict:
    return load_nomos(load_manifest(package).entry_path).ir


def test_types_of_a_game_with_hidden_information() -> None:
    text = game_types(ir_of(ROOT / "games" / "dudo"))
    assert 'export const GAME_ID = "dudo";' in text
    params = "export interface Params {\n  /** Dados de cada jugador al empezar */\n  dice: number;"
    assert params in text
    # Lo de cada asiento que solo ve su dueño puede llegar oculto; lo que ven todos, no.
    assert "  cup: (number[] | Hidden)[];" in text
    assert "  dice_left: number[];" in text
    assert "  die: number | Hidden;" in text
    assert 'export interface BidAction {\n  name: "bid";\n  args: { q: number; f: number };' in text
    assert "export type Action = BidAction | DudoAction;" in text
    assert 'export type NodeId = "Roll" | "Bid" | "End";' in text


def test_types_of_cards_zones_and_windows() -> None:
    text = game_types(ir_of(ROOT / "games" / "mentiroso"))
    assert "export interface Card {\n  suit: Suit;\n  rank: Rank;\n}" in text
    # Una zona nunca llega oculta entera: se ocultan sus elementos.
    assert "  hand: Zone<Card>[];" in text and "  pile: Zone<Card>;" in text
    assert "export type Action = PlayAction | PassAction | LiarAction;" in text
    grid = game_types(ir_of(ROOT / "games" / "connect-four"))
    assert "  board: (Disc | null)[][];" in grid


@pytest.mark.parametrize("package", GAMES, ids=lambda p: p.name)
def test_types_of_every_game(package: Path) -> None:
    ir = ir_of(package)
    text = game_types(ir)
    for var in ir["state"]:
        assert f"\n  {var['name']}: " in text, var["name"]
    assert text.endswith(";\n") and "\n\n\n" not in text


@pytest.mark.skipif(not BIOME.exists(), reason="hace falta pnpm install (Biome)")
def test_types_have_the_format_of_biome(tmp_path: Path) -> None:
    for package in GAMES:
        text = game_types(ir_of(package))
        out = subprocess.run(
            [str(BIOME), "format", f"--stdin-file-path={tmp_path / 'game.ts'}"],
            input=text,
            capture_output=True,
            text=True,
            cwd=ROOT,
            check=True,
        ).stdout
        assert out == text, package.name


@pytest.mark.parametrize("ui", UIS, ids=lambda p: p.parent.name)
def test_the_types_of_each_custom_ui_are_up_to_date(ui: Path) -> None:
    game = ui.parent
    output = ui / "src" / "game.ts"
    assert main(["sdk", "ts", str(game), "-o", str(output), "--check"]) == 0


def test_sdk_ts_command(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "game.ts"
    assert main(["sdk", "ts", str(ROOT / "games" / "nim"), "-o", str(out)]) == 0
    assert 'GAME_ID = "nim"' in out.read_text(encoding="utf-8")
    assert main(["sdk", "ts", str(ROOT / "games" / "nim"), "-o", str(out), "--check"]) == 0
    out.write_text("// viejo\n", encoding="utf-8")
    assert main(["sdk", "ts", str(ROOT / "games" / "nim"), "-o", str(out), "--check"]) == 1
    assert "no está al día" in capsys.readouterr().err


def test_ui_new_from_the_template(tmp_path: Path) -> None:
    package = tmp_path / "games" / "nim"
    shutil.copytree(ROOT / "games" / "nim", package)
    target = new_ui(package, ir_of(package))
    assert target == package / "ui"
    files = sorted(p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file())
    assert files == [
        "README.md",
        "index.html",
        "package.json",
        "src/Board.tsx",
        "src/game.ts",
        "src/index.tsx",
        "src/main.tsx",
        "src/styles.css",
        "test/Board.test.tsx",
        "tsconfig.json",
        "vite.config.ts",
        "vitest.config.ts",
    ]
    manifest = json.loads((target / "package.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "@gamehub-games/nim-ui"
    assert manifest["dependencies"]["@gamehub/shell"] == "workspace:*"
    every = "".join(p.read_text(encoding="utf-8") for p in target.rglob("*") if p.is_file())
    assert "__GAME_ID__" not in every and "__TITLE__" not in every and "__GAME_DIR__" not in every
    assert ".nim-board" in (target / "src" / "styles.css").read_text(encoding="utf-8")
    assert not in_workspace(target)  # sin pnpm-workspace.yaml en la raíz de tmp
    with pytest.raises(Exception, match="ya existe"):
        new_ui(package, ir_of(package))


def test_ui_new_command(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    package = tmp_path / "games" / "tictactoe"
    shutil.copytree(ROOT / "games" / "tictactoe", package, ignore=shutil.ignore_patterns("ui"))
    assert main(["ui", "new", str(package)]) == 0
    out = capsys.readouterr().out
    assert "UI propia de tictactoe creada" in out and "pnpm dev" in out
    assert (package / "ui" / "src" / "game.ts").is_file()
    assert main(["ui", "new", str(package)]) == 1


def test_the_catalog_uis_live_in_the_workspace() -> None:
    assert {ui.parent.name for ui in UIS} >= {"tictactoe", "connect-four", "dudo"}
    for ui in UIS:
        assert in_workspace(ui), ui
