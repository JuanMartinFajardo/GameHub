// SPDX-License-Identifier: Apache-2.0
/**
 * Arranca el Studio de Python (`gamehub studio`, con uv) sobre una copia temporal de algunos
 * juegos del catálogo, para los tests de integración. Si uv no está disponible o
 * GAMEHUB_SKIP_SERVER_TESTS=1, esos tests se saltan.
 */

import { type ChildProcess, spawn, spawnSync } from "node:child_process";
import { cpSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve, sep } from "node:path";
import { WebSocket } from "ws";
import { StudioApi } from "../src/api";
import { type SocketLike, StudioConnection } from "../src/connection";
import { Studio } from "../src/store";
import type { Analysis } from "../src/types";

export const REPO = resolve(import.meta.dirname, "../../../..");
export const TOKEN = "token-de-prueba";

export const serverAvailable =
  process.env.GAMEHUB_SKIP_SERVER_TESTS !== "1" &&
  spawnSync("uv", ["--version"], { stdio: "ignore" }).status === 0;

export interface RunningStudio {
  /** `http://127.0.0.1:<puerto>` */
  url: string;
  /** El directorio de trabajo (una copia temporal). */
  root: string;
  stop(): Promise<void>;
}

/** `gamehub studio` sobre una copia de los juegos dados, en un puerto libre. */
export function startStudio(games: string[] = ["tictactoe", "dudo"]): Promise<RunningStudio> {
  const root = mkdtempSync(join(tmpdir(), "gamehub-studio-"));
  for (const game of games) {
    const from = resolve(REPO, "games", game);
    cpSync(from, join(root, game), {
      recursive: true,
      // Sin la UI propia (con su node_modules): solo el paquete del juego.
      filter: (src) => !src.slice(from.length).startsWith(`${sep}ui`),
    });
  }
  const child: ChildProcess = spawn("uv", ["run", "gamehub", "studio", root, "--port", "0"], {
    cwd: resolve(REPO, "python"),
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env, PYTHONUNBUFFERED: "1", GAMEHUB_STUDIO_TOKEN: TOKEN },
  });
  return new Promise((ok, fail) => {
    let output = "";
    const timer = setTimeout(() => {
      child.kill("SIGKILL");
      fail(new Error(`el Studio no arranca:\n${output}`));
    }, 60_000);
    const read = (chunk: Buffer) => {
      output += chunk.toString();
      const found = output.match(/ábrelo en: (http:\/\/[^/\s]+)\//);
      if (found?.[1] !== undefined) {
        clearTimeout(timer);
        ok({
          url: found[1],
          root,
          stop: () =>
            new Promise((done) => {
              child.once("exit", () => {
                rmSync(root, { recursive: true, force: true });
                done();
              });
              child.kill("SIGINT");
            }),
        });
      }
    };
    child.stdout?.on("data", read);
    child.stderr?.on("data", read);
    child.once("exit", (code) => {
      clearTimeout(timer);
      fail(new Error(`el Studio ha terminado (${code}):\n${output}`));
    });
  });
}

/** Un `Studio` (el estado de la app) conectado al servidor, como lo crea `StudioApp`. */
export async function connectStudio(server: RunningStudio): Promise<Studio> {
  const api = new StudioApi(server.url, TOKEN);
  const workspace = await api.workspace();
  const connection = new StudioConnection({
    url: `${server.url.replace("http", "ws")}/lsp?token=${TOKEN}`,
    rootUri: workspace.rootUri,
    webSocket: (url) => new WebSocket(url) as unknown as SocketLike,
  });
  const studio = new Studio(connection, api);
  studio.set({ workspace });
  await connection.connect();
  return studio;
}

/** Espera a que se cumpla algo del estado del Studio. */
export function until<T>(
  studio: Studio,
  test: () => T | null | undefined | false,
  what: string,
  ms = 20_000,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const found = test();
    if (found) {
      resolve(found);
      return;
    }
    const timer = setTimeout(() => {
      stop();
      reject(new Error(`no ha pasado a tiempo: ${what}`));
    }, ms);
    const stop = studio.subscribe(() => {
      const value = test();
      if (value) {
        clearTimeout(timer);
        stop();
        resolve(value);
      }
    });
  });
}

/** El análisis del archivo abierto cuando su texto es el del editor. */
export function analysisOf(studio: Studio, version?: number): Promise<Analysis> {
  return until(
    studio,
    () => {
      const analysis = studio.getState().analysis;
      if (!analysis) return null;
      const current = studio.editor ? studio.connection.version(analysis.uri) : null;
      const wanted = version ?? current;
      return wanted === null || analysis.version === wanted ? analysis : null;
    },
    "el análisis del texto actual",
  );
}
