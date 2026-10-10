// SPDX-License-Identifier: Apache-2.0
/**
 * La GameIR tal como la lee la UI genérica: los tipos de lo que usa (`spec/ir/v0`) y su análisis
 * (tipos de las variables, dominios de las acciones y pistas `ui`).
 */

import type { Translatable } from "@gamehub/i18n";

export type IrType = string | [string, ...unknown[]];

export interface IrStateVar {
  name: string;
  type: IrType;
  init: unknown;
  visibility?: unknown;
  size_visibility?: unknown;
  doc?: Translatable;
}

export interface IrParam {
  name: string;
  type: IrType;
  default: unknown;
  doc?: Translatable;
}

export type IrTypeDecl =
  | { kind: "enum"; name: string; values: string[]; doc?: Translatable }
  | { kind: "struct"; name: string; fields: { name: string; type: IrType }[]; doc?: Translatable };

export interface IrActionParam {
  name: string;
  type: IrType;
  domain: unknown;
  visibility?: unknown;
}

export interface IrAction {
  name: string;
  doc?: Translatable;
  params?: IrActionParam[];
}

export interface IrNode {
  id: string;
  kind: "decision" | "simultaneous" | "window" | "chance" | "auto" | "phase" | "terminal";
  doc?: Translatable;
  actions?: IrAction[];
  nodes?: IrNode[];
}

export interface UiVarHint {
  widget?: Widget;
  place?: Place;
  label?: Translatable;
}

export interface UiTypeHint {
  label?: Translatable;
  symbols?: Record<string, string>;
  colors?: Record<string, string>;
  labels?: Record<string, Translatable>;
  card?: { rank?: string; suit?: string };
}

export interface UiParamHint {
  label?: Translatable;
  input?: "cell" | "column" | "row" | "pick";
  of?: string;
}

export interface UiHints {
  state?: Record<string, UiVarHint>;
  params?: Record<string, { label?: Translatable }>;
  types?: Record<string, UiTypeHint>;
  actions?: Record<string, { label?: Translatable; params?: Record<string, UiParamHint> }>;
  nodes?: Record<string, { label?: Translatable }>;
  seats?: { colors?: string[]; names?: Translatable[] };
}

export interface GameIr {
  ir_version: string;
  game: { id: string; version: string };
  meta?: { title?: Translatable; description?: Translatable; tags?: string[] };
  players: { min: number; max: number };
  params?: IrParam[];
  types?: IrTypeDecl[];
  state: IrStateVar[];
  flow: { start: string; nodes: IrNode[] };
  ui?: UiHints;
}

export type Widget =
  | "grid"
  | "hand"
  | "pile"
  | "deck"
  | "row"
  | "dice"
  | "counter"
  | "chips"
  | "seat"
  | "hidden"
  | "value";

export type Place = "table" | "seats" | "top";

// --- Tipos -------------------------------------------------------------------------------------

export type TypeRef =
  | { kind: "Bool" | "Int" | "Real" | "Text" | "Seat" | "Cell" }
  | { kind: "enum"; name: string; values: string[] }
  | { kind: "struct"; name: string; fields: [string, TypeRef][] }
  | { kind: "option" | "list" | "set" | "per_player" | "zone" | "bag"; inner: TypeRef }
  | { kind: "map"; key: TypeRef; value: TypeRef }
  | { kind: "tuple"; items: TypeRef[] }
  | { kind: "grid"; inner: TypeRef }
  | { kind: "unknown" };

const PRIMITIVES = new Set(["Bool", "Int", "Real", "Text", "Seat", "Cell"]);

export function parseType(raw: IrType, decls: ReadonlyMap<string, IrTypeDecl>, depth = 0): TypeRef {
  if (depth > 32) return { kind: "unknown" };
  if (typeof raw === "string") {
    if (PRIMITIVES.has(raw)) return { kind: raw as "Int" };
    const decl = decls.get(raw);
    if (decl?.kind === "enum") return { kind: "enum", name: raw, values: decl.values };
    if (decl?.kind === "struct") {
      return {
        kind: "struct",
        name: raw,
        fields: decl.fields.map((f) => [f.name, parseType(f.type, decls, depth + 1)]),
      };
    }
    return { kind: "unknown" };
  }
  const [head, ...rest] = raw;
  const sub = (x: unknown) => parseType(x as IrType, decls, depth + 1);
  switch (head) {
    case "option":
    case "list":
    case "set":
    case "per_player":
    case "zone":
    case "bag":
      return { kind: head, inner: sub(rest[0]) };
    case "map":
      return { kind: "map", key: sub(rest[0]), value: sub(rest[1]) };
    case "tuple":
      return { kind: "tuple", items: rest.map(sub) };
    case "grid":
      return { kind: "grid", inner: sub(rest[2]) };
    default:
      return { kind: "unknown" };
  }
}

