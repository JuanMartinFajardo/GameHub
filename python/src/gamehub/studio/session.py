# SPDX-License-Identifier: Apache-2.0
"""Una conexión del Studio: el servidor de lenguaje más los métodos propios (`gamehub/…`).

- `gamehub/analysis` (notificación del servidor, tras cada análisis, y petición): el modelo del
  documento para el diagrama y los formularios, sus problemas y la clasificación del juego.
- `gamehub/edit`: aplica operaciones del diagrama (ver `gamehub.studio.edits`) y devuelve los
  cambios de texto (en UTF-16) que el editor tiene que hacer.
- `gamehub/modelOf`: el modelo de un texto cualquiera (otra versión, para comparar).
- `gamehub/sim.*`: el simulador (ver `gamehub.studio.sim`).
- `gamehub/tests`: ejecuta los tests del juego y comprueba sus invariantes en partidas aleatorias.

Las posiciones van en desplazamientos UTF-16 (los de las cadenas de JavaScript).
"""

from __future__ import annotations

import asyncio
import secrets
from collections.abc import Callable
from pathlib import Path
from typing import Any

from gamehub.analysis.classify import classify
from gamehub.engine import Game
from gamehub.engine.errors import EngineError
from gamehub.lang import ast
from gamehub.lang.compiler import compile_source
from gamehub.lang.diagnostics import Diagnostic, Diagnostics, Severity
from gamehub.lang.model import CompiledGame
from gamehub.lang.parser import parse
from gamehub.lang.source import Source, Span
from gamehub.lang.testing import DEFAULT_SEED, GameTester
from gamehub.lsp.analysis import Analysis, uri_to_path
from gamehub.lsp.server import Handler, NomosServer, RpcError, create_server
from gamehub.studio import sim as S
from gamehub.studio.edits import EditError, apply_edits
from gamehub.studio.model import Utf16, document_model

INVALID = -32602
CONTENT_MODIFIED = -32801
FAILED = -32001

#: Simulaciones abiertas por conexión (las más viejas se cierran).
MAX_SIMULATIONS = 8


def problems_json(diagnostics: Diagnostics, source: Source) -> list[dict[str, Any]]:
    utf16 = Utf16(source.text)
    return [problem_json(d, source, utf16) for d in diagnostics.items]


def problem_json(d: Diagnostic, source: Source, utf16: Utf16) -> dict[str, Any]:
    item: dict[str, Any] = {
        "severity": "error" if d.severity is Severity.ERROR else "warning",
        "code": d.code,
        "message": d.message,
    }
    item.update(_where(d.span, source, utf16))
    if d.help:
        item["help"] = d.help
    if d.notes:
        item["notes"] = list(d.notes)
    return item


def _where(span: Span | None, source: Source, utf16: Utf16) -> dict[str, int]:
    """`from`/`to` (UTF-16) si la posición es del propio documento."""
    if span is None or span.source is None or span.source.name != source.name:
        return {}
    return {"from": utf16(span.start), "to": utf16(span.end)}


def analysis_json(analysis: Analysis, game: str | None = None) -> dict[str, Any]:
    result = analysis.result
    model = None
    if analysis.syntax_ok:
        model = document_model(
            analysis.source, analysis.tree, result.models if result is not None else None, game=game
        )
    classification = None
    if result is not None and result.ok and result.games:
        compiled = result.games.get(game or "") or next(iter(result.games.values()))
        info = classify(compiled.ir)
        classification = {"labels": info.labels(), **info.to_json()}
    return {
        "uri": analysis.uri,
        "version": analysis.version,
        "syntaxOk": analysis.syntax_ok,
        "compiled": result is not None and result.ok,
        "model": model,
        "problems": problems_json(analysis.diagnostics, analysis.source),
        "classification": classification,
    }


def _require(params: Any, *keys: str) -> dict[str, Any]:
    if not isinstance(params, dict):
        raise RpcError(INVALID, "faltan los parámetros")
    for key in keys:
        if key not in params:
            raise RpcError(INVALID, f"falta `{key}`")
    return params


