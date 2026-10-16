// SPDX-License-Identifier: Apache-2.0
// Tipos de parchis 1.0.0, generados de las reglas (`gamehub sdk ts`).
// No editar a mano: se vuelven a generar cuando cambian las reglas.

import type { View } from "@gamehub/protocol";

/** Parchís */
export const GAME_ID = "parchis";
export const GAME_VERSION = "1.0.0";
export const RULES_HASH = "sha256:8740b7f655561e3d3da661be58fc31e514f0325b7defbd08e4ad5c75253fbdaa";

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
  /** Por parejas (con cuatro jugadores: 0 y 2 contra 1 y 3) */
  pairs: boolean;
}

/** El estado tal como lo ve quien mira (lo oculto llega como `Hidden`). */
export interface State {
  /**
   * Dónde está cada ficha: -1 en casa, del 0 (la salida) al 63 dando la vuelta, del 64 al 70 en el
   * pasillo y 71 en la meta
   */
  pos: number[][];
  turn: Seat;
  die: number;
  /** Seises seguidos en el turno */
  sixes: number;
  /** La última ficha que movió el jugador en su turno (por si saca tres seises) */
  last_pawn: number;
  /** Casillas que hay que contar por haber comido (20) o llegado a la meta (10) */
  bonus: number;
  winner: Seat;
}

/** Los nodos del flow. */
export type NodeId = "Roll" | "Move" | "Bonus" | "Punish" | "After" | "Won";

/** La vista de una actualización (`update.view`) con el estado de este juego. */
export type GameView = Omit<View, "state" | "node"> & {
  node: NodeId | null;
  state: State;
};

export interface AdvanceAction {
  name: "advance";
  args: { k: number };
}

export interface CountBonusAction {
  name: "count_bonus";
  args: { k: number };
}

/** Cualquier acción del juego. */
export type Action = AdvanceAction | CountBonusAction;
