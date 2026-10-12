// SPDX-License-Identifier: Apache-2.0
/**
 * Del modelo del documento al grafo del diagrama (sin React): una caja por nodo, las fases como
 * contenedores, una flecha por transición (las de una acción salen de la acción) y marcas de
 * inicio y de salida de las fases. Aquí se decide también qué se ve resaltado: el nodo activo del
 * simulador, las transiciones recorridas, la cobertura de las partidas masivas, los puntos de
 * ruptura, los problemas y las diferencias con otra versión.
 */

import type { NodeKind } from "@gamehub/nomos";
import type { Coverage, GameModel, NodeModel, TransitionModel } from "../types";

export type DiffStatus = "added" | "removed" | "changed";

export interface DiagramOptions {
  collapsed?: ReadonlySet<string>;
  breakpoints?: ReadonlySet<string>;
  /** Peor problema de cada nodo. */
  problems?: ReadonlyMap<string, "error" | "warning">;
  coverage?: Coverage | null;
  /** Nodo activo del simulador y sus fases. */
  active?: readonly string[] | null;
  /** Claves de las transiciones del último paso del simulador (`node/N/i`, `action/N/a/i`). */
  taken?: ReadonlySet<string>;
  /** Diferencias con otra versión, por id de nodo o de flecha. */
  diff?: ReadonlyMap<string, DiffStatus> | null;
}

export interface ActionRow {
  name: string;
  label: string;
  /** Tiene transiciones propias (la flecha sale de la acción). */
  own: boolean;
  covered?: number;
}

export interface BoxData {
  [key: string]: unknown;
  id: string;
  kind: NodeKind;
  title: string;
  lines: string[];
  actions: ActionRow[];
  local: boolean;
  breakpoint: boolean;
  problem: "error" | "warning" | null;
  active: boolean;
  covered: number | null;
  diff: DiffStatus | null;
  collapsed: boolean;
  children: number;
}

export interface MarkerData {
  [key: string]: unknown;
  kind: "start" | "exit";
  owner: string | null;
}

export interface EdgeData {
  [key: string]: unknown;
  node: string;
  action: string | null;
  index: number;
  target: string;
  when: string | null;
  effects: string | null;
  /** Número de orden si el nodo tiene varias (las transiciones se prueban en orden). */
  order: number | null;
  /** «si no»: la última, sin condición, de varias. */
  otherwise: boolean;
  covered: number | null;
  taken: boolean;
  diff: DiffStatus | null;
  start?: boolean;
}

export interface GraphNode {
  id: string;
  type: "box" | "phase" | "marker";
  parent: string | null;
  width: number;
  height: number;
  data: BoxData | MarkerData;
}

export interface GraphEdge {
  id: string;
  source: string;
  sourceHandle: string | null;
  target: string;
  label: string;
  data: EdgeData;
}

export interface Graph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export const nodeId = (name: string) => `n:${name}`;
export const startId = (phase: string | null) => (phase ? `s:${phase}` : "s:");
export const exitId = (phase: string) => `x:${phase}`;
export const edgeId = (node: string, action: string | null, index: number) =>
  action ? `t:${node}:${action}:${index}` : `t:${node}:${index}`;
/** Clave de la traza del motor para una transición. */
export const traceKey = (node: string, action: string | null, index: number) =>
  action ? `action/${node}/${action}/${index}` : `node/${node}/${index}`;

export const BOX_WIDTH = 220;
const LINE = 18;
const MARKER = 20;

export function shorten(text: string, max = 34): string {
  const flat = text.replace(/\s+/g, " ").trim();
  return flat.length > max ? `${flat.slice(0, max - 1)}…` : flat;
}

function summary(node: NodeModel): string[] {
  const m = node.members;
  switch (node.kind) {
    case "decision":
      return m.actor ? [`▸ ${shorten(m.actor)}`] : [];
    case "simultaneous":
      return m.actors ? [`▸▸ ${shorten(m.actors)}`] : [];
    case "window":
      return [`${m.mode ?? "priority"} · ${shorten(m.eligible ?? "")}`];
    case "chance":
    case "auto":
      return (node.effects ?? "")
        .split("\n")
        .filter((l) => l.trim() && !l.trim().startsWith("//"))
        .slice(0, 3)
        .map((l) => shorten(l));
    case "terminal":
      return m.payoff ? [`= ${shorten(m.payoff)}`] : [];
    default:
      return [];
  }
}

