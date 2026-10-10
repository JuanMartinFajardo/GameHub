# SPDX-License-Identifier: Apache-2.0
"""Cliente de terminal para jugar en red (`gamehub join` y `gamehub host`).

Lee líneas (comandos que empiezan por `/`, la elección de jugadas o texto de chat) y mensajes del
servidor a la vez. Cuando te toca muestra el estado tal como lo ves y un menú de acciones (por
número o filtrando con palabras; si hay demasiadas, se construyen paso a paso).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import sys
import threading
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from gamehub.client.connection import Client, ClientError
from gamehub.console.play import Chooser, Quit
from gamehub.console.render import event_text, value_text, view_text
from gamehub.engine import Game
from gamehub.server import data_dir
from gamehub.server.codes import display

#: Comandos (en español, con alias en inglés) → acción.
COMMANDS = {
    "ayuda": "help",
    "help": "help",
    "listo": "ready",
    "ready": "ready",
    "nolisto": "unready",
    "unready": "unready",
    "chat": "chat",
    "say": "chat",
    "sentar": "sit",
    "sit": "sit",
    "levantar": "stand",
    "stand": "stand",
    "bot": "bot",
    "abrir": "open",
    "open": "open",
    "reservar": "reserve",
    "reserve": "reserve",
    "echar": "kick",
    "kick": "kick",
    "jugadores": "players",
    "players": "players",
    "opcion": "param",
    "opción": "param",
    "param": "param",
    "rendirse": "resign",
    "resign": "resign",
    "estado": "view",
    "view": "view",
    "sala": "room",
    "room": "room",
    "salir": "quit",
    "quit": "quit",
    "exit": "quit",
}

HELP = """Comandos (o escribe texto para el chat):
  /listo · /nolisto           listo (o no) para empezar; tras una partida, /listo = revancha
  /chat TEXTO                 mensaje para la sala
  /sentar [N] · /levantar     sentarte (en el asiento N) o pasar a espectador, en el lobby
  /estado · /sala             ver el estado de la partida o la sala
  /rendirse                   abandonar la partida (un bot juega por ti y quedas el último)
  /salir                      salir de la sala
Anfitrión: /bot N [random|first] · /abrir N · /reservar N NOMBRE · /echar NOMBRE ·
  /jugadores N · /opcion NOMBRE=VALOR"""


class Sessions:
    """Tokens de sesión guardados por servidor y sala, para volver a la misma partida si se
    cierra la terminal (`~/.local/share/gamehub/sessions.json`)."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or data_dir() / "sessions.json"

    def _load(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def get(self, server: str, code: str) -> str | None:
        entry = self._load().get(f"{server}|{code}")
        return entry.get("token") if isinstance(entry, dict) else None

    def put(self, server: str, code: str, token: str | None) -> None:
        data = self._load()
        key = f"{server}|{code}"
        if token is None:
            data.pop(key, None)
        else:
            data[key] = {"token": token}
        with contextlib.suppress(OSError):
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(data, indent=1), encoding="utf-8")


