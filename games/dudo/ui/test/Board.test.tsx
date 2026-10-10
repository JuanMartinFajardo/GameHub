// SPDX-License-Identifier: Apache-2.0
import type { LoggedEvent } from "@gamehub/client";
import { LocaleProvider } from "@gamehub/i18n";
import type { GameUiProps } from "@gamehub/shell";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Board, readLog } from "../src/Board";
import type { Action, State } from "../src/game";

afterEach(() => cleanup());

const STATE: State = {
  cup: [[2, 1, 5], { $hidden: true }],
  dice_left: [3, 2],
  die: { $hidden: true },
  quantity: 2,
  face: 3,
  bidder: 1,
  turn: 0,
  loser: 0,
};

function props(extra: Partial<GameUiProps<State, Action>> = {}) {
  return {
    view: { node: "Bid", status: "decision", active: [0], state: STATE },
    seat: 0,
    players: [
      { seat: 0, name: "Ana" },
      { seat: 1, name: "Luis" },
    ],
    actions: null,
    act: vi.fn(),
    busy: false,
    log: [],
    params: { dice: 3 },
    ...extra,
  } as unknown as GameUiProps<State, Action>;
}

const ev = (seq: number, event: Record<string, unknown>) => ({ seq, event }) as LoggedEvent;

describe("Dudo", () => {
  it("lee la ronda y la última dudada del registro", () => {
    const log = [
      ev(0, { type: "node", node: "Roll" }),
      ev(1, { type: "action", seat: 0, name: "bid", args: { q: 2, f: 5 } }),
      ev(2, { type: "action", seat: 1, name: "bid", args: { q: 4, f: 5 } }),
      ev(3, {
        type: "reveal",
        value: [
          [5, 1, 2],
          [3, 3, 3],
        ],
      }),
      ev(3, { type: "action", seat: 0, name: "dudo", args: {} }),
      ev(3, { type: "node", node: "Roll" }),
      ev(4, { type: "action", seat: 0, name: "bid", args: { q: 1, f: 2 } }),
    ];
    const { round, doubt } = readLog(log);
    expect(round).toEqual([{ seat: 0, q: 1, f: 2 }]);
    // Dos dados cuentan (un 5 y un as) y la apuesta era de 4: pierde quien apostó.
    expect(doubt).toMatchObject({ doubter: 0, count: 2, loser: 1, bid: { seat: 1, q: 4, f: 5 } });
  });

  it("enseña los dados propios y tapa los ajenos", () => {
    render(
      <LocaleProvider initial="es">
        <Board {...props()} />
      </LocaleProvider>,
    );
    expect(screen.getAllByText("Dado oculto")).toHaveLength(2);
    expect(screen.getByText("Dado: 5")).toBeTruthy();
    expect(screen.getByText("Turno de Ana")).toBeTruthy();
  });

  it("apuesta con el selector y duda", () => {
    const actions: Action[] = [
      { name: "bid", args: { q: 2, f: 4 } },
      { name: "bid", args: { q: 2, f: 6 } },
      { name: "bid", args: { q: 3, f: 2 } },
      { name: "dudo", args: {} },
    ];
    const p = props({ actions });
    render(
      <LocaleProvider initial="es">
        <Board {...p} />
      </LocaleProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Cara 6" }));
    fireEvent.click(screen.getByRole("button", { name: "Apostar 2 × 6" }));
    expect(p.act).toHaveBeenCalledWith({ name: "bid", args: { q: 2, f: 6 } });
    fireEvent.click(screen.getByRole("button", { name: "Uno más" }));
    expect(screen.getByRole("button", { name: "Apostar 3 × 2" })).toBeTruthy();
    expect((screen.getByRole("button", { name: "Cara 4" }) as HTMLButtonElement).disabled).toBe(
      true,
    );
    fireEvent.click(screen.getByRole("button", { name: "¡Dudo!" }));
    expect(p.act).toHaveBeenCalledWith({ name: "dudo", args: {} });
  });
});
