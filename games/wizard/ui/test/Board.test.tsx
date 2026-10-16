// SPDX-License-Identifier: Apache-2.0
import type { LoggedEvent } from "@gamehub/client";
import { LocaleProvider } from "@gamehub/i18n";
import type { GameUiProps } from "@gamehub/shell";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Board, lastTrick } from "../src/Board";
import type { Action, State, WizardCard } from "../src/game";

afterEach(() => cleanup());

const card = (suit: string, rank: string) => ({ suit, rank }) as WizardCard;
const hidden = { $hidden: true as const };

function state(extra: Partial<State> = {}): State {
  return {
    deck: { size: 51, items: [] },
    hand: [
      { size: 3, items: [card("Hearts", "Ace"), card("Clubs", "Two"), card("Spades", "Wizard")] },
      { size: 3, items: [hidden, hidden, hidden] },
      { size: 3, items: [hidden, hidden, hidden] },
    ],
    trump_card: { size: 1, items: [card("Hearts", "Seven")] },
    trump: "Hearts",
    round: 3,
    dealer: 2,
    bid: [null, null, null],
    won: [0, 0, 0],
    score: [0, 20, -10],
    trick: { size: 0, items: [] },
    trick_by: [],
    last_winner: null,
    discard: { size: 0, items: [] },
    turn: 0,
    ...extra,
  };
}

function props(s: State, extra: Partial<GameUiProps<State, Action>> = {}) {
  return {
    view: { node: "Bidding", status: "decision", active: [s.turn], state: s },
    seat: 0,
    players: [
      { seat: 0, name: "Ana" },
      { seat: 1, name: "Luis" },
      { seat: 2, name: "Eva" },
    ],
    actions: null,
    act: vi.fn(),
    busy: false,
    log: [],
    params: {},
    ...extra,
  } as unknown as GameUiProps<State, Action>;
}

function show(p: GameUiProps<State, Action>) {
  render(
    <LocaleProvider initial="es">
      <Board {...p} />
    </LocaleProvider>,
  );
}

describe("Wizard", () => {
  it("apuesta con un botón por cada número de bazas", () => {
    const p = props(state(), {
      actions: [0, 1, 2, 3].map((n) => ({ name: "bid", args: { n } }) as Action),
    });
    show(p);
    expect(screen.getByText("Te toca apostar: ¿cuántas bazas vas a ganar?")).toBeTruthy();
    expect(screen.getByText("Ronda 3 de 20")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "2" }));
    expect(p.act).toHaveBeenCalledWith({ name: "bid", args: { n: 2 } });
  });

  it("solo se pueden pulsar las cartas jugables", () => {
    const play = (c: WizardCard) => ({ name: "play", args: { c } }) as Action;
    const p = props(state(), {
      view: { node: "Play", status: "decision", active: [0], state: state() },
      actions: [play(card("Hearts", "Ace")), play(card("Spades", "Wizard"))],
    } as unknown as Partial<GameUiProps<State, Action>>);
    show(p);
    const two = screen.getByRole("button", { name: "2 de tréboles" }) as HTMLButtonElement;
    expect(two.disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Mago" }));
    expect(p.act).toHaveBeenCalledWith(play(card("Spades", "Wizard")));
  });

  it("la última baza sale del registro", () => {
    const ev = (seat: number, c: WizardCard): LoggedEvent =>
      ({ event: { type: "action", seat, name: "play", args: { c } } }) as unknown as LoggedEvent;
    const log = [
      ev(1, card("Clubs", "Two")),
      ev(2, card("Clubs", "Ace")),
      ev(0, card("Clubs", "King")),
      ev(2, card("Hearts", "Two")),
    ];
    expect(lastTrick(log, 3).map((p) => p.seat)).toEqual([1, 2, 0]);
  });
});
