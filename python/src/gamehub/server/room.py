# SPDX-License-Identifier: Apache-2.0
"""Una sala: lobby, asientos, participantes, partidas, bots, plazos y espectadores.

La sala es **lógica pura**: no abre conexiones ni lee la hora. Cada operación recibe `now`
(segundos de un reloj monótono) y deja los mensajes salientes en `outbox`; la capa de transporte
(`gamehub.server.app`) los entrega a las conexiones y llama a `tick` cuando indica `next_wakeup`.
Así toda la semántica se prueba sin red y con un reloj simulado.

**Espectadores.** Ven la partida desde fuera (vista pública u omnisciente, según la sala) y con un
retardo opcional: todo lo que se les envía sale `spectator_delay` segundos después. Quien llega a
mitad recibe primero un resumen (la sala, el inicio de la partida y la última actualización) tal
como estaban hace `spectator_delay` segundos.

**Abandono.** Quien abandona (`resign`, salir a mitad de partida o `on_timeout: forfeit`) queda el
último y un bot juega por su asiento hasta el final; si solo queda un asiento sin abandonar, la
partida termina.
"""

from __future__ import annotations

import contextlib
import hashlib
import secrets
import unicodedata
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from gamehub import __version__
from gamehub.engine import PUBLIC, EngineError, Game, IllegalAction, InvalidParams
from gamehub.engine.fairness import commitment, new_server_seed, valid_client_seed
from gamehub.engine.match import Agent, FirstAgent, Observation, RandomAgent
from gamehub.protocol import message
from gamehub.server.codes import display
from gamehub.server.match import Batch, Match
from gamehub.server.settings import BOT_KINDS, Settings

#: Espectadores como máximo por sala.
MAX_SPECTATORS = 32
#: Acciones legales enumeradas por defecto en cada actualización.
DEFAULT_LEGAL_LIMIT = 256
#: Identificadores de mensaje recordados por participante (para descartar `act` repetidos).
RECENT_IDS = 64


