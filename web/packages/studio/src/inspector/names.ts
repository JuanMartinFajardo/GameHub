// SPDX-License-Identifier: Apache-2.0
/** Los nombres que se ofrecen al escribir en un formulario: los del juego y lo predefinido. */

import type { NameSource } from "../editor/setup";
import type { GameModel } from "../types";

export const BUILTINS = [
  "len",
  "size",
  "items",
  "top",
  "first",
  "last",
  "only",
  "reverse",
  "distinct",
  "append",
  "concat",
  "union",
  "intersection",
  "difference",
  "subsets",
  "range",
  "slice",
  "contains",
  "set",
  "abs",
  "min",
  "max",
  "sum",
  "rat",
  "is_none",
  "unwrap",
  "ord",
  "next",
  "prev",
  "other",
  "seats_from",
  "cells",
  "lines",
  "neighbors",
  "in_bounds",
  "cell",
  "win_loss",
  "fill",
  "all",
  "any",
  "count",
  "argmax",
  "argmin",
  "sort_by",
  "map",
  "filter",
  "flat_map",
  "at",
  "roll",
  "random",
  "sample",
]; // prettier-ignore

export const CONTEXT = ["actor", "seats", "num_players", "viewer", "owner", "face_up"];

export const KEYWORDS = [
  "if",
  "else",
  "and",
  "or",
  "not",
  "in",
  "true",
  "false",
  "none",
  "case",
  "match",
  "let",
  "for",
  "move",
  "flip",
  "shuffle",
  "deal",
  "reveal",
  "emit",
  "reward",
  "fail",
  "from",
  "to",
  "each",
  "top",
  "bottom",
  "all",
  "face_up",
  "face_down",
]; // prettier-ignore

export const TYPES = [
  "Bool",
  "Int",
  "Real",
  "Text",
  "Seat",
  "Cell",
  "List",
  "Set",
  "Map",
  "Zone",
  "Bag",
  "Grid",
  "per_player",
];

/** Nombres para completar; `locals` añade los de la acción que se edita. */
export function namesOf(
  game: () => GameModel | null,
  locals: () => string[] = () => [],
): NameSource {
  return () => {
    const g = game();
    const out: { label: string; detail?: string; type?: string }[] = [];
    for (const name of locals()) out.push({ label: name, type: "variable", detail: "parámetro" });
    if (g) {
      for (const v of g.state) out.push({ label: v.name, detail: v.type, type: "variable" });
      for (const p of g.params) out.push({ label: p.name, detail: p.type, type: "constant" });
      for (const f of g.functions)
        out.push({ label: f.name, detail: `→ ${f.returns}`, type: "function" });
      for (const t of g.types) {
        out.push({ label: t.name, type: "type" });
        if (t.kind === "enum")
          for (const v of t.values) out.push({ label: v, detail: t.name, type: "enum" });
      }
      for (const x of g.externals)
        out.push({ label: x.name, detail: x.module, type: x.kind === "fn" ? "function" : "type" });
      for (const n of g.flow.nodes) out.push({ label: n.id, detail: n.kind, type: "class" });
    }
    for (const b of BUILTINS) out.push({ label: b, type: "function" });
    for (const c of CONTEXT) out.push({ label: c, type: "keyword" });
    for (const k of KEYWORDS) out.push({ label: k, type: "keyword" });
    for (const t of TYPES) out.push({ label: t, type: "type" });
    return out;
  };
}
