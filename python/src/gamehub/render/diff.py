# SPDX-License-Identifier: Apache-2.0
"""Diff semántico entre dos versiones de un juego (`gamehub diff`).

Compara las IR elemento a elemento —meta, jugadores, opciones, restricciones, componentes,
estado, funciones y flow (nodos, sus miembros, acciones y transiciones)— emparejando por nombre
y no por línea, así que mover o reformatear el texto no cuenta como cambio. Cada cambio se
muestra en Nomos. También dice si cambian las reglas (el hash) o solo los textos.
"""

from __future__ import annotations

import difflib
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from gamehub.analysis import irwalk
from gamehub.ir.hashing import rules_hash
from gamehub.lang.decompile import expression_text, fragment_text, type_text

NODE_MEMBERS = ("actor", "actors", "eligible", "mode", "order", "start", "payoff", "rank")
BLOCKS = ("effects", "resolve", "on_enter", "on_exit")


@dataclass(frozen=True)
class Change:
    op: str  # "+" añadido, "-" quitado, "~" cambiado
    path: str
    old: str | None = None
    new: str | None = None

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"op": self.op, "path": self.path}
        if self.old is not None:
            out["old"] = self.old
        if self.new is not None:
            out["new"] = self.new
        return out


@dataclass(frozen=True)
class GameDiff:
    old_hash: str
    new_hash: str
    changes: list[Change]

    @property
    def same_rules(self) -> bool:
        return self.old_hash == self.new_hash


def diff(old: dict[str, Any], new: dict[str, Any]) -> GameDiff:
    return GameDiff(rules_hash(old), rules_hash(new), _Diff(old, new).run())


class _Diff:
    def __init__(self, old: dict[str, Any], new: dict[str, Any]) -> None:
        self.old = old
        self.new = new
        self.changes: list[Change] = []

    def add(self, op: str, path: str, old: str | None = None, new: str | None = None) -> None:
        self.changes.append(Change(op, path, old, new))

    def compare(self, path: str, old: str | None, new: str | None) -> None:
        if old == new:
            return
        if old is None:
            self.add("+", path, new=new)
        elif new is None:
            self.add("-", path, old=old)
        else:
            self.add("~", path, old, new)

    def run(self) -> list[Change]:
        old, new = self.old, self.new
        if old["game"] != new["game"]:
            self.compare("juego", _game(old), _game(new))
        old_meta, new_meta = old.get("meta", {}), new.get("meta", {})
        for key in sorted(set(old_meta) | set(new_meta)):
            self.compare(f"meta.{key}", _json(old_meta.get(key)), _json(new_meta.get(key)))
        self.compare("players", _players(old), _players(new))
        self.named(
            "opción",
            old.get("params", []),
            new.get("params", []),
            lambda ir, p: (
                f"{p['name']}: {type_text(ir, p['type'])} = " + expression_text(ir, p["default"])
            ),
        )
        self.sequence(
            "restricción",
            [expression_text(old, c["expr"]) for c in old.get("constraints", [])],
            [expression_text(new, c["expr"]) for c in new.get("constraints", [])],
        )
        self.named(
            "tipo",
            old.get("types", []),
            new.get("types", []),
            lambda ir, t: fragment_text(ir, "type", t),
        )
        self.named("estado", old.get("state", []), new.get("state", []), _state_text)
        self.named(
            "función",
            old.get("functions", []),
            new.get("functions", []),
            lambda ir, f: fragment_text(ir, "function", f),
        )
        self.flow()
        return self.changes

    def named(
        self,
        what: str,
        old: list[dict[str, Any]],
        new: list[dict[str, Any]],
        show: Callable[[dict[str, Any], dict[str, Any]], str],
        key: str = "name",
    ) -> None:
        old_items = {x[key]: show(self.old, x) for x in old}
        new_items = {x[key]: show(self.new, x) for x in new}
        for name in [*old_items, *(n for n in new_items if n not in old_items)]:
            self.compare(f"{what} {name}", old_items.get(name), new_items.get(name))

    def sequence(self, what: str, old: list[str], new: list[str]) -> None:
        matcher = difflib.SequenceMatcher(a=old, b=new, autojunk=False)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                continue
            if tag == "replace" and i2 - i1 == j2 - j1:
                for a, b in zip(old[i1:i2], new[j1:j2], strict=True):
                    self.add("~", what, a, b)
                continue
            for a in old[i1:i2]:
                self.add("-", what, old=a)
            for b in new[j1:j2]:
                self.add("+", what, new=b)

    # --- flow -----------------------------------------------------------------------------------

    def flow(self) -> None:
        old_flow, new_flow = self.old["flow"], self.new["flow"]
        self.compare("flow.start", old_flow["start"], new_flow["start"])
        self.compare(
            "flow.preparación",
            _block(self.old, old_flow.get("setup")),
            _block(self.new, new_flow.get("setup")),
        )
        old_nodes = {n["id"]: (n, p) for n, p in irwalk.all_nodes(self.old)}
        new_nodes = {n["id"]: (n, p) for n, p in irwalk.all_nodes(self.new)}
        for node_id in [*old_nodes, *(n for n in new_nodes if n not in old_nodes)]:
            if node_id not in new_nodes:
                self.add("-", f"nodo {node_id}", old=_node_header(*old_nodes[node_id]))
            elif node_id not in old_nodes:
                self.add("+", f"nodo {node_id}", new=_node_header(*new_nodes[node_id]))
            else:
                self.node(node_id, old_nodes[node_id], new_nodes[node_id])

    def node(
        self,
        node_id: str,
        old: tuple[dict[str, Any], str | None],
        new: tuple[dict[str, Any], str | None],
    ) -> None:
        (a, a_parent), (b, b_parent) = old, new
        path = f"nodo {node_id}"
        self.compare(path, _node_header(a, a_parent), _node_header(b, b_parent))
        for key in NODE_MEMBERS:
            self.compare(f"{path}.{key}", _member(self.old, a, key), _member(self.new, b, key))
        for key in BLOCKS:
            self.compare(
                f"{path}.{key}", _block(self.old, a.get(key)), _block(self.new, b.get(key))
            )
        self.named(
            f"{path}.acción",
            a.get("actions", []),
            b.get("actions", []),
            lambda ir, x: fragment_text(ir, "action", x),
        )
        self.sequence(
            f"{path}.transición",
            [fragment_text(self.old, "transition", t) for t in a.get("transitions", [])],
            [fragment_text(self.new, "transition", t) for t in b.get("transitions", [])],
        )