class RoomError(Exception):
    """Una petición que no se puede atender. `code` es un código de error del protocolo."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class Recorder(Protocol):
    """Quien guarda las partidas (memoria o SQLite)."""

    def match_started(self, room: Room, match: Match) -> None: ...

    def match_progress(self, room: Room, match: Match) -> None: ...

    def match_ended(self, room: Room, match: Match) -> None: ...


class NullRecorder:
    def match_started(self, room: Room, match: Match) -> None:
        pass

    def match_progress(self, room: Room, match: Match) -> None:
        pass

    def match_ended(self, room: Room, match: Match) -> None:
        pass


@dataclass
class Outgoing:
    """Un mensaje para un participante, que sale en el instante `at`. Con `close`, la conexión se
    cierra después de enviarlo."""

    to: str
    msg: dict[str, Any]
    at: float
    close: bool = False


@dataclass
class Participant:
    id: str
    name: str
    token_hash: str
    kind: str  # human | bot (lo que declara el cliente)
    seat: int | None = None
    host: bool = False
    connected: bool = False
    ready: bool = False
    seed: str = ""
    legal_limit: int = DEFAULT_LEGAL_LIMIT
    recent: deque[str] = field(default_factory=lambda: deque(maxlen=RECENT_IDS))
    #: La cuenta del hub de quien se conectó con sesión (solo en las salas del hub).
    account: int | None = None

    @property
    def role(self) -> str:
        return "player" if self.seat is not None else "spectator"


@dataclass
class Seat:
    index: int
    participant: str | None = None
    reserved_for: str | None = None
    bot: str | None = None  # bot del servidor que ocupa el asiento
    takeover: str | None = None  # bot que juega por el asiento en esta partida

    @property
    def empty(self) -> bool:
        return self.participant is None and self.bot is None


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def clean_text(text: str, limit: int) -> str:
    """Texto visible: sin caracteres de control, con los espacios normalizados y recortado."""
    printable = "".join(c for c in text if unicodedata.category(c)[0] != "C")
    return " ".join(printable.split())[:limit]


def clean_name(text: str) -> str:
    return clean_text(text, 32)


class Room:
    def __init__(
        self,
        code: str,
        game: Game,
        *,
        settings: Settings,
        params: dict[str, Any] | None = None,
        now: float,
        recorder: Recorder | None = None,
    ) -> None:
        self.code = code
        self.game = game
        self.params: dict[str, Any] = dict(params or {})
        self._check_config(settings.players, self.params)
        self.settings = settings
        self.recorder: Recorder = recorder or NullRecorder()
        self.status = "lobby"
        self.seats = [Seat(i) for i in range(settings.players)]
        self.participants: dict[str, Participant] = {}
        self.match: Match | None = None
        self.matches = 0
        self.last: dict[str, Any] | None = None
        self.server_seed = new_server_seed()
        self.outbox: list[Outgoing] = []
        self.bots: dict[int, Agent] = {}
        self.bot_due: dict[int, float] = {}
        self.created = now
        self.touched = now
        self.match_players: list[dict[str, Any]] = []
        # Canal de espectadores: un resumen de lo ya visible y lo que aún no ha salido.
        self.keyframe: dict[str, dict[str, Any]] = {}
        self.pending: deque[tuple[float, dict[str, Any]]] = deque()

    # --- entrar y salir -------------------------------------------------------------------------

    def join(
        self,
        *,
        name: str,
        role: str,
        now: float,
        seat: int | None = None,
        kind: str = "human",
        legal_limit: int = DEFAULT_LEGAL_LIMIT,
        host: bool = False,
        connected: bool = True,
        re: str | None = None,
    ) -> tuple[Participant, str]:
        """Un participante nuevo (conectado, salvo que se cree por adelantado con
        `connected=False`, como el anfitrión de una sala creada por la API REST). Devuelve el
        participante y su token de sesión."""
        self._open()
        name = self._unique_name(clean_name(name) or "Anónimo")
        if role == "player":
            index = self._free_seat(seat, name)
        else:
            if not self.settings.spectators and not host:
                raise RoomError("not_allowed", "esta sala no admite espectadores")
            if len(self._spectators()) >= MAX_SPECTATORS:
                raise RoomError("room_full", "no caben más espectadores")
            index = None
        token = secrets.token_urlsafe(24)
        pid = secrets.token_hex(4)
        while pid in self.participants:
            pid = secrets.token_hex(4)
        p = Participant(
            pid,
            name,
            token_hash(token),
            kind,
            host=host,
            connected=connected,
            legal_limit=legal_limit,
        )
        self.participants[pid] = p
        if index is not None:
            self._seat(p, index)
        self.touched = now
        self._send(p, "joined", {"token": token, "session": self.session(p)}, now, re=re)
        self._catch_up(p, None, now)
        self._broadcast_room(now, skip=p.id)
        self._maybe_start(now)
        self.tick(now)
        return p, token

    def resume(
        self, pid: str, now: float, resume: dict[str, Any] | None = None, *, re: str | None = None
    ) -> None:
        """El participante vuelve a conectarse: recibe la sala y la partida (solo lo que le falta
        si `resume` indica la última actualización que vio)."""
        p = self._participant(pid)
        p.connected = True
        self.touched = now
        version = {"name": "gamehub", "version": __version__}
        self._send(p, "welcome", {"server": version, "session": self.session(p)}, now, re=re)
        self._catch_up(p, resume, now)
        self._broadcast_room(now, skip=p.id)
        self._maybe_start(now)
        self.tick(now)

    def disconnect(self, pid: str, now: float) -> None:
        p = self.participants.get(pid)
        if p is None or not p.connected:
            return
        p.connected = False
        self.touched = now
        self.outbox = [o for o in self.outbox if o.to != pid]
        self._broadcast_room(now)

    def leave(self, pid: str, now: float) -> None:
        """Sale de la sala: en partida, abandona; si era el anfitrión, el puesto pasa a otro."""
        p = self._participant(pid)
        self._remove(p, now)
        self._broadcast_room(now)
        self.tick(now)

    def kick(self, host_pid: str, target: str, now: float) -> None:
        self._require_host(host_pid)
        p = self._participant(target)
        if p.host:
            raise RoomError("not_allowed", "el anfitrión no puede echarse a sí mismo")
        self.outbox.append(
            Outgoing(
                p.id,
                message("error", {"code": "not_allowed", "message": "te han echado de la sala"}),
                now,
                close=True,
            )
        )
        self._remove(p, now)
        self._broadcast_room(now)
        self.tick(now)

    def close(self, now: float) -> None:
        """Cierra la sala (la partida en curso queda anulada)."""
        if self.status == "closed":
            return
        if self.match is not None and self.match.running:
            self.match.abort(now)
            self._finish_match(now)
        self.status = "closed"
        self._broadcast_room(now)

    # --- lobby ----------------------------------------------------------------------------------

    def sit(self, pid: str, seat: int | None, now: float) -> None:
        p = self._participant(pid)
        self._lobby_only()
        index = self._free_seat(seat, p.name, current=p.seat)
        if p.seat is not None:
            self.seats[p.seat].participant = None
        self._seat(p, index)
        self._broadcast_room(now)

    def stand(self, pid: str, now: float) -> None:
        p = self._participant(pid)
        self._lobby_only()
        if p.seat is not None:
            self.seats[p.seat].participant = None
            p.seat = None
            p.ready = False
        self._broadcast_room(now)

    def ready(self, pid: str, ready: bool, seed: str | None, now: float) -> None:
        p = self._participant(pid)
        self._lobby_only()
        if p.seat is None:
            raise RoomError("not_allowed", "solo los jugadores sentados se declaran listos")
        if seed is not None:
            if not valid_client_seed(seed):
                raise RoomError("bad_message", "la semilla es un texto imprimible de hasta 64")
            p.seed = seed
        p.ready = ready
        self.touched = now
        self._broadcast_room(now)
        self._maybe_start(now)
        self.tick(now)

    def configure(
        self,
        pid: str,
        now: float,
        *,
        players: int | None = None,
        params: dict[str, Any] | None = None,
        settings: dict[str, Any] | None = None,
    ) -> None:
        self._require_host(pid)
        self._lobby_only()
        new_players = self.settings.players if players is None else players
        new_params = self.params if params is None else dict(params)
        self._check_config(new_players, new_params)
        self.params = new_params
        self.settings = self.settings.patched({**(settings or {}), "players": new_players})
        if new_players < len(self.seats):
            for s in self.seats[new_players:]:
                if s.participant is not None:
                    self.participants[s.participant].seat = None
            del self.seats[new_players:]
        self.seats += [Seat(i) for i in range(len(self.seats), new_players)]
        for p in self.participants.values():
            p.ready = False
        self._broadcast_room(now)

    def set_seat(
        self,
        pid: str,
        seat: int,
        kind: str,
        now: float,
        *,
        name: str | None = None,
        bot: str | None = None,
    ) -> None:
        """Abrir un asiento, reservarlo o ponerle un bot (en partida, solo un bot, que juega por
        quien lo ocupaba)."""
        self._require_host(pid)
        self._open()
        if not 0 <= seat < len(self.seats):
            raise RoomError("not_allowed", f"no existe el asiento {seat}")
        target = self.seats[seat]
        bot_kind = bot or "random"
        if bot_kind not in BOT_KINDS:
            raise RoomError("bad_message", f"bot desconocido: {bot_kind}")
        if self.status == "running":
            if kind != "bot":
                raise RoomError("wrong_state", "en partida solo se puede poner un bot")
            if target.bot is None and target.takeover is None:
                target.takeover = bot_kind
                self._schedule_bots(now)
            self._broadcast_room(now)
            self.tick(now)
            return
        if target.participant is not None:
            occupant = self.participants[target.participant]
            occupant.seat = None
            occupant.ready = False
            target.participant = None
        reserved = (clean_name(name or "") or None) if kind == "reserved" else None
        if kind == "reserved" and reserved is None:
            raise RoomError("bad_message", "para reservar un asiento hace falta un nombre")
        target.bot = bot_kind if kind == "bot" else None
        target.reserved_for = reserved
        self._broadcast_room(now)
        self._maybe_start(now)
        self.tick(now)

    # --- partida --------------------------------------------------------------------------------

    def act(
        self, pid: str, seq: int, action: dict[str, Any], now: float, *, re: str | None = None
    ) -> None:
        p = self._participant(pid)
        if re is not None:
            if re in p.recent:
                return  # reintento de un act ya recibido
            p.recent.append(re)
        match = self.match
        if match is None or not match.running or self.status != "running":
            self._reject(p, None, "not_running", "no hay ninguna partida en marcha", now, re)
            return
        seat = p.seat
        if seat is None or self._controlled(seat):
            self._reject(p, seq, "not_your_turn", "no juegas en este asiento", now, re)
            return
        self.touched = now
        result = self._guard(lambda: match.act(seat, seq, action, now), now)
        if isinstance(result, Batch):
            self._after_batch(result, now)
            self.tick(now)
        elif result is not None:
            self._reject(p, seq, result.reason, result.detail, now, re)

    def query_actions(
        self,
        pid: str,
        seq: int,
        name: str | None,
        args: dict[str, Any] | None,
        now: float,
        *,
        re: str | None = None,
    ) -> None:
        p = self._participant(pid)
        match = self.match
        options: list[Any] = []
        current = 0
        if match is not None and match.running and p.seat is not None:
            current = match.seq
            if not self._controlled(p.seat):
                try:
                    options = match.options(p.seat, name, args)
                except IllegalAction as exc:
                    raise RoomError("bad_message", str(exc)) from None
        data: dict[str, Any] = {"seq": current, "options": options}
        if name is not None:
            data["name"] = name
        if args is not None:
            data["args"] = args
        self._send(p, "actions", data, now, re=re)

    def resign(self, pid: str, now: float) -> None:
        p = self._participant(pid)
        match = self.match
        if match is None or not match.running or p.seat is None:
            raise RoomError("wrong_state", "no estás jugando ninguna partida")
        self._forfeit(p.seat, now)
        self.tick(now)

    def chat(self, pid: str, text: str, now: float) -> None:
        p = self._participant(pid)
        text = clean_text(text, 500)
        if not text:
            return
        sender = {"participant": p.id, "name": p.name, "seat": p.seat}
        self._broadcast("chat", {"sender": sender, "text": text}, now)

    def resync(self, pid: str, now: float) -> None:
        self._catch_up(self._participant(pid), None, now)

    # --- tiempo ---------------------------------------------------------------------------------

    def tick(self, now: float) -> None:
        """Bots y plazos vencidos hasta `now` (si hay demasiados seguidos, sigue en la próxima
        llamada)."""
        for _ in range(100_000):
            match = self.match
            if match is None or not match.running or self.status != "running":
                return
            due = sorted(
                [(t, 0, s) for s, t in self.bot_due.items() if t <= now]
                + [(t, 1, s) for s, t in match.deadlines().items() if t <= now]
            )
            if not due:
                return
            _, kind, seat = due[0]
            if kind == 0:
                self._bot_move(seat, now)
            else:
                self._timeout(seat, now)

    def next_wakeup(self) -> float | None:
        times = [o.at for o in self.outbox]
        times += self.bot_due.values()
        if self.match is not None:
            times += self.match.deadlines().values()
        return min(times, default=None)

    def drain(self, now: float) -> list[Outgoing]:
        """Mensajes que ya pueden salir (en orden)."""
        ready = [o for o in self.outbox if o.at <= now]
        if ready:
            self.outbox = [o for o in self.outbox if o.at > now]
        return ready

    # --- información ----------------------------------------------------------------------------

    def info(self) -> dict[str, Any]:
        """Estado público de la sala (mensaje `room`)."""
        game, match = self.game, self.match
        seed = match.server_seed if match is not None and self.running_match else self.server_seed
        return {
            "code": self.code,
            "game": {
                "id": game.id,
                "version": game.version,
                "title": game.title,
                "rules_hash": game.rules_hash,
                "players": {"min": game.players[0], "max": game.players[1]},
            },
            "params": self.params,
            "settings": self.settings.to_json(),
            "status": self.status,
            "seats": [self._seat_info(s) for s in self.seats],
            "spectators": [
                {"participant": p.id, "name": p.name, "connected": p.connected, "host": p.host}
                for p in self._spectators()
            ],
            "commitment": commitment(seed),
            "match": self._match_ref() if self.running_match else None,
            "last": self.last,
        }

    def session(self, p: Participant) -> dict[str, Any]:
        return {
            "room": self.code,
            "participant": p.id,
            "name": p.name,
            "role": p.role,
            "seat": p.seat,
            "host": p.host,
        }

    def connected_count(self) -> int:
        return sum(1 for p in self.participants.values() if p.connected)

    @property
    def running_match(self) -> bool:
        return self.status == "running" and self.match is not None and self.match.running

    @property
    def display_code(self) -> str:
        return display(self.code)

    def players_json(self) -> list[dict[str, Any]]:
        return [{"name": self._seat_name(s), "kind": self._seat_kind(s)} for s in self.seats]

    # --- internos: asientos y participantes -----------------------------------------------------

    def _participant(self, pid: str) -> Participant:
        p = self.participants.get(pid)
        if p is None:
            raise RoomError("invalid_token", "ese participante ya no está en la sala")
        return p

    def _open(self) -> None:
        if self.status == "closed":
            raise RoomError("wrong_state", "la sala está cerrada")

    def _lobby_only(self) -> None:
        self._open()
        if self.status != "lobby":
            raise RoomError("wrong_state", "solo se puede hacer en el lobby, entre partidas")

    def _require_host(self, pid: str) -> None:
        if not self._participant(pid).host:
            raise RoomError("not_host", "solo el anfitrión puede hacerlo")

    def _check_config(self, players: int, params: dict[str, Any]) -> None:
        try:
            self.game.new_state(players, params)
        except InvalidParams as exc:
            raise RoomError("invalid_params", str(exc)) from None

    def _unique_name(self, name: str) -> str:
        taken = {p.name for p in self.participants.values()}
        if name not in taken:
            return name
        i = 2
        while f"{name[:28]} ({i})" in taken:
            i += 1
        return f"{name[:28]} ({i})"

    def _free_seat(self, wanted: int | None, name: str, current: int | None = None) -> int:
        if self.status != "lobby":
            raise RoomError("wrong_state", "la partida ya ha empezado: entra como espectador")
        if wanted is not None:
            if not 0 <= wanted < len(self.seats):
                raise RoomError("not_allowed", f"no existe el asiento {wanted}")
            s = self.seats[wanted]
            if wanted != current and not s.empty:
                raise RoomError("seat_taken", f"el asiento {wanted} está ocupado")
            if s.reserved_for is not None and s.reserved_for.casefold() != name.casefold():
                raise RoomError("seat_taken", f"el asiento {wanted} está reservado")
            return wanted
        for s in self.seats:
            if s.empty and (s.reserved_for or "").casefold() == name.casefold():
                return s.index
        for s in self.seats:
            if s.empty and s.reserved_for is None:
                return s.index
        raise RoomError("room_full", "no quedan asientos libres: entra como espectador")

    def _seat(self, p: Participant, index: int) -> None:
        seat = self.seats[index]
        seat.participant = p.id
        seat.reserved_for = None
        p.seat = index
        p.ready = False

    def _remove(self, p: Participant, now: float) -> None:
        if p.seat is not None:
            seat = self.seats[p.seat]
            if self.running_match:
                self._forfeit(p.seat, now)
            seat.participant = None
        del self.participants[p.id]
        self.outbox = [o for o in self.outbox if o.to != p.id or o.close]
        if p.host:
            heir = next(
                (q for q in self.participants.values() if q.kind == "human" and q.connected),
                None,
            ) or next(iter(self.participants.values()), None)
            if heir is None:
                self.close(now)
            else:
                heir.host = True
        if self.status == "lobby":
            self._maybe_start(now)

    def _spectators(self) -> list[Participant]:
        return [p for p in self.participants.values() if p.seat is None]

    def _controlled(self, seat: int) -> bool:
        """¿Juega un bot por el asiento (bot del servidor, o sustituto en esta partida)?"""
        s = self.seats[seat]
        return s.bot is not None or s.takeover is not None

    def _seat_kind(self, s: Seat) -> str:
        if s.bot is not None:
            return "bot"
        if s.participant is not None:
            return self.participants[s.participant].kind
        if s.takeover is not None:
            return "bot"
        return "reserved" if s.reserved_for is not None else "open"

    def _player_kind(self, s: Seat) -> str:
        return "bot" if self._seat_kind(s) == "bot" else "human"

    def _seat_name(self, s: Seat) -> str:
        if s.participant is not None:
            return self.participants[s.participant].name
        if s.bot is not None or s.takeover is not None:
            return f"Bot {s.index + 1}"
        return s.reserved_for or f"Asiento {s.index + 1}"

    def _seat_info(self, s: Seat) -> dict[str, Any]:
        info: dict[str, Any] = {"seat": s.index, "kind": self._seat_kind(s)}
        p = self.participants.get(s.participant or "")
        if p is not None:
            info |= {"participant": p.id, "name": p.name}
        elif s.bot is not None or s.takeover is not None or s.reserved_for is not None:
            info["name"] = self._seat_name(s)
        controlled = s.bot is not None or s.takeover is not None
        info["connected"] = p.connected if p is not None else controlled
        info["ready"] = p.ready if p is not None else controlled
        info["host"] = p is not None and p.host
        bot = s.takeover or s.bot
        if bot is not None:
            info["bot"] = bot
        return info

    # --- internos: partidas ---------------------------------------------------------------------

    def _maybe_start(self, now: float) -> None:
        if self.status != "lobby":
            return
        for s in self.seats:
            if s.bot is not None:
                continue
            p = self.participants.get(s.participant or "")
            if p is None or not p.connected or not p.ready:
                return
        self._start(now)

    def _start(self, now: float) -> None:
        self.matches += 1
        seeds = [
            self.participants[s.participant].seed if s.participant is not None else ""
            for s in self.seats
        ]
        match = Match(
            self.game,
            len(self.seats),
            self.params,
            match_id=secrets.token_hex(8),
            number=self.matches,
            server_seed=self.server_seed,
            client_seeds=seeds,
            clock=self.settings.clock,
            now=now,
        )
        self.match = match
        self.status = "running"
        self.bots = {
            s.index: _agent(s.bot, match.seed, s.index, self.game)
            for s in self.seats
            if s.bot is not None
        }
        self.bot_due.clear()
        self.match_players = self.players_json()
        self.recorder.match_started(self, match)
        self._broadcast_room(now)
        for p in self._connected():
            if p.seat is not None:
                self._send(p, "match_start", self._match_start(p.seat), now)
        self._to_spectators(message("match_start", self._match_start(None)), now)
        self._after_batch(match.batches[0], now)

    def _match_ref(self) -> dict[str, Any]:
        assert self.match is not None
        return {"id": self.match.id, "number": self.match.number}

    def _match_start(self, seat: int | None) -> dict[str, Any]:
        match = self.match
        assert match is not None
        return {
            "match": self._match_ref(),
            "seat": seat,
            "players": match.n,
            "params": match.params,
            "seats": [
                {"seat": s.index, "name": self._seat_name(s), "kind": self._player_kind(s)}
                for s in self.seats
            ],
            "fairness": match.fairness(reveal=False),
            "clock": match.clock_spec,
        }

    def _observer(self) -> int | None:
        return None if self.settings.spectator_view == "omniscient" else PUBLIC

    def _after_batch(self, batch: Batch, now: float) -> None:
        match = self.match
        assert match is not None
        for p in self._connected():
            if p.seat is not None:
                limit = None if self._controlled(p.seat) else p.legal_limit
                data = match.update(p.seat, batch, now=now, legal_limit=limit)
                self._send(p, "update", data, now)
        update = match.update(self._observer(), batch, now=now)
        self._to_spectators(message("update", update), now)
        self.recorder.match_progress(self, match)
        if not match.running:
            self._finish_match(now)
        else:
            self._schedule_bots(now)

    def _schedule_bots(self, now: float) -> None:
        match = self.match
        if match is None or not match.running:
            self.bot_due.clear()
            return
        active = set(match.active())
        self.bot_due = {
            s: self.bot_due.get(s, now + self.settings.bot_delay)
            for s in sorted(active)
            if self._controlled(s)
        }

    def _bot_move(self, seat: int, now: float) -> None:
        match = self.match
        assert match is not None
        self.bot_due.pop(seat, None)
        if seat not in match.active():
            return
        s = self.seats[seat]
        agent = self.bots.get(seat)
        if agent is None:
            kind = s.bot or s.takeover or "random"
            agent = self.bots[seat] = _agent(kind, match.seed, seat, self.game)
        state = match.state
        legal = state.legal_actions(seat)
        action = agent.act(Observation(state, seat), legal)
        batch = self._guard(lambda: match.apply(seat, action, now), now)
        if batch is not None:
            self._after_batch(batch, now)

    def _timeout(self, seat: int, now: float) -> None:
        match = self.match
        assert match is not None
        policy = self.settings.on_timeout
        if policy == "forfeit":
            self._forfeit(seat, now)
            return
        if policy == "bot":
            self.seats[seat].takeover = self.seats[seat].takeover or "random"
            self._broadcast_room(now)
            self._bot_move(seat, now)
            return
        action = match.random_action(seat, prefer_pass=policy == "pass")
        batch = self._guard(lambda: match.apply(seat, action, now), now)
        if batch is not None:
            self._after_batch(batch, now)

    def _forfeit(self, seat: int, now: float) -> None:
        match = self.match
        assert match is not None
        s = self.seats[seat]
        ended = match.forfeit(seat, now)
        if ended:
            self._finish_match(now)
            return
        s.takeover = s.takeover or "random"
        self._broadcast_room(now)
        self._schedule_bots(now)

    def _finish_match(self, now: float) -> None:
        match = self.match
        assert match is not None and match.ending is not None
        ending = match.ending
        self.recorder.match_ended(self, match)
        data = {
            "match": self._match_ref(),
            "reason": ending.reason,
            "payoffs": ending.payoffs,
            "ranking": ending.ranking,
            "forfeited": ending.forfeited,
            "view": match.state.view(None),
            "fairness": match.fairness(reveal=True),
            "replay": match.id,
        }
        self.last = {
            "match": self._match_ref(),
            "reason": ending.reason,
            "payoffs": ending.payoffs,
            "ranking": ending.ranking,
        }
        self._broadcast("match_end", data, now)
        self.status = "lobby"
        self.server_seed = new_server_seed()
        self.bot_due.clear()
        for s in self.seats:
            s.takeover = None
        for p in self.participants.values():
            p.ready = False
        self._broadcast_room(now)

    def _guard[T](self, step: Callable[[], T], now: float) -> T | None:
        """Ejecuta un paso del motor; si las reglas fallan (`RuleError`), anula la partida."""
        try:
            return step()
        except EngineError as exc:
            match = self.match
            assert match is not None
            text = f"error en las reglas del juego, partida anulada: {exc}"
            self._broadcast("error", {"code": "internal", "message": text}, now)
            match.abort(now)
            self._finish_match(now)
            return None

    # --- internos: envíos -----------------------------------------------------------------------

    def _connected(self) -> list[Participant]:
        return [p for p in self.participants.values() if p.connected]

    def _send(
        self, p: Participant, kind: str, data: Any, now: float, *, re: str | None = None
    ) -> None:
        if p.connected:
            self.outbox.append(Outgoing(p.id, message(kind, data, re), now))

    def _reject(
        self, p: Participant, seq: int | None, reason: str, detail: str, now: float, re: str | None
    ) -> None:
        self._send(p, "rejected", {"seq": seq, "reason": reason, "detail": detail}, now, re=re)

    def _broadcast(self, kind: str, data: Any, now: float, *, skip: str | None = None) -> None:
        """A los jugadores ya (salvo `skip`); a los espectadores, con el retardo de la sala."""
        for p in self._connected():
            if p.seat is not None and p.id != skip:
                self._send(p, kind, data, now)
        self._to_spectators(message(kind, data), now)

    def _broadcast_room(self, now: float, *, skip: str | None = None) -> None:
        self._broadcast("room", self.info(), now, skip=skip)

    def _to_spectators(self, msg: dict[str, Any], now: float) -> None:
        self.pending.append((now, msg))
        self._compact(now)
        release = now + self.settings.spectator_delay
        for p in self._connected():
            if p.seat is None:
                self.outbox.append(Outgoing(p.id, msg, release))

    def _compact(self, now: float) -> None:
        """Pasa al resumen lo que los espectadores ya han podido ver."""
        cutoff = now - self.settings.spectator_delay
        while self.pending and self.pending[0][0] <= cutoff:
            _, msg = self.pending.popleft()
            kind = msg["type"]
            if kind == "room":
                self.keyframe["room"] = msg
            elif kind == "match_start":
                self.keyframe["match_start"] = msg
                self.keyframe.pop("update", None)
            elif kind == "update":
                self.keyframe["update"] = msg
            elif kind == "match_end":
                self.keyframe.pop("match_start", None)
                self.keyframe.pop("update", None)

    def _catch_up(self, p: Participant, resume: dict[str, Any] | None, now: float) -> None:
        """Lo que necesita quien llega o vuelve para seguir la sala y la partida: un espectador,
        el resumen de lo que ya puede ver y lo pendiente; un jugador, la sala y la partida (solo
        las actualizaciones que le faltan si `resume` dice cuál fue la última que vio)."""
        match = self.match
        if p.seat is None:
            self._compact(now)
            for kind in ("room", "match_start", "update"):
                msg = self.keyframe.get(kind)
                if msg is not None:
                    self.outbox.append(Outgoing(p.id, msg, now))
            delay = self.settings.spectator_delay
            for at, msg in self.pending:
                self.outbox.append(Outgoing(p.id, msg, at + delay))
            return
        self._send(p, "room", self.info(), now)
        if match is None or not self.running_match:
            return
        limit = None if self._controlled(p.seat) else p.legal_limit
        if resume is not None and resume.get("match") == match.id and resume["seq"] <= match.seq:
            missed = match.batches[resume["seq"] + 1 :]
            for batch in missed:
                data = match.update(p.seat, batch, now=now, legal_limit=limit)
                self._send(p, "update", data, now)
            if not missed:  # no faltaba nada: el estado actual, para refrescar relojes y turno
                self._send(p, "update", match.snapshot(p.seat, now=now, legal_limit=limit), now)
            return
        self._send(p, "match_start", self._match_start(p.seat), now)
        self._send(p, "update", match.snapshot(p.seat, now=now, legal_limit=limit), now)


def _agent(kind: str, seed: int, seat: int, game: Any = None) -> Agent:
    if kind == "first":
        return FirstAgent()
    if kind != "random" and game is not None:
        from gamehub.bots.agents import make_bot

        # Los bots del servidor piensan poco (la sala no atiende mientras tanto).
        with contextlib.suppress(ImportError):
            return make_bot(game, {"kind": kind, "seconds": 0.2}, seat, seed)
    return RandomAgent(seed, seat)
