// SPDX-License-Identifier: Apache-2.0
/** Los eventos del motor como frases para el registro de la partida. */

import { type Locale, pickText, type Translate, translator } from "@gamehub/i18n";
import type { GameEvent } from "@gamehub/protocol";
import { valueText } from "./format";
import type { GameModel, TypeRef } from "./ir";
import { messages } from "./messages";

type Key = Parameters<Translate<keyof (typeof messages)["es"]>>[0];

export interface EventTextOptions {
  model: GameModel;
  locale: Locale;
  seatName: (seat: number) => string;
  /** Incluir los eventos de llegada a un nodo (por defecto, no). */
  nodes?: boolean;
}

function location(model: GameModel, loc: unknown, seatName: (s: number) => string, locale: Locale) {
  const where = (loc ?? {}) as { var?: string; seat?: number };
  const v = model.vars.find((x) => x.name === where.var);
  const label = v ? pickText(v.label, locale) : (where.var ?? "?");
  return typeof where.seat === "number" ? `${label} (${seatName(where.seat)})` : label;
}

/** Una línea de texto para un evento (null si no merece la pena mostrarlo). */
export function eventText(event: GameEvent, options: EventTextOptions): string | null {
  const { model, locale, seatName } = options;
  const t = translator(messages, locale);
  const tr = (key: Key, vars?: Record<string, string | number>) => t(key, vars);
  const value = (v: unknown, type?: TypeRef) => valueText(model, v, locale, seatName, type);
  const who = (s: unknown) => (typeof s === "number" ? seatName(s) : "?");
  switch (event.type) {
    case "action": {
      if (typeof event.name !== "string") return tr("ev_hiddenAction", { who: who(event.seat) });
      const action = findAction(model, event.name);
      const label =
        event.name === "pass" ? tr("pass") : pickText(action?.label ?? event.name, locale);
      const args = (event.args ?? {}) as Record<string, unknown>;
      const inner = Object.entries(args)
        .map(([k, v]) => {
          const param = action?.params.find((p) => p.name === k);
          const shown =
            v !== null && typeof v === "object" && "size" in v && !("items" in v)
              ? `${(v as { size: number }).size} ▒`
              : value(v, param?.type);
          return action?.params.length === 1
            ? shown
            : `${pickText(param?.label ?? k, locale)}: ${shown}`;
        })
        .join(", ");
      return tr("ev_action", {
        who: who(event.seat),
        action: inner ? `${label} (${inner})` : label,
      });
    }
    case "move": {
      const items = Array.isArray(event.items) ? (event.items as unknown[]) : [];
      const shown =
        items.length > 0 && items.some((x) => !isHiddenMark(x))
          ? `: ${items.map((x) => value(x)).join(" ")}`
          : "";
      return (
        tr("ev_move", {
          count: Number(event.count ?? items.length),
          from: location(model, event.from, seatName, locale),
          to: location(model, event.to, seatName, locale),
        }) + shown
      );
    }
    case "shuffle":
      return tr("ev_shuffle", { zone: location(model, event.zone, seatName, locale) });
    case "flip":
      return tr(event.face_up ? "ev_flipUp" : "ev_flipDown", {
        count: Number(event.count ?? 0),
        zone: location(model, event.zone, seatName, locale),
      });
    case "reveal": {
      const shown = value(event.value);
      if (event.label !== undefined) {
        return tr("ev_revealLabel", {
          label: pickText(event.label as never, locale),
          value: shown,
        });
      }
      return tr("ev_reveal", { value: shown });
    }
    case "emit": {
      const fields = Object.entries((event.fields ?? {}) as Record<string, unknown>)
        .map(([k, v]) => `${k}: ${k === "seat" && typeof v === "number" ? seatName(v) : value(v)}`)
        .join(", ");
      return `${String(event.name)} · ${fields}`;
    }
    case "reward":
      return tr("ev_reward", { who: who(event.seat), amount: value(event.amount) });
    case "end": {
      const payoffs = Array.isArray(event.payoffs) ? (event.payoffs as unknown[]) : [];
      return tr("ev_end", {
        payoffs: payoffs.map((p, s) => `${seatName(s)} ${value(p)}`).join(" · "),
      });
    }
    case "submitted":
    case "responded":
      return tr("ev_submitted", { who: who(event.seat) });
    case "responses": {
      const list = Array.isArray(event.responses)
        ? (event.responses as { seat: number; name: string }[])
        : [];
      return tr("ev_responses", {
        responses: list
          .map(
            (r) =>
              `${seatName(r.seat)}: ${r.name === "pass" ? tr("pass") : pickText(findAction(model, r.name)?.label ?? r.name, locale)}`,
          )
          .join(", "),
      });
    }
    case "node": {
      if (!options.nodes) return null;
      const node = model.nodes.get(String(event.node));
      return tr("ev_node", { node: node ? pickText(node.label, locale) : String(event.node) });
    }
    default:
      return null;
  }
}

function isHiddenMark(x: unknown): boolean {
  return typeof x === "object" && x !== null && (x as Record<string, unknown>).$hidden === true;
}

export function findAction(model: GameModel, name: string) {
  for (const node of model.nodes.values()) {
    const found = node.actions.get(name);
    if (found) return found;
  }
  return undefined;
}
