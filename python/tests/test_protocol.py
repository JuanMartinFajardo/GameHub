# SPDX-License-Identifier: Apache-2.0
"""Protocolo de partidas v1: el esquema, los tipos generados y la lectura de mensajes."""

from __future__ import annotations

import json

import pytest
from jsonschema import Draft202012Validator

from gamehub.protocol import (
    ProtocolError,
    check_server,
    client_message,
    data_def,
    envelopes,
    message,
    parse_client,
    problems,
    schema,
)
from gamehub.protocol.codegen import generate, sync_types, types_path


def test_schema_is_valid_json_schema() -> None:
    Draft202012Validator.check_schema(schema())


@pytest.mark.parametrize("union,link", [("ClientMessage", "id"), ("ServerMessage", "re")])
def test_envelopes_are_consistent(union: str, link: str) -> None:
    defs = schema()["$defs"]
    table = envelopes(union)
    assert len(table) == len(defs[union]["oneOf"]), "tipos de mensaje repetidos"
    for kind, name in table.items():
        envelope = defs[name]
        assert envelope["required"] == ["v", "type", "data"]
        assert envelope["additionalProperties"] is False
        props = envelope["properties"]
        assert props["v"] == {"const": 1}
        assert set(props) == {"v", "type", link, "data"}, kind
        assert data_def(union, kind) in defs


def test_every_reference_resolves() -> None:
    defs = schema()["$defs"]

    def refs(node: object) -> list[str]:
        if isinstance(node, dict):
            found = [node["$ref"]] if "$ref" in node else []
            return found + [r for v in node.values() for r in refs(v)]
        if isinstance(node, list):
            return [r for v in node for r in refs(v)]
        return []

    for ref in refs(schema()):
        assert ref.startswith("#/$defs/") and ref.rsplit("/", 1)[1] in defs, ref


def test_generated_types_are_up_to_date() -> None:
    assert sync_types(write=False) == 0
    assert types_path().read_text(encoding="utf-8") == generate(schema())


def test_generated_types_cover_every_definition() -> None:
    text = types_path().read_text(encoding="utf-8")
    for name in schema()["$defs"]:
        assert f"class {name}(TypedDict)" in text or f"type {name} = " in text, name


def hello(**data: object) -> str:
    return json.dumps(client_message("hello", {"client": {"name": "test", "kind": "bot"}, **data}))


def test_parse_a_valid_message() -> None:
    kind, data, msg_id = parse_client(hello(token="abc", legal_limit=10))
    assert kind == "hello" and data["token"] == "abc" and msg_id is None
    raw = json.dumps(client_message("act", {"seq": 3, "action": {"name": "x", "args": {}}}, "m1"))
    assert parse_client(raw) == ("act", {"seq": 3, "action": {"name": "x", "args": {}}}, "m1")


@pytest.mark.parametrize(
    "raw,code,fragment",
    [
        ("{no es json", "bad_message", "JSON"),
        ("[1, 2]", "bad_message", "objeto"),
        ('{"v": 2, "type": "hello", "data": {}}', "unsupported", "versión"),
        ('{"v": 1, "type": "teleport", "data": {}}', "bad_message", "desconocido"),
        (
            '{"v": 1, "type": "act", "data": {"seq": -1, "action": {"name": "x", "args": {}}}}',
            "bad_message",
            "seq",
        ),
        ('{"v": 1, "type": "ready", "data": {}}', "bad_message", "ready"),
        ('{"v": 1, "type": "leave", "data": {"why": 1}}', "bad_message", "why"),
        ('{"v": 1, "type": "chat", "data": {"text": "hola"}, "extra": 1}', "bad_message", "extra"),
    ],
)
def test_parse_rejects_bad_messages(raw: str, code: str, fragment: str) -> None:
    with pytest.raises(ProtocolError) as info:
        parse_client(raw)
    assert info.value.code == code
    assert fragment in info.value.message


def test_parse_rejects_huge_messages() -> None:
    with pytest.raises(ProtocolError, match="grande"):
        parse_client(hello(token="x" * 100_000))


def test_server_messages() -> None:
    ok = message("pong", {"t": 1.5, "server_time": 1_700_000_000.0}, re="p1")
    assert check_server(ok) == []
    assert check_server(message("pong", {"t": 1.5})) != []
    assert check_server({"v": 1, "type": "nope", "data": {}}) != []
    error = message("error", {"code": "room_full", "message": "no quedan asientos"})
    assert check_server(error) == []
    assert problems("RoomCode", "K7FQ2P") == []
    assert problems("RoomCode", "K7F-Q2P") != []  # en el protocolo va normalizado
    assert problems("Number", "-1/3") == [] and problems("Number", 1.5) != []