/** El tipo de cada elemento de una colección (o null si no lo es). */
export function elementType(t: TypeRef): TypeRef | null {
  switch (t.kind) {
    case "list":
    case "set":
    case "zone":
    case "bag":
    case "per_player":
      return t.inner;
    default:
      return null;
  }
}

// --- Juego analizado ---------------------------------------------------------------------------

export interface StateVarModel {
  name: string;
  type: TypeRef;
  /** El tipo de cada asiento si es per_player; si no, el mismo `type`. */
  base: TypeRef;
  perPlayer: boolean;
  widget: Widget;
  place: Place;
  label: Translatable;
  /** Nadie la ve nunca (visibilidad `none`): no se dibuja salvo que una pista lo pida. */
  secret: boolean;
}

/** Un número de la IR que se conoce al empezar la partida: una constante o una opción. */
export type Bound = number | { param: string };

export interface ParamInput {
  kind: "cell" | "column" | "row" | "pick" | "choice";
  /** La variable de estado sobre la que se elige (rejilla o zona). */
  of?: string;
  /** Para `pick` sobre una zona per_player: de qué asiento (expresión de la IR: `["actor"]`,
   * `["var", "leader"]`, `["const", 1]`…). */
  seat?: unknown;
  /** Para `pick`: se eligen varios elementos (una lista o un conjunto). */
  many?: boolean;
  min?: Bound;
  max?: Bound;
}

export interface ActionParamModel {
  name: string;
  type: TypeRef;
  label: Translatable;
  input: ParamInput;
}

export interface ActionModel {
  name: string;
  label: Translatable;
  doc?: Translatable;
  params: ActionParamModel[];
}

export interface NodeModel {
  id: string;
  kind: IrNode["kind"];
  label: Translatable;
  actions: Map<string, ActionModel>;
}

export interface GameModel {
  ir: GameIr;
  id: string;
  title: Translatable;
  description?: Translatable;
  decls: Map<string, IrTypeDecl>;
  types: Map<string, UiTypeHint>;
  vars: StateVarModel[];
  nodes: Map<string, NodeModel>;
  params: {
    name: string;
    type: TypeRef;
    label: Translatable;
    doc?: Translatable;
    default: unknown;
  }[];
  seatColors?: string[];
  seatNames?: Translatable[];
}

