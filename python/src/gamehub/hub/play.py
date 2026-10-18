# SPDX-License-Identifier: AGPL-3.0-or-later
"""Jugar en el hub: salas alojadas de las versiones publicadas, emparejamiento y valoraciones.

- **Salas**: el servidor de partidas de siempre (`gamehub.server`) montado en el hub, con un
  catálogo que carga cualquier versión publicada por su referencia: `dueño/juego@1.2.0` (o
  `dueño/juego`, la última).
- **Quién juega**: si quien se conecta tiene sesión en el hub, su asiento queda a su nombre.
- **Valoraciones humanas**: al acabar una partida, se guarda; si todos los asientos eran personas
  distintas con cuenta (sin bots ni sustituciones), cuenta para Elo, Glicko-2 y TrueSkill **por
  hash de reglas**, como la arena de bots (ADR-096). Se marca si fue "solo humanos".
- **Emparejamiento**: una cola por (versión, jugadores); con gente suficiente, el hub abre una
  sala, sienta a cada uno (con su token) y se lo dice. Empareja primero por cercanía de Elo y
  abre la ventana con la espera.
"""

from __future__ import annotations

import json
import re
import secrets
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from gamehub.bots.ratings import Result, elo, glicko2, trueskill
from gamehub.engine import Game
from gamehub.hub import registry
from gamehub.hub.service import Account, Hub, HubError, bad, not_found
from gamehub.server.catalog import Catalog, game_info
from gamehub.server.match import Match
from gamehub.server.room import Room

REF = re.compile(r"^([a-z0-9-]+)/([a-z0-9-]+)(?:@(.+))?$")


class HubCatalog(Catalog):
    """Los juegos del hub por su referencia de versión (con caché de los ya cargados)."""

    def __init__(self, hub: Hub, games: Catalog | None = None, size: int = 128) -> None:
        super().__init__(games.games.values() if games else ())
        self.hub = hub
        self.size = size
        self.loaded: OrderedDict[int, Game] = OrderedDict()
        #: Referencia de cada juego cargado (por identidad del objeto).
        self.refs: dict[int, str] = {}
        self.lock = threading.Lock()

    def get(self, game_id: str) -> Game | None:
        m = REF.match(game_id)
        if m is None:
            return super().get(game_id)
        owner, name, version = m.groups()
        try:
            repo = self.hub.repo(owner, name)
            row = registry.release(self.hub, repo, version or "latest")
        except HubError:
            return None
        if row["ir"] is None:
            return None
        with self.lock:
            game = self.loaded.get(row["id"])
            if game is None:
                game = Game(self.hub.blobs.get_json(row["ir"]))
                self.loaded[row["id"]] = game
                self.refs[id(game)] = registry.game_ref(self.hub, repo, row)
                while len(self.loaded) > self.size:
                    _, old = self.loaded.popitem(last=False)
                    self.refs.pop(id(old), None)
            else:
                self.loaded.move_to_end(row["id"])
        return game

    def ref_of(self, game: Game) -> str | None:
        return self.refs.get(id(game))

    def info(self) -> list[dict[str, Any]]:
        """Las versiones más recientes de los juegos más populares (para la portada)."""
        rows = self.hub.db.all(
            "SELECT r.id AS repo_id, v.version FROM releases v JOIN repos r ON r.id = v.repo"
            " WHERE r.hidden = 0 AND v.yanked = 0 AND v.ir IS NOT NULL"
            " ORDER BY r.stars DESC, v.created DESC LIMIT 200"
        )
        seen: set[int] = set()
        out = super().info()
        for row in rows:
            if row["repo_id"] in seen:
                continue
            seen.add(row["repo_id"])
            repo = self.hub.repo_by_id(row["repo_id"])
            release = registry.release(self.hub, repo, "latest")
            ref = registry.game_ref(self.hub, repo, release)
            game = self.get(ref)
            if game is not None:
                out.append({**game_info(game), "id": ref})
            if len(out) >= 50:
                break
        return out


