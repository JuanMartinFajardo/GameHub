// SPDX-License-Identifier: Apache-2.0
/** Rutas del repositorio para los tests: las IR de ejemplo y las trazas de conformidad. */

import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";

export const REPO = resolve(import.meta.dirname, "../../../..");
export const EXAMPLES = join(REPO, "spec/ir/examples");
export const CONFORMANCE = join(REPO, "spec/conformance");

export function exampleIr(name: string): string {
  return readFileSync(join(EXAMPLES, `${name}.ir.json`), "utf8");
}
