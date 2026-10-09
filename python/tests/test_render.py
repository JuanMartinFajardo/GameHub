# SPDX-License-Identifier: Apache-2.0
"""Presentaciones de un juego: diagrama del flow (`viz`), reglamento (`rules`) y diff semántico
(`diff`)."""

from __future__ import annotations

import copy
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

from gamehub.analysis import irwalk
from gamehub.cli import main
from gamehub.lang.compiler import compile_file
from gamehub.render.diff import diff, format_diff
from gamehub.render.rules import rules
from gamehub.render.viz import dot, flow_graph, mermaid

ROOT = Path(__file__).resolve().parents[2]
SOURCES = [
    *sorted((ROOT / "games").glob("*/*.game")),
    Path(__file__).resolve().parent / "fixtures" / "kitchen-sink.game",
]


def ir_of(path: Path) -> dict[str, Any]:
    return compile_file(path).game().ir


def transitions(ir: dict[str, Any]) -> int:
    count = 1  # el inicio del flow
    for node, _ in irwalk.all_nodes(ir):
        count += len(node.get("transitions", []))
        count += sum(len(a.get("transitions", [])) for a in node.get("actions", []))
        count += node["kind"] == "phase"  # el inicio de la fase
    return count


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.stem)
def test_the_diagram_matches_the_flow(path: Path) -> None:
    ir = ir_of(path)
    nodes = [node["id"] for node, _ in irwalk.all_nodes(ir)]
    flow = flow_graph(ir)
    assert sorted(b.id for b in flow.boxes) == sorted(nodes)
    assert len(flow.edges) == transitions(ir)
    text = mermaid(ir)
    assert text.splitlines()[3] == "flowchart TD"
    arrows = [line for line in text.splitlines() if "-->" in line]
    assert len(arrows) == len(flow.edges)
    for node in nodes:
        assert re.search(rf"^\s*(subgraph )?{node}\b", text, re.M), node
    graph = dot(ir)
    assert graph.startswith("digraph flow {") and graph.rstrip().endswith("}")
    assert graph.count(" -> ") == len(flow.edges)


def test_phases_have_entry_and_exit_marks() -> None:
    ir = ir_of(SOURCES[-1])
    text = mermaid(ir)
    assert 'subgraph Round["fase Round"]' in text
    assert "Round__start --> Bid" in text
    assert "Play --> Round__exit" in text
    assert 'Round__exit -- "si round #gt;= rounds" --> End' in text
    assert "Weather -> Round__start [lhead=cluster_Round];" in dot(ir)


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.stem)
def test_rulebook_covers_every_node(path: Path) -> None:
    ir = ir_of(path)
    text = rules(ir)
    title = ir.get("meta", {}).get("title", ir["game"]["id"])
    title = title["es"] if isinstance(title, dict) else title
    assert text.startswith(f"# {title}\n")
    for node, _ in irwalk.all_nodes(ir):
        assert f"### {node['id']} (" in text
    assert "```mermaid" in text
    if ir.get("params"):
        assert "## Opciones de la partida" in text


def test_rulebook_details() -> None:
    text = rules(ir_of(ROOT / "games" / "kuhn-poker" / "kuhn-poker.game"))
    assert "| `hand` | `per_player Bag<Card>` | `[]` | su dueño (cuántos: todos) |" in text
    assert "- **bet**. Solo si `opening()`" in text
    assert "- → **Showdown** si `moves == [Check, Check] or last(moves) == Call`" in text
    english = rules(ir_of(ROOT / "games" / "kuhn-poker" / "kuhn-poker.game"), lang="en")
    assert english.startswith("# Kuhn poker\n")


def test_diff_finds_semantic_changes() -> None:
    old = ir_of(ROOT / "games" / "tictactoe" / "tictactoe.game")
    assert diff(old, copy.deepcopy(old)).changes == []
    new = copy.deepcopy(old)
    new["meta"]["title"]["es"] = "Tres en raya (v2)"
    cosmetic = diff(old, new)
    assert cosmetic.same_rules and [c.path for c in cosmetic.changes] == ["meta.title"]
    new["state"].append({"name": "moves", "type": "Int", "init": ["const", 0]})
    win = next(n for n in new["flow"]["nodes"] if n["id"] == "Win")
    win["payoff"] = ["win_loss", ["var", "turn"], ["const", 2], ["const", -2]]
    move = next(n for n in new["flow"]["nodes"] if n["id"] == "Move")
    move["transitions"].insert(0, {"to": "Draw", "when": ["ge", ["var", "moves"], ["const", 9]]})
    result = diff(old, new)
    assert not result.same_rules
    changes = [(c.op, c.path) for c in result.changes]
    assert changes == [
        ("~", "meta.title"),
        ("+", "estado moves"),
        ("+", "nodo Move.transición"),
        ("~", "nodo Win.payoff"),
    ]
    text = format_diff(result)
    assert "~ nodo Win.payoff: win_loss(turn, 1, -1) → win_loss(turn, 2, -2)" in text
    assert "+ nodo Move.transición: -> Draw when moves >= 9" in text


def test_render_commands(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    game = ROOT / "games" / "nim" / "nim.game"
    assert main(["viz", str(game)]) == 0
    assert "flowchart TD" in capsys.readouterr().out
    assert main(["viz", str(game), "--format", "dot", "-o", str(tmp_path / "nim.dot")]) == 0
    assert (tmp_path / "nim.dot").read_text().startswith("digraph")
    assert main(["viz", str(game), "-o", str(tmp_path / "nim.md")]) == 0
    assert (tmp_path / "nim.md").read_text().startswith("```mermaid\n")
    assert main(["rules", str(game), "-o", str(tmp_path / "nim.md")]) == 0
    assert (tmp_path / "nim.md").read_text().startswith("# Nim")

    # diff entre dos revisiones de git
    repo = tmp_path / "repo"
    repo.mkdir()
    copied = repo / "nim.game"
    copied.write_text(game.read_text(encoding="utf-8"), encoding="utf-8")

    def git(*args: str) -> None:
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
            cwd=repo,
            check=True,
            capture_output=True,
        )

    git("init", "--quiet")
    git("add", ".")
    git("commit", "--quiet", "-m", "uno")
    copied.write_text(
        copied.read_text(encoding="utf-8").replace("misere: Bool = false", "misere: Bool = true"),
        encoding="utf-8",
    )
    capsys.readouterr()
    assert main(["diff", "HEAD..", str(copied), "--format", "json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert not report["same_rules"]
    assert report["changes"] == [
        {
            "op": "~",
            "path": "opción misere",
            "old": "misere: Bool = false",
            "new": "misere: Bool = true",
        }
    ]
