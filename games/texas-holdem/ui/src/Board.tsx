// SPDX-License-Identifier: Apache-2.0
/**
 * Texas Hold'em: la mesa de tapete con los jugadores alrededor (tú, abajo), sus fichas y lo que
 * han apostado en la ronda, el botón, las cartas comunes y el bote. Cuando te toca: retirarte,
 * pasar o igualar, y apostar o subir con una barra y atajos (mínimo, medio bote, bote, todo).
 */

import type { LoggedEvent } from "@gamehub/client";
import { defineMessages, useMessages } from "@gamehub/i18n";
import type { GameUiProps } from "@gamehub/shell";
import { Button, PlayingCard, standardRank, standardSuit } from "@gamehub/ui-kit";
import { type CSSProperties, useEffect, useMemo, useState } from "react";
import type { Action, Card, State, Zone } from "./game";

const messages = defineMessages(
  {
    yourTurn: "Te toca",
    turnOf: "Le toca a {name}",
    sending: "Enviando…",
    pot: "Bote: {n}",
    hand: "Mano {n}",
    fold: "Retirarse",
    check: "Pasar",
    call: "Igualar {n}",
    callAllIn: "All-in {n}",
    bet: "Apostar {n}",
    raise: "Subir a {n}",
    min: "Mínimo",
    half: "½ bote",
    full: "Bote",
    allIn: "Todo",
    amount: "Cantidad",
    folded: "Se retira",
    allInBadge: "All-in",
    won: "+{n}",
    dealer: "Botón",
    gameOver: "Fin de la partida",
    streets: "Antes del flop|Flop|Turn|River|Enfrentamiento",
    lastShowdown: "Último enfrentamiento (mano {n})",
  },
  {
    yourTurn: "Your turn",
    turnOf: "{name} to act",
    sending: "Sending…",
    pot: "Pot: {n}",
    hand: "Hand {n}",
    fold: "Fold",
    check: "Check",
    call: "Call {n}",
    callAllIn: "All-in {n}",
    bet: "Bet {n}",
    raise: "Raise to {n}",
    min: "Min",
    half: "½ pot",
    full: "Pot",
    allIn: "All in",
    amount: "Amount",
    folded: "Folded",
    allInBadge: "All-in",
    won: "+{n}",
    dealer: "Dealer",
    gameOver: "Game over",
    streets: "Pre-flop|Flop|Turn|River|Showdown",
    lastShowdown: "Last showdown (hand {n})",
  },
);

function isCard(x: Card | { $hidden: true }): x is Card {
  return !("$hidden" in x);
}

function cards(zone: Zone<Card> | undefined): { shown: Card[]; hidden: number } {
  const items = zone?.items ?? [];
  const shown = items.filter(isCard);
  return { shown, hidden: Math.max(0, (zone?.size ?? items.length) - shown.length) };
}

function CardFace({ card, size = "md" }: { card: Card; size?: "sm" | "md" | "lg" }) {
  return <PlayingCard rank={standardRank(card.rank)} suit={standardSuit(card.suit)} size={size} />;
}

export interface Showdown {
  hand: number;
  shown: { seat: number; cards: Card[] }[];
}

/** El último enfrentamiento (qué enseñó cada uno), a partir del registro: la mano siguiente
 * empieza enseguida y el estado ya no lo tiene. */
export function lastShowdown(log: LoggedEvent[]): Showdown | null {
  let hand = 0;
  let found: Showdown | null = null;
  for (const { event } of log) {
    if (event.type === "node" && event.node === "Deal") hand += 1;
    if (event.type === "reveal" && Array.isArray(event.value)) {
      const pairs = event.value as [number, Card[]][];
      found = { hand, shown: pairs.map(([seat, cards]) => ({ seat, cards })) };
    }
  }
  return found;
}