function actionLabel(a: NodeModel["actions"][number]): string {
  const params = a.params.map((p) => p.name).join(", ");
  return shorten(`${a.name}(${params})`, 30);
}

export function boxHeight(lines: number, actions: number): number {
  return 34 + lines * LINE + actions * 24 + (lines || actions ? 8 : 0);
}

/** El grafo del flow de un juego. */
export function buildGraph(game: GameModel, options: DiagramOptions = {}): Graph {
  const collapsed = options.collapsed ?? new Set<string>();
  const nodes = game.flow.nodes;
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const coverage = options.coverage ?? null;
  const active = new Set(options.active ?? []);
  const taken = options.taken ?? new Set<string>();

  /** La fase plegada más externa que oculta un nodo (o null si se ve). */
  const hiddenBy = (id: string): string | null => {
    let found: string | null = null;
    let current = byId.get(id)?.parent ?? null;
    while (current) {
      if (collapsed.has(current)) found = current;
      current = byId.get(current)?.parent ?? null;
    }
    return found;
  };
  const visible = (id: string) => hiddenBy(id) ?? id;

  const out: Graph = { nodes: [], edges: [] };
  for (const node of nodes) {
    if (hiddenBy(node.id)) continue;
    const isPhase = node.kind === "phase";
    const lines = isPhase ? [] : summary(node);
    const actions: ActionRow[] = node.actions.map((a) => ({
      name: a.name,
      label: actionLabel(a),
      own: a.transitions.length > 0,
      covered: coverage ? (coverage.actions[`${node.id}.${a.name}`] ?? 0) : undefined,
    }));
    const children = nodes.filter((n) => n.parent === node.id).length;
    const data: BoxData = {
      id: node.id,
      kind: node.kind,
      title: node.id,
      lines,
      actions,
      local: node.local,
      breakpoint: options.breakpoints?.has(node.id) ?? false,
      problem: options.problems?.get(node.id) ?? null,
      active: active.has(node.id),
      covered: coverage ? (coverage.nodes[node.id] ?? 0) : null,
      diff: options.diff?.get(nodeId(node.id)) ?? null,
      collapsed: isPhase && collapsed.has(node.id),
      children,
    };
    const folded = isPhase && collapsed.has(node.id);
    out.nodes.push({
      id: nodeId(node.id),
      type: isPhase && !folded ? "phase" : "box",
      parent: node.parent ? nodeId(node.parent) : null,
      width: BOX_WIDTH,
      height: isPhase && !folded ? 120 : boxHeight(lines.length, actions.length),
      data,
    });
    if (isPhase && !folded) {
      out.nodes.push(marker(startId(node.id), "start", node.id, nodeId(node.id)));
      if (exits(node.id, nodes))
        out.nodes.push(marker(exitId(node.id), "exit", node.id, nodeId(node.id)));
      if (node.start) {
        out.edges.push(startEdge(node.id, node.start.target, visible));
      }
    }
  }
  const start = game.flow.start;
  if (start) {
    out.nodes.unshift(marker(startId(null), "start", null, null));
    out.edges.push(startEdge(null, start.target, visible));
  }

  const seen = new Set<string>();
  const addTransitions = (node: NodeModel, action: string | null, list: TransitionModel[]) => {
    list.forEach((t, i) => {
      const id = edgeId(node.id, action, i);
      const sourceHidden = hiddenBy(node.id) !== null;
      let targetId: string;
      let targetHidden = false;
      if (t.target === "exit") {
        const phase = node.parent;
        if (!phase) return;
        targetId = sourceHidden ? nodeId(visible(phase)) : exitId(phase);
      } else {
        targetHidden = byId.has(t.target) && hiddenBy(t.target) !== null;
        targetId = nodeId(visible(t.target));
      }
      const sourceId = nodeId(visible(node.id));
      const folded = sourceHidden || targetHidden;
      if (folded && sourceId === targetId) return; // dentro de una fase plegada
      const key = traceKey(node.id, action, i);
      const many = list.length > 1;
      const data: EdgeData = {
        node: node.id,
        action,
        index: i,
        target: t.target,
        when: t.when,
        effects: t.effects,
        order: many ? i + 1 : null,
        otherwise: many && t.when === null && i === list.length - 1,
        covered: coverage ? (coverage.transitions[key] ?? 0) : null,
        taken: taken.has(key),
        diff: options.diff?.get(id) ?? null,
      };
      const label = data.when ? shorten(data.when, 28) : data.otherwise ? "si no" : "";
      const dedupe = folded ? `${sourceId}>${targetId}>${label}` : id;
      if (seen.has(dedupe)) return;
      seen.add(dedupe);
      out.edges.push({
        id,
        source: sourceId,
        sourceHandle: action && !sourceHidden ? `a:${action}` : "out",
        target: targetId,
        label,
        data,
      });
    });
  };
  for (const node of nodes) {
    for (const action of node.actions) addTransitions(node, action.name, action.transitions);
    addTransitions(node, null, node.transitions);
  }
  return out;
}

