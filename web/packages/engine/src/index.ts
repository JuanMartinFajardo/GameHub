// SPDX-License-Identifier: Apache-2.0
/**
 * El núcleo C++ de GameHub en WebAssembly (F8): las mismas reglas, trazas y plugins nativos que
 * el motor de Python, en el navegador y sin servidor. `loadEngine()` carga el módulo una vez;
 * `LocalTable` juega partidas locales hablando el protocolo de las salas.
 */

export * from "./core";
export * from "./local";
