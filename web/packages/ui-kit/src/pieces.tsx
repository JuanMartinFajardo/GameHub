// SPDX-License-Identifier: Apache-2.0
/** Dados y fichas. */

import { useMessages } from "@gamehub/i18n";
import type { CSSProperties, ReactNode } from "react";
import { cx } from "./basics";
import { messages } from "./messages";

const PIPS: Record<number, [number, number][]> = {
  1: [[50, 50]],
  2: [
    [28, 28],
    [72, 72],
  ],
  3: [
    [28, 28],
    [50, 50],
    [72, 72],
  ],
  4: [
    [28, 28],
    [72, 28],
    [28, 72],
    [72, 72],
  ],
  5: [
    [28, 28],
    [72, 28],
    [50, 50],
    [28, 72],
    [72, 72],
  ],
  6: [
    [28, 26],
    [72, 26],
    [28, 50],
    [72, 50],
    [28, 74],
    [72, 74],
  ],
};

export interface DieProps {
  /** De 1 a 6 se dibujan puntos; otros valores, el número. Sin valor: un dado oculto. */
  value?: number | null;
  size?: "sm" | "md" | "lg";
  highlight?: boolean;
  /** Color de la cara (por defecto, blanco). */
  color?: string;
  label?: string;
  onClick?: () => void;
  disabled?: boolean;
}

export function Die({
  value = null,
  size = "md",
  highlight,
  color,
  label,
  onClick,
  disabled,
}: DieProps) {
  const t = useMessages(messages);
  const hidden = value === null;
  const pips = value !== null ? PIPS[value] : undefined;
  const art = (
    <svg viewBox="0 0 100 100" aria-hidden="true">
      <rect
        x="4"
        y="4"
        width="92"
        height="92"
        rx="18"
        fill={color ?? "var(--gh-die)"}
        stroke="var(--gh-card-edge)"
        strokeWidth="2"
      />
      {hidden && (
        <text
          x="50"
          y="54"
          fontSize="44"
          textAnchor="middle"
          dominantBaseline="middle"
          fill="var(--gh-text-muted)"
        >
          ?
        </text>
      )}
      {pips?.map(([x, y]) => (
        <circle key={`${x}-${y}`} cx={x} cy={y} r="9" fill="var(--gh-die-pip)" />
      ))}
      {!hidden && pips === undefined && (
        <text
          x="50"
          y="54"
          fontSize="40"
          fontWeight="700"
          textAnchor="middle"
          dominantBaseline="middle"
          fill="var(--gh-die-pip)"
        >
          {value}
        </text>
      )}
    </svg>
  );
  const className = cx(
    "gh-die",
    size !== "md" && `gh-die--${size}`,
    hidden && "gh-die--hidden",
    highlight && "gh-die--highlight",
  );
  const name = label ?? (hidden ? t("hiddenDie") : t("die", { value: value ?? "" }));
  if (onClick) {
    return (
      <button
        type="button"
        className={className}
        aria-label={name}
        onClick={onClick}
        disabled={disabled}
      >
        {art}
      </button>
    );
  }
  return (
    <span className={className}>
      {art}
      <span className="gh-visually-hidden">{name}</span>
    </span>
  );
}

/** Varios dados en fila. */
export function Dice(props: {
  values: (number | null)[];
  size?: DieProps["size"];
  highlight?: (value: number | null, index: number) => boolean;
  label?: string;
}) {
  return (
    <ul className="gh-dice" aria-label={props.label}>
      {props.values.map((v, i) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: la posición es la identidad de cada dado.
        <li key={i}>
          <Die value={v} size={props.size} highlight={props.highlight?.(v, i)} />
        </li>
      ))}
    </ul>
  );
}

export interface TokenProps {
  /** Color de la ficha (cualquier color CSS). */
  color?: string;
  /** Un símbolo o texto corto encima (o, con `glyph`, solo el símbolo, sin ficha). */
  children?: ReactNode;
  glyph?: boolean;
  size?: "sm" | "md" | "lg" | "fill";
  label?: string;
}

export function Token({ color, children, glyph = false, size = "md", label }: TokenProps) {
  const style = color ? ({ "--gh-token-color": color } as CSSProperties) : undefined;
  return (
    <span
      className={cx("gh-token", glyph && "gh-token--glyph", size !== "md" && `gh-token--${size}`)}
      style={style}
    >
      <span aria-hidden={label !== undefined || undefined}>{children}</span>
      {label !== undefined && <span className="gh-visually-hidden">{label}</span>}
    </span>
  );
}
