// SPDX-License-Identifier: Apache-2.0
/** Tableros: rejilla, recorrido lineal y grafo. */

import { useMessages } from "@gamehub/i18n";
import { type CSSProperties, type ReactNode, useState } from "react";
import { cx } from "./basics";
import { messages } from "./messages";
import { Token } from "./pieces";

export interface GridProps {
  rows: number;
  columns: number;
  renderCell?: (row: number, column: number) => ReactNode;
  /** Qué se elige al pulsar: una casilla, una columna entera o una fila entera. */
  mode?: "cell" | "column" | "row";
  /** ¿Se puede elegir esta casilla (o, en modo columna/fila, su columna/fila)? */
  isTarget?: (row: number, column: number) => boolean;
  isSelected?: (row: number, column: number) => boolean;
  /** Casillas de la última jugada (se marcan sin resaltarlas). */
  isLast?: (row: number, column: number) => boolean;
  onSelect?: (row: number, column: number) => void;
  /** Casillas alternas oscuras (ajedrez, damas). */
  checkered?: boolean;
  /** Fondo neutro en vez de madera. */
  plain?: boolean;
  coordinates?: boolean;
  label?: string;
  cellLabel?: (row: number, column: number) => string;
  /** Tamaño de cada casilla (CSS), por defecto `--gh-cell-size`. */
  cellSize?: string;
}

export function Grid(props: GridProps) {
  const t = useMessages(messages);
  const { rows, columns, mode = "cell" } = props;
  const [hover, setHover] = useState<[number, number] | null>(null);
  const style = {
    "--gh-cols": columns,
    "--gh-rows": rows,
    ...(props.cellSize ? { "--gh-cell-size": props.cellSize } : {}),
  } as CSSProperties;
  const lined = (r: number, c: number) =>
    hover !== null &&
    ((mode === "column" && hover[1] === c) || (mode === "row" && hover[0] === r)) &&
    (props.isTarget?.(r, c) ?? false);
  const cell = (r: number, c: number) => {
    const target = props.isTarget?.(r, c) ?? false;
    const clickable = props.onSelect !== undefined && target;
    const className = cx(
      "gh-grid__cell",
      target && "gh-grid__cell--target",
      lined(r, c) && "gh-grid__cell--hover",
      props.isSelected?.(r, c) && "gh-grid__cell--selected",
      props.isLast?.(r, c) && "gh-grid__cell--last",
    );
    const content = (
      <>
        {props.coordinates && (
          <span className="gh-grid__coord" aria-hidden="true">
            {r},{c}
          </span>
        )}
        <span className="gh-grid__content">{props.renderCell?.(r, c)}</span>
      </>
    );
    const name =
      props.cellLabel?.(r, c) ??
      (mode === "column"
        ? t("column", { column: c })
        : mode === "row"
          ? t("row", { row: r })
          : t("cell", { row: r, column: c }));
    return (
      <td key={c} className={className} data-dark={(r + c) % 2 === 1}>
        {clickable ? (
          <button
            type="button"
            className="gh-grid__hit"
            aria-label={name}
            onClick={() => props.onSelect?.(r, c)}
            onMouseEnter={() => setHover([r, c])}
            onMouseLeave={() => setHover(null)}
            onFocus={() => setHover([r, c])}
            onBlur={() => setHover(null)}
          >
            {content}
          </button>
        ) : (
          content
        )}
      </td>
    );
  };
  return (
    <table
      className={cx(
        "gh-grid",
        props.checkered && "gh-grid--checkered",
        props.plain && "gh-grid--plain",
      )}
      style={style}
      aria-label={props.label}
    >
      <tbody>
        {Array.from({ length: rows }, (_, r) => (
          // biome-ignore lint/suspicious/noArrayIndexKey: filas fijas del tablero.
          <tr key={r}>{Array.from({ length: columns }, (_, c) => cell(r, c))}</tr>
        ))}
      </tbody>
    </table>
  );
}

