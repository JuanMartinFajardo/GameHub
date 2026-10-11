// SPDX-License-Identifier: Apache-2.0
/** Cómo se muestran los valores de un juego: enumerados, cartas y valores como texto. */

import { humanize, type Locale, pickText } from "@gamehub/i18n";
import { isHidden } from "@gamehub/protocol";
import { type CardSuit, standardRank, standardSuit } from "@gamehub/ui-kit";
import type { GameModel, TypeRef } from "./ir";

export interface EnumLook {
  text: string;
  symbol?: string;
  color?: string;
}

/** Cómo se ve un valor de enumerado: su nombre traducido, su símbolo y su color (pistas `ui`). */
export function enumLook(
  model: GameModel,
  enumName: string,
  value: string,
  locale: Locale,
): EnumLook {
  const hint = model.types.get(enumName);
  const label = hint?.labels?.[value];
  return {
    text: label !== undefined ? pickText(label, locale) : humanize(value),
    ...(hint?.symbols?.[value] !== undefined ? { symbol: hint.symbols[value] } : {}),
    ...(hint?.colors?.[value] !== undefined ? { color: hint.colors[value] } : {}),
  };
}

/** Cómo leer una carta de un valor de un tipo que se dibuja como carta. */
export interface CardLook {
  rank: string;
  suit: CardSuit | null;
  name: string;
}

function enumNamed(t: TypeRef): string | null {
  return t.kind === "enum" ? t.name : null;
}

function suitFrom(
  model: GameModel,
  enumName: string | null,
  value: unknown,
  locale: Locale,
): CardSuit | null {
  if (typeof value !== "string") return null;
  const hint = enumName ? model.types.get(enumName) : undefined;
  const standard = standardSuit(value);
  const symbol = hint?.symbols?.[value] ?? standard?.symbol;
  if (symbol === undefined) return null;
  const label = hint?.labels?.[value];
  return {
    symbol,
    color: hint?.colors?.[value] ?? standard?.color ?? "var(--gh-card-black)",
    name: label !== undefined ? pickText(label, locale) : (standard?.name ?? humanize(value)),
  };
}

function rankFrom(model: GameModel, enumName: string | null, value: unknown): string {
  if (typeof value === "number") return String(value);
  if (typeof value !== "string") return "?";
  const hint = enumName ? model.types.get(enumName) : undefined;
  return hint?.symbols?.[value] ?? standardRank(value);
}

/**
 * Si los valores de `type` se dibujan como cartas, la función que da su aspecto; si no, null.
 * Son cartas los tipos con la pista `card` y, sin pistas, los structs con campos `rank` y `suit`
 * y los enumerados que se llaman `Card`.
 */
export function cardReader(
  model: GameModel,
  type: TypeRef,
  locale: Locale,
): ((value: unknown) => CardLook) | null {
  if (type.kind !== "enum" && type.kind !== "struct") return null;
  const hint = model.types.get(type.name)?.card;
  if (type.kind === "enum") {
    if (hint === undefined && type.name.toLowerCase() !== "card") return null;
    return (value) => {
      const rank = rankFrom(model, type.name, value);
      return { rank, suit: null, name: typeof value === "string" ? humanize(value) : rank };
    };
  }
  const fields = new Map(type.fields);
  const find = (want: string) =>
    [...fields.keys()].find((k) => k.toLowerCase() === want) ?? undefined;
  const rankField = hint?.rank ?? (hint === undefined ? find("rank") : undefined);
  const suitField = hint?.suit ?? (hint === undefined ? find("suit") : undefined);
  if (rankField === undefined) return null;
  const rankType = fields.get(rankField);
  const suitType = suitField !== undefined ? fields.get(suitField) : undefined;
  return (value) => {
    const record = (value ?? {}) as Record<string, unknown>;
    const rank = rankFrom(model, rankType ? enumNamed(rankType) : null, record[rankField]);
    const suit =
      suitField !== undefined
        ? suitFrom(model, suitType ? enumNamed(suitType) : null, record[suitField], locale)
        : null;
    const rankName =
      typeof record[rankField] === "string" ? humanize(record[rankField] as string) : rank;
    return { rank, suit, name: suit ? `${rankName} · ${suit.name}` : rankName };
  };
}

