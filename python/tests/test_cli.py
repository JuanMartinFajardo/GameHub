# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from pathlib import Path

import pytest

from gamehub.cli import main
from gamehub.ir.spec import examples_dir


def test_check_valid_examples(capsys: pytest.CaptureFixture[str]) -> None:
    files = [str(p) for p in sorted(examples_dir().glob("*.ir.json"))]
    assert main(["ir", "check", *files]) == 0
    assert capsys.readouterr().out.count("✓") == len(files)


def test_check_reports_problems(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    broken = tmp_path / "broken.ir.json"
    broken.write_text('{"ir_version": "0.1.0"}', encoding="utf-8")
    assert main(["ir", "check", str(broken)]) == 1
    assert "'game' is a required property" in capsys.readouterr().out


def test_check_unreadable_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["ir", "check", str(tmp_path / "missing.ir.json")]) == 1
    assert "no se puede leer" in capsys.readouterr().out


def test_schemas_are_in_sync() -> None:
    assert main(["ir", "schemas", "--check"]) == 0
