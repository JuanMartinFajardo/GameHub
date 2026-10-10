// SPDX-License-Identifier: Apache-2.0
import { LocaleProvider } from "@gamehub/i18n";
import type { ActionData, Legal, View } from "@gamehub/protocol";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { AutoGame } from "../src";
import { IR, PLAYERS } from "./fixtures";

function es(node: ReactNode) {
  return render(<LocaleProvider initial="es">{node}</LocaleProvider>);
}

const empty = [
  [null, null, null],
  [null, "X", null],
  [null, null, null],
];

function tttView(active: number[]): View {
  return { node: "Move", status: "decision", active, state: { board: empty, turn: 1 } };
}

describe("tres en raya", () => {
  it("se juega pulsando una casilla libre", () => {
    const onAct = vi.fn();
    const legal: Legal = {
      kind: "enumerated",
      actions: [
        { name: "place", args: { c: [0, 0] } },
        { name: "place", args: { c: [2, 2] } },
      ],
    };
    es(
      <AutoGame
        game={IR.tictactoe}
        view={tttView([1])}
        seat={1}
        players={PLAYERS.slice(0, 2)}
        legal={legal}
        onAct={onAct}
      />,
    );
    expect(screen.getByText("Te toca")).toBeTruthy();
    expect(screen.getByText("Elige una casilla")).toBeTruthy();
    const targets = screen.getAllByRole("button", { name: /Casilla/ });
    expect(targets.map((b) => b.getAttribute("aria-label"))).toEqual([
      "Casilla 0, 0",
      "Casilla 2, 2",
    ]);
    fireEvent.click(screen.getByRole("button", { name: "Casilla 2, 2" }));
    expect(onAct).toHaveBeenCalledWith({ name: "place", args: { c: [2, 2] } });
  });

  it("quien mira no puede tocar nada y ve de quién es el turno", () => {
    es(
      <AutoGame
        game={IR.tictactoe}
        view={tttView([1])}
        seat={null}
        players={PLAYERS.slice(0, 2)}
      />,
    );
    expect(screen.queryAllByRole("button")).toHaveLength(0);
    expect(screen.getByText("Turno de Luis")).toBeTruthy();
    expect(screen.getByRole("table").textContent).toContain("X");
  });
});

