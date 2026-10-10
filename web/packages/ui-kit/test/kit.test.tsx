// SPDX-License-Identifier: Apache-2.0
import { LocaleProvider } from "@gamehub/i18n";
import { act, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  Clock,
  Deck,
  Die,
  formatClock,
  Grid,
  Hand,
  Pile,
  PlayerBadge,
  PlayingCard,
  Scoreboard,
  seatColor,
  standardRank,
  standardSuit,
  Token,
  Track,
} from "../src";

function inSpanish(node: ReactNode) {
  return render(<LocaleProvider initial="es">{node}</LocaleProvider>);
}

afterEach(() => {
  vi.useRealTimers();
});

describe("cartas", () => {
  it("reconoce palos y valores de la baraja francesa y la española", () => {
    expect(standardSuit("Hearts")?.symbol).toBe("♥");
    expect(standardSuit("Spades")?.name).toBe("picas");
    expect(standardSuit("Oros")?.name).toBe("oros");
    expect(standardSuit("Moons")).toBeNull();
    expect(standardRank("Ace")).toBe("A");
    expect(standardRank("Ten")).toBe("10");
    expect(standardRank("Queen")).toBe("Q");
    expect(standardRank("K")).toBe("K");
    expect(standardRank(7)).toBe("7");
  });

  it("se leen en voz alta y se pueden elegir", () => {
    const onClick = vi.fn();
    inSpanish(
      <>
        <PlayingCard rank="A" suit={standardSuit("Hearts")} onClick={onClick} />
        <PlayingCard faceDown />
      </>,
    );
    fireEvent.click(screen.getByRole("button", { name: "A de corazones" }));
    expect(onClick).toHaveBeenCalledOnce();
    expect(screen.getByText("Carta boca abajo")).toBeTruthy();
  });

  it("una mano ajena muestra solo dorsos y un montón cuenta sus cartas", () => {
    inSpanish(
      <>
        <Hand label="Mano de Luis" hidden={3} />
        <Pile count={5} label="Montón" top={<PlayingCard rank="K" />} />
        <Deck count={0} label="Mazo" />
      </>,
    );
    const hand = screen.getByRole("list", { name: "Mano de Luis" });
    expect(hand.textContent).toBe("Carta boca abajo".repeat(3));
    expect(screen.getByLabelText("Montón: 5 cartas")).toBeTruthy();
    expect(screen.getByLabelText("Mazo: 0 cartas")).toBeTruthy();
  });
});

describe("rejilla", () => {
  it("solo deja pulsar las casillas posibles", () => {
    const onSelect = vi.fn();
    inSpanish(
      <Grid
        rows={2}
        columns={2}
        isTarget={(r, c) => r === 1 && c === 0}
        onSelect={onSelect}
        renderCell={(r, c) => (r === 0 && c === 0 ? "X" : null)}
        label="Tablero"
      />,
    );
    expect(screen.getAllByRole("button")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Casilla 1, 0" }));
    expect(onSelect).toHaveBeenCalledWith(1, 0);
    expect(screen.getByRole("table", { name: "Tablero" }).textContent).toContain("X");
  });

  it("en modo columna se elige la columna", () => {
    const onSelect = vi.fn();
    inSpanish(
      <Grid rows={3} columns={2} mode="column" isTarget={(_, c) => c === 1} onSelect={onSelect} />,
    );
    const buttons = screen.getAllByRole("button", { name: "Columna 1" });
    expect(buttons).toHaveLength(3);
    fireEvent.mouseEnter(buttons[0] as HTMLElement);
    expect(document.querySelectorAll(".gh-grid__cell--hover")).toHaveLength(3);
    fireEvent.click(buttons[2] as HTMLElement);
    expect(onSelect).toHaveBeenCalledWith(2, 1);
  });
});

describe("piezas y jugadores", () => {
  it("dados con puntos, con número o tapados", () => {
    inSpanish(
      <>
        <Die value={5} />
        <Die value={12} />
        <Die />
      </>,
    );
    const five = screen.getByText("Dado: 5").parentElement as HTMLElement;
    expect(five.querySelectorAll("circle")).toHaveLength(5);
    expect(screen.getByText("Dado: 12").parentElement?.querySelector("svg")?.textContent).toBe(
      "12",
    );
    expect(screen.getByText("Dado oculto")).toBeTruthy();
  });

  it("fichas, recorridos y colores de asiento", () => {
    inSpanish(
      <>
        <Token color="#e53935" label="Ficha roja" />
        <Track spaces={4} tokens={[{ at: 2, color: "red", label: "Ana" }]} label="Recorrido" />
      </>,
    );
    expect(screen.getByText("Ficha roja")).toBeTruthy();
    const spaces = screen.getAllByRole("listitem");
    expect(spaces).toHaveLength(4);
    expect(spaces[2]?.textContent).toBe("3Ana");
    expect(seatColor(1)).toBe("var(--gh-seat-1)");
    expect(seatColor(9)).toBe("var(--gh-seat-1)");
    expect(seatColor(0, ["#000"])).toBe("#000");
  });

  it("insignias de jugador y marcador", () => {
    inSpanish(
      <>
        <PlayerBadge name="Ana" you active />
        <Scoreboard
          columns={["Jugador", "Pago"]}
          rows={[{ name: "Luis", values: [3], highlight: true }]}
        />
      </>,
    );
    expect(screen.getByText("(tú)")).toBeTruthy();
    expect(screen.getByText("le toca")).toBeTruthy();
    expect(screen.getByRole("table").textContent).toContain("Luis");
  });
});

describe("reloj", () => {
  it("formatea y descuenta mientras corre", () => {
    expect(formatClock(65_000)).toBe("1:05");
    expect(formatClock(3_725_000)).toBe("1:02:05");
    expect(formatClock(-5)).toBe("0:00");
    vi.useFakeTimers();
    inSpanish(<Clock ms={12_000} running />);
    expect(screen.getByRole("timer").textContent).toBe("0:12");
    act(() => {
      vi.advanceTimersByTime(3_000);
    });
    expect(screen.getByRole("timer").textContent).toBe("0:09");
    expect(screen.getByRole("timer").className).toContain("gh-clock--low");
  });
});
