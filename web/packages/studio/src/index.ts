// SPDX-License-Identifier: Apache-2.0
/**
 * GameHub Studio como librería de React: la app (`StudioApp`) y sus piezas (la conexión con
 * `gamehub studio`, el estado, el diagrama, el editor, el inspector y el simulador).
 *
 *     import "@gamehub/ui-kit/styles.css";
 *     import "@gamehub/auto-ui/styles.css";
 *     import "@gamehub/studio/styles.css";
 *     <LocaleProvider><StudioApp /></LocaleProvider>
 */

export * from "./api";
export * from "./connection";
export * from "./context";
export * from "./diagram/Diagram";
export * from "./diagram/diff";
export * from "./diagram/export";
export * from "./diagram/graph";
export * from "./diagram/layout";
export * from "./editor/TextEditor";
export * from "./messages";
export * from "./StudioApp";
export * from "./store";
export * from "./tools/components";
export type * from "./types";
