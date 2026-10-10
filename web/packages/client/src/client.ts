// SPDX-License-Identifier: Apache-2.0
/**
 * Cliente del protocolo de partidas: una conexión WebSocket que sigue el estado de la sala y la
 * partida y se reconecta sola (como el SDK de Python).
 *
 *     const client = new GameClient({ server: "http://192.168.1.20:7420", name: "Ana" });
 *     await client.connect();
 *     await client.join("K7F-Q2P");
 *     client.ready();
 *     client.subscribe(() => {
 *       const state = client.getState();     // inmutable: vale para useSyncExternalStore
 *       const legal = legalOf(state);
 *       if (legal?.kind === "enumerated") client.act(legal.actions[0]);
 *     });
 *
 * Si se corta la conexión y hay sesión, vuelve a conectar con espera creciente y retoma con el
 * último `seq` visto (`resume`): el servidor reenvía solo lo que faltaba.
 */

import {
  type ActionData,
  type BotKind,
  type ClientData,
  type ClientMessageType,
  type Configure,
  clientMessage,
  type Hello,
  type Joined,
  normalizeCode,
  PROTOCOL_VERSION,
  type ServerMessage,
  type ServerMessageOf,
  type ServerMessageType,
  type Welcome,
} from "@gamehub/protocol";
import { endpoints } from "./endpoints";
import { ClientError } from "./errors";
import { type ClientState, type ConnectionStatus, initialState, reduce } from "./state";

/** Lo mínimo de un WebSocket (el del navegador o el global de Node 22, o uno falso en tests). */
export interface WebSocketLike {
  readonly readyState: number;
  onopen: ((event: unknown) => void) | null;
  onmessage: ((event: { data: unknown }) => void) | null;
  onclose: ((event: { code: number; reason: string }) => void) | null;
  onerror: ((event: unknown) => void) | null;
  send(data: string): void;
  close(code?: number, reason?: string): void;
}

export type WebSocketFactory = (url: string) => WebSocketLike;

export interface GameClientOptions {
  /** Servidor: `http://192.168.1.20:7420`, `host:7420`, un enlace de sala… "" = el origen. */
  server?: string;
  /** Nombre en la sala (hasta 32 caracteres). */
  name?: string;
  kind?: "human" | "bot";
  /** Cuántas acciones legales enumerar como mucho; por encima, construcción progresiva. */
  legalLimit?: number;
  /** Token de una sesión anterior, para retomarla. */
  token?: string | null;
  /** Reconectar solo si se corta la conexión (por defecto, sí). */
  reconnect?: boolean;
  /** Milisegundos para conectar y para cada respuesta (por defecto 10 000). */
  timeout?: number;
  /** Milisegundos intentando reconectar antes de rendirse (por defecto 120 000). */
  reconnectFor?: number;
  /** Cada cuántos milisegundos comprobar que la conexión sigue viva (0 = nunca; 20 000). */
  heartbeat?: number;
  /** Nombre y versión del programa cliente en el `hello`. */
  clientName?: string;
  clientVersion?: string;
  webSocket?: WebSocketFactory;
}

type Listener = () => void;
export type MessageListener = (msg: ServerMessage, state: ClientState) => void;

interface Waiting {
  expect: ReadonlySet<string>;
  tolerate: ReadonlySet<string>;
  resolve: (msg: ServerMessage) => void;
  reject: (error: ClientError) => void;
  timer: ReturnType<typeof setTimeout>;
}

const OPEN = 1;

function defaultWebSocket(url: string): WebSocketLike {
  if (typeof WebSocket === "undefined") {
    throw new ClientError("connection", "este entorno no tiene WebSocket");
  }
  return new WebSocket(url) as unknown as WebSocketLike;
}

function randomPrefix(): string {
  const bytes = new Uint8Array(4);
  crypto.getRandomValues(bytes);
  return [...bytes].map((b) => b.toString(16).padStart(2, "0")).join("");
}

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

export class GameClient {
  readonly http: string;
  readonly wsUrl: string;
  /** El código de sala si la dirección del servidor era un enlace de sala. */
  readonly roomCode: string | null;
  name: string;
  readonly kind: "human" | "bot";
  readonly legalLimit: number;
  readonly reconnect: boolean;

