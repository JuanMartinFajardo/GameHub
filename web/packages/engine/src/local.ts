// SPDX-License-Identifier: Apache-2.0
/**
 * Partidas en el navegador sin servidor: una «mesa» local que hace lo que la partida del servidor
 * (`gamehub.server.match`) —actualizaciones numeradas con la jugada y todo el azar que la sigue,
 * acciones legales enumeradas o progresivas, bots, resultado y puestos— y un cliente por asiento
 * con la misma interfaz que `GameClient`, cuyo estado sale del mismo `reduce` con los mismos
 * mensajes del protocolo. Las UIs (genérica o propias) no notan la diferencia.
 */

import { type ClientState, initialState, reduce } from "@gamehub/client";
import type {
  ActionData,
  GameInfo,
  MatchEnd,
  MatchStart,
  Rejected,
  SeatPlayer,
  ServerMessage,
  Update,
} from "@gamehub/protocol";
import { type BotKind, type CoreGame, type CoreSession, EngineError } from "./core";

/** Cuántas acciones legales se enumeran como mucho en cada actualización (como el servidor). */
export const DEFAULT_LEGAL_LIMIT = 256;

export interface LocalSeat {
  name: string;
  /** Sin bot, el asiento lo juega una persona en este dispositivo. */
  bot?: BotKind;
}

export interface LocalTableOptions {
  game: CoreGame;
  /** La mesa libera el juego al liberarse ella. */
  ownsGame?: boolean;
  /** Lo que el protocolo dice del juego (id, versión, título…). */
  info: GameInfo;
  /** Un asiento por jugador. */
  seats: LocalSeat[];
  params?: Record<string, unknown>;
  /** La semilla de la primera partida (al azar si no se indica; las siguientes, al azar). */
  seed?: number;
  legalLimit?: number;
  /** Pausa antes de cada jugada de un bot, en milisegundos. */
  botDelay?: number;
  /** Simulaciones de los bots MCTS… */
  simulations?: number;
  /** …y segundos como mucho por jugada (en juegos largos, cada simulación cuesta más). */
  thinkSeconds?: number;
}

interface Batch {
  seq: number;
  /** El primer paso de la sesión que incluye (0 = la preparación). */
  first: number;
}

function randomSeed(): number {
  const word = new Uint32Array(1);
  globalThis.crypto.getRandomValues(word);
  return word[0] ?? 0;
}

/** Puestos finales (como `final_ranking` del servidor, sin abandonos). */
function finalRanking(n: number, base: number[] | null): number[] {
  return Array.from(
    { length: n },
    (_, s) => 1 + (base === null ? 0 : base.filter((r) => r < (base[s] ?? 0)).length),
  );
}

/** Una mesa: una partida tras otra con los mismos asientos. */
export class LocalTable {
  readonly game: CoreGame;
  private readonly ownsGame: boolean;
  readonly info: GameInfo;
  readonly seats: LocalSeat[];
  readonly params: Record<string, unknown>;
  private readonly legalLimit: number;
  private readonly botDelay: number;
  private readonly simulations: number;
  private readonly thinkSeconds: number;
  private readonly clients = new Map<number, LocalClient>();
  private session: CoreSession | null = null;
  private batches: Batch[] = [];
  private number = 0;
  private seed: number;
  private ended = false;
  private readonly ready = new Set<number>();
  private botTimer: ReturnType<typeof setTimeout> | null = null;
  private disposed = false;
  private counter = 0;

  constructor(options: LocalTableOptions) {
    this.game = options.game;
    this.ownsGame = options.ownsGame ?? false;
    this.info = options.info;
    this.seats = options.seats;
    this.params = options.params ?? {};
    this.legalLimit = options.legalLimit ?? DEFAULT_LEGAL_LIMIT;
    this.botDelay = options.botDelay ?? 400;
    this.simulations = options.simulations ?? 2000;
    this.thinkSeconds = options.thinkSeconds ?? 1;
    this.seed = options.seed ?? randomSeed();
    // Comprueba ya los parámetros (lanza EngineError "params").
    this.game.session(this.seats.length, this.params, 0).dispose();
    const host = this.seats.findIndex((s) => s.bot === undefined);
    this.seats.forEach((seat, i) => {
      if (seat.bot === undefined)
        this.clients.set(i, new LocalClient(this, i, seat.name, i === host));
    });
  }

  /** El cliente de un asiento humano. */
  client(seat: number): LocalClient {
    const c = this.clients.get(seat);
    if (c === undefined) throw new Error(`el asiento ${seat} no es de una persona`);
    return c;
  }

  /** Los asientos que juegan personas en este dispositivo. */
  humans(): number[] {
    return [...this.clients.keys()];
  }

  get running(): boolean {
    return this.session !== null && !this.ended;
  }

