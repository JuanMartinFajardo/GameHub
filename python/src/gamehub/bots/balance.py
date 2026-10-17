# SPDX-License-Identifier: Apache-2.0
"""Análisis de balance (ADR-087): «¿está equilibrado mi juego?», con partidas entre bots.

    report = balance(game, BalanceOptions(games=200))
    print(report.markdown())
    print(compare(old_report, new_report).markdown())    # Balance CI

Métricas (heuristics-and-ai.md §4), todas de partidas entre bots del núcleo C++:

- **Ventaja por asiento**: `games` partidas del bot de referencia contra sí mismo; pago medio y
  proporción de primeros puestos de cada asiento, con su intervalo del 95 %.
- **Tablas y duración**: partidas con empate en cabeza; pasos y decisiones por partida.
- **Perfil de ramificación**: acciones legales por decisión, por décimas de la partida, y
  decisiones forzadas.
- **Habilidad frente a suerte**: el bot de referencia contra bots al azar (asientos rotados):
  cuánto supera lo que daría la suerte (1/n).
- **Cadena de habilidad**: una escalera de bots cada vez más fuertes; cuántos peldaños ganan al
  anterior con significación.
- **Cambios de líder y decisión**: con la evaluación de la heurística de cada asiento tras cada
  paso, cuántas veces cambia quién va primero y desde qué punto el ganador ya no deja de serlo.
- **Estrategias dominantes**: acciones que, cuando se usan, disparan las victorias.
- **Cobertura de reglas**: acciones y transiciones de la IR que no aparecen en ninguna partida.
- **Kingmaking** (n ≥ 3): decisiones de quien ya no puede ganar que cambian quién gana
  (`gamehub_core.kingmaking`).
"""

from __future__ import annotations

import itertools
import math
import os
import statistics
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from fractions import Fraction
from typing import Any

from gamehub.bots.agents import bot_label, parse_bot_spec

DEFAULT_LADDER = (
    "random",
    "greedy",
    "mcts:iterations=100,seconds=0",
    "mcts:iterations=400,seconds=0",
    "mcts:iterations=1600,seconds=0",
)


@dataclass
class BalanceOptions:
    bot: str = "greedy"  # el bot de referencia (autojuego)
    weak: str = "random"  # el bot de la suerte
    games: int = 200
    num_players: int | None = None
    params: dict[str, Any] = field(default_factory=dict)
    seed: int = 0
    jobs: int | None = None
    ladder: Sequence[str] = DEFAULT_LADDER
    ladder_games: int = 60
    kingmaking_games: int = 10
    heuristic: str | None = None  # la de la evaluación (la primera del juego si no se da)
    max_steps: int = 100_000


@dataclass
class Interval:
    value: float
    low: float
    high: float

    @staticmethod
    def proportion(successes: float, n: int) -> Interval:
        """Wilson al 95 %."""
        if n == 0:
            return Interval(0.0, 0.0, 1.0)
        z = 1.96
        p = successes / n
        center = (p + z * z / (2 * n)) / (1 + z * z / n)
        half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
        return Interval(p, max(0.0, center - half), min(1.0, center + half))

    @staticmethod
    def mean(values: Sequence[float]) -> Interval:
        if not values:
            return Interval(0.0, 0.0, 0.0)
        m = statistics.fmean(values)
        if len(values) < 2:
            return Interval(m, m, m)
        half = 1.96 * statistics.stdev(values) / math.sqrt(len(values))
        return Interval(m, m - half, m + half)

    def __str__(self) -> str:
        return f"{self.value:.3f} [{self.low:.3f}, {self.high:.3f}]"


@dataclass
class SeatStats:
    seat: int
    payoff: Interval
    first: Interval  # proporción de primeros puestos (con empates)


@dataclass
class LadderStep:
    bot: str
    against: str
    score: Interval  # proporción de primeros puestos del bot nuevo
    significant: bool


@dataclass
class ActionStats:
    action: str
    uses: int
    win_rate_when_used: float
    lift: float  # frente a la proporción de victorias media


