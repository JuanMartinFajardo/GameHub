// SPDX-License-Identifier: Apache-2.0
/**
 * El núcleo C++ en WebAssembly: cargar el módulo, los juegos (desde su IR) y las sesiones de
 * partida. Todo lo que cruza a C++ va como JSON; aquí se tipa y los errores del motor se
 * convierten en `EngineError`.
 */

import type { ActionData, ExactNumber, GameEvent, View } from "@gamehub/protocol";
import type { MainModule, Game as RawGame, Session as RawSession } from "../wasm/gamehub-core.mjs";
import { NATIVE_PLUGINS } from "./natives.gen";

/** Qué falló: las reglas, una acción ilegal, los parámetros, algo no enumerable u otra cosa. */
export type EngineErrorKind = "rule" | "illegal" | "params" | "not_enumerable" | "error";

export class EngineError extends Error {
  constructor(
    message: string,
    readonly kind: EngineErrorKind,
  ) {
    super(message);
    this.name = "EngineError";
  }
}

/** Quién mira: un asiento, lo público (un espectador) o todo. */
export type Observer = number | "public" | "omniscient";

export type Status = "chance" | "decision" | "terminal";

/** Lee el contenido de una URL (por defecto con `fetch`; en Node, p. ej., con `readFile`). */
export type BytesLoader = (url: URL) => Promise<ArrayBuffer | Uint8Array>;

export interface EngineOptions {
  /** Cómo leer los plugins nativos (por defecto, `fetch`). */
  loadBytes?: BytesLoader;
}

export interface GameOptions {
  /** Usar los plugins nativos de la stdlib (por defecto sí). Sin ellos, la referencia. */
  natives?: boolean;
}

export interface PlayoutOptions {
  players: number;
  params?: Record<string, unknown>;
  seed?: number;
  games?: number;
  maxSteps?: number;
}

export interface PlayoutReport {
  games: number;
  completed: number;
  truncated: number;
  steps: number;
  /** (semilla, mensaje) de cada partida que acabó en un error de reglas. */
  errors: [number, string][];
  /** Huella de las partidas: la misma con cualquier motor que juegue las mismas. */
  fingerprint: string;
}

/** Las partidas al azar del Studio con su cobertura (como `gamehub.studio.sim.playouts`). */
export interface CoverageStats {
  games: number;
  finished: number;
  truncated: number;
  errors: { game: number; message: string; node: string | null }[];
  errorCount: number;
  length: { min: number | null; max: number | null; mean: number | null };
  payoffMean: (number | null)[];
  winRate: (number | null)[];
  /** Partidas en que todos quedan primeros. */
  drawRate: number | null;
  coverage: {
    nodes: Record<string, number>;
    actions: Record<string, number>;
    transitions: Record<string, number>;
  };
  seconds: number;
}

export interface CoverageOptions extends PlayoutOptions {
  /** Segundos como mucho (0 = sin límite). */
  timeLimit?: number;
}

interface RawCoverage {
  games: number;
  finished: number;
  truncated: number;
  errors: CoverageStats["errors"];
  lengths: { count: number; min?: number; max?: number; sum?: number };
  totals: string[];
  wins: number[];
  draws: number;
  coverage: CoverageStats["coverage"];
}

/** p/(q·k) redondeado una sola vez, como `float(Fraction(p, q) / k)` en Python. */
function exactRatio(fraction: string, k: number): number {
  const [p = "0", q = "1"] = fraction.split("/");
  const num = BigInt(p);
  const den = BigInt(q) * BigInt(k);
  const safe = BigInt(Number.MAX_SAFE_INTEGER);
  if ((num < 0n ? -num : num) <= safe && den <= safe) return Number(num) / Number(den);
  return Number(p) / Number(q) / k;
}

function addFractions(a: string, b: string): string {
  const [ap = "0", aq = "1"] = a.split("/");
  const [bp = "0", bq = "1"] = b.split("/");
  let p = BigInt(ap) * BigInt(bq) + BigInt(bp) * BigInt(aq);
  let q = BigInt(aq) * BigInt(bq);
  let [x, y] = [p < 0n ? -p : p, q];
  while (y !== 0n) [x, y] = [y, x % y];
  if (x > 1n) {
    p /= x;
    q /= x;
  }
  return q === 1n ? String(p) : `${p}/${q}`;
}

