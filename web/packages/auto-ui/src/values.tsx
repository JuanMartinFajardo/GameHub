// SPDX-License-Identifier: Apache-2.0
/** Dibujo de valores según su tipo y de cada variable de estado según su forma (widget). */

import { pickText, useMessages } from "@gamehub/i18n";
import { isHidden } from "@gamehub/protocol";
import {
  Badge,
  Chips,
  Counter,
  Deck,
  Dice,
  Die,
  Grid,
  Hand,
  Pile,
  PlayerBadge,
  PlayingCard,
  Token,
} from "@gamehub/ui-kit";
import type { ReactNode } from "react";
import { useAuto } from "./context";
import { cardReader, enumLook, valueText } from "./format";
import { elementType, type StateVarModel, type TypeRef } from "./ir";
import { messages } from "./messages";

/** Un valor cualquiera, dibujado según su tipo. */
export function ValueView(props: { type: TypeRef; value: unknown; size?: "sm" | "md" | "lg" }) {
  const ctx = useAuto();
  const t = useMessages(messages);
  const { type, value } = props;
  if (isHidden(value)) return <HiddenValue type={type} />;
  const card = cardReader(ctx.model, type, ctx.locale);
  if (card && value !== null && value !== undefined) {
    const look = card(value);
    return (
      <PlayingCard rank={look.rank} suit={look.suit} label={look.name} size={props.size ?? "sm"} />
    );
  }
  switch (type.kind) {
    case "Bool":
      return <Badge tone={value ? "success" : "neutral"}>{value ? t("yes") : t("no")}</Badge>;
    case "Seat":
      return typeof value === "number" ? (
        <PlayerBadge name={ctx.seatName(value)} color={ctx.seatColor(value)} />
      ) : (
        <span>{t("none")}</span>
      );
    case "enum": {
      const look = enumLook(ctx.model, type.name, String(value), ctx.locale);
      if (look.color) {
        return (
          <span className="gh-auto-enum">
            <Token size="sm" color={look.color}>
              {look.symbol}
            </Token>
            {look.text}
          </span>
        );
      }
      return <Badge tone="accent">{look.symbol ? `${look.symbol} ${look.text}` : look.text}</Badge>;
    }
    case "option":
      return value === null ? (
        <span className="gh-muted">{t("none")}</span>
      ) : (
        <ValueView type={type.inner} value={value} size={props.size} />
      );
    case "list":
    case "set":
    case "zone":
    case "bag":
      return <ItemsRow type={type} value={value} />;
    case "grid":
      return <GridView type={type} value={value} />;
    default:
      return (
        <span className="gh-auto-text">
          {valueText(ctx.model, value, ctx.locale, ctx.seatName, type)}
        </span>
      );
  }
}

/** Lo que no se puede ver: un dorso de carta, un dado tapado o una interrogación. */
export function HiddenValue(props: { type: TypeRef }) {
  const ctx = useAuto();
  const t = useMessages(messages);
  if (cardReader(ctx.model, props.type, ctx.locale)) return <PlayingCard faceDown size="sm" />;
  return (
    <span className="gh-auto-hidden" title={t("hidden")}>
      ?
    </span>
  );
}

/** Los elementos de una lista, conjunto, zona o bolsa (con los ocultos al final). */
export function zoneItems(value: unknown): { items: unknown[]; hidden: number } {
  if (Array.isArray(value)) return { items: value, hidden: 0 };
  if (value !== null && typeof value === "object" && "items" in value) {
    const zone = value as { size?: number; items: unknown[] };
    const size = typeof zone.size === "number" ? zone.size : zone.items.length;
    return { items: zone.items, hidden: Math.max(0, size - zone.items.length) };
  }
  return { items: [], hidden: 0 };
}

export function zoneSize(value: unknown): number {
  const { items, hidden } = zoneItems(value);
  return items.length + hidden;
}