@dataclass
class BalanceReport:
    game: str
    rules_hash: str
    players: int
    bot: str
    games: int
    seats: list[SeatStats] = field(default_factory=list)
    seat_advantage: bool = False  # ¿algún asiento se sale del reparto justo?
    draw_rate: float = 0.0
    length: dict[str, float] = field(default_factory=dict)
    branching: dict[str, Any] = field(default_factory=dict)
    skill: dict[str, Any] = field(default_factory=dict)
    ladder: list[LadderStep] = field(default_factory=list)
    chain_depth: int = 0
    tension: dict[str, Any] = field(default_factory=dict)
    actions: list[ActionStats] = field(default_factory=list)
    dominant: list[str] = field(default_factory=list)
    uncovered: dict[str, list[str]] = field(default_factory=dict)
    kingmaking: dict[str, Any] | None = None
    errors: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    def markdown(self) -> str:
        n = self.players
        lines = [
            f"# Balance de {self.game}",
            "",
            f"Reglas `{self.rules_hash}` · {n} jugadores · bot de referencia `{self.bot}` · "
            f"{self.games} partidas.",
            "",
            "## Ventaja por asiento",
            "",
            "| Asiento | Pago medio [IC 95 %] | Primer puesto [IC 95 %] |",
            "|---:|---|---|",
        ]
        for s in self.seats:
            lines.append(f"| {s.seat} | {s.payoff} | {s.first} |")
        fair = 1 / n
        lines += [
            "",
            (
                f"**Hay ventaja de asiento**: algún intervalo de primeros puestos no incluye "
                f"{fair:.3f} (1/n)."
                if self.seat_advantage
                else f"Ningún asiento se aleja con significación del reparto justo ({fair:.3f})."
            ),
            "",
            "## Tablas y duración",
            "",
            f"- Tablas (empate en cabeza): {self.draw_rate:.1%}",
            f"- Pasos por partida: media {self.length.get('mean', 0):.1f}, mediana "
            f"{self.length.get('median', 0):.0f}, p10–p90 {self.length.get('p10', 0):.0f}–"
            f"{self.length.get('p90', 0):.0f}",
            f"- Decisiones por partida: {self.length.get('decisions', 0):.1f}",
            "",
            "## Perfil de ramificación",
            "",
            f"- Acciones legales por decisión: {self.branching.get('mean', 0):.1f} de media; "
            f"decisiones forzadas (una sola acción): {self.branching.get('forced', 0):.1%}",
            "- Por décimas de la partida: "
            + " · ".join(f"{x:.1f}" for x in self.branching.get("profile", [])),
            "",
            "## Habilidad frente a suerte",
            "",
            f"- `{self.skill.get('strong')}` contra `{self.skill.get('weak')}`: primer puesto en "
            f"{self.skill.get('strong_first', Interval(0, 0, 0))} (la suerte daría {fair:.3f}).",
            f"- Peso de la habilidad: {self.skill.get('skill_share', 0):.2f} (0 = pura suerte, "
            "1 = el mejor gana siempre).",
            "",
            "## Cadena de habilidad",
            "",
            "| Peldaño | Contra | Primer puesto [IC 95 %] | ¿Mejora? |",
            "|---|---|---|---|",
        ]
        for step in self.ladder:
            lines.append(
                f"| `{step.bot}` | `{step.against}` | {step.score} | "
                f"{'sí' if step.significant else 'no'} |"
            )
        lines += [
            "",
            f"Profundidad de la cadena: **{self.chain_depth}** peldaños con mejora significativa.",
            "",
            "## Tensión",
            "",
        ]
        if self.tension:
            lines += [
                f"- Cambios de líder por partida (según `{self.tension['heuristic']}`): "
                f"{self.tension['lead_changes']:.2f}",
                f"- El ganador va primero sin interrupción desde el "
                f"{self.tension['decided_at']:.0%} de la partida (de media).",
            ]
        else:
            lines.append("- Sin heurística con evaluación: no se mide.")
        lines += ["", "## Acciones", "", "| Acción | Usos | Victorias al usarla | Diferencia |"]
        lines.append("|---|---:|---:|---:|")
        for a in self.actions:
            lines.append(
                f"| `{a.action}` | {a.uses} | {a.win_rate_when_used:.1%} | {a.lift:+.1%} |"
            )
        if self.dominant:
            lines += ["", "**Posibles estrategias dominantes**: " + ", ".join(self.dominant)]
        lines += ["", "## Cobertura de reglas", ""]
        missing = sum(len(v) for v in self.uncovered.values())
        if not missing:
            lines.append("Todas las acciones y transiciones aparecen en alguna partida.")
        for kind, names in self.uncovered.items():
            if names:
                lines.append(f"- {kind} sin usar: " + ", ".join(f"`{x}`" for x in names))
        if self.kingmaking is not None:
            k = self.kingmaking
            lines += [
                "",
                "## Kingmaking",
                "",
                f"- {k['events']} de {k['probes']} decisiones examinadas al final de "
                f"{k['games']} partidas ({k['rate']:.1%}): quien ya no podía ganar decidió "
                "quién ganaba.",
            ]
        if self.errors:
            lines += ["", "## Errores", ""] + [f"- {e}" for e in self.errors[:10]]
        return "\n".join(lines) + "\n"


