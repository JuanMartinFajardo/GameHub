// SPDX-License-Identifier: Apache-2.0
import { LocaleProvider } from "@gamehub/i18n";
import type { GameUiProps } from "@gamehub/shell";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Board, steps } from "../src/Board";
import type { Action, State } from "../src/game";
import { corridorPoint, isSafe, pawnPoint, RING, ringPoint, ringSquare } from "../src/geometry";

afterEach(() => cleanup());

function state(extra: Partial<State> = {}): State {
  return {
    pos: [
      [-1, -1, -1, -1],
      [-1, -1, -1, -1],
      [-1, -1, -1, -1],
      [-1, -1, -1, -1],
    ],
    turn: 0,
    die: 5,
    sixes: 0,
    last_pawn: -1,
    bonus: 0,
    winner: 0,
    ...extra,
  };
}

function props(s: State, extra: Partial<GameUiProps<State, Action>> = {}) {
  return {
    view: { node: "Move", status: "decision", active: [s.turn], state: s },
    seat: 0,
    players: [0, 1, 2, 3].map((seat) => ({ seat, name: ["Ana", "Luis", "Eva", "Juan"][seat] })),
    actions: null,
    act: vi.fn(),
    busy: false,
    log: [],
    params: { pairs: false },
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

describe("Parchís", () => {
  it("la geometría del tablero", () => {
    expect(RING.length).toBe(68);
    expect(new Set(RING.map((p) => p.join(","))).size).toBe(68);
    expect(ringPoint(5)).toEqual([10, 14]);
    expect(ringPoint(68)).toEqual([9, 18]);
    expect(isSafe(12) && isSafe(68) && !isSafe(6)).toBe(true);
    expect(pawnPoint(0, 0, 0)).toEqual(ringPoint(5));
    expect(pawnPoint(1, 64, 0)).toEqual(corridorPoint(1, 0));
    expect(ringSquare(1, 53)).toBe(7);
  });

  it("un seis cuenta siete sin fichas en casa", () => {
    expect(steps(6, [3, 10, 71, 64])).toBe(7);
    expect(steps(6, [3, -1, 71, 64])).toBe(6);
  });

  it("se mueve pulsando una ficha resaltada", () => {
    const p = props(state(), { actions: [{ name: "advance", args: { k: 0 } }] as Action[] });
    show(p);
    expect(screen.getByText("Te toca: mueve una ficha 5")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Ficha 1 de Ana (en casa)" }));
    expect(p.act).toHaveBeenCalledWith({ name: "advance", args: { k: 0 } });
    fireEvent.click(screen.getByRole("button", { name: "Ficha 2 de Ana (en casa)" }));
    expect(p.act).toHaveBeenCalledTimes(1);
  });

  it("el premio se cuenta con count_bonus", () => {
    const s = state({ bonus: 20, pos: [[3, -1, -1, -1], ...state().pos.slice(1)] });
    const p = props(s, {
      view: { node: "Bonus", status: "decision", active: [0], state: s },
      actions: [{ name: "count_bonus", args: { k: 0 } }] as Action[],
    } as unknown as Partial<GameUiProps<State, Action>>);
    show(p);
    expect(screen.getByText("¡Premio! Cuenta 20 con una ficha")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Ficha 1 de Ana (3)" }));
    expect(p.act).toHaveBeenCalledWith({ name: "count_bonus", args: { k: 0 } });
  });
});