export interface PlacedToken {
  at: number | string;
  color?: string;
  label?: string;
}

export interface TrackProps {
  spaces: number;
  tokens?: PlacedToken[];
  isTarget?: (index: number) => boolean;
  onSelect?: (index: number) => void;
  label?: string;
  /** Numerar las casillas desde 1 (por defecto) o desde 0. */
  from?: 0 | 1;
}

export function Track({ spaces, tokens = [], isTarget, onSelect, label, from = 1 }: TrackProps) {
  const t = useMessages(messages);
  return (
    <ol className="gh-track" aria-label={label}>
      {Array.from({ length: spaces }, (_, i) => {
        const here = tokens.filter((tk) => tk.at === i);
        const target = isTarget?.(i) ?? false;
        const inner = (
          <>
            <span className="gh-track__index">{i + from}</span>
            {here.map((tk, k) => (
              // biome-ignore lint/suspicious/noArrayIndexKey: fichas sin identidad propia.
              <Token key={k} size="sm" color={tk.color} label={tk.label} />
            ))}
          </>
        );
        return (
          <li
            // biome-ignore lint/suspicious/noArrayIndexKey: casillas fijas del recorrido.
            key={i}
            className={cx("gh-track__space", target && "gh-grid__cell--target")}
          >
            {target && onSelect ? (
              <button
                type="button"
                className="gh-grid__hit"
                aria-label={t("space", { n: i + from })}
                onClick={() => onSelect(i)}
              >
                {inner}
              </button>
            ) : (
              inner
            )}
          </li>
        );
      })}
    </ol>
  );
}

export interface GraphNode {
  id: number | string;
  x: number;
  y: number;
  label?: string;
}

export interface GraphBoardProps {
  nodes: GraphNode[];
  edges: [number | string, number | string][];
  tokens?: PlacedToken[];
  isTarget?: (id: number | string) => boolean;
  onSelect?: (id: number | string) => void;
  width?: number;
  height?: number;
  label?: string;
}

export function GraphBoard(props: GraphBoardProps) {
  const { nodes, edges, tokens = [], width = 400, height = 300 } = props;
  const byId = new Map(nodes.map((n) => [n.id, n]));
  return (
    <svg
      className="gh-graph"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={props.label}
      width={width}
      height={height}
    >
      {edges.map(([a, b]) => {
        const p = byId.get(a);
        const q = byId.get(b);
        if (!p || !q) return null;
        return (
          <line key={`${a}-${b}`} x1={p.x} y1={p.y} x2={q.x} y2={q.y} className="gh-graph__edge" />
        );
      })}
      {nodes.map((n) => {
        const target = props.isTarget?.(n.id) ?? false;
        const here = tokens.filter((tk) => tk.at === n.id);
        return (
          // biome-ignore lint/a11y/noStaticElementInteractions: el nodo es parte del dibujo; hay alternativa por teclado en la barra de acciones.
          <g
            key={n.id}
            onClick={target && props.onSelect ? () => props.onSelect?.(n.id) : undefined}
          >
            <circle
              cx={n.x}
              cy={n.y}
              r={16}
              className={cx("gh-graph__node", target && "gh-graph__node--target")}
            />
            {n.label && (
              <text x={n.x} y={n.y + 30} textAnchor="middle" className="gh-graph__label">
                {n.label}
              </text>
            )}
            {here.map((tk, k) => (
              <circle
                // biome-ignore lint/suspicious/noArrayIndexKey: fichas sin identidad propia.
                key={k}
                cx={n.x + (k - (here.length - 1) / 2) * 10}
                cy={n.y}
                r={7}
                fill={tk.color ?? "var(--gh-text)"}
              >
                {tk.label && <title>{tk.label}</title>}
              </circle>
            ))}
          </g>
        );
      })}
    </svg>
  );
}