# --- Partidas ------------------------------------------------------------------------------------


class _Matches:
    """Partidas entre bots en el núcleo, en hilos (un juego del núcleo por hilo)."""

    def __init__(self, game: Any, options: BalanceOptions, n: int) -> None:
        import threading

        self.ir = game.ir
        self.options = options
        self.n = n
        self.local = threading.local()
        self.workers = options.jobs or max(1, (os.cpu_count() or 2) - 1)

    def core(self) -> Any:
        found = getattr(self.local, "core", None)
        if found is None:
            from gamehub.engine.core import CoreGame

            found = self.local.core = CoreGame(self.ir, check=False).core
        return found

    def play(
        self, jobs: Sequence[tuple[list[str], int]], *, trace: bool = False, eval: str = ""
    ) -> list[dict[str, Any]]:
        import gamehub_core  # pyright: ignore[reportMissingImports]

        def one(job: tuple[list[str], int]) -> dict[str, Any]:
            specs, seed = job
            r = gamehub_core.play_bots(
                self.core(),
                self.n,
                self.options.params,
                [parse_bot_spec(s) for s in specs],
                seed=seed,
                max_steps=self.options.max_steps,
                trace=trace,
                eval=eval,
            )
            r["specs"] = specs
            return r

        with ThreadPoolExecutor(self.workers) as pool:
            return list(pool.map(one, jobs))


def _number(x: Any) -> float:
    return float(Fraction(x)) if isinstance(x, str) else float(x)


def _firsts(ranking: Sequence[int]) -> list[int]:
    """Los asientos en primer puesto (el motor numera los puestos desde 1)."""
    return [k for k, r in enumerate(ranking) if r == 1]


# --- Análisis -------------------------------------------------------------------------------------


