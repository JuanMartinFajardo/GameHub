// SPDX-License-Identifier: Apache-2.0
/**
 * Tipos de lo que manda el servidor del Studio (ver `gamehub.studio.model` y
 * `gamehub.studio.session`). Las posiciones son desplazamientos UTF-16 en el texto: `[desde, hasta]`.
 */

import type { NodeKind } from "@gamehub/nomos";

export type Span = [number, number];
export type Translatable = string | Record<string, string>;

export interface Located {
  span: Span | null;
  /** Viene de este archivo (si no, del juego base de una variante: se ve, no se edita aquí). */
  local: boolean;
  nameSpan?: Span | null;
  doc?: Translatable;
}

export interface TransitionModel extends Located {
  index: number;
  target: string;
  when: string | null;
  effects: string | null;
}

export interface ActionParamModel {
  name: string;
  type: string | null;
  domain: string | null;
  visibility: string | null;
  sizeVisibility: string | null;
}

export interface ActionModel extends Located {
  name: string;
  params: ActionParamModel[];
  requires: string | null;
  effects: string | null;
  visibility: string | null;
  transitions: TransitionModel[];
}

export interface NodeModel extends Located {
  id: string;
  kind: NodeKind;
  parent: string | null;
  fullSpan: Span | null;
  members: Record<string, string>;
  lets: { name: string; value: string }[];
  blocks: Record<string, string | null>;
  effects: string | null;
  actions: ActionModel[];
  transitions: TransitionModel[];
  /** En una fase: su inicio y sus nodos. */
  start?: { target: string; span: Span | null };
  children?: string[];
}

export interface StateVarModel extends Located {
  name: string;
  type: string;
  init: string | null;
  visibility: string | null;
  sizeVisibility: string | null;
}

export interface ParamModel extends Located {
  name: string;
  type: string;
  default: string;
}

export type TypeModel =
  | (Located & { kind: "enum"; name: string; values: string[] })
  | (Located & { kind: "struct"; name: string; fields: { name: string; type: string }[] });

export interface FunctionModel extends Located {
  name: string;
  params: { name: string; type: string }[];
  returns: string;
  body: string;
}

export interface UiEntryModel extends Located {
  target: string;
  hints: string;
}

export interface GameModel {
  name: string;
  extends: string | null;
  span: Span | null;
  meta: Record<string, unknown>;
  players: { min: number; max: number; local: boolean } | null;
  params: ParamModel[];
  asserts: (Located & { expr: string; message: Translatable | null })[];
  types: TypeModel[];
  state: StateVarModel[];
  functions: FunctionModel[];
  externals: { name: string; kind: "enum" | "struct" | "fn"; module: string }[];
  flow: {
    span: Span | null;
    start: { target: string; setup: string | null; span: Span | null; local: boolean } | null;
    nodes: NodeModel[];
  };
  ui: UiEntryModel[];
  tests: (Located & { name: string; body: string })[];
  invariants: (Located & { expr: string })[];
}

/** Lo que devuelve `gamehub/tests`: cada test y los invariantes en partidas al azar. */
export interface TestReport {
  tests: { name: string; ok: boolean; from?: number; to?: number; failure: Problem | null }[];
  invariants: number;
  playouts: { games: number; states: number; failure: Problem | null };
}

export interface DocumentModel {
  games: { name: string; kind: "game" | "alias"; extends: string | null; span: Span | null }[];
  game: GameModel | null;
}

export interface Problem {
  severity: "error" | "warning";
  code: string;
  message: string;
  from?: number;
  to?: number;
  help?: string;
  notes?: string[];
}

export interface Classification {
  labels: string[];
  players: { min: number; max: number };
  chance: boolean;
  perfect_information: boolean;
  simultaneous: boolean;
  zero_sum: boolean | null;
}

/** Lo que manda el servidor tras analizar un documento (`gamehub/analysis`). */
export interface Analysis {
  uri: string;
  version: number | null;
  syntaxOk: boolean;
  compiled: boolean;
  model: DocumentModel | null;
  problems: Problem[];
  classification: Classification | null;
}

