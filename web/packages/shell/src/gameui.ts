// SPDX-License-Identifier: Apache-2.0
/**
 * El contrato de una UI propia: un componente de React que recibe la partida tal como la ve un
 * asiento y una función para jugar. Se declara con `defineGameUi` y la app la usa en vez de la
 * UI genérica para ese juego (con un botón para cambiar a la genérica).
 *
 *     export default defineGameUi<State, Action>({
 *       game: "tictactoe",
 *       component: Board,
 *     });
 */

import type { GameModel, PlayerInfo } from "@gamehub/auto-ui";
import type { LoggedEvent } from "@gamehub/client";
import type { Locale, Translatable } from "@gamehub/i18n";
import type { ActionData, Clocks, Legal, MatchEnd, View } from "@gamehub/protocol";
import type { ComponentType } from "react";

export interface GameUiProps<S = Record<string, unknown>, A extends ActionData = ActionData> {
  /** El juego analizado (tipos, variables, acciones, pistas `ui`). */
  model: GameModel;
  view: View & { state: S };
  /** El asiento de quien mira (null: espectador). */
  seat: number | null;
  players: PlayerInfo[];
  /** Las acciones legales enumeradas si me toca (null si no o si son progresivas). */
  actions: A[] | null;
  legal: Legal | null;
  act: (action: A) => void;
  queryActions: (name?: string, args?: Record<string, unknown>) => Promise<unknown[]>;
  /** Hay una jugada enviada sin respuesta. */
  busy: boolean;
  rejected: { detail: string } | null;
  log: LoggedEvent[];
  clocks: Clocks | null;
  /** Opciones de la partida. */
  params: Record<string, unknown>;
  end: MatchEnd | null;
  locale: Locale;
}

export interface GameUi {
  /** El id del juego (`meta.id`). */
  game: string;
  name?: Translatable;
  // biome-ignore lint/suspicious/noExplicitAny: cada UI tipa su estado y sus acciones.
  component: ComponentType<GameUiProps<any, any>>;
}

export type GameUiRegistry = Readonly<Record<string, GameUi>>;

export function defineGameUi<S = Record<string, unknown>, A extends ActionData = ActionData>(ui: {
  game: string;
  name?: Translatable;
  component: ComponentType<GameUiProps<S, A>>;
}): GameUi {
  return ui as GameUi;
}

/** Un registro a partir de módulos que exportan por defecto una UI (p. ej. `import.meta.glob`). */
export function registry(modules: Record<string, { default: GameUi }>): GameUiRegistry {
  const out: Record<string, GameUi> = {};
  for (const module of Object.values(modules)) out[module.default.game] = module.default;
  return out;
}
