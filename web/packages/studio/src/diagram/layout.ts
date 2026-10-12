// SPDX-License-Identifier: Apache-2.0
/**
 * Dónde va cada caja del diagrama. La primera vez (o al pedir «reordenar») se calcula con ELK
 * (algoritmo por capas, con las fases como subgrafos); después manda lo que el usuario movió, que
 * se guarda en el archivo hermano `<juego>.layout.json`. Una caja nueva se coloca cerca de la que
 * apunta a ella.
 */

import type ElkConstructor from "elkjs/lib/elk.bundled.js";
import type { GameLayout } from "../types";
import type { Graph, GraphNode } from "./graph";

export interface Placement {
  x: number;
  y: number;
  width: number;
  height: number;
}
export type Placements = Map<string, Placement>;
export type Direction = "DOWN" | "RIGHT";

const PHASE_PADDING = { top: 44, left: 24, bottom: 24, right: 24 };
const GAP = 56;

/** La clave de un nodo del diagrama en el archivo de disposición (legible: el nombre del nodo). */
export function layoutKey(id: string): string {
  if (id.startsWith("n:")) return id.slice(2);
  if (id === "s:") return "start";
  if (id.startsWith("s:")) return `start:${id.slice(2)}`;
  if (id.startsWith("x:")) return `exit:${id.slice(2)}`;
  return id;
}

interface ElkNode {
  id: string;
  width?: number;
  height?: number;
  x?: number;
  y?: number;
  children?: ElkNode[];
  edges?: { id: string; sources: string[]; targets: string[] }[];
  layoutOptions?: Record<string, string>;
}

let engine: InstanceType<typeof ElkConstructor> | null = null;

/** Disposición automática de todo el grafo con ELK (que se carga la primera vez: pesa). */
export async function autoLayout(graph: Graph, direction: Direction = "DOWN"): Promise<Placements> {
  if (!engine) {
    const { default: ELK } = await import("elkjs/lib/elk.bundled.js");
    engine = new ELK();
  }
  const kids = new Map<string | null, GraphNode[]>();
  for (const n of graph.nodes) {
    const list = kids.get(n.parent) ?? [];
    list.push(n);
    kids.set(n.parent, list);
  }
  const toElk = (n: GraphNode): ElkNode => {
    const children = kids.get(n.id);
    if (n.type === "phase" && children) {
      return {
        id: n.id,
        children: children.map(toElk),
        layoutOptions: {
          "elk.padding": `[top=${PHASE_PADDING.top},left=${PHASE_PADDING.left},bottom=${PHASE_PADDING.bottom},right=${PHASE_PADDING.right}]`,
        },
      };
    }
    return { id: n.id, width: n.width, height: n.height };
  };
  const ids = new Set(graph.nodes.map((n) => n.id));
  const root: ElkNode = {
    id: "root",
    layoutOptions: {
      "elk.algorithm": "layered",
      "elk.direction": direction,
      "elk.hierarchyHandling": "INCLUDE_CHILDREN",
      "elk.layered.spacing.nodeNodeBetweenLayers": "56",
      "elk.spacing.nodeNode": "36",
      "elk.layered.nodePlacement.strategy": "BRANDES_KOEPF",
      "elk.layered.crossingMinimization.semiInteractive": "true",
      // Los ciclos (volver a tirar, otra ronda) se rompen por el orden del texto: la flecha que
      // vuelve a un nodo anterior es la que sube, y el flujo empieza arriba.
      "elk.layered.cycleBreaking.strategy": "MODEL_ORDER",
    },
    children: (kids.get(null) ?? []).map(toElk),
    edges: graph.edges
      .filter((e) => ids.has(e.source) && ids.has(e.target) && e.source !== e.target)
      .map((e) => ({ id: e.id, sources: [e.source], targets: [e.target] })),
  };
  const result = (await engine.layout(root as never)) as unknown as ElkNode;
  const out: Placements = new Map();
  const visit = (node: ElkNode) => {
    for (const child of node.children ?? []) {
      out.set(child.id, {
        x: Math.round(child.x ?? 0),
        y: Math.round(child.y ?? 0),
        width: Math.round(child.width ?? 0),
        height: Math.round(child.height ?? 0),
      });
      visit(child);
    }
  };
  visit(result);
  return out;
}

