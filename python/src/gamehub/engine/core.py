# SPDX-License-Identifier: Apache-2.0
"""El motor C++ (`gamehub-core`, F8) con la API del motor de referencia.

    from gamehub.engine.core import CoreGame, available
    game = CoreGame(ir)                 # o core_game(game) a partir de un `Game`
    state = game.new_state(2)
    state = state.apply_action(0, state.legal_actions(0)[4])

`CoreGame` y `CoreState` tienen los mismos métodos que `Game` y `State` (`gamehub.engine`), con los
mismos valores de Python (`Action`, `EnumValue`, `Fraction`…), así que los drivers (`play_match`,
`fuzz`, `record`, `replay`) funcionan con cualquiera de los dos. La semántica es la misma: lo
comprueban las trazas de conformidad y la suite diferencial (`gamehub diff`, ADR-078).

Diferencias: `evaluate` y `edited` (herramientas de los tests de Nomos) no existen en C++, y los
enteros son de 64 bits (un desbordamiento es un `RuleError`, ADR-076). Los algoritmos en C++
(playouts, alfa-beta, MCTS, CFR…) están en `gamehub.engine.core_algorithms`.

Necesita el paquete `gamehub-core` (`pip install 'gamehub[core]'`).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from fractions import Fraction
from typing import TYPE_CHECKING, Any

from gamehub.engine.errors import RuleError
from gamehub.engine.events import Event
from gamehub.engine.rng import Pcg32
from gamehub.engine.state import PASS, Action, Status, Step
from gamehub.engine.values import Type, TypeTable

if TYPE_CHECKING:
    from gamehub.engine.game import Game

try:
    import gamehub_core as _core  # pyright: ignore[reportMissingImports]
except ImportError:  # pragma: no cover - depende de la instalación
    _core = None


def available() -> bool:
    """¿Está instalado el núcleo C++?"""
    return _core is not None


def _require() -> Any:
    if _core is None:
        raise ImportError("el núcleo C++ no está instalado: pip install 'gamehub[core]'")
    return _core


_STATUS = {"chance": Status.CHANCE, "decision": Status.DECISION, "terminal": Status.TERMINAL}


def _number(j: Any) -> Any:
    """Un número en JSON (entero o "n/d") como valor del motor."""
    if isinstance(j, str):
        return Fraction(j)
    return j


class CoreGame:
    """Un juego cargado en el motor C++ (la misma interfaz que `Game`)."""

    def __init__(self, ir: dict[str, Any], *, check: bool = True) -> None:
        core = _require()
        if check:
            from gamehub.ir import check as check_ir

            problems = check_ir(ir)
            if problems:
                listing = "\n  ".join(str(p) for p in problems[:20])
                raise RuleError(f"la IR no es válida:\n  {listing}")
        self.ir = ir
        self.core = core.Game(json.dumps(ir, ensure_ascii=False))
        self.types = TypeTable(ir.get("types", []))
        self._params: dict[tuple[str, str], list[tuple[str, Type]]] = {}
        self._param_types = {p["name"]: self.types.parse(p["type"]) for p in ir.get("params", [])}

        def walk(nodes: list[dict[str, Any]]) -> None:
            for node in nodes:
                for a in node.get("actions", []):
                    self._params[(node["id"], a["name"])] = [
                        (p["name"], self.types.parse(p["type"])) for p in a.get("params", [])
                    ]
                if node["kind"] == "phase":
                    walk(node["nodes"])

        walk(ir["flow"]["nodes"])

    @property
    def id(self) -> str:
        return self.ir["game"]["id"]

    @property
    def version(self) -> str:
        return self.ir["game"]["version"]

    @property
    def title(self) -> str:
        return self.core.title

    @property
    def rules_hash(self) -> str:
        return self.core.rules_hash

    @property
    def players(self) -> tuple[int, int]:
        return tuple(self.core.players)  # type: ignore[return-value]

    def new_state(
        self,
        num_players: int | None = None,
        params: dict[str, Any] | None = None,
        *,
        events: bool = True,
        history: bool = True,
    ) -> CoreState:
        n = num_players or self.players[0]
        state = self.core.new_state(n, params or {}, events=events, history=history)
        return CoreState(self, state, params or {})

    def action_from_json(self, node: str | None, data: dict[str, Any]) -> Action:
        """Una acción (JSON con su nombre y sus argumentos) como `Action` con valores del motor."""
        name = data["name"]
        if name == "pass" and (node, name) not in self._params:
            return PASS
        params = self._params.get((node or "", name), [])
        given = data.get("args", {})
        return Action(name, tuple((p, self.types.decode(given[p], t)) for p, t in params))

    def decode_action(self, node: str | None, data: dict[str, Any]) -> Action:
        """Acción del nodo `node` desde JSON, sin estado (como `Game.decode_action`)."""
        action = self.core.decode_action(node, data)
        return self.action_from_json(node, self.core.action_to_json(action))


def core_game(game: Game) -> CoreGame:
    """El mismo juego (ya validado) en el motor C++."""
    return CoreGame(game.ir, check=False)


class CoreState:
    """Un estado del motor C++ (la misma interfaz que `State`)."""

    __slots__ = ("_given", "_s", "game")

    def __init__(self, game: CoreGame, state: Any, given: dict[str, Any]) -> None:
        self.game = game
        self._s = state
        self._given = given

    # --- consulta -----------------------------------------------------------------------------

    @property
    def core(self) -> Any:
        """El estado de `gamehub_core` (para los algoritmos en C++)."""
        return self._s

    @property
    def status(self) -> Status:
        return _STATUS[self._s.status]

    @property
    def is_terminal(self) -> bool:
        return self._s.is_terminal

    @property
    def active_seats(self) -> tuple[int, ...]:
        return self._s.active_seats

    @property
    def node(self) -> str | None:
        return self._s.node

    @property
    def n(self) -> int:
        return self._s.num_players

    @property
    def depth(self) -> int:
        return self._s.depth

    @property
    def payoffs(self) -> tuple[Any, ...] | None:
        raw = self._s.payoffs
        return None if raw is None else tuple(_number(p) for p in raw)

    @property
    def params(self) -> dict[str, Any]:
        """Los parámetros de la partida (con sus valores por defecto), como `State.params`."""
        raw = self._s.params()
        values: dict[str, Any] = {"num_players": raw.pop("num_players")}
        for name, j in raw.items():
            values[name] = self.game.types.decode(j, self.game._param_types[name])
        return values

    def _wrap(self, state: Any) -> CoreState:
        return CoreState(self.game, state, self._given)

    def legal_actions(self, seat: int) -> list[Action]:
        node = self.node
        decode = self.game.action_from_json
        return [decode(node, a) for a in self._s.legal_actions_json(seat)]

    def iter_legal_actions(self, seat: int) -> Iterator[Action]:
        yield from self.legal_actions(seat)

    def count_legal(self, seat: int) -> int:
        return self._s.count_legal(seat)

    def ranking(self) -> tuple[int, ...] | None:
        ranks = self._s.ranking()
        return None if ranks is None else tuple(ranks)

    def options(
        self, seat: int, name: str | None = None, args: dict[str, Any] | None = None
    ) -> list[Any]:
        from gamehub.engine.values import to_json

        given = {k: to_json(v) for k, v in (args or {}).items()}
        raw = self._s.options(seat, name, given)
        if name is None:
            return raw
        params = self.game._params.get((self.node or "", name), [])
        i = len(given)
        if i >= len(params):
            return []
        t = params[i][1]
        return [self.game.types.decode(v, t) for v in raw]

    def is_legal(self, seat: int, action: Action) -> bool:
        return self.illegal_reason(seat, action) is None

    def illegal_reason(self, seat: int, action: Action) -> str | None:
        from gamehub.engine.errors import IllegalAction

        try:
            core_action = self._s.decode_action(action.to_json())
        except IllegalAction as exc:
            return str(exc)
        return self._s.illegal_reason(seat, core_action)

    def value(self, name: str) -> Any:
        snap = self._s.snapshot()["store"][name]
        index = next(i for i, v in enumerate(self.game.ir.get("state", [])) if v["name"] == name)
        t = self.game.types.parse(self.game.ir["state"][index]["type"])
        return _from_snapshot(self.game.types, snap, t)

    def evaluate(self, expr: Any, **locals_: Any) -> Any:
        raise NotImplementedError("evaluate solo existe en el motor de referencia")

    def edited(self, stmts: list[Any], **locals_: Any) -> CoreState:
        raise NotImplementedError("edited solo existe en el motor de referencia")

    # --- transiciones -------------------------------------------------------------------------

    def apply_action(self, seat: int, action: Action) -> CoreState:
        core_action = self._s.decode_action(action.to_json())
        return self._wrap(self._s.apply_action(seat, core_action))

    def chance_outcomes(self, limit: int = 100_000) -> list[tuple[tuple[int, ...], Fraction]]:
        return [(o, Fraction(n, d)) for o, (n, d) in self._s.chance_outcomes(limit)]

    def sample_chance(self, rng: Pcg32) -> tuple[int, ...]:
        outcome, state = self._s.sample_chance(rng.state, rng.inc)
        rng.state = state
        return outcome

    def apply_chance(self, outcome: tuple[int, ...] | list[int]) -> CoreState:
        return self._wrap(self._s.apply_chance(tuple(outcome)))

    def outcome_probability(self, outcome: tuple[int, ...]) -> Fraction:
        n, d = self._s.outcome_probability(tuple(outcome))
        return Fraction(n, d)

    # --- información --------------------------------------------------------------------------

    def view(self, seat: int | None) -> dict[str, Any]:
        return self._s.view(seat)

    def events(self, seat: int | None) -> list[dict[str, Any]]:
        return self._s.events(seat)

    def snapshot(self) -> dict[str, Any]:
        return self._s.snapshot()

    def digest(self) -> str:
        return self._s.digest()

    def information_state(self, seat: int) -> str:
        return self._s.information_state(seat)

    def decode_action(self, seat: int, data: dict[str, Any]) -> Action:
        return self.game.decode_action(self.node, data)

    @property
    def step(self) -> Step:
        raw = self._s.step()
        kind = raw["kind"]
        if kind == "action":
            action = self.game.action_from_json(self._parent_node(), raw["action"])
            return Step("action", raw["seat"], action, events=self._events())
        if kind == "chance":
            return Step("chance", outcome=tuple(raw["outcome"]), events=self._events())
        return Step(kind, events=self._events())

    def _parent_node(self) -> str | None:
        parent = self._s.parent()
        return None if parent is None else parent.node

    def _events(self) -> tuple[Event, ...]:
        """Los eventos del paso con lo que ve cada asiento (como `Step.events`)."""
        return tuple(Event(full, seen, pub) for full, seen, pub in self._s.step_events())

    def history(self) -> list[Step]:
        return [s.step for s in self.path()]

    def path(self) -> list[CoreState]:
        states: list[CoreState] = []
        current = self._s
        while current is not None:
            states.append(self._wrap(current))
            current = current.parent()
        return states[::-1]


def _from_snapshot(types: TypeTable, snap: Any, t: Type) -> Any:
    from gamehub.engine.values import Grid, Zone, ZoneItem

    if t.kind in ("zone", "bag"):
        up = set(snap.get("face_up", []))
        items = tuple(
            ZoneItem(types.decode(v, t.inner), i in up) for i, v in enumerate(snap["items"])
        )
        return Zone(items, ordered=t.kind == "zone")
    if t.kind in ("list", "per_player"):
        return tuple(_from_snapshot(types, x, t.inner) for x in snap)
    if t.kind == "grid":
        cells = tuple(types.decode(x, t.inner) for row in snap for x in row)
        return Grid(len(snap[0]) if snap else 0, len(snap), cells)
    return types.decode(snap, t)


# --- Partidas aleatorias en C++ ----------------------------------------------------------------


def core_fuzz(
    game: Game | CoreGame,
    games: int,
    *,
    seed: int = 0,
    num_players: int | None = None,
    params: dict[str, Any] | None = None,
    max_steps: int = 10_000,
    jobs: int = 1,
) -> Any:
    """Las mismas partidas que `gamehub.engine.match.fuzz` (semillas `seed + i`), jugadas en C++
    sin eventos ni historial. Con `jobs` > 1, en hilos (cada uno con su copia del juego; el C++
    suelta el GIL). Devuelve un `FuzzReport`."""
    import time
    from concurrent.futures import ThreadPoolExecutor

    from gamehub.engine.match import FuzzReport

    core = _require()
    ir_text = json.dumps(game.ir, ensure_ascii=False)
    n = num_players or game.players[0]
    jobs = max(1, min(jobs, games or 1))
    size = -(-games // jobs) if games else 0
    chunks = [(seed + k * size, min(size, games - k * size)) for k in range(jobs)]
    chunks = [(s, g) for s, g in chunks if g > 0]
    started = time.perf_counter()

    def run(chunk: tuple[int, int]) -> dict[str, Any]:
        local = core.Game(ir_text)
        return local.playouts(n, params or {}, chunk[0], chunk[1], max_steps)

    if len(chunks) == 1:
        results = [run(chunks[0])]
    else:
        with ThreadPoolExecutor(len(chunks)) as ex:
            results = list(ex.map(run, chunks))
    report = FuzzReport(payoff_sums=[Fraction(0)] * n)
    for r in results:
        report.games += r["games"]
        report.completed += r["completed"]
        report.truncated += r["truncated"]
        report.total_steps += r["steps"]
        report.errors.extend((s, m) for s, m in r["errors"])
        report.payoff_sums = [
            a + Fraction(num, den)
            for a, (num, den) in zip(report.payoff_sums, r["payoff_sums"], strict=True)
        ]
    report.errors.sort()
    report.seconds = time.perf_counter() - started
    return report
