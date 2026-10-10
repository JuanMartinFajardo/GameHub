// SPDX-License-Identifier: Apache-2.0
import { useCallback } from "react";
import { type Locale, useLocale } from "./locale";
import { format } from "./text";

/** Un catálogo de mensajes: las mismas claves en cada idioma. */
export type Messages<K extends string> = Readonly<Record<Locale, Readonly<Record<K, string>>>>;

/** Declara un catálogo (TypeScript comprueba que el inglés tiene las claves del español). */
export function defineMessages<K extends string>(
  es: Readonly<Record<K, string>>,
  en: Readonly<Record<K, string>>,
): Messages<K> {
  return { es, en };
}

export type Translate<K extends string> = (
  key: K,
  vars?: Readonly<Record<string, string | number>>,
) => string;

/** Traduce con un catálogo en un idioma concreto (fuera de React). */
export function translator<K extends string>(messages: Messages<K>, locale: Locale): Translate<K> {
  return (key, vars) => format(messages[locale][key] ?? messages.es[key] ?? key, vars);
}

/** `t(clave, variables)` en el idioma de la interfaz. */
export function useMessages<K extends string>(messages: Messages<K>): Translate<K> {
  const { locale } = useLocale();
  // biome-ignore lint/correctness/useExhaustiveDependencies: el catálogo es una constante.
  return useCallback(translator(messages, locale), [locale]);
}

/** Forma singular o plural según `n` (las reglas del idioma). */
export function plural(locale: Locale, n: number, one: string, other: string): string {
  return new Intl.PluralRules(locale).select(n) === "one" ? one : other;
}