  private state: ClientState;
  private ws: WebSocketLike | null = null;
  private readonly listeners = new Set<Listener>();
  private readonly messageListeners = new Set<MessageListener>();
  private readonly waiting = new Map<string, Waiting>();
  // Los ids de mensaje son únicos en toda la sesión, también entre pestañas o procesos que la
  // retoman con el mismo token: el servidor descarta un `act` con un id ya visto.
  private readonly prefix = randomPrefix();
  private counter = 0;
  private closedByUser = false;
  private resyncAsked = false;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private lastSeen = 0;
  private readonly options: Required<
    Pick<GameClientOptions, "timeout" | "reconnectFor" | "heartbeat" | "clientName">
  > &
    Pick<GameClientOptions, "clientVersion" | "webSocket">;

  constructor(options: GameClientOptions = {}) {
    const where = endpoints(options.server ?? "");
    this.http = where.http;
    this.wsUrl = where.ws;
    this.roomCode = where.code;
    this.name = (options.name ?? "Anónimo").trim().slice(0, 32) || "Anónimo";
    this.kind = options.kind ?? "human";
    this.legalLimit = options.legalLimit ?? 500;
    this.reconnect = options.reconnect ?? true;
    this.options = {
      timeout: options.timeout ?? 10_000,
      reconnectFor: options.reconnectFor ?? 120_000,
      heartbeat: options.heartbeat ?? 20_000,
      clientName: options.clientName ?? "gamehub-web",
      clientVersion: options.clientVersion,
      webSocket: options.webSocket,
    };
    this.state = { ...initialState, token: options.token ?? null };
  }

  // --- estado ---------------------------------------------------------------------------------

  /** El estado actual (un objeto nuevo en cada cambio; el mismo si no cambia nada). */
  getState = (): ClientState => this.state;

  /** Avisa de cada cambio de estado. Devuelve la función para dejar de escuchar. */
  subscribe = (listener: Listener): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  /** Cada mensaje del servidor, ya incorporado al estado (para animaciones, sonidos…). */
  onMessage(listener: MessageListener): () => void {
    this.messageListeners.add(listener);
    return () => this.messageListeners.delete(listener);
  }

  get token(): string | null {
    return this.state.token;
  }

  get seq(): number {
    return this.state.match?.update?.seq ?? 0;
  }

  // --- conexión -------------------------------------------------------------------------------

  /** Conecta y saluda (retomando la sesión si hay token). Devuelve los datos de `welcome`. */
  async connect(): Promise<Welcome> {
    this.closedByUser = false;
    this.setStatus("connecting");
    try {
      await this.open();
      const msg = await this.request("hello", this.hello(), ["welcome"], ["invalid_token"]);
      this.setStatus("connected");
      return msg.data;
    } catch (error) {
      this.setStatus("closed");
      this.ws?.close();
      throw error;
    }
  }

  /** Cierra la conexión (sin salir de la sala: el token sigue valiendo para volver). */
  close(): void {
    this.closedByUser = true;
    this.stopHeartbeat();
    this.failWaiting(new ClientError("closed", "conexión cerrada"));
    this.ws?.close(1000);
    this.ws = null;
    this.setStatus("closed");
  }

  // --- peticiones -----------------------------------------------------------------------------

  /** Entra en una sala (la del enlace del servidor si no se indica). */
  async join(
    room?: string,
    options: { role?: "player" | "spectator"; seat?: number; name?: string } = {},
  ): Promise<Joined> {
    const code = normalizeCode(room ?? this.roomCode ?? "");
    if (code === null) throw new ClientError("unknown_room", "código de sala no válido");
    if (options.name !== undefined) this.name = options.name.trim().slice(0, 32) || this.name;
    const data: ClientData<"join"> = {
      room: code,
      role: options.role ?? "player",
      name: this.name,
    };
    if (options.seat !== undefined) data.seat = options.seat;
    const msg = await this.request("join", data, ["joined"]);
    return msg.data;
  }

  ready(ready = true, seed?: string): string {
    return this.send("ready", seed === undefined ? { ready } : { ready, seed });
  }

  /**
   * Juega una acción (con el `seq` de la última actualización si no se indica). Devuelve el id
   * del mensaje; si no se aplica, el estado recoge el `rejected` en `match.rejected`.
   */
  act(action: ActionData, seq?: number): string {
    const at = seq ?? this.seq;
    const id = this.send("act", { seq: at, action });
    const match = this.state.match;
    if (match !== null) {
      this.setState({
        ...this.state,
        match: { ...match, pending: { id, seq: at, action }, rejected: null },
      });
    }
    return id;
  }

