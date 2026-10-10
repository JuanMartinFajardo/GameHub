// SPDX-License-Identifier: Apache-2.0
/**
 * Estado que un cliente sigue a partir de los mensajes del servidor. `reduce` es puro: cada
 * mensaje produce un estado nuevo (o el mismo objeto si no cambia nada), que es lo que necesita
 * React (`useSyncExternalStore`).
 */

import type {
  ActionData,
  Chat,
  ErrorInfo,
  GameEvent,
  Legal,
  MatchEnd,
  MatchStart,
  Rejected,
  Room,
  ServerMessage,
  ServerRef,
  Session,
  Update,
} from "@gamehub/protocol";

export type ConnectionStatus = "idle" | "connecting" | "connected" | "reconnecting" | "closed";

/** Un evento del registro de la partida, con la actualización en la que llegó. */
export interface LoggedEvent {
  seq: number;
  event: GameEvent;
}

/** Una jugada enviada que aún no se ha visto aplicada ni rechazada. */
export interface PendingAct {
  id: string;
  seq: number;
  action: ActionData;
}

export interface MatchState {
  start: MatchStart;
  /** La última actualización (vista, eventos, acciones legales y relojes). */
  update: Update | null;
  /** Todos los eventos vistos desde el comienzo de la partida (los últimos `LOG_LIMIT`). */
  log: LoggedEvent[];
  end: MatchEnd | null;
  /** La última jugada propia rechazada (se olvida con la siguiente actualización). */
  rejected: (Rejected & { re: string | null }) | null;
  pending: PendingAct | null;
}

export interface ChatEntry extends Chat {
  /** Hora de llegada (ms desde la época). */
  at: number;
}

export interface ClientState {
  status: ConnectionStatus;
  server: ServerRef | null;
  token: string | null;
  session: Session | null;
  room: Room | null;
  match: MatchState | null;
  chat: ChatEntry[];
  /** El último error del servidor que no era la respuesta a una petición. */
  error: ErrorInfo | null;
  /** Falta alguna actualización (llegó una con un `seq` que se salta otro): hay que pedir resync. */
  stale: boolean;
}

export const LOG_LIMIT = 1000;
export const CHAT_LIMIT = 200;

export const initialState: ClientState = {
  status: "idle",
  server: null,
  token: null,
  session: null,
  room: null,
  match: null,
  chat: [],
  error: null,
  stale: false,
};

/** El estado tras recibir un mensaje del servidor. */
export function reduce(state: ClientState, msg: ServerMessage, now = Date.now()): ClientState {
  switch (msg.type) {
    case "welcome": {
      // Tras reconectar, una jugada enviada antes del corte puede no haber llegado: se olvida (si
      // llegó, la actualización que la refleja viene a continuación).
      const { session } = msg.data;
      const match = state.match?.pending ? { ...state.match, pending: null } : state.match;
      return { ...state, server: msg.data.server, session: session ?? state.session, match };
    }
    case "joined":
      return { ...state, token: msg.data.token, session: msg.data.session, error: null };
    case "room":
      return { ...state, room: msg.data, session: followSeat(state.session, msg.data) };
    case "match_start":
      return {
        ...state,
        stale: false,
        match: { start: msg.data, update: null, log: [], end: null, rejected: null, pending: null },
      };
    case "update":
      return applyUpdate(state, msg.data);
    case "rejected": {
      if (state.match === null) return state;
      const re = msg.re ?? null;
      const pending = state.match.pending?.id === re ? null : state.match.pending;
      return { ...state, match: { ...state.match, rejected: { ...msg.data, re }, pending } };
    }
    case "match_end":
      if (state.match === null || state.match.start.match.id !== msg.data.match.id) return state;
      return { ...state, match: { ...state.match, end: msg.data, pending: null } };
    case "chat": {
      const chat = [...state.chat, { ...msg.data, at: now }].slice(-CHAT_LIMIT);
      return { ...state, chat };
    }
    case "error":
      switch (msg.data.code) {
        case "invalid_token":
          // La sesión ya no existe (la sala se cerró o el servidor se reinició).
          return { ...state, token: null, session: null, room: null, match: null };
        case "replaced":
          return { ...state, error: msg.data, status: "closed" };
        default:
          return msg.re === undefined ? { ...state, error: msg.data } : state;
      }
    case "actions":
    case "pong":
      return state;
  }
}

function applyUpdate(state: ClientState, update: Update): ClientState {
  const match = state.match;
  if (match === null) return state;
  const last = match.update?.seq ?? -1;
  // Un `seq` ya visto es un refresco (reconexión, resync): se reemplaza la vista sin repetir los
  // eventos. Uno que se salta otro deja el estado marcado para pedir resync.
  const fresh = update.seq > last;
  const log = fresh
    ? [...match.log, ...update.events.map((event) => ({ seq: update.seq, event }))].slice(
        -LOG_LIMIT,
      )
    : match.log;
  const advanced = fresh && match.update !== null;
  return {
    ...state,
    stale: state.stale || (match.update !== null && update.seq > last + 1),
    match: {
      ...match,
      update,
      log,
      pending: advanced ? null : match.pending,
      rejected: advanced ? null : match.rejected,
    },
  };
}

/** El asiento propio puede cambiar (sentarse, levantarse, configurar la sala, otro anfitrión). */
function followSeat(session: Session | null, room: Room): Session | null {
  if (session === null) return null;
  const me = session.participant;
  const seat = room.seats.find((s) => s.participant === me);
  const spectator = room.spectators.find((s) => s.participant === me);
  const host = seat?.host ?? spectator?.host ?? session.host;
  const next: Session = {
    ...session,
    seat: seat?.seat ?? null,
    role: seat !== undefined ? "player" : "spectator",
    host,
  };
  const same =
    next.seat === session.seat && next.role === session.role && next.host === session.host;
  return same ? session : next;
}

// --- Consultas sobre el estado ---------------------------------------------------------------

/** El asiento propio (null si se mira como espectador). */
export function mySeat(state: ClientState): number | null {
  return state.session?.seat ?? null;
}

/** Las acciones legales si me toca: enumeradas o, si son demasiadas, solo sus nombres. */
export function legalOf(state: ClientState): Legal | null {
  const match = state.match;
  if (match === null || match.end !== null || match.update === null) return null;
  return match.update.legal ?? null;
}

/** ¿Me toca? (hay acciones legales para mí y no he jugado ya en este turno) */
export function myTurn(state: ClientState): boolean {
  return legalOf(state) !== null && state.match?.pending === null;
}

/** ¿Hay una partida en curso (empezada y sin terminar)? */
export function inMatch(state: ClientState): boolean {
  return state.match !== null && state.match.end === null;
}
