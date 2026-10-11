// SPDX-License-Identifier: Apache-2.0
/** Manos (en abanico o en fila), montones y mazos. */

import { useMessages } from "@gamehub/i18n";
import { Children, type CSSProperties, type ReactNode } from "react";
import { cx } from "./basics";
import { PlayingCard } from "./cards";
import { messages } from "./messages";

export interface HandProps {
  children?: ReactNode;
  /** Cartas boca abajo que añadir al final (la mano de otro jugador: solo se ve el tamaño). */
  hidden?: number;
  /** En abanico (por defecto) o en fila. */
  layout?: "fan" | "flat";
  label?: string;
  className?: string;
}

export function Hand({ children, hidden = 0, layout = "fan", label, className }: HandProps) {
  const t = useMessages(messages);
  const items = [
    ...Children.toArray(children),
    // biome-ignore lint/suspicious/noArrayIndexKey: dorsos iguales; la posición es la identidad.
    ...Array.from({ length: hidden }, (_, i) => <PlayingCard key={`hidden-${i}`} faceDown />),
  ];
  const n = items.length;
  return (
    <ul className={cx("gh-hand", `gh-hand--${layout}`, className)} aria-label={label}>
      {n === 0 && <li className="gh-hand__empty">{t("empty")}</li>}
      {items.map((item, i) => {
        const angle = layout === "fan" && n > 1 ? (i - (n - 1) / 2) * Math.min(4, 40 / n) : 0;
        const style: CSSProperties | undefined = angle
          ? { transform: `rotate(${angle.toFixed(2)}deg)` }
          : undefined;
        return (
          // biome-ignore lint/suspicious/noArrayIndexKey: la posición en la mano es la identidad.
          <li key={i} style={style}>
            {item}
          </li>
        );
      })}
    </ul>
  );
}

export interface PileProps {
  /** Cuántos elementos tiene. */
  count: number;
  /** El de arriba, si se ve (por ejemplo, una carta boca arriba). */
  top?: ReactNode;
  /** Boca abajo: se dibuja el dorso de las cartas. */
  faceDown?: boolean;
  label?: string;
  className?: string;
}

export function Pile({ count, top, faceDown = false, label, className }: PileProps) {
  const t = useMessages(messages);
  const layers = Math.min(count, 3);
  return (
    <figure
      className={cx("gh-pile", className)}
      aria-label={`${label ? `${label}: ` : ""}${count === 1 ? t("card") : t("cards", { n: count })}`}
      style={{ margin: 0 }}
    >
      <div className="gh-pile__stack">
        {count === 0 && <div className="gh-pile__empty" />}
        {Array.from({ length: layers }, (_, i) => {
          const offset = (layers - 1 - i) * 3;
          const isTop = i === layers - 1;
          return (
            <div
              // biome-ignore lint/suspicious/noArrayIndexKey: capas fijas.
              key={i}
              className="gh-pile__layer"
              style={{ transform: `translate(${offset}px, ${offset}px)` }}
            >
              {isTop && top !== undefined && !faceDown ? top : <PlayingCard faceDown />}
            </div>
          );
        })}
      </div>
      <figcaption className="gh-pile__count">{label ? `${label} · ${count}` : count}</figcaption>
    </figure>
  );
}

/** Un mazo: un montón boca abajo. */
export function Deck(props: Omit<PileProps, "faceDown" | "top">) {
  return <Pile {...props} faceDown />;
}