class Terminal:
    def __init__(
        self,
        client: Client,
        *,
        out: Callable[[str], None] = print,
        sessions: Sessions | None = None,
        host_mode: bool = False,
    ) -> None:
        self.client = client
        self.out = out
        self.sessions = sessions
        self.host_mode = host_mode
        self.game: Game | None = None
        self.chooser: Chooser | None = None
        self.building: dict[str, Any] | None = None  # acción progresiva a medio construir
        self.finished = False
        self.last_status: str | None = None
        self.connected: dict[int, bool] = {}

    # --- bucle ----------------------------------------------------------------------------------

    async def run(self, lines: AsyncIterator[str]) -> int:
        """Atiende mensajes y líneas hasta `/salir` o hasta que se cierra la conexión."""
        reader = asyncio.create_task(self._read(lines))
        try:
            await self._load_game()
            if self.client.room is not None:
                self._show_room(self.client.room)
            async for msg in self.client:
                await self.on_message(msg)
                if self.finished:
                    break
        finally:
            reader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reader
        return 0

    async def _read(self, lines: AsyncIterator[str]) -> None:
        async for line in lines:
            try:
                await self.on_line(line)
            except ClientError as exc:
                self.out(f"error: {exc.message}")
            if self.finished:
                break
        else:
            await self._quit()

    # --- mensajes del servidor ------------------------------------------------------------------

    async def on_message(self, msg: dict[str, Any]) -> None:
        kind, data = msg["type"], msg["data"]
        match kind:
            case "welcome" if "session" in data:
                self.out("Conexión recuperada.")
            case "joined":
                self._remember(data["token"])
                where = (
                    "como espectador"
                    if data["session"]["seat"] is None
                    else (f"en el asiento {data['session']['seat'] + 1}")
                )
                self.out(f"Has entrado en la sala {display(data['session']['room'])} {where}.")
                await self._load_game()
            case "room":
                self._on_room(data)
            case "match_start":
                self._on_match_start(data)
            case "update":
                await self._on_update(data)
            case "rejected":
                self.out(f"  ✗ Jugada rechazada: {data['detail']}")
                await self._prompt_action()
            case "match_end":
                self._on_match_end(data)
            case "chat":
                sender = data["sender"]
                self.out(f"  [{sender['name']}] {data['text']}")
            case "error":
                self.out(f"  error: {data['message']}")
                if data["code"] in ("replaced", "not_allowed") and "echado" in data["message"]:
                    self._remember(None)
                    self.finished = True

    def _on_room(self, room: dict[str, Any]) -> None:
        status = room["status"]
        if status == "closed":
            self.out("La sala se ha cerrado.")
            self._remember(None)
            self.finished = True
            return
        changed = status != self.last_status
        self.last_status = status
        if status == "lobby":
            self._show_room(room)
            return
        # En partida, solo los cambios de conexión.
        for seat in room["seats"]:
            index, now = seat["seat"], seat["connected"]
            before = self.connected.get(index)
            if before is not None and before != now and seat["kind"] != "bot":
                name = seat.get("name", f"asiento {index + 1}")
                self.out(f"  · {name} {'ha vuelto' if now else 'se ha desconectado'}")
            self.connected[index] = now
        if changed:
            self.connected = {s["seat"]: s["connected"] for s in room["seats"]}

    def _show_room(self, room: dict[str, Any]) -> None:
        me = self.client.seat
        game = room["game"]
        self.out(f"── Sala {display(room['code'])} · {game['title']} · lobby ──")
        for seat in room["seats"]:
            name = seat.get("name", "libre")
            tags = []
            if seat["seat"] == me:
                tags.append("tú")
            if seat["host"]:
                tags.append("anfitrión")
            if seat["kind"] == "bot":
                tags.append("bot")
            elif seat["kind"] == "reserved":
                tags.append("reservado")
            elif seat["kind"] != "open":
                tags.append("listo" if seat["ready"] else "esperando")
                if not seat["connected"]:
                    tags.append("desconectado")
            extra = f" ({', '.join(tags)})" if tags else ""
            self.out(f"  {seat['seat'] + 1}. {name}{extra}")
        watchers = [s["name"] for s in room["spectators"] if s["connected"]]
        if watchers:
            self.out(f"  Espectadores: {', '.join(watchers)}")
        last = room.get("last")
        if last is not None and last["payoffs"] is not None:
            self.out(f"  Última partida: pagos {', '.join(str(p) for p in last['payoffs'])}")
        if me is not None:
            info = self.client.seat_info(me)
            if info is not None and not info["ready"]:
                self.out("Escribe /listo cuando quieras empezar (/ayuda: comandos).")
        else:
            self.out("Eres espectador: /sentar para jugar (/ayuda: comandos).")

    def _on_match_start(self, data: dict[str, Any]) -> None:
        self.last_status = "running"
        names = ", ".join(f"{s['seat'] + 1}. {s['name']}" for s in data["seats"])
        who = (
            "miras la partida"
            if data["seat"] is None
            else f"juegas en el asiento {data['seat'] + 1}"
        )
        self.out(f"── Partida {data['match']['number']} · {who} ──")
        self.out(f"  Jugadores: {names}")
        commitment = data["fairness"]["commitment"]
        self.out(f"  Compromiso del azar: {commitment[:16]}… (se revela al terminar)")

    async def _on_update(self, data: dict[str, Any]) -> None:
        for event in data["events"]:
            if event.get("type") == "node":
                continue
            text = event_text(event)
            if text is not None:
                self.out(f"  · {self._names(text)}")
        if "legal" in data:
            await self._prompt_action(data)
        else:
            self.chooser = None
            self.building = None
            active = data["view"]["active"]
            if active and data["view"]["status"] == "decision":
                who = ", ".join(self._seat_name(s) for s in active)
                self.out(f"  Turno de {who}{self._clock_text(data, active[0])}")

    def _on_match_end(self, data: dict[str, Any]) -> None:
        self.chooser = None
        self.building = None
        reasons = {"terminal": "fin", "forfeit": "abandono", "aborted": "anulada"}
        self.out(f"── Fin de la partida ({reasons.get(data['reason'], data['reason'])}) ──")
        if self.game is not None:
            self.out(view_text(self.game, data["view"], seat=None))
        for seat, rank in sorted(enumerate(data["ranking"]), key=lambda x: x[1]):
            payoff = data["payoffs"][seat] if data["payoffs"] is not None else "—"
            mark = " ← tú" if seat == self.client.seat else ""
            gone = " (abandonó)" if seat in data["forfeited"] else ""
            self.out(f"  {rank}.º {self._seat_name(seat)}: {payoff}{gone}{mark}")
        fair = data["fairness"]
        self.out(f"  Azar: semilla revelada {fair['server_seed'][:16]}… (replay {data['replay']})")
        self.out("Escribe /listo para la revancha o /salir.")

    # --- jugar ----------------------------------------------------------------------------------

    async def _prompt_action(self, data: dict[str, Any] | None = None) -> None:
        data = data or self.client.update
        if data is None or "legal" not in data or self.client.seat is None:
            return
        seat = self.client.seat
        if self.game is not None:
            self.out(view_text(self.game, data["view"], seat=seat))
        legal = data["legal"]
        self.out(f"Te toca{self._clock_text(data, seat)}.")
        if legal["kind"] == "enumerated":
            self.building = None
            self.chooser = Chooser(legal["actions"], _action_label)
        else:
            self.building = {"name": None, "args": {}}
            self.chooser = Chooser(legal["names"], str)
        self._show_menu()

    def _show_menu(self) -> None:
        if self.chooser is None:
            return
        lines, prompt = self.chooser.menu()
        for line in lines:
            self.out(line)
        self.out(prompt.rstrip())

    async def _choose(self, line: str) -> None:
        assert self.chooser is not None
        try:
            chosen, notice = self.chooser.feed(line)
        except Quit:
            await self._quit()
            return
        if notice is not None:
            self.out(notice)
        if chosen is None:
            self._show_menu()
            return
        if self.building is None:
            self.chooser = None
            await self.client.act(chosen)
            return
        await self._build(chosen)

    async def _build(self, chosen: Any) -> None:
        """Construcción progresiva: primero el nombre, después cada parámetro."""
        building = self.building
        assert building is not None
        if building["name"] is None:
            building["name"] = chosen
        else:
            params = self._params(building["name"])
            building["args"][params[len(building["args"])]] = chosen
        params = self._params(building["name"])
        if len(building["args"]) == len(params):
            self.chooser = self.building = None
            await self.client.act(building)
            return
        options = await self.client.query_actions(building["name"], building["args"])
        if not options:
            self.out("  No hay ninguna jugada legal por ese camino; vuelve a empezar.")
            await self._prompt_action()
            return
        self.out(f"  {building['name']}: elige {params[len(building['args'])]}")
        self.chooser = Chooser(options, value_text)
        self._show_menu()

    def _params(self, name: str) -> list[str]:
        if name == "pass" or self.game is None or self.client.view is None:
            return []
        node = self.game.defn.nodes[self.client.view["node"]]
        return [p.name for p in node.actions_by_name[name].params]

    # --- líneas del usuario ---------------------------------------------------------------------

    async def on_line(self, line: str) -> None:
        text = line.strip()
        if text.startswith("/"):
            await self._command(text[1:])
        elif self.chooser is not None:
            await self._choose(text)
        elif text.isdigit():
            self.out("  No es tu turno.")
        elif text:
            await self.client.chat(text)

    async def _command(self, text: str) -> None:
        name, _, rest = text.partition(" ")
        rest = rest.strip()
        command = COMMANDS.get(name.lower())
        c = self.client
        match command:
            case "help":
                self.out(HELP)
            case "ready":
                await c.ready(True)
            case "unready":
                await c.ready(False)
            case "chat" if rest:
                await c.chat(rest)
            case "sit":
                await c.sit(int(rest) - 1 if rest.isdigit() else None)
            case "stand":
                await c.stand()
            case "bot" if rest:
                seat, _, kind = rest.partition(" ")
                await c.set_seat(int(seat) - 1, "bot", bot=kind.strip() or "random")
            case "open" if rest.isdigit():
                await c.set_seat(int(rest) - 1, "open")
            case "reserve" if rest:
                seat, _, who = rest.partition(" ")
                await c.set_seat(int(seat) - 1, "reserved", name=who.strip())
            case "kick" if rest:
                await self._kick(rest)
            case "players" if rest.isdigit():
                await c.configure(players=int(rest))
            case "param" if "=" in rest:
                key, _, value = rest.partition("=")
                params = dict((c.room or {}).get("params", {}))
                try:
                    params[key.strip()] = json.loads(value)
                except ValueError:
                    params[key.strip()] = value.strip()
                await c.configure(params=params)
            case "resign":
                await c.resign()
            case "view":
                if c.update is not None and self.game is not None:
                    self.out(view_text(self.game, c.update["view"], seat=c.seat))
                else:
                    self.out("  No hay ninguna partida en marcha.")
            case "room":
                if c.room is not None:
                    self._show_room(c.room)
            case "quit":
                await self._quit()
            case _:
                self.out(f"  Comando desconocido o incompleto: /{text} (/ayuda)")

    async def _kick(self, who: str) -> None:
        room = self.client.room or {}
        people = [s for s in room.get("seats", []) if "participant" in s]
        people += room.get("spectators", [])
        target = next(
            (
                p
                for p in people
                if p.get("name", "").casefold() == who.casefold()
                or (who.isdigit() and p.get("seat") == int(who) - 1)
            ),
            None,
        )
        if target is None:
            self.out(f"  No hay nadie llamado {who} en la sala.")
            return
        await self.client.kick(target["participant"])

    async def _quit(self) -> None:
        if self.finished:
            return
        self.finished = True
        with contextlib.suppress(ClientError):
            await self.client.leave()
        self._remember(None)
        self.out("Has salido de la sala.")
        await self.client.close()

    # --- utilidades -----------------------------------------------------------------------------

    async def _load_game(self) -> None:
        if self.game is None and self.client.session is not None:
            with contextlib.suppress(ClientError, Exception):
                self.game = Game(await self.client.room_ir())

    def _remember(self, token: str | None) -> None:
        session = self.client.session
        if self.sessions is not None and session is not None:
            self.sessions.put(self.client.http, session["room"], token)

    def _seat_name(self, seat: int) -> str:
        match = self.client.match
        if match is not None:
            for s in match["seats"]:
                if s["seat"] == seat:
                    return s["name"]
        info = self.client.seat_info(seat)
        return info.get("name", f"asiento {seat + 1}") if info else f"asiento {seat + 1}"

    def _names(self, text: str) -> str:
        """`asiento 2` → el nombre de quien está en él."""
        match = self.client.match
        if match is None:
            return text
        for s in match["seats"]:
            text = text.replace(f"asiento {s['seat']}", s["name"])
        return text

    @staticmethod
    def _clock_text(data: dict[str, Any], seat: int) -> str:
        clocks = data.get("clocks")
        if clocks is None:
            return ""
        remaining = clocks["remaining_ms"][seat]
        if remaining is None:
            return ""
        seconds = remaining // 1000
        return f" (⏱ {seconds // 60}:{seconds % 60:02d})"


def _action_label(action: dict[str, Any]) -> str:
    args = action.get("args") or {}
    if not args:
        return action["name"]
    inner = ", ".join(f"{k}: {value_text(v)}" for k, v in args.items())
    return f"{action['name']}({inner})"


async def stdin_lines() -> AsyncIterator[str]:
    """Las líneas de la entrada estándar, leídas en un hilo (que no impide salir)."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    def put(item: str | None) -> None:
        with contextlib.suppress(RuntimeError):  # el bucle ya ha terminado
            loop.call_soon_threadsafe(queue.put_nowait, item)

    def read() -> None:
        for line in sys.stdin:
            put(line.rstrip("\n"))
        put(None)

    threading.Thread(target=read, daemon=True).start()
    while (line := await queue.get()) is not None:
        yield line
