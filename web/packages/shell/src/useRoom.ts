// SPDX-License-Identifier: Apache-2.0
/**
 * La conexión de esta pestaña a una sala: retoma la sesión guardada (al recargar o volver más
 * tarde), entra con un nombre como jugador o espectador y la guarda.
 */

import {
  type ClientState,
  endpoints,
  forgetSession,
  GameClient,
  getRoom,
  initialState,
  loadSession,
  saveSession,
} from "@gamehub/client";
import type { Room } from "@gamehub/protocol";
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";

const NAME_KEY = "gamehub:name";

export function savedName(): string {
  try {
    return localStorage.getItem(NAME_KEY) ?? "";
  } catch {
    return "";
  }
}

export function rememberName(name: string): void {
  try {
    localStorage.setItem(NAME_KEY, name);
  } catch {
    // Sin almacenamiento.
  }
}

/** Qué hacer al entrar por primera vez tras crear la sala: sentarse y poner bots. */
export interface AutoSetup {
  sit: boolean;
  bots: number;
}

const SETUP_KEY = "gamehub:setup:";

export function planSetup(code: string, setup: AutoSetup): void {
  try {
    sessionStorage.setItem(SETUP_KEY + code, JSON.stringify(setup));
  } catch {
    // Sin almacenamiento: el anfitrión se sienta a mano.
  }
}

function takeSetup(code: string): AutoSetup | null {
  try {
    const raw = sessionStorage.getItem(SETUP_KEY + code);
    sessionStorage.removeItem(SETUP_KEY + code);
    return raw ? (JSON.parse(raw) as AutoSetup) : null;
  } catch {
    return null;
  }
}

export interface RoomConnection {
  client: GameClient | null;
  state: ClientState;
  /** La sala por REST, antes de entrar (null si no existe o aún no ha llegado). */
  preview: Room | null;
  missing: boolean;
  /** Retomando una sesión guardada. */
  resuming: boolean;
  error: string | null;
  join: (name: string, role: "player" | "spectator") => Promise<void>;
  leave: () => void;
  reconnect: () => void;
}

const EMPTY_SUBSCRIBE = () => () => {};
const EMPTY_STATE = () => initialState;

export function useRoomConnection(server: string, code: string): RoomConnection {
  const http = endpoints(server).http;
  const [client, setClient] = useState<GameClient | null>(null);
  const [preview, setPreview] = useState<Room | null>(null);
  const [missing, setMissing] = useState(false);
  const [resuming, setResuming] = useState(() => loadSession(http, code) !== null);
  const [error, setError] = useState<string | null>(null);
  const current = useRef<GameClient | null>(null);

  const adopt = useCallback((next: GameClient | null) => {
    current.current?.close();
    current.current = next;
    setClient(next);
  }, []);

  const resume = useCallback(async () => {
    const saved = loadSession(http, code);
    if (saved === null) {
      setResuming(false);
      return;
    }
    setResuming(true);
    const c = new GameClient({ server, name: saved.name, token: saved.token });
    adopt(c);
    try {
      const welcome = await c.connect();
      if (welcome.session === undefined || welcome.session.room !== code) {
        forgetSession(http, code);
        adopt(null);
        setError("sessionLost");
        return;
      }
      const setup = takeSetup(code);
      if (setup) await applySetup(c, setup);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setResuming(false);
    }
  }, [server, http, code, adopt]);

  useEffect(() => {
    let live = true;
    getRoom(server, code).then(
      (room) => live && setPreview(room),
      (e: unknown) => {
        if (!live) return;
        if (e instanceof Error && "code" in e && e.code === "unknown_room") setMissing(true);
        else setError(e instanceof Error ? e.message : String(e));
      },
    );
    void resume();
    return () => {
      live = false;
      current.current?.close();
      current.current = null;
    };
  }, [server, code, resume]);

  // Guardar el token cada vez que cambia (al entrar).
  const state = useSyncExternalStore(
    client?.subscribe ?? EMPTY_SUBSCRIBE,
    client?.getState ?? EMPTY_STATE,
    client?.getState ?? EMPTY_STATE,
  );
  useEffect(() => {
    if (client && state.token && state.session?.room === code) {
      saveSession(http, code, state.token, client.name);
    }
    if (client && state.token === null && state.session === null && state.server !== null) {
      forgetSession(http, code);
    }
  }, [client, state.token, state.session, state.server, http, code]);

  const join = useCallback(
    async (name: string, role: "player" | "spectator") => {
      setError(null);
      rememberName(name);
      const c = new GameClient({ server, name });
      adopt(c);
      try {
        await c.connect();
        await c.join(code, { role });
      } catch (e) {
        adopt(null);
        setError(e instanceof Error ? e.message : String(e));
      }
    },
    [server, code, adopt],
  );

  const leave = useCallback(() => {
    client?.leave();
    forgetSession(http, code);
    adopt(null);
  }, [client, http, code, adopt]);

  return {
    client,
    state,
    preview,
    missing,
    resuming,
    error,
    join,
    leave,
    reconnect: () => void resume(),
  };
}

async function applySetup(client: GameClient, setup: AutoSetup): Promise<void> {
  if (setup.sit) client.sit();
  if (setup.bots <= 0) return;
  // Los bots, en los últimos asientos, cuando llegue la sala con el anfitrión sentado.
  await new Promise<void>((resolve) => {
    const done = () => {
      const room = client.getState().room;
      const me = client.getState().session;
      if (!room || !me) return false;
      const free = room.seats.filter((s) => s.kind === "open").map((s) => s.seat);
      for (const seat of free.slice(-setup.bots)) client.setSeat(seat, "bot", { bot: "random" });
      return true;
    };
    const stop = client.subscribe(() => {
      if (client.getState().session?.seat != null && done()) {
        stop();
        resolve();
      }
    });
    setTimeout(() => {
      stop();
      resolve();
    }, 5000);
  });
}
