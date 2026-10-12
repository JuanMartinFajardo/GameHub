// SPDX-License-Identifier: Apache-2.0
/**
 * Diferencias entre dos versiones de un juego, para verlas en el diagrama: nodos y transiciones
 * añadidos, quitados o cambiados. Se compara el modelo (no el texto), así que el formato y los
 * comentarios no cuentan; los nodos se emparejan por nombre y las transiciones por su posición
 * en su nodo o acción.
 */

import type { GameModel, NodeModel, TransitionModel } from "../types";
import { type DiffStatus, edgeId, nodeId } from "./graph";

export interface ModelDiff {
  /** Por id del diagrama (`n:Nodo`, `t:Nodo:i`…). */
  status: Map<string, DiffStatus>;
  /** Nodos que solo están en la otra versión (se dibujan como fantasmas). */
  removed: NodeModel[];
  summary: { added: string[]; removed: string[]; changed: string[] };
}

/** Lo que importa de un nodo para decidir si cambió (sin posiciones). */
function signature(node: NodeModel): string {
  return JSON.stringify({
    kind: node.kind,
    parent: node.parent,
    members: node.members,
    lets: node.lets,
    blocks: node.blocks,
    effects: node.effects,
    doc: node.doc ?? null,
    actions: node.actions.map((a) => ({
      name: a.name,
      params: a.params,
      requires: a.requires,
      effects: a.effects,
      visibility: a.visibility,
    })),
  });
}

function transitionSignature(t: TransitionModel): string {
  return JSON.stringify([t.target, t.when, t.effects]);
}

function transitions(node: NodeModel): [string, TransitionModel][] {
  const out: [string, TransitionModel][] = [];
  for (const a of node.actions) {
    a.transitions.forEach((t, i) => {
      out.push([edgeId(node.id, a.name, i), t]);
    });
  }
  node.transitions.forEach((t, i) => {
    out.push([edgeId(node.id, null, i), t]);
  });
  return out;
}

/** Diferencias de `current` respecto de `base`. */
export function diffModels(base: GameModel, current: GameModel): ModelDiff {
  const status = new Map<string, DiffStatus>();
  const summary = { added: [] as string[], removed: [] as string[], changed: [] as string[] };
  const before = new Map(base.flow.nodes.map((n) => [n.id, n]));
  const after = new Map(current.flow.nodes.map((n) => [n.id, n]));
  for (const node of current.flow.nodes) {
    const old = before.get(node.id);
    if (!old) {
      status.set(nodeId(node.id), "added");
      summary.added.push(node.id);
    } else if (signature(old) !== signature(node)) {
      status.set(nodeId(node.id), "changed");
      summary.changed.push(node.id);
    }
    const oldEdges = new Map(old ? transitions(old) : []);
    for (const [id, t] of transitions(node)) {
      const was = oldEdges.get(id);
      if (!was) status.set(id, "added");
      else if (transitionSignature(was) !== transitionSignature(t)) status.set(id, "changed");
    }
    if (old && !status.has(nodeId(node.id))) {
      const now = new Set(transitions(node).map(([id]) => id));
      if ([...oldEdges.keys()].some((id) => !now.has(id))) {
        status.set(nodeId(node.id), "changed");
        summary.changed.push(node.id);
      }
    }
  }
  const removed = base.flow.nodes.filter((n) => !after.has(n.id));
  for (const node of removed) {
    status.set(nodeId(node.id), "removed");
    summary.removed.push(node.id);
  }
  return { status, removed, summary };
}

/** El modelo actual con los nodos quitados añadidos como fantasmas (para dibujarlos). */
export function withGhosts(current: GameModel, diff: ModelDiff): GameModel {
  if (diff.removed.length === 0) return current;
  const present = new Set(current.flow.nodes.map((n) => n.id));
  const ghosts = diff.removed.map((n) => ({
    ...n,
    local: false,
    parent: n.parent && present.has(n.parent) ? n.parent : null,
    transitions: n.transitions.filter((t) => present.has(t.target) || t.target === "exit"),
    actions: n.actions.map((a) => ({
      ...a,
      transitions: a.transitions.filter((t) => present.has(t.target)),
    })),
  }));
  return { ...current, flow: { ...current.flow, nodes: [...current.flow.nodes, ...ghosts] } };
}
