// SPDX-License-Identifier: Apache-2.0
import type { Locale } from "@gamehub/i18n";
import { createContext, useContext } from "react";
import type { GameModel } from "./ir";

/** Lo que necesitan todos los componentes de la UI genérica. */
export interface AutoContext {
  model: GameModel;
  locale: Locale;
  /** El asiento de quien mira (null: espectador). */
  seat: number | null;
  seatName: (seat: number) => string;
  seatColor: (seat: number) => string;
  /** Las opciones de la partida (para límites como `max_play`). */
  params: Record<string, unknown>;
}

export const Auto = createContext<AutoContext | null>(null);

export function useAuto(): AutoContext {
  const ctx = useContext(Auto);
  if (ctx === null) throw new Error("componente de auto-ui fuera de <AutoGame>");
  return ctx;
}
