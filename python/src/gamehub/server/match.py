# SPDX-License-Identifier: Apache-2.0
"""Una partida en el servidor: el estado del motor, las actualizaciones numeradas, los turnos,
los relojes, el azar verificable y el resultado.

**Actualizaciones.** Cada entrada (una acción, una jugada por plazo vencido o un bot) produce una
actualización (`Batch`) con número `seq` consecutivo desde 0: la acción y todo el azar que la sigue
hasta la siguiente decisión o el final. La actualización 0 es la preparación. Cada destinatario
recibe la vista final y los eventos de esos pasos tal como él los ve.

**Turnos.** El turno de un asiento empieza en la primera actualización en que puede actuar y dura
mientras siga pudiendo, sin haber actuado y sin que se llegue a ningún nodo (en un nodo simultáneo
o una ventana, que otro responda no cambia tu turno). Un `act` con `seq` anterior al comienzo del
turno vigente se rechaza (`stale_seq`): se decidió viendo un estado que ya no es el de ese turno.
Los relojes cuentan por turnos.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import islice
from typing import Any

from gamehub.engine import PASS, Action, Game, IllegalAction, State, Status
from gamehub.engine.fairness import block, derive_seed
from gamehub.engine.replay import record, step_json
from gamehub.engine.rng import STREAM_CHANCE, STREAM_SERVER, Pcg32
from gamehub.engine.values import to_json
from gamehub.server.clock import Clock

#: Máximo de acciones legales que se enumeran en una actualización (por encima, progresivas).
MAX_ENUMERATED = 20_000


@dataclass(frozen=True)
class Batch:
    """Una actualización: los estados `states[first..last]` y cuándo se produjo."""

    seq: int
    first: int
    last: int
    at: float


@dataclass(frozen=True)
class Rejection:
    reason: str  # illegal_action | stale_seq | not_your_turn | not_running
    detail: str


@dataclass(frozen=True)
class Ending:
    reason: str  # terminal | forfeit | aborted
    payoffs: list[Any] | None
    ranking: list[int]
    forfeited: list[int]


class Match:
    def __init__(
        self,
        game: Game,
        n: int,
        params: dict[str, Any],
        *,
        match_id: str,
        number: int,
        server_seed: str,
        client_seeds: list[str],
        clock: dict[str, Any],
        now: float,
    ) -> None:
        self.game = game
        self.n = n
        self.id = match_id
        self.number = number
        self.server_seed = server_seed
        self.client_seeds = list(client_seeds)
        self.seed = derive_seed(server_seed, self.client_seeds)
        self.clock_spec = clock
        self.clock = Clock(clock, n)
        self.server_rng = Pcg32(self.seed, STREAM_SERVER)
        self._chance = Pcg32(self.seed, STREAM_CHANCE)
        self.states: list[State] = [game.new_state(n, params)]
        self.params = {
            k: to_json(v) for k, v in self.states[0].params.items() if k != "num_players"
        }
        self.batches: list[Batch] = []
        self.turns: dict[int, int] = {}
        self.forfeited: list[int] = []
        self.ending: Ending | None = None
        self._advance()
        self._close(0, now, actor=None)

    # --- consulta -------------------------------------------------------------------------------

    @property
    def state(self) -> State:
        return self.states[-1]

    @property
    def seq(self) -> int:
        return self.batches[-1].seq

    @property
    def running(self) -> bool:
        return self.ending is None

    def active(self) -> tuple[int, ...]:
        return self.state.active_seats if self.running else ()

    def update(
        self, observer: int | None, batch: Batch, *, now: float, legal_limit: int | None = None
    ) -> dict[str, Any]:
        """Datos de un mensaje `update` para un observador (asiento, `PUBLIC` o `None` =
        omnisciente). Las acciones legales y los relojes solo van en la última actualización;
        `legal_limit=None` = sin acciones legales."""
        states = self.states[batch.first : batch.last + 1]
        data: dict[str, Any] = {
            "seq": batch.seq,
            "view": states[-1].view(observer),
            "events": [e for st in states for e in st.events(observer)],
        }
        latest = batch is self.batches[-1]
        if latest and legal_limit is not None and observer in self.active():
            assert observer is not None
            data["legal"] = self.legal(observer, legal_limit)
        clocks = self.clock.snapshot(now) if latest and self.running else None
        if clocks is not None:
            data["clocks"] = clocks
        return data

    def snapshot(
        self, observer: int | None, *, now: float, legal_limit: int | None = None
    ) -> dict[str, Any]:
        """La última actualización sin sus eventos (para quien llega o vuelve)."""
        data = self.update(observer, self.batches[-1], now=now, legal_limit=legal_limit)
        data["events"] = []
        return data

    def legal(self, seat: int, limit: int) -> dict[str, Any]:
        limit = max(0, min(limit, MAX_ENUMERATED))
        found = list(islice(self.state.iter_legal_actions(seat), limit + 1))
        if len(found) <= limit:
            return {"kind": "enumerated", "actions": [a.to_json() for a in found]}
        return {"kind": "progressive", "names": list(self.state.options(seat))}

    def options(self, seat: int, name: str | None, args: dict[str, Any] | None) -> list[Any]:
        """Construcción progresiva (`query_actions`). Lanza `IllegalAction` si los argumentos no
        son de la acción."""
        if seat not in self.active():
            return []
        if name is None:
            return list(self.state.options(seat))
        if name == "pass":
            return []
        typed = self.game.decode_arguments(self.state.node, name, args or {})
        return [to_json(v) for v in self.state.options(seat, name, typed)]

    def deadlines(self) -> dict[int, float]:
        return self.clock.deadlines() if self.running else {}

    # --- jugadas --------------------------------------------------------------------------------

    def act(self, seat: int, seq: int, data: dict[str, Any], now: float) -> Rejection | Batch:
        """Una jugada de un cliente: comprueba turno, `seq` y legalidad, y la aplica."""
        if not self.running:
            return Rejection("not_running", "la partida ha terminado")
        if seq > self.seq:
            return Rejection(
                "stale_seq", f"la actualización {seq} no existe (la última es {self.seq})"
            )
        if seat not in self.active():
            return Rejection("not_your_turn", f"el asiento {seat} no puede actuar ahora")
        since = self.turns.get(seat, self.seq)
        if seq < since:
            return Rejection(
                "stale_seq",
                f"tu turno empezó en la actualización {since} y la jugada se decidió en la {seq}",
            )
        try:
            action = self.state.decode_action(seat, data)
        except IllegalAction as exc:
            return Rejection("illegal_action", str(exc))
        reason = self.state.illegal_reason(seat, action)
        if reason is not None:
            return Rejection("illegal_action", reason)
        return self.apply(seat, action, now)

    def apply(self, seat: int, action: Action, now: float) -> Batch:
        """Aplica una jugada legal (de un cliente, de un bot o por plazo vencido)."""
        first = len(self.states)
        self.states.append(self.state.apply_action(seat, action))
        self._advance()
        return self._close(first, now, actor=seat)

    def random_action(self, seat: int, *, prefer_pass: bool = False) -> Action:
        """Una jugada legal al azar (flujo del servidor de PCG32), o pasar si se puede."""
        legal = self.state.legal_actions(seat)
        if prefer_pass and PASS in legal:
            return PASS
        return legal[self.server_rng.below(len(legal))]

    def forfeit(self, seat: int, now: float) -> bool:
        """El asiento abandona: queda el último. Si solo queda uno, la partida termina. Devuelve
        si ha terminado."""
        if not self.running or seat in self.forfeited:
            return False
        self.forfeited.append(seat)
        if self.n - len(self.forfeited) <= 1:
            self._finish("forfeit", now)
            return True
        return False

    def abort(self, now: float) -> None:
        if self.running:
            self._finish("aborted", now)

    # --- resultado y replay ---------------------------------------------------------------------

    def fairness(self, *, reveal: bool) -> dict[str, Any]:
        data = block(self.server_seed, self.client_seeds, reveal=reveal)
        if reveal:
            data["seed"] = self.seed
        return data

    def steps(self, start: int = 0) -> list[dict[str, Any]]:
        """Pasos del replay desde el índice `start` (0 = el primero tras la preparación)."""
        return [step_json(st) for st in self.states[start + 1 :]]

    def replay(self, players: list[dict[str, Any]]) -> dict[str, Any]:
        data = record(self.state, self.seed, game=self.game)
        data["players"] = players
        data["fairness"] = self.fairness(reveal=not self.running)
        if self.ending is not None:
            result = data.setdefault("result", {})
            result.update(
                reason=self.ending.reason,
                ranking=self.ending.ranking,
                forfeited=self.ending.forfeited,
            )
        return data

    # --- internos -------------------------------------------------------------------------------

    def _advance(self) -> None:
        while self.state.status is Status.CHANCE:
            self.states.append(self.state.apply_chance(self.state.sample_chance(self._chance)))

    def _close(self, first: int, now: float, *, actor: int | None) -> Batch:
        batch = Batch(len(self.batches), first, len(self.states) - 1, now)
        self.batches.append(batch)
        if self.state.is_terminal:
            self._finish("terminal", now)
        else:
            self._turns(batch, actor, now)
        return batch

    def _turns(self, batch: Batch, actor: int | None, now: float) -> None:
        arrived = any(
            e.full.get("type") == "node"
            for st in self.states[batch.first : batch.last + 1]
            for e in st.step.events
        )
        active = set(self.state.active_seats)
        for seat in list(self.turns):
            if seat == actor or seat not in active or arrived:
                del self.turns[seat]
                self.clock.stop(seat, now, acted=seat == actor)
        for seat in sorted(active - set(self.turns)):
            self.turns[seat] = batch.seq
            self.clock.start(seat, now)

    def _finish(self, reason: str, now: float) -> None:
        payoffs: list[Any] | None = None
        base: tuple[int, ...] | None = None
        if reason == "terminal":
            assert self.state.payoffs is not None
            payoffs = [to_json(p) for p in self.state.payoffs]
            base = self.state.ranking()
        self.ending = Ending(
            reason, payoffs, final_ranking(self.n, base, self.forfeited), [*self.forfeited]
        )
        for seat in list(self.turns):
            self.clock.stop(seat, now, acted=False)
        self.turns.clear()


def final_ranking(n: int, base: tuple[int, ...] | None, forfeited: list[int]) -> list[int]:
    """Puestos finales: quienes no abandonaron, según el puesto del motor (o empatados en el 1.º
    si no lo hay); después quienes abandonaron, el último en abandonar antes."""
    alive = [s for s in range(n) if s not in forfeited]
    ranks = [0] * n
    for s in alive:
        ranks[s] = 1 + sum(1 for t in alive if base is not None and base[t] < base[s])
    for place, s in enumerate(reversed(forfeited), start=len(alive) + 1):
        ranks[s] = place
    return ranks
