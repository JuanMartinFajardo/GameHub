# SPDX-License-Identifier: Apache-2.0
"""La arena (ADR-085): torneos entre bots con valoraciones por hash de reglas.

    result = run_arena(game, [load_entrant("greedy"), load_entrant("mcts:seconds=0.05")],
                       tournament="round-robin", games=20)
    print(result.table())

- **Formatos**: todos contra todos (cada mesa de n participantes distintos; si hay menos que
  asientos, se repiten), suizo (rondas que emparejan a quienes van igualados) y gauntlet (el
  primero contra cada uno de los demás).
- **Partidas espejo**: con `mirror`, cada semilla se juega con todas las rotaciones de asientos
  de la mesa, con el mismo azar (PCG32(semilla, 1)): la suerte del reparto se reparte.
- **Valoraciones**: Elo (máxima verosimilitud), Glicko-2 (una ronda por lote) y TrueSkill (n
  jugadores), siempre **por hash de reglas**: una base de datos JSON (`--db`) acumula las
  partidas de cada versión de las reglas por separado.
- Los bots del núcleo juegan en C++ en hilos (`gamehub_core.play_bots`, sin el GIL); si hay un
  bot de Python, la partida se juega con `play_match` y ese bot en su proceso.
"""

from __future__ import annotations

import itertools
import json
import os
import threading
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any

from gamehub.bots.package import Entrant
from gamehub.bots.ratings import Result, elo, glicko2, trueskill

TOURNAMENTS = ("round-robin", "swiss", "gauntlet")


@dataclass
class MatchRecord:
    """Una partida de la arena. `ranking`: el puesto de cada asiento desde 0 (el motor los da
    desde 1)."""

    players: tuple[str, ...]  # el participante de cada asiento
    seed: int
    payoffs: tuple[float, ...] = ()
    ranking: tuple[int, ...] = ()
    steps: int = 0
    seconds: tuple[float, ...] = ()
    error: str | None = None
    truncated: bool = False
    failures: tuple[str, ...] = ()  # fallos de bots en su proceso

    @property
    def ok(self) -> bool:
        return self.error is None and not self.truncated and bool(self.ranking)

    def result(self) -> Result:
        return Result(self.players, self.ranking)


@dataclass
class Standing:
    name: str
    matches: int = 0
    payoff: float = 0.0  # pago medio
    firsts: float = 0.0  # proporción de partidas en primer puesto (empates incluidos)
    rank: float = 0.0  # puesto medio (0 = primero)
    elo: float = 1500.0
    glicko: float = 1500.0
    glicko_rd: float = 350.0
    mu: float = 25.0
    sigma: float = 25 / 3
    seconds: float = 0.0  # tiempo medio pensando por partida

    @property
    def conservative(self) -> float:
        return self.mu - 3 * self.sigma


@dataclass
class ArenaResult:
    game: str
    rules_hash: str
    players: int
    tournament: str
    entrants: list[str]
    matches: list[MatchRecord] = field(default_factory=list)

    def standings(self, history: Sequence[MatchRecord] = ()) -> list[Standing]:
        """La clasificación (con las partidas anteriores de `history`, de las mismas reglas,
        para las valoraciones)."""
        everything = [*history, *self.matches]
        good = [m for m in everything if m.ok]
        results = [m.result() for m in good]
        elos = elo(results)
        periods: dict[int, list[Result]] = {}
        for m in good:
            periods.setdefault(m.seed, []).append(m.result())
        glickos = glicko2(periods[k] for k in sorted(periods))
        skills = trueskill(results)
        table: dict[str, Standing] = {}
        for name in dict.fromkeys([*self.entrants, *(p for m in good for p in m.players)]):
            table[name] = Standing(name)
        for m in good:
            seen: set[str] = set()
            for seat, name in enumerate(m.players):
                s = table[name]
                s.matches += 1
                s.payoff += m.payoffs[seat]
                s.rank += m.ranking[seat]
                s.firsts += 1 if m.ranking[seat] == 0 else 0
                if name not in seen and m.seconds:
                    s.seconds += sum(m.seconds[k] for k, p in enumerate(m.players) if p == name)
                seen.add(name)
        for s in table.values():
            if s.matches:
                s.payoff /= s.matches
                s.rank /= s.matches
                s.firsts /= s.matches
                s.seconds /= s.matches
            s.elo = elos.get(s.name, 1500.0)
            if s.name in glickos:
                s.glicko, s.glicko_rd = glickos[s.name].rating, glickos[s.name].rd
            if s.name in skills:
                s.mu, s.sigma = skills[s.name].mu, skills[s.name].sigma
        return sorted(table.values(), key=lambda s: (-s.elo, -s.payoff))

    def table(self, history: Sequence[MatchRecord] = ()) -> str:
        rows = self.standings(history)
        errors = [m for m in self.matches if not m.ok]
        lines = [
            "(1.º = partidas en primer puesto, empates incluidos)",
            f"{self.game} · {self.players} jugadores · {self.tournament} · "
            f"{len(self.matches)} partidas · reglas {self.rules_hash[:19]}…",
            "",
            f"{'':3}{'bot':<40}{'partidas':>9}{'pago':>9}{'1.º':>7}{'Elo':>7}"
            f"{'Glicko-2':>13}{'TrueSkill':>17}",
        ]
        for i, s in enumerate(rows, 1):
            lines.append(
                f"{i:<3}{s.name[:39]:<40}{s.matches:>9}{s.payoff:>9.3f}{s.firsts:>7.0%}"
                f"{s.elo:>7.0f}{s.glicko:>8.0f} ±{s.glicko_rd:<3.0f}"
                f"{s.mu:>8.2f} ±{s.sigma:.2f} ({s.conservative:5.1f})"
            )
        if errors:
            lines.append("")
            lines.append(f"{len(errors)} partidas sin terminar o con errores de reglas")
            for m in errors[:5]:
                lines.append(f"  semilla {m.seed}: {m.error or 'truncada'}")
        failures = [f for m in self.matches for f in m.failures]
        if failures:
            lines.append(f"{len(failures)} fallos de bots en su proceso (siguieron al azar)")
        return "\n".join(lines)

    def to_json(self, history: Sequence[MatchRecord] = ()) -> dict[str, Any]:
        return {
            "game": self.game,
            "rules_hash": self.rules_hash,
            "players": self.players,
            "tournament": self.tournament,
            "entrants": self.entrants,
            "standings": [
                {**asdict(s), "conservative": s.conservative} for s in self.standings(history)
            ],
            "matches": [asdict(m) for m in self.matches],
        }


