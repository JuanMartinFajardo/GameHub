// SPDX-License-Identifier: Apache-2.0
/** Cartas de baraja dibujadas en SVG (cara y dorso), con los palos y valores más comunes. */

import { useMessages } from "@gamehub/i18n";
import { useId } from "react";
import { cx } from "./basics";
import { messages } from "./messages";

/** Un palo: el símbolo que se dibuja, su color y su nombre para lectores de pantalla. */
export interface CardSuit {
  symbol: string;
  color: string;
  name: string;
}

const RED = "var(--gh-card-red)";
const BLACK = "var(--gh-card-black)";

const SUITS: Record<string, CardSuit> = {
  clubs: { symbol: "♣", color: BLACK, name: "tréboles" },
  diamonds: { symbol: "♦", color: RED, name: "diamantes" },
  hearts: { symbol: "♥", color: RED, name: "corazones" },
  spades: { symbol: "♠", color: BLACK, name: "picas" },
  oros: { symbol: "O", color: "#b8860b", name: "oros" },
  copas: { symbol: "C", color: RED, name: "copas" },
  espadas: { symbol: "E", color: "#1e5aa8", name: "espadas" },
  bastos: { symbol: "B", color: "#2e7d32", name: "bastos" },
};

/** El palo de un nombre de la IR (`Hearts`, `Oros`…), o null si no es un palo conocido. */
export function standardSuit(name: string): CardSuit | null {
  const key = name.toLowerCase().replace(/s?$/, "");
  return SUITS[name.toLowerCase()] ?? SUITS[`${key}s`] ?? null;
}

const RANKS: Record<string, string> = {
  ace: "A",
  as: "A",
  one: "1",
  two: "2",
  three: "3",
  four: "4",
  five: "5",
  six: "6",
  seven: "7",
  eight: "8",
  nine: "9",
  ten: "10",
  jack: "J",
  knave: "J",
  queen: "Q",
  king: "K",
  joker: "★",
  sota: "S",
  caballo: "C",
  rey: "R",
};

/** El índice de un valor de la IR: `Ace` → «A», `Ten` → «10», `7` → «7», `J` → «J». */
export function standardRank(name: string | number): string {
  if (typeof name === "number") return String(name);
  return RANKS[name.toLowerCase()] ?? (name.length <= 3 ? name : name.slice(0, 2));
}

export interface PlayingCardProps {
  rank?: string;
  suit?: CardSuit | null;
  faceDown?: boolean;
  selected?: boolean;
  target?: boolean;
  disabled?: boolean;
  size?: "sm" | "md" | "lg";
  /** Nombre para lectores de pantalla (por defecto, «A de corazones»). */
  label?: string;
  onClick?: () => void;
  className?: string;
}

export function PlayingCard(props: PlayingCardProps) {
  const t = useMessages(messages);
  const pattern = useId();
  const { rank = "", suit = null, faceDown = false } = props;
  const label =
    props.label ??
    (faceDown ? t("faceDown") : suit ? t("cardOf", { rank, suit: suit.name }) : rank);
  const color = suit?.color ?? BLACK;
  const big = suit?.symbol ?? rank;
  const art = faceDown ? (
    <svg viewBox="0 0 100 140" aria-hidden="true">
      <defs>
        <pattern id={pattern} width="12" height="12" patternUnits="userSpaceOnUse">
          <path d="M0 12 L12 0" className="gh-card__back-pattern" />
        </pattern>
      </defs>
      <rect x="1" y="1" width="98" height="138" rx="9" className="gh-card__back" />
      <rect x="8" y="8" width="84" height="124" rx="6" fill={`url(#${pattern})`} />
    </svg>
  ) : (
    <svg viewBox="0 0 100 140" aria-hidden="true">
      <rect x="1" y="1" width="98" height="138" rx="9" className="gh-card__face" />
      <g fill={color} className="gh-card__index">
        <text x="9" y="26" fontSize={rank.length > 1 ? 20 : 24}>
          {rank}
        </text>
        {suit && (
          <text x="10" y="46" fontSize="18">
            {suit.symbol}
          </text>
        )}
        <g transform="rotate(180 50 70)">
          <text x="9" y="26" fontSize={rank.length > 1 ? 20 : 24}>
            {rank}
          </text>
          {suit && (
            <text x="10" y="46" fontSize="18">
              {suit.symbol}
            </text>
          )}
        </g>
        <text
          x="50"
          y="72"
          fontSize={big.length > 2 ? 30 : 46}
          textAnchor="middle"
          dominantBaseline="middle"
        >
          {big}
        </text>
      </g>
    </svg>
  );
  const className = cx(
    "gh-card",
    props.size && props.size !== "md" && `gh-card--${props.size}`,
    props.selected && "gh-card--selected",
    props.target && "gh-card--target",
    props.className,
  );
  if (props.onClick === undefined) {
    return (
      <span className={className}>
        {art}
        <span className="gh-visually-hidden">{label}</span>
      </span>
    );
  }
  return (
    <button
      type="button"
      className={className}
      aria-label={label}
      aria-pressed={props.selected}
      disabled={props.disabled}
      onClick={props.onClick}
    >
      {art}
    </button>
  );
}
