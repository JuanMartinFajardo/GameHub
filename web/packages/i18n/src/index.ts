// SPDX-License-Identifier: Apache-2.0
/**
 * Idiomas de las interfaces: español (por defecto) e inglés.
 *
 * - `pickText` elige el idioma de un texto de la IR (`"…"` o `{ es: "…", en: "…" }`).
 * - `defineMessages` declara un catálogo de mensajes con sus dos traducciones (TypeScript exige
 *   las mismas claves en ambas) y `useMessages` lo usa en un componente: `t("key", { n: 3 })`.
 * - `LocaleProvider` guarda el idioma elegido (en localStorage) y `useLocale` lo lee o lo cambia.
 */

export * from "./locale";
export * from "./messages";
export * from "./text";
