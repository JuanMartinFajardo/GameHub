// SPDX-License-Identifier: Apache-2.0
/**
 * Kit de componentes para interfaces de juegos de GameHub. Importa también los estilos:
 *
 *     import "@gamehub/ui-kit/styles.css";
 *     import { Grid, PlayingCard, Hand, Die } from "@gamehub/ui-kit";
 *
 * Todo el aspecto sale de variables CSS (`--gh-…`, ver styles.css) y de la clase `gh-root` en el
 * contenedor: una UI propia cambia colores y tamaños redefiniéndolas.
 */

export * from "./basics";
export * from "./boards";
export * from "./cards";
export * from "./pieces";
export * from "./players";
export * from "./zones";
