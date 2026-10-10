// SPDX-License-Identifier: Apache-2.0
import type { Locale } from "./locale";

/** Un texto de la IR: una cadena o un mapa idioma → texto. */
export type Translatable = string | Readonly<Record<string, string>>;

/** El texto en el idioma pedido (o en español, inglés o el primero que haya). */
export function pickText(text: Translatable | null | undefined, locale: Locale): string {
  if (text == null) return "";
  if (typeof text === "string") return text;
  return text[locale] ?? text.es ?? text.en ?? Object.values(text)[0] ?? "";
}

/** `dice_left` → «Dice left», `TicTacToe` → «Tic tac toe»: un nombre del código para personas. */
export function humanize(name: string): string {
  const words = name
    .replace(/[_-]+/g, " ")
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .trim()
    .toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** Rellena `{nombre}` con los valores dados. */
export function format(template: string, vars?: Readonly<Record<string, string | number>>): string {
  if (vars === undefined) return template;
  return template.replace(/\{(\w+)\}/g, (whole, key: string) =>
    key in vars ? String(vars[key]) : whole,
  );
}
