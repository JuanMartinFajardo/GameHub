// SPDX-License-Identifier: Apache-2.0
/** Jugadores, marcador, contadores, fichas de apuesta, reloj y barra de acciones. */

import { useMessages } from "@gamehub/i18n";
import { type CSSProperties, type ReactNode, useEffect, useState } from "react";
import { cx } from "./basics";
import { messages } from "./messages";

const PALETTE = 8;

/** El color de un asiento: el de la paleta del kit, salvo que el juego dé los suyos. */
export function seatColor(seat: number, colors?: readonly string[]): string {
  return colors?.[seat] ?? `var(--gh-seat-${seat % PALETTE})`;
}

export interface PlayerBadgeProps {
  name: string;
  color?: string;
  active?: boolean;
  you?: boolean;
  bot?: boolean;
  away?: boolean;
  ready?: boolean;
  extra?: ReactNode;
}

export function PlayerBadge(props: PlayerBadgeProps) {
  const t = useMessages(messages);
  const style = props.color ? ({ "--gh-player-color": props.color } as CSSProperties) : undefined;
  const tags = [
    props.you && t("you"),
    props.bot && t("bot"),
    props.away && t("away"),
    props.ready && t("ready"),
  ].filter(Boolean);
  return (
    <span
      className={cx(
        "gh-player",
        props.active && "gh-player--active",
        props.away && "gh-player--away",
      )}
      style={style}
    >
      <span className="gh-player__dot" aria-hidden="true" />
      <span className="gh-player__name">{props.name}</span>
      {tags.length > 0 && <span className="gh-muted">({tags.join(", ")})</span>}
      {props.active && <span className="gh-visually-hidden">{t("turn")}</span>}
      {props.extra}
    </span>
  );
}

export interface ScoreRow {
  name: string;
  color?: string;
  values: ReactNode[];
  highlight?: boolean;
}

export function Scoreboard(props: { columns: string[]; rows: ScoreRow[]; caption?: string }) {
  return (
    <table className="gh-scoreboard">
      {props.caption && <caption className="gh-visually-hidden">{props.caption}</caption>}
      <thead>
        <tr>
          <th scope="col">{props.columns[0]}</th>
          {props.columns.slice(1).map((c) => (
            <th key={c} scope="col" className="gh-num">
              {c}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {props.rows.map((row, i) => (
          // biome-ignore lint/suspicious/noArrayIndexKey: filas en orden fijo.
          <tr key={i} className={row.highlight ? "gh-scoreboard--highlight" : undefined}>
            <th scope="row">
              <PlayerBadge name={row.name} color={row.color} />
            </th>
            {row.values.map((v, k) => (
              // biome-ignore lint/suspicious/noArrayIndexKey: columnas en orden fijo.
              <td key={k} className="gh-num">
                {v}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function Counter(props: { value: ReactNode; label?: ReactNode }) {
  return (
    <span className="gh-counter">
      <span className="gh-counter__value">{props.value}</span>
      {props.label !== undefined && <span className="gh-counter__label">{props.label}</span>}
    </span>
  );
}

export function Chips(props: { amount: ReactNode; label?: string }) {
  return (
    <span className="gh-chips">
      <span className="gh-chips__icon" aria-hidden="true" />
      {props.label !== undefined && <span className="gh-visually-hidden">{props.label}: </span>}
      {props.amount}
    </span>
  );
}

/** «m:ss» (o «h:mm:ss») de una cantidad de milisegundos. */
export function formatClock(ms: number): string {
  const total = Math.max(0, Math.ceil(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const ss = String(s).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${ss}` : `${m}:${ss}`;
}

export interface ClockProps {
  /** Milisegundos que quedaban al recibir el dato. */
  ms: number;
  /** Si corre, se descuenta en la pantalla desde que llegó el dato. */
  running?: boolean;
  /** Por debajo de esto se marca en rojo (por defecto, 10 s). */
  warnBelow?: number;
  label?: string;
}

export function Clock({ ms, running = false, warnBelow = 10_000, label }: ClockProps) {
  const t = useMessages(messages);
  const [since, setSince] = useState(() => Date.now());
  const [now, setNow] = useState(since);
  // biome-ignore lint/correctness/useExhaustiveDependencies: un `ms` nuevo reinicia la cuenta.
  useEffect(() => {
    const start = Date.now();
    setSince(start);
    setNow(start);
    if (!running) return;
    const timer = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(timer);
  }, [ms, running]);
  const left = running ? ms - (now - since) : ms;
  return (
    <span
      className={cx(
        "gh-clock",
        running && "gh-clock--running",
        left < warnBelow && "gh-clock--low",
      )}
      role="timer"
      aria-label={label ?? t("clock")}
    >
      {formatClock(left)}
    </span>
  );
}

export function ActionBar(props: {
  children: ReactNode;
  label?: ReactNode;
  sticky?: boolean;
  className?: string;
}) {
  return (
    <div
      className={cx("gh-actionbar", props.sticky && "gh-actionbar--sticky", props.className)}
      role="toolbar"
    >
      {props.label !== undefined && <span className="gh-actionbar__label">{props.label}</span>}
      {props.children}
    </div>
  );
}
