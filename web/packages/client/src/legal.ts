// SPDX-License-Identifier: Apache-2.0
/**
 * Utilidades para elegir una acción entre las legales: comparar acciones y construirlas
 * argumento a argumento (lo que hace una interfaz al rellenar un formulario o al pulsar casillas).
 */

import type { ActionData } from "@gamehub/protocol";

/** JSON canónico (claves ordenadas): dos valores iguales dan el mismo texto. */
export function canonicalJson(value: unknown): string {
  return JSON.stringify(sortKeys(value));
}

function sortKeys(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sortKeys);
  if (value !== null && typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>).sort(([a], [b]) =>
      a < b ? -1 : a > b ? 1 : 0,
    );
    return Object.fromEntries(entries.map(([k, v]) => [k, sortKeys(v)]));
  }
  return value;
}

/** Clave de una acción para compararla o usarla en un `Map`. */
export function actionKey(action: ActionData): string {
  return canonicalJson([action.name, action.args]);
}

export function sameAction(a: ActionData, b: ActionData): boolean {
  return actionKey(a) === actionKey(b);
}

export function sameValue(a: unknown, b: unknown): boolean {
  return canonicalJson(a) === canonicalJson(b);
}

/** Las acciones legales con ese nombre cuyos argumentos coinciden con los ya elegidos. */
export function matching(
  legal: readonly ActionData[],
  name: string,
  chosen: Readonly<Record<string, unknown>> = {},
): ActionData[] {
  const keys = Object.entries(chosen).map(([k, v]) => [k, canonicalJson(v)] as const);
  return legal.filter(
    (a) => a.name === name && keys.every(([k, v]) => k in a.args && canonicalJson(a.args[k]) === v),
  );
}

/** Los valores posibles de `param` dados los argumentos ya elegidos (sin repetir, en orden). */
export function nextValues(
  legal: readonly ActionData[],
  name: string,
  chosen: Readonly<Record<string, unknown>>,
  param: string,
): unknown[] {
  const seen = new Set<string>();
  const values: unknown[] = [];
  for (const action of matching(legal, name, chosen)) {
    const value = action.args[param];
    const key = canonicalJson(value);
    if (!seen.has(key)) {
      seen.add(key);
      values.push(value);
    }
  }
  return values;
}

/** Los nombres de las acciones legales, sin repetir, en el orden en que llegan. */
export function actionNames(legal: readonly ActionData[]): string[] {
  return [...new Set(legal.map((a) => a.name))];
}
