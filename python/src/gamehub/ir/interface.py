# SPDX-License-Identifier: Apache-2.0
"""La interfaz de un juego: lo que ven y lo que mandan las UIs y los bots.

    {params:  {nombre: tipo},                                  # las opciones de la sala
     view:    {variable: {type, visibility, size_visibility}}, # lo que llega en las vistas
     actions: {nombre: [[{name, type, visibility}, …], …]},    # las firmas de cada acción
     events:  {nombre: [campo, …]},
     types:   {nombre: declaración}}                           # los tipos que nombran los demás

El **hash de interfaz** es el SHA-256 de su JSON canónico. Cambia menos que el de reglas: retocar
una condición, un pago o un efecto cambia las reglas, no la interfaz.

`compare` dice qué cambió entre dos versiones y si rompe algo (quitar o cambiar una acción, un
campo de la vista, una opción o un tipo que usan) o solo amplía (algo nuevo); `change_level`
lo traduce al nivel de semver que exige el hub (ADR-091).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from gamehub.analysis import irwalk
from gamehub.ir.hashing import canonical_json, rules_hash, strip_cosmetic
from gamehub.semver import Level

_PRIMITIVES = frozenset({"Bool", "Int", "Real", "Text", "Seat", "Cell"})


def interface(ir: dict[str, Any]) -> dict[str, Any]:
    declared = {t["name"]: t for t in ir.get("types", [])}
    used: set[str] = set()

    def ty(t: Any) -> Any:
        _collect(t, declared, used)
        return t

    params = {p["name"]: ty(p["type"]) for p in ir.get("params", [])}
    view: dict[str, Any] = {}
    for var in ir.get("state", []):
        vis = var.get("visibility", "all")
        size = var.get("size_visibility", "all")
        if vis == "none" and size == "none":
            continue
        view[var["name"]] = {"type": ty(var["type"]), "visibility": vis, "size_visibility": size}
    actions: dict[str, list[list[dict[str, Any]]]] = {}
    events: dict[str, list[str]] = {}
    blocks: list[list[Any]] = [ir["flow"].get("setup", [])]
    for node, _ in irwalk.all_nodes(ir):
        blocks += list(irwalk.node_blocks(node))
        for action in node.get("actions", []):
            sig = [
                {"name": p["name"], "type": ty(p["type"]), "visibility": p.get("visibility", "all")}
                for p in action.get("params", [])
            ]
            sigs = actions.setdefault(action["name"], [])
            if sig not in sigs:
                sigs.append(sig)
    for block in blocks:
        for stmt in irwalk.walk_block(block):
            if stmt[0] == "emit":
                fields = sorted(stmt[2]) if isinstance(stmt[2], dict) else []
                events[stmt[1]] = sorted(set(events.get(stmt[1], [])) | set(fields))
    for sigs in actions.values():
        sigs.sort(key=canonical_json)
    types = {name: _decl(declared[name]) for name in sorted(used)}
    return {"params": params, "view": view, "actions": actions, "events": events, "types": types}


def _collect(t: Any, declared: dict[str, Any], used: set[str]) -> None:
    """Añade a `used` los tipos declarados que nombra `t` (también los de sus campos)."""
    if isinstance(t, str):
        if t in declared and t not in used:
            used.add(t)
            for field in declared[t].get("fields", []):
                _collect(field["type"], declared, used)
    elif isinstance(t, list):
        for part in t[1:]:
            _collect(part, declared, used)


def _decl(decl: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in decl.items() if k != "doc"}
    return strip_cosmetic(out)


def interface_hash(ir: dict[str, Any]) -> str:
    digest = hashlib.sha256(canonical_json(interface(ir)).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


@dataclass(frozen=True)
class InterfaceChange:
    op: str  # "+" añadido, "-" quitado, "~" cambiado
    path: str  # p. ej. "actions.bid", "view.score", "types.Card"
    breaking: bool

    def __str__(self) -> str:
        mark = " (incompatible)" if self.breaking else ""
        return f"{self.op} {self.path}{mark}"

    def to_json(self) -> dict[str, Any]:
        return {"op": self.op, "path": self.path, "breaking": self.breaking}


def compare(old: dict[str, Any], new: dict[str, Any]) -> list[InterfaceChange]:
    """Los cambios de interfaz de `old` a `new`. Rompe quitar o cambiar algo; añadir, no (una
    opción nueva tiene su valor por defecto; una acción, un campo o un evento nuevos los
    ignora quien no los conoce)."""
    a, b = interface(old), interface(new)
    changes: list[InterfaceChange] = []
    for section in ("params", "view", "actions", "events", "types"):
        before, after = a[section], b[section]
        for name in sorted(set(before) | set(after)):
            path = f"{section}.{name}"
            if name not in after:
                changes.append(InterfaceChange("-", path, True))
            elif name not in before:
                changes.append(InterfaceChange("+", path, False))
            elif before[name] != after[name]:
                changes.append(
                    InterfaceChange("~", path, _breaking(section, before[name], after[name]))
                )
    return changes


def _breaking(section: str, old: Any, new: Any) -> bool:
    if section == "events":
        return not set(old) <= set(new)  # un campo nuevo en un evento no molesta
    if section == "actions":
        return not all(sig in new for sig in old)  # una firma nueva más, tampoco
    return True


def change_level(old: dict[str, Any], new: dict[str, Any]) -> Level | None:
    """El nivel de semver del cambio de `old` a `new`: `major` si la interfaz cambia de forma
    incompatible, `minor` si cambian las reglas o la interfaz se amplía, `patch` si solo cambian
    textos, presentación o heurísticas, y None si son idénticos."""
    changes = compare(old, new)
    if any(c.breaking for c in changes):
        return "major"
    if changes or rules_hash(old) != rules_hash(new):
        return "minor"
    if canonical_json(old) != canonical_json(new):
        return "patch"
    return None
