// SPDX-License-Identifier: Apache-2.0
// Generado desde spec/protocol/v1/protocol.schema.json con `gamehub protocol types --write`.
// No editar a mano.

/** Cualquier mensaje del cliente al servidor. */
export type ClientMessage =
  | HelloMessage
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
  | KickMessage;

/** Cualquier mensaje del servidor al cliente. */
export type ServerMessage =
  | WelcomeMessage
  | JoinedMessage
  | RoomMessage
  | MatchStartMessage
  | UpdateMessage
  | ActionsMessage
  | RejectedMessage
  | MatchEndMessage
  | ChatMessage
  | PongMessage
  | ErrorMessage;

/**
 * Identificador que elige el cliente, único en toda la sesión (también si otro proceso la retoma
 * con el mismo token: conviene un prefijo aleatorio): el servidor lo devuelve en `re` y descarta un
 * `act` con un id ya visto.
 */
export type MessageId = string;

/**
 * Código de sala: 6 caracteres de Crockford base32 (se muestra como K7F-Q2P; al escribirlo se
 * admiten minúsculas, guiones y espacios, y O/I/L valen 0/1/1).
 */
export type RoomCode = string;

export type Name = string;

export type Seat = number;

/** Número exacto: entero, o racional como texto «n/d». */
export type ExactNumber = number | string;

/** Cualquier valor JSON. */
export type Json = unknown;

export type JsonObject = Record<string, Json>;

export type Empty = Record<string, never>;

/** Una acción: nombre y argumentos en JSON (como en los replays). */
export interface ActionData {
  name: string;
  args: JsonObject;
}

export interface PlayerRange {
  min: number;
  max: number;
}

export interface GameInfo {
  id: string;
  version: string;
  title: string;
  rules_hash: string;
  players: PlayerRange;
}

/** Control de tiempo de la sala. */
export type Clock = ClockNone | ClockMove | ClockMatch;

/** Sin reloj. */
export interface ClockNone {
  kind: "none";
}

/** Un plazo fijo para cada decisión. */
export interface ClockMove {
  kind: "move";
  seconds: number;
}

/**
 * Reloj de ajedrez: un tiempo total por asiento que corre mientras le toca, más un incremento tras
 * cada jugada.
 */
export interface ClockMatch {
  kind: "match";
  initial: number;
  increment: number;
}

/**
 * Qué pasa al vencer un plazo: una jugada legal al azar, pasar (si se puede; si no, al azar), un
 * bot juega por el asiento el resto de la partida, o el asiento abandona.
 */
export type OnTimeout = "random" | "pass" | "bot" | "forfeit";

/**
 * Qué ven los espectadores: lo público, o todo (como en una retransmisión de póquer; conviene con
 * retardo).
 */
export type SpectatorView = "public" | "omniscient";

/** Bots que ejecuta el propio servidor. */
export type BotKind = "random" | "first";

export interface RoomSettings {
  players: number;
  clock: Clock;
  on_timeout: OnTimeout;
  spectators: boolean;
  spectator_view: SpectatorView;
  spectator_delay: number;
  bot_delay: number;
  private: boolean;
}

/** Cambios de configuración (solo los campos indicados). */
export interface SettingsPatch {
  clock?: Clock;
  on_timeout?: OnTimeout;
  spectators?: boolean;
  spectator_view?: SpectatorView;
  spectator_delay?: number;
  bot_delay?: number;
  private?: boolean;
}

/**
 * open: libre · reserved: libre, guardado para un nombre · human: una persona · bot: un bot (del
 * servidor o un cliente bot).
 */
export type SeatKind = "open" | "reserved" | "human" | "bot";

export interface SeatInfo {
  seat: Seat;
  kind: SeatKind;
  participant?: string;
  name?: Name;
  connected: boolean;
  ready: boolean;
  host: boolean;
  bot?: BotKind;
}

export interface SpectatorInfo {
  participant: string;
  name: Name;
  connected: boolean;
  host: boolean;
}

