// SPDX-License-Identifier: Apache-2.0
// Tipos de tictactoe 1.0.0, generados de las reglas (`gamehub sdk ts`).
// No editar a mano: se vuelven a generar cuando cambian las reglas.

import type { View } from "@gamehub/protocol";

/** Tres en raya */
export const GAME_ID = "tictactoe";
export const GAME_VERSION = "1.0.0";
export const RULES_HASH = "sha256:267838131f33afe1050572be2ef405719ec1ad6e0bdc8199c27a42b0a5013286";

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

export type Mark = "X" | "O";
export const Mark = ["X", "O"] as const;

/** Las opciones de la partida. */
export type Params = Record<string, never>;

/** El estado tal como lo ve quien mira (lo oculto llega como `Hidden`). */
export interface State {
  board: (Mark | null)[][];
  turn: Seat;
}

/** Los nodos del flow. */
export type NodeId = "Move" | "Win" | "Draw";

/** La vista de una actualización (`update.view`) con el estado de este juego. */
export type GameView = Omit<View, "state" | "node"> & {
  node: NodeId | null;
  state: State;
};

export interface PlaceAction {
  name: "place";
  args: { c: Cell };
}

/** Cualquier acción del juego. */
export type Action = PlaceAction;
