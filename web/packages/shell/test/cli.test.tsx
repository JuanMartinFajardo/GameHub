// SPDX-License-Identifier: Apache-2.0
/**
 * Aceptación de la Fase 4: una partida en línea entre el navegador y la terminal. Ana juega al
 * tres en raya con la app (pulsando casillas) y Luis con `gamehub join` en una terminal de
 * verdad (un subproceso al que se contesta leyendo lo que escribe).
 */

import { type ChildProcess, spawn } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { createRoom, endpoints, saveSession } from "@gamehub/client";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { WebSocket } from "ws";
import { REPO, type RunningServer, serverAvailable, startServer } from "../../client/test/server";
import { PlayApp } from "../src";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = false;
(globalThis as { WebSocket: unknown }).WebSocket = WebSocket;

/** Luis en su terminal: se declara listo y juega la primera opción de cada menú. */
class Terminal {
  readonly lines: string[] = [];
  readonly process: ChildProcess;
  /** Los datos de la terminal (sesiones guardadas), aparte de los del usuario. */
  readonly data = mkdtempSync(join(tmpdir(), "gamehub-terminal-"));
  ends = 0;

  constructor(link: string) {
    this.process = spawn("uv", ["run", "gamehub", "join", link, "--player", "Luis"], {
      cwd: resolve(REPO, "python"),
      stdio: ["pipe", "pipe", "pipe"],
      env: { ...process.env, PYTHONUNBUFFERED: "1", GAMEHUB_DATA: this.data },
    });
    let buffer = "";
    const read = (chunk: Buffer) => {
      buffer += chunk.toString();
      let newline = buffer.indexOf("\n");
      // Las preguntas no acaban en salto de línea: también se miran las líneas a medias.
      while (newline >= 0) {
        this.line(buffer.slice(0, newline));
        buffer = buffer.slice(newline + 1);
        newline = buffer.indexOf("\n");
      }
      if (/(Elige un número|Filtro)[^\n]*: $/.test(buffer)) {
        this.line(buffer);
        buffer = "";
      }
    };
    this.process.stdout?.on("data", read);
    this.process.stderr?.on("data", read);
  }

  private line(text: string) {
    this.lines.push(text);
    if (text.includes("Escribe /listo cuando")) this.say("/listo");
    else if (text.startsWith("Elige un número")) this.say("1");
    else if (text.includes("Fin de la partida")) this.ends += 1;
  }

  say(text: string) {
    this.lines.push(`» ${text}`);
    this.process.stdin?.write(`${text}\n`);
  }

  quit(): Promise<void> {
    return new Promise((done) => {
      this.process.once("exit", () => {
        rmSync(this.data, { recursive: true, force: true });
        done();
      });
      this.say("/salir");
      setTimeout(() => this.process.kill("SIGKILL"), 10_000);
    });
  }
}

let server: RunningServer;

describe.skipIf(!serverAvailable)("navegador contra terminal", () => {
  beforeAll(async () => {
    server = await startServer(["tictactoe"]);
  }, 90_000);

  afterAll(async () => {
    await server?.stop();
  });

  it("Ana juega en la app y Luis en la terminal, hasta el final", async () => {
    const created = await createRoom(server.url, { game: "tictactoe", name: "Ana" });
    saveSession(endpoints(server.url).http, created.code, created.token, "Ana");
    localStorage.setItem("gamehub:locale", "es");
    history.pushState(null, "", `/r/${created.code}`);
    render(<PlayApp server={server.url} />);
    const sit = await screen.findAllByRole(
      "button",
      { name: "Sentarme aquí" },
      { timeout: 10_000 },
    );
    fireEvent.click(sit[0] as HTMLElement);
    await screen.findByRole("button", { name: "Levantarme" }, { timeout: 10_000 });
    const luis = new Terminal(`${server.url}/r/${created.code}`);
    try {
      await screen.findByText("Luis", undefined, { timeout: 30_000 });
      fireEvent.click(await screen.findByRole("button", { name: "Estoy listo" }));
      await screen.findByText("Elige una casilla", undefined, { timeout: 30_000 });
      for (let turn = 0; turn < 5 && !screen.queryByText("Resultado"); turn++) {
        const cells = await waitFor(
          () => {
            const free = screen.queryAllByRole("button", { name: /^Casilla \d, \d$/ });
            if (free.length === 0 && !screen.queryByText("Resultado"))
              throw new Error("turno de Luis");
            return free;
          },
          { timeout: 30_000 },
        );
        if (cells.length === 0) break;
        fireEvent.click(cells[cells.length - 1] as HTMLElement);
        await waitFor(
          () => {
            if (screen.queryAllByRole("button", { name: /^Casilla \d, \d$/ }).length > 0) {
              throw new Error("esperando la respuesta");
            }
          },
          { timeout: 30_000 },
        );
      }
      await screen.findByText("Resultado", undefined, { timeout: 30_000 });
      await waitFor(() => expect(luis.ends).toBe(1), { timeout: 30_000 });
      // Las jugadas de Luis llegaron desde la terminal y las de Ana desde la app.
      expect(luis.lines.some((l) => l.startsWith("» 1"))).toBe(true);
      expect(screen.getAllByText(/^Luis: /).length).toBeGreaterThan(0);
      expect(screen.getAllByText(/^Ana: /).length).toBeGreaterThan(0);
    } catch (error) {
      throw new Error(`${error}\n--- terminal de Luis\n${luis.lines.slice(-40).join("\n")}`);
    } finally {
      await luis.quit();
    }
  }, 120_000);
});
