# SPDX-License-Identifier: Apache-2.0
"""Ejecución de los bloques `test` e `invariant` de un juego compilado (`gamehub test`).

Semántica de un test (referencia en docs/wiki/language.md):

- `players`, `params` y `seed` configuran la partida y van al principio. Por defecto: el mínimo
  de jugadores, los valores por defecto de los parámetros y la semilla 0.
- Antes de cada paso, el azar pendiente se resuelve con PCG32(semilla). `chance [r, …]` y
  `chance where c` lo resuelven de forma explícita: con ese resultado, o con uno que cumpla `c`
  (si hay varios, se elige con la semilla según su probabilidad).
- `play a(), 1: b()`: cada acción la hace el asiento indicado o, si no se indica, el único
  asiento que puede actuar.
- `expect c` exige que `c` se cumpla; en `c` (y en los argumentos de las acciones) existen
  `payoff` (los pagos, solo en un estado terminal) y `active` (los asientos que pueden actuar).
- `expect legal a()` / `expect illegal a()`.
- `set x = v` cambia el estado a mano. Desde ese momento el test no comprueba los invariantes:
  el estado puede no ser alcanzable jugando.
- Los invariantes se comprueban en cada estado que alcanza el test y en partidas aleatorias.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

from gamehub.engine.errors import EngineError, NotEnumerable, RuleError
from gamehub.engine.game import Game
from gamehub.engine.match import Observation, RandomAgent
from gamehub.engine.rng import STREAM_CHANCE, Pcg32
from gamehub.engine.state import PASS, Action, State, Status
from gamehub.engine.values import (
    EnumValue,
    Grid,
    MapValue,
    SetValue,
    StructValue,
    Zone,
    to_json,
)
from gamehub.lang.decompile import expression_text
from gamehub.lang.diagnostics import Diagnostic, Label, Severity
from gamehub.lang.model import ActionCall, CompiledGame, Invariant, TestCase, TestStep
from gamehub.lang.printer import decimal_text, quote
from gamehub.lang.source import Span

DEFAULT_SEED = 0
#: Resultados de azar que `chance where` enumera antes de pasar a probar al azar.
ENUMERATION_LIMIT = 10_000
#: Intentos al azar de `chance where` cuando no se pueden enumerar los resultados.
REJECTION_TRIES = 10_000
#: Pasos máximos de una partida aleatoria de comprobación de invariantes.
PLAYOUT_MAX_STEPS = 10_000

COMPARISONS = {"eq": "==", "ne": "!=", "lt": "<", "le": "<=", "gt": ">", "ge": ">="}


class TestFailure(Exception):
    """Un test no se cumple; `diagnostic` lo explica con la posición del paso."""

    __test__ = False

    def __init__(self, diagnostic: Diagnostic) -> None:
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic


@dataclass
class TestResult:
    __test__ = False

    name: str
    span: Span
    failure: Diagnostic | None = None

    @property
    def ok(self) -> bool:
        return self.failure is None


@dataclass
class PlayoutReport:
    """Invariantes comprobados en partidas aleatorias (y la suma de los pagos de cada final:
    si es siempre la misma, el juego parece de suma constante)."""

    playouts: int = 0
    states: int = 0
    failure: Diagnostic | None = None
    payoff_sums: set[Fraction] = field(default_factory=set)


@dataclass
class GameReport:
    name: str
    tests: list[TestResult] = field(default_factory=list)
    invariants: int = 0
    playouts: PlayoutReport = field(default_factory=PlayoutReport)

    @property
    def failures(self) -> int:
        return sum(not t.ok for t in self.tests) + (self.playouts.failure is not None)


class GameTester:
    """Ejecuta los tests y comprueba los invariantes de un juego compilado."""

    __test__ = False

    def __init__(self, compiled: CompiledGame) -> None:
        self.compiled = compiled
        self.game = Game(compiled.ir)
        compile_expr = self.game.defn.exprs.compile
        self.invariants: list[tuple[Invariant, Callable[..., Any]]] = [
            (inv, compile_expr(inv.expr)) for inv in compiled.invariants
        ]

    def run_all(
        self, playouts: int = 0, seed: int = DEFAULT_SEED, select: str | None = None
    ) -> GameReport:
        report = GameReport(self.compiled.name, invariants=len(self.invariants))
        for case in self.compiled.tests:
            if select is None or select.lower() in case.name.lower():
                report.tests.append(self.run(case))
        if playouts:
            report.playouts = self.playouts(playouts, seed)
        return report

    def run(self, case: TestCase) -> TestResult:
        try:
            _TestRun(self, case).execute()
        except TestFailure as failure:
            return TestResult(case.name, case.span, failure.diagnostic)
        return TestResult(case.name, case.span)

    # --- invariantes ----------------------------------------------------------------------------

    def violated(self, state: State) -> tuple[Invariant, str] | None:
        """Primer invariante que no se cumple en el estado, con la explicación."""
        for inv, compiled in self.invariants:
            try:
                ok = state.evaluate(compiled)
            except EngineError as exc:
                return inv, f"no se puede evaluar: {exc}"
            if ok is not True:
                return inv, self.explain(state, inv.expr, {})
        return None

    def playouts(self, count: int, seed: int = DEFAULT_SEED) -> PlayoutReport:
        """Partidas aleatorias (la i-ésima con la semilla `seed + i` y, por turnos, cada número
        de jugadores admitido) comprobando los invariantes en cada estado."""
        report = PlayoutReport()
        lo, hi = self.game.players
        for i in range(count):
            n = lo + i % (hi - lo + 1)
            match_seed = seed + i
            where = f"partida aleatoria con semilla {match_seed} y {n} jugadores"
            try:
                state = self.game.new_state(n)
            except EngineError as exc:
                report.failure = Diagnostic(
                    Severity.ERROR,
                    "E614",
                    f"no se puede crear una {where}: {exc}",
                    [Label(self.compiled.span)],
                )
                return report
            chance = Pcg32(match_seed, STREAM_CHANCE)
            agents = [RandomAgent(match_seed, s) for s in range(n)]
            steps = 0
            while True:
                report.states += 1
                problem = self.violated(state)
                if problem is not None:
                    inv, explanation = problem
                    report.failure = self.invariant_failure(
                        inv, explanation, state, [f"{where}, tras {steps} pasos{_last_step(state)}"]
                    )
                    return report
                if state.payoffs is not None:
                    report.payoff_sums.add(Fraction(sum(state.payoffs)))
                    break
                if steps >= PLAYOUT_MAX_STEPS:
                    break
                try:
                    if state.status is Status.CHANCE:
                        state = state.apply_chance(state.sample_chance(chance))
                    else:
                        seat = state.active_seats[0]
                        legal = state.legal_actions(seat)
                        action = agents[seat].act(Observation(state, seat), legal)
                        state = state.apply_action(seat, action)
                except RuleError as exc:
                    report.failure = Diagnostic(
                        Severity.ERROR,
                        "E614",
                        f"error de las reglas en una {where}: {exc}",
                        [Label(self.compiled.span)],
                        notes=[f"tras {steps} pasos{_last_step(state)}"],
                    )
                    return report
                steps += 1
            report.playouts += 1
        return report

    def invariant_failure(
        self, inv: Invariant, explanation: str, state: State, notes: list[str]
    ) -> Diagnostic:
        title = f"invariante incumplido: {inv.label}" if inv.label else "invariante incumplido"
        notes = [*notes, describe_state(state)]
        return Diagnostic(Severity.ERROR, "E613", title, [Label(inv.span, explanation)], notes)

    # --- explicaciones --------------------------------------------------------------------------

    def text(self, expr: Any) -> str:
        return expression_text(self.compiled.ir, expr)

    def explain(self, state: State, expr: Any, locals_: dict[str, Any]) -> str:
        """Por qué una condición no se cumple: la primera parte de un `and` que falla y, si es
        una comparación, el valor de cada lado."""
        op = expr[0] if isinstance(expr, list) and expr else None
        if op == "and":
            for part in expr[1:]:
                if state.evaluate(part, **locals_) is not True:
                    return self.explain(state, part, locals_)
        text = f"`{self.text(expr)}`"
        if op in COMPARISONS or op == "contains":
            shown = []
            sides = expr[1:] if op in COMPARISONS else [expr[2], expr[1]]
            for side in sides:
                value = show_value(state.evaluate(side, **locals_))
                if value != self.text(side):
                    shown.append(f"`{self.text(side)}` vale {value}")
            if shown:
                return f"{text} es falso: {' y '.join(shown)}"
        return f"{text} es falso"


class _TestRun:
    """Una ejecución de un test: el estado actual y la fuente de azar."""

    def __init__(self, tester: GameTester, case: TestCase) -> None:
        self.tester = tester
        self.case = case
        self.rng = Pcg32(DEFAULT_SEED, STREAM_CHANCE)
        self.state: State | None = None
        self.edited = False

    @property
    def current(self) -> State:
        assert self.state is not None
        return self.state

    def execute(self) -> None:
        steps = self.case.steps
        i = 0
        while i < len(steps) and steps[i].kind in ("players", "params", "seed"):
            i += 1
        self.start(steps[:i])
        for step in steps[i:]:
            self.step(step)

    # --- preparación ----------------------------------------------------------------------------

    def start(self, config: list[TestStep]) -> None:
        game = self.tester.game
        n = game.players[0]
        seed = DEFAULT_SEED
        entries: dict[str, Any] = {}
        span = self.case.span
        for step in config:
            if step.kind == "players":
                n = step.value
            elif step.kind == "seed":
                seed = step.value
            else:
                entries.update(step.entries)
                span = step.span
        try:
            base = State.initial(game.defn, n, {})
            params = {name: to_json(base.evaluate(e)) for name, e in entries.items()}
            self.state = game.new_state(n, params)
        except EngineError as exc:
            raise self.fail(span, f"no se puede crear la partida: {exc}", code="E614") from None
        self.rng = Pcg32(seed, STREAM_CHANCE)
        self.check_invariants(span)

    # --- pasos ----------------------------------------------------------------------------------

    def step(self, step: TestStep) -> None:
        match step.kind:
            case "chance":
                self.chance(step)
            case "play":
                for call in step.actions:
                    self.settle(call.span)
                    self.play(call)
            case "expect":
                self.settle(step.span)
                self.expect(step)
            case "legal" | "illegal":
                self.settle(step.span)
                self.legality(step)
            case "set":
                self.settle(step.span)
                self.set(step)
            case _:
                raise self.fail(step.span, f"'{step.kind}' va al principio del test", code="E614")

    def settle(self, span: Span) -> None:
        """Resuelve el azar pendiente con la semilla del test."""
        while self.current.status is Status.CHANCE:
            try:
                state = self.current
                self.state = state.apply_chance(state.sample_chance(self.rng))
            except RuleError as exc:
                raise self.fail(
                    span, f"error de las reglas al resolver el azar: {exc}", code="E614"
                ) from None
            self.check_invariants(span)

    def chance(self, step: TestStep) -> None:
        state = self.current
        if state.status is not Status.CHANCE:
            raise self.fail(
                step.span, "no hay azar pendiente", code="E612", note=describe_state(state)
            )
        if step.target is None:
            outcome = self.value(step.value, step.span)
            try:
                self.state = state.apply_chance(tuple(outcome))
            except EngineError as exc:
                raise self.fail(
                    step.span, f"resultado de azar no válido: {exc}", code="E612"
                ) from None
        else:
            self.state = self.conditioned(step)
        self.check_invariants(step.span)

    def conditioned(self, step: TestStep) -> State:
        """`chance where c`: un resultado que cumpla `c`, elegido con la semilla según su
        probabilidad (es decir, con la probabilidad condicionada a `c`)."""
        state = self.current
        try:
            outcomes = state.chance_outcomes(limit=ENUMERATION_LIMIT)
        except NotEnumerable:
            for _ in range(REJECTION_TRIES):
                candidate = state.apply_chance(state.sample_chance(self.rng))
                if self.holds(step.target, candidate, step.span):
                    return candidate
            raise self.fail(
                step.span,
                "no se encontró ningún resultado del azar que cumpla la condición",
                code="E612",
                note=f"hay demasiados para enumerarlos y se probaron {REJECTION_TRIES} al azar",
            ) from None
        matches: list[tuple[State, Fraction]] = []
        for outcome, probability in outcomes:
            candidate = state.apply_chance(outcome)
            if self.holds(step.target, candidate, step.span):
                matches.append((candidate, probability))
        if not matches:
            raise self.fail(
                step.span,
                "ningún resultado del azar cumple la condición",
                code="E612",
                note=(
                    "hay un único resultado posible"
                    if len(outcomes) == 1
                    else f"hay {len(outcomes)} resultados posibles"
                ),
            )
        return _pick(matches, self.rng)

    def play(self, call: ActionCall) -> None:
        state = self.current
        shown = self.call_text(call)
        if state.is_terminal:
            raise self.fail(call.span, f"la partida ya ha terminado: no se puede jugar {shown}")
        seat = self.seat(call, call.span)
        if seat is None:
            raise self.fail(call.span, f"ningún asiento puede jugar {shown} ahora")
        action = self.action(call, seat)
        if action is None:
            raise self.fail(
                call.span,
                f"{call.name} no es una acción de {state.node}",
                note=self.legal_note(seat),
            )
        reason = state.illegal_reason(seat, action)
        if reason is not None:
            raise self.fail(
                call.span,
                f"jugada ilegal del asiento {seat}: {shown}",
                label=reason,
                note=self.legal_note(seat),
            )
        try:
            self.state = state.apply_action(seat, action)
        except RuleError as exc:
            raise self.fail(
                call.span, f"error de las reglas al jugar {shown}: {exc}", code="E614"
            ) from None
        self.check_invariants(call.span)

    def expect(self, step: TestStep) -> None:
        state = self.current
        if self.value(step.value, step.span) is not True:
            locals_ = self.locals(state)
            raise self.fail(
                step.span,
                "no se cumple lo esperado",
                code="E610",
                label=self.tester.explain(state, step.value, locals_),
                note=describe_state(state),
            )

    def legality(self, step: TestStep) -> None:
        state = self.current
        call = step.actions[0]
        expected = step.kind == "legal"
        seat = self.seat(call, step.span)
        if seat is None:
            reason: str | None = "ningún asiento puede actuar"
        else:
            action = self.action(call, seat)
            if action is None:
                reason = f"{call.name} no es una acción de {state.node}"
            else:
                reason = state.illegal_reason(seat, action)
        if (reason is None) == expected:
            return
        shown = self.call_text(call)
        if expected:
            raise self.fail(
                step.span,
                f"se esperaba que {shown} fuera legal",
                code="E610",
                label=reason or "",
                note=self.legal_note(seat) if seat is not None else describe_state(state),
            )
        raise self.fail(
            step.span,
            f"se esperaba que {shown} fuera ilegal, y es legal para el asiento {seat}",
            code="E610",
            note=describe_state(state),
        )

    def set(self, step: TestStep) -> None:
        state = self.current
        try:
            self.state = state.edited([["assign", step.target, step.value]], **self.locals(state))
        except EngineError as exc:
            raise self.fail(
                step.span, f"no se puede cambiar el estado: {exc}", code="E614"
            ) from None
        self.edited = True

    # --- utilidades -----------------------------------------------------------------------------

    def locals(self, state: State) -> dict[str, Any]:
        out: dict[str, Any] = {"active": state.active_seats}
        if state.payoffs is not None:
            out["payoff"] = state.payoffs
        return out

    def value(self, expr: Any, span: Span) -> Any:
        state = self.current
        if state.payoffs is None and _uses_local(expr, "payoff"):
            raise self.fail(
                span,
                "`payoff` solo tiene valor cuando la partida ha terminado",
                code="E610",
                note=describe_state(state),
            )
        try:
            return state.evaluate(expr, **self.locals(state))
        except EngineError as exc:
            raise self.fail(span, f"no se puede evaluar: {exc}", code="E614") from None

    def holds(self, expr: Any, state: State, span: Span) -> bool:
        try:
            return state.evaluate(expr, **self.locals(state)) is True
        except EngineError as exc:
            raise self.fail(span, f"no se puede evaluar la condición: {exc}", code="E614") from None

    def seat(self, call: ActionCall, span: Span) -> int | None:
        if call.seat is not None:
            return call.seat
        active = self.current.active_seats
        if len(active) > 1:
            seats = ", ".join(map(str, active))
            raise self.fail(
                span,
                f"pueden actuar varios asientos ({seats}): indica cuál",
                help=f"escribe el asiento delante de la acción: {active[0]}: {call.name}(…)",
            )
        return active[0] if active else None

    def action(self, call: ActionCall, seat: int) -> Action | None:
        """La acción del test como acción del motor (`None` si el nodo no la tiene)."""
        state = self.current
        if call.name == "pass":
            return PASS
        node = state.game.nodes.get(state.node or "")
        adef = node.actions_by_name.get(call.name) if node is not None else None
        if adef is None:
            return None
        values = [self.value(arg, call.span) for arg in call.args]
        return Action(adef.name, tuple(zip((p.name for p in adef.params), values, strict=True)))

    def call_text(self, call: ActionCall) -> str:
        args = ", ".join(self.tester.text(a) for a in call.args)
        seat = f"{call.seat}: " if call.seat is not None else ""
        return f"{seat}{call.name}({args})"

    def legal_note(self, seat: int) -> str:
        state = self.current
        legal = state.legal_actions(seat)
        if not legal:
            return f"el asiento {seat} no tiene jugadas legales; {describe_state(state)}"
        shown = ", ".join(show_action(a) for a in legal[:8])
        more = f" y {len(legal) - 8} más" if len(legal) > 8 else ""
        return f"jugadas legales del asiento {seat}: {shown}{more}"

    def check_invariants(self, span: Span) -> None:
        if self.edited:
            return
        problem = self.tester.violated(self.current)
        if problem is None:
            return
        inv, explanation = problem
        diagnostic = self.tester.invariant_failure(inv, explanation, self.current, [])
        diagnostic.with_label(span, "tras este paso")
        raise TestFailure(diagnostic)

    def fail(
        self,
        span: Span,
        message: str,
        *,
        code: str = "E611",
        label: str = "",
        note: str | None = None,
        help: str | None = None,
    ) -> TestFailure:
        """E610: no se cumple lo esperado; E611: jugada imposible; E612: azar; E614: error de
        las reglas o de evaluación (E613, invariante incumplido, lo crea `GameTester`)."""
        diagnostic = Diagnostic(Severity.ERROR, code, message, [Label(span, label)], help=help)
        if note:
            diagnostic.with_note(note)
        return TestFailure(diagnostic)


# --- presentación de valores --------------------------------------------------------------------


def show_value(v: Any, limit: int = 160) -> str:
    """Un valor del motor escrito como en Nomos (recortado a `limit` caracteres)."""
    text = _show(v)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _show(v: Any) -> str:
    if v is None:
        return "none"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, Fraction):
        if v.denominator == 1:
            return str(v.numerator)
        return decimal_text(v) or f"{v.numerator}/{v.denominator}"
    if isinstance(v, str):
        return quote(v)
    if isinstance(v, EnumValue):
        return v.name
    if isinstance(v, StructValue):
        return f"{v.type} {{ " + ", ".join(f"{k}: {_show(x)}" for k, x in v.fields) + " }"
    if isinstance(v, tuple):
        return "[" + ", ".join(_show(x) for x in v) + "]"
    if isinstance(v, SetValue):
        return "set(" + ", ".join(_show(x) for x in v.items) + ")"
    if isinstance(v, MapValue):
        return "{" + ", ".join(f"{_show(k)}: {_show(x)}" for k, x in v.items) + "}"
    if isinstance(v, Zone):
        return "[" + ", ".join(_show(x) for x in v.values()) + "]"
    if isinstance(v, Grid):
        return "[" + ", ".join(_show(row) for row in v.rows()) + "]"
    return repr(v)


def show_action(action: Action) -> str:
    return f"{action.name}({', '.join(_show(v) for _, v in action.args)})"


def describe_state(state: State) -> str:
    if state.payoffs is not None:
        return f"la partida terminó en {state.node} con pagos {show_value(state.payoffs)}"
    if state.status is Status.CHANCE:
        where = state.node or "la preparación"
        return f"la partida espera un resultado de azar ({where})"
    active = ", ".join(map(str, state.active_seats)) or "ninguno"
    return f"la partida está en {state.node}; pueden actuar: {active}"


def _last_step(state: State) -> str:
    step = state.step
    if step.kind == "action" and step.action is not None:
        return f" (último: el asiento {step.seat} jugó {show_action(step.action)})"
    if step.kind == "chance":
        return " (último: un resultado de azar)"
    return ""


def _uses_local(expr: Any, name: str) -> bool:
    if isinstance(expr, list):
        if len(expr) == 2 and expr[0] == "local" and expr[1] == name:
            return True
        return any(_uses_local(x, name) for x in expr)
    if isinstance(expr, dict):
        return any(_uses_local(x, name) for x in expr.values())
    return False


def _pick(matches: list[tuple[State, Fraction]], rng: Pcg32) -> State:
    """Elige un estado con probabilidad proporcional a su peso (exacto, con PCG32)."""
    if len(matches) == 1:
        return matches[0][0]
    denominator = math.lcm(*(p.denominator for _, p in matches))
    weights = [int(p * denominator) for _, p in matches]
    r = _below(rng, sum(weights))
    for (state, _), weight in zip(matches, weights, strict=True):
        if r < weight:
            return state
        r -= weight
    raise AssertionError


def _below(rng: Pcg32, bound: int) -> int:
    """Entero uniforme en [0, bound), también para cotas de más de 32 bits."""
    if bound <= 1 << 32:
        return rng.below(bound)
    words = (bound.bit_length() + 31) // 32
    span = 1 << (32 * words)
    limit = span - span % bound
    while True:
        x = 0
        for _ in range(words):
            x = (x << 32) | rng.next_u32()
        if x < limit:
            return x % bound