class HubRecorder:
    """Guarda en el hub las partidas de sus salas y actualiza las valoraciones (además de lo que
    haga el almacén de replays del servidor, al que delega)."""

    def __init__(self, hub: Hub, catalog: HubCatalog, inner: Any) -> None:
        self.hub = hub
        self.catalog = catalog
        self.inner = inner

    def replay(self, match_id: str) -> dict[str, Any] | None:
        return self.inner.replay(match_id)

    def game(self, rules_hash: str) -> dict[str, Any] | None:
        return self.inner.game(rules_hash)

    def matches(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.inner.matches(limit)

    def close(self) -> None:
        self.inner.close()

    def match_started(self, room: Room, match: Match) -> None:
        self.inner.match_started(room, match)

    def match_progress(self, room: Room, match: Match) -> None:
        self.inner.match_progress(room, match)

    def match_ended(self, room: Room, match: Match) -> None:
        self.inner.match_ended(room, match)
        ref = self.catalog.ref_of(match.game)
        ending = match.ending
        if ref is None or ending is None:
            return
        players = seat_players(room)
        accounts = [p["account"] for p in players]
        humans_only = all(p["kind"] == "human" for p in players)
        rated = (
            humans_only
            and ending.reason in ("terminal", "forfeit")
            and all(a is not None for a in accounts)
            and len(set(accounts)) == len(accounts)
            and len(accounts) >= 2
        )
        self.hub.db.execute(
            "INSERT INTO matches (id, rules_hash, game, room, players, result, rated, humans_only,"
            " created) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                match.id,
                match.game.rules_hash,
                ref,
                room.code,
                json.dumps(players, ensure_ascii=False),
                json.dumps(
                    {"reason": ending.reason, "payoffs": ending.payoffs, "ranking": ending.ranking}
                ),
                int(rated),
                int(humans_only),
                self.hub.now(),
            ),
        )
        if rated:
            update_ratings(self.hub, match.game.rules_hash)


def seat_players(room: Room) -> list[dict[str, Any]]:
    """Quién jugó cada asiento: nombre, tipo (human/bot) y cuenta del hub (si la había)."""
    out = []
    for seat in room.seats:
        p = room.participants.get(seat.participant) if seat.participant else None
        human = p is not None and p.kind == "human" and seat.bot is None and seat.takeover is None
        out.append(
            {
                "name": p.name if p else (seat.bot or "?"),
                "kind": "human" if human else "bot",
                "account": getattr(p, "account", None) if human else None,
            }
        )
    return out


def update_ratings(hub: Hub, rules_hash: str) -> None:
    """Recalcula las valoraciones de un juego (por hash de reglas) con todas sus partidas
    puntuables: son pocas comparadas con las de la arena, y así el orden no importa para Elo."""
    rows = hub.db.all(
        "SELECT players, result FROM matches WHERE rules_hash = ? AND rated = 1 ORDER BY created",
        (rules_hash,),
    )
    results = []
    for row in rows:
        players = json.loads(row["players"])
        result = json.loads(row["result"])
        results.append(Result(tuple(str(p["account"]) for p in players), tuple(result["ranking"])))
    if not results:
        return
    elos = elo(results)
    glicko = glicko2([[r] for r in results])
    skills = trueskill(results)
    games: dict[str, int] = {}
    for r in results:
        for p in set(r.players):
            games[p] = games.get(p, 0) + 1
    with hub.db.transaction():
        hub.db.execute("DELETE FROM ratings WHERE rules_hash = ?", (rules_hash,))
        for account, count in games.items():
            g = glicko.get(account)
            s = skills.get(account)
            hub.db.execute(
                "INSERT INTO ratings (rules_hash, account, elo, glicko, glicko_rd, trueskill,"
                " games) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    rules_hash,
                    int(account),
                    elos.get(account, 1500.0),
                    g.rating if g else 1500.0,
                    g.rd if g else 350.0,
                    s.conservative if s else 0.0,
                    count,
                ),
            )


def leaderboard(hub: Hub, rules_hash: str, limit: int = 100) -> list[dict[str, Any]]:
    rows = hub.db.all(
        "SELECT r.*, a.name FROM ratings r JOIN accounts a ON a.id = r.account"
        " WHERE r.rules_hash = ? ORDER BY r.elo DESC LIMIT ?",
        (rules_hash, limit),
    )
    return [
        {
            "account": r["name"],
            "elo": round(r["elo"], 1),
            "glicko": round(r["glicko"], 1),
            "glicko_rd": round(r["glicko_rd"], 1),
            "trueskill": round(r["trueskill"], 2),
            "games": r["games"],
        }
        for r in rows
    ]


