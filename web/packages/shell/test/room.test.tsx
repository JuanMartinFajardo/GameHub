// SPDX-License-Identifier: Apache-2.0
/**
 * Una sala de verdad con la app: crear la sala por REST, entrar con el formulario, sentarse,
 * declararse listo y jugar al tres en raya contra un bot del servidor hasta el final, todo
 * pulsando la interfaz.
 */

import { createRoom, endpoints, GameClient, saveSession } from "@gamehub/client";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { WebSocket } from "ws";
import { type RunningServer, serverAvailable, startServer } from "../../client/test/server";
import { PlayApp } from "../src";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = false;
// En jsdom el WebSocket del navegador simulado no sirve con un servidor real (ver auto-ui).
(globalThis as { WebSocket: unknown }).WebSocket = WebSocket;

let server: RunningServer;

describe.skipIf(!serverAvailable)("una sala con la app", () => {
  beforeAll(async () => {
    server = await startServer(["tictactoe"]);
  }, 90_000);

  afterAll(async () => {
    await server?.stop();
  });

  it("se entra, se juega contra un bot y se ve el resultado", async () => {
    const created = await createRoom(server.url, { game: "tictactoe", name: "Anfitrión" });
    // El anfitrión (con su sesión) pone un bot en el asiento 2.
    saveSession(endpoints(server.url).http, created.code, created.token, "Anfitrión");
    localStorage.setItem("gamehub:locale", "es");
    history.pushState(null, "", `/r/${created.code}`);
    render(<PlayApp server={server.url} />);
    await screen.findByText("Estoy listo", undefined, { timeout: 10_000 }).catch(() => null);
    // Sentarse en el asiento 1 (el anfitrión entra como espectador).
    const sit = await screen.findAllByRole(
      "button",
      { name: "Sentarme aquí" },
      { timeout: 10_000 },
    );
    fireEvent.click(sit[0] as HTMLElement);
    await screen.findByRole("button", { name: "Levantarme" }, { timeout: 10_000 });
    const bot = await screen.findAllByRole("button", { name: "Bot" }, { timeout: 10_000 });
    fireEvent.click(bot[0] as HTMLElement);
    fireEvent.click(
      await screen.findByRole("button", { name: "Estoy listo" }, { timeout: 10_000 }),
    );
    await screen.findByText("Elige una casilla", undefined, { timeout: 10_000 });
    // Jugar en la primera casilla libre hasta que termine.
    for (let turn = 0; turn < 9; turn++) {
      if (screen.queryByText("Resultado")) break;
      const cells = await waitFor(
        () => {
          const free = screen.queryAllByRole("button", { name: /^Casilla \d, \d$/ });
          if (free.length === 0 && !screen.queryByText("Resultado"))
            throw new Error("esperando turno");
          return free;
        },
        { timeout: 10_000 },
      );
      if (cells.length === 0) break;
      fireEvent.click(cells[0] as HTMLElement);
      await waitFor(
        () => {
          if (!screen.queryByText("Elige una casilla") && !screen.queryByText("Resultado")) {
            throw new Error("esperando al bot");
          }
        },
        { timeout: 10_000 },
      );
    }
    await screen.findByText("Resultado", undefined, { timeout: 10_000 });
    expect(screen.getByRole("button", { name: "Revancha" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Ver la partida" })).toBeTruthy();
  }, 60_000);

  it("se mira una partida de dos bots como espectador", async () => {
    const created = await createRoom(server.url, { game: "tictactoe", name: "Anfitrión" });
    // El anfitrión pone dos bots lentos: la partida empieza sola.
    const host = new GameClient({ server: server.url, token: created.token, heartbeat: 0 });
    await host.connect();
    host.configure({ settings: { bot_delay: 0.2 } });
    host.setSeat(0, "bot", { bot: "random" });
    host.setSeat(1, "bot", { bot: "first" });
    try {
      localStorage.clear();
      localStorage.setItem("gamehub:locale", "es");
      history.pushState(null, "", `/r/${created.code}`);
      render(<PlayApp server={server.url} />);
      fireEvent.click(await screen.findByRole("button", { name: "Mirar" }, { timeout: 10_000 }));
      // Se ve la partida (sin poder jugar) y su final.
      await screen.findByText(/Turno de Bot|Partida terminada/, undefined, { timeout: 20_000 });
      expect(screen.queryAllByRole("button", { name: /^Casilla/ })).toHaveLength(0);
      await screen.findByText("Resultado", undefined, { timeout: 30_000 });
    } finally {
      host.close();
    }
  }, 60_000);
});
