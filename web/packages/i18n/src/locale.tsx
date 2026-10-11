// SPDX-License-Identifier: Apache-2.0
import { createContext, type ReactNode, useCallback, useContext, useMemo, useState } from "react";

export const LOCALES = ["es", "en"] as const;
export type Locale = (typeof LOCALES)[number];

const STORAGE_KEY = "gamehub:locale";

export function isLocale(value: unknown): value is Locale {
  return typeof value === "string" && (LOCALES as readonly string[]).includes(value);
}

/** El idioma guardado o, si no hay, el del navegador; español si no es ninguno de los dos. */
export function detectLocale(): Locale {
  try {
    const saved = globalThis.localStorage?.getItem(STORAGE_KEY);
    if (isLocale(saved)) return saved;
  } catch {
    // Sin almacenamiento: se mira el navegador.
  }
  const languages = globalThis.navigator?.languages ?? [];
  for (const language of languages) {
    const short = language.slice(0, 2).toLowerCase();
    if (isLocale(short)) return short;
  }
  return "es";
}

function saveLocale(locale: Locale): void {
  try {
    globalThis.localStorage?.setItem(STORAGE_KEY, locale);
  } catch {
    // Sin almacenamiento: dura lo que la pestaña.
  }
}

interface LocaleState {
  locale: Locale;
  setLocale: (locale: Locale) => void;
}

const LocaleContext = createContext<LocaleState>({ locale: "es", setLocale: () => {} });

export function LocaleProvider(props: { children: ReactNode; initial?: Locale }) {
  const [locale, setState] = useState<Locale>(() => props.initial ?? detectLocale());
  const setLocale = useCallback((next: Locale) => {
    saveLocale(next);
    setState(next);
    if (typeof document !== "undefined") document.documentElement.lang = next;
  }, []);
  const value = useMemo(() => ({ locale, setLocale }), [locale, setLocale]);
  return <LocaleContext.Provider value={value}>{props.children}</LocaleContext.Provider>;
}

/** El idioma de la interfaz y la función para cambiarlo. */
export function useLocale(): LocaleState {
  return useContext(LocaleContext);
}
