# SPDX-License-Identifier: Apache-2.0
"""Aceptación de la Fase 5 (Studio), contra el servidor del Studio de verdad (WebSocket, versiones
del documento y `gamehub/edit`, como hace la app web):

1. Crear el tres en raya desde cero solo con el diagrama y los formularios (las operaciones que
   mandan la paleta, las flechas y el inspector, una a una) y jugarlo en el simulador. Además se
   comprueba que es el mismo juego que el del catálogo.
2. Cambiar el flujo de Dudo en el diagrama y ver el texto actualizado sin perder comentarios, y al
   revés: cambiar el texto y ver el diagrama (el modelo del documento) actualizado.
"""

from __future__ import annotations

import random
import re
import shutil
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from gamehub.engine import Game
from gamehub.lang.compiler import compile_source, load_nomos
from gamehub.lang.source import Source
from gamehub.lang.testing import show_action
from gamehub.studio.server import StudioThread
from studio_harness import TOKEN, Session, call, open_session

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    shutil.copytree(ROOT / "games" / "dudo", tmp_path / "dudo", ignore=shutil.ignore_patterns("ui"))
    return tmp_path


@pytest.fixture
def session(workspace: Path) -> Iterator[tuple[StudioThread, Session]]:
    with StudioThread(workspace, token=TOKEN) as studio, open_session(studio, workspace) as s:
        yield studio, s


class Document:
    """Un documento abierto en el Studio, editado como lo edita la app (operación a operación)."""

    def __init__(self, s: Session, path: Path) -> None:
        self.s = s
        self.uri = s.open(path)
        self.text = path.read_text(encoding="utf-8")
        self.version = 1
        self.analysis = s.wait("gamehub/analysis")

    def apply(self, *ops: dict[str, Any]) -> str:
        for op in ops:
            self.text = self.s.edit(self.uri, self.version, self.text, [op])
            self.version += 1
        return self.refresh()

    def type(self, new: str) -> str:
        """Lo que pasa al escribir en el editor de texto."""
        self.version += 1
        self.text = new
        change = {
            "textDocument": {"uri": self.uri, "version": self.version},
            "contentChanges": [{"text": new}],
        }
        self.s.notify("textDocument/didChange", change)
        return self.refresh()

    def refresh(self) -> str:
        self.analysis = self.s.wait("gamehub/analysis", lambda p: p["version"] == self.version)
        return self.text

    @property
    def game(self) -> dict[str, Any]:
        return self.analysis["model"]["game"]

    def node(self, name: str) -> dict[str, Any]:
        return next(n for n in self.game["flow"]["nodes"] if n["id"] == name)

    def errors(self) -> list[str]:
        return [p["message"] for p in self.analysis["problems"] if p["severity"] == "error"]


# --- 1. El tres en raya desde cero, solo con el diagrama -----------------------------------------