function mergeCounts(a: Record<string, number>, b: Record<string, number>) {
  const out = { ...a };
  for (const [k, v] of Object.entries(b)) out[k] = (out[k] ?? 0) + v;
  return out;
}

/** Junta dos tramos de partidas (el segundo empieza en la partida `offset`). */
function mergeCoverage(a: RawCoverage, b: RawCoverage, offset: number): RawCoverage {
  const lengths: RawCoverage["lengths"] = { count: a.lengths.count + b.lengths.count };
  const pick = (f: (x: number, y: number) => number, x?: number, y?: number) =>
    x === undefined ? y : y === undefined ? x : f(x, y);
  const min = pick(Math.min, a.lengths.min, b.lengths.min);
  const max = pick(Math.max, a.lengths.max, b.lengths.max);
  if (min !== undefined) lengths.min = min;
  if (max !== undefined) lengths.max = max;
  if (lengths.count) lengths.sum = (a.lengths.sum ?? 0) + (b.lengths.sum ?? 0);
  const errors = [...a.errors, ...b.errors.map((e) => ({ ...e, game: e.game + offset }))];
  return {
    games: a.games + b.games,
    finished: a.finished + b.finished,
    truncated: a.truncated + b.truncated,
    errors: errors.slice(0, 20),
    lengths,
    totals: a.totals.map((t, s) => addFractions(t, b.totals[s] ?? "0")),
    wins: a.wins.map((w, s) => w + (b.wins[s] ?? 0)),
    draws: a.draws + b.draws,
    coverage: {
      nodes: mergeCounts(a.coverage.nodes, b.coverage.nodes),
      actions: mergeCounts(a.coverage.actions, b.coverage.actions),
      transitions: mergeCounts(a.coverage.transitions, b.coverage.transitions),
    },
  };
}

function coverageStats(raw: RawCoverage, seconds: number): CoverageStats {
  const { finished, lengths } = raw;
  return {
    games: raw.games,
    finished,
    truncated: raw.truncated,
    errors: raw.errors,
    errorCount: raw.games - finished - raw.truncated,
    length: {
      min: lengths.min ?? null,
      max: lengths.max ?? null,
      mean: lengths.count ? (lengths.sum ?? 0) / lengths.count : null,
    },
    payoffMean: raw.totals.map((t) => (finished ? exactRatio(t, finished) : null)),
    winRate: raw.wins.map((w) => (finished ? w / finished : null)),
    drawRate: finished ? raw.draws / finished : null,
    coverage: raw.coverage,
    seconds: Math.round(seconds * 1000) / 1000,
  };
}

export interface LegalList {
  actions: ActionData[];
  /** Había más de las pedidas. */
  truncated: boolean;
}

/**
 * Bots: al azar, la primera legal, MCTS (ve el estado entero: solo con información perfecta) y los
 * de la F9, que usan la heurística del juego y, con información oculta, determinizaciones:
 * reglas de prioridad (`greedy`), alfa-beta, ISMCTS y PIMC.
 */
export type BotKind = "random" | "first" | "mcts" | "greedy" | "alphabeta" | "ismcts" | "pimc";

interface Reply {
  ok: boolean;
  kind?: EngineErrorKind;
  error?: string;
  [key: string]: unknown;
}

function unwrap<T extends object>(text: string): T & Reply {
  const reply = JSON.parse(text) as T & Reply;
  if (!reply.ok) throw new EngineError(reply.error ?? "error del motor", reply.kind ?? "error");
  return reply;
}

async function fetchBytes(url: URL): Promise<ArrayBuffer> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`no se ha podido cargar ${url}: ${response.status}`);
  return response.arrayBuffer();
}

/** Las funciones nativas que pide una IR ("std.poker.hand_value"…). */
export function nativeIds(ir: unknown): string[] {
  const functions = (ir as { functions?: { native?: string }[] }).functions ?? [];
  return functions.flatMap((f) => (typeof f.native === "string" ? [f.native] : []));
}

/** Un plugin nativo instanciado (ABI gamehub-native/1). */
interface Plugin {
  exports: Record<string, unknown>;
  memory: WebAssembly.Memory;
  buffer: number;
}

const BUFFER_WORDS = 16384;

type NativeFunction = (input: number, len: number, output: number) => number;

