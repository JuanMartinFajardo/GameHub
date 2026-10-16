// SPDX-License-Identifier: Apache-2.0
import { LocaleProvider } from "@gamehub/i18n";
import type { GameUiProps } from "@gamehub/shell";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Board, betting, nearest } from "../src/Board";
import type { Action, State } from "../src/game";

afterEach(() => cleanup());

const hidden = { $hidden: true as const };

function state(extra: Partial<State> = {}): State {
  return {
    deck: { size: 46, items: [] },
    hole: [
      {
        size: 2,
        items: [
          { suit: "Hearts", rank: "Ace" },
          { suit: "Spades", rank: "Ace" },
        ],
      },
      { size: 2, items: [hidden, hidden] },
      { size: 2, items: [hidden, hidden] },
    ],
    board: { size: 0, items: [] },
    chips: [200, 199, 198],
    bet: [0, 1, 2],
    put: [0, 1, 2],
    folded: [false, false, false],
    acted: [false, false, false],
    can_raise: [true, true, true],
    min_raise: 2,
    button: 0,
    big: 2,
    turn: 0,
    street: 0,
    hand_no: 1,
    shown: false,
    won: [0, 0, 0],
    ...extra,
  };
}

function props(s: State, extra: Partial<GameUiProps<State, Action>> = {}) {
  return {
    view: { node: "Betting", status: "decision", active: [s.turn], state: s },
    seat: 0,
    players: [
      { seat: 0, name: "Ana" },
      { seat: 1, name: "Luis" },
      { seat: 2, name: "Eva" },
    ],
    actions: null,
    legal: null,
    act: vi.fn(),
    queryActions: vi.fn(),
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

const raises = (from: number, to: number): Action[] =>
  Array.from({ length: to - from + 1 }, (_, i) => ({ name: "raise", args: { to: from + i } }));

describe("Texas Hold'em", () => {
  it("lee las opciones de apuesta", () => {
    const options = betting([
      { name: "fold", args: {} },
      { name: "call", args: {} },
      ...raises(4, 9),
    ]);
    expect(options).toMatchObject({ fold: true, call: true, check: false, kind: "raise" });
    expect(options.amounts).toEqual([4, 5, 6, 7, 8, 9]);
    expect(nearest(options.amounts, 100)).toBe(9);
  });

  it("igualar y subir", () => {
    const p = props(state(), {
      actions: [{ name: "fold", args: {} }, { name: "call", args: {} }, ...raises(4, 200)],
    });
    show(p);
    expect(screen.getByText("Igualar 2")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Todo" }));
    fireEvent.click(screen.getByRole("button", { name: "Subir a 200" }));
    expect(p.act).toHaveBeenCalledWith({ name: "raise", args: { to: 200 } });
    fireEvent.click(screen.getByRole("button", { name: "Igualar 2" }));
    expect(p.act).toHaveBeenCalledWith({ name: "call", args: {} });
  });

  it("enseña el bote, el botón y las cartas propias", () => {
    show(props(state()));
    expect(screen.getByText("Bote: 3")).toBeTruthy();
    expect(screen.getByTitle("Botón")).toBeTruthy();
    expect(screen.getByText("A de corazones")).toBeTruthy();
  });
});

describe("el último enfrentamiento", () => {
  it("sale del registro", async () => {
    const { lastShowdown } = await import("../src/Board");
    const ev = (event: Record<string, unknown>) => ({ event }) as never;
    const log = [
      ev({ type: "node", node: "Deal" }),
      ev({ type: "node", node: "Deal" }),
      ev({ type: "reveal", value: [[0, [{ suit: "Hearts", rank: "Ace" }]]] }),
      ev({ type: "node", node: "Deal" }),
    ];
    expect(lastShowdown(log)).toEqual({
      hand: 2,
      shown: [{ seat: 0, cards: [{ suit: "Hearts", rank: "Ace" }] }],
    });
  });
});