# --- Calendario ----------------------------------------------------------------------------------


def tables_round_robin(names: Sequence[str], n: int) -> list[tuple[str, ...]]:
    if len(names) >= n:
        return list(itertools.combinations(names, n))
    return [tuple(names[k % len(names)] for k in range(n))]


def tables_gauntlet(names: Sequence[str], n: int) -> list[tuple[str, ...]]:
    champion, rest = names[0], list(names[1:])
    if not rest:
        raise ValueError("el gauntlet necesita al menos dos participantes")
    if n == 2:
        return [(champion, r) for r in rest]
    groups = [rest[i : i + n - 1] for i in range(0, len(rest), n - 1)]
    return [(champion, *(g[k % len(g)] for k in range(n - 1))) for g in groups]


def seatings(
    table: tuple[str, ...], games: int, mirror: bool, first_seed: int
) -> list[tuple[tuple[str, ...], int]]:
    """Las partidas de una mesa: con espejo, cada semilla con todas las rotaciones; si no, una
    rotación distinta por semilla."""
    n = len(table)
    out = []
    for g in range(games):
        seed = first_seed + g
        rotations = range(n) if mirror else [g % n]
        for r in rotations:
            out.append((table[r:] + table[:r], seed))
    return out


# --- Ejecución -----------------------------------------------------------------------------------


def _number(x: Any) -> float:
    return float(Fraction(x)) if isinstance(x, str) else float(x)


class _Runner:
    def __init__(
        self,
        game: Any,
        entrants: dict[str, Entrant],
        n: int,
        params: dict[str, Any],
        max_steps: int,
    ) -> None:
        from gamehub.engine.core import CoreGame, core_game

        self.game = game
        self.core = game if isinstance(game, CoreGame) else core_game(game)
        self.entrants = entrants
        self.n = n
        self.params = params
        self.max_steps = max_steps
        # Un juego del núcleo por hilo: sus cachés (memo estático, rejillas) no se comparten.
        self.local = threading.local()

    def thread_core(self) -> Any:
        found = getattr(self.local, "core", None)
        if found is None:
            from gamehub.engine.core import CoreGame

            found = self.local.core = CoreGame(self.core.ir, check=False)
        return found

    def play(self, players: tuple[str, ...], seed: int) -> MatchRecord:
        record = MatchRecord(players=players, seed=seed)
        entrants = [self.entrants[p] for p in players]
        if all(e.is_core for e in entrants):
            specs = [dict(e.spec or {}) for e in entrants]
            r = _play_bots(
                self.thread_core().core, self.n, self.params, specs, seed, self.max_steps
            )
            record.steps = r["steps"]
            record.truncated = r["truncated"]
            record.seconds = tuple(r["seconds"])
            record.error = r["error"]
            if "payoffs" in r:
                record.payoffs = tuple(_number(x) for x in r["payoffs"])
                record.ranking = tuple(x - 1 for x in r["ranking"])  # 0 = primero
            return record
        return self._play_python(record, entrants)

    def _play_python(self, record: MatchRecord, entrants: list[Entrant]) -> MatchRecord:
        import time

        from gamehub.bots.agents import make_bot
        from gamehub.bots.sandbox import SandboxedAgent
        from gamehub.engine.errors import RuleError
        from gamehub.engine.match import Observation, play_match

        agents: list[Any] = []
        for seat, e in enumerate(entrants):
            if e.python is not None:
                agents.append(
                    SandboxedAgent(e.python, self.core.ir, seat, limits=e.limits, seed=record.seed)
                )
            else:
                spec = e.spec or {"kind": "random"}
                agents.append(make_bot(self.thread_core(), spec, seat, record.seed))
        seconds = [0.0] * self.n

        class Timed:
            def __init__(self, seat: int) -> None:
                self.seat = seat

            def act(self, observation: Observation, legal: Any) -> Any:
                started = time.perf_counter()
                try:
                    return agents[self.seat].act(observation, legal)
                finally:
                    seconds[self.seat] += time.perf_counter() - started

        try:
            result = play_match(
                self.thread_core(),
                [Timed(s) for s in range(self.n)],
                seed=record.seed,
                num_players=self.n,
                params=self.params,
                max_steps=self.max_steps,
            )
            record.steps = result.steps
            record.truncated = result.truncated
            if not result.truncated:
                record.payoffs = tuple(float(x) for x in result.state.payoffs or ())
                record.ranking = tuple(x - 1 for x in result.state.ranking() or ())
        except RuleError as exc:
            record.error = str(exc)
        finally:
            for a in agents:
                if isinstance(a, SandboxedAgent):
                    record.failures += tuple(a.report.failures)
                    a.close()
        record.seconds = tuple(seconds)
        return record


