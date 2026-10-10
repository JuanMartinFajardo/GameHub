// SPDX-License-Identifier: Apache-2.0
/** API REST del servidor de partidas (`/api/v1`): información, salas, juegos y replays. */

import type {
  ApiError,
  CreatedRoom,
  CreateRoom,
  EndReason,
  ExactNumber,
  GameEvent,
  Room,
  RoomList,
  ServerInfo,
  View,
} from "@gamehub/protocol";
import { endpoints } from "./endpoints";
import { ClientError } from "./errors";

/** Una GameIR (JSON): `ir.schema.json`. `@gamehub/auto-ui` la tipa con detalle. */
export type GameIr = Record<string, unknown>;

/** Quien jugó en cada asiento de una partida guardada (la posición en la lista es el asiento). */
export interface RecordedPlayer {
  name: string;
  kind: "human" | "bot";
}

/** Resumen de una partida terminada (`GET /api/v1/matches`). */
export interface MatchListing {
  id: string;
  game: { id: string; version: string; rules_hash: string };
  players: RecordedPlayer[];
  reason: EndReason;
  payoffs: ExactNumber[] | null;
  ranking: number[] | null;
  steps: number;
}

/** Replay de una partida terminada (`gamehub-replay/0.1`, con el azar revelado). */
export interface Replay {
  format: string;
  game: { id: string; version: string; rules_hash: string };
  num_players: number;
  params: Record<string, unknown>;
  seed: number | null;
  steps: ({ chance: unknown[] } | { seat: number; action: { name: string; args: object } })[];
  players?: RecordedPlayer[];
  result?: {
    node?: string;
    payoffs?: ExactNumber[];
    reason?: EndReason;
    ranking?: number[];
    forfeited?: number[];
  };
  [key: string]: unknown;
}

/** GET (o POST con `body`) de JSON. Los errores de la API llegan como `ClientError`. */
export async function fetchJson<T>(url: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, {
      method: body === undefined ? "GET" : "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: body === undefined ? null : JSON.stringify(body),
      signal: signal ?? null,
    });
  } catch (error) {
    throw new ClientError("connection", `no se puede conectar con ${url}: ${String(error)}`);
  }
  const text = await response.text();
  let data: unknown = null;
  try {
    data = text === "" ? null : JSON.parse(text);
  } catch {
    if (response.ok) throw new ClientError("http", `respuesta que no es JSON de ${url}`);
  }
  if (!response.ok) {
    const error = (data as ApiError | null)?.error;
    if (error !== undefined) throw new ClientError(error.code, error.message);
    throw new ClientError("http", `HTTP ${response.status} en ${url}`);
  }
  return data as T;
}

function api(server: string, path: string): string {
  return `${endpoints(server).http}/api/v1${path}`;
}

export function serverInfo(server: string): Promise<ServerInfo> {
  return fetchJson(api(server, "/info"));
}

export function listRooms(server: string): Promise<RoomList> {
  return fetchJson(api(server, "/rooms"));
}

/** Crea una sala (`game` del catálogo o `ir`). El token devuelto es la sesión del anfitrión. */
export function createRoom(server: string, body: CreateRoom): Promise<CreatedRoom> {
  return fetchJson(api(server, "/rooms"), body);
}

export function getRoom(server: string, code: string): Promise<Room> {
  return fetchJson(api(server, `/rooms/${encodeURIComponent(code)}`));
}

/** La IR del juego de una sala. */
export function roomIr(server: string, code: string): Promise<GameIr> {
  return fetchJson(api(server, `/rooms/${encodeURIComponent(code)}/ir`));
}

/** La IR de un juego del catálogo del servidor. */
export function gameIr(server: string, id: string): Promise<GameIr> {
  return fetchJson(api(server, `/games/${encodeURIComponent(id)}`));
}

export async function listMatches(server: string): Promise<MatchListing[]> {
  const data = await fetchJson<{ matches: MatchListing[] }>(api(server, "/matches"));
  return data.matches;
}

export function getReplay(server: string, id: string): Promise<Replay> {
  return fetchJson(api(server, `/replays/${encodeURIComponent(id)}`));
}

/** Un estado de una partida terminada tal como lo vio alguien (`GET …/frames`). */
export interface ReplayFrame {
  step: number;
  view: View;
  events: GameEvent[];
}

export interface ReplayFrames {
  match: string;
  /** "all" (todo a la vista), "public" (espectador) o el asiento. */
  seat: string;
  ir: GameIr;
  players: RecordedPlayer[];
  params: Record<string, unknown>;
  result: Replay["result"] | null;
  fairness?: unknown;
  frames: ReplayFrame[];
}

/** La partida paso a paso tal como la vio `seat` ("all", "public" o un asiento). */
export function replayFrames(
  server: string,
  id: string,
  seat: string | number = "all",
): Promise<ReplayFrames> {
  return fetchJson(
    api(
      server,
      `/replays/${encodeURIComponent(id)}/frames?seat=${encodeURIComponent(String(seat))}`,
    ),
  );
}
