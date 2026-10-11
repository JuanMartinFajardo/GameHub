// SPDX-License-Identifier: Apache-2.0
import { DEFAULT_PORT, normalizeCode } from "@gamehub/protocol";
import { ClientError } from "./errors";

/** Dónde está un servidor: la URL HTTP base, la del WebSocket y el código de sala, si lo lleva. */
export interface Endpoints {
  http: string;
  ws: string;
  code: string | null;
}

/**
 * Las direcciones de algo como `192.168.1.20`, `host:7420`, `http://host:7420/r/K7FQ2P` o
 * `ws://host:7420/ws` (igual que el SDK de Python). Sin esquema se supone `http` y, sin puerto,
 * el 7420. Una cadena vacía es el propio origen de la página (la app servida por el servidor).
 */
export function endpoints(target: string): Endpoints {
  const text = target.trim();
  if (text === "") {
    if (typeof location === "undefined") {
      throw new ClientError("connection", "falta la dirección del servidor");
    }
    return fromUrl(new URL(location.href), location.host);
  }
  const full = text.includes("://") ? text : `http://${text}`;
  let url: URL;
  try {
    url = new URL(full);
  } catch {
    throw new ClientError("connection", `dirección de servidor no válida: ${target}`);
  }
  // Sin puerto escrito: el 7420 en http/ws (el del servidor de partidas) y el 443 en https/wss.
  const written = /^[a-z]+:\/\/(\[[^\]]*\]|[^/:]*):\d+/i.test(full);
  const secure = url.protocol === "https:" || url.protocol === "wss:";
  const port = written ? url.port : secure ? "" : String(DEFAULT_PORT);
  return fromUrl(url, port === "" ? url.hostname : `${url.hostname}:${port}`);
}

function fromUrl(url: URL, host: string): Endpoints {
  const scheme = { "ws:": "http:", "wss:": "https:" }[url.protocol] ?? url.protocol;
  if ((scheme !== "http:" && scheme !== "https:") || url.hostname === "") {
    throw new ClientError("connection", `dirección de servidor no válida: ${url.href}`);
  }
  const parts = url.pathname.split("/").filter((p) => p !== "");
  const code = parts.length === 2 && parts[0] === "r" ? normalizeCode(parts[1] ?? "") : null;
  return {
    http: `${scheme}//${host}`,
    ws: `${scheme === "https:" ? "wss:" : "ws:"}//${host}/ws`,
    code,
  };
}

/**
 * Servidor y código de sala de lo que escribe alguien: un enlace de sala
 * (`http://192.168.1.20:7420/r/K7FQ2P`) o un código (`K7F-Q2P`) en el servidor `server`.
 */
export function roomTarget(room: string, server = ""): { server: string; code: string } {
  if (room.includes("/") || room.includes(":")) {
    const found = endpoints(room);
    if (found.code === null) {
      throw new ClientError("unknown_room", `el enlace no lleva el código de la sala: ${room}`);
    }
    return { server: found.http, code: found.code };
  }
  const code = normalizeCode(room);
  if (code === null) throw new ClientError("unknown_room", `código de sala no válido: ${room}`);
  return { server: endpoints(server).http, code };
}