  /** La sesión de la partida en curso (para depurar o para el simulador). */
  get current(): CoreSession | null {
    return this.session;
  }

  /** La semilla de la partida en curso. */
  get matchSeed(): number {
    return this.seed;
  }

  /** Empieza una partida (la primera, o la siguiente cuando todos están listos). */
  start(): void {
    if (this.disposed) return;
    this.stopBots();
    this.session?.dispose();
    this.number += 1;
    if (this.number > 1) this.seed = randomSeed();
    this.session = this.game.session(this.seats.length, this.params, this.seed);
    this.batches = [];
    this.ended = false;
    this.ready.clear();
    const players: SeatPlayer[] = this.seats.map((s, seat) => ({
      seat,
      name: s.name,
      kind: s.bot === undefined ? "human" : "bot",
    }));
    for (const [seat, client] of this.clients) {
      const start: MatchStart = {
        match: this.matchRef(),
        seat,
        players: this.seats.length,
        params: this.params,
        seats: players,
        fairness: this.fairness(false),
        clock: { kind: "none" },
      };
      client.deliver({ v: 1, type: "match_start", data: start });
    }
    this.step(0);
  }

  // --- jugadas ----------------------------------------------------------------------------------

  /** Una jugada de un asiento humano (la valida como el servidor). */
  act(seat: number, action: ActionData, re: string): void {
    const session = this.session;
    const reject = (reason: Rejected["reason"], detail: string) =>
      this.clients.get(seat)?.deliver({
        v: 1,
        type: "rejected",
        re,
        data: { seq: this.seq, reason, detail },
      });
    if (session === null || this.ended) {
      reject("not_running", "la partida ha terminado");
      return;
    }
    if (!session.activeSeats().includes(seat)) {
      reject("not_your_turn", `el asiento ${seat} no puede actuar ahora`);
      return;
    }
    const first = session.depth + 1;
    try {
      session.act(seat, action);
    } catch (error) {
      if (error instanceof EngineError && error.kind !== "rule") {
        reject("illegal_action", error.message);
      } else {
        this.abort(error);
      }
      return;
    }
    this.step(first);
  }

  /** Construcción progresiva de una acción (`query_actions`). */
  options(seat: number, name?: string, args?: Record<string, unknown>): unknown[] {
    const session = this.session;
    if (session === null || this.ended || !session.activeSeats().includes(seat)) return [];
    if (name === "pass") return [];
    return session.options(seat, name, args);
  }

  /** Un asiento humano está listo para la siguiente partida. */
  markReady(seat: number, ready: boolean): void {
    if (ready) this.ready.add(seat);
    else this.ready.delete(seat);
    const all = this.humans().every((s) => this.ready.has(s));
    if (all && (this.session === null || this.ended)) this.start();
  }

  /** Un cliente se cierra; cuando se han cerrado todos, la mesa se libera. */
  release(seat: number): void {
    this.clients.delete(seat);
    if (this.clients.size === 0) this.dispose();
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.stopBots();
    this.session?.dispose();
    this.session = null;
    if (this.ownsGame) this.game.dispose();
  }

  nextId(): string {
    this.counter += 1;
    return `local-${this.counter}`;
  }

  // --- internos ---------------------------------------------------------------------------------

  private get seq(): number {
    return this.batches.at(-1)?.seq ?? 0;
  }

  private matchRef() {
    return { id: `local-${this.number}`, number: this.number };
  }

  private fairness(reveal: boolean) {
    // Sin servidor no hay compromiso que verificar: solo la semilla (se revela al terminar).
    return reveal
      ? { scheme: "gamehub-fair/1" as const, commitment: "", client_seeds: [], seed: this.seed }
      : { scheme: "gamehub-fair/1" as const, commitment: "", client_seeds: [] };
  }

  /** El azar que sigue a una jugada, hasta la siguiente decisión o el final. */
  private advance(): void {
    const session = this.session;
    while (session !== null && session.status === "chance") session.chance();
  }

  private close(first: number): void {
    const session = this.session;
    if (session === null) return;
    const batch: Batch = { seq: this.batches.length, first };
    this.batches.push(batch);
    this.ended = session.terminal;
    const active = this.ended ? [] : session.activeSeats();
    for (const [seat, client] of this.clients) {
      const update: Update = {
        seq: batch.seq,
        view: session.view(seat),
        events: session.eventsFrom(first, seat),
      };
      if (active.includes(seat)) update.legal = this.legal(session, seat);
      client.deliver({ v: 1, type: "update", data: update });
    }
    if (this.ended) {
      this.finish(session);
      return;
    }
    if (active.some((s) => this.seats[s]?.bot !== undefined)) this.scheduleBots();
  }