/** Un valor como texto corto (registro de eventos, botones, celdas sin dibujo propio). */
export function valueText(
  model: GameModel,
  value: unknown,
  locale: Locale,
  seatName: (seat: number) => string,
  type?: TypeRef,
): string {
  const text = (v: unknown, t?: TypeRef): string => {
    if (isHidden(v)) return "▒";
    if (v === null || v === undefined) return "—";
    if (t?.kind === "Seat" && typeof v === "number") return seatName(v);
    if (typeof v === "boolean") return v ? "✓" : "✗";
    if (typeof v === "number") return String(v);
    if (typeof v === "string") {
      if (t?.kind === "enum") {
        const look = enumLook(model, t.name, v, locale);
        return look.symbol ?? look.text;
      }
      const owner = findEnum(model, v);
      if (owner !== null) {
        const look = enumLook(model, owner, v, locale);
        return look.symbol ?? look.text;
      }
      return /^-?\d+\/\d+$/.test(v) ? v : v;
    }
    if (Array.isArray(v)) {
      if (
        t?.kind === "Cell" ||
        (v.length === 2 && v.every((x) => typeof x === "number") && t === undefined)
      ) {
        return `(${v.join(", ")})`;
      }
      const inner = t && "inner" in t ? t.inner : undefined;
      if (t?.kind === "tuple") return `(${v.map((x, i) => text(x, t.items[i])).join(", ")})`;
      if (t?.kind === "map")
        return v
          .map(
            (pair) =>
              `${text((pair as unknown[])[0], t.key)}: ${text((pair as unknown[])[1], t.value)}`,
          )
          .join(", ");
      return `[${v.map((x) => text(x, inner)).join(", ")}]`;
    }
    if (typeof v === "object") {
      const record = v as Record<string, unknown>;
      if ("items" in record && Array.isArray(record.items)) {
        const inner = t && "inner" in t ? t.inner : undefined;
        const shown = (record.items as unknown[]).map((x) => text(x, inner));
        const size = typeof record.size === "number" ? record.size : shown.length;
        const extra = size - shown.length;
        return [...shown, ...(extra > 0 ? [`+${extra} ▒`] : [])].join(" ") || "∅";
      }
      if (t?.kind === "struct" || t === undefined) {
        const struct = t?.kind === "struct" ? t : findStruct(model, record);
        if (struct) {
          const card = cardReader(model, struct, locale);
          if (card) {
            const look = card(record);
            return `${look.rank}${look.suit?.symbol ?? ""}`;
          }
          return struct.fields.map(([k, ft]) => `${k}: ${text(record[k], ft)}`).join(", ");
        }
      }
      return Object.entries(record)
        .map(([k, x]) => `${k}: ${text(x)}`)
        .join(", ");
    }
    return String(v);
  };
  return text(value, type);
}

/** El enumerado al que pertenece un nombre de valor, si es de uno solo. */
export function findEnum(model: GameModel, value: string): string | null {
  let found: string | null = null;
  for (const decl of model.decls.values()) {
    if (decl.kind === "enum" && decl.values.includes(value)) {
      if (found !== null) return null;
      found = decl.name;
    }
  }
  return found;
}

/** El struct cuyos campos son exactamente las claves de un objeto, si hay uno solo. */
export function findStruct(
  model: GameModel,
  record: Record<string, unknown>,
): Extract<TypeRef, { kind: "struct" }> | null {
  const keys = Object.keys(record).sort().join(",");
  let found: Extract<TypeRef, { kind: "struct" }> | null = null;
  for (const decl of model.decls.values()) {
    if (
      decl.kind === "struct" &&
      decl.fields
        .map((f) => f.name)
        .sort()
        .join(",") === keys
    ) {
      if (found !== null) return null;
      found = {
        kind: "struct",
        name: decl.name,
        fields: decl.fields.map((f) => [f.name, structFieldType(model, f.type)]),
      };
    }
  }
  return found;
}

function structFieldType(model: GameModel, raw: unknown): TypeRef {
  if (typeof raw === "string") {
    const decl = model.decls.get(raw);
    if (decl?.kind === "enum") return { kind: "enum", name: raw, values: decl.values };
    if (["Bool", "Int", "Real", "Text", "Seat", "Cell"].includes(raw))
      return { kind: raw as "Int" };
  }
  return { kind: "unknown" };
}
