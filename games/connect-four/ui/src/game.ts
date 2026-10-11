// SPDX-License-Identifier: Apache-2.0
// Tipos de connect-four 1.0.0, generados de las reglas (`gamehub sdk ts`).
// No editar a mano: se vuelven a generar cuando cambian las reglas.

import type { View } from "@gamehub/protocol";

/** Conecta 4 */
export const GAME_ID = "connect-four";
export const GAME_VERSION = "1.0.0";
export const RULES_HASH = "sha256:174e366723393fbe8ac455dd97e930a9b6df8aef68c5f106aac7f2514a0f990d";

/** Un valor que quien mira no puede ver. */
export interface Hidden {
  $hidden: true;
}

/** Una zona o bolsa: su tamaño (si se ve) y los elementos que se ven. */
export interface Zone<T> {
  size?: number;
  items: (T | Hidden)[];
}

/** Un asiento (0, 1, …). */
export type Seat = number;

/** Una casilla de una rejilla: [fila, columna]. */
export type Cell = [number, number];

/** Número exacto: entero o racional como texto «n/d». */
export type Real = number | string;

export type Disc = "Red" | "Yellow";
export const Disc = ["Red", "Yellow"] as const;

/** Las opciones de la partida. */
export interface Params {
  /** Columnas del tablero */
  columns: number;
  /** Filas del tablero */
  rows: number;
  /** Fichas en línea para ganar */
  connect: number;
}

/** El estado tal como lo ve quien mira (lo oculto llega como `Hidden`). */
export interface State {
  /** La fila 0 es la de arriba: las fichas caen hacia filas mayores. */
  board: (Disc | null)[][];
  turn: Seat;
}

/** Los nodos del flow. */
export type NodeId = "Move" | "Win" | "Draw";

/** La vista de una actualización (`update.view`) con el estado de este juego. */
export type GameView = Omit<View, "state" | "node"> & {
  node: NodeId | null;
  state: State;
};

export interface DropAction {
  name: "drop";
  args: { c: number };
}

/** Cualquier acción del juego. */
export type Action = DropAction;
