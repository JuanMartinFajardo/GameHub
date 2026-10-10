# SPDX-License-Identifier: Apache-2.0
"""Protocolo de partidas v1 (spec/protocol/v1/protocol.schema.json).

- `parse_client`: lee y valida un mensaje de un cliente → `(tipo, datos, id)`.
- `message`: construye un mensaje del servidor; `check_server` lo valida (tests y depuración).
- `problems(nombre, valor)`: errores de un valor según una definición del esquema.

Los tipos (`gamehub.protocol.types`) se generan desde el esquema con
`gamehub protocol types --write`.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from gamehub.ir.spec import load_json, spec_dir

VERSION = 1
#: Tamaño máximo de un mensaje de cliente (bytes).
MAX_MESSAGE_BYTES = 64 * 1024


class ProtocolError(Exception):
    """Un mensaje que no cumple el protocolo. `code` es un código de error del esquema."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def schema_path() -> Path:
    return spec_dir().parent.parent / "protocol" / f"v{VERSION}" / "protocol.schema.json"


@cache
def schema() -> dict[str, Any]:
    return load_json(schema_path())


@cache
def _registry() -> Registry[Any]:
    doc = schema()
    resource = Resource.from_contents(doc, default_specification=DRAFT202012)
    return Registry().with_resource(doc["$id"], resource)


@cache
def _validator(name: str) -> Draft202012Validator:
    if name not in schema()["$defs"]:
        raise KeyError(f"definición desconocida en el protocolo: {name}")
    ref = {"$ref": f"{schema()['$id']}#/$defs/{name}"}
    return Draft202012Validator(ref, registry=_registry())


def problems(name: str, value: Any) -> list[str]:
    """Errores de `value` según la definición `name` del esquema (vacía si es válido)."""
    found = set()
    for error in _validator(name).iter_errors(value):
        detail = best_match([error]) or error
        path = "/".join(str(p) for p in detail.absolute_path)
        found.add(f"{path or '(raíz)'}: {detail.message}")
    return sorted(found)


def _def_name(ref: dict[str, str]) -> str:
    return ref["$ref"].rsplit("/", 1)[1]


@cache
def envelopes(union: str) -> dict[str, str]:
    """Tipo de mensaje → definición de su sobre, para `ClientMessage` o `ServerMessage`."""
    defs = schema()["$defs"]
    table = {}
    for ref in defs[union]["oneOf"]:
        name = _def_name(ref)
        table[defs[name]["properties"]["type"]["const"]] = name
    return table


@cache
def data_def(union: str, kind: str) -> str:
    """Definición de los datos de un tipo de mensaje."""
    envelope = schema()["$defs"][envelopes(union)[kind]]
    return _def_name(envelope["properties"]["data"])


def parse_client(raw: str | bytes) -> tuple[str, dict[str, Any], str | None]:
    """Mensaje de un cliente → `(tipo, datos, id)`. `ProtocolError("bad_message")` si no es
    JSON, no tiene la forma de un sobre o sus datos no cumplen el esquema de su tipo;
    `ProtocolError("unsupported")` si es de otra versión del protocolo."""
    if len(raw) > MAX_MESSAGE_BYTES:
        raise ProtocolError("bad_message", f"mensaje demasiado grande (> {MAX_MESSAGE_BYTES} B)")
    try:
        msg = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ProtocolError("bad_message", f"no es JSON válido: {exc}") from None
    if not isinstance(msg, dict):
        raise ProtocolError("bad_message", "un mensaje es un objeto {v, type, data}")
    if msg.get("v") != VERSION:
        raise ProtocolError("unsupported", f"versión del protocolo no admitida: {msg.get('v')!r}")
    kind = msg.get("type")
    table = envelopes("ClientMessage")
    if not isinstance(kind, str) or kind not in table:
        raise ProtocolError("bad_message", f"tipo de mensaje desconocido: {kind!r}")
    found = problems(table[kind], msg)
    if found:
        raise ProtocolError("bad_message", f"'{kind}': " + "; ".join(found[:3]))
    return kind, msg["data"], msg.get("id")


def message(kind: str, data: Any, re: str | None = None) -> dict[str, Any]:
    """Un mensaje del servidor (sin validar)."""
    msg: dict[str, Any] = {"v": VERSION, "type": kind, "data": data}
    if re is not None:
        msg["re"] = re
    return msg


def client_message(kind: str, data: Any, id: str | None = None) -> dict[str, Any]:
    """Un mensaje de cliente (sin validar)."""
    msg: dict[str, Any] = {"v": VERSION, "type": kind, "data": data}
    if id is not None:
        msg["id"] = id
    return msg


def check_server(msg: dict[str, Any]) -> list[str]:
    """Errores de un mensaje del servidor según el esquema (vacía si es válido)."""
    kind = msg.get("type")
    table = envelopes("ServerMessage")
    if not isinstance(kind, str) or kind not in table:
        return [f"tipo de mensaje del servidor desconocido: {kind!r}"]
    return problems(table[kind], msg)
