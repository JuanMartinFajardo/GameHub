# SPDX-License-Identifier: Apache-2.0
"""Genera `gamehub/protocol/types.py` (un `TypedDict` por objeto) desde el esquema del protocolo.

    gamehub protocol types --write   # regenera los tipos
    gamehub protocol types --check   # falla si están desactualizados

Traducción: objeto cerrado (`additionalProperties: false`) → `TypedDict` (las propiedades no
obligatorias, `NotRequired`); objeto abierto → `dict[str, T]`; `oneOf`/`anyOf` y listas de tipos →
unión; `enum`/`const` → `Literal`; `array` → `list[T]`; sin tipo → `Any`. El resto de
definiciones son alias (`type X = …`). La salida ya tiene el formato de `ruff format`.
"""

from __future__ import annotations

import json
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gamehub.protocol import schema, schema_path

WIDTH = 100
INDENT = "    "

HEADER = '''# SPDX-License-Identifier: Apache-2.0
# Generado desde spec/protocol/v1/protocol.schema.json con `gamehub protocol types --write`.
# No editar a mano.
"""Tipos del protocolo de partidas v1: un `TypedDict` por objeto del esquema."""

from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict
'''


# --- Expresiones de tipo -------------------------------------------------------------------------


@dataclass(frozen=True)
class _Name:
    text: str


@dataclass(frozen=True)
class _Union:
    parts: tuple[Expr, ...]


@dataclass(frozen=True)
class _Subscript:
    head: str
    items: tuple[Expr, ...]


type Expr = _Name | _Union | _Subscript


def _flat(e: Expr) -> str:
    match e:
        case _Name(text):
            return text
        case _Union(parts):
            return " | ".join(_flat(p) for p in parts)
        case _Subscript(head, items):
            return f"{head}[{', '.join(_flat(i) for i in items)}]"


def _render(e: Expr, indent: str, room: int) -> str:
    """`e` en una línea si cabe en `room` columnas; si no, partida al estilo de ruff."""
    flat = _flat(e)
    if len(flat) <= room:
        return flat
    inner = indent + INDENT
    match e:
        case _Name(text):
            return text
        case _Union(parts):
            lines = [_render(p, inner, WIDTH - len(inner) - 2) for p in parts]
            body = f"\n{inner}| ".join(lines)
            return f"(\n{inner}{body}\n{indent})"
        case _Subscript(head, items):
            if len(items) == 1:
                [item] = items
                return f"{head}[\n{inner}{_render(item, inner, WIDTH - len(inner))}\n{indent}]"
            lines = [f"{inner}{_render(i, inner, WIDTH - len(inner) - 1)}," for i in items]
            return f"{head}[\n" + "\n".join(lines) + f"\n{indent}]"


def _literal(values: list[Any]) -> Expr:
    return _Subscript("Literal", tuple(_Name(json.dumps(v, ensure_ascii=False)) for v in values))


def _ref(ref: str) -> Expr:
    return _Name(ref.rsplit("/", 1)[1])


def _expr(s: Any) -> Expr:
    if s is True or s == {} or (isinstance(s, dict) and set(s) <= {"description"}):
        return _Name("Any")
    if "$ref" in s:
        return _ref(s["$ref"])
    if "const" in s:
        return _literal([s["const"]])
    if "enum" in s:
        return _literal(s["enum"])
    for key in ("oneOf", "anyOf"):
        if key in s:
            return _union([_expr(x) for x in s[key]])
    kind = s.get("type")
    if isinstance(kind, list):
        return _union([_expr({**s, "type": k}) for k in kind])
    match kind:
        case "string":
            return _Name("str")
        case "integer":
            return _Name("int")
        case "number":
            return _Name("float")
        case "boolean":
            return _Name("bool")
        case "null":
            return _Name("None")
        case "array":
            return _Subscript("list", (_expr(s.get("items", True)),))
        case "object":
            if _is_struct(s):
                raise ValueError("los objetos cerrados del protocolo deben ser definiciones")
            extra = s.get("additionalProperties", True)
            return _Subscript("dict", (_Name("str"), _expr(extra)))
    raise ValueError(f"esquema no admitido por el generador: {s}")


def _union(parts: list[Expr]) -> Expr:
    flat: list[Expr] = []
    for p in parts:
        flat.extend(p.parts if isinstance(p, _Union) else (p,))
    return flat[0] if len(flat) == 1 else _Union(tuple(flat))


def _is_struct(s: Any) -> bool:
    return (
        isinstance(s, dict) and s.get("type") == "object" and s.get("additionalProperties") is False
    )


# --- Definiciones --------------------------------------------------------------------------------


def _docstring(text: str, indent: str) -> list[str]:
    # Las comillas de cierre van siempre al final de la última línea (como deja ruff).
    lines = textwrap.wrap(f'"""{text}', width=WIDTH - len(indent) - 3, break_on_hyphens=False)
    lines[-1] += '"""'
    return [indent + line for line in lines]


def _comment(text: str) -> list[str]:
    return [f"# {line}" for line in textwrap.wrap(text, width=WIDTH - 2, break_on_hyphens=False)]


def _definition(name: str, s: dict[str, Any]) -> list[str]:
    doc = s.get("description")
    if _is_struct(s):
        lines = [f"class {name}(TypedDict):"]
        if doc:
            lines += _docstring(doc, INDENT)
            if s.get("properties"):
                lines.append("")
        required = set(s.get("required", []))
        for prop, ps in s.get("properties", {}).items():
            e = _expr(ps)
            if prop not in required:
                e = _Subscript("NotRequired", (e,))
            head = f"{INDENT}{prop}: "
            lines.append(head + _render(e, INDENT, WIDTH - len(head)))
        if len(lines) == 1:
            lines.append(f"{INDENT}pass")
        return lines
    head = f"type {name} = "
    lines = _comment(doc) if doc else []
    lines.append(head + _render(_expr(s), "", WIDTH - len(head)))
    return lines


def generate(doc: dict[str, Any]) -> str:
    chunks = ["\n".join(_definition(name, s)) for name, s in doc["$defs"].items()]
    # Tras los imports, una línea en blanco antes de un alias y dos antes de una clase.
    first = next(iter(doc["$defs"].values()))
    gap = "\n\n\n" if _is_struct(first) else "\n\n"
    return HEADER.rstrip("\n") + gap + "\n\n\n".join(chunks) + "\n"


def types_path() -> Path:
    return Path(__file__).with_name("types.py")


def sync_types(*, write: bool) -> int:
    """Comprueba (o regenera, si `write`) `types.py`. Devuelve el código de salida."""
    text = generate(schema())
    path = types_path()
    current = path.read_text(encoding="utf-8") if path.exists() else None
    if current == text:
        return 0
    if write:
        path.write_text(text, encoding="utf-8")
        print(f"escrito {path}")
        return 0
    print(
        f"Tipos del protocolo desactualizados respecto a {schema_path().name}"
        " → ejecuta: gamehub protocol types --write",
        file=sys.stderr,
    )
    return 1
