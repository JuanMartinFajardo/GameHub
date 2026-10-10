// SPDX-License-Identifier: Apache-2.0
/**
 * Protocolo de partidas de GameHub, versión 1: los tipos de todos los mensajes (generados desde
 * `spec/protocol/v1/protocol.schema.json`) y las utilidades que comparten todos los clientes.
 * Semántica: `docs/wiki/protocolo.md`.
 */

import type { ClientMessage, ServerMessage } from "./types";

export * from "./codes";
export type * from "./types";

/** Versión del protocolo: va en el campo `v` de cada mensaje. */
export const PROTOCOL_VERSION = 1;

/** Tamaño máximo de un mensaje del cliente. */
export const MAX_MESSAGE_BYTES = 64 * 1024;

/** Puerto por defecto del servidor de partidas (`gamehub serve`, `gamehub host`). */
export const DEFAULT_PORT = 7420;

/** Cuántas acciones legales enumera como mucho el servidor en cada `update`. */
export const MAX_LEGAL_LIMIT = 20_000;

export type ClientMessageType = ClientMessage["type"];
export type ServerMessageType = ServerMessage["type"];

/** Los datos de un mensaje del cliente, por tipo: `ClientData<"act">` es `Act`. */
export type ClientData<T extends ClientMessageType> = Extract<ClientMessage, { type: T }>["data"];

/** Los datos de un mensaje del servidor, por tipo: `ServerData<"update">` es `Update`. */
export type ServerData<T extends ServerMessageType> = Extract<ServerMessage, { type: T }>["data"];

/** Un mensaje del servidor de un tipo concreto. */
export type ServerMessageOf<T extends ServerMessageType> = Extract<ServerMessage, { type: T }>;

/** Marcador de un valor oculto en vistas y eventos (lo que el destinatario no puede ver). */
export interface Hidden {
  $hidden: true;
}

/** ¿Es este valor de una vista un marcador de valor oculto? */
export function isHidden(value: unknown): value is Hidden {
  return (
    typeof value === "object" &&
    value !== null &&
    (value as Record<string, unknown>).$hidden === true
  );
}

/** Construye un mensaje del cliente. */
export function clientMessage<T extends ClientMessageType>(
  type: T,
  data: ClientData<T>,
  id?: string,
): Extract<ClientMessage, { type: T }> {
  const msg: Record<string, unknown> = { v: PROTOCOL_VERSION, type, data };
  if (id !== undefined) msg.id = id;
  return msg as unknown as Extract<ClientMessage, { type: T }>;
}
