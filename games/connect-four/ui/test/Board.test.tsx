// SPDX-License-Identifier: Apache-2.0
import { LocaleProvider } from "@gamehub/i18n";
import type { GameUiProps } from "@gamehub/shell";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Board, landingRow, winningCells } from "../src/Board";
import type { Action, Disc, State } from "../src/game";

afterEach(() => cleanup());

function grid(rows: number, columns: number): (Disc | null)[][] {
  return Array.from({ length: rows }, () => Array.from({ length: columns }, () => null));
}

function props(state: State, extra: Partial<GameUiProps<State, Action>> = {}) {
  return {
    view: { node: "Move", status: "decision", active: [state.turn], state },
    seat: 0,
    players: [
      { seat: 0, name: "Ana" },
      { seat: 1, name: "Luis" },
    ],
    actions: null,
    act: vi.fn(),
    busy: false,
    params: { columns: 7, rows: 6, connect: 4 },
    ...extra,
  } as unknown as GameUiProps<State, Action>;
}

describe("Conecta 4", () => {
  it("las fichas caen hasta la fila libre más baja", () => {
    const board = grid(6, 7);
    expect(landingRow(board, 3)).toBe(5);
    (board[5] as (Disc | null)[])[3] = "Red";
    expect(landingRow(board, 3)).toBe(4);
  });

  it("encuentra la línea ganadora", () => {
    const board = grid(6, 7);
    for (const r of [2, 3, 4, 5]) (board[r] as (Disc | null)[])[0] = "Yellow";
    expect([...winningCells(board, 4)].sort()).toEqual(["2,0", "3,0", "4,0", "5,0"]);
    expect(winningCells(grid(6, 7), 4).size).toBe(0);
  });

  it("se juega pulsando una columna", () => {
    const p = props(
      { board: grid(6, 7), turn: 0 },
      { actions: [0, 1, 2, 3, 4, 5, 6].map((c) => ({ name: "drop", args: { c } })) },
    );
    render(
      <LocaleProvider initial="es">
        <Board {...p} />
      </LocaleProvider>,
    );
    expect(screen.getByText("Te toca: suelta una ficha")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Columna 4" }));
    expect(p.act).toHaveBeenCalledWith({ name: "drop", args: { c: 3 } });
  });
});