def compile_condition(source: Source, game: str | None, expr: str) -> Any:
    """Compila una condición (un punto de ruptura) en el contexto del juego: se añade como
    invariante al final del juego y se toma su IR. Lanza `RpcError` con los errores situados en
    la condición."""
    diagnostics = Diagnostics()
    tree = parse(source, diagnostics)
    decls = [g for g in tree.items if isinstance(g, ast.GameDecl)]
    decl = next((g for g in decls if g.name == game), decls[0] if decls else None)
    if decl is None or diagnostics.has_errors:
        raise RpcError(FAILED, "el juego no compila")
    insert = decl.span.end - 1
    prefix = "\n  invariant "
    text = source.text[:insert] + prefix + expr.replace("\n", " ") + "\n" + source.text[insert:]
    start, end = insert + len(prefix), insert + len(prefix) + len(expr)
    result = compile_source(Source(source.name, text, source.path), schema=False)
    if not result.ok:
        mine = [
            {"message": d.message, "offset": max(0, d.span.start - start)}
            for d in result.diagnostics.errors
            if d.span is not None and start <= d.span.start <= end
        ]
        if mine:
            raise RpcError(INVALID, mine[0]["message"], {"errors": mine})
        raise RpcError(FAILED, "el juego no compila: corrige sus errores antes de usar condiciones")
    compiled = result.games.get(decl.name)
    if compiled is None or not compiled.invariants:
        raise RpcError(FAILED, "no se pudo compilar la condición")
    return compiled.invariants[-1].expr


