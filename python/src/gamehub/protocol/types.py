# SPDX-License-Identifier: Apache-2.0
# Generado desde spec/protocol/v1/protocol.schema.json con `gamehub protocol types --write`.
# No editar a mano.
"""Tipos del protocolo de partidas v1: un `TypedDict` por objeto del esquema."""

from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict

# Cualquier mensaje del cliente al servidor.
type ClientMessage = (
    HelloMessage
    | JoinMessage
    | SitMessage
    | StandMessage
    | LeaveMessage
    | ReadyMessage
    | ActMessage
    | QueryActionsMessage
    | ResignMessage
    | ChatSendMessage
    | PingMessage
    | ResyncMessage
    | ConfigureMessage
    | SetSeatMessage
    | KickMessage
)


# Cualquier mensaje del servidor al cliente.
type ServerMessage = (
    WelcomeMessage
    | JoinedMessage
    | RoomMessage
    | MatchStartMessage
    | UpdateMessage
    | ActionsMessage
    | RejectedMessage
    | MatchEndMessage
    | ChatMessage
    | PongMessage
    | ErrorMessage
)


# Identificador que elige el cliente: el servidor lo devuelve en `re` y descarta un `act` repetido.
type MessageId = str


# Código de sala: 6 caracteres de Crockford base32 (se muestra como K7F-Q2P; al escribirlo se
# admiten minúsculas, guiones y espacios, y O/I/L valen 0/1/1).
type RoomCode = str


type Name = str


type Seat = int


# Número exacto: entero, o racional como texto «n/d».
type Number = int | str


# Cualquier valor JSON.
type Json = Any


type JsonObject = dict[str, Json]


class Empty(TypedDict):
    pass


class ActionData(TypedDict):
    """Una acción: nombre y argumentos en JSON (como en los replays)."""

    name: str
    args: JsonObject


class PlayerRange(TypedDict):
    min: int
    max: int


class GameInfo(TypedDict):
    id: str
    version: str
    title: str
    rules_hash: str
    players: PlayerRange


# Control de tiempo de la sala.
type Clock = ClockNone | ClockMove | ClockMatch


class ClockNone(TypedDict):
    """Sin reloj."""

    kind: Literal["none"]


class ClockMove(TypedDict):
    """Un plazo fijo para cada decisión."""

    kind: Literal["move"]
    seconds: float


class ClockMatch(TypedDict):
    """Reloj de ajedrez: un tiempo total por asiento que corre mientras le toca, más un
    incremento tras cada jugada."""

    kind: Literal["match"]
    initial: float
    increment: float


# Qué pasa al vencer un plazo: una jugada legal al azar, pasar (si se puede; si no, al azar), un bot
# juega por el asiento el resto de la partida, o el asiento abandona.
type OnTimeout = Literal["random", "pass", "bot", "forfeit"]


# Bots que ejecuta el propio servidor.
type BotKind = Literal["random", "first"]


class RoomSettings(TypedDict):
    players: int
    clock: Clock
    on_timeout: OnTimeout
    spectators: bool
    spectator_delay: float
    bot_delay: float
    private: bool


class SettingsPatch(TypedDict):
    """Cambios de configuración (solo los campos indicados)."""

    clock: NotRequired[Clock]
    on_timeout: NotRequired[OnTimeout]
    spectators: NotRequired[bool]
    spectator_delay: NotRequired[float]
    bot_delay: NotRequired[float]
    private: NotRequired[bool]


# open: libre · reserved: libre, guardado para un nombre · human: una persona · bot: un bot (del
# servidor o un cliente bot).
type SeatKind = Literal["open", "reserved", "human", "bot"]


class SeatInfo(TypedDict):
    seat: Seat
    kind: SeatKind
    participant: NotRequired[str]
    name: NotRequired[Name]
    connected: bool
    ready: bool
    host: bool
    bot: NotRequired[BotKind]


class SpectatorInfo(TypedDict):
    participant: str
    name: Name
    connected: bool
    host: bool


type RoomStatus = Literal["lobby", "running", "closed"]