/** Una operación de edición (ver `gamehub.studio.edits`). */
export type Op = { op: string } & Record<string, unknown>;

/** Qué elemento quedó creado o cambiado tras una edición. */
export interface Focus {
  node?: string;
  action?: string;
  transition?: number;
  state?: string;
  param?: string;
  type?: string;
  fn?: string;
}

export interface FragmentError {
  message: string;
  offset: number;
  length: number;
  help?: string;
}

/** Error de una edición: el mensaje y, si lo hay, el campo y los errores del trozo escrito. */
export interface EditFailure {
  message: string;
  field?: string;
  errors?: FragmentError[];
  /** Qué campo del formulario hizo la edición (para enseñar el error allí). */
  key?: string;
}

/** Lo que hay seleccionado en el diagrama y en el inspector. */
export type Selection =
  | { kind: "game" }
  | { kind: "node"; node: string }
  | { kind: "action"; node: string; action: string }
  | { kind: "transition"; node: string; action?: string; index: number };

export interface WorkspaceFile {
  path: string;
  name: string;
  package?: string;
}

export interface TemplateInfo {
  id: string;
  title: Translatable;
  description: Translatable;
}

export interface WorkspaceInfo {
  root: string;
  name: string;
  rootUri: string;
  open: string | null;
  files: WorkspaceFile[];
  templates: TemplateInfo[];
}

export interface OpenedFile {
  path: string;
  uri: string;
  text: string;
  mtime: number;
  layout: LayoutFile | null;
}

/** El archivo hermano `<juego>.layout.json`: posiciones del diagrama por juego. */
export interface LayoutFile {
  version?: number;
  games?: Record<string, GameLayout>;
}

export interface GameLayout {
  direction?: "DOWN" | "RIGHT";
  nodes?: Record<string, { x: number; y: number }>;
  collapsed?: string[];
}

// --- Simulador ---------------------------------------------------------------------------------

export interface SimStep {
  kind: "start" | "action" | "chance";
  seat?: number;
  action?: { name: string; args: Record<string, unknown> };
  outcome?: number[];
  trace: string[][];
  nodes: string[];
}

export interface SimSnapshot {
  index: number;
  length: number;
  status: "decision" | "chance" | "terminal";
  node: string | null;
  path: string[];
  active: number[];
  omniscient: import("@gamehub/protocol").View;
  views: Record<string, import("@gamehub/protocol").View>;
  public: import("@gamehub/protocol").View;
  events: Record<string, Record<string, unknown>[]>;
  allEvents: Record<string, unknown>[];
  step: SimStep;
  legal: Record<string, import("@gamehub/protocol").Legal>;
  error: { message: string; node: string | null; index: number } | null;
  chance?: {
    enumerable: boolean;
    outcomes?: { outcome: number[]; probability: string; value: number }[];
  };
  payoffs?: unknown[];
  ranking?: number[];
}

export interface PlayoutStats {
  games: number;
  finished: number;
  truncated: number;
  errors: { game: number; message: string; node: string | null }[];
  errorCount: number;
  length: { min: number | null; max: number | null; mean: number | null };
  payoffMean: (number | null)[];
  winRate: (number | null)[];
  /** Partidas en que todos quedan primeros (no cuentan como victoria de nadie). */
  drawRate: number | null;
  coverage: Coverage;
  seconds: number;
}

export interface Coverage {
  nodes: Record<string, number>;
  actions: Record<string, number>;
  transitions: Record<string, number>;
}

export interface SizeEstimate {
  samples: number;
  log10States?: number;
  states?: string;
  meanLength?: number;
  meanBranching?: number | null;
  seconds?: number;
}

export interface TreeNode {
  path: number[];
  node: string | null;
  status: string;
  active: number[];
  children: {
    kind: "action" | "chance";
    seat?: number;
    action?: { name: string; args: Record<string, unknown> };
    outcome?: number[];
    probability?: string;
    label?: string;
    truncated?: boolean;
  }[];
  payoffs?: unknown[];
}
