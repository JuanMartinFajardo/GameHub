// SPDX-License-Identifier: Apache-2.0
// Tipos de dudo 1.0.0, generados de las reglas (`gamehub sdk ts`).
// No editar a mano: se vuelven a generar cuando cambian las reglas.

import type { View } from "@gamehub/protocol";

/** Dudo */
export const GAME_ID = "dudo";
export const GAME_VERSION = "1.0.0";
export const RULES_HASH = "sha256:aef285042260e98550ddaff6067f6b090c0f00e0b7a2e6c20a464181f863145c";

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

/** Las opciones de la partida. */
export interface Params {
  /** Dados de cada jugador al empezar */
  dice: number;
}

/** El estado tal como lo ve quien mira (lo oculto llega como `Hidden`). */
export interface State {
  /** Los dados de cada jugador, bajo su cubilete */
  cup: (number[] | Hidden)[];
  /** Cuántos dados le quedan a cada uno (eso sí se ve) */
  dice_left: number[];
  die: number | Hidden;
  /** La apuesta en vigor: al menos `quantity` dados con la cara `face` (0 = aún no hay) */
  quantity: number;
  face: number;
  bidder: Seat;
  turn: Seat;
  loser: Seat;
}

/** Los nodos del flow. */
export type NodeId = "Roll" | "Bid" | "End";

/** La vista de una actualización (`update.view`) con el estado de este juego. */
export type GameView = Omit<View, "state" | "node"> & {
  node: NodeId | null;
  state: State;
};

export interface BidAction {
  name: "bid";
  args: { q: number; f: number };
}

export interface DudoAction {
  name: "dudo";
  args: Record<string, never>;
}

/** Cualquier acción del juego. */
export type Action = BidAction | DudoAction;
