// SPDX-License-Identifier: Apache-2.0
import { LocaleProvider } from "@gamehub/i18n";
import type { GameUiProps } from "@gamehub/shell";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Board, winningLine } from "../src/Board";
import type { Action, State } from "../src/game";

afterEach(() => cleanup());

function props(state: State, extra: Partial<GameUiProps<State, Action>> = {}) {
  return {
    view: { node: "Move", status: "decision", active: [state.turn], state },
    seat: 0,
    players: [
      { seat: 0, name: "Ana" },
      { seat: 1, name: "Luis" },
    ],
    actions: null,
    legal: null,
    act: vi.fn(),
    queryActions: vi.fn(),
    busy: false,
    rejected: null,
    log: [],
    clocks: null,
    params: {},
    end: null,
    locale: "es",
    ...extra,
  } as unknown as GameUiProps<State, Action>;
}

const empty = () => [
  [null, null, null],
  [null, null, null],
  [null, null, null],
];

describe("tres en raya", () => {
  it("juega pulsando una casilla libre", () => {
    const p = props(
      { board: empty(), turn: 0 },
      { actions: [{ name: "place", args: { c: [1, 1] } }] },
    );
    render(
      <LocaleProvider initial="es">
        <Board {...p} />
      </LocaleProvider>,
    );
    expect(screen.getByText("Te toca: pon tu ✕")).toBeTruthy();
    const center = screen.getByRole("button", { name: "Casilla 2, 2: vacía" });
    fireEvent.click(center);
    expect(p.act).toHaveBeenCalledWith({ name: "place", args: { c: [1, 1] } });
    expect(
      (screen.getByRole("button", { name: "Casilla 1, 1: vacía" }) as HTMLButtonElement).disabled,
    ).toBe(true);
  });

  it("marca la línea ganadora", () => {
    const board = empty();
    for (const c of [0, 1, 2]) (board[1] as (string | null)[])[c] = "O";
    expect(winningLine(board as State["board"])).toEqual([
      [1, 0],
      [1, 1],
      [1, 2],
    ]);
    render(
      <LocaleProvider initial="es">
        <Board
          {...props(
            { board: board as State["board"], turn: 1 },
            {
              view: {
                node: "Win",
                status: "terminal",
                active: [],
                state: { board: board as State["board"], turn: 1 },
              },
            },
          )}
        />
      </LocaleProvider>,
    );
    expect(screen.getByText("Ha ganado Luis")).toBeTruthy();
    expect(document.querySelectorAll(".ttt-cell--win")).toHaveLength(3);
  });
});