# terminal: las reglas acabaron la partida · forfeit: abandonaron todos menos uno · aborted: se
# cerró la sala a medias.
type EndReason = Literal["terminal", "forfeit", "aborted"]


class MatchRef(TypedDict):
    id: str
    number: int


class MatchSummary(TypedDict):
    match: MatchRef
    reason: EndReason
    payoffs: list[Number] | None
    ranking: list[int]


class Room(TypedDict):
    """Estado público de una sala (mensaje `room` y GET /api/v1/rooms/{code})."""

    code: RoomCode
    game: GameInfo
    params: JsonObject
    settings: RoomSettings
    status: RoomStatus
    seats: list[SeatInfo]
    spectators: list[SpectatorInfo]
    commitment: str
    match: MatchRef | None
    last: MatchSummary | None


class Session(TypedDict):
    """Quién es el cliente en la sala."""

    room: RoomCode
    participant: str
    name: Name
    role: Literal["player", "spectator"]
    seat: Seat | None
    host: bool


class View(TypedDict):
    """El estado tal como lo ve el destinatario (vista redactada del motor)."""

    node: str | None
    status: Literal["chance", "decision", "terminal"]
    active: list[Seat]
    state: JsonObject
    responded: NotRequired[list[Seat]]
    payoffs: NotRequired[list[Number]]


# Un evento del motor tal como lo ve el destinatario (node, action, move, reveal, emit…).
type Event = dict[str, Json]


# Las acciones legales del destinatario cuando le toca.
type Legal = LegalEnumerated | LegalProgressive


class LegalEnumerated(TypedDict):
    """Todas las acciones legales, en el orden del motor."""

    kind: Literal["enumerated"]
    actions: list[ActionData]


class LegalProgressive(TypedDict):
    """Demasiadas para enumerarlas: los nombres disponibles; el resto se construye con
    query_actions."""

    kind: Literal["progressive"]
    names: list[str]


class Clocks(TypedDict):
    """Tiempo en milisegundos al enviar el mensaje: lo que le queda a cada asiento (null si su
    reloj no corre) y qué asientos tienen el reloj en marcha."""

    kind: Literal["move", "match"]
    remaining_ms: list[int | None]
    running: list[Seat]


class Fairness(TypedDict):
    """Azar verificable (esquema gamehub-fair/1): el compromiso se publica antes de empezar;
    server_seed y seed se revelan al terminar."""

    scheme: Literal["gamehub-fair/1"]
    commitment: str
    client_seeds: list[str]
    server_seed: NotRequired[str]
    seed: NotRequired[int]


class SeatPlayer(TypedDict):
    seat: Seat
    name: Name
    kind: Literal["human", "bot"]


class ClientInfo(TypedDict):
    name: str
    version: NotRequired[str]
    kind: Literal["human", "bot"]


class ServerRef(TypedDict):
    name: str
    version: str


class Sender(TypedDict):
    participant: str
    name: Name
    seat: Seat | None


class Hello(TypedDict):
    """Primer mensaje de cada conexión. Con `token`, retoma la sesión (reconexión): el servidor
    reenvía la sala y las actualizaciones posteriores a `last_seq`."""

    client: ClientInfo
    token: NotRequired[str]
    last_seq: NotRequired[int]
    legal_limit: NotRequired[int]


class Join(TypedDict):
    """Entrar en una sala como jugador (en el asiento pedido o en el primero libre) o como
    espectador."""

    room: str
    role: Literal["player", "spectator"]
    name: Name
    seat: NotRequired[Seat]


class Sit(TypedDict):
    """Sentarse (o cambiar de asiento) en el lobby."""

    seat: NotRequired[Seat]


class Ready(TypedDict):
    """Listo (o no) para empezar; `seed` es la semilla que aporta el jugador al azar de la
    partida."""

    ready: bool
    seed: NotRequired[str]


class Act(TypedDict):
    """Jugar una acción. `seq` es la última actualización vista: se rechaza si es anterior al
    comienzo del turno vigente del asiento."""

    seq: int
    action: ActionData


