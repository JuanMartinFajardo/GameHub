// SPDX-License-Identifier: Apache-2.0
/**
 * UI genérica de GameHub: cualquier juego se dibuja y se juega a partir de su IR.
 *
 *     import "@gamehub/ui-kit/styles.css";
 *     import "@gamehub/auto-ui/styles.css";
 *     <AutoGame game={ir} view={view} seat={0} players={players} legal={legal} onAct={act} />
 *
 * El aspecto se deduce de los tipos (rejillas, zonas, cartas, números, asientos) y de las pistas
 * de la sección `ui { … }` del juego; cómo se elige cada argumento, de su dominio (`cells(board)`
 * → pulsar una casilla; `subsets(items(mano))` → marcar cartas) o de las pistas.
 */

export * from "./AutoGame";
export * from "./builder";
export * from "./context";
export * from "./events";
export * from "./format";
export * from "./ir";
export * from "./values";