/** El módulo cargado. Se comparte: `loadEngine()` lo carga una sola vez. */
export class Engine {
  private readonly plugins = new Map<string, Promise<Plugin | null>>();
  private readonly functions: { plugin: Plugin; fn: NativeFunction }[] = [];
  private readonly loaded = new Map<string, Plugin | null>();

  constructor(
    readonly module: MainModule,
    private readonly loadBytes: BytesLoader = fetchBytes,
  ) {
    (module as unknown as { ghNatives: unknown }).ghNatives = {
      find: (id: string) => this.find(id),
      call: (handle: number, words: Int32Array) => this.call(handle, words),
    };
  }

  /** Un juego desde su IR (objeto o texto JSON). Carga antes los plugins nativos que use. */
  async game(ir: unknown, options: GameOptions = {}): Promise<CoreGame> {
    const text = typeof ir === "string" ? ir : JSON.stringify(ir);
    const natives = options.natives ?? true;
    if (natives) {
      const parsed = typeof ir === "string" ? (JSON.parse(ir) as unknown) : ir;
      const modules = new Set(nativeIds(parsed).map((id) => id.slice(0, id.lastIndexOf("."))));
      await Promise.all([...modules].map((m) => this.plugin(m)));
    }
    return this.gameSync(text, natives);
  }

  /** Como `game`, sin cargar plugins (usa los ya cargados). */
  gameSync(ir: string, natives = false): CoreGame {
    const raw = new this.module.Game(ir, natives);
    const error = raw.error();
    if (error) {
      raw.delete();
      const reply = JSON.parse(error) as Reply;
      throw new EngineError(reply.error ?? "IR inválida", reply.kind ?? "error");
    }
    return new CoreGame(this, raw);
  }

  private plugin(module: string): Promise<Plugin | null> {
    let found = this.plugins.get(module);
    if (found === undefined) {
      const url = NATIVE_PLUGINS[module]?.();
      found = url ? this.instantiate(url) : Promise.resolve(null);
      found.then(
        (p) => this.loaded.set(module, p),
        () => this.loaded.set(module, null),
      );
      this.plugins.set(module, found);
    }
    return found.catch(() => null);
  }

  private async instantiate(url: URL): Promise<Plugin> {
    const compiled = await WebAssembly.compile((await this.loadBytes(url)) as BufferSource);
    const instance = await WebAssembly.instantiate(compiled, {});
    const exports = instance.exports as Record<string, unknown>;
    const memory = exports.memory;
    const buffer = exports.gh_buffer;
    if (!(memory instanceof WebAssembly.Memory) || typeof buffer !== "function") {
      throw new Error(`${url}: no es un plugin gamehub-native/1`);
    }
    return { exports, memory, buffer: (buffer as () => number)() };
  }

  private find(id: string): number {
    const dot = id.lastIndexOf(".");
    const plugin = this.loaded.get(id.slice(0, dot));
    const fn = plugin?.exports[id.slice(dot + 1)];
    if (!plugin || typeof fn !== "function") return -1;
    this.functions.push({ plugin, fn: fn as NativeFunction });
    return this.functions.length - 1;
  }

  private call(handle: number, words: Int32Array): Int32Array | number {
    const entry = this.functions[handle];
    if (!entry) return -1;
    const { plugin, fn } = entry;
    const output = plugin.buffer + 4 * (BUFFER_WORDS / 2);
    new Int32Array(plugin.memory.buffer).set(words, plugin.buffer >> 2);
    let n: number;
    try {
      n = fn(plugin.buffer, words.length, output);
    } catch {
      return -1;
    }
    if (n < 0) return n;
    // La memoria del plugin puede haber crecido: se vuelve a mirar.
    return new Int32Array(plugin.memory.buffer).slice(output >> 2, (output >> 2) + n);
  }
}

let shared: Promise<Engine> | null = null;

/**
 * Carga el núcleo (una vez por página). Con `loadBytes`, también el binario se lee con él (en
 * Node o en tests); si no, lo descarga el propio módulo.
 */
export function loadEngine(options: EngineOptions = {}): Promise<Engine> {
  if (shared === null) {
    shared = (async () => {
      const { default: create } = await import("../wasm/gamehub-core.mjs");
      const settings: Record<string, unknown> = {};
      if (options.loadBytes) {
        const url = new URL("../wasm/gamehub-core.wasm", import.meta.url);
        const compiled = WebAssembly.compile((await options.loadBytes(url)) as BufferSource);
        settings.instantiateWasm = (
          imports: WebAssembly.Imports,
          done: (instance: WebAssembly.Instance, module: WebAssembly.Module) => void,
        ) => {
          compiled
            .then((module) => WebAssembly.instantiate(module, imports).then((i) => done(i, module)))
            .catch((error: unknown) => console.error(error));
          return {};
        };
      }
      return new Engine(await create(settings), options.loadBytes);
    })();
    shared.catch(() => {
      shared = null;
    });
  }
  return shared;
}

