// SPDX-License-Identifier: Apache-2.0
import { LocaleProvider } from "@gamehub/i18n";
import type { GameUiProps } from "@gamehub/shell";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { attacked, Board, capturedPieces, squareName } from "../src/Board";
import type { Action, Cell, Piece, State } from "../src/game";

afterEach(() => cleanup());

const BACK = ["Rook", "Knight", "Bishop", "Queen", "King", "Bishop", "Knight", "Rook"];

function start(): (Piece | null)[][] {
  const rank = (color: string) => BACK.map((k) => `${color}${k}` as Piece);
  const pawns = (color: string) => Array.from({ length: 8 }, () => `${color}Pawn` as Piece);
  const empty = () => Array.from({ length: 8 }, () => null);
  return [
    rank("Black"),
    pawns("Black"),
    empty(),
    empty(),
    empty(),
    empty(),
    pawns("White"),
    rank("White"),
  ];
}

function state(board = start(), turn = 0): State {
  return {
    board,
    turn,
    castling: [true, true, true, true],
    en_passant: null,
    kings: [
      [7, 4],
      [0, 4],
    ],
    halfmove: 0,
    fullmove: 1,
    history: [],
    from_cell: [0, 0],
    to_cell: [0, 0],
    promotion: null,
  };
}

function props(s: State, extra: Partial<GameUiProps<State, Action>> = {}) {
  return {
    view: { node: "Move", status: "decision", active: [s.turn], state: s },
    seat: 0,
    players: [
      { seat: 0, name: "Ana" },
      { seat: 1, name: "Luis" },
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

const play = (from: Cell, to: Cell): Action => ({ name: "play", args: { from, to } });

describe("Ajedrez", () => {
  it("nombra las casillas como en la notación", () => {
    expect(squareName([6, 4])).toBe("e2");
    expect(squareName([0, 0])).toBe("a8");
  });

  it("ve el jaque", () => {
    const board = start();
    (board[1] as (Piece | null)[])[5] = null;
    (board[3] as (Piece | null)[])[7] = "WhiteQueen";
    expect(attacked(board, [0, 4], true)).toBe(true);
    expect(attacked(start(), [0, 4], true)).toBe(false);
    expect(attacked(start(), [5, 5], true)).toBe(true);
  });

  it("cuenta las piezas capturadas", () => {
    const board = start();
    (board[1] as (Piece | null)[])[3] = null;
    expect(capturedPieces(board)).toEqual(["BlackPawn"]);
  });

  it("se juega pulsando la pieza y el destino", () => {
    const p = props(state(), { actions: [play([6, 4], [5, 4]), play([6, 4], [4, 4])] });
    show(p);
    expect(screen.getByText("Te toca")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Casilla e2 ♙" }));
    fireEvent.click(screen.getByRole("button", { name: "Casilla e4" }));
    expect(p.act).toHaveBeenCalledWith(play([6, 4], [4, 4]));
  });

  it("al coronar se elige la pieza", () => {
    const board = start();
    (board[0] as (Piece | null)[])[0] = null;
    (board[1] as (Piece | null)[])[0] = "WhitePawn";
    const promote = (into: string) =>
      ({ name: "promote", args: { from: [1, 0], to: [0, 0], into } }) as Action;
    const p = props(state(board), {
      actions: [promote("Queen"), promote("Rook"), promote("Bishop"), promote("Knight")],
    });
    show(p);
    fireEvent.click(screen.getByRole("button", { name: "Casilla a7 ♙" }));
    fireEvent.click(screen.getByRole("button", { name: "Casilla a8" }));
    fireEvent.click(screen.getByRole("button", { name: "Caballo" }));
    expect(p.act).toHaveBeenCalledWith(promote("Knight"));
  });

  it("las negras ven el tablero girado y el final", () => {
    const p = props(state(start(), 1), {
      seat: 1,
      view: { node: "Checkmate", status: "terminal", active: [], state: state(start(), 1) },
    } as unknown as Partial<GameUiProps<State, Action>>);
    show(p);
    const cells = screen.getAllByRole("button");
    expect(cells[0]?.getAttribute("aria-label")).toBe("Casilla h1 ♖");
    expect(screen.getByText("Jaque mate: has perdido")).toBeTruthy();
  });
});
