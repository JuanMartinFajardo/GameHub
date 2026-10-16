// SPDX-License-Identifier: Apache-2.0
/** La paleta de nodos: se arrastra un tipo al diagrama (o se pulsa para añadirlo al final). */

import { useLocale, useMessages } from "@gamehub/i18n";
import { NODE_KINDS } from "@gamehub/nomos";
import { useStudio } from "../context";
import { messages } from "../messages";
import { NODE_DRAG_TYPE } from "./Diagram";
import { kindName } from "./nodes";

const ICONS: Record<string, string> = {
  decision: "👤",
  simultaneous: "👥",
  window: "⏱",
  chance: "🎲",
  auto: "⚙",
  phase: "▣",
  terminal: "🏁",
};

export function Palette(props: { disabled?: boolean }) {
  const t = useMessages(messages);
  const { locale } = useLocale();
  const [state, studio] = useStudio();
  const parent =
    state.selection.kind !== "game"
      ? (studio.game?.flow.nodes.find(
          (n) => n.id === (state.selection as { node: string }).node && n.kind === "phase",
        )?.id ?? null)
      : null;
  return (
    <div
      className="gh-sd-palette"
      role="toolbar"
      aria-label={t("palette")}
      title={t("paletteHint")}
    >
      {NODE_KINDS.map((kind) => (
        <button
          key={kind}
          type="button"
          className={`gh-sd-palette__item gh-sd-palette__item--${kind}`}
          draggable={!props.disabled}
          disabled={props.disabled}
          data-kind={kind}
          aria-label={kindName(kind, locale)}
          title={kindName(kind, locale)}
          onDragStart={(e) => {
            e.dataTransfer.setData(NODE_DRAG_TYPE, kind);
            e.dataTransfer.effectAllowed = "copy";
          }}
          onClick={() => {
            const op: { op: string; kind: string; parent?: string } = { op: "addNode", kind };
            if (parent) op.parent = parent;
            studio.tryApply([op]);
          }}
        >
          <span aria-hidden="true">{ICONS[kind]}</span>
          <span className="gh-sd-palette__label">{kindName(kind, locale)}</span>
        </button>
      ))}
    </div>
  );
}