/**
 * Posiciones finales: las guardadas, las automáticas (si se dan) para lo que no está guardado y,
 * si no, cerca de quien apunta a la caja. Las fases toman el tamaño de lo que contienen.
 */
export function place(
  graph: Graph,
  saved: GameLayout | undefined,
  auto: Placements | null,
): Placements {
  const out: Placements = new Map();
  const stored = saved?.nodes ?? {};
  const byId = new Map(graph.nodes.map((n) => [n.id, n]));
  const missing: GraphNode[] = [];
  for (const n of graph.nodes) {
    const s = stored[layoutKey(n.id)];
    const a = auto?.get(n.id);
    if (s) out.set(n.id, { x: s.x, y: s.y, width: n.width, height: n.height });
    else if (a && !Object.keys(stored).length) out.set(n.id, { ...a });
    else missing.push(n);
  }
  // Cajas nuevas: debajo (o a la derecha) de una caja que apunta a ellas, sin pisar a nadie.
  const direction = saved?.direction ?? "DOWN";
  for (const n of missing) {
    const from = graph.edges.find(
      (e) => e.target === n.id && out.has(e.source) && byId.get(e.source)?.parent === n.parent,
    );
    const siblings = [...out.entries()].filter(([id]) => byId.get(id)?.parent === n.parent);
    let x = 0;
    let y = n.parent ? PHASE_PADDING.top : 0;
    if (from) {
      const p = out.get(from.source) as Placement;
      x = direction === "DOWN" ? p.x : p.x + p.width + GAP;
      y = direction === "DOWN" ? p.y + p.height + GAP : p.y;
    } else if (siblings.length) {
      const lowest = Math.max(...siblings.map(([, p]) => p.y + p.height));
      x = Math.min(...siblings.map(([, p]) => p.x));
      y = lowest + GAP;
    } else if (n.parent) {
      x = PHASE_PADDING.left;
    }
    while (siblings.some(([, p]) => overlaps(p, { x, y, width: n.width, height: n.height }))) {
      if (direction === "DOWN") x += n.width + GAP / 2;
      else y += n.height + GAP / 2;
    }
    out.set(n.id, { x, y, width: n.width, height: n.height });
  }
  fitPhases(graph, out);
  return out;
}

function overlaps(a: Placement, b: Placement): boolean {
  return a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;
}

/** Cada fase abarca a sus hijos (de dentro afuera). */
export function fitPhases(graph: Graph, placements: Placements): void {
  const depth = (id: string): number => {
    let d = 0;
    let current = graph.nodes.find((n) => n.id === id)?.parent ?? null;
    while (current) {
      d += 1;
      current = graph.nodes.find((n) => n.id === current)?.parent ?? null;
    }
    return d;
  };
  const phases = graph.nodes
    .filter((n) => n.type === "phase")
    .sort((a, b) => depth(b.id) - depth(a.id));
  for (const phase of phases) {
    const children = graph.nodes.filter((n) => n.parent === phase.id);
    const own = placements.get(phase.id);
    if (!own || children.length === 0) continue;
    let right = 260;
    let bottom = 120;
    for (const child of children) {
      const p = placements.get(child.id);
      if (!p) continue;
      right = Math.max(right, p.x + p.width + PHASE_PADDING.right);
      bottom = Math.max(bottom, p.y + p.height + PHASE_PADDING.bottom);
    }
    placements.set(phase.id, {
      ...own,
      width: Math.max(own.width, right),
      height: Math.max(own.height, bottom),
    });
  }
}

/** Las posiciones que se guardan (sin tamaños). */
export function toLayout(placements: Placements, base: GameLayout = {}): GameLayout {
  const nodes: Record<string, { x: number; y: number }> = {};
  for (const [id, p] of placements)
    nodes[layoutKey(id)] = { x: Math.round(p.x), y: Math.round(p.y) };
  return { ...base, nodes };
}
