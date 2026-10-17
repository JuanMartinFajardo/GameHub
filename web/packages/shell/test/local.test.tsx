// SPDX-License-Identifier: Apache-2.0
/**
 * Una partida en este dispositivo sin servidor de partidas: la app solo pide la IR del juego y
 * juega con el núcleo C++ en WebAssembly (@gamehub/engine), pulsando la interfaz.
 */

import { readFileSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { loadEngine } from "@gamehub/engine";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { PlayApp } from "../src";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = false;

const REPO = resolve(import.meta.dirname, "../../../..");
const IR = readFileSync(resolve(REPO, "spec/ir/examples/tictactoe.ir.json"), "utf8");

/** Un «servidor» que solo sirve la IR del tres en raya; cualquier otra petición falla. */
function serveIrOnly() {
  const requests: string[] = [];
  vi.stubGlobal("fetch", async (input: RequestInfo | URL) => {
    const url = String(input);
    requests.push(url);
    if (url.endsWith("/api/v1/games/tictactoe")) {
      return new Response(IR, { headers: { "content-type": "application/json" } });
    }
    return new Response(JSON.stringify({ error: { code: "internal", message: "no" } }), {
      status: 500,
    });
  });
  return requests;
}

beforeAll(async () => {
  // El módulo se carga una vez por página: aquí, leyendo los binarios del disco (Vite sirve el
  // paquete en /@fs/… en los tests).
  await loadEngine({
    loadBytes: (url) =>
      readFile(url.protocol === "file:" ? url : decodeURIComponent(url.pathname.slice(4))),
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function freeCells(): Promise<HTMLElement[]> {
  return waitFor(
    () => {
      const free = screen.queryAllByRole("button", { name: /^Casilla \d, \d$/ });
      if (free.length === 0 && !screen.queryByText("Resultado")) throw new Error("esperando");
      return free;
    },
    { timeout: 10_000 },
  );
}

describe("en este dispositivo, con el motor en el navegador", () => {
  it("dos personas se turnan hasta el final y juegan otra", async () => {
    const requests = serveIrOnly();
    localStorage.setItem("gamehub:locale", "es");
    history.pushState(null, "", "/local/tictactoe");
    render(<PlayApp server="" />);
    fireEvent.click(await screen.findByRole("button", { name: "Empezar" }, { timeout: 10_000 }));
    await screen.findByText("Elige una casilla", undefined, { timeout: 10_000 });
    for (let turn = 0; turn < 9 && !screen.queryByText("Resultado"); turn++) {
      const cells = await freeCells();
      if (cells.length === 0) break;
      fireEvent.click(cells[0] as HTMLElement);
      // La UI pasa al siguiente asiento (o al resultado).
      await waitFor(
        () => {
          const left = screen.queryAllByRole("button", { name: /^Casilla \d, \d$/ }).length;
          if (left >= cells.length && !screen.queryByText("Resultado")) throw new Error("…");
        },
        { timeout: 10_000 },
      );
    }
    await screen.findByText("Resultado", undefined, { timeout: 10_000 });
    // Solo se ha pedido la IR: ninguna sala.
    expect(requests.every((u) => u.endsWith("/api/v1/games/tictactoe"))).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Otra partida" }));
    await screen.findByText("Elige una casilla", undefined, { timeout: 10_000 });
  }, 60_000);

  it("contra un bot MCTS", async () => {
    serveIrOnly();
    localStorage.setItem("gamehub:locale", "es");
    history.pushState(null, "", "/local/tictactoe");
    render(<PlayApp server="" />);
    const bot = await screen.findAllByRole("checkbox", undefined, { timeout: 10_000 });
    fireEvent.click(bot[0] as HTMLElement);
    fireEvent.change(screen.getByRole("combobox", { name: "Tipo de bot" }), {
      target: { value: "mcts" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Empezar" }));
    await screen.findByText("Elige una casilla", undefined, { timeout: 10_000 });
    for (let turn = 0; turn < 5 && !screen.queryByText("Resultado"); turn++) {
      const cells = await freeCells();
      if (cells.length === 0) break;
      fireEvent.click(cells[0] as HTMLElement);
      await waitFor(
        () => {
          if (!screen.queryByText("Elige una casilla") && !screen.queryByText("Resultado")) {
            throw new Error("esperando al bot");
          }
          const left = screen.queryAllByRole("button", { name: /^Casilla \d, \d$/ }).length;
          if (left > cells.length - 2 && !screen.queryByText("Resultado")) throw new Error("…");
        },
        { timeout: 15_000 },
      );
    }
    await screen.findByText("Resultado", undefined, { timeout: 15_000 });
    // Jugando siempre la primera casilla libre, MCTS no pierde: el pago de Jugador 1 no es 1.
    const row = screen.getByRole("rowheader", { name: /Jugador 1/ }).closest("tr");
    const payoff = row?.querySelectorAll("td")[1]?.textContent;
    expect(["0", "-1"]).toContain(payoff);
  }, 60_000);
});
