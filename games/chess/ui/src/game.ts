// SPDX-License-Identifier: Apache-2.0
// Tipos de chess 1.0.0, generados de las reglas (`gamehub sdk ts`).
// No editar a mano: se vuelven a generar cuando cambian las reglas.

import type { View } from "@gamehub/protocol";

/** Ajedrez */
export const GAME_ID = "chess";
export const GAME_VERSION = "1.0.0";
export const RULES_HASH = "sha256:e5ccb9d1e894022ec73e377d064e1eb47db5841746a3db778d2219182bb94283";

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

export type Color = "White" | "Black";
export const Color = ["White", "Black"] as const;

export type Kind = "Pawn" | "Knight" | "Bishop" | "Rook" | "Queen" | "King";
export const Kind = ["Pawn", "Knight", "Bishop", "Rook", "Queen", "King"] as const;

/** Las doce piezas: el color y el tipo en un solo valor (así cada una tiene su símbolo). */
export type Piece =
  | "WhitePawn"
  | "WhiteKnight"
  | "WhiteBishop"
  | "WhiteRook"
  | "WhiteQueen"
  | "WhiteKing"
  | "BlackPawn"
  | "BlackKnight"
  | "BlackBishop"
  | "BlackRook"
  | "BlackQueen"
  | "BlackKing";
export const Piece = [
  "WhitePawn",
  "WhiteKnight",
  "WhiteBishop",
  "WhiteRook",
  "WhiteQueen",
  "WhiteKing",
  "BlackPawn",
  "BlackKnight",
  "BlackBishop",
  "BlackRook",
  "BlackQueen",
  "BlackKing",
] as const;

/** Las opciones de la partida. */
export type Params = Record<string, never>;

/** El estado tal como lo ve quien mira (lo oculto llega como `Hidden`). */
export interface State {
  /** La fila 0 es la octava (la de las negras) y la columna 0, la «a». */
  board: (Piece | null)[][];
  /** 0 = blancas, 1 = negras */
  turn: Seat;
  /** Derechos de enroque: blancas corto y largo, negras corto y largo */
  castling: boolean[];
  /** Casilla a la que se puede capturar al paso (solo si hay una captura legal) */
  en_passant: Cell | null;
  /** Dónde está el rey de cada color */
  kings: Cell[];
  /** Medias jugadas desde la última captura o jugada de peón (reglas de las 50 y 75 jugadas) */
  halfmove: number;
  /** Número de la jugada, como en la notación: empieza en 1 y sube tras jugar las negras */
  fullmove: number;
  /** Posiciones desde la última jugada irreversible, para contar repeticiones */
  history: [(Piece | null)[][], Cell | null][];
  /** La jugada elegida, que aplica el nodo `Apply` */
  from_cell: Cell;
  to_cell: Cell;
  promotion: Kind | null;
}

/** Los nodos del flow. */
export type NodeId = "Move" | "Apply" | "Checkmate" | "Stalemate" | "Draw";

/** La vista de una actualización (`update.view`) con el estado de este juego. */
export type GameView = Omit<View, "state" | "node"> & {
  node: NodeId | null;
  state: State;
};

export interface PlayAction {
  name: "play";
  args: { from: Cell; to: Cell };
}

export interface PromoteAction {
  name: "promote";
  args: { from: Cell; to: Cell; into: Kind };
}

export interface ClaimDrawAction {
  name: "claim_draw";
  args: Record<string, never>;
}

/** Cualquier acción del juego. */
export type Action = PlayAction | PromoteAction | ClaimDrawAction;
