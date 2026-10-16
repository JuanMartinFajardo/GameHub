// SPDX-License-Identifier: Apache-2.0
// Tipos de wizard 1.0.0, generados de las reglas (`gamehub sdk ts`).
// No editar a mano: se vuelven a generar cuando cambian las reglas.

import type { View } from "@gamehub/protocol";

/** Wizard */
export const GAME_ID = "wizard";
export const GAME_VERSION = "1.0.0";
export const RULES_HASH = "sha256:189706cb5258fa76bcd95d633e11539ce4a7502e36d61576aac49f8f58e420c5";

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

/** Rangos de la baraja de Wizard: el bufón (el más bajo), del 2 al as y el mago (el más alto). */
export type WizardRank =
  | "Jester"
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
  | "Ace"
  | "Wizard";
export const WizardRank = [
  "Jester",
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
  "Wizard",
] as const;

/**
 * Una carta de Wizard. Cada mago y cada bufón lleva un palo, pero solo de adorno: no tienen palo a
 * efectos del juego.
 */
export interface WizardCard {
  suit: Suit;
  rank: WizardRank;
}

/** Las opciones de la partida. */
export interface Params {
  /** Rondas que se juegan (0 = todas: 60 cartas entre el número de jugadores) */
  rounds: number;
  /**
   * Variante: la suma de las apuestas no puede ser igual al número de bazas (lo cuida quien
   * reparte, que apuesta el último)
   */
  hook: boolean;
}

/** El estado tal como lo ve quien mira (lo oculto llega como `Hidden`). */
export interface State {
  deck: Zone<WizardCard>;
  hand: Zone<WizardCard>[];
  /** La carta vuelta que marca el triunfo */
  trump_card: Zone<WizardCard>;
  trump: Suit | null;
  round: number;
  dealer: Seat;
  bid: (number | null)[];
  won: number[];
  score: number[];
  /** La baza en juego, en el orden en que se jugaron las cartas, y quién jugó cada una */
  trick: Zone<WizardCard>;
  trick_by: Seat[];
  /** Quién se llevó la última baza */
  last_winner: Seat | null;
  discard: Zone<WizardCard>;
  turn: Seat;
}

/** Los nodos del flow. */
export type NodeId = "Round" | "Deal" | "ChooseTrump" | "Bidding" | "Play" | "Trick" | "End";

/** La vista de una actualización (`update.view`) con el estado de este juego. */
export type GameView = Omit<View, "state" | "node"> & {
  node: NodeId | null;
  state: State;
};

export interface ChooseAction {
  name: "choose";
  args: { s: Suit };
}

export interface BidAction {
  name: "bid";
  args: { n: number };
}

export interface PlayAction {
  name: "play";
  args: { c: WizardCard };
}

/** Cualquier acción del juego. */
export type Action = ChooseAction | BidAction | PlayAction;