  /** Construcción progresiva: sin nombre, los nombres; con nombre y argumentos, los valores del
   * siguiente argumento. */
  async queryActions(name?: string, args?: Record<string, unknown>): Promise<unknown[]> {
    const data: ClientData<"query_actions"> = { seq: this.seq };
    if (name !== undefined) data.name = name;
    if (args !== undefined) data.args = args;
    const msg = await this.request("query_actions", data, ["actions"]);
    return msg.data.options;
  }

  sit(seat?: number): string {
    return this.send("sit", seat === undefined ? {} : { seat });
  }

  stand(): string {
    return this.send("stand", {});
  }

  /** Sale de la sala (en partida, abandona). La sesión deja de existir. */
  leave(): string {
    const id = this.send("leave", {});
    this.setState({ ...this.state, token: null, session: null, room: null, match: null });
    return id;
  }

  resign(): string {
    return this.send("resign", {});
  }

  chat(text: string): string {
    return this.send("chat", { text });
  }

  resync(): string {
    return this.send("resync", {});
  }

  configure(data: Configure): string {
    return this.send("configure", data);
  }

  setSeat(
    seat: number,
    kind: "open" | "reserved" | "bot",
    extra: { name?: string; bot?: BotKind } = {},
  ): string {
    return this.send("set_seat", { seat, kind, ...extra });
  }

  kick(participant: string): string {
    return this.send("kick", { participant });
  }

  /** Ida y vuelta al servidor, en milisegundos. */
  async ping(): Promise<number> {
    const t = Date.now();
    await this.request("ping", { t }, ["pong"]);
    return Date.now() - t;
  }

  /** Envía un mensaje sin esperar respuesta. Devuelve su id. */
  send<T extends ClientMessageType>(type: T, data: ClientData<T>): string {
    const id = this.nextId();
    this.raw(clientMessage(type, data, id));
    return id;
  }