/** ¿Puede este entorno ejecutar WebAssembly? */
export function engineSupported(): boolean {
  return typeof WebAssembly === "object" && typeof WebAssembly.instantiate === "function";
}

/** Un juego cargado en el núcleo. Hay que liberarlo con `dispose()` al dejar de usarlo. */
export class CoreGame {
  readonly id: string;
  readonly title: string;
  readonly rulesHash: string;
  readonly minPlayers: number;
  readonly maxPlayers: number;
  /** ¿Usa algún plugin nativo (en vez de la implementación de referencia)? */
  readonly natives: boolean;

  constructor(
    readonly engine: Engine,
    readonly raw: RawGame,
  ) {
    this.id = raw.id();
    this.title = raw.title();
    this.rulesHash = raw.rulesHash();
    this.minPlayers = raw.minPlayers();
    this.maxPlayers = raw.maxPlayers();
    this.natives = raw.usesNatives();
  }

  /** Partidas aleatorias (las mismas que `gamehub fuzz` con la misma semilla). */
  playouts(options: PlayoutOptions): PlayoutReport {
    const reply = unwrap<PlayoutReport>(
      this.raw.playouts(
        options.players,
        JSON.stringify(options.params ?? {}),
        options.seed ?? 0,
        options.games ?? 100,
        options.maxSteps ?? 10_000,
      ),
    );
    const { ok: _ok, ...report } = reply;
    return report as PlayoutReport;
  }

  /**
   * Las partidas al azar del Studio: resultados, longitudes, errores y cobertura de nodos,
   * acciones y transiciones; las mismas partidas y las mismas cifras que en Python.
   */
  studioPlayouts(options: CoverageOptions): CoverageStats {
    const started = performance.now();
    const raw = this.rawCoverage(options, options.seed ?? 0, options.games ?? 100, 0);
    return coverageStats(raw, (performance.now() - started) / 1000);
  }

  /**
   * Lo mismo por tramos de `chunk` partidas, cediendo el hilo entre uno y otro (la partida g usa
   * la semilla `seed + g`, así que trocear no cambia el resultado).
   */
  async studioPlayoutsChunked(options: CoverageOptions, chunk = 250): Promise<CoverageStats> {
    const started = performance.now();
    const seed = options.seed ?? 0;
    const games = options.games ?? 100;
    const limit = options.timeLimit ?? 0;
    let total: RawCoverage | null = null;
    for (let done = 0; done < games; done += chunk) {
      const elapsed = (performance.now() - started) / 1000;
      if (limit > 0 && elapsed > limit) break;
      const part = this.rawCoverage(
        options,
        seed + done,
        Math.min(chunk, games - done),
        limit > 0 ? Math.max(limit - elapsed, 1e-9) : 0,
      );
      total = total === null ? part : mergeCoverage(total, part, done);
      if (part.games < Math.min(chunk, games - done)) break;
      await new Promise((resolve) => setTimeout(resolve, 0));
    }
    const empty = this.rawCoverage(options, seed, 0, 0);
    return coverageStats(total ?? empty, (performance.now() - started) / 1000);
  }

  private rawCoverage(
    options: CoverageOptions,
    seed: number,
    games: number,
    timeLimit: number,
  ): RawCoverage {
    const { ok: _ok, ...raw } = unwrap<RawCoverage>(
      this.raw.studioPlayouts(
        options.players,
        JSON.stringify(options.params ?? {}),
        seed,
        games,
        options.maxSteps ?? 10_000,
        timeLimit,
      ),
    );
    return raw;
  }

  /** Una partida nueva. `seed` decide el azar (el mismo que el servidor con esa semilla). */
  session(players: number, params: Record<string, unknown> = {}, seed = 0): CoreSession {
    const raw = new this.engine.module.Session(this.raw, players, JSON.stringify(params), seed);
    const error = raw.error();
    if (error) {
      raw.delete();
      unwrap(error);
    }
    return new CoreSession(this.engine, raw, players);
  }

