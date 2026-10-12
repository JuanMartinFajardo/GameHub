// SPDX-License-Identifier: Apache-2.0
/**
 * El lienzo del diagrama (React Flow). Dibuja el grafo del flow y convierte los gestos en
 * operaciones de edición: arrastrar un tipo de nodo desde la paleta lo crea, unir dos cajas crea
 * una transición (desde una acción, la de esa acción), soltar una caja dentro de una fase la mete
 * en ella, Supr borra. Las posiciones se guardan aparte (no son reglas).
 */

import {
  applyEdgeChanges,
  applyNodeChanges,
  Background,
  BackgroundVariant,
  type Connection,
  Controls,
  type Edge,
  type EdgeChange,
  MarkerType,
  MiniMap,
  type Node,
  type NodeChange,
  type OnNodeDrag,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
} from "@xyflow/react";
import {
  type DragEvent,
  type MouseEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { Focus, GameLayout, GameModel, Op, Selection } from "../types";
import { edgeTypes } from "./edges";
import { buildGraph, type DiagramOptions, type Graph, type GraphNode, nodeId } from "./graph";
import { autoLayout, type Direction, layoutKey, type Placements, place, toLayout } from "./layout";
import { nodeTypes } from "./nodes";

export const NODE_DRAG_TYPE = "application/x-gamehub-node";
const FIT = { padding: 0.15, maxZoom: 1.1 };

export interface DiagramHandle {
  graph: Graph;
  placements: Placements;
  fit: () => void;
}

export interface DiagramProps {
  game: GameModel;
  layout: GameLayout | undefined;
  options: DiagramOptions;
  selection: Selection | null;
  editable: boolean;
  onSelect: (selection: Selection) => void;
  onOps: (ops: Op[]) => Promise<Focus | null>;
  onLayout: (layout: GameLayout) => void;
  onToggleCollapse: (phase: string) => void;
  /** Cambia para pedir una disposición automática nueva. */
  relayout?: number;
  onReady?: (handle: DiagramHandle) => void;
  onContextMenu?: (
    target: { node?: string; edge?: string },
    point: { x: number; y: number },
  ) => void;
}

export function Diagram(props: DiagramProps) {
  return (
    <ReactFlowProvider>
      <DiagramCanvas {...props} />
    </ReactFlowProvider>
  );
}

const nameOf = (id: string) => (id.startsWith("n:") ? id.slice(2) : null);

function DiagramCanvas(props: DiagramProps) {
  const { game, options, editable } = props;
  const flow = useReactFlow();
  const graph = useMemo(() => buildGraph(game, options), [game, options]);
  const direction: Direction = props.layout?.direction ?? "DOWN";
  /** Posiciones de esta sesión (empiezan siendo las guardadas). */
  const memory = useRef<Record<string, { x: number; y: number }>>({
    ...(props.layout?.nodes ?? {}),
  });
  const [placements, setPlacements] = useState<Placements | null>(null);
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const fitted = useRef(false);
  const lastRelayout = useRef(props.relayout ?? 0);

  // Disposición: la de memoria; con ELK si no hay ninguna o si se pide reordenar.
  // biome-ignore lint/correctness/useExhaustiveDependencies: se recalcula con el grafo o al reordenar.
  useEffect(() => {
    let cancelled = false;
    const reorder = (props.relayout ?? 0) !== lastRelayout.current;
    lastRelayout.current = props.relayout ?? 0;
    const run = async () => {
      const known = Object.keys(memory.current).length > 0;
      let auto: Placements | null = null;
      if (!known || reorder) {
        auto = await autoLayout(graph, direction);
        memory.current = {};
      }
      const next = place(graph, { ...props.layout, direction, nodes: memory.current }, auto);
      if (cancelled) return;
      for (const [id, p] of next) memory.current[layoutKey(id)] = { x: p.x, y: p.y };
      setPlacements(next);
      if (reorder) props.onLayout(toLayout(next, { ...props.layout, direction }));
    };
    run().catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [graph, props.relayout, direction]);

  const selectedNode =
    props.selection && props.selection.kind !== "game" ? props.selection.node : null;
  const selectedEdge =
    props.selection?.kind === "transition"
      ? props.selection.action
        ? `t:${props.selection.node}:${props.selection.action}:${props.selection.index}`
        : `t:${props.selection.node}:${props.selection.index}`
      : null;

  useEffect(() => {
    if (!placements) return;
    setNodes(
      graph.nodes.map((n) => {
        const p = placements.get(n.id) ?? { x: 0, y: 0, width: n.width, height: n.height };
        const local = n.type === "marker" || (n.data as { local?: boolean }).local !== false;
        return {
          id: n.id,
          type: n.type,
          position: { x: p.x, y: p.y },
          parentId: n.parent ?? undefined,
          data: n.data,
          width: p.width,
          height: p.height,
          style: { width: p.width, height: p.height },
          draggable: editable && local,
          connectable: editable && local,
          selectable: n.type !== "marker",
          selected: selectedNode !== null && n.id === nodeId(selectedNode),
          // Las fases al fondo, luego las flechas y encima las cajas (con sus asas: si las
          // tapara una flecha, no se podría tirar otra desde ellas).
          zIndex: n.type === "phase" ? 0 : 2,
        } satisfies Node;
      }),
    );
    setEdges(
      graph.edges.map((e) => ({
        id: e.id,
        source: e.source,
        sourceHandle: e.sourceHandle,
        target: e.target,
        type: "transition",
        label: e.label,
        data: e.data,
        selected: e.id === selectedEdge,
        markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
        reconnectable: editable && !e.data.start ? "target" : false,
        zIndex: 1,
      })),
    );
  }, [graph, placements, selectedNode, selectedEdge, editable]);

  useEffect(() => {
    if (placements && !fitted.current && nodes.length) {
      fitted.current = true;
      requestAnimationFrame(() => flow.fitView(FIT));
    }
  }, [placements, nodes.length, flow]);

  // Si el lienzo cambia de tamaño (otra vista, la ventana) y nadie ha movido ni ampliado el
  // diagrama a mano, se vuelve a encuadrar.
  const canvas = useRef<HTMLDivElement>(null);
  const moved = useRef(false);
  useEffect(() => {
    const element = canvas.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    let last = { width: element.clientWidth, height: element.clientHeight };
    const observer = new ResizeObserver(() => {
      const size = { width: element.clientWidth, height: element.clientHeight };
      if (!size.width || !size.height) return; // oculto (vista de texto)
      if (Math.abs(size.width - last.width) < 2 && Math.abs(size.height - last.height) < 2) return;
      last = size;
      if (fitted.current && !moved.current) requestAnimationFrame(() => flow.fitView(FIT));
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [flow]);

  useEffect(() => {
    if (placements) {
      props.onReady?.({ graph, placements, fit: () => flow.fitView(FIT) });
    }
  }, [graph, placements, flow, props.onReady]);

  // Lo seleccionado (un nodo recién añadido, el elegido en el texto) se trae a la vista.
  useEffect(() => {
    const element = canvas.current;
    if (!selectedNode || !placements || !element) return;
    const frame = requestAnimationFrame(() => {
      const node = flow.getInternalNode(nodeId(selectedNode));
      if (!node) return;
      const { x, y } = node.internals.positionAbsolute;
      const width = node.measured.width ?? node.width ?? 0;
      const height = node.measured.height ?? node.height ?? 0;
      const box = element.getBoundingClientRect();
      const a = flow.flowToScreenPosition({ x, y });
      const b = flow.flowToScreenPosition({ x: x + width, y: y + height });
      const visible = a.x >= box.left && a.y >= box.top && b.x <= box.right && b.y <= box.bottom;
      if (!visible && box.width && box.height) {
        flow.setCenter(x + width / 2, y + height / 2, { zoom: flow.getZoom(), duration: 200 });
      }
    });
    return () => cancelAnimationFrame(frame);
  }, [selectedNode, placements, flow]);

  const onNodesChange = useCallback((changes: NodeChange[]) => {
    setNodes((current) => applyNodeChanges(changes, current));
  }, []);
  const onEdgesChange = useCallback((changes: EdgeChange[]) => {
    setEdges((current) => applyEdgeChanges(changes, current));
  }, []);

  /** La fase (visible, desplegada) que contiene el punto, la más interior. */
  const phaseAt = useCallback(
    (point: { x: number; y: number }, except: string | null): string | null => {
      let found: { id: string; area: number } | null = null;
      for (const n of flow.getNodes()) {
        if (n.type !== "phase" || n.id === except) continue;
        if (except && isInside(graph, n.id, except)) continue;
        const abs = flow.getInternalNode(n.id)?.internals.positionAbsolute;
        const w = n.measured?.width ?? n.width ?? 0;
        const h = n.measured?.height ?? n.height ?? 0;
        if (!abs) continue;
        if (point.x >= abs.x && point.x <= abs.x + w && point.y >= abs.y && point.y <= abs.y + h) {
          if (!found || w * h < found.area) found = { id: n.id, area: w * h };
        }
      }
      return found ? (nameOf(found.id) ?? null) : null;
    },
    [flow, graph],
  );

  const saveLayout = useCallback(() => {
    props.onLayout({ ...props.layout, direction, nodes: { ...memory.current } });
  }, [props.onLayout, props.layout, direction]);

  const onNodeDragStop: OnNodeDrag = useCallback(
    (_event, _node, dragged) => {
      let moved: Op | null = null;
      for (const n of dragged) {
        memory.current[layoutKey(n.id)] = {
          x: Math.round(n.position.x),
          y: Math.round(n.position.y),
        };
        const name = nameOf(n.id);
        if (!name || !editable || dragged.length > 1) continue;
        const internal = flow.getInternalNode(n.id);
        const abs = internal?.internals.positionAbsolute;
        if (!abs) continue;
        const center = { x: abs.x + (n.measured?.width ?? 0) / 2, y: abs.y + 16 };
        const target = phaseAt(center, n.id);
        const current = game.flow.nodes.find((x) => x.id === name)?.parent ?? null;
        if (target !== current) {
          moved = { op: "moveNode", node: name, parent: target };
          const parentAbs = target
            ? flow.getInternalNode(nodeId(target))?.internals.positionAbsolute
            : null;
          memory.current[name] = {
            x: Math.round(abs.x - (parentAbs?.x ?? 0)),
            y: Math.round(abs.y - (parentAbs?.y ?? 0)),
          };
        }
      }
      saveLayout();
      if (moved) props.onOps([moved]).catch(() => undefined);
    },
    [editable, flow, game, phaseAt, props.onOps, saveLayout],
  );

  const onConnect = useCallback(
    (connection: Connection) => {
      if (!editable) return;
      const target = connection.target.startsWith("x:")
        ? "exit"
        : (nameOf(connection.target) ?? null);
      if (!target) return;
      if (connection.source.startsWith("s:")) {
        const phase = connection.source.slice(2) || null;
        props.onOps([{ op: "setStart", phase, target }]).catch(() => undefined);
        return;
      }
      const node = nameOf(connection.source);
      if (!node) return;
      const action = connection.sourceHandle?.startsWith("a:")
        ? connection.sourceHandle.slice(2)
        : null;
      const op: Op = { op: "addTransition", node, target };
      if (action) op.action = action;
      props.onOps([op]).catch(() => undefined);
    },
    [editable, props.onOps],
  );

  const onReconnect = useCallback(
    (old: Edge, connection: Connection) => {
      const data = old.data as { node: string; action: string | null; index: number } | undefined;
      if (!editable || !data || data.index < 0) return;
      const target = connection.target.startsWith("x:") ? "exit" : nameOf(connection.target);
      if (!target) return;
      const op: Op = { op: "updateTransition", node: data.node, index: data.index, target };
      if (data.action) op.action = data.action;
      props.onOps([op]).catch(() => undefined);
    },
    [editable, props.onOps],
  );

  const onDelete = useCallback(
    ({ nodes: gone, edges: cut }: { nodes: Node[]; edges: Edge[] }) => {
      if (!editable) return;
      const ops: Op[] = [];
      const removedNodes = new Set(gone.map((n) => nameOf(n.id)).filter((x): x is string => !!x));
      const transitions = cut
        .map(
          (e) =>
            e.data as
              | { node: string; action: string | null; index: number; start?: boolean }
              | undefined,
        )
        .filter(
          (d): d is { node: string; action: string | null; index: number } => !!d && d.index >= 0,
        )
        .filter((d) => !removedNodes.has(d.node))
        .sort((a, b) => b.index - a.index);
      for (const d of transitions) {
        const op: Op = { op: "deleteTransition", node: d.node, index: d.index };
        if (d.action) op.action = d.action;
        ops.push(op);
      }
      for (const name of removedNodes) ops.push({ op: "deleteNode", node: name });
      if (ops.length) props.onOps(ops).catch(() => undefined);
    },
    [editable, props.onOps],
  );

  const onDrop = useCallback(
    (event: DragEvent) => {
      event.preventDefault();
      const kind = event.dataTransfer.getData(NODE_DRAG_TYPE);
      if (!kind || !editable) return;
      const point = flow.screenToFlowPosition({ x: event.clientX, y: event.clientY });
      const parent = phaseAt(point, null);
      const parentAbs = parent
        ? flow.getInternalNode(nodeId(parent))?.internals.positionAbsolute
        : null;
      const op: Op = { op: "addNode", kind };
      if (parent) op.parent = parent;
      props
        .onOps([op])
        .then((focus) => {
          if (focus?.node) {
            memory.current[focus.node] = {
              x: Math.round(point.x - (parentAbs?.x ?? 0) - 110),
              y: Math.round(point.y - (parentAbs?.y ?? 0) - 20),
            };
            saveLayout();
          }
        })
        .catch(() => undefined);
    },
    [editable, flow, phaseAt, props.onOps, saveLayout],
  );

  const onNodeClick = useCallback(
    (event: MouseEvent, node: Node) => {
      const element = event.target as HTMLElement;
      const fold = element.closest("[data-fold]")?.getAttribute("data-fold");
      if (fold) {
        props.onToggleCollapse(fold);
        return;
      }
      const name = nameOf(node.id);
      if (!name) return;
      const action = element.closest("[data-action]")?.getAttribute("data-action");
      if ((node.data as { collapsed?: boolean }).collapsed && event.detail === 2) {
        props.onToggleCollapse(name);
        return;
      }
      props.onSelect(
        action ? { kind: "action", node: name, action } : { kind: "node", node: name },
      );
    },
    [props.onSelect, props.onToggleCollapse],
  );

  const onEdgeClick = useCallback(
    (_event: MouseEvent, edge: Edge) => {
      const d = edge.data as { node: string; action: string | null; index: number } | undefined;
      if (!d || d.index < 0) return;
      props.onSelect(
        d.action
          ? { kind: "transition", node: d.node, action: d.action, index: d.index }
          : { kind: "transition", node: d.node, index: d.index },
      );
    },
    [props.onSelect],
  );

  return (
    // biome-ignore lint/a11y/noStaticElementInteractions: zona donde soltar lo que se arrastra de la paleta; con teclado, los botones de la paleta añaden el nodo.
    <div
      ref={canvas}
      className="gh-sd-canvas"
      onDragOver={(e) => e.preventDefault()}
      onDrop={onDrop}
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeDragStop={onNodeDragStop}
        onConnect={onConnect}
        onReconnect={onReconnect}
        onDelete={onDelete}
        onNodeClick={onNodeClick}
        onEdgeClick={onEdgeClick}
        onPaneClick={() => props.onSelect({ kind: "game" })}
        onMoveStart={(event) => {
          // Sin evento: lo ha movido el programa (encuadrar), no la persona.
          if (event) moved.current = true;
        }}
        onNodeContextMenu={(event, node) => {
          if (!props.onContextMenu) return;
          event.preventDefault();
          const name = nameOf(node.id);
          if (name) props.onContextMenu({ node: name }, { x: event.clientX, y: event.clientY });
        }}
        onEdgeContextMenu={(event, edge) => {
          if (!props.onContextMenu) return;
          event.preventDefault();
          props.onContextMenu({ edge: edge.id }, { x: event.clientX, y: event.clientY });
        }}
        deleteKeyCode={editable ? ["Delete", "Backspace"] : null}
        nodesDraggable={editable}
        nodesConnectable={editable}
        edgesReconnectable={editable}
        connectionRadius={28}
        minZoom={0.15}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
        fitView={false}
      >
        <Background variant={BackgroundVariant.Dots} gap={18} size={1} />
        <Controls
          showInteractive={false}
          onFitView={() => {
            moved.current = false;
          }}
        />
        <MiniMap pannable zoomable className="gh-sd-minimap" style={{ width: 160, height: 100 }} />
      </ReactFlow>
    </div>
  );
}

function isInside(graph: Graph, phase: string, node: string): boolean {
  const parents = new Map<string, string | null>(
    graph.nodes.map((n: GraphNode) => [n.id, n.parent]),
  );
  let current = parents.get(phase) ?? null;
  while (current) {
    if (current === node) return true;
    current = parents.get(current) ?? null;
  }
  return false;
}
