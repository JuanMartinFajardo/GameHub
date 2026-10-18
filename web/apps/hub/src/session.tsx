// SPDX-License-Identifier: AGPL-3.0-or-later
/** Quién está conectado al hub (la cookie de sesión) y los datos del propio hub. */

import { createContext, type ReactNode, useCallback, useContext, useEffect, useState } from "react";
import { get, type HubInfo, post, type User } from "./api";

export interface Session {
  info: HubInfo | null;
  user: User | null;
  ready: boolean;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
}

const SessionContext = createContext<Session>({
  info: null,
  user: null,
  ready: false,
  refresh: async () => {},
  logout: async () => {},
});

export function SessionProvider(props: { children: ReactNode }) {
  const [info, setInfo] = useState<HubInfo | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setUser((await get<{ user: User | null }>("/session")).user);
    } finally {
      setReady(true);
    }
  }, []);

  const logout = useCallback(async () => {
    await post("/auth/logout");
    setUser(null);
  }, []);

  useEffect(() => {
    get<HubInfo>("/hub").then(setInfo, () => setInfo(null));
    refresh().catch(() => setReady(true));
  }, [refresh]);

  return (
    <SessionContext.Provider value={{ info, user, ready, refresh, logout }}>
      {props.children}
    </SessionContext.Provider>
  );
}

export function useSession(): Session {
  return useContext(SessionContext);
}
