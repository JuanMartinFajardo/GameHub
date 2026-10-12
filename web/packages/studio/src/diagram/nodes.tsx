// SPDX-License-Identifier: Apache-2.0
/** Las cajas del diagrama: un nodo de cada tipo, las fases y las marcas de inicio y salida. */

import { useLocale } from "@gamehub/i18n";
import { cx } from "@gamehub/ui-kit";
import { Handle, type Node, type NodeProps, Position } from "@xyflow/react";
import type { BoxData, MarkerData } from "./graph";

export type BoxNode = Node<BoxData, "box">;
export type PhaseNode = Node<BoxData, "phase">;
export type MarkerNode = Node<MarkerData, "marker">;

const ICONS: Record<string, string> = {
  decision: "👤",
  simultaneous: "👥",
  window: "⏱",
  chance: "🎲",
  auto: "⚙",
  phase: "▣",
  terminal: "🏁",
};

export const KIND_NAMES: Record<string, { es: string; en: string }> = {
  decision: { es: "decisión", en: "decision" },
  simultaneous: { es: "simultáneo", en: "simultaneous" },
  window: { es: "ventana", en: "window" },
  chance: { es: "azar", en: "chance" },
  auto: { es: "automático", en: "automatic" },
  phase: { es: "fase", en: "phase" },
  terminal: { es: "final", en: "terminal" },
};

/** El nombre del tipo de nodo en el idioma de la interfaz. */
export function kindName(kind: string, locale: string): string {
  return KIND_NAMES[kind]?.[locale === "en" ? "en" : "es"] ?? kind;
}

function Flags(props: { data: BoxData }) {
  const { data } = props;
  return (
    <span className="gh-sd-flags">
      {data.breakpoint ? (
        <span className="gh-sd-flag gh-sd-flag--break" title="punto de ruptura" />
      ) : null}
      {data.problem ? (
        <span className={cx("gh-sd-flag", `gh-sd-flag--${data.problem}`)} title={data.problem}>
          {data.problem === "error" ? "!" : "?"}
        </span>
      ) : null}
      {data.covered !== null ? (
        <span className={cx("gh-sd-count", data.covered === 0 && "is-zero")} title="veces">
          {data.covered}
        </span>
      ) : null}
    </span>
  );
}

export function BoxView(props: NodeProps<BoxNode>) {
  const { data, selected } = props;
  const { locale } = useLocale();
  return (
    <div
      className={cx(
        "gh-sd-box",
        `gh-sd-box--${data.kind}`,
        selected && "is-selected",
        data.active && "is-active",
        data.problem && `has-${data.problem}`,
        data.diff && `is-${data.diff}`,
        !data.local && "is-inherited",
      )}
      data-node={data.id}
    >
      <Handle type="target" position={Position.Top} className="gh-sd-handle" />
      <div className="gh-sd-box__head">
        <span className="gh-sd-box__icon" aria-hidden="true">
          {ICONS[data.kind]}
        </span>
        <span className="gh-sd-box__kind">{kindName(data.kind, locale)}</span>
        <Flags data={data} />
      </div>
      <div className="gh-sd-box__title">
        {data.title}
        {data.collapsed ? <span className="gh-sd-box__folded"> (+{data.children})</span> : null}
      </div>
      {data.lines.map((line, i) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: líneas fijas del resumen.
        <div key={i} className="gh-sd-box__line">
          {line}
        </div>
      ))}
      {data.actions.length ? (
        <ul className="gh-sd-actions">
          {data.actions.map((a) => (
            <li key={a.name} className="gh-sd-action" data-action={a.name}>
              <span>{a.label}</span>
              {a.covered !== undefined ? (
                <span className={cx("gh-sd-count", a.covered === 0 && "is-zero")}>{a.covered}</span>
              ) : null}
              <Handle
                type="source"
                id={`a:${a.name}`}
                position={Position.Right}
                className={cx("gh-sd-handle", "gh-sd-handle--action", !a.own && "is-free")}
              />
            </li>
          ))}
        </ul>
      ) : null}
      {data.kind !== "terminal" ? (
        <Handle type="source" id="out" position={Position.Bottom} className="gh-sd-handle" />
      ) : null}
    </div>
  );
}

export function PhaseView(props: NodeProps<PhaseNode>) {
  const { data, selected } = props;
  return (
    <div
      className={cx(
        "gh-sd-phase",
        selected && "is-selected",
        data.active && "is-active",
        data.problem && `has-${data.problem}`,
        data.diff && `is-${data.diff}`,
      )}
      data-node={data.id}
    >
      <Handle type="target" position={Position.Top} className="gh-sd-handle" />
      <div className="gh-sd-phase__head">
        <span aria-hidden="true">{ICONS.phase}</span>
        <span className="gh-sd-phase__title">{data.title}</span>
        <button
          type="button"
          className="gh-sd-phase__fold nodrag"
          data-fold={data.id}
          aria-label="plegar"
          title="plegar"
        >
          −
        </button>
        <Flags data={data} />
      </div>
      <Handle type="source" id="out" position={Position.Bottom} className="gh-sd-handle" />
    </div>
  );
}

export function MarkerView(props: NodeProps<MarkerNode>) {
  const { data } = props;
  return (
    <div
      className={cx("gh-sd-marker", `gh-sd-marker--${data.kind}`)}
      title={data.kind === "start" ? "inicio" : "salida de la fase"}
    >
      {data.kind === "exit" ? (
        <Handle type="target" position={Position.Top} className="gh-sd-handle" />
      ) : (
        <Handle type="source" id="out" position={Position.Bottom} className="gh-sd-handle" />
      )}
    </div>
  );
}

export const nodeTypes = { box: BoxView, phase: PhaseView, marker: MarkerView };
