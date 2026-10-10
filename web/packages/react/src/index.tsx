// SPDX-License-Identifier: Apache-2.0
/**
 * Hooks de React sobre `@gamehub/client`:
 *
 *     <GameClientProvider client={client}>
 *       <MiTablero />
 *     </GameClientProvider>
 *
 *     function MiTablero() {
 *       const view = useView<MiEstado>();      // la vista que me toca ver (tipos de `gamehub sdk ts`)
 *       const legal = useLegalActions();       // acciones legales enumeradas si me toca
 *       const act = useAct();
 *       …
 *     }
 */

import {
  type ClientState,
  type GameClient,
  type GameIr,
  type LoggedEvent,
  legalOf,
  type MatchState,
  myTurn,
  roomIr,
} from "@gamehub/client";
import type {
  ActionData,
  Legal,
  MatchEnd,
  MatchStart,
  Room,
  Session,
  View,
} from "@gamehub/protocol";
import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";

const ClientContext = createContext<GameClient | null>(null);

export function GameClientProvider(props: { client: GameClient; children: ReactNode }) {
  return <ClientContext.Provider value={props.client}>{props.children}</ClientContext.Provider>;
}

/** El cliente del proveedor más cercano. */
export function useGameClient(): GameClient {
  const client = useContext(ClientContext);
  if (client === null) throw new Error("falta <GameClientProvider client={…}>");
  return client;
}

/** Todo el estado del cliente; se vuelve a dibujar con cada cambio. */
export function useClientState(client?: GameClient): ClientState {
  const fromContext = useContext(ClientContext);
  const c = client ?? fromContext;
  if (c === null) throw new Error("falta <GameClientProvider client={…}>");
  return useSyncExternalStore(c.subscribe, c.getState, c.getState);
}

/** Una parte del estado; solo se vuelve a dibujar si esa parte cambia (por identidad). */
export function useClientSelector<T>(select: (state: ClientState) => T, client?: GameClient): T {
  const fromContext = useContext(ClientContext);
  const c = client ?? fromContext;
  if (c === null) throw new Error("falta <GameClientProvider client={…}>");
  const getSnapshot = () => select(c.getState());
  return useSyncExternalStore(c.subscribe, getSnapshot, getSnapshot);
}

export const useRoom = (): Room | null => useClientSelector((s) => s.room);
export const useSession = (): Session | null => useClientSelector((s) => s.session);
export const useMatch = (): MatchState | null => useClientSelector((s) => s.match);
export const useMatchStart = (): MatchStart | null =>
  useClientSelector((s) => s.match?.start ?? null);
export const useMatchEnd = (): MatchEnd | null => useClientSelector((s) => s.match?.end ?? null);
export const useLog = (): LoggedEvent[] => useClientSelector((s) => s.match?.log ?? EMPTY);
export const useMySeat = (): number | null => useClientSelector((s) => s.session?.seat ?? null);
export const useMyTurn = (): boolean => useClientSelector(myTurn);
export const useLegal = (): Legal | null => useClientSelector(legalOf);

const EMPTY: LoggedEvent[] = [];

/** La vista de la última actualización, con el tipo de estado del juego (`gamehub sdk ts`). */
export function useView<S = Record<string, unknown>>(): (View & { state: S }) | null {
  return useClientSelector((s) => (s.match?.update?.view ?? null) as (View & { state: S }) | null);
}

/** Las acciones legales enumeradas si me toca (null si no me toca o si son progresivas). */
export function useLegalActions<A extends ActionData = ActionData>(): A[] | null {
  const legal = useLegal();
  return legal?.kind === "enumerated" ? (legal.actions as A[]) : null;
}

/** Jugar una acción. */
export function useAct<A extends ActionData = ActionData>(): (action: A) => void {
  const client = useGameClient();
  return useCallback((action: A) => void client.act(action), [client]);
}

/** Un dato que se carga de forma asíncrona (p. ej. por REST). */
export interface Resource<T> {
  data: T | null;
  error: Error | null;
  loading: boolean;
}

/** Carga `load()` cada vez que cambia `key` (null = no cargar nada). */
export function useResource<T>(key: string | null, load: () => Promise<T>): Resource<T> {
  const [state, setState] = useState<Resource<T>>({
    data: null,
    error: null,
    loading: key !== null,
  });
  const loader = useRef(load);
  loader.current = load;
  useEffect(() => {
    if (key === null) {
      setState({ data: null, error: null, loading: false });
      return;
    }
    let live = true;
    setState((s) => ({ ...s, loading: true, error: null }));
    loader.current().then(
      (data) => live && setState({ data, error: null, loading: false }),
      (error: unknown) =>
        live &&
        setState({
          data: null,
          error: error instanceof Error ? error : new Error(String(error)),
          loading: false,
        }),
    );
    return () => {
      live = false;
    };
  }, [key]);
  return state;
}

const irCache = new Map<string, Promise<GameIr>>();

/** La IR del juego de una sala (se pide una vez por servidor y sala). */
export function useRoomIr(server: string, code: string | null): Resource<GameIr> {
  return useResource(code === null ? null : `${server}|${code}`, () => {
    const key = `${server}|${code}`;
    let found = irCache.get(key);
    if (found === undefined) {
      found = roomIr(server, code as string);
      found.catch(() => irCache.delete(key));
      irCache.set(key, found);
    }
    return found;
  });
}
