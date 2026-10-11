// SPDX-License-Identifier: Apache-2.0
/**
 * Dudo: la apuesta en la mesa y lo apostado en la ronda, los cubiletes (el tuyo a la vista; los
 * demás, con tantos dados tapados como les quedan), lo que pasó la última vez que alguien dudó y
 * un selector de apuesta: cuántos dados y qué cara.
 */

import type { LoggedEvent } from "@gamehub/client";
import { defineMessages, useMessages } from "@gamehub/i18n";
import type { GameUiProps } from "@gamehub/shell";
import { Button, Die } from "@gamehub/ui-kit";
import { useEffect, useMemo, useState } from "react";
import type { Action, BidAction, State } from "./game";

const messages = defineMessages(
  {
    yourTurn: "Te toca: sube la apuesta o duda",
    turnOf: "Turno de {name}",
    youWon: "¡Has ganado!",
    winner: "Gana {name}",
    noBid: "Aún no hay apuesta: abre la ronda.",
    bidBy: "apuesta de {name}",
    atLeast: "al menos",
    round: "En esta ronda",
    you: "tú",
    dice: "{n} dados",
    out: "fuera",
    howMany: "Cuántos",
    face: "Cara",
    bid: "Apostar {q} × {f}",
    doubt: "¡Dudo!",
    less: "Uno menos",
    more: "Uno más",
    lastDoubt: "La última vez que se dudó",
    counted: "Había {n} con la cara {f} (los ases cuentan): la apuesta era de {q}.",
    loses: "Pierde un dado {name}.",
    sending: "Enviando…",
  },
  {
    yourTurn: "Your turn: raise the bid or call it",
    turnOf: "{name} to play",
    youWon: "You won!",
    winner: "{name} wins",
    noBid: "No bid yet: open the round.",
    bidBy: "{name}'s bid",
    atLeast: "at least",
    round: "This round",
    you: "you",
    dice: "{n} dice",
    out: "out",
    howMany: "How many",
    face: "Face",
    bid: "Bid {q} × {f}",
    doubt: "Doubt!",
    less: "One less",
    more: "One more",
    lastDoubt: "Last time someone called it",
    counted: "There were {n} showing {f} (aces are wild): the bid was {q}.",
    loses: "{name} loses a die.",
    sending: "Sending…",
  },
);

interface Bid {
  seat: number;
  q: number;
  f: number;
}

interface Doubt {
  doubter: number;
  bid: Bid;
  cups: number[][];
  count: number;
  loser: number;
}

/** Las apuestas de la ronda en curso y la última vez que se dudó, a partir del registro. */
export function readLog(log: LoggedEvent[]): { round: Bid[]; doubt: Doubt | null } {
  let round: Bid[] = [];
  let doubt: Doubt | null = null;
  let reveal: number[][] | null = null;
  for (const { event } of log) {
    if (event.type === "node" && event.node === "Roll") {
      round = [];
    } else if (event.type === "reveal" && Array.isArray(event.value)) {
      reveal = event.value as number[][];
    } else if (event.type === "action" && event.name === "bid") {
      const args = event.args as { q: number; f: number };
      round.push({ seat: event.seat as number, q: args.q, f: args.f });
    } else if (event.type === "action" && event.name === "dudo" && reveal !== null) {
      const bid = round.at(-1);
      if (bid) {
        const count = reveal.flat().filter((d) => d === bid.f || d === 1).length;
        const doubter = event.seat as number;
        doubt = { doubter, bid, cups: reveal, count, loser: count >= bid.q ? doubter : bid.seat };
      }
      reveal = null;
    }
  }
  return { round, doubt };
}

