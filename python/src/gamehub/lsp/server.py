# SPDX-License-Identifier: Apache-2.0
"""El servidor de lenguaje de Nomos sobre pygls.

Cada documento se analiza (parser, compilador sin el JSON Schema e índice de símbolos) en un hilo
aparte, un momento después del último cambio; al terminar se publican sus diagnósticos y se avisa
a quien escuche (el Studio, que manda el modelo del documento al diagrama). Las peticiones (hover,
renombrar…) usan el análisis de la versión actual; si aún no lo hay, lo hacen en el momento.

Transportes: la entrada estándar (`gamehub lsp`, para editores) y un WebSocket de Starlette (lo
usa `gamehub studio`), con una instancia del servidor por conexión.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from lsprotocol import types
from pygls.exceptions import JsonRpcInvalidParams
from pygls.lsp.server import LanguageServer

from gamehub.lsp import features as F
from gamehub.lsp.analysis import Analysis, Positions, analyze
from gamehub.studio.edits import EditError

logger = logging.getLogger(__name__)

#: Espera tras un cambio antes de analizar (para no compilar a cada tecla).
DEBOUNCE = 0.15


class NomosServer(LanguageServer):
    def __init__(self) -> None:
        from gamehub import __version__

        super().__init__(
            "gamehub-nomos",
            __version__,
            text_document_sync_kind=types.TextDocumentSyncKind.Incremental,
        )
        self.analyses: dict[str, Analysis] = {}
        self.last_good: dict[str, Analysis] = {}
        self.pending: dict[str, asyncio.Task[None]] = {}
        #: Funciones a las que avisar tras cada análisis (el Studio).
        self.listeners: list[Callable[[Analysis], None]] = []
        #: Versiones que llegarán de una edición del Studio (no de teclear): se analizan sin
        #: esperar, para que el diagrama se ponga al día enseguida.
        self.immediate: dict[str, int] = {}

    # --- análisis -------------------------------------------------------------------------------

    def _store(self, analysis: Analysis) -> None:
        self.analyses[analysis.uri] = analysis
        if analysis.result is not None:
            self.last_good[analysis.uri] = analysis

    def analysis(self, uri: str) -> Analysis:
        """El análisis de la versión actual del documento (se hace ahora si no está)."""
        doc = self.workspace.get_text_document(uri)
        current = self.analyses.get(uri)
        if current is not None and current.version == doc.version and current.text == doc.source:
            return current
        analysis = analyze(uri, doc.source, doc.version, doc.position_codec)
        self._store(analysis)
        return analysis

    def schedule(self, uri: str, delay: float = DEBOUNCE) -> None:
        task = self.pending.pop(uri, None)
        if task is not None:
            task.cancel()
        self.pending[uri] = asyncio.ensure_future(self._refresh(uri, delay))

    async def _refresh(self, uri: str, delay: float) -> None:
        try:
            if delay:
                await asyncio.sleep(delay)
            doc = self.workspace.get_text_document(uri)
            text, version, codec = doc.source, doc.version, doc.position_codec
            analysis = await asyncio.to_thread(analyze, uri, text, version, codec)
            if self.workspace.get_text_document(uri).version != version:
                return
            self._store(analysis)
            self.publish(analysis)
        except asyncio.CancelledError:
            pass
        except Exception:  # pragma: no cover - un fallo aquí no debe tirar el servidor
            logger.exception("fallo al analizar %s", uri)
        finally:
            if self.pending.get(uri) is asyncio.current_task():
                del self.pending[uri]

    def publish(self, analysis: Analysis) -> None:
        self.text_document_publish_diagnostics(
            types.PublishDiagnosticsParams(
                uri=analysis.uri, diagnostics=F.diagnostics(analysis), version=analysis.version
            )
        )
        for listener in self.listeners:
            listener(analysis)

    def offset(self, uri: str, position: types.Position) -> tuple[Analysis, int]:
        analysis = self.analysis(uri)
        return analysis, analysis.positions.offset(position)


def create_server() -> NomosServer:
    server = NomosServer()

    @server.feature(types.TEXT_DOCUMENT_DID_OPEN)
    def did_open(params: types.DidOpenTextDocumentParams) -> None:
        server.schedule(params.text_document.uri, 0)

    @server.feature(types.TEXT_DOCUMENT_DID_CHANGE)
    def did_change(params: types.DidChangeTextDocumentParams) -> None:
        uri, version = params.text_document.uri, params.text_document.version
        server.schedule(uri, 0 if server.immediate.pop(uri, None) == version else DEBOUNCE)

    @server.feature(types.TEXT_DOCUMENT_DID_SAVE)
    def did_save(params: types.DidSaveTextDocumentParams) -> None:
        server.schedule(params.text_document.uri, 0)

    @server.feature(types.TEXT_DOCUMENT_DID_CLOSE)
    def did_close(params: types.DidCloseTextDocumentParams) -> None:
        uri = params.text_document.uri
        task = server.pending.pop(uri, None)
        if task is not None:
            task.cancel()
        server.analyses.pop(uri, None)
        server.last_good.pop(uri, None)
        server.text_document_publish_diagnostics(
            types.PublishDiagnosticsParams(uri=uri, diagnostics=[])
        )

    @server.feature(types.TEXT_DOCUMENT_HOVER)
    def hover(params: types.HoverParams) -> types.Hover | None:
        analysis, offset = server.offset(params.text_document.uri, params.position)
        best = analysis
        if analysis.result is None:
            best = server.last_good.get(analysis.uri, analysis)
            offset = best.positions.offset(params.position)
        return F.hover(best, offset)

    @server.feature(types.TEXT_DOCUMENT_DEFINITION)
    def definition(params: types.DefinitionParams) -> list[types.Location]:
        analysis, offset = server.offset(params.text_document.uri, params.position)
        return F.definition(analysis, offset)

    @server.feature(types.TEXT_DOCUMENT_REFERENCES)
    def references(params: types.ReferenceParams) -> list[types.Location]:
        analysis, offset = server.offset(params.text_document.uri, params.position)
        return F.references(analysis, offset, params.context.include_declaration)

    @server.feature(types.TEXT_DOCUMENT_DOCUMENT_HIGHLIGHT)
    def highlight(params: types.DocumentHighlightParams) -> list[types.DocumentHighlight]:
        analysis, offset = server.offset(params.text_document.uri, params.position)
        return F.highlights(analysis, offset)

    @server.feature(types.TEXT_DOCUMENT_PREPARE_RENAME)
    def prepare_rename(params: types.PrepareRenameParams) -> types.PrepareRenamePlaceholder | None:
        analysis, offset = server.offset(params.text_document.uri, params.position)
        return F.prepare_rename(analysis, offset)

    @server.feature(types.TEXT_DOCUMENT_RENAME, types.RenameOptions(prepare_provider=True))
    def rename(params: types.RenameParams) -> types.WorkspaceEdit:
        analysis, offset = server.offset(params.text_document.uri, params.position)
        try:
            return F.rename(analysis, offset, params.new_name)
        except EditError as exc:
            raise JsonRpcInvalidParams(exc.message) from None

    @server.feature(types.TEXT_DOCUMENT_FORMATTING)
    def formatting(params: types.DocumentFormattingParams) -> list[types.TextEdit] | None:
        return F.formatting(server.analysis(params.text_document.uri))

    @server.feature(types.TEXT_DOCUMENT_DOCUMENT_SYMBOL)
    def symbols(params: types.DocumentSymbolParams) -> list[types.DocumentSymbol]:
        return F.document_symbols(server.analysis(params.text_document.uri))

    @server.feature(types.TEXT_DOCUMENT_FOLDING_RANGE)
    def folding(params: types.FoldingRangeParams) -> list[types.FoldingRange]:
        return F.folding_ranges(server.analysis(params.text_document.uri))

    @server.feature(
        types.TEXT_DOCUMENT_CODE_ACTION,
        types.CodeActionOptions(code_action_kinds=[types.CodeActionKind.QuickFix]),
    )
    def code_action(params: types.CodeActionParams) -> list[types.CodeAction]:
        analysis = server.analysis(params.text_document.uri)
        return F.code_actions(analysis, params.context.diagnostics)

    @server.feature(
        types.TEXT_DOCUMENT_SIGNATURE_HELP,
        types.SignatureHelpOptions(trigger_characters=["(", ","]),
    )
    def signature_help(params: types.SignatureHelpParams) -> types.SignatureHelp | None:
        analysis, offset = server.offset(params.text_document.uri, params.position)
        return F.signature_help(analysis, offset, server.last_good.get(analysis.uri))

    @server.feature(
        types.TEXT_DOCUMENT_COMPLETION,
        types.CompletionOptions(trigger_characters=[".", ">", "@", ":"]),
    )
    def completion(params: types.CompletionParams) -> types.CompletionList:
        uri = params.text_document.uri
        doc = server.workspace.get_text_document(uri)
        current = server.analyses.get(uri)
        if current is None or current.version != doc.version:
            # Mientras se escribe no se espera a compilar: basta con el árbol del texto actual.
            positions = Positions(doc.source, doc.position_codec)
            current = _parse_only(uri, doc.source, doc.version, positions)
        offset = current.positions.offset(params.position)
        return F.completion(current, offset, server.last_good.get(uri))

    return server


def _parse_only(uri: str, text: str, version: int | None, positions: Any) -> Analysis:
    """Un análisis solo sintáctico (rápido): para completar mientras se escribe."""
    from gamehub.lang.diagnostics import Diagnostics
    from gamehub.lang.parser import parse
    from gamehub.lang.source import Source
    from gamehub.lang.symbols import SymbolIndex
    from gamehub.lsp.analysis import uri_to_path

    path = uri_to_path(uri)
    source = Source(str(path) if path is not None else uri, text, path)
    diagnostics = Diagnostics()
    tree = parse(source, diagnostics)
    return Analysis(
        uri=uri,
        version=version,
        source=source,
        tree=tree,
        syntax_ok=not diagnostics.has_errors,
        parse_diagnostics=diagnostics,
        result=None,
        index=SymbolIndex(),
        positions=positions,
    )


# --- Transportes ---------------------------------------------------------------------------------


def run_stdio() -> None:
    """`gamehub lsp`: el servidor por la entrada y la salida estándar."""
    create_server().start_io()


class RpcError(Exception):
    """Error de un método propio: se responde como error de JSON-RPC."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


