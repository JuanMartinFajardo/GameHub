// SPDX-License-Identifier: Apache-2.0
/**
 * Exportar el diagrama como SVG (vectorial, de verdad: rectángulos, flechas y texto, sin HTML
 * dentro) o como PNG (el SVG pintado en un canvas). Se dibuja a partir del grafo y de las
 * posiciones, igual que en pantalla pero sin interacción.
 */

import type { BoxData, Graph, GraphEdge, MarkerData } from "./graph";
import type { Placement, Placements } from "./layout";

const KIND_LABEL: Record<string, string> = {
  decision: "decisión",
  simultaneous: "simultáneo",
  window: "ventana",
  chance: "azar",
  auto: "automático",
  phase: "fase",
  terminal: "final",
};

const COLORS: Record<string, { fill: string; stroke: string }> = {
  decision: { fill: "#eef2ff", stroke: "#4f46e5" },
  simultaneous: { fill: "#f5f3ff", stroke: "#7c3aed" },
  window: { fill: "#fff7ed", stroke: "#c2410c" },
  chance: { fill: "#ecfeff", stroke: "#0e7490" },
  auto: { fill: "#f3f4f6", stroke: "#6b7280" },
  phase: { fill: "#fafafa", stroke: "#94a3b8" },
  terminal: { fill: "#f0fdf4", stroke: "#15803d" },
};