  dispose(): void {
    if (!this.raw.isDeleted()) this.raw.delete();
  }
}

/**
 * Una partida en curso con su historia (para deshacer). El azar se sortea con el generador de la
 * sesión (`PCG32(semilla, STREAM_CHANCE)`, como el servidor) y los bots con uno por asiento.
 */
export class CoreSession {
  constructor(
    readonly engine: Engine,
    readonly raw: RawSession,
    readonly players: number,
  ) {}

  private observer(who: Observer): number {
    if (who === "public") return this.engine.module.PUBLIC;
    if (who === "omniscient") return this.engine.module.OMNISCIENT;
    return who;
  }

  get status(): Status {
    return this.raw.status() as Status;
  }

  get terminal(): boolean {
    return this.status === "terminal";
  }

  /** El nodo actual ("" si ninguno). */
  get node(): string {
    return this.raw.node();
  }

  /** Pasos aplicados desde la preparación. */
  get depth(): number {
    return this.raw.depth();
  }

  activeSeats(): number[] {
    return JSON.parse(this.raw.activeSeats()) as number[];
  }

  view(who: Observer): View {
    return JSON.parse(this.raw.view(this.observer(who))) as View;
  }

  /** Los eventos desde el paso `first` (0 = la preparación) hasta el actual, como los ve `who`. */
  eventsFrom(first: number, who: Observer): GameEvent[] {
    return JSON.parse(this.raw.eventsFrom(first, this.observer(who))) as GameEvent[];
  }

  /** La instantánea canónica (JSON) y su SHA-256: los de las trazas de conformidad. */
  snapshot(): string {
    return this.raw.snapshot();
  }

  digest(): string {
    return this.raw.digest();
  }

  payoffs(): ExactNumber[] | null {
    return JSON.parse(this.raw.payoffs()) as ExactNumber[] | null;
  }

  /** Puesto de cada asiento al terminar (1 = primero), o null. */
  ranking(): number[] | null {
    const text = this.raw.ranking();
    return text === "null" ? null : (JSON.parse(text) as number[] | null);
  }

  /** Las acciones legales de un asiento (como mucho `limit`; 0 = todas). */
  legal(seat: number, limit = 0): LegalList {
    const { actions, truncated } = unwrap<LegalList>(this.raw.legal(seat, limit));
    return { actions, truncated };
  }

  /**
   * Construcción progresiva: sin nombre, las acciones disponibles; con nombre y argumentos ya
   * elegidos, los valores posibles del siguiente.
   */
  options(seat: number, name?: string, args: Record<string, unknown> = {}): unknown[] {
    return unwrap<{ options: unknown[] }>(this.raw.options(seat, name ?? "", JSON.stringify(args)))
      .options;
  }

  /** Aplica una acción (lanza `EngineError` "illegal" si no es legal). */
  act(seat: number, action: ActionData): void {
    unwrap(this.raw.act(seat, JSON.stringify(action)));
  }

  /** Sortea el punto de azar actual y lo aplica; devuelve el resultado. */
  chance(): number[] {
    return unwrap<{ outcome: number[] }>(this.raw.chance()).outcome;
  }

  applyChance(outcome: number[]): void {
    unwrap(this.raw.applyChance(JSON.stringify(outcome)));
  }

  /** Los resultados posibles del azar con su probabilidad exacta ("1/6"…). */
  chanceOutcomes(limit = 100_000): [number[], string][] {
    return unwrap<{ outcomes: [number[], string][] }>(this.raw.chanceOutcomes(limit)).outcomes;
  }

  /** Vuelve al estado anterior (false si ya está en la preparación). */
  undo(): boolean {
    return this.raw.undo();
  }

  /**
   * La jugada de un bot: al azar, la primera legal, MCTS con `simulations` partidas (y como
   * mucho `maxSeconds`, si se indica) o un bot de la F9 (`maxSeconds` por jugada; 0,5 s si no).
   */
  botAction(
    seat: number,
    kind: BotKind = "random",
    simulations = 1000,
    maxSeconds = 0,
  ): ActionData {
    const reply = this.raw.botAction(seat, kind, simulations, maxSeconds);
    return unwrap<{ action: ActionData }>(reply).action;
  }

  dispose(): void {
    if (!this.raw.isDeleted()) this.raw.delete();
  }
}