export type RoomStatus = "lobby" | "running" | "closed";

/**
 * terminal: las reglas acabaron la partida · forfeit: abandonaron todos menos uno · aborted: se
 * cerró la sala a medias.
 */
export type EndReason = "terminal" | "forfeit" | "aborted";

export interface MatchRef {
  id: string;
  number: number;
}

export interface MatchSummary {
  match: MatchRef;
  reason: EndReason;
  payoffs: ExactNumber[] | null;
  ranking: number[];
}

/** Estado público de una sala (mensaje `room` y GET /api/v1/rooms/{code}). */
export interface Room {
  code: RoomCode;
  game: GameInfo;
  params: JsonObject;
  settings: RoomSettings;
  status: RoomStatus;
  seats: SeatInfo[];
  spectators: SpectatorInfo[];
  /** Compromiso del azar de la partida en curso o de la siguiente (azar verificable). */
  commitment: string;
  match: MatchRef | null;
  last: MatchSummary | null;
}

/** Quién es el cliente en la sala. */
export interface Session {
  room: RoomCode;
  participant: string;
  name: Name;
  role: "player" | "spectator";
  seat: Seat | null;
  host: boolean;
}

/** El estado tal como lo ve el destinatario (vista redactada del motor). */
export interface View {
  node: string | null;
  status: "chance" | "decision" | "terminal";
  active: Seat[];
  state: JsonObject;
  responded?: Seat[];
  payoffs?: ExactNumber[];
}

/** Un evento del motor tal como lo ve el destinatario (node, action, move, reveal, emit…). */
export interface GameEvent {
  type: string;
  [key: string]: Json;
}

/** Las acciones legales del destinatario cuando le toca. */
export type Legal = LegalEnumerated | LegalProgressive;

/** Todas las acciones legales, en el orden del motor. */
export interface LegalEnumerated {
  kind: "enumerated";
  actions: ActionData[];
}

/**
 * Demasiadas para enumerarlas: los nombres disponibles; el resto se construye con query_actions.
 */
export interface LegalProgressive {
  kind: "progressive";
  names: string[];
}

/**
 * Tiempo en milisegundos al enviar el mensaje: lo que le queda a cada asiento (null si su reloj no
 * corre) y qué asientos tienen el reloj en marcha.
 */
export interface Clocks {
  kind: "move" | "match";
  remaining_ms: (number | null)[];
  running: Seat[];
}

/**
 * Azar verificable (esquema gamehub-fair/1): el compromiso se publica antes de empezar; server_seed
 * y seed se revelan al terminar.
 */
export interface Fairness {
  scheme: "gamehub-fair/1";
  commitment: string;
  client_seeds: string[];
  server_seed?: string;
  seed?: number;
}

export interface SeatPlayer {
  seat: Seat;
  name: Name;
  kind: "human" | "bot";
}

export interface ClientInfo {
  name: string;
  version?: string;
  kind: "human" | "bot";
}

export interface ServerRef {
  name: string;
  version: string;
}

export interface Sender {
  participant: string;
  name: Name;
  seat: Seat | null;
}

/**
 * Primer mensaje de cada conexión. Con `token`, retoma la sesión (reconexión): el servidor reenvía
 * la sala y la partida; con `resume`, solo las actualizaciones que faltan.
 */
export interface Hello {
  client: ClientInfo;
  token?: string;
  resume?: Resume;
  /**
   * Cuántas acciones legales enumerar como mucho en cada update (por defecto 256); por encima,
   * construcción progresiva.
   */
  legal_limit?: number;
}

/** Última actualización recibida antes de perder la conexión. */
export interface Resume {
  match: string;
  seq: number;
}

/**
 * Entrar en una sala como jugador (en el asiento pedido o en el primero libre) o como espectador.
 */
export interface Join {
  room: string;
  role: "player" | "spectator";
  name: Name;
  seat?: Seat;
}