describe("Nim", () => {
  it("elige los argumentos uno a uno con botones", () => {
    const onAct = vi.fn();
    const view: View = {
      node: "Take",
      status: "decision",
      active: [0],
      state: { heaps: [1, 2], turn: 0 },
    };
    const legal: Legal = {
      kind: "enumerated",
      actions: [
        { name: "take", args: { heap: 0, count: 1 } },
        { name: "take", args: { heap: 1, count: 1 } },
        { name: "take", args: { heap: 1, count: 2 } },
      ],
    };
    es(
      <AutoGame
        game={IR.nim}
        view={view}
        seat={0}
        players={PLAYERS.slice(0, 2)}
        legal={legal}
        onAct={onAct}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Take…" }));
    expect(screen.getByText(/· Heap:/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "1" }));
    expect(screen.getByText(/· Count:/)).toBeTruthy();
    const counts = screen.getAllByRole("button").filter((b) => b.hasAttribute("data-gh-choice"));
    expect(counts.map((b) => b.textContent)).toEqual(["1", "2"]);
    fireEvent.click(counts[1] as HTMLElement);
    expect(onAct).toHaveBeenCalledWith({ name: "take", args: { heap: 1, count: 2 } });
  });

  it("con acciones progresivas pregunta al servidor", async () => {
    const onAct = vi.fn();
    const queryActions = vi.fn(async (_name?: string, args?: Record<string, unknown>) =>
      args && "heap" in args ? [1, 2, 3] : [0, 1],
    );
    const view: View = {
      node: "Take",
      status: "decision",
      active: [0],
      state: { heaps: [1, 3], turn: 0 },
    };
    es(
      <AutoGame
        game={IR.nim}
        view={view}
        seat={0}
        players={PLAYERS.slice(0, 2)}
        legal={{ kind: "progressive", names: ["take"] }}
        onAct={onAct}
        queryActions={queryActions}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Take…" }));
    await waitFor(() =>
      expect(
        screen.getAllByRole("button").filter((b) => b.hasAttribute("data-gh-choice")),
      ).toHaveLength(2),
    );
    fireEvent.click(
      screen
        .getAllByRole("button")
        .filter((b) => b.hasAttribute("data-gh-choice"))[1] as HTMLElement,
    );
    await waitFor(() =>
      expect(
        screen.getAllByRole("button").filter((b) => b.hasAttribute("data-gh-choice")),
      ).toHaveLength(3),
    );
    fireEvent.click(
      screen
        .getAllByRole("button")
        .filter((b) => b.hasAttribute("data-gh-choice"))[2] as HTMLElement,
    );
    expect(queryActions).toHaveBeenCalledWith("take", {});
    expect(queryActions).toHaveBeenCalledWith("take", { heap: 1 });
    expect(onAct).toHaveBeenCalledWith({ name: "take", args: { heap: 1, count: 3 } });
  });
});

describe("Mentiroso", () => {
  const hand = [
    { suit: "Clubs", rank: "Ace" },
    { suit: "Hearts", rank: "Two" },
    { suit: "Spades", rank: "Ace" },
  ];
  const view: View = {
    node: "Play",
    status: "decision",
    active: [0],
    state: {
      deck: { size: 0, items: [] },
      hand: [
        { size: 3, items: hand },
        { size: 17, items: [] },
        { size: 17, items: [] },
      ],
      pile: { size: 0, items: [] },
      turn: 0,
      rank: "Ace",
      last_by: 0,
      last_count: 0,
      winner: 0,
    },
  };
  const subsets: ActionData[] = [[0], [1], [2], [0, 1], [0, 2], [1, 2], [0, 1, 2]].map((ix) => ({
    name: "play",
    args: { cards: ix.map((i) => hand[i]) },
  }));

  it("se marcan cartas de la mano y se juegan", () => {
    const onAct = vi.fn();
    es(
      <AutoGame
        game={IR.mentiroso}
        view={view}
        seat={0}
        players={PLAYERS}
        legal={{ kind: "enumerated", actions: subsets }}
        onAct={onAct}
        params={{ max_play: 4 }}
      />,
    );
    expect(screen.getByText(/Elige de Hand \(1–4\)/)).toBeTruthy();
    const confirm = screen.getByRole("button", { name: "Play" });
    expect((confirm as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Ace · picas" }));
    fireEvent.click(screen.getByRole("button", { name: "Ace · tréboles" }));
    const ready = screen.getByRole("button", { name: "Play (2)" }) as HTMLButtonElement;
    expect(ready.disabled).toBe(false);
    fireEvent.click(ready);
    expect(onAct).toHaveBeenCalledWith({ name: "play", args: { cards: [hand[0], hand[2]] } });
  });

  it("las manos ajenas se ven boca abajo", () => {
    es(
      <AutoGame
        game={IR.mentiroso}
        view={view}
        seat={0}
        players={PLAYERS}
        params={{ max_play: 4 }}
      />,
    );
    expect(screen.getAllByText("Carta boca abajo")).toHaveLength(34);
    expect(screen.queryByRole("button", { name: /Ace/ })).toBeNull();
  });
});

describe("estado de la partida", () => {
  it("muestra el resultado al terminar", () => {
    es(
      <AutoGame
        game={IR.tictactoe}
        view={{ ...tttView([]), status: "terminal" }}
        seat={0}
        players={PLAYERS.slice(0, 2)}
        end={{
          match: { id: "m", number: 1 },
          reason: "terminal",
          payoffs: [1, -1],
          ranking: [1, 2],
          forfeited: [],
          view: tttView([]),
          fairness: { scheme: "gamehub-fair/1", commitment: "x", client_seeds: [] },
          replay: "m",
        }}
      />,
    );
    expect(screen.getByText("Partida terminada")).toBeTruthy();
    expect(screen.getByText("Resultado")).toBeTruthy();
    expect(screen.getAllByText("#1").length).toBeGreaterThan(0);
  });

  it("enseña un rechazo y espera mientras se envía", () => {
    const { rerender } = es(
      <AutoGame
        game={IR.tictactoe}
        view={tttView([0])}
        seat={0}
        players={PLAYERS.slice(0, 2)}
        busy
        legal={{ kind: "enumerated", actions: [] }}
      />,
    );
    expect(screen.getByText("Enviando…")).toBeTruthy();
    act(() => {
      rerender(
        <LocaleProvider initial="es">
          <AutoGame
            game={IR.tictactoe}
            view={tttView([0])}
            seat={0}
            players={PLAYERS.slice(0, 2)}
            legal={{ kind: "enumerated", actions: [{ name: "place", args: { c: [0, 0] } }] }}
            rejected={{ detail: "esa casilla está ocupada" }}
          />
        </LocaleProvider>,
      );
    });
    expect(screen.getByText("Jugada rechazada: esa casilla está ocupada")).toBeTruthy();
  });
});