function esc(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** Posiciones absolutas (las de los hijos de una fase son relativas a ella). */
export function absolute(graph: Graph, placements: Placements): Map<string, Placement> {
  const parents = new Map(graph.nodes.map((n) => [n.id, n.parent]));
  const out = new Map<string, Placement>();
  const resolve = (id: string): Placement | null => {
    const known = out.get(id);
    if (known) return known;
    const own = placements.get(id);
    if (!own) return null;
    const parent = parents.get(id);
    const base = parent ? resolve(parent) : null;
    const abs = base ? { ...own, x: own.x + base.x, y: own.y + base.y } : { ...own };
    out.set(id, abs);
    return abs;
  };
  for (const n of graph.nodes) resolve(n.id);
  return out;
}

function edgePath(a: Placement, b: Placement, handleY: number | null): string {
  const sx = handleY === null ? a.x + a.width / 2 : a.x + a.width;
  const sy = handleY === null ? a.y + a.height : a.y + handleY;
  const tx = b.x + b.width / 2;
  const ty = b.y;
  if (ty > sy + 10) {
    const my = (sy + ty) / 2;
    return `M${sx},${sy} C${sx},${my} ${tx},${my} ${tx},${ty}`;
  }
  // Hacia arriba (un bucle): por el lado.
  const side = Math.max(a.x + a.width, b.x + b.width) + 40;
  return `M${sx},${sy} C${side},${sy} ${side},${ty - 30} ${tx},${ty}`;
}

/** El diagrama en SVG. */
export function toSvg(graph: Graph, placements: Placements, title = ""): string {
  const abs = absolute(graph, placements);
  let minX = Number.POSITIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;
  for (const p of abs.values()) {
    minX = Math.min(minX, p.x);
    minY = Math.min(minY, p.y);
    maxX = Math.max(maxX, p.x + p.width);
    maxY = Math.max(maxY, p.y + p.height);
  }
  if (!Number.isFinite(minX)) {
    minX = minY = 0;
    maxX = maxY = 100;
  }
  const pad = 40;
  const top = title ? 36 : 0;
  const width = Math.ceil(maxX - minX + pad * 2 + 60);
  const height = Math.ceil(maxY - minY + pad * 2 + top);
  const dx = pad - minX;
  const dy = pad + top - minY;
  const parts: string[] = [];
  parts.push(
    `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" font-family="system-ui, -apple-system, Segoe UI, sans-serif">`,
    `<title>${esc(title || "Diagrama")}</title>`,
    '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#475569"/></marker></defs>',
    `<rect width="${width}" height="${height}" fill="#ffffff"/>`,
  );
  if (title) {
    parts.push(
      `<text x="${pad}" y="28" font-size="18" font-weight="700" fill="#111827">${esc(title)}</text>`,
    );
  }
  const shift = (p: Placement): Placement => ({ ...p, x: p.x + dx, y: p.y + dy });
  // Fases detrás, luego flechas, luego cajas.
  for (const n of graph.nodes.filter((n) => n.type === "phase")) {
    const p = abs.get(n.id);
    if (!p) continue;
    const s = shift(p);
    const data = n.data as BoxData;
    parts.push(
      `<rect x="${s.x}" y="${s.y}" width="${s.width}" height="${s.height}" rx="14" fill="${COLORS.phase?.fill}" stroke="${COLORS.phase?.stroke}" stroke-dasharray="6 4"/>`,
      `<text x="${s.x + 14}" y="${s.y + 24}" font-size="13" font-weight="700" fill="#334155">fase ${esc(data.title)}</text>`,
    );
  }
  for (const e of graph.edges) parts.push(edgeSvg(e, graph, abs, shift));
  for (const n of graph.nodes) {
    if (n.type === "phase") continue;
    const p = abs.get(n.id);
    if (!p) continue;
    const s = shift(p);
    if (n.type === "marker") {
      const data = n.data as MarkerData;
      const cx = s.x + s.width / 2;
      const cy = s.y + s.height / 2;
      parts.push(
        data.kind === "start"
          ? `<circle cx="${cx}" cy="${cy}" r="8" fill="#111827"/>`
          : `<circle cx="${cx}" cy="${cy}" r="8" fill="#fff" stroke="#111827" stroke-width="3"/>`,
      );
      continue;
    }
    const data = n.data as BoxData;
    const color = COLORS[data.kind] ?? { fill: "#fff", stroke: "#475569" };
    const double = data.kind === "simultaneous" || data.kind === "terminal";
    parts.push(
      `<rect x="${s.x}" y="${s.y}" width="${s.width}" height="${s.height}" rx="${data.kind === "chance" ? 18 : 10}" fill="${color.fill}" stroke="${color.stroke}" stroke-width="${double ? 3 : 1.5}"/>`,
    );
    if (double) {
      parts.push(
        `<rect x="${s.x + 4}" y="${s.y + 4}" width="${s.width - 8}" height="${s.height - 8}" rx="8" fill="none" stroke="${color.stroke}" stroke-width="1"/>`,
      );
    }
    parts.push(
      `<text x="${s.x + 12}" y="${s.y + 15}" font-size="10" fill="${color.stroke}">${esc(KIND_LABEL[data.kind] ?? data.kind)}</text>`,
      `<text x="${s.x + 12}" y="${s.y + 29}" font-size="13" font-weight="700" fill="#111827">${esc(data.title)}</text>`,
    );
    let y = s.y + 48;
    for (const line of data.lines) {
      parts.push(
        `<text x="${s.x + 12}" y="${y}" font-size="11" fill="#374151" font-family="ui-monospace, monospace">${esc(line)}</text>`,
      );
      y += 18;
    }
    for (const a of data.actions) {
      parts.push(
        `<rect x="${s.x + 8}" y="${y - 13}" width="${s.width - 16}" height="20" rx="5" fill="#ffffff" stroke="#cbd5e1"/>`,
        `<text x="${s.x + 14}" y="${y + 1}" font-size="11" fill="#1f2937" font-family="ui-monospace, monospace">${esc(a.label)}</text>`,
      );
      y += 24;
    }
  }
  parts.push("</svg>");
  return parts.join("\n");
}

function edgeSvg(
  e: GraphEdge,
  graph: Graph,
  abs: Map<string, Placement>,
  shift: (p: Placement) => Placement,
): string {
  const a = abs.get(e.source);
  const b = abs.get(e.target);
  if (!a || !b) return "";
  let handleY: number | null = null;
  if (e.sourceHandle?.startsWith("a:")) {
    const source = graph.nodes.find((n) => n.id === e.source);
    const data = source?.data as BoxData | undefined;
    const i = data?.actions.findIndex((x) => `a:${x.name}` === e.sourceHandle) ?? -1;
    if (data && i >= 0) handleY = 34 + data.lines.length * 18 + 12 + i * 24;
  }
  const path = edgePath(shift(a), shift(b), handleY);
  const out = [
    `<path d="${path}" fill="none" stroke="#475569" stroke-width="1.5" marker-end="url(#arrow)"/>`,
  ];
  const label = [e.data.order ? `${e.data.order}.` : "", e.label].filter(Boolean).join(" ");
  if (label) {
    const sa = shift(a);
    const sb = shift(b);
    const x = (sa.x + sa.width / 2 + sb.x + sb.width / 2) / 2;
    const y = (sa.y + sa.height + sb.y) / 2;
    const w = label.length * 6.2 + 12;
    out.push(
      `<rect x="${x - w / 2}" y="${y - 10}" width="${w}" height="18" rx="9" fill="#ffffff" stroke="#e2e8f0"/>`,
      `<text x="${x}" y="${y + 3}" font-size="10.5" text-anchor="middle" fill="#334155">${esc(label)}</text>`,
    );
  }
  return out.join("\n");
}

/** El SVG pintado en un PNG (en el navegador). */
export async function toPng(svg: string, scale = 2): Promise<Blob> {
  const url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
  try {
    const image = new Image();
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve();
      image.onerror = () => reject(new Error("no se pudo dibujar el SVG"));
      image.src = url;
    });
    const canvas = document.createElement("canvas");
    canvas.width = image.width * scale;
    canvas.height = image.height * scale;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("sin canvas");
    ctx.scale(scale, scale);
    ctx.drawImage(image, 0, 0);
    return await new Promise<Blob>((resolve, reject) =>
      canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("sin PNG"))), "image/png"),
    );
  } finally {
    URL.revokeObjectURL(url);
  }
}

/** Ofrece un archivo para descargar. */
export function download(name: string, data: Blob | string, type = "image/svg+xml"): void {
  const blob = typeof data === "string" ? new Blob([data], { type }) : data;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
