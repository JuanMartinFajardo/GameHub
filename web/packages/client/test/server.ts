// SPDX-License-Identifier: Apache-2.0
/**
 * Arranca el servidor de partidas de Python (`gamehub serve`, con uv) para los tests de
 * integración. Si uv no está disponible o GAMEHUB_SKIP_SERVER_TESTS=1, esos tests se saltan.
 */

import { type ChildProcess, spawn, spawnSync } from "node:child_process";
import { resolve } from "node:path";

export const REPO = resolve(import.meta.dirname, "../../../..");

export const serverAvailable =
  process.env.GAMEHUB_SKIP_SERVER_TESTS !== "1" &&
  spawnSync("uv", ["--version"], { stdio: "ignore" }).status === 0;

export interface RunningServer {
  url: string;
  stop(): Promise<void>;
}

/** `gamehub serve` con los juegos indicados (directorios de `games/`; `""` = todo el catálogo),
 * en un puerto libre. */
export function startServer(games: string[], extra: string[] = []): Promise<RunningServer> {
  const args = [
    "run",
    "gamehub",
    "serve",
    ...games.map((g) => resolve(REPO, "games", g)),
    "--host",
    "127.0.0.1",
    "--port",
    "0",
    "--db",
    ":memory:",
    ...extra,
  ];
  const child: ChildProcess = spawn("uv", args, {
    cwd: resolve(REPO, "python"),
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env, PYTHONUNBUFFERED: "1" },
  });
  return new Promise((ok, fail) => {
    let output = "";
    const timer = setTimeout(() => {
      child.kill("SIGKILL");
      fail(new Error(`el servidor no arranca:\n${output}`));
    }, 60_000);
    const read = (chunk: Buffer) => {
      output += chunk.toString();
      const found = output.match(/Servidor de partidas en (http:\/\/\S+)/);
      if (found?.[1] !== undefined) {
        clearTimeout(timer);
        ok({
          url: found[1],
          stop: () =>
            new Promise((done) => {
              child.once("exit", () => done());
              child.kill("SIGINT");
            }),
        });
      }
    };
    child.stdout?.on("data", read);
    child.stderr?.on("data", read);
    child.once("exit", (code) => {
      clearTimeout(timer);
      fail(new Error(`el servidor ha terminado (${code}):\n${output}`));
    });
  });
}