#: Un método propio (`gamehub/…`): recibe los parámetros tal cual llegan en el JSON.
Handler = Callable[[Any], Awaitable[Any]]


class _QueueWriter:
    """Escribe los mensajes del servidor en una cola que vacía una sola tarea (en orden)."""

    def __init__(self) -> None:
        self.queue: asyncio.Queue[str | None] = asyncio.Queue()

    def write(self, data: bytes) -> None:
        self.queue.put_nowait(data.decode("utf-8"))

    def send(self, message: dict[str, Any]) -> None:
        self.queue.put_nowait(json.dumps({"jsonrpc": "2.0", **message}, ensure_ascii=False))

    def close(self) -> None:
        self.queue.put_nowait(None)


async def run_websocket(
    websocket: Any,
    server: NomosServer,
    *,
    methods: dict[str, Handler] | None = None,
    on_open: Callable[[Callable[[dict[str, Any]], None]], None] | None = None,
) -> None:
    """Sirve el LSP por un WebSocket de Starlette (ya aceptado) hasta que se cierre.

    `methods`: métodos propios que se atienden aquí, con sus parámetros en JSON tal cual (pygls
    los convertiría en tuplas con nombre); se responden en orden de llegada al terminar.
    `on_open` recibe una función para mandar mensajes al cliente (notificaciones propias)."""
    from starlette.websockets import WebSocketDisconnect

    writer = _QueueWriter()
    server.protocol.set_writer(writer, include_headers=False)
    if on_open is not None:
        on_open(writer.send)
    custom = methods or {}

    async def send() -> None:
        while True:
            message = await writer.queue.get()
            if message is None:
                return
            with contextlib.suppress(Exception):
                await websocket.send_text(message)

    async def call(rid: Any, handler: Handler, params: Any) -> None:
        try:
            result = await handler(params)
            writer.send({"id": rid, "result": result})
        except RpcError as exc:
            error: dict[str, Any] = {"code": exc.code, "message": exc.message}
            if exc.data is not None:
                error["data"] = exc.data
            writer.send({"id": rid, "error": error})
        except Exception as exc:  # pragma: no cover - fallo inesperado de un método propio
            logger.exception("fallo en %s", rid)
            writer.send({"id": rid, "error": {"code": -32603, "message": f"error interno: {exc}"}})

    sender = asyncio.ensure_future(send())
    calls: set[asyncio.Task[None]] = set()
    try:
        while True:
            data = await websocket.receive_text()
            try:
                raw = json.loads(data)
            except ValueError:
                logger.warning("mensaje LSP no válido: %.200s", data)
                continue
            method = raw.get("method") if isinstance(raw, dict) else None
            if method == "exit":
                break  # pygls saldría del proceso: aquí solo se cierra esta conexión
            if method in custom:
                if "id" in raw:
                    task = asyncio.ensure_future(call(raw["id"], custom[method], raw.get("params")))
                else:
                    task = asyncio.ensure_future(custom[method](raw.get("params")))
                calls.add(task)
                task.add_done_callback(calls.discard)
                continue
            message = json.loads(data, object_hook=server.protocol.structure_message)
            server.protocol.handle_message(message)
    except WebSocketDisconnect:
        pass
    finally:
        for task in [*server.pending.values(), *calls]:
            task.cancel()
        writer.close()
        await sender
