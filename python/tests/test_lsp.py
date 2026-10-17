# SPDX-License-Identifier: Apache-2.0
"""Servidor de lenguaje de Nomos: sus funciones (directamente) y una sesión por la entrada
estándar con `gamehub lsp`."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import pytest
from lsprotocol import types

from gamehub.lsp import features as F
from gamehub.lsp.analysis import Analysis, analyze, path_to_uri
from gamehub.lsp.context import context_at
from gamehub.studio.edits import EditError

ROOT = Path(__file__).resolve().parents[2]
TICTACTOE = ROOT / "games" / "tictactoe" / "tictactoe.game"


def doc(text: str, name: str = "/tmp/juego.game") -> Analysis:
    return analyze(Path(name).as_uri(), text, 1)


def tictactoe() -> tuple[str, Analysis]:
    text = TICTACTOE.read_text(encoding="utf-8")
    return text, analyze(path_to_uri(TICTACTOE), text, 1)


def labels(result: types.CompletionList) -> list[str]:
    return [i.label for i in result.items]


def hover_text(analysis: Analysis, offset: int) -> str:
    h = F.hover(analysis, offset)
    assert h is not None and isinstance(h.contents, types.MarkupContent)
    return h.contents.value


# --- Diagnósticos, hover, definición, referencias -----------------------------------------------


def test_diagnostics_with_position_notes_and_help() -> None:
    a = doc(
        "game G {\n  players 2\n  state { turn: Seat = 0 }\n  flow {\n    start -> A\n"
        "    terminal A { payoff: fill(trun) }\n  }\n}\n"
    )
    [d] = F.diagnostics(a)
    assert d.code == "E201" and d.severity == types.DiagnosticSeverity.Error
    assert d.range.start == types.Position(5, 30) and d.range.end == types.Position(5, 34)
    assert "¿quisiste decir `turn`?" in d.message
    [fix] = F.code_actions(a, [d])
    assert fix.edit is not None and fix.edit.changes is not None
    assert fix.edit.changes[a.uri][0].new_text == "turn"


def test_syntax_errors_are_reported_without_compiling() -> None:
    a = doc("game G {\n  players\n}\n")
    assert not a.syntax_ok and a.result is None
    assert [d.code for d in F.diagnostics(a)] == ["E110"]


def test_hover() -> None:
    text, a = tictactoe()
    at = text.index("board[c] = mark")
    assert "board: Grid[3, 3] of Mark?" in hover_text(a, at + 1)
    assert "variable de estado" in hover_text(a, at + 1)
    assert "cells(g) -> List<Cell>" in hover_text(a, text.index("cells(board)") + 1)
    assert "**decision**" in hover_text(a, text.index("decision Move") + 1)
    assert "`actor`" not in hover_text(a, text.index("actor: turn") + 9)
    assert "fn mark(p: Seat) -> Mark" in hover_text(a, text.index("mark(turn)") + 1)
    # Una expresión sin nombre: su tipo.
    assert hover_text(a, text.index("(0, 0)") + 1) == "`0`: `Int`"


def test_definition_references_highlights() -> None:
    text, a = tictactoe()
    [loc] = F.definition(a, text.index("mark(turn)") + 1)
    assert loc.uri == path_to_uri(TICTACTOE)
    decl = text.index("fn mark") + 3
    assert loc.range.start == a.positions.position(decl)
    refs = F.references(a, text.index("mark(turn)") + 1, include_declaration=False)
    assert len(refs) == 6  # 2 en las reglas y 4 en la heurística
    assert len(F.references(a, decl, include_declaration=True)) == 7
    marks = F.highlights(a, decl)
    assert [h.kind for h in marks].count(types.DocumentHighlightKind.Write) == 1


def test_rename() -> None:
    text, a = tictactoe()
    at = text.index("turn: Seat")
    placeholder = F.prepare_rename(a, at)
    assert placeholder is not None and placeholder.placeholder == "turn"
    edit = F.rename(a, at, "player")
    assert edit.changes is not None
    edits = edit.changes[a.uri]
    assert all(e.new_text == "player" for e in edits) and len(edits) == 8
    with pytest.raises(EditError, match="ya hay una variable de estado"):
        F.rename(a, at, "board")
    # Lo predefinido no se renombra.
    assert F.prepare_rename(a, text.index("cells(board)") + 1) is None


def test_formatting_symbols_and_folding() -> None:
    a = doc("game G {\n    players 2\n  flow { start -> A\n terminal A { payoff: fill(0) } }\n}\n")
    edits = F.formatting(a)
    assert edits
    text = a.text
    for e in sorted(
        edits, key=lambda e: (e.range.start.line, e.range.start.character), reverse=True
    ):
        start = a.positions.offset(e.range.start)
        end = a.positions.offset(e.range.end)
        text = text[:start] + e.new_text + text[end:]
    assert text == (
        "game G {\n  players 2\n  flow {\n    start -> A\n"
        "    terminal A { payoff: fill(0) }\n  }\n}\n"
    )
    _, ttt = tictactoe()
    [game] = F.document_symbols(ttt)
    assert game.name == "TicTacToe"
    names = [c.name for c in game.children or []]
    assert names[:6] == ["Mark", "board", "turn", "mark", "wins", "full"]
    flow = next(c for c in game.children or [] if c.name == "flow")
    assert [n.name for n in flow.children or []] == ["Move", "Win", "Draw"]
    assert F.folding_ranges(ttt)


def test_signature_help() -> None:
    text, a = tictactoe()
    help_ = F.signature_help(a, text.index("lines(board, 3)") + len("lines(board, "))
    assert help_ is not None
    assert help_.signatures[0].label == "lines(g, k) -> List<List<Cell>>"
    assert help_.active_parameter == 1
    mine = F.signature_help(a, text.index("mark(turn)") + len("mark("))
    assert mine is not None and mine.signatures[0].label == "mark(p: Seat) -> Mark"


# --- Autocompletado -------------------------------------------------------------------------------


def complete(text: str, marker: str = "|", last_good: Analysis | None = None) -> list[str]:
    offset = text.index(marker)
    a = doc(text.replace(marker, "", 1))
    return labels(F.completion(a, offset, last_good))


GAME = """\
game G {
  players 2
  enum Mark { X, O }
  struct Card { suit: Mark, rank: Int }
  state {
    turn: Seat = 0
    hand: List<Card>
  }
  fn first_card() -> Card = hand[0]
  flow {
    start -> Play
    decision Play {
      actor: turn
      action pick(i in 0..2) { turn = next(turn) }
      -> End
    }
    terminal End { payoff: fill(0) }
  }
}
"""


def test_completion_contexts() -> None:
    good = doc(GAME)

    def at(anchor: str, insert: str) -> list[str]:
        # Mientras se escribe el texto suele estar roto: el servidor usa el último que compiló.
        text = GAME.replace(anchor, anchor + insert, 1)
        return complete(text, last_good=good)

    assert at("      -> ", "|") == ["Play", "End"]
    assert {"Bool", "Seat", "Mark", "Card", "Grid"} <= set(at("    hand: ", "|"))
    assert at("  fn first_card() -> Card = ", "Mark.|")[:3] == ["X", "O", "values"]
    assert set(at("  fn first_card() -> Card = ", "first_card().|")) >= {"suit", "rank"}
    assert set(at("  fn first_card() -> Card = hand[0]\n", "|")) >= {"state", "flow", "fn"}
    assert set(at("    decision Play {\n", "|")) >= {"actor", "action", "->"}
    assert set(at("    terminal End { ", "|")) >= {"payoff", "rank", "let"}
    stmts = at("action pick(i in 0..2) { ", "|")
    assert {"move", "shuffle", "turn"} <= set(stmts)
    expr = at("      -> End", " when |")
    assert {"turn", "hand", "first_card", "X", "seats", "cells"} <= set(expr)
    # Los parámetros de la acción, solo dentro de la acción.
    assert "i" in at("action pick(i in 0..2) { turn = ", "|")
    assert "i" not in at("      -> End", " when |")
    assert set(at("    decision Play {\n", "@|")) == {"visible", "size_visible", "doc"}


def test_completion_in_meta_ui_and_tests() -> None:
    text = GAME.replace("  players 2\n", "  meta {\n    |\n  }\n  players 2\n", 1)
    assert "title" in complete(text)
    text = GAME.replace("\n}\n", "\n  ui {\n    turn: |\n  }\n}\n")
    assert {"seat", "hidden", "label"} <= set(complete(text))
    text = GAME.replace("\n}\n", '\n  test "t" {\n    play |\n  }\n}\n')
    assert "pick" in complete(text, last_good=doc(GAME))


def test_completion_while_the_text_is_broken() -> None:
    good = doc(GAME)
    broken = GAME.replace("      -> End\n", "      -> End when tu|\n      oops oops\n")
    names = complete(broken, last_good=good)
    assert "turn" in names


def test_context_continues_after_operators() -> None:
    text = "game G {\n  flow {\n    decision A {\n      -> B when x and\n        y"
    ctx = context_at(text, len(text))
    assert ctx.prefix == "y" and [t.text for t in ctx.before][:2] == ["->", "B"]


# --- Sesión por la entrada estándar ---------------------------------------------------------------


class Client:
    def __init__(self) -> None:
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "gamehub", "lsp"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        self.next_id = 0
        self.messages: list[dict[str, Any]] = []
        self.lock = threading.Condition()
        threading.Thread(target=self.read, daemon=True).start()

    def read(self) -> None:
        assert self.proc.stdout is not None
        while True:
            header = b""
            while not header.endswith(b"\r\n\r\n"):
                ch = self.proc.stdout.read(1)
                if not ch:
                    return
                header += ch
            length = int(header.split(b"Content-Length:")[1].split(b"\r\n")[0])
            body = json.loads(self.proc.stdout.read(length))
            with self.lock:
                self.messages.append(body)
                self.lock.notify_all()

    def send(self, message: dict[str, Any]) -> None:
        data = json.dumps({"jsonrpc": "2.0", **message}).encode()
        assert self.proc.stdin is not None
        self.proc.stdin.write(f"Content-Length: {len(data)}\r\n\r\n".encode() + data)
        self.proc.stdin.flush()

    def wait(self, test: Any, timeout: float = 20) -> dict[str, Any]:
        with self.lock:
            ok = self.lock.wait_for(lambda: any(test(m) for m in self.messages), timeout=timeout)
            assert ok, self.messages
            return next(m for m in self.messages if test(m))

    def request(self, method: str, params: Any) -> Any:
        self.next_id += 1
        rid = self.next_id
        self.send({"id": rid, "method": method, "params": params})
        reply = self.wait(lambda m: m.get("id") == rid)
        assert "error" not in reply, reply
        return reply["result"]


def test_a_session_over_stdio() -> None:
    client = Client()
    try:
        init = client.request(
            "initialize", {"processId": None, "rootUri": None, "capabilities": {}}
        )
        caps = init["capabilities"]
        assert caps["hoverProvider"] and caps["renameProvider"] and caps["completionProvider"]
        client.send({"method": "initialized", "params": {}})
        uri = path_to_uri(TICTACTOE)
        text = TICTACTOE.read_text(encoding="utf-8").replace("turn: Seat = 0", "turn: Seat = true")
        client.send(
            {
                "method": "textDocument/didOpen",
                "params": {
                    "textDocument": {"uri": uri, "languageId": "nomos", "version": 1, "text": text}
                },
            }
        )
        published = client.wait(lambda m: m.get("method") == "textDocument/publishDiagnostics")
        assert [d["code"] for d in published["params"]["diagnostics"]] == ["E301"]
        line = text[: text.index("mark(turn)")].count("\n")
        hover = client.request(
            "textDocument/hover",
            {"textDocument": {"uri": uri}, "position": {"line": line, "character": 60}},
        )
        assert hover is None or "contents" in hover
        client.request("shutdown", None)
        client.send({"method": "exit"})
        assert client.proc.wait(timeout=20) == 0
    finally:
        if client.proc.poll() is None:
            client.proc.kill()