function ItemsRow(props: { type: TypeRef; value: unknown }) {
  const ctx = useAuto();
  const inner = elementType(props.type) ?? { kind: "unknown" as const };
  const { items, hidden } = zoneItems(props.value);
  if (isHidden(props.value)) return <HiddenValue type={inner} />;
  const isCard = cardReader(ctx.model, inner, ctx.locale) !== null;
  if (isCard) {
    return (
      <Hand layout="flat" hidden={hidden}>
        {items.map((item, i) => (
          // biome-ignore lint/suspicious/noArrayIndexKey: la posición es la identidad.
          <ValueView key={i} type={inner} value={item} />
        ))}
      </Hand>
    );
  }
  return (
    <span className="gh-auto-row">
      {items.length === 0 && hidden === 0 && <span className="gh-muted">∅</span>}
      {items.map((item, i) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: la posición es la identidad.
        <ValueView key={i} type={inner} value={item} />
      ))}
      {hidden > 0 && <span className="gh-auto-hidden">+{hidden}</span>}
    </span>
  );
}

/** El contenido de una casilla de una rejilla. */
export function CellContent(props: { type: TypeRef; value: unknown }) {
  const ctx = useAuto();
  const { type, value } = props;
  if (value === null || value === undefined) return null;
  if (isHidden(value)) return <HiddenValue type={type} />;
  const inner = type.kind === "option" ? type.inner : type;
  if (inner.kind === "enum") {
    const look = enumLook(ctx.model, inner.name, String(value), ctx.locale);
    if (look.color)
      return (
        <Token size="fill" color={look.color} label={look.text}>
          {look.symbol}
        </Token>
      );
    return (
      <Token
        glyph
        label={look.text}
        color={look.symbol ? undefined : enumColor(inner.values.indexOf(String(value)))}
      >
        {look.symbol ?? shortName(look.text)}
      </Token>
    );
  }
  if (inner.kind === "Seat" && typeof value === "number") {
    return <Token size="fill" color={ctx.seatColor(value)} label={ctx.seatName(value)} />;
  }
  if (inner.kind === "Bool") return <span>{value ? "●" : ""}</span>;
  return <ValueView type={inner} value={value} size="sm" />;
}

function shortName(text: string): string {
  return text.length <= 2 ? text : text.slice(0, 1).toUpperCase();
}

/** Un color para el valor n de un enumerado sin colores propios (los de los asientos). */
function enumColor(index: number): string {
  return `var(--gh-seat-${Math.max(0, index) % 8})`;
}

export interface GridInteraction {
  mode: "cell" | "column" | "row";
  isTarget: (row: number, column: number) => boolean;
  onSelect: (row: number, column: number) => void;
}

export function GridView(props: {
  type: TypeRef;
  value: unknown;
  label?: string;
  interaction?: GridInteraction | null;
  isLast?: (row: number, column: number) => boolean;
}) {
  const rows = Array.isArray(props.value) ? (props.value as unknown[][]) : [];
  const inner = props.type.kind === "grid" ? props.type.inner : { kind: "unknown" as const };
  const columns = rows[0]?.length ?? 0;
  const it = props.interaction;
  return (
    <Grid
      rows={rows.length}
      columns={columns}
      label={props.label}
      renderCell={(r, c) => <CellContent type={inner} value={rows[r]?.[c]} />}
      mode={it?.mode ?? "cell"}
      isTarget={it?.isTarget}
      onSelect={it?.onSelect}
      isLast={props.isLast}
    />
  );
}

export interface PickInteraction {
  isSelectable: (index: number) => boolean;
  isSelected: (index: number) => boolean;
  toggle: (index: number) => void;
}

