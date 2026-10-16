// SPDX-License-Identifier: Apache-2.0
/**
 * Wizard: la carta de triunfo, la baza en juego (y la última, que se ve hasta que empieza la
 * siguiente), los jugadores con su apuesta, sus bazas y sus puntos, y tu mano. Para apostar, un
 * botón por cada número de bazas; para jugar, se pulsa una carta (las que no se pueden jugar
 * salen apagadas).
 */

import type { LoggedEvent } from "@gamehub/client";
import { defineMessages, useMessages } from "@gamehub/i18n";
import type { GameUiProps } from "@gamehub/shell";
import { Button, PlayingCard, standardRank, standardSuit } from "@gamehub/ui-kit";
import { useMemo } from "react";
import type { Action, State, Suit, WizardCard, Zone } from "./game";

const messages = defineMessages(
  {
    yourBid: "Te toca apostar: ¿cuántas bazas vas a ganar?",
    yourCard: "Te toca jugar una carta",
    chooseTrump: "Ha salido un mago: elige el triunfo",
    turnOf: "Le toca a {name}",
    sending: "Enviando…",
    round: "Ronda {n} de {total}",
    trump: "Triunfo",
    noTrump: "Sin triunfo",
    trick: "Baza",
    lastTrick: "Última baza (se la lleva {name})",
    bid: "Apuesta {n}",
    noBid: "Sin apuesta",
    tricks: "{n} bazas",
    points: "{n} puntos",
    dealer: "Reparte",
    wizard: "Mago",
    jester: "Bufón",
    winner: "Gana {name} con {n} puntos",
    Clubs: "Tréboles",
    Diamonds: "Diamantes",
    Hearts: "Corazones",
    Spades: "Picas",
  },
  {
    yourBid: "Your bid: how many tricks will you take?",
    yourCard: "Your turn: play a card",
    chooseTrump: "A wizard came up: choose the trump suit",
    turnOf: "{name} to play",
    sending: "Sending…",
    round: "Round {n} of {total}",
    trump: "Trump",
    noTrump: "No trump",
    trick: "Trick",
    lastTrick: "Last trick (taken by {name})",
    bid: "Bid {n}",
    noBid: "No bid",
    tricks: "{n} tricks",
    points: "{n} points",
    dealer: "Dealer",
    wizard: "Wizard",
    jester: "Jester",
    winner: "{name} wins with {n} points",
    Clubs: "Clubs",
    Diamonds: "Diamonds",
    Hearts: "Hearts",
    Spades: "Spades",
  },
);

const SUITS: Suit[] = ["Clubs", "Diamonds", "Hearts", "Spades"];

function visible(zone: Zone<WizardCard> | undefined): WizardCard[] {
  return (zone?.items ?? []).filter((x): x is WizardCard => !("$hidden" in x));
}

const key = (c: WizardCard) => `${c.rank}-${c.suit}`;

export interface Play {
  seat: number;
  card: WizardCard;
}

/** Las cartas de la última baza completa, a partir del registro (la baza en juego se vacía en
 * cuanto se completa). */
export function lastTrick(log: LoggedEvent[], players: number): Play[] {
  const plays: Play[] = [];
  for (const { event } of log) {
    if (event.type === "node" && event.node === "Deal") plays.length = 0;
    if (event.type === "action" && event.name === "play") {
      plays.push({ seat: event.seat as number, card: (event.args as { c: WizardCard }).c });
    }
  }
  const complete = Math.floor(plays.length / players) * players;
  return complete === 0 ? [] : plays.slice(complete - players, complete);
}

function Card(props: {
  card: WizardCard;
  onClick?: () => void;
  disabled?: boolean;
  size?: "sm" | "md";
}) {
  const t = useMessages(messages);
  const { card } = props;
  const special = card.rank === "Wizard" ? "Z" : card.rank === "Jester" ? "N" : null;
  const label =
    card.rank === "Wizard" ? t("wizard") : card.rank === "Jester" ? t("jester") : undefined;
  return (
    <PlayingCard
      rank={special ?? standardRank(card.rank)}
      suit={special ? null : standardSuit(card.suit)}
      label={label}
      size={props.size}
      onClick={props.onClick}
      disabled={props.disabled}
      className={special ? `wizard-card--${card.rank.toLowerCase()}` : undefined}
    />
  );
}