#: Lo que se hace en el Studio, en orden: cada operación es un gesto en el diagrama o un campo del
#: inspector (los nombres de los nodos se cambian en el inspector, como los de la paleta).
TICTACTOE_OPS: list[dict[str, Any]] = [
    # Inspector del juego: título, un enumerado, el tablero y tres funciones.
    {"op": "setMeta", "key": "title", "value": {"es": "Tres en raya", "en": "Tic-tac-toe"}},
    {"op": "addEnum", "name": "Mark", "values": ["X", "O"]},
    {"op": "addState", "name": "board", "type": "Grid[3, 3] of Mark?", "init": "none"},
    {
        "op": "addFn",
        "name": "mark",
        "params": [{"name": "p", "type": "Seat"}],
        "returns": "Mark",
        "body": "X if p == 0 else O",
    },
    {
        "op": "addFn",
        "name": "wins",
        "params": [{"name": "m", "type": "Mark"}],
        "returns": "Bool",
        "body": "any(line in lines(board, 3) : all(c in line : board[c] == m))",
    },
    {
        "op": "addFn",
        "name": "full",
        "params": [],
        "returns": "Bool",
        "body": "all(c in cells(board) : not is_none(board[c]))",
    },
    # El turno de la plantilla pasa a ser la jugada, con su acción.
    {"op": "rename", "key": "node:Turn", "name": "Move"},
    {"op": "rename", "key": "node:End", "name": "Draw"},
    {"op": "rename", "key": "action:finish", "name": "place"},
    {
        "op": "updateAction",
        "node": "Move",
        "action": "place",
        "params": [{"name": "c", "type": None, "domain": "cells(board)", "visibility": None}],
    },
    {"op": "updateAction", "node": "Move", "action": "place", "requires": "is_none(board[c])"},
    {"op": "updateAction", "node": "Move", "action": "place", "effects": "board[c] = mark(turn)"},
    # Paleta: un final nuevo; flechas: de la jugada a la victoria (arriba del todo), a las tablas
    # y de vuelta a la jugada.
    {"op": "addNode", "kind": "terminal"},
    {"op": "rename", "key": "node:End", "name": "Win"},
    {"op": "setMember", "node": "Win", "key": "payoff", "value": "win_loss(turn, 1, -1)"},
    {"op": "addTransition", "node": "Move", "target": "Win"},
    {"op": "moveTransition", "node": "Move", "index": 1, "to": 0},
    {"op": "updateTransition", "node": "Move", "index": 0, "when": "wins(mark(turn))"},
    {"op": "updateTransition", "node": "Move", "index": 1, "when": "full()"},
    {"op": "addTransition", "node": "Move", "target": "Move"},
    {"op": "updateTransition", "node": "Move", "index": 2, "effects": "turn = next(turn)"},
    # Inspector del juego: los tests y un invariante.
    {
        "op": "updateTest",
        "index": 0,
        "name": "X gana en diagonal",
        "body": "play place((0, 0)), place((0, 1)), place((1, 1)), place((0, 2)), place((2, 2))\n"
        "expect at(Win)\nexpect payoff == [1, -1]",
    },
    {
        "op": "addTest",
        "name": "tablero lleno sin línea: empate",
        "body": "play place((0, 0)), place((0, 1)), place((0, 2)), place((1, 1)), place((1, 0))\n"
        "play place((1, 2)), place((2, 1)), place((2, 0)), place((2, 2))\n"
        "expect at(Draw) and payoff == [0, 0]",
    },
    {
        "op": "addInvariant",
        "expr": "count(c in cells(board) : board[c] == X)"
        " - count(c in cells(board) : board[c] == O) in 0..1",
    },
]


def test_tictactoe_from_scratch_with_the_diagram_only(
    session: tuple[StudioThread, Session], workspace: Path
) -> None:
    studio, s = session
    # «Nuevo juego» con la plantilla vacía.
    body = {"name": "tres-en-raya", "template": "vacio", "title": "Tres en raya"}
    made = call(studio, "POST", "/api/new", body=body)
    assert made.status == 200
    path = workspace / made.json()["path"]
    doc = Document(s, path)
    assert doc.analysis["compiled"]
    assert [n["id"] for n in doc.game["flow"]["nodes"]] == ["Turn", "End"]

    for op in TICTACTOE_OPS:
        doc.apply(op)
        # El texto sigue siendo válido tras cada gesto (el diagrama nunca se queda sin modelo).
        assert doc.analysis["syntaxOk"], (op, doc.text)

    assert doc.analysis["compiled"], doc.errors()
    assert not doc.analysis["problems"], doc.analysis["problems"]
    assert [n["id"] for n in doc.game["flow"]["nodes"]] == ["Move", "Draw", "Win"]
    move = doc.node("Move")
    assert [(t["target"], t["when"]) for t in move["transitions"]] == [
        ("Win", "wins(mark(turn))"),
        ("Draw", "full()"),
        ("Move", None),
    ]
    assert doc.analysis["classification"]["perfect_information"] is True
    # Los comentarios de la plantilla siguen arriba.
    assert doc.text.startswith("// Tres en raya\n// Juego nuevo")

    # Los tests del juego pasan y los invariantes se cumplen en partidas aleatorias.
    report = s.request("gamehub/tests", {"uri": doc.uri, "playouts": 40})
    assert [(t["name"], t["ok"]) for t in report["tests"]] == [
        ("X gana en diagonal", True),
        ("tablero lleno sin línea: empate", True),
    ]
    assert report["invariants"] == 1
    assert report["playouts"]["games"] == 40 and report["playouts"]["failure"] is None

    # Se juega en el simulador: las cruces ganan en diagonal.
    started = s.request("gamehub/sim.start", {"uri": doc.uri, "seed": 1})
    sid, snap = started["session"], started["snapshot"]
    for cell in [(0, 0), (0, 1), (1, 1), (0, 2), (2, 2)]:
        seat = snap["active"][0]
        legal = snap["legal"][str(seat)]["actions"]
        action = next(a for a in legal if _cell(a) == cell)
        snap = s.request(
            "gamehub/sim.act",
            {"session": sid, "index": snap["index"], "seat": seat, "action": action},
        )
    assert snap["status"] == "terminal" and snap["payoffs"] == [1, -1]

    # Se guarda y es el mismo juego que el del catálogo: mismas jugadas legales en cada estado y
    # mismos pagos, en partidas al azar.
    saved = call(studio, "PUT", "/api/file", body={"path": made.json()["path"], "text": doc.text})
    assert saved.status == 200
    assert path.read_text(encoding="utf-8") == doc.text
    assert _same_game(_compile(doc.text), load_nomos(ROOT / "games/tictactoe/tictactoe.game"))


