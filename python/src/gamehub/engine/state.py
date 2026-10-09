# SPDX-License-Identifier: Apache-2.0
"""Estados inmutables y semántica operacional del flow (ver docs/wiki/motor.md).

Un `State` es una configuración del juego: valores de las variables, nodo activo, envíos
pendientes (nodos simultáneos y ventanas) y pagos si es terminal. `apply_action` y
`apply_chance` devuelven un estado **nuevo**; el anterior no cambia. Cada estado guarda el paso
que lo produjo y su padre, de modo que el historial completo es recuperable (replays,
estados de información con recuerdo perfecto).
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
from typing import Any

from gamehub.engine.env import Ctx, Env
from gamehub.engine.errors import IllegalAction, RuleError
from gamehub.engine.events import Event
from gamehub.engine.expr import boolean, iterate, num, seat
from gamehub.engine.game import ActionDef, GameDef, NodeDef, TransitionDef
from gamehub.engine.rng import Draws, Outcome, Pcg32, RngDraws, enumerate_outcomes, replay_outcome
from gamehub.engine.values import HIDDEN, Zone, norm_num, to_json
from gamehub.engine.visibility import redact
from gamehub.ir.hashing import canonical_json

#: Llegadas a nodos permitidas en un solo paso antes de declarar un bucle sin progreso.
MAX_ARRIVALS = 10_000


class Status(Enum):
    CHANCE = "chance"
    DECISION = "decision"
    TERMINAL = "terminal"


@dataclass(frozen=True, slots=True)
class Action:
    name: str
    args: tuple[tuple[str, Any], ...] = ()

    @staticmethod
    def of(name: str, **args: Any) -> Action:
        return Action(name, tuple(args.items()))

    def arg(self, name: str) -> Any:
        return dict(self.args)[name]

    def to_json(self) -> dict[str, Any]:
        return {"name": self.name, "args": {k: to_json(v) for k, v in self.args}}

    def __str__(self) -> str:
        inner = ", ".join(f"{k}={to_json(v)}" for k, v in self.args)
        return f"{self.name}({inner})"


PASS = Action("pass")


@dataclass(frozen=True, slots=True)
class Pending:
    """Asientos convocados en el nodo actual (orden de prioridad o de asiento) y envíos hechos."""

    order: tuple[int, ...]
    submitted: tuple[tuple[int, Action], ...] = ()

    def responded(self) -> set[int]:
        return {s for s, _ in self.submitted}


@dataclass(frozen=True, slots=True)
class Step:
    """Lo que llevó a un estado: preparación, acción de un asiento o resultado de azar."""

    kind: str
    seat: int | None = None
    action: Action | None = None
    outcome: Outcome | None = None
    events: tuple[Event, ...] = ()


class State:
    __slots__ = (
        "depth",
        "game",
        "n",
        "node",
        "params",
        "parent",
        "payoffs",
        "pending",
        "step",
        "store",
    )

    def __init__(
        self,
        game: GameDef,
        n: int,
        params: dict[str, Any],
        store: tuple[Any, ...],
        node: str | None,
        pending: Pending | None,
        payoffs: tuple[Any, ...] | None,
        parent: State | None,
        step: Step,
    ) -> None:
        self.game = game
        self.n = n
        self.params = params
        self.store = store
        self.node = node
        self.pending = pending
        self.payoffs = payoffs
        self.parent = parent
        self.step = step
        self.depth = 0 if parent is None else parent.depth + 1

    # --- creación -------------------------------------------------------------------------------

    @staticmethod
    def initial(game: GameDef, n: int, given: dict[str, Any]) -> State:
        params = game.initial_values(n, given)
        store = tuple(game.initial_store(n, params))
        if game.setup_is_random:
            return State(game, n, params, store, None, None, None, None, Step("start"))
        tx = _Tx(game, n, params, store, None, None)
        tx.start()
        return tx.commit(None, Step("start", events=tuple(tx.ctx.events)))

    # --- consulta -------------------------------------------------------------------------------

    @property
    def status(self) -> Status:
        if self.payoffs is not None:
            return Status.TERMINAL
        if self.node is None or self.game.nodes[self.node].kind == "chance":
            return Status.CHANCE
        return Status.DECISION

    @property
    def is_terminal(self) -> bool:
        return self.payoffs is not None

    @property
    def active_seats(self) -> tuple[int, ...]:
        if self.status is not Status.DECISION or self.pending is None:
            return ()
        node = self.game.nodes[self.node or ""]
        done = self.pending.responded()
        waiting = tuple(s for s in self.pending.order if s not in done)
        if node.kind == "window" and node.mode == "priority":
            return waiting[:1]
        return waiting

    def value(self, name: str) -> Any:
        """Valor real de una variable de estado (sin redactar: solo para depuración y tests)."""
        return self.store[self.game.var_index[name]]

    def legal_actions(self, seat_: int) -> list[Action]:
        if seat_ not in self.active_seats:
            return []
        node = self.game.nodes[self.node or ""]
        actions = list(self._enumerate(node, seat_))
        if node.kind == "window":
            actions.append(PASS)
        return actions

    def options(
        self, seat_: int, name: str | None = None, args: dict[str, Any] | None = None
    ) -> list[Any]:
        """Construcción progresiva de una acción.

        - Sin `name`: nombres de las acciones con al menos una forma legal (y `pass` en ventanas).
        - Con `name` y los primeros argumentos ya elegidos (en orden de declaración): valores del
          siguiente parámetro que admiten al menos una acción legal completa. Lista vacía si ya
          están todos.
        """
        if seat_ not in self.active_seats:
            return []
        node = self.game.nodes[self.node or ""]
        env = self._env(actor=seat_)
        if name is None:
            names = [a.name for a in node.actions if next(_complete(a, env, 0, {}), None)]
            return [*names, "pass"] if node.kind == "window" else names
        adef = node.actions_by_name.get(name)
        if adef is None:
            return []
        chosen = dict(args or {})
        i = len(chosen)
        if [p.name for p in adef.params[:i]] != list(chosen) or i >= len(adef.params):
            return []
        p = adef.params[i]
        values = iterate(p.domain(env.with_args(dict(chosen))), "dominio")
        return [v for v in values if next(_complete(adef, env, i + 1, {**chosen, p.name: v}), None)]

    def is_legal(self, seat_: int, action: Action) -> bool:
        try:
            self._canonical(seat_, action)
        except IllegalAction:
            return False
        return True

    # --- transiciones ---------------------------------------------------------------------------

    def apply_action(self, seat_: int, action: Action) -> State:
        action = self._canonical(seat_, action)
        tx = self._tx()
        tx.act(seat_, action)
        return tx.commit(self, Step("action", seat_, action, events=tuple(tx.ctx.events)))

    def chance_outcomes(self, limit: int = 100_000) -> list[tuple[Outcome, Fraction]]:
        """Resultados posibles del punto de azar actual con su probabilidad exacta."""
        self._require(Status.CHANCE)
        return enumerate_outcomes(lambda draws: self._tx(draws).run_chance(), limit)

    def sample_chance(self, rng: Pcg32) -> Outcome:
        self._require(Status.CHANCE)
        draws = RngDraws(rng)
        self._tx(draws).run_chance()
        return tuple(draws.taken)

    def apply_chance(self, outcome: Outcome) -> State:
        self._require(Status.CHANCE)
        holder: list[_Tx] = []

        def run(draws: Draws) -> None:
            tx = self._tx(draws)
            holder.append(tx)
            tx.run_chance()

        replay_outcome(run, outcome)
        tx = holder[-1]
        return tx.commit(self, Step("chance", outcome=tuple(outcome), events=tuple(tx.ctx.events)))

    # --- información ----------------------------------------------------------------------------

    def view(self, seat_: int | None) -> dict[str, Any]:
        """El estado tal como lo ve un asiento (`None` = vista omnisciente)."""
        ctx = Ctx(self.game, list(self.store), self.params, self.n, self._path())
        env = Env(ctx, viewer=seat_)
        state = {
            var.name: redact(self.store[var.index], var.type, var.policy, var.size_policy, env)
            for var in self.game.vars
        }
        view: dict[str, Any] = {
            "node": self.node,
            "status": self.status.value,
            "active": list(self.active_seats),
            "state": state,
        }
        if self.pending is not None and self.status is Status.DECISION:
            view["responded"] = sorted(self.pending.responded())
        if self.payoffs is not None:
            view["payoffs"] = [to_json(p) for p in self.payoffs]
        return view

    def snapshot(self) -> dict[str, Any]:
        """Configuración completa en JSON canónico (incluye caras de las cartas y envíos
        pendientes). Dos estados con la misma instantánea son el mismo estado."""
        store = {var.name: _snapshot_value(self.store[var.index]) for var in self.game.vars}
        snap: dict[str, Any] = {"node": self.node, "store": store}
        if self.pending is not None:
            snap["pending"] = {
                "order": list(self.pending.order),
                "submitted": [[s, a.to_json()] for s, a in self.pending.submitted],
            }
        if self.payoffs is not None:
            snap["payoffs"] = [to_json(p) for p in self.payoffs]
        return snap

    def digest(self) -> str:
        """Huella SHA-256 de la instantánea: sirve para comparar motores paso a paso."""
        return hashlib.sha256(canonical_json(self.snapshot()).encode("utf-8")).hexdigest()

    def decode_action(self, seat_: int, data: dict[str, Any]) -> Action:
        """Acción desde JSON (`{"name": …, "args": {…}}`), con los tipos de sus parámetros."""
        name = data.get("name")
        node = self.game.nodes.get(self.node or "")
        if node is None:
            raise IllegalAction("no hay acciones en este estado")
        if name == "pass" and node.kind == "window":
            return PASS
        adef = node.actions_by_name.get(name or "")
        if adef is None:
            raise IllegalAction(f"acción desconocida en {node.id}: {name}")
        given = data.get("args", {})
        try:
            args = tuple(
                (p.name, self.game.types.decode(given[p.name], p.type)) for p in adef.params
            )
        except (KeyError, ValueError) as exc:
            raise IllegalAction(f"argumentos inválidos para {name}: {exc}") from None
        return Action(adef.name, args)

    def events(self, seat_: int | None) -> list[dict[str, Any]]:
        """Eventos del último paso que ve el asiento (`None` = todos, sin redactar)."""
        return [e for e in (ev.for_seat(seat_) for ev in self.step.events) if e is not None]

    def history(self) -> list[Step]:
        steps: list[Step] = []
        state: State | None = self
        while state is not None:
            steps.append(state.step)
            state = state.parent
        return steps[::-1]

    def path(self) -> list[State]:
        states: list[State] = []
        state: State | None = self
        while state is not None:
            states.append(state)
            state = state.parent
        return states[::-1]

    def information_state(self, seat_: int) -> str:
        """Clave del conjunto de información del asiento: resumen de todo lo que ha observado
        (vistas y eventos de cada paso, incluidas sus propias acciones). Recuerdo perfecto."""
        digest = hashlib.sha256()
        for state in self.path():
            observation = {"view": state.view(seat_), "events": state.events(seat_)}
            digest.update(canonical_json(observation).encode("utf-8"))
        return digest.hexdigest()

    # --- internos -------------------------------------------------------------------------------

    def _require(self, status: Status) -> None:
        if self.status is not status:
            raise IllegalAction(f"el estado es {self.status.value}, no {status.value}")

    def _path(self) -> tuple[str, ...]:
        if self.node is None:
            return ()
        return (*self.game.nodes[self.node].ancestors, self.node)

    def _tx(self, draws: Draws | None = None) -> _Tx:
        return _Tx(self.game, self.n, self.params, self.store, self.node, self.pending, draws)

    def _env(self, **kw: Any) -> Env:
        return Env(Ctx(self.game, list(self.store), self.params, self.n, self._path()), **kw)

    def _enumerate(self, node: NodeDef, seat_: int) -> Iterator[Action]:
        for adef in node.actions:
            env = self._env(actor=seat_)
            yield from _complete(adef, env, 0, {})

    def _canonical(self, seat_: int, action: Action) -> Action:
        """Comprueba la legalidad y devuelve la acción con sus argumentos en forma canónica."""
        if self.status is not Status.DECISION:
            raise IllegalAction(f"no se puede actuar: el estado es {self.status.value}")
        if seat_ not in self.active_seats:
            raise IllegalAction(f"el asiento {seat_} no puede actuar ahora")
        node = self.game.nodes[self.node or ""]
        if node.kind == "window" and action.name == "pass":
            if action.args:
                raise IllegalAction("'pass' no lleva argumentos")
            return PASS
        adef = node.actions_by_name.get(action.name)
        if adef is None:
            raise IllegalAction(f"acción desconocida en {node.id}: {action.name}")
        given = dict(action.args)
        if set(given) != {p.name for p in adef.params}:
            raise IllegalAction(
                f"argumentos de {action.name}: se esperaba {[p.name for p in adef.params]}"
            )
        env = self._env(actor=seat_)
        args: dict[str, Any] = {}
        for p in adef.params:
            ok, value = p.member(env.with_args(dict(args)), given[p.name])
            if not ok:
                raise IllegalAction(
                    f"{action.name}: valor no permitido para {p.name}: {to_json(given[p.name])}"
                )
            args[p.name] = value
        if adef.requires is not None and not boolean(
            adef.requires(env.with_args(args)), "requires"
        ):
            raise IllegalAction(f"{action.name}: no se cumple la condición de la acción")
        return Action(action.name, tuple(args.items()))


def _snapshot_value(v: Any) -> Any:
    if isinstance(v, Zone):
        snap: dict[str, Any] = {"items": [to_json(i.value) for i in v.items]}
        up = [i for i, item in enumerate(v.items) if item.face_up]
        if up:
            snap["face_up"] = up
        return snap
    if isinstance(v, tuple):
        return [_snapshot_value(x) for x in v]
    return to_json(v)


def _complete(adef: ActionDef, env: Env, i: int, args: dict[str, Any]) -> Iterator[Action]:
    """Enumera las acciones legales de `adef`: parámetros en orden, valores en orden de dominio."""
    if i == len(adef.params):
        if adef.requires is None or boolean(adef.requires(env.with_args(args)), "requires"):
            yield Action(adef.name, tuple(args.items()))
        return
    p = adef.params[i]
    for value in iterate(p.domain(env.with_args(dict(args))), "dominio"):
        yield from _complete(adef, env, i + 1, {**args, p.name: value})


class _Tx:
    """Transacción mutable que calcula el estado siguiente. No sobrevive al paso."""

    def __init__(
        self,
        game: GameDef,
        n: int,
        params: dict[str, Any],
        store: tuple[Any, ...],
        node: str | None,
        pending: Pending | None,
        draws: Draws | None = None,
    ) -> None:
        self.game = game
        self.n = n
        self.node = node
        self.pending = pending
        self.payoffs: tuple[Any, ...] | None = None
        self.ctx = Ctx(game, list(store), params, n, draws=draws)
        self.arrivals = 0
        # Siguiente salto pendiente: ("transfer", fases_activas, destino) o ("exit", fase, None).
        # Los saltos se encadenan en un bucle (no por recursión) para admitir cadenas largas
        # de nodos automáticos.
        self._next: tuple[str, Any, Any] | None = None
        self._set_node(node)

    def commit(self, parent: State | None, step: Step) -> State:
        return State(
            self.game,
            self.n,
            self.ctx.params,
            tuple(self.ctx.store),
            self.node,
            self.pending,
            self.payoffs,
            parent,
            step,
        )

    # --- utilidades -----------------------------------------------------------------------------

    def _set_node(self, node: str | None) -> None:
        self.node = node
        self.ctx.path = () if node is None else (*self.game.nodes[node].ancestors, node)

    def env(self, **kw: Any) -> Env:
        return Env(self.ctx, **kw)

    def emit(self, payload: dict[str, Any]) -> None:
        self.ctx.events.append(Event.public(payload, self.n))

    @property
    def current(self) -> NodeDef:
        assert self.node is not None
        return self.game.nodes[self.node]

    # --- flow -----------------------------------------------------------------------------------

    def start(self) -> None:
        self.game.setup(self.env())
        self.ctx.draws = None
        self.descend(self.game.start)
        self._drain()

    def run_chance(self) -> None:
        if self.node is None:
            self.start()
            return
        node = self.current
        assert node.effects is not None
        node.effects(self.env())
        self.ctx.draws = None
        self.take([(node.transitions, self.env())], node.id)
        self._drain()

    def _drain(self) -> None:
        while self._next is not None:
            kind, a, b = self._next
            self._next = None
            if kind == "exit":
                self.exit_phase(a)
            else:
                self.transfer(a, b)

    def descend(self, node_id: str) -> None:
        node = self.game.nodes[node_id]
        while node.kind == "phase":
            self._set_node(node.id)
            if node.on_enter is not None:
                node.on_enter(self.env())
            node = self.game.nodes[node.start]
        self.arrive(node.id)

    def transfer(self, active: tuple[str, ...], target: str) -> None:
        """Sale de las fases activas que no contienen al destino y entra en las que sí."""
        chain = self.game.nodes[target].ancestors
        common = 0
        while common < min(len(active), len(chain)) and active[common] == chain[common]:
            common += 1
        for phase in reversed(active[common:]):
            self._exit_actions(phase)
        for phase in chain[common:]:
            self._set_node(phase)
            on_enter = self.game.nodes[phase].on_enter
            if on_enter is not None:
                on_enter(self.env())
        self.descend(target)

    def _exit_actions(self, phase: str) -> None:
        self._set_node(phase)
        on_exit = self.game.nodes[phase].on_exit
        if on_exit is not None:
            on_exit(self.env())

    def exit_phase(self, phase: str) -> None:
        """`$exit` desde un hijo: on_exit de la fase y después sus transiciones."""
        self._exit_actions(phase)
        self.take([(self.game.nodes[phase].transitions, self.env())], phase)

    def take(self, candidates: list[tuple[tuple[TransitionDef, ...], Env]], origin: str) -> None:
        """Primera transición aplicable (por orden de grupo y de declaración) y la sigue."""
        for transitions, env in candidates:
            for t in transitions:
                if t.when is None or boolean(t.when(env), "when"):
                    t.effects(env)
                    if t.to == "$exit":
                        parent = self.game.nodes[origin].parent
                        assert parent is not None
                        self._next = ("exit", parent, None)
                    else:
                        self._next = ("transfer", self.game.nodes[origin].ancestors, t.to)
                    return
        raise RuleError("ninguna transición aplicable", origin)

    def arrive(self, node_id: str) -> None:
        self.arrivals += 1
        if self.arrivals > MAX_ARRIVALS:
            raise RuleError(f"bucle sin progreso: más de {MAX_ARRIVALS} nodos en un paso", node_id)
        self._set_node(node_id)
        self.pending = None
        node = self.current
        self.emit({"type": "node", "node": node_id})
        env = self.env()
        match node.kind:
            case "auto":
                if node.effects is not None:
                    node.effects(env)
                self.take([(node.transitions, self.env())], node_id)
            case "chance":
                pass
            case "terminal":
                assert node.payoff is not None
                payoffs = tuple(
                    norm_num(num(x, "payoff")) for x in iterate(node.payoff(env), "payoff")
                )
                if len(payoffs) != self.n:
                    raise RuleError(
                        f"el pago tiene {len(payoffs)} valores para {self.n} asientos", node_id
                    )
                self.payoffs = payoffs
                self.emit({"type": "end", "payoffs": [to_json(p) for p in payoffs]})
            case "decision":
                assert node.actor is not None
                actor = seat(node.actor(env), self.n, "actor")
                self.pending = Pending((actor,))
                self._require_choice(node, actor)
            case "simultaneous":
                assert node.actors is not None
                actors = tuple(
                    sorted({seat(s, self.n, "actors") for s in iterate(node.actors(env))})
                )
                for s in actors:
                    self._require_choice(node, s)
                self.pending = Pending(actors)
                if not actors:
                    self.resolve_simultaneous()
            case "window":
                assert node.eligible is not None
                eligible = [seat(s, self.n, "eligible") for s in iterate(node.eligible(env))]
                preferred = (
                    [seat(s, self.n, "order") for s in iterate(node.order(env))]
                    if node.order
                    else []
                )
                order = [s for s in preferred if s in eligible]
                order += [s for s in eligible if s not in order]
                self.pending = Pending(tuple(dict.fromkeys(order)))
                if not order:
                    self.close_window(None, None)

    def _require_choice(self, node: NodeDef, actor: int) -> None:
        probe = State(
            self.game,
            self.n,
            self.ctx.params,
            tuple(self.ctx.store),
            node.id,
            Pending((actor,)),
            None,
            None,
            Step("probe"),
        )
        for _ in probe._enumerate(node, actor):
            return
        raise RuleError(f"el asiento {actor} no tiene ninguna acción legal", node.id)

    # --- acciones -------------------------------------------------------------------------------

    def act(self, actor: int, action: Action) -> None:
        node = self.current
        assert self.pending is not None
        match node.kind:
            case "decision":
                self.perform(node, actor, action)
            case "simultaneous":
                self.pending = Pending(
                    self.pending.order, (*self.pending.submitted, (actor, action))
                )
                self.emit({"type": "submitted", "seat": actor})
                if len(self.pending.submitted) == len(self.pending.order):
                    self.resolve_simultaneous()
            case "window":
                self.respond(node, actor, action)
        self._drain()

    def perform(
        self, node: NodeDef, actor: int, action: Action, *, node_transitions_actor: bool = True
    ) -> None:
        """Ejecuta una acción y sigue la transición de la acción o, si no hay, la del nodo."""
        adef = node.actions_by_name[action.name]
        env = self.env(actor=actor, args=dict(action.args))
        adef.effects(env)
        self._action_event(adef, actor, action)
        node_env = self.env(actor=actor) if node_transitions_actor else self.env()
        self.take([(adef.transitions, env), (node.transitions, node_env)], node.id)

    def resolve_simultaneous(self) -> None:
        node = self.current
        assert self.pending is not None
        for actor, action in sorted(self.pending.submitted, key=lambda sa: sa[0]):
            adef = node.actions_by_name[action.name]
            adef.effects(self.env(actor=actor, args=dict(action.args)))
            self._action_event(adef, actor, action)
        if node.resolve is not None:
            node.resolve(self.env())
        self.take([(node.transitions, self.env())], node.id)

    def respond(self, node: NodeDef, actor: int, action: Action) -> None:
        assert self.pending is not None
        submitted = (*self.pending.submitted, (actor, action))
        self.pending = Pending(self.pending.order, submitted)
        complete = len(submitted) == len(self.pending.order)
        if node.mode == "collect":
            self.emit({"type": "responded", "seat": actor})
            if not complete:
                return
            responses = dict(submitted)
            self.emit(
                {
                    "type": "responses",
                    "responses": [
                        {"seat": s, "name": responses[s].name} for s in self.pending.order
                    ],
                }
            )
            winner = next((s for s in self.pending.order if responses[s] != PASS), None)
            self.close_window(winner, None if winner is None else responses[winner])
            return
        if action == PASS:
            self.emit({"type": "action", "seat": actor, "name": "pass", "args": {}})
            if complete:
                self.close_window(None, None)
            return
        self.close_window(actor, action)

    def close_window(self, actor: int | None, action: Action | None) -> None:
        node = self.current
        if actor is None or action is None:
            self.take([(node.transitions, self.env())], node.id)
        else:
            self.perform(node, actor, action, node_transitions_actor=False)

    def _action_event(self, adef: ActionDef, actor: int, action: Action) -> None:
        full = {"type": "action", "seat": actor, **action.to_json()}
        seen: list[dict[str, Any] | None] = []
        for viewer in range(self.n):
            env = Env(self.ctx, viewer=viewer, owner=actor)
            if viewer == actor:
                seen.append(full)
            elif not adef.policy.allows(env):
                seen.append({"type": "action", "seat": actor})
            else:
                args = {}
                for p in adef.params:
                    value = action.arg(p.name)
                    if p.policy.allows(env):
                        args[p.name] = to_json(value)
                    elif p.size_policy.allows(env) and isinstance(value, tuple):
                        args[p.name] = {"size": len(value)}
                    else:
                        args[p.name] = HIDDEN
                seen.append({"type": "action", "seat": actor, "name": action.name, "args": args})
        self.ctx.events.append(Event(full, tuple(seen)))