def _game(ir: dict[str, Any]) -> str:
    return f"{ir['game']['id']} {ir['game']['version']}"


def _json(value: Any) -> str | None:
    return None if value is None else json.dumps(value, ensure_ascii=False, sort_keys=True)


def _players(ir: dict[str, Any]) -> str:
    lo, hi = ir["players"]["min"], ir["players"]["max"]
    return str(lo) if lo == hi else f"{lo}..{hi}"


def _state_text(ir: dict[str, Any], v: dict[str, Any]) -> str:
    text = f"{v['name']}: {type_text(ir, v['type'])} = {expression_text(ir, v['init'])}"
    for key, label in (("visibility", "@visible"), ("size_visibility", "@size_visible")):
        vis = v.get(key)
        if vis not in (None, "all"):
            shown = vis if isinstance(vis, str) else expression_text(ir, vis["when"])
            text = f"{label}({shown}) {text}"
    return text


def _node_header(node: dict[str, Any], parent: str | None) -> str:
    where = f" (en la fase {parent})" if parent else ""
    return f"{node['kind']} {node['id']}{where}"


def _member(ir: dict[str, Any], node: dict[str, Any], key: str) -> str | None:
    if key not in node:
        return None
    value = node[key]
    if key in ("mode", "start"):
        return str(value)
    return expression_text(ir, value)


def _block(ir: dict[str, Any], block: list[Any] | None) -> str | None:
    if not block:
        return None
    from gamehub.lang.decompile import statements_text

    return statements_text(ir, block)


def format_diff(result: GameDiff) -> str:
    lines = []
    if result.same_rules:
        lines.append(f"mismas reglas ({result.old_hash[:19]}…)")
    else:
        lines.append(f"las reglas cambian: {result.old_hash[:19]}… → {result.new_hash[:19]}…")
    if not result.changes:
        lines.append("sin cambios")
    for c in result.changes:
        if c.op == "~":
            if "\n" in (c.old or "") or "\n" in (c.new or ""):
                lines.append(f"~ {c.path}:")
                lines += [f"    - {line}" for line in (c.old or "").splitlines()]
                lines += [f"    + {line}" for line in (c.new or "").splitlines()]
            else:
                lines.append(f"~ {c.path}: {c.old} → {c.new}")
        else:
            text = c.new if c.op == "+" else c.old
            first, *rest = (text or "").splitlines() or [""]
            lines.append(f"{c.op} {c.path}: {first}")
            lines += [f"    {line}" for line in rest]
    return "\n".join(lines) + "\n"