def _cell(action: Any) -> tuple[int, ...] | None:
    """La casilla de una acción `place` tal como la manda el protocolo."""
    found = re.findall(r"-?\d+", str(action))
    return tuple(int(x) for x in found) if len(found) == 2 else None


def _compile(text: str) -> Game:
    result = compile_source(Source("tres-en-raya.game", text), schema=False)
    assert result.ok, [d.message for d in result.diagnostics.errors]
    return Game(next(iter(result.games.values())).ir)


def _same_game(a: Game, b: Game, games: int = 40) -> bool:
    for seed in range(games):
        rng = random.Random(seed)
        sa, sb = a.new_state(2), b.new_state(2)
        while sa.payoffs is None:
            assert sb.payoffs is None
            assert sa.active_seats == sb.active_seats
            seat = sa.active_seats[0]
            la, lb = sa.legal_actions(seat), sb.legal_actions(seat)
            assert [show_action(x) for x in la] == [show_action(x) for x in lb]
            i = rng.randrange(len(la))
            sa, sb = sa.apply_action(seat, la[i]), sb.apply_action(seat, lb[i])
        assert sa.payoffs == sb.payoffs
    return True


# --- 2. Dudo: del diagrama al texto y del texto al diagrama --------------------------------------

#: Comentarios corrientes repartidos por el flujo de Dudo (además de los de la cabecera y de la
#: documentación `///` que ya tiene), para comprobar que ninguna edición se los come.
EXTRA_COMMENTS = [
    ("    start -> Roll\n", "    // Cada ronda empieza tirando los dados.\n    start -> Roll\n"),
    ("      face = 2\n      -> Bid\n", "      face = 2\n      -> Bid // a apostar\n"),
    (
        "      /// Dudar de la apuesta anterior",
        "      // (el orden de las acciones es el de los botones)\n\n"
        "      /// Dudar de la apuesta anterior",
    ),
    (
        "    terminal End {",
        "    // Gana quien conserva dados.\n    terminal End {",
    ),
]


def comments(text: str) -> Counter[str]:
    """Los comentarios del texto (`//` y `///`), sin la sangría: lo que no se puede perder."""
    return Counter(m.group(0).strip() for m in re.finditer(r"//.*", text))


def changed_lines(old: str, new: str) -> int:
    import difflib

    diff = difflib.unified_diff(old.splitlines(), new.splitlines(), n=0, lineterm="")
    return sum(1 for line in diff if line[:1] in "+-" and line[:3] not in ("+++", "---"))


