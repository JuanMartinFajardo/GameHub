// SPDX-License-Identifier: Apache-2.0
/** Las etiquetas de los juegos (`meta.tags`, en inglés en la IR) tal como se muestran. */

import type { Locale } from "@gamehub/i18n";

const SPANISH: Record<string, string> = {
  "anti-coordination": "anticoordinación",
  benchmark: "banco de pruebas",
  bluffing: "faroles",
  board: "tablero",
  cards: "cartas",
  chance: "azar",
  classic: "clásico",
  combinatorial: "combinatorio",
  connection: "conexión",
  coordination: "coordinación",
  deterministic: "determinista",
  dice: "dados",
  "general-sum": "suma general",
  impartial: "imparcial",
  "imperfect-information": "información imperfecta",
  "normal-form": "forma normal",
  "perfect-information": "información perfecta",
  poker: "póquer",
  "reaction-window": "ventana de reacción",
  research: "investigación",
  simultaneous: "simultáneo",
  "zero-sum": "suma cero",
};

export function tagText(tag: string, locale: Locale): string {
  if (locale === "es") return SPANISH[tag] ?? tag.replaceAll("-", " ");
  return tag.replaceAll("-", " ");
}
