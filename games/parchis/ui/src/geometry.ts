// SPDX-License-Identifier: Apache-2.0
/**
 * La geometría del tablero de parchís, en una cuadrícula de 19 × 19: cuatro brazos de 3 × 8
 * casillas alrededor de la meta (3 × 3). Cada brazo tiene dos carriles del anillo y, en medio, el
 * pasillo de su color; la casilla del final del pasillo es la de entrada. Se avanza en sentido
 * contrario a las agujas del reloj: amarillo abajo, azul a la derecha, rojo arriba y verde a la
 * izquierda, con las salidas en la 5, 22, 39 y 56.
 */

/** [columna, fila] en la cuadrícula. */
export type Point = [number, number];

export const SIZE = 19;
export const COLORS = ["#fdd835", "#1e88e5", "#e53935", "#43a047"];

function buildRing(): Point[] {
  const ring: Point[] = [];
  for (let r = 18; r >= 11; r--) ring.push([10, r]); // 1–8
  for (let c = 11; c <= 18; c++) ring.push([c, 10]); // 9–16
  ring.push([18, 9]); // 17
  for (let c = 18; c >= 11; c--) ring.push([c, 8]); // 18–25
  for (let r = 7; r >= 0; r--) ring.push([10, r]); // 26–33
  ring.push([9, 0]); // 34
  for (let r = 0; r <= 7; r++) ring.push([8, r]); // 35–42
  for (let c = 7; c >= 0; c--) ring.push([c, 8]); // 43–50
  ring.push([0, 9]); // 51
  for (let c = 0; c <= 7; c++) ring.push([c, 10]); // 52–59
  for (let r = 11; r <= 18; r++) ring.push([8, r]); // 60–67
  ring.push([9, 18]); // 68
  return ring;
}

/** La casilla `q` (1 a 68) del anillo. */
export const RING: readonly Point[] = buildRing();

export function ringPoint(q: number): Point {
  return RING[(((q - 1) % 68) + 68) % 68] as Point;
}

/** Los seguros: las salidas y las casillas 7 y 12 después de cada una. */
export function isSafe(q: number): boolean {
  return [0, 7, 12].includes((((q - 5) % 17) + 17) % 17);
}

export function exitSquare(color: number): number {
  return 5 + 17 * color;
}

/** La casilla `j` (0 a 6) del pasillo de un color. */
export function corridorPoint(color: number, j: number): Point {
  switch (color) {
    case 0:
      return [9, 17 - j];
    case 1:
      return [17 - j, 9];
    case 2:
      return [9, 1 + j];
    default:
      return [1 + j, 9];
  }
}

const HOMES: Point[] = [
  [14.5, 14.5],
  [14.5, 3.5],
  [3.5, 3.5],
  [3.5, 14.5],
];

const GOALS: Point[] = [
  [9, 10],
  [10, 9],
  [9, 8],
  [8, 9],
];

/** El color de cada asiento: con dos jugadores, colores opuestos (como en las reglas). */
export function colorOf(seat: number, players: number): number {
  return players === 2 ? ([0, 2][seat] ?? 0) : seat;
}

/**
 * Dónde se dibuja una ficha en la posición `i` de su recorrido: en casa (-1), en el anillo (0 a
 * 63), en el pasillo (64 a 70) o en la meta (71). `k` separa las fichas de casa y de la meta.
 */
export function pawnPoint(color: number, i: number, k: number): Point {
  if (i < 0) {
    const [x, y] = HOMES[color] as Point;
    return [x + (k % 2 === 0 ? -1.2 : 1.2), y + (k < 2 ? -1.2 : 1.2)];
  }
  if (i <= 63) return ringPoint(exitSquare(color) + i);
  if (i <= 70) return corridorPoint(color, i - 64);
  const [x, y] = GOALS[color] as Point;
  const spread = (k - 1.5) * 0.35;
  return color % 2 === 0 ? [x + spread, y] : [x, y + spread];
}

/** La casilla del anillo (1 a 68) en la que está una ficha, o null si no está en el anillo. */
export function ringSquare(color: number, i: number): number | null {
  return i >= 0 && i <= 63 ? ((exitSquare(color) - 1 + i) % 68) + 1 : null;
}