def test_dudo_flow_edits_in_the_diagram_keep_the_comments(
    session: tuple[StudioThread, Session], workspace: Path
) -> None:
    _, s = session
    path = workspace / "dudo" / "dudo.game"
    text = path.read_text(encoding="utf-8")
    for old, new in EXTRA_COMMENTS:
        assert old in text
        text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")
    doc = Document(s, path)
    assert doc.analysis["compiled"], doc.errors()
    original = comments(doc.text)
    assert sum(original.values()) == 20

    # Una flecha que se arrastra a otro nodo cambia una sola línea del texto.
    before = doc.text
    doc.apply({"op": "addNode", "kind": "auto"})  # de la paleta: `auto Update`
    doc.apply({"op": "rename", "key": "node:Update", "name": "Reveal"})
    doc.apply({"op": "addTransition", "node": "Reveal", "target": "Roll"})
    step = doc.text
    doc.apply({"op": "updateTransition", "node": "Bid", "action": "dudo", "index": 1,
               "target": "Reveal"})  # fmt: skip
    assert changed_lines(step, doc.text) == 2  # la línea de la flecha, antes y después
    assert "-> Reveal { turn = first_alive_from(loser) }" in doc.text
    dudo = next(a for a in doc.node("Bid")["actions"] if a["name"] == "dudo")
    assert [t["target"] for t in dudo["transitions"]] == ["End", "Reveal"]
    assert doc.node("Reveal")["kind"] == "auto"
    assert [t["target"] for t in doc.node("Reveal")["transitions"]] == ["Roll"]

    # Reordenar las acciones (inspector) y meter la ronda en una fase (arrastrar al contenedor).
    doc.apply({"op": "moveAction", "node": "Bid", "action": "dudo", "index": 0})
    assert [a["name"] for a in doc.node("Bid")["actions"]] == ["dudo", "bid"]
    doc.apply({"op": "addNode", "kind": "phase"})  # `phase Round`
    for name in ("Roll", "Bid", "Reveal"):
        doc.apply({"op": "moveNode", "node": name, "parent": "Round"})
    assert {n["id"]: n["parent"] for n in doc.game["flow"]["nodes"]} == {
        "End": None,
        "Round": None,
        "Roll": "Round",
        "Bid": "Round",
        "Reveal": "Round",
    }
    assert doc.analysis["compiled"], doc.errors()
    # Ningún comentario se ha perdido, ni la documentación `///`.
    assert comments(doc.text) == original, comments(doc.text) - original
    assert doc.text.startswith(before[: before.index("game Dudo")])

    # Y sigue siendo Dudo: se juega entero.
    report = s.request("gamehub/tests", {"uri": doc.uri, "playouts": 10})
    assert all(t["ok"] for t in report["tests"]), report["tests"]
    assert report["playouts"]["failure"] is None


def test_dudo_text_edits_reach_the_diagram(
    session: tuple[StudioThread, Session], workspace: Path
) -> None:
    _, s = session
    doc = Document(s, workspace / "dudo" / "dudo.game")
    original = comments(doc.text)

    # Se escribe en el texto: una condición nueva, con su comentario, y un nodo nuevo.
    text = doc.text.replace(
        "        -> End when alive() == 1\n",
        "        // si solo queda uno, se acaba\n        -> End when alive() <= 1\n",
    )
    text = text.replace(
        "    terminal End {",
        "    terminal Abandoned { payoff: fill(0) }\n\n    terminal End {",
    )
    doc.type(text)
    dudo = next(a for a in doc.node("Bid")["actions"] if a["name"] == "dudo")
    assert dudo["transitions"][0]["when"] == "alive() <= 1"
    assert [n["id"] for n in doc.game["flow"]["nodes"]] == ["Roll", "Bid", "Abandoned", "End"]
    assert any(p["code"] == "W401" for p in doc.analysis["problems"])  # Abandoned, inalcanzable

    # Con el texto roto el diagrama no se pierde (el análisis no trae modelo y la app dibuja el
    # último); al arreglarlo, vuelve.
    doc.type(text.replace("decision Bid {", "decision Bid {{"))
    assert not doc.analysis["syntaxOk"] and doc.analysis["model"] is None
    doc.type(text)
    assert doc.analysis["syntaxOk"] and doc.node("Abandoned")["kind"] == "terminal"

    # Y del diagrama otra vez al texto, sin tocar lo escrito a mano.
    doc.apply({"op": "addTransition", "node": "Bid", "action": "dudo", "target": "Abandoned",
               "when": "alive() == 0"})  # fmt: skip
    assert "// si solo queda uno, se acaba" in doc.text
    assert comments(doc.text) - original == Counter({"// si solo queda uno, se acaba": 1})
    assert not doc.errors()