class QueryActions(TypedDict):
    """Construcción progresiva: sin `name`, los nombres de acción disponibles; con `name` y los
    primeros argumentos, los valores posibles del siguiente."""

    seq: int
    name: NotRequired[str]
    args: NotRequired[JsonObject]


class ChatSend(TypedDict):
    text: str


class Ping(TypedDict):
    t: NotRequired[float]


class Configure(TypedDict):
    """Solo el anfitrión y en el lobby: número de jugadores, opciones del juego y configuración
    de la sala."""

    players: NotRequired[int]
    params: NotRequired[JsonObject]
    settings: NotRequired[SettingsPatch]


class SetSeat(TypedDict):
    """Solo el anfitrión: abrir un asiento, reservarlo para un nombre o ponerle un bot del
    servidor (también en partida: el bot sustituye a quien ocupaba el asiento)."""

    seat: Seat
    kind: Literal["open", "reserved", "bot"]
    name: NotRequired[Name]
    bot: NotRequired[BotKind]


class Kick(TypedDict):
    """Solo el anfitrión: echar a un participante de la sala."""

    participant: str


class Welcome(TypedDict):
    server: ServerRef
    session: NotRequired[Session]


class Joined(TypedDict):
    """Respuesta a `join`: el token de sesión (guárdalo para reconectar) y quién eres."""

    token: str
    session: Session


class MatchStart(TypedDict):
    match: MatchRef
    seat: Seat | None
    players: int
    params: JsonObject
    seats: list[SeatPlayer]
    fairness: Fairness
    clock: Clock


class Update(TypedDict):
    """Lo que ha pasado desde la actualización anterior (una acción y el azar que la sigue) y el
    estado resultante, proyectado para el destinatario."""

    seq: int
    view: View
    events: list[Event]
    legal: NotRequired[Legal]
    clocks: NotRequired[Clocks]


class Actions(TypedDict):
    """Respuesta a query_actions."""

    seq: int
    name: NotRequired[str]
    args: NotRequired[JsonObject]
    options: list[Json]


class Rejected(TypedDict):
    """Una acción que no se ha aplicado."""

    seq: int | None
    reason: Literal["illegal_action", "stale_seq", "not_your_turn", "not_running"]
    detail: str


class MatchEnd(TypedDict):
    """Fin de la partida: resultado, vista completa, semilla revelada y el replay (GET
    /api/v1/replays/{replay})."""

    match: MatchRef
    reason: EndReason
    payoffs: list[Number] | None
    ranking: list[int]
    forfeited: list[Seat]
    view: View
    fairness: Fairness
    replay: str


class Chat(TypedDict):
    sender: Sender
    text: str


class Pong(TypedDict):
    t: NotRequired[float]
    server_time: float


class Error(TypedDict):
    code: Literal[
        "bad_message",
        "unsupported",
        "unknown_room",
        "room_full",
        "seat_taken",
        "not_allowed",
        "not_host",
        "invalid_token",
        "wrong_state",
        "rate_limited",
        "replaced",
        "internal",
    ]
    message: str


class HelloMessage(TypedDict):
    v: Literal[1]
    type: Literal["hello"]
    id: NotRequired[MessageId]
    data: Hello


class JoinMessage(TypedDict):
    v: Literal[1]
    type: Literal["join"]
    id: NotRequired[MessageId]
    data: Join


class SitMessage(TypedDict):
    v: Literal[1]
    type: Literal["sit"]
    id: NotRequired[MessageId]
    data: Sit


class StandMessage(TypedDict):
    """Levantarse del asiento en el lobby (se queda como espectador)."""

    v: Literal[1]
    type: Literal["stand"]
    id: NotRequired[MessageId]
    data: Empty


class LeaveMessage(TypedDict):
    """Salir de la sala (en partida, equivale a abandonar)."""

    v: Literal[1]
    type: Literal["leave"]
    id: NotRequired[MessageId]
    data: Empty


class ReadyMessage(TypedDict):
    v: Literal[1]
    type: Literal["ready"]
    id: NotRequired[MessageId]
    data: Ready


class ActMessage(TypedDict):
    v: Literal[1]
    type: Literal["act"]
    id: NotRequired[MessageId]
    data: Act