def balance(
    game: Any, options: BalanceOptions | None = None, progress: Callable[[str], None] | None = None
) -> BalanceReport:
    options = options or BalanceOptions()
    say = progress or (lambda text: None)
    n = options.num_players or game.players[0]
    heuristics = [h["name"] for h in game.ir.get("heuristics", [])]
    evaluator = options.heuristic or next(
        (h["name"] for h in game.ir.get("heuristics", []) if h.get("features")), ""
    )
    if evaluator and evaluator not in heuristics:
        raise ValueError(f"el juego no tiene la heurística {evaluator}")
    report = BalanceReport(game.id, game.rules_hash, n, bot_label(options.bot), options.games)
    m = _Matches(game, options, n)

    # 1. Autojuego del bot de referencia, con trazas.
    say(f"autojuego: {options.games} partidas de {options.bot}")
    selfplay = m.play(
        [([options.bot] * n, options.seed + k) for k in range(options.games)],
        trace=True,
        eval=evaluator,
    )
    finished = [r for r in selfplay if r.get("payoffs") is not None and not r["truncated"]]
    report.errors += [
        f"semilla {options.seed + k}: {r['error']}" for k, r in enumerate(selfplay) if r["error"]
    ]
    _seats(report, finished, n)
    _length_and_branching(report, finished)
    if evaluator:
        _tension(report, finished, evaluator)
    _actions(report, finished)
    covered = list(selfplay)

    # 2. Habilidad frente a suerte: el de referencia contra el débil, rotando su asiento.
    say(f"habilidad: {options.bot} contra {options.weak}")
    jobs = []
    for k in range(options.games):
        seat = k % n
        specs = [options.weak] * n
        specs[seat] = options.bot
        jobs.append((specs, options.seed + 10_000 + k))
    duel = m.play(jobs, trace=True)
    wins = 0.0
    played = 0
    for (specs, _), r in zip(jobs, duel, strict=True):
        if r.get("ranking") is None:
            continue
        seat = specs.index(options.bot)
        firsts = _firsts(r["ranking"])
        wins += 1 / len(firsts) if seat in firsts else 0
        played += 1
    strong = Interval.proportion(wins, played)
    _coverage(report, game.ir, [*covered, *duel])
    report.skill = {
        "strong": bot_label(options.bot),
        "weak": bot_label(options.weak),
        "strong_first": strong,
        "skill_share": (strong.value - 1 / n) / (1 - 1 / n),
    }

    # 3. Cadena de habilidad.
    ladder = list(options.ladder)
    for prev, cur in itertools.pairwise(ladder):
        say(f"cadena: {cur} contra {prev}")
        jobs = []
        for k in range(options.ladder_games):
            seat = k % n
            specs = [prev] * n
            specs[seat] = cur
            jobs.append((specs, options.seed + 20_000 + k))
        results = m.play(jobs)
        wins, played = 0.0, 0
        for (specs, _), r in zip(jobs, results, strict=True):
            if r.get("ranking") is None:
                continue
            firsts = _firsts(r["ranking"])
            seat = specs.index(cur)
            wins += 1 / len(firsts) if seat in firsts else 0
            played += 1
        score = Interval.proportion(wins, played)
        report.ladder.append(LadderStep(bot_label(cur), bot_label(prev), score, score.low > 1 / n))
    report.chain_depth = sum(1 for s in report.ladder if s.significant)

    # 4. Kingmaking.
    if n >= 3 and options.kingmaking_games > 0:
        import gamehub_core  # pyright: ignore[reportMissingImports]

        say(f"kingmaking: {options.kingmaking_games} partidas")
        probes = events = 0
        for k in range(options.kingmaking_games):
            r = gamehub_core.kingmaking(
                m.core(),
                n,
                options.params,
                [parse_bot_spec(options.bot)] * n,
                seed=options.seed + 30_000 + k,
            )
            probes += r["probes"]
            events += r["events"]
        report.kingmaking = {
            "games": options.kingmaking_games,
            "probes": probes,
            "events": events,
            "rate": events / probes if probes else 0.0,
        }
    return report


def _seats(report: BalanceReport, finished: list[dict[str, Any]], n: int) -> None:
    for seat in range(n):
        payoffs = [_number(r["payoffs"][seat]) for r in finished]
        firsts = 0.0
        for r in finished:
            top = _firsts(r["ranking"])
            firsts += 1 / len(top) if seat in top else 0
        report.seats.append(
            SeatStats(seat, Interval.mean(payoffs), Interval.proportion(firsts, len(finished)))
        )
    fair = 1 / n
    report.seat_advantage = any(not (s.first.low <= fair <= s.first.high) for s in report.seats)
    report.draw_rate = (
        sum(1 for r in finished if len(_firsts(r["ranking"])) > 1) / len(finished)
        if finished
        else 0
    )


