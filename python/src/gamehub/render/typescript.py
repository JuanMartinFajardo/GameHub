# SPDX-License-Identifier: Apache-2.0
"""Tipos de TypeScript de un juego (`gamehub sdk ts`): su vista, sus acciones y sus opciones.

Una UI propia los importa para tener autocompletado y para que el compilador avise si las reglas
cambian (una variable que desaparece, una acción con otro argumento):

    import type { Action, GameView, State } from "./game";

Traducción de los tipos de la IR: `Bool` → `boolean`; `Int` y `Seat` → `number`; `Real` →
`Real` (número o racional «n/d»); `Text` → `string`; `Cell` → `Cell` (`[fila, columna]`);
enumerados → unión de cadenas (y una constante con sus valores); structs → `interface`;
`T?` → `T | null`; listas y conjuntos → `T[]`; tuplas → `[A, B]`; mapas → `[K, V][]`;
`per_player T` → `T[]` (uno por asiento); zonas y bolsas → `Zone<T>`; rejillas → `T[][]`
(filas). Lo que puede estar oculto para quien mira (visibilidad distinta de `all`) admite
además `Hidden`.

La salida ya tiene el formato de Biome (la herramienta de formato de `web/`).
"""

from __future__ import annotations

import json
import textwrap
from typing import Any

from gamehub.ir.hashing import rules_hash

WIDTH = 100

PRIMITIVES = {
    "Bool": "boolean",
    "Int": "number",
    "Seat": "Seat",
    "Real": "Real",
    "Text": "string",
    "Cell": "Cell",
}

PRELUDE = """/** Un valor que quien mira no puede ver. */
export interface Hidden {
  $hidden: true;
}

/** Una zona o bolsa: su tamaño (si se ve) y los elementos que se ven. */
export interface Zone<T> {
  size?: number;
  items: (T | Hidden)[];
}

/** Un asiento (0, 1, …). */
export type Seat = number;

/** Una casilla de una rejilla: [fila, columna]. */
export type Cell = [number, number];

/** Número exacto: entero o racional como texto «n/d». */
export type Real = number | string;
"""


def _pascal(name: str) -> str:
    parts = [p for p in name.replace("-", "_").split("_") if p]
    return "".join(p[:1].upper() + p[1:] for p in parts)


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return str(value.get("es") or next(iter(value.values()), ""))
    return str(value)


def _doc(text: str, indent: str = "") -> list[str]:
    text = " ".join(text.split())
    if not text:
        return []
    one = f"{indent}/** {text} */"
    if len(one) <= WIDTH:
        return [one]
    body = textwrap.wrap(text, width=WIDTH - len(indent) - 3, break_on_hyphens=False)
    return [f"{indent}/**", *(f"{indent} * {line}" for line in body), f"{indent} */"]


def _hidden(visibility: Any) -> bool:
    return visibility is not None and visibility != "all"


class _Types:
    def __init__(self, ir: dict[str, Any]) -> None:
        self.ir = ir
        self.enums = {t["name"] for t in ir.get("types", []) if t["kind"] == "enum"}

    def ts(self, t: Any) -> str:
        if isinstance(t, str):
            return PRIMITIVES.get(t, t)
        head, *rest = t
        match head:
            case "option":
                return f"{self.ts(rest[0])} | null"
            case "list" | "set" | "per_player":
                return self.array(self.ts(rest[0]))
            case "tuple":
                return "[" + ", ".join(self.ts(x) for x in rest) + "]"
            case "map":
                return f"[{self.ts(rest[0])}, {self.ts(rest[1])}][]"
            case "zone" | "bag":
                return f"Zone<{self.ts(rest[0])}>"
            case "grid":
                return self.array(self.array(self.ts(rest[2])))
        raise ValueError(f"tipo de la IR desconocido: {t!r}")

    @staticmethod
    def array(inner: str) -> str:
        return f"({inner})[]" if _top_level_union(inner) else f"{inner}[]"

    def var(self, var: dict[str, Any]) -> str:
        """El tipo de una variable de estado tal como llega en una vista. Una zona nunca llega
        oculta entera: se ocultan sus elementos (y, si acaso, su tamaño)."""
        t = var["type"]
        per_player = isinstance(t, list) and t[0] == "per_player"
        base = t[1] if per_player else t
        zone = isinstance(base, list) and base[0] in ("zone", "bag")
        hidden = _hidden(var.get("visibility")) and not zone
        inner = self.ts(base)
        if hidden:
            inner = f"{inner} | Hidden"
        return self.array(inner) if per_player else inner


def _top_level_union(type_: str) -> bool:
    """¿Es `type_` una unión (`A | B`) fuera de paréntesis, corchetes y genéricos?"""
    depth = 0
    for i, ch in enumerate(type_):
        if ch in "([<{":
            depth += 1
        elif ch in ")]>}":
            depth -= 1
        elif ch == "|" and depth == 0 and type_[i - 1 : i + 2] == " | ":
            return True
    return False


def _member(name: str, type_: str, indent: str = "  ") -> list[str]:
    line = f"{indent}{name}: {type_};"
    if len(line) <= WIDTH:
        return [line]
    parts = [p.strip() for p in type_.split(" | ")]
    lines = [f"{indent}{name}:", *(f"{indent}  | {p}" for p in parts)]
    lines[-1] += ";"
    return lines


