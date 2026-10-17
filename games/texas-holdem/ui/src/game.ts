// SPDX-License-Identifier: Apache-2.0
// Tipos de texas-holdem 1.0.0, generados de las reglas (`gamehub sdk ts`).
// No editar a mano: se vuelven a generar cuando cambian las reglas.

import type { View } from "@gamehub/protocol";

/** Texas Hold'em */
export const GAME_ID = "texas-holdem";
export const GAME_VERSION = "1.0.0";
export const RULES_HASH = "sha256:8232465cb2ef85ede1c9ca81800441085d96ff8b5c91ff201966b6c271c87ade";

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

/** Palos de la baraja francesa: tréboles, diamantes, corazones y picas. */
export type Suit = "Clubs" | "Diamonds" | "Hearts" | "Spades";
export const Suit = ["Clubs", "Diamonds", "Hearts", "Spades"] as const;

/** Rangos de la baraja francesa, de menor a mayor (el as es el más alto). */
export type Rank =
  | "Two"
  | "Three"
  | "Four"
  | "Five"
  | "Six"
  | "Seven"
  | "Eight"
  | "Nine"
  | "Ten"
  | "Jack"
  | "Queen"
  | "King"
  | "Ace";
export const Rank = [
  "Two",
  "Three",
  "Four",
  "Five",
  "Six",
  "Seven",
  "Eight",
  "Nine",
  "Ten",
  "Jack",
  "Queen",
  "King",
  "Ace",
] as const;

/** Una carta de la baraja francesa. */
export interface Card {
  suit: Suit;
  rank: Rank;
}

/** Las opciones de la partida. */
export interface Params {
  /** Fichas de cada jugador al empezar */
  stack: number;
  small_blind: number;
  big_blind: number;
  /** Manos que se juegan como mucho (0 = hasta que solo quede un jugador con fichas) */
  hands: number;
}

/** El estado tal como lo ve quien mira (lo oculto llega como `Hidden`). */
export interface State {
  deck: Zone<Card>;
  /** Las dos cartas de cada uno; en el enfrentamiento se enseñan las de quien sigue en la mano */
  hole: Zone<Card>[];
  board: Zone<Card>;
  /** Nadie puede tener, apostar ni poner más fichas que las que hay en la mesa */
  chips: number[];
  /** Lo apostado en la ronda en curso y en toda la mano */
  bet: number[];
  put: number[];
  folded: boolean[];
  /**
   * Si ya habló en esta ronda y si aún puede subir (una subida «all-in» que no llega al mínimo no
   * reabre la apuesta a quien ya habló)
   */
  acted: boolean[];
  can_raise: boolean[];
  /** Cuánto hay que subir como mínimo (lo que subió el último) */
  min_raise: number;
  button: Seat;
  /** Quién puso la ciega grande en esta mano */
  big: Seat;
  turn: Seat;
  /** 0 = antes del flop, 1 = flop, 2 = turn, 3 = river */
  street: number;
  hand_no: number;
  shown: boolean;
  /** Lo que ganó cada uno en la última mano */
  won: number[];
}

/** Los nodos del flow. */
export type NodeId =
  | "Hand"
  | "Deal"
  | "Betting"
  | "Street"
  | "Board"
  | "FoldWin"
  | "Showdown"
  | "End";

/** La vista de una actualización (`update.view`) con el estado de este juego. */
export type GameView = Omit<View, "state" | "node"> & {
  node: NodeId | null;
  state: State;
};

export interface FoldAction {
  name: "fold";
  args: Record<string, never>;
}

export interface CheckAction {
  name: "check";
  args: Record<string, never>;
}

export interface CallAction {
  name: "call";
  args: Record<string, never>;
}

export interface BetAction {
  name: "bet";
  args: { amount: number };
}

export interface RaiseAction {
  name: "raise";
  args: { to: number };
}

/** Cualquier acción del juego. */
export type Action = FoldAction | CheckAction | CallAction | BetAction | RaiseAction;