class StudioSession:
    def __init__(self) -> None:
        self.server: NomosServer = create_server()
        self.send: Callable[[dict[str, Any]], None] = lambda message: None
        self.simulations: dict[str, S.Simulation] = {}
        self.sources: dict[str, str] = {}  # simulación → uri
        self.server.listeners.append(self.on_analysis)

    def open(self, send: Callable[[dict[str, Any]], None]) -> None:
        self.send = send

    def on_analysis(self, analysis: Analysis) -> None:
        self.send({"method": "gamehub/analysis", "params": analysis_json(analysis)})

    @property
    def methods(self) -> dict[str, Handler]:
        return {
            "gamehub/analysis": self.analysis,
            "gamehub/edit": self.edit,
            "gamehub/modelOf": self.model_of,
            "gamehub/sim.start": self.sim_start,
            "gamehub/sim.snapshot": self.sim_snapshot,
            "gamehub/sim.act": self.sim_act,
            "gamehub/sim.chance": self.sim_chance,
            "gamehub/sim.run": self.sim_run,
            "gamehub/sim.options": self.sim_options,
            "gamehub/sim.timeline": self.sim_timeline,
            "gamehub/sim.reload": self.sim_reload,
            "gamehub/sim.stop": self.sim_stop,
            "gamehub/sim.tree": self.sim_tree,
            "gamehub/sim.count": self.sim_count,
            "gamehub/sim.playouts": self.playouts,
            "gamehub/sim.estimate": self.estimate,
            "gamehub/sim.condition": self.condition,
            "gamehub/tests": self.tests,
        }

    # --- documento --------------------------------------------------------------------------

    def document(self, uri: str) -> Analysis:
        try:
            return self.server.analysis(uri)
        except Exception:
            raise RpcError(INVALID, f"el documento no está abierto: {uri}") from None

    async def analysis(self, params: Any) -> dict[str, Any]:
        p = _require(params, "uri")
        return analysis_json(self.document(p["uri"]), p.get("game"))

    async def edit(self, params: Any) -> dict[str, Any]:
        p = _require(params, "uri", "ops")
        uri = p["uri"]
        doc = self.server.workspace.get_text_document(uri)
        version = p.get("version")
        if version is not None and doc.version != version:
            raise RpcError(CONTENT_MODIFIED, "el texto ha cambiado: vuelve a intentarlo")
        path = uri_to_path(uri)
        name = str(path) if path is not None else uri
        try:
            result = await asyncio.to_thread(
                apply_edits, doc.source, list(p["ops"]), name=name, path=path, game=p.get("game")
            )
        except EditError as exc:
            raise RpcError(INVALID, exc.message, exc.to_json()) from None
        if result.changes and doc.version is not None:
            # El editor mandará el texto nuevo como la versión siguiente: se analiza en seguida.
            self.server.immediate[uri] = doc.version + 1
        utf16 = Utf16(doc.source)
        return {
            "edits": [
                {"from": utf16(c.start), "to": utf16(c.end), "insert": c.insert}
                for c in result.changes
            ],
            "focus": result.focus,
        }

    async def model_of(self, params: Any) -> dict[str, Any]:
        p = _require(params, "text")
        path = Path(p["path"]) if p.get("path") else None
        source = Source(str(path) if path else "<versión>", p["text"], path)
        result = await asyncio.to_thread(compile_source, source, schema=False)
        return {
            "model": document_model(source, result.file, result.models, game=p.get("game")),
            "compiled": result.ok,
        }

    # --- simulador --------------------------------------------------------------------------

    def game_of(self, uri: str, game: str | None) -> Game:
        compiled = self.compiled_of(uri, game)
        try:
            return Game(compiled.ir)
        except EngineError as exc:
            raise RpcError(FAILED, str(exc)) from None

    def compiled_of(self, uri: str, game: str | None) -> CompiledGame:
        analysis = self.document(uri)
        result = analysis.result
        if result is None:
            raise RpcError(FAILED, "el texto tiene errores de sintaxis")
        if not result.ok:
            first = result.diagnostics.errors[0]
            raise RpcError(FAILED, f"el juego no compila: {first.message}")
        compiled = result.games.get(game or "") if game else None
        if compiled is None:
            compiled = next(iter(result.games.values()), None)
        if compiled is None:
            raise RpcError(FAILED, "el archivo no tiene ningún juego")
        return compiled

    def simulation(self, params: Any) -> tuple[dict[str, Any], S.Simulation]:
        p = _require(params, "session")
        sim = self.simulations.get(p["session"])
        if sim is None:
            raise RpcError(INVALID, "esa simulación ya no existe")
        return p, sim

    def snapshot(self, sim: S.Simulation, index: int, seats: Any = None) -> dict[str, Any]:
        try:
            return sim.snapshot(index, seats if isinstance(seats, list) else None)
        except S.SimError as exc:
            raise RpcError(INVALID, str(exc)) from None

    async def sim_start(self, params: Any) -> dict[str, Any]:
        p = _require(params, "uri")
        game = await asyncio.to_thread(self.game_of, p["uri"], p.get("game"))
        players = p.get("players")
        lo, hi = game.players
        if players is not None and not (isinstance(players, int) and lo <= players <= hi):
            raise RpcError(INVALID, f"el juego admite de {lo} a {hi} jugadores")
        try:
            seed = int(p.get("seed", 0))
            sim = S.Simulation(game, players=players, params=p.get("params"), seed=seed)
        except EngineError as exc:
            raise RpcError(FAILED, str(exc)) from None
        session = secrets.token_hex(4)
        self.simulations[session] = sim
        self.sources[session] = p["uri"]
        while len(self.simulations) > MAX_SIMULATIONS:
            oldest = next(iter(self.simulations))
            self.simulations.pop(oldest)
            self.sources.pop(oldest, None)
        return {
            "session": session,
            "players": sim.players,
            "ir": game.ir,
            "snapshot": self.snapshot(sim, 0),
        }

    async def sim_snapshot(self, params: Any) -> dict[str, Any]:
        p, sim = self.simulation(params)
        index = p.get("index", len(sim.states) - 1)
        return self.snapshot(sim, index, p.get("seats"))

    async def sim_act(self, params: Any) -> dict[str, Any]:
        p, sim = self.simulation(params)
        try:
            index = sim.act(int(p["index"]), int(p["seat"]), p["action"])
        except (S.SimError, KeyError, TypeError, ValueError) as exc:
            raise RpcError(INVALID, str(exc), {"error": sim.error}) from None
        return self.snapshot(sim, index, p.get("seats"))

    async def sim_chance(self, params: Any) -> dict[str, Any]:
        p, sim = self.simulation(params)
        try:
            index = sim.chance(int(p["index"]), p.get("outcome"))
        except (S.SimError, KeyError, TypeError, ValueError) as exc:
            raise RpcError(INVALID, str(exc), {"error": sim.error}) from None
        return self.snapshot(sim, index, p.get("seats"))

    async def sim_run(self, params: Any) -> dict[str, Any]:
        p, sim = self.simulation(params)
        uri = self.sources[p["session"]]
        breakpoints: list[S.Condition] = []
        for bp in p.get("breakpoints") or []:
            if bp.get("node"):
                breakpoints.append(S.Condition(node=bp["node"], label=bp.get("label", "")))
            elif bp.get("expr"):
                analysis = self.document(uri)
                expr = compile_condition(analysis.source, p.get("game"), bp["expr"])
                breakpoints.append(S.Condition(expr=expr, label=bp.get("label") or bp["expr"]))
        policies = {int(k): v for k, v in (p.get("policies") or {}).items()}
        humans = {int(s) for s in p.get("humans") or []}
        try:
            index, reason, label = await asyncio.to_thread(
                sim.run,
                int(p["index"]),
                policies=policies,
                breakpoints=breakpoints,
                max_steps=int(p.get("maxSteps", 10_000)),
                stop_at_humans=humans,
            )
        except S.SimError as exc:
            raise RpcError(INVALID, str(exc)) from None
        return {
            "reason": reason,
            "label": label,
            "snapshot": self.snapshot(sim, index, p.get("seats")),
        }

    async def sim_options(self, params: Any) -> list[Any]:
        p, sim = self.simulation(params)
        try:
            return sim.options(int(p["index"]), int(p["seat"]), p.get("name"), p.get("args"))
        except (EngineError, S.SimError, KeyError, ValueError, TypeError) as exc:
            raise RpcError(INVALID, str(exc)) from None

    async def sim_timeline(self, params: Any) -> list[dict[str, Any]]:
        _, sim = self.simulation(params)
        return sim.timeline()

    async def sim_reload(self, params: Any) -> dict[str, Any]:
        p, sim = self.simulation(params)
        uri = self.sources[p["session"]]
        game = await asyncio.to_thread(self.game_of, uri, p.get("game"))
        kept = await asyncio.to_thread(sim.reload, game)
        return {
            "kept": kept,
            "ir": game.ir,
            "snapshot": self.snapshot(sim, len(sim.states) - 1, p.get("seats")),
        }

    async def sim_stop(self, params: Any) -> None:
        p = _require(params, "session")
        self.simulations.pop(p["session"], None)
        self.sources.pop(p["session"], None)

    async def sim_tree(self, params: Any) -> dict[str, Any]:
        p, sim = self.simulation(params)
        state = sim.state(int(p.get("index", len(sim.states) - 1)))
        try:
            return await asyncio.to_thread(S.tree, state, list(p.get("path") or []))
        except (S.SimError, EngineError) as exc:
            raise RpcError(INVALID, str(exc)) from None

    async def sim_count(self, params: Any) -> dict[str, Any]:
        p, sim = self.simulation(params)
        state = sim.state(int(p.get("index", len(sim.states) - 1)))
        budget = min(int(p.get("budget", 200_000)), 2_000_000)
        limit = min(float(p.get("timeLimit", 3)), 30)
        try:
            return await asyncio.to_thread(S.count_tree, state, budget=budget, time_limit=limit)
        except EngineError as exc:
            raise RpcError(FAILED, str(exc)) from None

    async def playouts(self, params: Any) -> dict[str, Any]:
        p = _require(params, "uri")
        game = await asyncio.to_thread(self.game_of, p["uri"], p.get("game"))
        try:
            return await asyncio.to_thread(
                S.playouts,
                game,
                games=min(int(p.get("games", 100)), 100_000),
                players=p.get("players"),
                params=p.get("params"),
                seed=int(p.get("seed", 0)),
                time_limit=min(float(p.get("timeLimit", 10)), 120),
            )
        except EngineError as exc:
            raise RpcError(FAILED, str(exc)) from None

    async def tests(self, params: Any) -> dict[str, Any]:
        p = _require(params, "uri")
        compiled = self.compiled_of(p["uri"], p.get("game"))
        source = self.document(p["uri"]).source
        playouts = max(0, min(int(p.get("playouts", 0)), 10_000))
        seed = int(p.get("seed", DEFAULT_SEED))
        try:
            report = await asyncio.to_thread(
                lambda: GameTester(compiled).run_all(playouts=playouts, seed=seed)
            )
        except EngineError as exc:
            raise RpcError(FAILED, str(exc)) from None
        utf16 = Utf16(source.text)
        failure = report.playouts.failure
        return {
            "tests": [
                {
                    "name": t.name,
                    "ok": t.ok,
                    **_where(t.span, source, utf16),
                    "failure": problem_json(t.failure, source, utf16) if t.failure else None,
                }
                for t in report.tests
            ],
            "invariants": report.invariants,
            "playouts": {
                "games": report.playouts.playouts,
                "states": report.playouts.states,
                "failure": problem_json(failure, source, utf16) if failure else None,
            },
        }

    async def estimate(self, params: Any) -> dict[str, Any]:
        p = _require(params, "uri")
        game = await asyncio.to_thread(self.game_of, p["uri"], p.get("game"))
        try:
            return await asyncio.to_thread(
                S.estimate_size,
                game,
                players=p.get("players"),
                params=p.get("params"),
                samples=min(int(p.get("samples", 200)), 10_000),
                seed=int(p.get("seed", 0)),
                time_limit=min(float(p.get("timeLimit", 5)), 60),
            )
        except EngineError as exc:
            raise RpcError(FAILED, str(exc)) from None

    async def condition(self, params: Any) -> dict[str, Any]:
        p = _require(params, "uri", "expr")
        analysis = self.document(p["uri"])
        compile_condition(analysis.source, p.get("game"), p["expr"])
        return {"ok": True}