/** Sentarse (o cambiar de asiento) en el lobby. */
export interface Sit {
  seat?: Seat;
}

/** Listo (o no) para empezar; `seed` es la semilla que aporta el jugador al azar de la partida. */
export interface Ready {
  ready: boolean;
  seed?: string;
}

/**
 * Jugar una acción. `seq` es la última actualización vista: se rechaza si es anterior al comienzo
 * del turno vigente del asiento.
 */
export interface Act {
  seq: number;
  action: ActionData;
}

/**
 * Construcción progresiva: sin `name`, los nombres de acción disponibles; con `name` y los primeros
 * argumentos, los valores posibles del siguiente.
 */
export interface QueryActions {
  seq: number;
  name?: string;
  args?: JsonObject;
}

export interface ChatSend {
  text: string;
}

export interface Ping {
  t?: number;
}

/**
 * Solo el anfitrión y en el lobby: número de jugadores, opciones del juego y configuración de la
 * sala.
 */
export interface Configure {
  players?: number;
  params?: JsonObject;
  settings?: SettingsPatch;
}

/**
 * Solo el anfitrión: abrir un asiento, reservarlo para un nombre o ponerle un bot del servidor
 * (también en partida: el bot sustituye a quien ocupaba el asiento).
 */
export interface SetSeat {
  seat: Seat;
  kind: "open" | "reserved" | "bot";
  name?: Name;
  bot?: BotKind;
}

/** Solo el anfitrión: echar a un participante de la sala. */
export interface Kick {
  participant: string;
}

export interface Welcome {
  server: ServerRef;
  session?: Session;
}

/** Respuesta a `join`: el token de sesión (guárdalo para reconectar) y quién eres. */
export interface Joined {
  token: string;
  session: Session;
}

export interface MatchStart {
  match: MatchRef;
  seat: Seat | null;
  players: number;
  params: JsonObject;
  seats: SeatPlayer[];
  fairness: Fairness;
  clock: Clock;
}

/**
 * Lo que ha pasado desde la actualización anterior (una acción y el azar que la sigue) y el estado
 * resultante, proyectado para el destinatario.
 */
export interface Update {
  seq: number;
  view: View;
  events: GameEvent[];
  legal?: Legal;
  clocks?: Clocks;
}

/** Respuesta a query_actions. */
export interface Actions {
  seq: number;
  name?: string;
  args?: JsonObject;
  options: Json[];
}

/** Una acción que no se ha aplicado. */
export interface Rejected {
  seq: number | null;
  reason: "illegal_action" | "stale_seq" | "not_your_turn" | "not_running";
  detail: string;
}

/**
 * Fin de la partida: resultado, vista completa, semilla revelada y el replay (GET
 * /api/v1/replays/{replay}).
 */
export interface MatchEnd {
  match: MatchRef;
  reason: EndReason;
  payoffs: ExactNumber[] | null;
  ranking: number[];
  forfeited: Seat[];
  view: View;
  fairness: Fairness;
  replay: string;
}

export interface Chat {
  sender: Sender;
  text: string;
}

export interface Pong {
  t?: number;
  /** Segundos desde la época Unix. */
  server_time: number;
}

export interface ErrorInfo {
  code:
    | "bad_message"
    | "unsupported"
    | "unknown_room"
    | "room_full"
    | "seat_taken"
    | "not_allowed"
    | "not_host"
    | "invalid_token"
    | "wrong_state"
    | "invalid_params"
    | "rate_limited"
    | "replaced"
    | "internal";
  message: string;
}

export interface HelloMessage {
  v: 1;
  type: "hello";
  id?: MessageId;
  data: Hello;
}

export interface JoinMessage {
  v: 1;
  type: "join";
  id?: MessageId;
  data: Join;
}

export interface SitMessage {
  v: 1;
  type: "sit";
  id?: MessageId;
  data: Sit;
}

/** Levantarse del asiento en el lobby (se queda como espectador). */
export interface StandMessage {
  v: 1;
  type: "stand";
  id?: MessageId;
  data: Empty;
}

