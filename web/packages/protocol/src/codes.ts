// SPDX-License-Identifier: Apache-2.0
/**
 * Códigos de sala: 6 caracteres de Crockford base32 (sin I, L, O ni U), p. ej. `K7F-Q2P`.
 *
 * Al leerlos se admiten minúsculas, guiones y espacios, y las letras que se confunden con cifras
 * valen como ellas (O → 0; I, L → 1), como en Crockford. Igual que `gamehub.server.codes`.
 */

export const CODE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ";
export const CODE_LENGTH = 6;

const CONFUSABLE: Record<string, string> = { O: "0", I: "1", L: "1" };

/** El código canónico (mayúsculas, sin separadores) o `null` si no es un código válido. */
export function normalizeCode(text: string): string | null {
  const code = [...text.replace(/[\s-]/g, "").toUpperCase()]
    .map((c) => CONFUSABLE[c] ?? c)
    .join("");
  if (code.length !== CODE_LENGTH || [...code].some((c) => !CODE_ALPHABET.includes(c))) {
    return null;
  }
  return code;
}

/** El código como se muestra: `K7FQ2P` → `K7F-Q2P`. */
export function displayCode(code: string): string {
  const half = CODE_LENGTH / 2;
  return `${code.slice(0, half)}-${code.slice(half)}`;
}