function marker(id: string, kind: "start" | "exit", owner: string | null, parent: string | null) {
  return {
    id,
    type: "marker" as const,
    parent,
    width: MARKER,
    height: MARKER,
    data: { kind, owner } satisfies MarkerData,
  };
}

function startEdge(
  phase: string | null,
  target: string,
  visible: (id: string) => string,
): GraphEdge {
  return {
    id: phase ? `st:${phase}` : "st:",
    source: startId(phase),
    sourceHandle: "out",
    target: nodeId(visible(target)),
    label: "",
    data: {
      node: phase ?? "",
      action: null,
      index: -1,
      target,
      when: null,
      effects: null,
      order: null,
      otherwise: false,
      covered: null,
      taken: false,
      diff: null,
      start: true,
    },
  };
}

function exits(phase: string, nodes: NodeModel[]): boolean {
  return nodes.some(
    (n) =>
      n.parent === phase &&
      (n.transitions.some((t) => t.target === "exit") ||
        n.actions.some((a) => a.transitions.some((t) => t.target === "exit"))),
  );
}

/** El nodo, la acción o la transición del modelo cuyo texto contiene la posición `offset`. */
export function elementAt(
  game: GameModel,
  offset: number,
):
  | { kind: "node"; node: string }
  | { kind: "action"; node: string; action: string }
  | { kind: "transition"; node: string; action?: string; index: number }
  | null {
  const inside = (span: [number, number] | null | undefined) =>
    span != null && span[0] <= offset && offset <= span[1];
  let best: ReturnType<typeof elementAt> = null;
  let size = Number.POSITIVE_INFINITY;
  const consider = (span: [number, number] | null | undefined, found: NonNullable<typeof best>) => {
    if (span && inside(span) && span[1] - span[0] < size) {
      size = span[1] - span[0];
      best = found;
    }
  };
  for (const node of game.flow.nodes) {
    consider(node.span, { kind: "node", node: node.id });
    for (const a of node.actions) {
      consider(a.span, { kind: "action", node: node.id, action: a.name });
      for (const [i, t] of a.transitions.entries()) {
        consider(t.span, { kind: "transition", node: node.id, action: a.name, index: i });
      }
    }
    for (const [i, t] of node.transitions.entries()) {
      consider(t.span, { kind: "transition", node: node.id, index: i });
    }
  }
  return best;
}

/** El peor problema de cada nodo (por posición en el texto). */
export function problemsByNode(
  game: GameModel,
  problems: { severity: "error" | "warning"; from?: number; to?: number }[],
): Map<string, "error" | "warning"> {
  const out = new Map<string, "error" | "warning">();
  for (const p of problems) {
    if (p.from === undefined) continue;
    const found = elementAt(game, p.from);
    if (!found) continue;
    if (out.get(found.node) !== "error") out.set(found.node, p.severity);
  }
  return out;
}