export function Board(props: GameUiProps<State, Action>) {
  const t = useMessages(messages);
  const { view, actions, act, seat, players, busy, log } = props;
  const state = view.state;
  const name = (s: number) => players.find((p) => p.seat === s)?.name ?? `#${s + 1}`;
  const bids = useMemo(
    () => (actions ?? []).filter((a): a is BidAction => a.name === "bid"),
    [actions],
  );
  const canDoubt = (actions ?? []).some((a) => a.name === "dudo");
  const quantities = [...new Set(bids.map((b) => b.args.q))].sort((a, b) => a - b);
  const [q, setQ] = useState<number | null>(null);
  const [f, setF] = useState<number | null>(null);
  // Cada turno empieza por la apuesta más baja posible.
  // biome-ignore lint/correctness/useExhaustiveDependencies: unas acciones nuevas = un turno nuevo.
  useEffect(() => {
    setQ(null);
    setF(null);
  }, [actions]);
  const chosenQ = q ?? quantities[0] ?? null;
  const faces = bids.filter((b) => b.args.q === chosenQ).map((b) => b.args.f);
  const chosenF = f !== null && faces.includes(f) ? f : (faces[0] ?? null);
  const { round, doubt } = useMemo(() => readLog(log), [log]);
  const mine = actions !== null && !busy;
  const alive = state.dice_left.filter((n) => n > 0).length;

  let status: string;
  if (view.status === "terminal") {
    const winner = state.dice_left.findIndex((n) => n > 0);
    status = winner === seat ? t("youWon") : t("winner", { name: name(winner) });
  } else if (busy) status = t("sending");
  else if (mine) status = t("yourTurn");
  else status = t("turnOf", { name: name(state.turn) });

  return (
    <div className="dudo">
      <p className={`dudo-status${mine ? " dudo-status--mine" : ""}`} aria-live="polite">
        {status}
      </p>
      <section className="dudo-table">
        {state.quantity === 0 ? (
          <p className="dudo-muted">{t("noBid")}</p>
        ) : (
          <div className="dudo-bid">
            <span className="dudo-muted">{t("atLeast")}</span>
            <strong className="dudo-bid__q">{state.quantity}</strong>
            <span className="dudo-bid__x">×</span>
            <Die value={state.face} size="lg" />
            <span className="dudo-muted">{t("bidBy", { name: name(state.bidder) })}</span>
          </div>
        )}
        {round.length > 0 && (
          <ol className="dudo-round" aria-label={t("round")}>
            {round.map((b, i) => (
              // biome-ignore lint/suspicious/noArrayIndexKey: apuestas en orden.
              <li key={i}>
                {name(b.seat)}: {b.q} × <Die value={b.f} size="sm" />
              </li>
            ))}
          </ol>
        )}
      </section>
      <ul className="dudo-cups">
        {players.map((p) => {
          const left = state.dice_left[p.seat] ?? 0;
          const cup = state.cup[p.seat];
          const values = Array.isArray(cup) ? cup : Array.from({ length: left }, () => null);
          return (
            <li
              key={p.seat}
              className={`dudo-cup${view.active.includes(p.seat) ? " dudo-cup--active" : ""}${left === 0 ? " dudo-cup--out" : ""}`}
            >
              <header>
                <strong>{p.name}</strong>
                {p.seat === seat && <span className="dudo-muted">({t("you")})</span>}
                <span className="dudo-spacer" />
                <span className="dudo-muted">{left > 0 ? t("dice", { n: left }) : t("out")}</span>
              </header>
              <div className="dudo-dice">
                {values.map((v, i) => (
                  // biome-ignore lint/suspicious/noArrayIndexKey: la posición es la identidad del dado.
                  <Die key={i} value={v} />
                ))}
              </div>
            </li>
          );
        })}
      </ul>
      {doubt && alive > 1 && (
        <section className="dudo-doubt">
          <h4>{t("lastDoubt")}</h4>
          <p>
            {t("counted", { n: doubt.count, f: doubt.bid.f, q: doubt.bid.q })}{" "}
            <strong>{t("loses", { name: name(doubt.loser) })}</strong>
          </p>
          <div className="dudo-reveal">
            {doubt.cups.map((cup, s) => (
              // biome-ignore lint/suspicious/noArrayIndexKey: un cubilete por asiento.
              <div key={s}>
                <span className="dudo-muted">{name(s)}</span>
                {cup.map((d, i) => (
                  <Die
                    // biome-ignore lint/suspicious/noArrayIndexKey: la posición es la identidad del dado.
                    key={i}
                    value={d}
                    size="sm"
                    highlight={d === doubt.bid.f || d === 1}
                  />
                ))}
              </div>
            ))}
          </div>
        </section>
      )}
      {mine && (
        <section className="dudo-actions">
          {chosenQ !== null && chosenF !== null && (
            <div className="dudo-picker">
              <span className="dudo-muted">{t("howMany")}</span>
              <Button
                size="sm"
                aria-label={t("less")}
                disabled={quantities.indexOf(chosenQ) <= 0}
                onClick={() => setQ(quantities[quantities.indexOf(chosenQ) - 1] ?? chosenQ)}
              >
                −
              </Button>
              <strong className="dudo-picker__q">{chosenQ}</strong>
              <Button
                size="sm"
                aria-label={t("more")}
                disabled={quantities.indexOf(chosenQ) >= quantities.length - 1}
                onClick={() => setQ(quantities[quantities.indexOf(chosenQ) + 1] ?? chosenQ)}
              >
                +
              </Button>
              <span className="dudo-muted">{t("face")}</span>
              {[2, 3, 4, 5, 6].map((face) => (
                <Die
                  key={face}
                  value={face}
                  highlight={face === chosenF}
                  disabled={!faces.includes(face)}
                  onClick={() => setF(face)}
                  label={`${t("face")} ${face}`}
                />
              ))}
              <Button
                variant="primary"
                onClick={() => act({ name: "bid", args: { q: chosenQ, f: chosenF } })}
              >
                {t("bid", { q: chosenQ, f: chosenF })}
              </Button>
            </div>
          )}
          {canDoubt && (
            <Button variant="danger" size="lg" onClick={() => act({ name: "dudo", args: {} })}>
              {t("doubt")}
            </Button>
          )}
        </section>
      )}
    </div>
  );
}
