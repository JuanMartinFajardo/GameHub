# SPDX-License-Identifier: Apache-2.0
"""Catálogo de operadores de la GameIR (spec/ir/v0/ops.json) y generación de esquemas.

`expr.schema.json` y `stmt.schema.json` se generan a partir del catálogo:

    gamehub ir schemas --write   # regenera los esquemas
    gamehub ir schemas --check   # falla si están desactualizados
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from functools import cache
from typing import Any

from gamehub.ir.spec import SCHEMA_BASE_URI, load_json, spec_dir

ARG_KINDS = frozenset(
    {"e", "l", "id", "bind", "type", "node", "lit", "int", "fields", "cases", "block", "sel"}
    | {"pos", "vis", "text"}
)


@dataclass(frozen=True)
class ArgSpec:
    kind: str
    optional: bool = False
    variadic: bool = False

    @classmethod
    def parse(cls, raw: str) -> ArgSpec:
        if raw.endswith("?"):
            return cls(raw[:-1], optional=True)
        if raw.endswith("*"):
            return cls(raw[:-1], variadic=True)
        return cls(raw)


@dataclass(frozen=True)
class OpSpec:
    name: str
    args: tuple[ArgSpec, ...]
    doc: str
    chance: bool = False
    context: str | None = None

    @property
    def min_args(self) -> int:
        return sum(1 for a in self.args if not (a.optional or a.variadic))

    @property
    def variadic(self) -> ArgSpec | None:
        return next((a for a in self.args if a.variadic), None)

    def kinds_for(self, count: int) -> list[str]:
        """Tipo de cada uno de `count` argumentos reales (expande el variádico)."""
        fixed = [a.kind for a in self.args if not a.variadic]
        if self.variadic is not None and count > len(fixed):
            fixed += [self.variadic.kind] * (count - len(fixed))
        return fixed[:count]


@dataclass(frozen=True)
class Catalog:
    version: str
    expressions: dict[str, OpSpec]
    statements: dict[str, OpSpec]
    selectors: dict[str, OpSpec]

    @property
    def chance_statements(self) -> frozenset[str]:
        return frozenset(name for name, op in self.statements.items() if op.chance)


def _parse_ops(section: dict[str, Any]) -> dict[str, OpSpec]:
    return {
        name: OpSpec(
            name=name,
            args=tuple(ArgSpec.parse(a) for a in raw["args"]),
            doc=raw["doc"],
            chance=raw.get("chance", False),
            context=raw.get("context"),
        )
        for name, raw in section.items()
    }


@cache
def load_catalog() -> Catalog:
    raw = load_json(spec_dir() / "ops.json")
    return Catalog(
        version=raw["catalog_version"],
        expressions=_parse_ops(raw["expressions"]),
        statements=_parse_ops(raw["statements"]),
        selectors=_parse_ops(raw["selectors"]),
    )


def catalog_problems(catalog: Catalog) -> list[str]:
    """Errores de forma del propio catálogo."""
    problems: list[str] = []
    sections = {
        "expressions": catalog.expressions,
        "statements": catalog.statements,
        "selectors": catalog.selectors,
    }
    for section, ops in sections.items():
        for op in ops.values():
            where = f"{section}.{op.name}"
            if not op.doc.strip():
                problems.append(f"{where}: falta la documentación")
            seen_optional = False
            for i, arg in enumerate(op.args):
                if arg.kind not in ARG_KINDS:
                    problems.append(f"{where}: tipo de argumento desconocido {arg.kind!r}")
                if arg.variadic and i != len(op.args) - 1:
                    problems.append(f"{where}: el argumento variádico debe ser el último")
                if seen_optional and not (arg.optional or arg.variadic):
                    problems.append(f"{where}: argumento obligatorio después de uno opcional")
                seen_optional = seen_optional or arg.optional
            if section != "statements" and op.chance:
                problems.append(f"{where}: solo las sentencias pueden ser aleatorias")
    return problems


# --- Generación de esquemas --------------------------------------------------------------------

_IDENT = {"$ref": "common.schema.json#/$defs/ident"}
_EXPR = {"$ref": "expr.schema.json"}


def _arg_schema(kind: str) -> dict[str, Any]:
    match kind:
        case "e" | "l":
            return _EXPR
        case "id" | "bind" | "type" | "node":
            return _IDENT
        case "lit":
            return {"type": ["null", "boolean", "integer", "string"]}
        case "int":
            return {"type": "integer"}
        case "fields":
            return {"type": "object", "propertyNames": _IDENT, "additionalProperties": _EXPR}
        case "cases":
            pair = {"type": "array", "prefixItems": [_EXPR, _EXPR], "minItems": 2, "maxItems": 2}
            return {"type": "array", "minItems": 1, "items": pair}
        case "block":
            return {"$ref": "common.schema.json#/$defs/block"}
        case "sel":
            return {"$ref": "stmt.schema.json#/$defs/selector"}
        case "pos":
            return {"enum": ["top", "bottom"]}
        case "vis":
            return {"$ref": "common.schema.json#/$defs/visibility"}
        case "text":
            return {"$ref": "common.schema.json#/$defs/text"}
    raise ValueError(f"tipo de argumento desconocido: {kind}")


def _op_schema(op: OpSpec) -> dict[str, Any]:
    fixed = [a for a in op.args if not a.variadic]
    schema: dict[str, Any] = {
        "description": op.doc,
        "type": "array",
        "prefixItems": [{"const": op.name}, *(_arg_schema(a.kind) for a in fixed)],
        "minItems": 1 + op.min_args,
    }
    if op.variadic is not None:
        schema["items"] = _arg_schema(op.variadic.kind)
    else:
        schema["maxItems"] = 1 + len(op.args)
    return schema


def _dispatch(ops: dict[str, OpSpec], prefix: str = "") -> dict[str, Any]:
    names = sorted(ops)
    return {
        "type": "array",
        "minItems": 1,
        "prefixItems": [{"enum": names}],
        "allOf": [
            {"if": {"prefixItems": [{"const": n}]}, "then": {"$ref": f"#/$defs/{prefix}{n}"}}
            for n in names
        ],
    }


def build_schemas(catalog: Catalog) -> dict[str, dict[str, Any]]:
    """Esquemas generados, por nombre de archivo."""
    header = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$comment": "GENERADO desde ops.json por gamehub.ir.catalog. No editar a mano.",
    }
    expr = {
        **header,
        "$id": SCHEMA_BASE_URI + "expr.schema.json",
        "title": f"GameIR v0 — expresión (catálogo {catalog.version})",
        **_dispatch(catalog.expressions),
        "$defs": {n: _op_schema(op) for n, op in sorted(catalog.expressions.items())},
    }
    stmt = {
        **header,
        "$id": SCHEMA_BASE_URI + "stmt.schema.json",
        "title": f"GameIR v0 — sentencia (catálogo {catalog.version})",
        **_dispatch(catalog.statements),
        "$defs": {
            **{n: _op_schema(op) for n, op in sorted(catalog.statements.items())},
            "selector": _dispatch(catalog.selectors, prefix="sel_"),
            **{f"sel_{n}": _op_schema(op) for n, op in sorted(catalog.selectors.items())},
        },
    }
    return {"expr.schema.json": expr, "stmt.schema.json": stmt}


def render(schema: dict[str, Any]) -> str:
    return json.dumps(schema, ensure_ascii=False, indent=2) + "\n"


def sync_schemas(*, write: bool) -> int:
    """Comprueba (o regenera, si `write`) los esquemas generados. Devuelve el código de salida."""
    catalog = load_catalog()
    problems = catalog_problems(catalog)
    if problems:
        print("Catálogo inválido:", *problems, sep="\n  ", file=sys.stderr)
        return 1

    stale: list[str] = []
    for filename, schema in build_schemas(catalog).items():
        path = spec_dir() / filename
        text = render(schema)
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current == text:
            continue
        if write:
            path.write_text(text, encoding="utf-8")
            print(f"escrito {path}")
        else:
            stale.append(filename)
    if stale:
        print(
            "Esquemas desactualizados:",
            ", ".join(stale),
            "→ ejecuta: gamehub ir schemas --write",
            file=sys.stderr,
        )
        return 1
    return 0