def recent_matches(
    hub: Hub, rules_hash: str | None = None, limit: int = 30
) -> list[dict[str, Any]]:
    if rules_hash:
        rows = hub.db.all(
            "SELECT * FROM matches WHERE rules_hash = ? ORDER BY created DESC LIMIT ?",
            (rules_hash, limit),
        )
    else:
        rows = hub.db.all("SELECT * FROM matches ORDER BY created DESC LIMIT ?", (limit,))
    out = []
    for r in rows:
        players = json.loads(r["players"])
        for p in players:
            if p["account"] is not None:
                acc_row = hub.db.one("SELECT name FROM accounts WHERE id = ?", (p["account"],))
                p["account"] = acc_row["name"] if acc_row else None
        out.append(
            {
                "id": r["id"],
                "game": r["game"],
                "players": players,
                "result": json.loads(r["result"]),
                "rated": bool(r["rated"]),
                "humans_only": bool(r["humans_only"]),
                "created": r["created"],
            }
        )
    return out


# --- emparejamiento -----------------------------------------------------------------------------


@dataclass
class Ticket:
    id: str
    game: str  # referencia exacta (dueño/juego@versión)
    players: int
    account: int
    name: str
    rating: float
    since: float
    #: Cuando hay sala: su código y el token de este jugador.
    room: str | None = None
    token: str | None = None
    seat: int | None = None


@dataclass
class Matchmaker:
    """Colas de espera por (versión, jugadores). Lógica pura: el tiempo y la creación de salas
    los pone quien llama."""

    #: Diferencia de Elo admitida al empezar y cuánto crece por segundo de espera.
    window: float = 200.0
    widen: float = 20.0
    tickets: dict[str, Ticket] = field(default_factory=dict)

    def join(self, game: str, players: int, account: Account, rating: float, now: float) -> Ticket:
        for t in self.tickets.values():
            if t.account == account["id"] and t.room is None:
                if t.game == game and t.players == players:
                    return t
                raise HubError(409, "queued", f"ya esperas partida de {t.game}")
        ticket = Ticket(
            secrets.token_urlsafe(12),
            game,
            players,
            account["id"],
            account["display"] or account["name"],
            rating,
            now,
        )
        self.tickets[ticket.id] = ticket
        return ticket

    def leave(self, ticket_id: str, account: Account) -> None:
        t = self.tickets.get(ticket_id)
        if t is None or t.account != account["id"]:
            raise not_found("no existe ese turno de espera")
        del self.tickets[ticket_id]

    def ticket(self, ticket_id: str, account: Account) -> Ticket:
        t = self.tickets.get(ticket_id)
        if t is None or t.account != account["id"]:
            raise not_found("no existe ese turno de espera")
        return t

    def groups(self, now: float) -> list[list[Ticket]]:
        """Los grupos que ya pueden jugar: por cola, del que más espera, los más cercanos en
        Elo dentro de la ventana de cada uno."""
        found: list[list[Ticket]] = []
        queues: dict[tuple[str, int], list[Ticket]] = {}
        for t in sorted(self.tickets.values(), key=lambda t: t.since):
            if t.room is None:
                queues.setdefault((t.game, t.players), []).append(t)
        for (_, n), waiting in queues.items():
            while len(waiting) >= n:
                first = waiting[0]
                reach = self.window + self.widen * (now - first.since)
                near = sorted(waiting[1:], key=lambda t: abs(t.rating - first.rating))
                chosen = [
                    t
                    for t in near
                    if abs(t.rating - first.rating)
                    <= max(reach, self.window + self.widen * (now - t.since))
                ][: n - 1]
                if len(chosen) < n - 1:
                    break
                group = [first, *chosen]
                found.append(group)
                waiting = [t for t in waiting if t not in group]
        return found

    def expire(self, now: float, ttl: float = 600.0) -> None:
        """Olvida los turnos ya servidos hace rato y los abandonados."""
        for key, t in list(self.tickets.items()):
            if now - t.since > ttl:
                del self.tickets[key]


def rating_of(hub: Hub, rules_hash: str, account: Account) -> float:
    row = hub.db.one(
        "SELECT elo FROM ratings WHERE rules_hash = ? AND account = ?",
        (rules_hash, account["id"]),
    )
    return float(row["elo"]) if row else 1500.0


def check_players(game: Game, players: int | None) -> int:
    n = players or game.players[0]
    if not game.players[0] <= n <= game.players[1]:
        raise bad(f"este juego es de {game.players[0]} a {game.players[1]} jugadores")
    return n
