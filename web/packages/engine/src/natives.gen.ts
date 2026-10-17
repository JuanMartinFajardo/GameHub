// SPDX-License-Identifier: Apache-2.0
// Generado por `gamehub wasm --write`: los plugins nativos de la stdlib (ABI
// gamehub-native/1) que el núcleo puede usar en el navegador, por módulo.

export const NATIVE_PLUGINS: Readonly<Record<string, () => URL>> = {
  "std.poker": () => new URL("../wasm/natives/std.poker.wasm", import.meta.url),
};
