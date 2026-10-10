// SPDX-License-Identifier: Apache-2.0
/** Tema claro, oscuro o el del sistema, recordado en localStorage. */

import { useCallback, useEffect, useState } from "react";

export type Theme = "auto" | "light" | "dark";
const KEY = "gamehub:theme";

function load(): Theme {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === "light" || saved === "dark") return saved;
  } catch {
    // Sin almacenamiento: el del sistema.
  }
  return "auto";
}

function apply(theme: Theme) {
  if (theme === "auto") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = theme;
}

export function useTheme(): [Theme, (next: Theme) => void] {
  const [theme, setTheme] = useState<Theme>(load);
  useEffect(() => apply(theme), [theme]);
  const set = useCallback((next: Theme) => {
    try {
      if (next === "auto") localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, next);
    } catch {
      // Dura lo que la pestaña.
    }
    setTheme(next);
  }, []);
  return [theme, set];
}