/** Una variable de estado (o el valor de un asiento si es per_player) con su forma. */
export function VarWidget(props: {
  v: StateVarModel;
  value: unknown;
  grid?: GridInteraction | null;
  pick?: PickInteraction | null;
  compact?: boolean;
}): ReactNode {
  const ctx = useAuto();
  const { v, value } = props;
  const label = pickText(v.label, ctx.locale);
  const inner = elementType(v.base) ?? v.base;
  switch (v.widget) {
    case "hidden":
      return null;
    case "grid":
      return <GridView type={v.base} value={value} label={label} interaction={props.grid} />;
    case "counter":
      return isHidden(value) ? (
        <HiddenValue type={v.base} />
      ) : (
        <Counter
          value={valueText(ctx.model, value, ctx.locale, ctx.seatName, v.base)}
          label={props.compact ? undefined : label}
        />
      );
    case "chips":
      return isHidden(value) ? (
        <HiddenValue type={v.base} />
      ) : (
        <Chips
          amount={valueText(ctx.model, value, ctx.locale, ctx.seatName, v.base)}
          label={label}
        />
      );
    case "dice": {
      if (isHidden(value)) return <Die />;
      if (typeof value === "number") return <Die value={value} />;
      const { items, hidden } = zoneItems(value);
      return (
        <Dice
          label={label}
          values={[
            ...items.map((x) => (typeof x === "number" ? x : null)),
            ...Array.from({ length: hidden }, () => null),
          ]}
        />
      );
    }
    case "seat":
      return <ValueView type={v.base} value={value} />;
    case "hand":
    case "row":
      return (
        <ZoneView
          v={v}
          value={value}
          layout={v.widget === "hand" ? "fan" : "flat"}
          pick={props.pick}
          label={label}
          itemType={inner}
        />
      );
    case "pile":
    case "deck": {
      if (isHidden(value)) return <Deck count={0} label={label} />;
      const { items, hidden } = zoneItems(value);
      const count = items.length + hidden;
      if (v.widget === "deck") return <Deck count={count} label={label} />;
      const top = items[0];
      return (
        <Pile
          count={count}
          label={label}
          top={
            top !== undefined && !isHidden(top) ? <ValueView type={inner} value={top} /> : undefined
          }
        />
      );
    }
    default:
      return <ValueView type={v.base} value={value} />;
  }
}

function ZoneView(props: {
  v: StateVarModel;
  value: unknown;
  layout: "fan" | "flat";
  pick?: PickInteraction | null;
  label: string;
  itemType: TypeRef;
}) {
  const ctx = useAuto();
  if (isHidden(props.value)) return <HiddenValue type={props.itemType} />;
  const { items, hidden } = zoneItems(props.value);
  const card = cardReader(ctx.model, props.itemType, ctx.locale);
  const pick = props.pick;
  if (card) {
    return (
      <Hand layout={props.layout} hidden={hidden} label={props.label}>
        {items.map((item, i) => {
          if (isHidden(item)) {
            // biome-ignore lint/suspicious/noArrayIndexKey: la posición es la identidad.
            return <PlayingCard key={i} faceDown />;
          }
          const look = card(item);
          const selectable = pick?.isSelectable(i) ?? false;
          return (
            <PlayingCard
              // biome-ignore lint/suspicious/noArrayIndexKey: la posición es la identidad.
              key={i}
              rank={look.rank}
              suit={look.suit}
              label={look.name}
              target={selectable}
              selected={pick?.isSelected(i) ?? false}
              onClick={selectable ? () => pick?.toggle(i) : undefined}
            />
          );
        })}
      </Hand>
    );
  }
  return (
    <span className="gh-auto-row">
      {items.length === 0 && hidden === 0 && <span className="gh-muted">∅</span>}
      {items.map((item, i) =>
        pick?.isSelectable(i) ? (
          <button
            // biome-ignore lint/suspicious/noArrayIndexKey: la posición es la identidad.
            key={i}
            type="button"
            className="gh-auto-pick"
            data-gh-target=""
            aria-pressed={pick.isSelected(i)}
            onClick={() => pick.toggle(i)}
          >
            <ValueView type={props.itemType} value={item} />
          </button>
        ) : (
          // biome-ignore lint/suspicious/noArrayIndexKey: la posición es la identidad.
          <span key={i}>
            <ValueView type={props.itemType} value={item} />
          </span>
        ),
      )}
      {hidden > 0 && <span className="gh-auto-hidden">+{hidden}</span>}
    </span>
  );
}
