# SPDX-License-Identifier: Apache-2.0
"""Extensión de VS Code (editors/vscode/nomos): la gramática sigue al lenguaje y la extensión
entiende la salida de `gamehub check --format json`."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from gamehub.cli import main
from gamehub.lang.builtins import AGGREGATES, BUILTINS
from gamehub.lang.checker import RANDOM_CALLS
from gamehub.lang.lexer import KEYWORDS

EXTENSION = Path(__file__).resolve().parents[2] / "editors" / "vscode" / "nomos"


def load(name: str) -> Any:
    return json.loads((EXTENSION / name).read_text(encoding="utf-8"))


def patterns(node: Any) -> list[str]:
    """Todas las expresiones regulares de la gramática."""
    found: list[str] = []
    if isinstance(node, dict):
        for key in ("match", "begin", "end"):
            if key in node:
                found.append(node[key])
        for value in node.values():
            found += patterns(value)
    elif isinstance(node, list):
        for value in node:
            found += patterns(value)
    return found


def test_manifest_points_to_existing_files() -> None:
    manifest = load("package.json")
    [language] = manifest["contributes"]["languages"]
    assert language["id"] == "nomos" and language["extensions"] == [".game"]
    load(language["configuration"])
    [grammar] = manifest["contributes"]["grammars"]
    assert load(grammar["path"])["scopeName"] == grammar["scopeName"] == "source.nomos"
    assert (EXTENSION / manifest["main"]).is_file()


def test_grammar_regexes_compile_and_cover_the_language() -> None:
    grammar = load("syntaxes/nomos.tmLanguage.json")
    regexes = patterns(grammar)
    for regex in regexes:
        re.compile(regex)  # Oniguruma admite más, pero aquí solo se usa lo común
    words = set(re.findall(r"[a-z_]+", " ".join(regexes)))
    assert words >= KEYWORDS, sorted(KEYWORDS - words)
    builtins = grammar["repository"]["builtins"]["match"]
    names = set(BUILTINS) | set(AGGREGATES) | set(RANDOM_CALLS) | {"at"}
    missing = {n for n in names if not re.search(rf"\b{n}\b", builtins)}
    assert not missing, sorted(missing)


def test_grammar_recognises_declarations() -> None:
    grammar = load("syntaxes/nomos.tmLanguage.json")
    declarations = grammar["repository"]["declarations"]["patterns"]
    node = re.compile(declarations[2]["match"])
    match = node.search("    decision Play {")
    assert match is not None and match.group(2) == "Play"
    transition = re.compile(declarations[3]["match"])
    match = transition.search("-> End when x > 2")
    assert match is not None and match.group(2) == "End"


@pytest.mark.skipif(shutil.which("node") is None, reason="hace falta node")
def test_extension_script_is_valid_javascript() -> None:
    subprocess.run(["node", "--check", str(EXTENSION / "extension.js")], check=True)


def test_check_json_has_what_the_extension_reads(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "bad.game"
    bad.write_text(
        "game G {\n  players 2\n  state {\n    x: Int = true\n  }\n}\n", encoding="utf-8"
    )
    assert main(["check", "--format", "json", str(bad)]) == 1
    items = json.loads(capsys.readouterr().out)
    assert items, "debería haber diagnósticos"
    for item in items:
        assert {"severity", "code", "message", "file", "line", "column"} <= set(item)
        assert {"end_line", "end_column"} <= set(item)
        assert item["severity"] in ("error", "warning")
    assert any(item["code"] == "E301" and item["line"] == 4 for item in items)