  private legal(session: CoreSession, seat: number): Update["legal"] {
    const { actions, truncated } = session.legal(seat, this.legalLimit);
    if (truncated) {
      return { kind: "progressive", names: session.options(seat) as string[] };
    }
    return { kind: "enumerated", actions };
  }

  private finish(session: CoreSession): void {
    this.stopBots();
    const end: MatchEnd = {
      match: this.matchRef(),
      reason: "terminal",
      payoffs: session.payoffs(),
      ranking: finalRanking(this.seats.length, session.ranking()),
      forfeited: [],
      view: session.view("omniscient"),
      fairness: this.fairness(true),
      replay: "",
    };
    for (const client of this.clients.values()) {
      client.deliver({ v: 1, type: "match_end", data: end });
    }
  }

  private scheduleBots(): void {
    if (this.botTimer !== null || this.disposed) return;
    this.botTimer = setTimeout(() => {
      this.botTimer = null;
      this.playBots();
    }, this.botDelay);
  }

  private stopBots(): void {
    if (this.botTimer !== null) clearTimeout(this.botTimer);
    this.botTimer = null;
  }

  /** Juega el primer bot activo (los demás, en las siguientes vueltas). */
  private playBots(): void {
    const session = this.session;
    if (session === null || this.ended) return;
    const seat = session.activeSeats().find((s) => this.seats[s]?.bot !== undefined);
    if (seat === undefined) return;
    const kind = this.seats[seat]?.bot ?? "random";
    const first = session.depth + 1;
    try {
      session.act(seat, session.botAction(seat, kind, this.simulations, this.thinkSeconds));
    } catch (error) {
      this.abort(error);
      return;
    }
    this.step(first);
  }

  /** Tras una jugada: el azar que la sigue y la actualización. */
  private step(first: number): void {
    try {
      this.advance();
    } catch (error) {
      this.abort(error);
      return;
    }
    this.close(first);
  }

  /** Un error de las reglas: la partida se interrumpe (como en el servidor). */
  private abort(error: unknown): void {
    const session = this.session;
    if (session === null || this.ended) return;
    this.ended = true;
    this.stopBots();
    const detail = error instanceof Error ? error.message : String(error);
    const message = `error en las reglas del juego, partida anulada: ${detail}`;
    const end: MatchEnd = {
      match: this.matchRef(),
      reason: "aborted",
      payoffs: null,
      ranking: finalRanking(this.seats.length, null),
      forfeited: [],
      view: session.view("omniscient"),
      fairness: this.fairness(true),
      replay: "",
    };
    for (const client of this.clients.values()) {
      client.deliver({ v: 1, type: "error", data: { code: "internal", message } });
      client.deliver({ v: 1, type: "match_end", data: end });
    }
  }
}

type Listener = () => void;

/** El cliente de un asiento: la interfaz de `GameClient` que usan las UIs para jugar. */
export class LocalClient {
  private state: ClientState;
  private readonly listeners = new Set<Listener>();
  private closed = false;

  constructor(
    readonly table: LocalTable,
    readonly seat: number,
    readonly name: string,
    host: boolean,
  ) {
    this.state = {
      ...initialState,
      status: "connected",
      server: { name: "local", version: "wasm" },
      session: {
        room: "LOCAL",
        participant: `local-${seat}`,
        name,
        role: "player",
        seat,
        host,
      },
    };
  }

  getState = (): ClientState => this.state;

  subscribe = (listener: Listener): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  get seq(): number {
    return this.state.match?.update?.seq ?? 0;
  }

  /** Recibe un mensaje de la mesa (como si llegara del servidor). */
  deliver(msg: ServerMessage): void {
    if (this.closed) return;
    const next = reduce(this.state, msg);
    if (next === this.state) return;
    this.state = next;
    for (const listener of this.listeners) listener();
  }

  /** Juega una acción; el resultado llega como actualización o como `rejected`. */
  act(action: ActionData, seq?: number): string {
    const id = this.table.nextId();
    const at = seq ?? this.seq;
    const match = this.state.match;
    if (match !== null) {
      const pending = { id, seq: at, action };
      this.state = { ...this.state, match: { ...match, pending, rejected: null } };
      for (const listener of this.listeners) listener();
    }
    // Como por la red: después de volver (las UIs actualizan su estado antes).
    queueMicrotask(() => this.table.act(this.seat, action, id));
    return id;
  }

  async queryActions(name?: string, args?: Record<string, unknown>): Promise<unknown[]> {
    return this.table.options(this.seat, name, args);
  }

  ready(ready = true): string {
    const id = this.table.nextId();
    queueMicrotask(() => this.table.markReady(this.seat, ready));
    return id;
  }

  close(): void {
    if (this.closed) return;
    this.closed = true;
    this.state = { ...this.state, status: "closed" };
    for (const listener of this.listeners) listener();
    this.listeners.clear();
    this.table.release(this.seat);
  }
}