  /** Envía y espera la respuesta con su `re`. Un `error` rechaza la promesa con `ClientError`,
   * salvo los de `tolerate`, tras los que se sigue esperando. */
  request<T extends ClientMessageType, R extends ServerMessageType>(
    type: T,
    data: ClientData<T>,
    expect: readonly R[],
    tolerate: readonly string[] = [],
  ): Promise<ServerMessageOf<R>> {
    const id = this.nextId();
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.waiting.delete(id);
        reject(new ClientError("timeout", `el servidor no ha respondido a ${type}`));
      }, this.options.timeout);
      this.waiting.set(id, {
        expect: new Set<string>([...expect, "error"]),
        tolerate: new Set(tolerate),
        resolve: (msg) => resolve(msg as ServerMessageOf<R>),
        reject,
        timer,
      });
      try {
        this.raw(clientMessage(type, data, id));
      } catch (error) {
        clearTimeout(timer);
        this.waiting.delete(id);
        reject(error);
      }
    });
  }

  // --- internos -------------------------------------------------------------------------------

  private nextId(): string {
    this.counter += 1;
    return `${this.prefix}-${this.counter}`;
  }

  private hello(): Hello {
    const client: Hello["client"] = { name: this.options.clientName, kind: this.kind };
    if (this.options.clientVersion !== undefined) client.version = this.options.clientVersion;
    const data: Hello = { client, legal_limit: this.legalLimit };
    const { token, match } = this.state;
    if (token !== null) {
      data.token = token;
      if (match !== null && match.end === null && match.update !== null) {
        data.resume = { match: match.start.match.id, seq: match.update.seq };
      }
    }
    return data;
  }

  private raw(msg: object): void {
    const ws = this.ws;
    if (ws === null || ws.readyState !== OPEN) {
      throw new ClientError("connection", "no hay conexión con el servidor");
    }
    ws.send(JSON.stringify(msg));
  }

  private open(): Promise<void> {
    const factory = this.options.webSocket ?? defaultWebSocket;
    return new Promise((resolve, reject) => {
      let ws: WebSocketLike;
      try {
        ws = factory(this.wsUrl);
      } catch (error) {
        reject(new ClientError("connection", `no se puede conectar con ${this.http}: ${error}`));
        return;
      }
      let opened = false;
      const timer = setTimeout(() => {
        if (!opened) {
          ws.close();
          reject(new ClientError("timeout", `no se puede conectar con ${this.http}`));
        }
      }, this.options.timeout);
      ws.onopen = () => {
        opened = true;
        clearTimeout(timer);
        this.ws = ws;
        this.lastSeen = Date.now();
        this.startHeartbeat();
        resolve();
      };
      ws.onmessage = (event) => {
        if (this.ws === ws) this.receive(event.data);
      };
      ws.onerror = () => {
        // Le sigue siempre un `close`: ahí se decide qué hacer.
      };
      ws.onclose = () => {
        clearTimeout(timer);
        if (!opened) {
          reject(new ClientError("connection", `no se puede conectar con ${this.http}`));
        } else if (this.ws === ws) {
          this.lost();
        }
      };
    });
  }

  private receive(raw: unknown): void {
    this.lastSeen = Date.now();
    let msg: ServerMessage;
    try {
      msg = JSON.parse(String(raw)) as ServerMessage;
    } catch {
      return;
    }
    if (msg === null || typeof msg !== "object" || msg.v !== PROTOCOL_VERSION) return;
    this.dispatch(msg);
  }

  private dispatch(msg: ServerMessage): void {
    if (msg.type === "match_start") this.resyncAsked = false;
    this.setState(reduce(this.state, msg));
    const re = msg.re;
    const waiting = re === undefined ? undefined : this.waiting.get(re);
    if (waiting?.expect.has(msg.type)) {
      const tolerated = msg.type === "error" && waiting.tolerate.has(msg.data.code);
      if (!tolerated) {
        clearTimeout(waiting.timer);
        this.waiting.delete(re as string);
        if (msg.type === "error") waiting.reject(new ClientError(msg.data.code, msg.data.message));
        else waiting.resolve(msg);
      }
    }
    for (const listener of this.messageListeners) listener(msg, this.state);
    if (msg.type === "error" && msg.data.code === "replaced") {
      // La sesión se ha abierto en otra conexión (otra pestaña): esta ya no reconecta.
      this.closedByUser = true;
      this.stopHeartbeat();
      this.ws?.close(1000);
      this.ws = null;
    }
    if (this.state.stale && !this.resyncAsked && this.ws !== null) {
      this.resyncAsked = true;
      this.send("resync", {});
    }
  }

  private lost(): void {
    this.ws = null;
    this.stopHeartbeat();
    this.failWaiting(new ClientError("connection", "se ha perdido la conexión"));
    if (this.closedByUser || !this.reconnect || this.state.token === null) {
      this.setStatus("closed");
      return;
    }
    void this.again();
  }

  /** Reconecta con espera creciente y retoma la sesión. */
  private async again(): Promise<void> {
    this.setStatus("reconnecting");
    const deadline = Date.now() + this.options.reconnectFor;
    let delay = 250;
    while (!this.closedByUser && Date.now() < deadline) {
      await sleep(delay);
      delay = Math.min(delay * 2, 5000);
      if (this.closedByUser) return;
      try {
        await this.open();
        this.send("hello", this.hello());
      } catch {
        continue;
      }
      this.setStatus("connected");
      return;
    }
    if (!this.closedByUser) this.setStatus("closed");
  }

  private startHeartbeat(): void {
    this.stopHeartbeat();
    const every = this.options.heartbeat;
    if (every <= 0) return;
    this.heartbeatTimer = setInterval(() => {
      const ws = this.ws;
      if (ws === null) return;
      if (Date.now() - this.lastSeen > 2 * every) {
        // Nada del servidor en dos latidos: la conexión está muerta aunque no lo parezca.
        ws.close();
        if (this.ws === ws) this.lost();
        return;
      }
      try {
        this.send("ping", { t: Date.now() });
      } catch {
        // Se resolverá con el `close`.
      }
    }, every);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer !== null) clearInterval(this.heartbeatTimer);
    this.heartbeatTimer = null;
  }

  private failWaiting(error: ClientError): void {
    for (const waiting of this.waiting.values()) {
      clearTimeout(waiting.timer);
      waiting.reject(error);
    }
    this.waiting.clear();
  }

  private setStatus(status: ConnectionStatus): void {
    if (this.state.status !== status) this.setState({ ...this.state, status });
  }

  private setState(next: ClientState): void {
    if (next === this.state) return;
    this.state = next;
    for (const listener of this.listeners) listener();
  }
}