export function Board(props: GameUiProps<State, Action>) {
  const t = useMessages(messages);
  const { view, actions, act, seat, players, busy, log } = props;
  const state = view.state;
  const n = state.score.length;
  const total = Math.floor(60 / n);
  const name = (s: number) => players.find((p) => p.seat === s)?.name ?? `#${s + 1}`;
  const mine = actions !== null && !busy;
  const bids = (mine ? actions : []).flatMap((a) => (a.name === "bid" ? [a.args.n] : []));
  const choose = mine && actions.some((a) => a.name === "choose");
  const playable = new Set(
    (mine ? actions : []).flatMap((a) => (a.name === "play" ? [key(a.args.c)] : [])),
  );
  const hand = seat === null ? [] : visible(state.hand[seat]);
  const trick = visible(state.trick);
  const last = useMemo(() => lastTrick(log, n), [log, n]);
  const trumpCard = visible(state.trump_card)[0];

  let status: string;
  if (view.status === "terminal") {
    const best = Math.max(...state.score);
    const winner = state.score.indexOf(best);
    status = t("winner", { name: name(winner), n: best });
  } else if (busy) status = t("sending");
  else if (choose) status = t("chooseTrump");
  else if (bids.length > 0) status = t("yourBid");
  else if (mine) status = t("yourCard");
  else status = t("turnOf", { name: name(state.turn) });

  const order = Array.from({ length: n }, (_, i) => ((seat ?? 0) + i) % n);
  return (
    <div className="wizard">
      <p className={`wizard-status${mine ? " wizard-status--mine" : ""}`} aria-live="polite">
        {status}
      </p>
      <p className="wizard-round">{t("round", { n: state.round, total })}</p>
      <div className="wizard-table">
        <section className="wizard-trump" aria-label={t("trump")}>
          <h3>{t("trump")}</h3>
          {trumpCard && <Card card={trumpCard} size="sm" />}
          <strong>{state.trump ? t(state.trump) : t("noTrump")}</strong>
        </section>
        <section className="wizard-trick" aria-label={t("trick")}>
          <h3>
            {trick.length > 0 || last.length === 0
              ? t("trick")
              : t("lastTrick", { name: name(state.last_winner ?? 0) })}
          </h3>
          <div className="wizard-trick__cards">
            {(trick.length > 0
              ? trick.map((card, i) => ({ seat: state.trick_by[i] ?? 0, card }))
              : last
            ).map((p) => (
              <figure key={key(p.card)} className="wizard-play">
                <Card card={p.card} size="sm" />
                <figcaption>{name(p.seat)}</figcaption>
              </figure>
            ))}
          </div>
        </section>
      </div>
      <ul className="wizard-players">
        {order.map((s) => {
          const b = state.bid[s];
          return (
            <li
              key={s}
              className={`wizard-player${view.active.includes(s) ? " wizard-player--active" : ""}${s === seat ? " wizard-player--me" : ""}`}
            >
              <strong>{name(s)}</strong>
              {s === state.dealer && <span className="wizard-dealer">{t("dealer")}</span>}
              <span>{b === null || b === undefined ? t("noBid") : t("bid", { n: b })}</span>
              <span>{t("tricks", { n: state.won[s] ?? 0 })}</span>
              <span className="wizard-score">{t("points", { n: state.score[s] ?? 0 })}</span>
            </li>
          );
        })}
      </ul>
      {choose && (
        <div className="wizard-choices">
          {SUITS.map((s) => (
            <Button key={s} onClick={() => act({ name: "choose", args: { s } })}>
              {standardSuit(s)?.symbol} {t(s)}
            </Button>
          ))}
        </div>
      )}
      {bids.length > 0 && (
        <div className="wizard-choices">
          {bids.map((b) => (
            <Button key={b} onClick={() => act({ name: "bid", args: { n: b } })}>
              {b}
            </Button>
          ))}
        </div>
      )}
      {hand.length > 0 && (
        <div className="wizard-hand">
          {hand.map((card) => {
            const can = playable.has(key(card));
            return (
              <Card
                key={key(card)}
                card={card}
                disabled={mine && !can}
                onClick={mine ? () => can && act({ name: "play", args: { c: card } }) : undefined}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}
