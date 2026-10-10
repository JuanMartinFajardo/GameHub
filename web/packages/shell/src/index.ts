// SPDX-License-Identifier: Apache-2.0
/**
 * La experiencia de jugar de GameHub como librería: la usa la app web (`apps/play`) y el
 * servidor de desarrollo de cada UI propia.
 *
 *     import "@gamehub/ui-kit/styles.css";
 *     import "@gamehub/auto-ui/styles.css";
 *     import "@gamehub/shell/styles.css";
 *     createRoot(root).render(<PlayApp customUis={{ tictactoe: miUi }} />);
 */

export * from "./forms";
export * from "./games";
export * from "./gameui";
export * from "./Home";
export * from "./HotSeat";
export * from "./NewRoom";
export * from "./PlayApp";
export * from "./Replay";
export * from "./Room";
export * from "./router";
export * from "./theme";
export * from "./useRoom";