function humanizeName(name: string): string {
  const words = name
    .replace(/[_-]+/g, " ")
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .trim()
    .toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function defaultWidget(base: TypeRef, perPlayer: boolean, secret: boolean): Widget {
  switch (base.kind) {
    case "grid":
      return "grid";
    case "zone":
    case "bag":
      return perPlayer ? "hand" : secret ? "deck" : "row";
    case "list":
    case "set":
      return "row";
    case "Int":
    case "Real":
      return "counter";
    case "Seat":
      return "seat";
    default:
      return "value";
  }
}

/** Analiza la IR una vez: tipos, variables, acciones de cada nodo y pistas. */
export function buildModel(ir: GameIr): GameModel {
  const decls = new Map((ir.types ?? []).map((d) => [d.name, d]));
  const ui = ir.ui ?? {};
  const vars: StateVarModel[] = ir.state.map((v) => {
    const type = parseType(v.type, decls);
    const perPlayer = type.kind === "per_player";
    const base = type.kind === "per_player" ? type.inner : type;
    const hint = ui.state?.[v.name] ?? {};
    const secret = v.visibility === "none";
    return {
      name: v.name,
      type,
      base,
      perPlayer,
      widget: hint.widget ?? defaultWidget(base, perPlayer, secret),
      place: hint.place ?? (perPlayer ? "seats" : "table"),
      label: hint.label ?? humanizeName(v.name),
      secret: secret && hint.widget === undefined,
    };
  });
  const nodes = new Map<string, NodeModel>();
  const walk = (list: IrNode[]) => {
    for (const node of list) {
      const actions = new Map<string, ActionModel>();
      for (const a of node.actions ?? []) {
        const hint = ui.actions?.[a.name];
        actions.set(a.name, {
          name: a.name,
          label: hint?.label ?? humanizeName(a.name),
          doc: a.doc,
          params: (a.params ?? []).map((p) => {
            const type = parseType(p.type, decls);
            const phint = hint?.params?.[p.name];
            return {
              name: p.name,
              type,
              label: phint?.label ?? humanizeName(p.name),
              input: inputFor(p, type, phint, vars),
            };
          }),
        });
      }
      nodes.set(node.id, {
        id: node.id,
        kind: node.kind,
        label: ui.nodes?.[node.id]?.label ?? humanizeName(node.id),
        actions,
      });
      walk(node.nodes ?? []);
    }
  };
  walk(ir.flow.nodes);
  return {
    ir,
    id: ir.game.id,
    title: ir.meta?.title ?? humanizeName(ir.game.id),
    description: ir.meta?.description,
    decls,
    types: new Map(Object.entries(ui.types ?? {})),
    vars,
    nodes,
    params: (ir.params ?? []).map((p) => ({
      name: p.name,
      type: parseType(p.type, decls),
      label: ui.params?.[p.name]?.label ?? p.doc ?? humanizeName(p.name),
      doc: p.doc,
      default: p.default,
    })),
    seatColors: ui.seats?.colors,
    seatNames: ui.seats?.names,
  };
}

// --- Cómo se elige cada argumento --------------------------------------------------------------

type Expr = unknown[];

function isExpr(x: unknown, op: string): x is Expr {
  return Array.isArray(x) && x[0] === op;
}

/** `["var", Z]` o `["index", ["var", Z], asiento]` → la zona y la expresión del asiento. */
function zoneRef(e: unknown): { name: string; seat?: unknown } | null {
  if (isExpr(e, "var") && typeof e[1] === "string") return { name: e[1] };
  if (isExpr(e, "index") && isExpr(e[1], "var") && typeof e[1][1] === "string") {
    return { name: e[1][1], seat: e[2] };
  }
  return null;
}

function bound(e: unknown): Bound | undefined {
  if (isExpr(e, "const") && typeof e[1] === "number") return e[1];
  if (isExpr(e, "param") && typeof e[1] === "string") return { param: e[1] };
  return undefined;
}

/** El valor de un límite con las opciones de la partida. */
export function resolveBound(
  b: Bound | undefined,
  params: Record<string, unknown>,
): number | undefined {
  if (b === undefined || typeof b === "number") return b;
  const value = params[b.param];
  return typeof value === "number" ? value : undefined;
}

/** El asiento de una expresión sencilla de la IR (`actor`, una constante o una variable). */
export function resolveSeat(
  e: unknown,
  actor: number | null,
  state: Record<string, unknown>,
): number | null {
  if (isExpr(e, "actor")) return actor;
  if (isExpr(e, "const") && typeof e[1] === "number") return e[1];
  if (isExpr(e, "var") && typeof e[1] === "string") {
    const value = state[e[1]];
    return typeof value === "number" ? value : null;
  }
  return null;
}

/**
 * Cómo elegir un argumento: la pista `ui` si la hay; si no, se deduce del dominio
 * (`cells(G)` → pulsar una casilla de G; `subsets(items(Z), a, b)` → elegir varios de la zona Z;
 * `items(Z)` → elegir uno); el resto se elige de una lista de botones.
 */
function inputFor(
  p: IrActionParam,
  type: TypeRef,
  hint: UiParamHint | undefined,
  vars: StateVarModel[],
): ParamInput {
  const byName = new Map(vars.map((v) => [v.name, v]));
  if (hint?.input !== undefined && hint.of !== undefined) {
    const v = byName.get(hint.of);
    return {
      kind: hint.input,
      of: hint.of,
      ...(v?.perPlayer ? { seat: ["actor"] } : {}),
      many: hint.input === "pick" && (type.kind === "list" || type.kind === "set"),
    };
  }
  const d = p.domain;
  if (isExpr(d, "cells") && isExpr(d[1], "var") && typeof d[1][1] === "string") {
    return { kind: "cell", of: d[1][1] };
  }
  if (isExpr(d, "subsets") && isExpr(d[1], "items")) {
    const zone = zoneRef(d[1][1]);
    if (zone && byName.has(zone.name)) {
      const min = bound(d[2]);
      const max = bound(d[3]);
      return {
        kind: "pick",
        of: zone.name,
        ...(zone.seat !== undefined ? { seat: zone.seat } : {}),
        many: true,
        ...(min !== undefined ? { min } : {}),
        ...(max !== undefined ? { max } : {}),
      };
    }
  }
  if (isExpr(d, "items")) {
    const zone = zoneRef(d[1]);
    if (zone && byName.has(zone.name)) {
      return {
        kind: "pick",
        of: zone.name,
        ...(zone.seat !== undefined ? { seat: zone.seat } : {}),
        many: false,
      };
    }
  }
  return { kind: "choice" };
}
