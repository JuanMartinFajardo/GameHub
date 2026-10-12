# SPDX-License-Identifier: Apache-2.0
"""Un cliente mínimo del Studio para los tests: la API HTTP (`call`) y una sesión por WebSocket con
el servidor de lenguaje y los métodos `gamehub/…` (`Session`)."""

from __future__ import annotations

import contextlib
import http.client
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from websockets.sync.client import connect

from gamehub.studio.server import StudioThread

TOKEN = "secreto-de-prueba"


class Response:
    def __init__(self, status: int, headers: dict[str, str], body: bytes) -> None:
        self.status = status
        self.headers = headers
        self.text = body.decode("utf-8", "replace")

    def json(self) -> Any:
        return json.loads(self.text)


def call(
    studio: StudioThread,
    method: str,
    path: str,
    *,
    body: Any = None,
    token: str | None = TOKEN,
    headers: dict[str, str] | None = None,
) -> Response:
    conn = http.client.HTTPConnection("127.0.0.1", studio.port, timeout=30)
    sent = dict(headers or {})
    if token is not None:
        sent.setdefault("x-gamehub-token", token)
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        sent["content-type"] = "application/json"
    conn.request(method, path, body=data, headers=sent)
    response = conn.getresponse()
    out = Response(
        response.status, {k.lower(): v for k, v in response.getheaders()}, response.read()
    )
    conn.close()
    return out


class Session:
    def __init__(self, ws: Any) -> None:
        self.ws = ws
        self.next_id = 0
        self.notes: list[dict[str, Any]] = []

    def request(self, method: str, params: Any = None) -> Any:
        self.next_id += 1
        rid = self.next_id
        self.ws.send(json.dumps({"jsonrpc": "2.0", "id": rid, "method": method, "params": params}))
        while True:
            message = json.loads(self.ws.recv(timeout=60))
            if message.get("id") == rid:
                if "error" in message:
                    raise RuntimeError(json.dumps(message["error"], ensure_ascii=False))
                return message["result"]
            if "method" in message:
                self.notes.append(message)

    def notify(self, method: str, params: Any) -> None:
        self.ws.send(json.dumps({"jsonrpc": "2.0", "method": method, "params": params}))

    def open(self, path: Path) -> str:
        uri = path.as_uri()
        text = path.read_text(encoding="utf-8")
        document = {"uri": uri, "languageId": "nomos", "version": 1, "text": text}
        self.notify("textDocument/didOpen", {"textDocument": document})
        return uri

    def wait(self, method: str, test: Any = lambda p: True) -> dict[str, Any]:
        while True:
            for note in self.notes:
                if note["method"] == method and test(note["params"]):
                    self.notes.remove(note)
                    return note["params"]
            message = json.loads(self.ws.recv(timeout=60))
            if "method" in message:
                self.notes.append(message)

    def edit(self, uri: str, version: int, text: str, ops: list[dict[str, Any]]) -> str:
        """Lo que hace el editor del Studio: pide la edición, aplica los cambios al texto y se
        los manda al servidor como la versión siguiente. Devuelve el texto nuevo."""
        result = self.request("gamehub/edit", {"uri": uri, "version": version, "ops": ops})
        new = apply(text, result["edits"])
        change = {
            "textDocument": {"uri": uri, "version": version + 1},
            "contentChanges": [{"text": new}],
        }
        self.notify("textDocument/didChange", change)
        return new


def apply(text: str, edits: list[dict[str, Any]]) -> str:
    for e in sorted(edits, key=lambda e: e["from"], reverse=True):
        text = text[: e["from"]] + e["insert"] + text[e["to"] :]
    return text


@contextlib.contextmanager
def open_session(studio: StudioThread, root: Path) -> Iterator[Session]:
    url = f"ws://127.0.0.1:{studio.port}/lsp?token={TOKEN}"
    with connect(url, max_size=None) as ws:
        s = Session(ws)
        init = {"processId": None, "rootUri": root.as_uri(), "capabilities": {}}
        s.request("initialize", init)
        s.notify("initialized", {})
        yield s