def _union(name: str, members: list[str]) -> list[str]:
    if not members:
        return [f"export type {name} = never;"]
    line = f"export type {name} = {' | '.join(members)};"
    if len(line) <= WIDTH:
        return [line]
    return [f"export type {name} =", *(f"  | {m}" for m in members[:-1]), f"  | {members[-1]};"]


def _const_list(name: str, values: list[str]) -> list[str]:
    quoted = [json.dumps(v, ensure_ascii=False) for v in values]
    line = f"export const {name} = [{', '.join(quoted)}] as const;"
    if len(line) <= WIDTH:
        return [line]
    return [f"export const {name} = [", *(f"  {q}," for q in quoted), "] as const;"]


def _actions(ir: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Las acciones del juego por nombre (los parámetros de la primera declaración) y si hay
    ventanas (que admiten `pass`)."""
    found: dict[str, list[dict[str, Any]]] = {}

    def walk(nodes: list[dict[str, Any]]) -> None:
        for node in nodes:
            if node["kind"] == "window":
                found.setdefault("pass", [])
            for action in node.get("actions", []):
                found.setdefault(action["name"], action.get("params", []))
            walk(node.get("nodes", []))

    walk(ir["flow"]["nodes"])
    return found


def _nodes(ir: dict[str, Any]) -> list[str]:
    ids: list[str] = []

    def walk(nodes: list[dict[str, Any]]) -> None:
        for node in nodes:
            ids.append(node["id"])
            walk(node.get("nodes", []))

    walk(ir["flow"]["nodes"])
    return ids


def game_types(ir: dict[str, Any]) -> str:
    """El módulo de TypeScript con los tipos del juego de `ir`."""
    types = _Types(ir)
    game = ir["game"]
    out: list[str] = [
        "// SPDX-License-Identifier: Apache-2.0",
        f"// Tipos de {game['id']} {game['version']}, generados de las reglas (`gamehub sdk ts`).",
        "// No editar a mano: se vuelven a generar cuando cambian las reglas.",
        "",
        'import type { View } from "@gamehub/protocol";',
        "",
        *_doc(_text(ir.get("meta", {}).get("title")) or game["id"]),
        f'export const GAME_ID = "{game["id"]}";',
        f'export const GAME_VERSION = "{game["version"]}";',
        f'export const RULES_HASH = "{rules_hash(ir)}";',
        "",
        PRELUDE.rstrip("\n"),
    ]
    for decl in ir.get("types", []):
        out.append("")
        out += _doc(_text(decl.get("doc")))
        if decl["kind"] == "enum":
            out += _union(decl["name"], [json.dumps(v, ensure_ascii=False) for v in decl["values"]])
            out += _const_list(decl["name"], decl["values"])
        else:
            out.append(f"export interface {decl['name']} {{")
            for field in decl["fields"]:
                out += _member(field["name"], types.ts(field["type"]))
            out.append("}")
    params = ir.get("params", [])
    out += ["", "/** Las opciones de la partida. */"]
    if params:
        out.append("export interface Params {")
        for p in params:
            out += _doc(_text(p.get("doc")), "  ")
            out += _member(p["name"], types.ts(p["type"]))
        out.append("}")
    else:
        out.append("export type Params = Record<string, never>;")
    out += ["", "/** El estado tal como lo ve quien mira (lo oculto llega como `Hidden`). */"]
    out.append("export interface State {")
    for var in ir["state"]:
        out += _doc(_text(var.get("doc")), "  ")
        out += _member(var["name"], types.var(var))
    out.append("}")
    out += ["", "/** Los nodos del flow. */"]
    out += _union("NodeId", [json.dumps(n) for n in _nodes(ir)])
    out += [
        "",
        "/** La vista de una actualización (`update.view`) con el estado de este juego. */",
        'export type GameView = Omit<View, "state" | "node"> & { node: NodeId | null; '
        "state: State };",
    ]
    actions = _actions(ir)
    names: list[str] = []
    for name, params_ in actions.items():
        type_name = f"{_pascal(name)}Action"
        names.append(type_name)
        out.append("")
        out.append(f"export interface {type_name} {{")
        out.append(f'  name: "{name}";')
        if params_:
            fields = [f"{p['name']}: {types.ts(p['type'])}" for p in params_]
            line = f"  args: {{ {'; '.join(fields)} }};"
            if len(line) <= WIDTH:
                out.append(line)
            else:
                out.append("  args: {")
                out += [f"    {f};" for f in fields]
                out.append("  };")
        else:
            out.append("  args: Record<string, never>;")
        out.append("}")
    out += ["", "/** Cualquier acción del juego. */"]
    out += _union("Action", names)
    text = "\n".join(out) + "\n"
    # El GameView largo: partido como lo haría Biome.
    return text.replace(
        'export type GameView = Omit<View, "state" | "node"> & { node: NodeId | null; state: '
        "State };",
        'export type GameView = Omit<View, "state" | "node"> & {\n  node: NodeId | null;\n'
        "  state: State;\n};",
    )
