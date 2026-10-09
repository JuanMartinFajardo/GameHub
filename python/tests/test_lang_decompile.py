# SPDX-License-Identifier: Apache-2.0
"""Descompilador: IR → Nomos → IR da la misma IR, y el texto descompilado es estable."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from gamehub.cli import main
from gamehub.ir.spec import examples_dir, load_json
from gamehub.lang.compiler import compile_file, compile_text
from gamehub.lang.decompile import camel, decompile_text

FIXTURE = Path(__file__).parent / "fixtures" / "kitchen-sink.game"


def normalized(x: Any) -> Any:
    """Sin valores por defecto explícitos (listas vacías, visibilidad all)."""
    if isinstance(x, dict):
        return {
            k: normalized(v)
            for k, v in x.items()
            if v != [] and not (k in ("visibility", "size_visibility") and v == "all")
        }
    if isinstance(x, list):
        return [normalized(v) for v in x]
    return x


def roundtrip(ir: dict[str, Any]) -> None:
    text = decompile_text(ir)
    result = compile_text(text, "descompilado.game")
    assert result.ok, "\n".join(str(d) for d in result.diagnostics)
    again = result.game().ir
    assert normalized(again) == normalized(ir)
    assert decompile_text(again) == text


@pytest.mark.parametrize("path", sorted(examples_dir().glob("*.ir.json")), ids=lambda p: p.stem)
def test_examples_roundtrip(path: Path) -> None:
    roundtrip(load_json(path))


def test_kitchen_sink_roundtrip() -> None:
    roundtrip(compile_file(FIXTURE).game().ir)


def test_camel() -> None:
    assert camel("kuhn-poker") == "KuhnPoker"
    assert camel("tictactoe") == "Tictactoe"


def test_decompile_command(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "nim.game"
    assert main(["decompile", str(examples_dir() / "nim.ir.json"), "-o", str(out)]) == 0
    assert main(["check", str(out)]) == 0
    assert "game Nim" in out.read_text()
