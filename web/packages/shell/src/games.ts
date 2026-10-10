// SPDX-License-Identifier: Apache-2.0
/** Información del servidor y de sus juegos, pedida una vez y compartida por las páginas. */

import { buildModel, type GameIr, type GameModel } from "@gamehub/auto-ui";
import { gameIr, roomIr, serverInfo } from "@gamehub/client";
import type { ServerInfo } from "@gamehub/protocol";
import { useEffect, useState } from "react";

const infos = new Map<string, Promise<ServerInfo>>();
const models = new Map<string, Promise<GameModel>>();

function cached<T>(map: Map<string, Promise<T>>, key: string, load: () => Promise<T>): Promise<T> {
  let found = map.get(key);
  if (found === undefined) {
    found = load();
    found.catch(() => map.delete(key));
    map.set(key, found);
  }
  return found;
}

export function loadServerInfo(server: string): Promise<ServerInfo> {
  return cached(infos, server, () => serverInfo(server));
}

export function loadGameModel(server: string, id: string): Promise<GameModel> {
  return cached(models, `${server}|game|${id}`, async () =>
    buildModel((await gameIr(server, id)) as unknown as GameIr),
  );
}

export function loadRoomModel(server: string, code: string): Promise<GameModel> {
  return cached(models, `${server}|room|${code}`, async () =>
    buildModel((await roomIr(server, code)) as unknown as GameIr),
  );
}

export interface Loaded<T> {
  data: T | null;
  error: string | null;
}

/** Espera una promesa (que cambia con `key`) y devuelve su valor o su error. */
export function useLoaded<T>(key: string | null, load: () => Promise<T>): Loaded<T> {
  const [state, setState] = useState<Loaded<T>>({ data: null, error: null });
  // biome-ignore lint/correctness/useExhaustiveDependencies: `key` decide cuándo volver a cargar.
  useEffect(() => {
    if (key === null) return;
    let live = true;
    setState({ data: null, error: null });
    load().then(
      (data) => live && setState({ data, error: null }),
      (e: unknown) =>
        live && setState({ data: null, error: e instanceof Error ? e.message : String(e) }),
    );
    return () => {
      live = false;
    };
  }, [key]);
  return state;
}

/** El valor de una expresión constante de la IR (valores por defecto de las opciones). */
export function constValue(expr: unknown): unknown {
  if (!Array.isArray(expr)) return undefined;
  const [op, ...args] = expr;
  switch (op) {
    case "const":
      return args[0];
    case "list":
      return args.map(constValue);
    case "enum":
      return args[1];
    case "neg": {
      const v = constValue(args[0]);
      return typeof v === "number" ? -v : undefined;
    }
    default:
      return undefined;
  }
}