/** Salir de la sala (en partida, equivale a abandonar). */
export interface LeaveMessage {
  v: 1;
  type: "leave";
  id?: MessageId;
  data: Empty;
}

export interface ReadyMessage {
  v: 1;
  type: "ready";
  id?: MessageId;
  data: Ready;
}

export interface ActMessage {
  v: 1;
  type: "act";
  id?: MessageId;
  data: Act;
}

export interface QueryActionsMessage {
  v: 1;
  type: "query_actions";
  id?: MessageId;
  data: QueryActions;
}

/** Abandonar la partida: un bot juega por el asiento, que queda el último. */
export interface ResignMessage {
  v: 1;
  type: "resign";
  id?: MessageId;
  data: Empty;
}

export interface ChatSendMessage {
  v: 1;
  type: "chat";
  id?: MessageId;
  data: ChatSend;
}

export interface PingMessage {
  v: 1;
  type: "ping";
  id?: MessageId;
  data: Ping;
}

/** Pedir de nuevo la sala y el estado completo. */
export interface ResyncMessage {
  v: 1;
  type: "resync";
  id?: MessageId;
  data: Empty;
}

export interface ConfigureMessage {
  v: 1;
  type: "configure";
  id?: MessageId;
  data: Configure;
}

export interface SetSeatMessage {
  v: 1;
  type: "set_seat";
  id?: MessageId;
  data: SetSeat;
}

export interface KickMessage {
  v: 1;
  type: "kick";
  id?: MessageId;
  data: Kick;
}

export interface WelcomeMessage {
  v: 1;
  type: "welcome";
  re?: MessageId;
  data: Welcome;
}

export interface JoinedMessage {
  v: 1;
  type: "joined";
  re?: MessageId;
  data: Joined;
}

export interface RoomMessage {
  v: 1;
  type: "room";
  re?: MessageId;
  data: Room;
}

export interface MatchStartMessage {
  v: 1;
  type: "match_start";
  re?: MessageId;
  data: MatchStart;
}

export interface UpdateMessage {
  v: 1;
  type: "update";
  re?: MessageId;
  data: Update;
}

export interface ActionsMessage {
  v: 1;
  type: "actions";
  re?: MessageId;
  data: Actions;
}

export interface RejectedMessage {
  v: 1;
  type: "rejected";
  re?: MessageId;
  data: Rejected;
}

export interface MatchEndMessage {
  v: 1;
  type: "match_end";
  re?: MessageId;
  data: MatchEnd;
}

export interface ChatMessage {
  v: 1;
  type: "chat";
  re?: MessageId;
  data: Chat;
}

export interface PongMessage {
  v: 1;
  type: "pong";
  re?: MessageId;
  data: Pong;
}

export interface ErrorMessage {
  v: 1;
  type: "error";
  re?: MessageId;
  data: ErrorInfo;
}

/**
 * POST /api/v1/rooms: un juego del catálogo del servidor (`game`) o una IR completa (`ir`, si el
 * servidor lo permite).
 */
export interface CreateRoom {
  game?: string;
  ir?: JsonObject;
  players?: number;
  params?: JsonObject;
  settings?: SettingsPatch;
  name?: Name;
}

/** Respuesta de POST /api/v1/rooms: `token` es la sesión del anfitrión (hello con ese token). */
export interface CreatedRoom {
  code: RoomCode;
  token: string;
  url: string;
  room: Room;
}

/** GET /api/v1/info. */
export interface ServerInfo {
  name: string;
  version: string;
  protocol: 1;
  upload: boolean;
  games: GameInfo[];
  rooms: number;
}

/** GET /api/v1/rooms: salas públicas (no privadas) y abiertas. */
export interface RoomList {
  rooms: Room[];
}

/** Cuerpo de las respuestas de error de la API REST. */
export interface ApiError {
  error: ErrorInfo;
}