def _play_bots(
    core: Any,
    n: int,
    params: dict[str, Any],
    specs: list[dict[str, Any]],
    seed: int,
    max_steps: int,
) -> dict[str, Any]:
    import gamehub_core  # pyright: ignore[reportMissingImports]

    return gamehub_core.play_bots(core, n, params, specs, seed=seed, max_steps=max_steps)


def run_arena(
    game: Any,
    entrants: Sequence[Entrant],
    *,
    num_players: int | None = None,
    params: dict[str, Any] | None = None,
    tournament: str = "round-robin",
    games: int = 10,
    mirror: bool = True,
    rounds: int | None = None,
    seed: int = 0,
    jobs: int | None = None,
    max_steps: int = 100_000,
    progress: Callable[[MatchRecord], None] | None = None,
) -> ArenaResult:
    if tournament not in TOURNAMENTS:
        raise ValueError(f"formato desconocido: {tournament} (hay: {', '.join(TOURNAMENTS)})")
    names = [e.name for e in entrants]
    if len(set(names)) != len(names):
        raise ValueError("dos participantes con el mismo nombre (ponles nombre: fuerte=…)")
    for e in entrants:
        e.check(game.id, game.rules_hash)
    n = num_players or game.players[0]
    runner = _Runner(game, {e.name: e for e in entrants}, n, params or {}, max_steps)
    result = ArenaResult(game.id, game.rules_hash, n, tournament, names)
    workers = jobs or max(1, (os.cpu_count() or 2) - 1)

    def play_all(schedule: list[tuple[tuple[str, ...], int]]) -> list[MatchRecord]:
        with ThreadPoolExecutor(workers) as pool:
            records = []
            for record in pool.map(lambda job: runner.play(*job), schedule):
                if progress is not None:
                    progress(record)
                records.append(record)
        return records

    if tournament == "swiss":
        total_rounds = rounds or max(3, (len(names) - 1).bit_length() + 2)
        for r in range(total_rounds):
            order = [s.name for s in result.standings()] if r else list(names)
            tables = [
                tuple(order[(i + k) % len(order)] for k in range(n))
                for i in range(0, len(order), n)
            ]
            schedule = [
                job
                for t, table in enumerate(tables)
                for job in seatings(table, games, mirror, seed + 1000 * r + 100 * t)
            ]
            result.matches += play_all(schedule)
        return result
    tables = tables_gauntlet(names, n) if tournament == "gauntlet" else tables_round_robin(names, n)
    schedule = [job for table in tables for job in seatings(table, games, mirror, seed)]
    result.matches = play_all(schedule)
    return result


# --- Base de datos por hash de reglas ------------------------------------------------------------


def load_history(db: Path, rules_hash: str) -> list[MatchRecord]:
    if not db.exists():
        return []
    data = json.loads(db.read_text(encoding="utf-8"))
    return [_record(m) for m in data.get(rules_hash, {}).get("matches", [])]


def save_history(db: Path, result: ArenaResult) -> None:
    data = json.loads(db.read_text(encoding="utf-8")) if db.exists() else {}
    entry = data.setdefault(result.rules_hash, {"game": result.game, "matches": []})
    entry["matches"] += [asdict(m) for m in result.matches]
    db.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def _record(m: dict[str, Any]) -> MatchRecord:
    return MatchRecord(
        players=tuple(m["players"]),
        seed=m["seed"],
        payoffs=tuple(m.get("payoffs", ())),
        ranking=tuple(m.get("ranking", ())),
        steps=m.get("steps", 0),
        seconds=tuple(m.get("seconds", ())),
        error=m.get("error"),
        truncated=m.get("truncated", False),
        failures=tuple(m.get("failures", ())),
    )