class QueryActionsMessage(TypedDict):
    v: Literal[1]
    type: Literal["query_actions"]
    id: NotRequired[MessageId]
    data: QueryActions


class ResignMessage(TypedDict):
    """Abandonar la partida: un bot juega por el asiento, que queda el último."""

    v: Literal[1]
    type: Literal["resign"]
    id: NotRequired[MessageId]
    data: Empty


class ChatSendMessage(TypedDict):
    v: Literal[1]
    type: Literal["chat"]
    id: NotRequired[MessageId]
    data: ChatSend


class PingMessage(TypedDict):
    v: Literal[1]
    type: Literal["ping"]
    id: NotRequired[MessageId]
    data: Ping


class ResyncMessage(TypedDict):
    """Pedir de nuevo la sala y el estado completo."""

    v: Literal[1]
    type: Literal["resync"]
    id: NotRequired[MessageId]
    data: Empty


class ConfigureMessage(TypedDict):
    v: Literal[1]
    type: Literal["configure"]
    id: NotRequired[MessageId]
    data: Configure


class SetSeatMessage(TypedDict):
    v: Literal[1]
    type: Literal["set_seat"]
    id: NotRequired[MessageId]
    data: SetSeat


class KickMessage(TypedDict):
    v: Literal[1]
    type: Literal["kick"]
    id: NotRequired[MessageId]
    data: Kick


class WelcomeMessage(TypedDict):
    v: Literal[1]
    type: Literal["welcome"]
    re: NotRequired[MessageId]
    data: Welcome


class JoinedMessage(TypedDict):
    v: Literal[1]
    type: Literal["joined"]
    re: NotRequired[MessageId]
    data: Joined


class RoomMessage(TypedDict):
    v: Literal[1]
    type: Literal["room"]
    re: NotRequired[MessageId]
    data: Room


class MatchStartMessage(TypedDict):
    v: Literal[1]
    type: Literal["match_start"]
    re: NotRequired[MessageId]
    data: MatchStart


class UpdateMessage(TypedDict):
    v: Literal[1]
    type: Literal["update"]
    re: NotRequired[MessageId]
    data: Update


class ActionsMessage(TypedDict):
    v: Literal[1]
    type: Literal["actions"]
    re: NotRequired[MessageId]
    data: Actions


class RejectedMessage(TypedDict):
    v: Literal[1]
    type: Literal["rejected"]
    re: NotRequired[MessageId]
    data: Rejected


class MatchEndMessage(TypedDict):
    v: Literal[1]
    type: Literal["match_end"]
    re: NotRequired[MessageId]
    data: MatchEnd


class ChatMessage(TypedDict):
    v: Literal[1]
    type: Literal["chat"]
    re: NotRequired[MessageId]
    data: Chat


class PongMessage(TypedDict):
    v: Literal[1]
    type: Literal["pong"]
    re: NotRequired[MessageId]
    data: Pong


class ErrorMessage(TypedDict):
    v: Literal[1]
    type: Literal["error"]
    re: NotRequired[MessageId]
    data: Error


class CreateRoom(TypedDict):
    """POST /api/v1/rooms: un juego del catálogo del servidor (`game`) o una IR completa (`ir`,
    si el servidor lo permite)."""

    game: NotRequired[str]
    ir: NotRequired[JsonObject]
    players: NotRequired[int]
    params: NotRequired[JsonObject]
    settings: NotRequired[SettingsPatch]
    name: NotRequired[Name]


class CreatedRoom(TypedDict):
    """Respuesta de POST /api/v1/rooms: `token` es la sesión del anfitrión (hello con ese token)."""

    code: RoomCode
    token: str
    url: str
    room: Room


class ServerInfo(TypedDict):
    """GET /api/v1/info."""

    name: str
    version: str
    protocol: Literal[1]
    upload: bool
    games: list[GameInfo]
    rooms: int


class RoomList(TypedDict):
    """GET /api/v1/rooms: salas públicas (no privadas) y abiertas."""

    rooms: list[Room]


class ApiError(TypedDict):
    """Cuerpo de las respuestas de error de la API REST."""

    error: Error