/** Las cantidades a las que se puede apostar o subir (de las acciones legales). */
export function betting(actions: Action[] | null): {
  fold: boolean;
  check: boolean;
  call: boolean;
  kind: "bet" | "raise" | null;
  amounts: number[];
} {
  const list = actions ?? [];
  const bets = list.flatMap((a) => (a.name === "bet" ? [a.args.amount] : []));
  const raises = list.flatMap((a) => (a.name === "raise" ? [a.args.to] : []));
  return {
    fold: list.some((a) => a.name === "fold"),
    check: list.some((a) => a.name === "check"),
    call: list.some((a) => a.name === "call"),
    kind: bets.length > 0 ? "bet" : raises.length > 0 ? "raise" : null,
    amounts: (bets.length > 0 ? bets : raises).sort((a, b) => a - b),
  };
}

/** La cantidad legal más cercana a `want`. */
export function nearest(amounts: number[], want: number): number | undefined {
  let best: number | undefined;
  for (const a of amounts)
    if (best === undefined || Math.abs(a - want) < Math.abs(best - want)) best = a;
  return best;
}

export function Board(props: GameUiProps<State, Action>) {
  const t = useMessages(messages);
  const { view, actions, act, seat, players, busy, legal, queryActions } = props;
  const state = view.state;
  const n = state.chips.length;
  const name = (s: number) => players.find((p) => p.seat === s)?.name ?? `#${s + 1}`;
  const pot = state.put.reduce((a, b) => a + b, 0);
  const current = Math.max(...state.bet);
  const mine = (actions !== null || legal?.kind === "progressive") && !busy && seat !== null;

  // Con muchas cantidades posibles, el servidor no las enumera: se le preguntan.
  const [queried, setQueried] = useState<Action[] | null>(null);
  useEffect(() => {
    setQueried(null);
    if (legal?.kind !== "progressive") return;
    let alive = true;
    const names = legal.names as Action["name"][];
    Promise.all(
      names.map(async (nm) => {
        if (nm !== "bet" && nm !== "raise") return [{ name: nm, args: {} } as Action];
        const values = (await queryActions(nm, {})) as number[];
        return values.map((v) =>
          nm === "bet"
            ? ({ name: "bet", args: { amount: v } } as Action)
            : ({ name: "raise", args: { to: v } } as Action),
        );
      }),
    ).then((lists) => alive && setQueried(lists.flat()));
    return () => {
      alive = false;
    };
  }, [legal, queryActions]);

  const options = useMemo(() => betting(actions ?? queried), [actions, queried]);
  const showdown = useMemo(() => lastShowdown(props.log), [props.log]);
  const [amount, setAmount] = useState<number | null>(null);
  // biome-ignore lint/correctness/useExhaustiveDependencies: unas acciones nuevas = un turno nuevo.
  useEffect(() => setAmount(null), [actions, queried]);
  const low = options.amounts[0];
  const high = options.amounts.at(-1);
  const chosen = amount ?? low;
  const me = seat ?? 0;
  const toCall = Math.min(current - (state.bet[me] ?? 0), state.chips[me] ?? 0);

  const streets = t("streets").split("|");
  let status: string;
  if (view.status === "terminal") status = t("gameOver");
  else if (busy) status = t("sending");
  else if (mine) status = t("yourTurn");
  else status = t("turnOf", { name: name(state.turn) });

  const shortcut = (want: number) => {
    const v = nearest(options.amounts, want);
    if (v !== undefined) setAmount(v);
  };
  const board = cards(state.board);
  const order = Array.from({ length: n }, (_, i) => (me + i) % n);

  return (
    <div className="holdem">
      <p className={`holdem-status${mine ? " holdem-status--mine" : ""}`} aria-live="polite">
        {status} · {t("hand", { n: state.hand_no })} · {streets[Math.min(state.street, 4)]}
      </p>
      <div className="holdem-table">
        <div className="holdem-center">
          <div className="holdem-board">
            {board.shown.map((c) => (
              <CardFace key={`${c.rank}${c.suit}`} card={c} />
            ))}
            {Array.from({ length: 5 - board.shown.length }, (_, i) => (
              // biome-ignore lint/suspicious/noArrayIndexKey: huecos vacíos de la mesa.
              <span key={i} className="holdem-slot" />
            ))}
          </div>
          <p className="holdem-pot">{t("pot", { n: pot })}</p>
        </div>
        {order.map((s, i) => {
          const angle = (i / n) * 2 * Math.PI;
          const style = {
            "--holdem-x": `${50 + 44 * Math.sin(angle)}%`,
            "--holdem-y": `${50 + 40 * Math.cos(angle)}%`,
          } as CSSProperties;
          const hole = cards(state.hole[s]);
          const out = state.folded[s] && (state.chips[s] ?? 0) === 0 && (state.put[s] ?? 0) === 0;
          const classes = [
            "holdem-seat",
            view.active.includes(s) ? "holdem-seat--active" : "",
            state.folded[s] ? "holdem-seat--folded" : "",
            s === seat ? "holdem-seat--me" : "",
          ].filter(Boolean);
          return (
            <div key={s} className={classes.join(" ")} style={style}>
              <div className="holdem-hole">
                {hole.shown.map((c) => (
                  <CardFace key={`${c.rank}${c.suit}`} card={c} size="sm" />
                ))}
                {!out &&
                  Array.from({ length: hole.hidden }, (_, k) => (
                    // biome-ignore lint/suspicious/noArrayIndexKey: dorsos iguales.
                    <PlayingCard key={k} faceDown size="sm" />
                  ))}
              </div>
              <div className="holdem-plate">
                <strong>{name(s)}</strong>
                {s === state.button && (
                  <span className="holdem-dealer" title={t("dealer")}>
                    D
                  </span>
                )}
                <span className="holdem-chips">{state.chips[s]}</span>
              </div>
              {(state.bet[s] ?? 0) > 0 && <span className="holdem-bet">{state.bet[s]}</span>}
              {state.folded[s] && !out && <span className="holdem-tag">{t("folded")}</span>}
              {!state.folded[s] && state.chips[s] === 0 && view.status !== "terminal" && (
                <span className="holdem-tag holdem-tag--allin">{t("allInBadge")}</span>
              )}
              {(state.won[s] ?? 0) > 0 && (
                <span className="holdem-won">{t("won", { n: state.won[s] ?? 0 })}</span>
              )}
            </div>
          );
        })}
      </div>
      {showdown && view.status !== "terminal" && state.street === 0 && (
        <section className="holdem-showdown">
          <h3>{t("lastShowdown", { n: Math.max(1, showdown.hand) })}</h3>
          <ul>
            {showdown.shown.map(({ seat: s, cards: shown }) => (
              <li key={s}>
                <strong>{name(s)}</strong>
                {shown.map((c) => (
                  <CardFace key={`${c.rank}${c.suit}`} card={c} size="sm" />
                ))}
              </li>
            ))}
          </ul>
        </section>
      )}
      {mine && (
        <div className="holdem-actions">
          {options.fold && (
            <Button variant="danger" onClick={() => act({ name: "fold", args: {} })}>
              {t("fold")}
            </Button>
          )}
          {options.check && (
            <Button onClick={() => act({ name: "check", args: {} })}>{t("check")}</Button>
          )}
          {options.call && (
            <Button onClick={() => act({ name: "call", args: {} })}>
              {toCall >= (state.chips[me] ?? 0)
                ? t("callAllIn", { n: toCall })
                : t("call", { n: toCall })}
            </Button>
          )}
          {options.kind && chosen !== undefined && low !== undefined && high !== undefined && (
            <div className="holdem-raise">
              <input
                type="range"
                aria-label={t("amount")}
                min={low}
                max={high}
                value={chosen}
                onChange={(e) => shortcut(Number(e.target.value))}
              />
              <div className="holdem-shortcuts">
                <Button size="sm" onClick={() => shortcut(low)}>
                  {t("min")}
                </Button>
                <Button size="sm" onClick={() => shortcut(current + Math.round(pot / 2))}>
                  {t("half")}
                </Button>
                <Button size="sm" onClick={() => shortcut(current + pot)}>
                  {t("full")}
                </Button>
                <Button size="sm" onClick={() => shortcut(high)}>
                  {t("allIn")}
                </Button>
              </div>
              <Button
                variant="primary"
                onClick={() =>
                  act(
                    options.kind === "bet"
                      ? { name: "bet", args: { amount: chosen } }
                      : { name: "raise", args: { to: chosen } },
                  )
                }
              >
                {t(options.kind, { n: chosen })}
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