def _length_and_branching(report: BalanceReport, finished: list[dict[str, Any]]) -> None:
    if not finished:
        return
    lengths = sorted(r["steps"] for r in finished)
    decisions = [sum(1 for st in r["trace"] if st[0] >= 0) for r in finished]
    report.length = {
        "mean": statistics.fmean(lengths),
        "median": statistics.median(lengths),
        "p10": lengths[len(lengths) // 10],
        "p90": lengths[min(len(lengths) - 1, 9 * len(lengths) // 10)],
        "decisions": statistics.fmean(decisions),
    }
    legal: list[int] = []
    bins: list[list[int]] = [[] for _ in range(10)]
    for r in finished:
        steps = [st for st in r["trace"] if st[0] >= 0]
        for i, st in enumerate(steps):
            legal.append(st[1])
            bins[min(9, 10 * i // max(1, len(steps)))].append(st[1])
    report.branching = {
        "mean": statistics.fmean(legal) if legal else 0.0,
        "forced": sum(1 for x in legal if x == 1) / len(legal) if legal else 0.0,
        "profile": [statistics.fmean(b) if b else 0.0 for b in bins],
    }


def _tension(report: BalanceReport, finished: list[dict[str, Any]], heuristic: str) -> None:
    changes: list[int] = []
    decided: list[float] = []
    for r in finished:
        leaders = []
        for st in r["trace"]:
            if st[3]:
                best = max(st[3])
                top = [k for k, v in enumerate(st[3]) if v == best]
                leaders.append(top[0] if len(top) == 1 else -1)
        if not leaders:
            continue
        changes.append(sum(1 for a, b in itertools.pairwise(leaders) if a != b))
        winners = _firsts(r["ranking"])
        if len(winners) != 1:
            continue
        w = winners[0]
        k = len(leaders)
        while k > 0 and leaders[k - 1] == w:
            k -= 1
        decided.append(k / len(leaders))
    report.tension = {
        "heuristic": heuristic,
        "lead_changes": statistics.fmean(changes) if changes else 0.0,
        "decided_at": statistics.fmean(decided) if decided else 1.0,
    }


def _actions(report: BalanceReport, finished: list[dict[str, Any]]) -> None:
    uses: dict[str, int] = {}
    wins_when: dict[str, float] = {}
    users: dict[str, int] = {}
    total_first = 0.0
    total_seats = 0
    for r in finished:
        top = _firsts(r["ranking"])
        n = len(r["ranking"])
        total_first += 1
        total_seats += n
        used: dict[tuple[int, str], bool] = {}
        for st in r["trace"]:
            if st[0] >= 0:
                uses[st[2]] = uses.get(st[2], 0) + 1
                used[(st[0], st[2])] = True
        for seat, action in used:
            users[action] = users.get(action, 0) + 1
            if seat in top:
                wins_when[action] = wins_when.get(action, 0.0) + 1 / len(top)
    base = total_first / total_seats if total_seats else 0.0
    for action in sorted(uses):
        rate = wins_when.get(action, 0.0) / users[action] if users.get(action) else 0.0
        report.actions.append(ActionStats(action, uses[action], rate, rate - base))
    report.dominant = [
        a.action for a in report.actions if a.lift > 0.25 and users.get(a.action, 0) >= 20
    ]


def ir_elements(ir: dict[str, Any]) -> dict[str, list[str]]:
    """Las acciones y transiciones de la IR, con las claves de las trazas del núcleo."""
    actions: list[str] = []
    transitions: list[str] = []

    def walk(nodes: list[dict[str, Any]]) -> None:
        for node in nodes:
            for i, _ in enumerate(node.get("transitions", [])):
                transitions.append(f"node/{node['id']}/{i}")
            for a in node.get("actions", []):
                actions.append(a["name"])
                for i, _ in enumerate(a.get("transitions", [])):
                    transitions.append(f"action/{node['id']}/{a['name']}/{i}")
            if node["kind"] == "phase":
                walk(node["nodes"])

    walk(ir["flow"]["nodes"])
    return {"acciones": sorted(set(actions)), "transiciones": transitions}


def _coverage(report: BalanceReport, ir: dict[str, Any], matches: list[dict[str, Any]]) -> None:
    elements = ir_elements(ir)
    seen_actions = {st[2] for r in matches for st in r.get("trace", []) if st[0] >= 0}
    seen_transitions = {t for r in matches for t in r.get("transitions", [])}
    report.uncovered = {
        "acciones": [a for a in elements["acciones"] if a not in seen_actions],
        "transiciones": [t for t in elements["transiciones"] if t not in seen_transitions],
    }


# --- Balance CI -----------------------------------------------------------------------------------


@dataclass
class Change:
    metric: str
    before: str
    after: str
    regression: bool
    note: str = ""


@dataclass
class Comparison:
    game: str
    before: str  # hashes de reglas
    after: str
    changes: list[Change] = field(default_factory=list)

    @property
    def regressions(self) -> list[Change]:
        return [c for c in self.changes if c.regression]

    def markdown(self) -> str:
        lines = [
            f"# Balance CI: {self.game}",
            "",
            f"`{self.before[:19]}…` → `{self.after[:19]}…`",
            "",
            "| Métrica | Antes | Después | |",
            "|---|---|---|---|",
        ]
        for c in self.changes:
            mark = "⚠️ " + c.note if c.regression else c.note
            lines.append(f"| {c.metric} | {c.before} | {c.after} | {mark} |")
        lines.append("")
        lines.append(
            f"**{len(self.regressions)} empeoramientos.**"
            if self.regressions
            else "Sin empeoramientos de balance."
        )
        return "\n".join(lines) + "\n"


def compare(before: BalanceReport, after: BalanceReport) -> Comparison:
    """Compara dos versiones de un juego con las mismas opciones: marca como empeoramiento una
    ventaja de asiento que aparece o crece con significación, más tablas o partidas mucho más
    largas, menos peso de la habilidad o una cadena más corta, reglas que dejan de usarse, una
    estrategia dominante nueva y más kingmaking."""
    out = Comparison(before.game, before.rules_hash, after.rules_hash)
    n = after.players

    def spread(r: BalanceReport) -> float:
        return max(abs(s.first.value - 1 / n) for s in r.seats) if r.seats else 0.0

    s0, s1 = spread(before), spread(after)
    out.changes.append(
        Change(
            "Ventaja máxima de un asiento",
            f"{s0:.3f}",
            f"{s1:.3f}",
            after.seat_advantage and s1 > s0 + 0.03,
            "aparece una ventaja de asiento significativa" if after.seat_advantage else "",
        )
    )
    out.changes.append(
        Change(
            "Tablas",
            f"{before.draw_rate:.1%}",
            f"{after.draw_rate:.1%}",
            after.draw_rate > before.draw_rate + 0.05,
        )
    )
    l0, l1 = before.length.get("mean", 0.0), after.length.get("mean", 0.0)
    out.changes.append(
        Change("Pasos por partida", f"{l0:.1f}", f"{l1:.1f}", l0 > 0 and l1 > 1.25 * l0)
    )
    k0, k1 = before.skill.get("skill_share", 0.0), after.skill.get("skill_share", 0.0)
    out.changes.append(Change("Peso de la habilidad", f"{k0:.2f}", f"{k1:.2f}", k1 < k0 - 0.1))
    out.changes.append(
        Change(
            "Profundidad de la cadena",
            str(before.chain_depth),
            str(after.chain_depth),
            after.chain_depth < before.chain_depth,
        )
    )
    new_uncovered = sorted(
        {x for v in after.uncovered.values() for x in v}
        - {x for v in before.uncovered.values() for x in v}
    )
    out.changes.append(
        Change(
            "Reglas sin usar",
            str(sum(len(v) for v in before.uncovered.values())),
            str(sum(len(v) for v in after.uncovered.values())),
            bool(new_uncovered),
            ", ".join(new_uncovered[:5]),
        )
    )
    new_dominant = sorted(set(after.dominant) - set(before.dominant))
    out.changes.append(
        Change(
            "Estrategias dominantes",
            ", ".join(before.dominant) or "—",
            ", ".join(after.dominant) or "—",
            bool(new_dominant),
        )
    )
    if before.kingmaking is not None and after.kingmaking is not None:
        r0, r1 = before.kingmaking["rate"], after.kingmaking["rate"]
        out.changes.append(Change("Kingmaking", f"{r0:.1%}", f"{r1:.1%}", r1 > r0 + 0.05))
    return out
