// SPDX-License-Identifier: Apache-2.0
// Un test de ejemplo: el tablero se dibuja y jugar llama a `act`. Cámbialo con tu tablero.
import { LocaleProvider } from "@gamehub/i18n";
import type { GameUiProps } from "@gamehub/shell";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Board } from "../src/Board";
import type { Action, State } from "../src/game";

afterEach(() => cleanup());

describe("__TITLE__", () => {
  it("enseña las acciones legales y juega", () => {
    const act = vi.fn();
    const action = { name: "example", args: {} } as unknown as Action;
    const props = {
      view: { node: null, status: "decision", active: [0], state: {} as State },
      seat: 0,
      players: [{ seat: 0, name: "Ana" }],
      actions: [action],
      act,
      busy: false,
    } as unknown as GameUiProps<State, Action>;
    render(
      <LocaleProvider initial="es">
        <Board {...props} />
      </LocaleProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "example" }));
    expect(act).toHaveBeenCalledWith(action);
  });
});
