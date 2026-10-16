# SPDX-License-Identifier: Apache-2.0
"""Ediciones del Studio: las operaciones del diagrama y de los formularios cambian solo lo
necesario del texto, sin perder comentarios (y lo comprueban tests de propiedad sobre todos los
juegos del catálogo)."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from gamehub.lang import ast
from gamehub.lang.compiler import compile_source, compile_text
from gamehub.lang.parser import parse_text
from gamehub.lang.source import Source
from gamehub.lang.symbols import RENAMABLE, SymbolIndex
from gamehub.studio.edits import EditError, apply_edits, text_changes

ROOT = Path(__file__).resolve().parents[2]
GAMES = sorted(p for p in (ROOT / "games").glob("*/*.game") if p.parent.name != "tests")
#: Los que tienen un juego con cuerpo (no solo un combinador como `repeat(…)`).
EDITABLE = [p for p in GAMES if re.search(r"^game \w+( extends \w+)? \{", p.read_text(), re.M)]

DEMO = """\
game Demo {
  players 2

  // el estado
  state {
    turn: Seat = 0 // de quién es el turno
    score: per_player Int
  }

  flow {
    start -> Play

    /// El turno de cada uno
    decision Play {
      actor: turn
      // jugar
      action go() { score[actor] += 1 }
      action stop()
      -> End when score[turn] >= 3 // fin
      -> Play { turn = next(turn) }
    }

    terminal End { payoff: [score[0], score[1]] }
  }
}
"""


def edit(*ops: dict[str, Any], text: str = DEMO) -> str:
    return apply_edits(text, list(ops)).text


def comments(text: str) -> Counter[str]:
    """Los comentarios `//` del texto (los `///` son documentación: van en el árbol)."""
    return Counter(m.group(0).rstrip() for m in re.finditer(r"(?<!/)//(?!/)[^\n]*", text))


# --- Operaciones ---------------------------------------------------------------------------------


def test_add_node_writes_only_the_new_node() -> None:
    result = apply_edits(DEMO, [{"op": "addNode", "kind": "terminal", "name": "Tie"}])
    assert result.focus == {"node": "Tie"}
    assert [c.insert for c in result.changes] == ["\n    terminal Tie { payoff: fill(0) }\n"]
    assert result.text.endswith(
        "    terminal End { payoff: [score[0], score[1]] }\n\n"
        "    terminal Tie { payoff: fill(0) }\n  }\n}\n"
    )


def test_new_nodes_get_a_free_name_and_placeholders() -> None:
    text = edit({"op": "addNode", "kind": "decision"}, {"op": "addNode", "kind": "decision"})
    assert "decision Turn { actor: 0 }" in text and "decision Turn2 { actor: 0 }" in text


def test_add_transition_goes_before_a_final_catch_all() -> None:
    text = edit({"op": "addTransition", "node": "Play", "target": "End", "when": "turn == 1"})
    assert (
        "      -> End when score[turn] >= 3 // fin\n"
        "      -> End when turn == 1\n"
        "      -> Play { turn = next(turn) }\n"
    ) in text


def test_action_transitions_open_the_action_block() -> None:
    text = edit({"op": "addTransition", "node": "Play", "action": "stop", "target": "End"})
    assert "      action stop() {\n        -> End\n      }\n" in text


def test_update_move_and_delete_transitions() -> None:
    text = edit({"op": "updateTransition", "node": "Play", "index": 0, "when": "turn == 0"})
    assert "-> End when turn == 0 // fin" in text
    text = edit({"op": "moveTransition", "node": "Play", "index": 1, "to": 0})
    assert text.index("-> Play {") < text.index("-> End when")
    text = edit({"op": "deleteTransition", "node": "Play", "index": 0})
    assert "-> End when" not in text and "// fin" not in text
    with pytest.raises(EditError, match="no hay transición número 5"):
        edit({"op": "deleteTransition", "node": "Play", "index": 5})


def test_delete_node_also_removes_the_arrows_into_it() -> None:
    text = edit({"op": "deleteNode", "node": "End"})
    assert "terminal End" not in text and "-> End" not in text
    assert "// jugar" in text and "/// El turno de cada uno" in text


def test_actions() -> None:
    text = edit(
        {
            "op": "addAction",
            "node": "Play",
            "name": "bet",
            "params": [{"name": "n", "domain": "1..3"}],
            "requires": "n <= 2",
            "effects": "score[actor] += n",
        }
    )
    assert "      action bet(n in 1..3) requires n <= 2 { score[actor] += n }\n" in text
    text = edit({"op": "updateAction", "node": "Play", "action": "go", "effects": ""})
    assert "      action go()\n      action stop()" in text
    text = edit({"op": "moveAction", "node": "Play", "action": "stop", "index": 0})
    assert text.index("action stop()") < text.index("// jugar") < text.index("action go()")
    text = edit({"op": "deleteAction", "node": "Play", "action": "go"})
    assert "action go" not in text and "// jugar" not in text


def test_members_blocks_and_kinds() -> None:
    text = edit({"op": "setMember", "node": "Play", "key": "actor", "value": "next(turn)"})
    assert "      actor: next(turn)\n" in text
    with pytest.raises(EditError, match="no tiene `payoff`"):
        edit({"op": "setMember", "node": "Play", "key": "payoff", "value": "fill(0)"})
    text = edit({"op": "setNodeKind", "node": "End", "kind": "auto"})
    assert "auto End {}" in text
    text = edit(
        {"op": "addNode", "kind": "chance", "name": "Roll"},
        {"op": "setBlock", "node": "Roll", "key": "effects", "value": "turn = random(seats)"},
        {"op": "addTransition", "node": "Roll", "target": "Play"},
    )
    assert "    chance Roll {\n      turn = random(seats)\n      -> Play\n    }\n" in text
    assert compile_text(text).ok


def test_phases_and_moving_nodes() -> None:
    text = edit(
        {"op": "addNode", "kind": "phase", "name": "Game"},
        {"op": "moveNode", "node": "Play", "parent": "Game"},
    )
    assert "    phase Game {\n      start -> Play\n\n      /// El turno de cada uno\n" in text
    assert "      decision Play {\n        actor: turn\n        // jugar\n" in text
    # El inicio del flow pasa a la fase que ahora contiene el nodo.
    assert "  flow {\n    start -> Game\n" in text
    assert compile_text(text).ok
    with pytest.raises(EditError, match="dentro de sí misma"):
        edit(
            {"op": "addNode", "kind": "phase", "name": "P"},
            {"op": "moveNode", "node": "P", "parent": "P"},
        )


def test_declarations() -> None:
    text = edit(
        {"op": "addEnum", "name": "Mark", "values": ["X", "O"]},
        {"op": "addState", "name": "board", "type": "Grid[3, 3] of Mark?", "init": "none"},
        {
            "op": "addFn",
            "name": "free",
            "params": [{"name": "c", "type": "Cell"}],
            "returns": "Bool",
            "body": "is_none(board[c])",
        },
        {"op": "setMeta", "key": "title", "value": {"es": "Demo", "en": "Demo"}},
        {"op": "setPlayers", "min": 2, "max": 4},
    )
    assert text.startswith('game Demo {\n  meta {\n    title: { es: "Demo", en: "Demo" }\n  }\n')
    assert "  players 2..4\n\n  enum Mark { X, O }\n\n  // el estado\n" in text
    assert "    score: per_player Int\n    board: Grid[3, 3] of Mark? = none\n  }\n" in text
    assert "  fn free(c: Cell) -> Bool = is_none(board[c])\n" in text
    assert compile_text(text).ok
    with pytest.raises(EditError, match="ya hay algo que se llama `turn`"):
        edit({"op": "addState", "name": "turn", "type": "Int"})


def test_errors_point_at_the_field() -> None:
    with pytest.raises(EditError) as info:
        edit({"op": "addTransition", "node": "Play", "target": "End", "when": "turn =="})
    error = info.value.to_json()
    assert error["field"] == "when"
    assert error["errors"][0]["offset"] == 7
    with pytest.raises(EditError, match="errores de sintaxis"):
        edit({"op": "addNode", "kind": "terminal"}, text=DEMO.replace("players 2", "players"))
    with pytest.raises(EditError, match="operación desconocida"):
        edit({"op": "fly"})


def test_ui_entries() -> None:
    text = edit({"op": "setUiEntry", "target": "turn", "hints": 'seat, label("Turno")'})
    assert '  ui {\n    turn: seat, label("Turno")\n  }\n}\n' in text
    again = edit({"op": "setUiEntry", "target": "turn", "hints": "hidden"}, text=text)
    assert "turn: hidden" in again and "seat" not in again
    gone = edit({"op": "setUiEntry", "target": "turn", "hints": None}, text=again)
    assert "ui {" not in gone


def test_insert_source_merges_into_existing_blocks() -> None:
    text = edit(
        {
            "op": "insertSource",
            "source": "state {\n  dice: List<Int>\n}\n"
            "flow {\n  start -> Other\n  terminal Other { payoff: fill(1) }\n}\n",
        }
    )
    assert "    score: per_player Int\n    dice: List<Int>\n  }" in text
    assert text.count("start ->") == 1 and "terminal Other" in text


def test_add_import_keeps_the_header_comments_on_top() -> None:
    text = "// Licencia\n// Mi juego\n\n" + DEMO
    result = edit(
        {"op": "addImport", "path": ["std", "cards"], "names": ["Card", "french52"]}, text=text
    )
    assert result.startswith(
        "// Licencia\n// Mi juego\n\nimport std.cards.{Card, french52}\n\ngame Demo {\n"
    )
    again = edit({"op": "addImport", "path": ["std", "cards"], "names": ["Rank"]}, text=result)
    assert "import std.cards.{Card, french52, Rank}\n" in again


def test_tests_and_invariants() -> None:
    body = "play go(), stop()\n// y otra vez\nexpect score[0] == 1"
    text = edit({"op": "addTest", "name": "un punto", "body": body})
    assert '  test "un punto" {\n    play go(), stop()\n    // y otra vez\n' in text
    assert text.rstrip().endswith("expect score[0] == 1\n  }\n}")
    renamed = edit({"op": "updateTest", "index": 0, "name": "uno"}, text=text)
    assert 'test "uno" {' in renamed and "// y otra vez" in renamed
    assert "test" not in edit({"op": "deleteTest", "index": 0}, text=renamed).split("flow")[1]
    with pytest.raises(EditError, match="ya hay un test") as exc:
        edit({"op": "addTest", "name": "uno"}, text=renamed)
    assert exc.value.field == "name"
    with pytest.raises(EditError, match="al menos un paso"):
        edit({"op": "updateTest", "index": 0, "body": "// nada"}, text=renamed)
    with pytest.raises(EditError) as exc:
        edit({"op": "updateTest", "index": 0, "body": "play go("}, text=renamed)
    assert exc.value.field == "body" and exc.value.errors
    with pytest.raises(EditError, match="ningún test en la posición 3"):
        edit({"op": "deleteTest", "index": 3}, text=renamed)
    # Un test sin nombre recibe uno libre; los invariantes van al final.
    text = edit({"op": "addTest"}, {"op": "addInvariant", "expr": "score[0] >= 0"}, text=text)
    assert 'test "test 2" {\n    expect true\n  }' in text
    assert text.rstrip().endswith("invariant score[0] >= 0\n}")
    text = edit({"op": "updateInvariant", "index": 0, "expr": "score[1] >= 0"}, text=text)
    assert "invariant score[1] >= 0" in text
    assert "invariant" not in edit({"op": "deleteInvariant", "index": 0}, text=text)


# --- Renombrar -----------------------------------------------------------------------------------


def test_rename_changes_every_use() -> None:
    text = edit({"op": "rename", "key": "state:score", "name": "points"})
    assert "score" not in text and text.count("points") == 5
    text = edit({"op": "rename", "key": "node:Play", "name": "Turn"})
    assert "start -> Turn" in text and "-> Turn {" in text and "decision Turn {" in text
    with pytest.raises(EditError, match="ya hay una variable de estado que se llama `turn`"):
        edit({"op": "rename", "key": "state:score", "name": "turn"})
    with pytest.raises(EditError, match="palabra reservada"):
        edit({"op": "rename", "key": "state:score", "name": "flow"})
    with pytest.raises(EditError, match="predefinido"):
        edit({"op": "rename", "key": "builtin:next", "name": "nxt"})


#: Cuántos símbolos de cada juego se renombran como mucho.
RENAME_SAMPLE = 40


@pytest.mark.parametrize("path", GAMES, ids=lambda p: p.stem)
def test_renaming_every_symbol_there_and_back(path: Path) -> None:
    """Renombrar cualquier símbolo deja un juego que compila, y volver al nombre original deja
    el texto como estaba."""
    text = path.read_text(encoding="utf-8")
    index = SymbolIndex()
    compile_source(Source(str(path), text, path), index=index, schema=False)
    keys = [
        k
        for k, s in index.symbols.items()
        if s.kind in RENAMABLE - {"game"}
        and any(d.source is not None and d.source.name == str(path) for d in s.decls)
    ]
    # En los juegos grandes (el ajedrez declara cientos de nombres), una muestra fija y repartida:
    # cada renombrado vuelve a compilar el juego dos veces.
    keys = sorted(keys)[:: -(-len(keys) // RENAME_SAMPLE)] if len(keys) > RENAME_SAMPLE else keys
    for key in keys:  # (un juego hecho con un combinador no declara nada)
        name = index.symbols[key].name
        try:
            renamed = apply_edits(
                text, [{"op": "rename", "key": key, "name": f"{name}_x"}], name=str(path), path=path
            ).text
        except EditError as exc:
            # Lo que se sustituye en un juego base (override) no se puede renombrar solo aquí.
            assert "no se puede renombrar así" in exc.message, (key, exc.message)
            continue
        assert renamed != text, key
        result = compile_source(Source(str(path), renamed, path), schema=False)
        assert result.ok, (key, [str(d) for d in result.diagnostics.errors][:2])
        if key.startswith("local:"):
            continue  # su clave es su posición, que cambia al renombrar otras cosas
        cut = max(key.rfind(":"), key.rfind("."))
        back_key = key[: cut + 1] + f"{name}_x"
        back = apply_edits(
            renamed, [{"op": "rename", "key": back_key, "name": name}], name=str(path), path=path
        ).text
        assert back == text, key


# --- Propiedades ---------------------------------------------------------------------------------

#: Operaciones que no quitan nada: el texto conserva todos sus comentarios.
KEEPS_COMMENTS = {
    "addNode",
    "addTransition",
    "updateTransition",
    "moveTransition",
    "addAction",
    "moveAction",
    "setMember",
    "addState",
    "rename",
    "moveNode",
    "setDoc",
}


def candidate_ops(text: str) -> list[dict[str, Any]]:
    """Operaciones válidas para el texto (según su árbol)."""
    tree, _ = parse_text(text)
    game = next(g for g in tree.items if isinstance(g, ast.GameDecl))
    nodes: list[tuple[ast.NodeDecl, ast.NodeDecl | None]] = []

    def walk(items: list[ast.Item], parent: ast.NodeDecl | None) -> None:
        for item in items:
            if isinstance(item, ast.NodeDecl):
                nodes.append((item, parent))
                if item.kind == "phase":
                    walk(item.members, item)

    for item in game.items:
        if isinstance(item, ast.FlowBlock):
            walk(item.items, None)
    names = [n.name for n, _ in nodes]
    phases = [n.name for n, _ in nodes if n.kind == "phase"]
    ops: list[dict[str, Any]] = []
    for kind in ("decision", "chance", "terminal", "auto"):
        ops.append({"op": "addNode", "kind": kind})
        for phase in phases:
            ops.append({"op": "addNode", "kind": kind, "parent": phase})
    for node, parent in nodes:
        transitions = [m for m in node.members if isinstance(m, ast.Transition)]
        actions = [m for m in node.members if isinstance(m, ast.ActionDecl)]
        targets = [*names[:4], *(["exit"] if parent is not None else [])]
        if node.kind != "terminal":
            for target in targets:
                ops.append(
                    {"op": "addTransition", "node": node.name, "target": target, "when": "true"}
                )
        for i in range(len(transitions)):
            ops.append({"op": "updateTransition", "node": node.name, "index": i, "when": "1 == 1"})
            ops.append({"op": "moveTransition", "node": node.name, "index": i, "to": 0})
            ops.append({"op": "deleteTransition", "node": node.name, "index": i})
        for a in actions:
            ops.append({"op": "moveAction", "node": node.name, "action": a.name, "index": 0})
            ops.append({"op": "deleteAction", "node": node.name, "action": a.name})
            for i in range(len(a.transitions)):
                ops.append(
                    {"op": "deleteTransition", "node": node.name, "action": a.name, "index": i}
                )
            if node.kind != "simultaneous":
                ops.append(
                    {"op": "addTransition", "node": node.name, "action": a.name, "target": names[0]}
                )
        if node.kind in ("decision", "window", "simultaneous"):
            ops.append({"op": "addAction", "node": node.name})
        if node.kind == "decision":
            ops.append({"op": "setMember", "node": node.name, "key": "actor", "value": "0"})
        ops.append({"op": "setDoc", "target": {"node": node.name}, "doc": "Un nodo"})
        if parent is None and phases and node.kind != "phase":
            ops.append({"op": "moveNode", "node": node.name, "parent": phases[0]})
        ops.append({"op": "deleteNode", "node": node.name})
        ops.append({"op": "rename", "key": f"node:{node.name}", "name": f"{node.name}Nuevo"})
    ops.append({"op": "addState", "type": "Int", "init": "0"})
    tests = [i for i in game.items if isinstance(i, ast.TestDecl)]
    invariants = [i for i in game.items if isinstance(i, ast.InvariantDecl)]
    for i in range(len(tests)):
        ops.append({"op": "updateTest", "index": i, "body": "expect true"})
        ops.append({"op": "deleteTest", "index": i})
    for i in range(len(invariants)):
        ops.append({"op": "updateInvariant", "index": i, "expr": "true"})
        ops.append({"op": "deleteInvariant", "index": i})
    ops.append({"op": "addTest", "body": "expect true"})
    ops.append({"op": "addInvariant", "expr": "true"})
    return ops


@pytest.mark.parametrize("path", EDITABLE, ids=lambda p: p.stem)
@settings(
    max_examples=15,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)
@given(data=st.data())
def test_random_edits_keep_the_text_valid_and_the_comments(path: Path, data: st.DataObject) -> None:
    text = path.read_text(encoding="utf-8")
    for _ in range(data.draw(st.integers(1, 4), label="pasos")):
        op = data.draw(st.sampled_from(candidate_ops(text)), label="op")
        try:
            result = apply_edits(text, [op], name=str(path), path=path)
        except EditError as exc:
            # Solo se aceptan los rechazos razonados (no los errores internos).
            assert "error interno" not in exc.message, (op, exc.message)
            continue
        new = result.text
        _, diagnostics = parse_text(new)
        assert not diagnostics.has_errors, (op, [str(d) for d in diagnostics.errors])
        if op["op"] in KEEPS_COMMENTS:
            assert comments(new) == comments(text), op
        else:
            assert not comments(new) - comments(text), op
        # Los cambios describen exactamente el paso del texto viejo al nuevo.
        rebuilt = text
        for change in sorted(result.changes, key=lambda c: c.start, reverse=True):
            rebuilt = rebuilt[: change.start] + change.insert + rebuilt[change.end :]
        assert rebuilt == new
        text = new


def test_text_changes_are_minimal() -> None:
    old = "a\nb\nc\nd\n"
    new = "a\nbx\nc\nd\ne\n"
    changes = text_changes(old, new)
    assert [(c.start, c.end, c.insert) for c in changes] == [(3, 3, "x"), (8, 8, "e\n")]
