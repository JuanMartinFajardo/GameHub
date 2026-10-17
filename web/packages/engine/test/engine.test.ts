// SPDX-License-Identifier: Apache-2.0
/**
 * El núcleo WebAssembly en Node: las trazas doradas de conformidad (spec/conformance), las mismas
 * partidas que el motor de Python con la misma semilla, los errores y los plugins nativos.
 */

import { spawnSync } from "node:child_process";
import { mkdtempSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import { type CoreGame, type Engine, EngineError, loadEngine, nativeIds } from "../src";
import { CONFORMANCE, exampleIr, REPO } from "./fixtures";

interface Trace {
  game: { id: string; rules_hash: string };
  num_players: number;
  params: Record<string, unknown>;
  seed: number;
  steps: ({ chance: number[] } | { seat: number; action: { name: string; args: object } })[];
  digests: string[];
  result?: { node: string; payoffs: (number | string)[] };
}

function traces(): [string, string, Trace][] {
  const found: [string, string, Trace][] = [];
  for (const game of readdirSync(CONFORMANCE)) {
    for (const file of readdirSync(join(CONFORMANCE, game))) {
      const text = readFileSync(join(CONFORMANCE, game, file), "utf8");
      found.push([game, file, JSON.parse(text) as Trace]);
    }
  }
  return found;
}

let engine: Engine;
const games = new Map<string, CoreGame>();

async function game(name: string): Promise<CoreGame> {
  let found = games.get(name);
  if (found === undefined) {
    found = await engine.game(exampleIr(name));
    games.set(name, found);
  }
  return found;
}

beforeAll(async () => {
  engine = await loadEngine({ loadBytes: (url) => readFile(url) });
});

describe("trazas de conformidad", () => {
  it.each(traces())("%s/%s: la misma huella en cada paso", async (name, _file, trace) => {
    const g = await game(name);
    expect(g.rulesHash).toBe(trace.game.rules_hash);
    const s = g.session(trace.num_players, trace.params, trace.seed);
    const digests = [s.digest()];
    for (const step of trace.steps) {
      if ("chance" in step) s.applyChance(step.chance);
      else s.act(step.seat, step.action as never);
      digests.push(s.digest());
    }
    expect(digests).toEqual(trace.digests);
    if (trace.result) {
      expect(s.node).toBe(trace.result.node);
      expect(s.payoffs()).toEqual(trace.result.payoffs);
    }
    s.dispose();
  });

  it.each(traces())(
    "%s/%s: el azar y los bots de la sesión juegan la misma partida que Python",
    async (name, _file, trace) => {
      // Las trazas son partidas de `play_match` con agentes aleatorios: el azar sale de
      // PCG32(semilla, STREAM_CHANCE) y cada agente de PCG32(semilla, 1000 + asiento).
      const g = await game(name);
      const s = g.session(trace.num_players, trace.params, trace.seed);
      const digests = [s.digest()];
      while (!s.terminal) {
        if (s.status === "chance") s.chance();
        else {
          const seat = s.activeSeats()[0] ?? 0;
          s.act(seat, s.botAction(seat, "random"));
        }
        digests.push(s.digest());
      }
      expect(digests).toEqual(trace.digests);
      s.dispose();
    },
  );
});

describe("sesiones", () => {
  it("vistas, eventos, acciones legales, opciones y deshacer", async () => {
    const g = await game("tictactoe");
    const s = g.session(2);
    expect(s.status).toBe("decision");
    expect(s.activeSeats()).toEqual([0]);
    const legal = s.legal(0);
    expect(legal.actions).toHaveLength(9);
    expect(legal.truncated).toBe(false);
    expect(s.legal(0, 4)).toEqual({ actions: legal.actions.slice(0, 4), truncated: true });
    expect(s.options(0)).toEqual(["place"]);
    const first = legal.actions[4];
    if (first === undefined) throw new Error("sin acciones");
    s.act(0, first);
    expect(s.depth).toBe(1);
    expect(s.activeSeats()).toEqual([1]);
    expect(s.view(1).active).toEqual([1]);
    expect(s.eventsFrom(1, 0).some((e) => e.type === "action")).toBe(true);
    expect(s.undo()).toBe(true);
    expect(s.depth).toBe(0);
    expect(s.undo()).toBe(false);
    s.dispose();
  });

  it("los errores llegan como EngineError con su tipo", async () => {
    const g = await game("tictactoe");
    const s = g.session(2);
    const bad = { name: "place", args: { c: [7, 7] } };
    expect(() => s.act(0, bad)).toThrow(EngineError);
    try {
      s.act(1, { name: "place", args: { c: [0, 0] } });
    } catch (error) {
      expect((error as EngineError).kind).toBe("illegal");
    }
    expect(() => g.session(5)).toThrow(EngineError);
    expect(() => engine.gameSync("{}")).toThrow(EngineError);
    s.dispose();
  });

  it("el azar se puede enumerar con probabilidades exactas", async () => {
    const g = await game("kuhn-poker");
    const s = g.session(2);
    expect(s.status).toBe("chance");
    const outcomes = s.chanceOutcomes();
    expect(outcomes).toHaveLength(6);
    expect(new Set(outcomes.map(([, p]) => p))).toEqual(new Set(["1/6"]));
    s.dispose();
  });

  it("MCTS no deja ganar al rival en el tres en raya", async () => {
    const g = await game("tictactoe");
    const s = g.session(2, {}, 3);
    // X amenaza la fila de arriba: O debe tapar (0, 2).
    s.act(0, { name: "place", args: { c: [0, 0] } });
    s.act(1, { name: "place", args: { c: [1, 1] } });
    s.act(0, { name: "place", args: { c: [0, 1] } });
    expect(s.botAction(1, "mcts", 3000)).toEqual({ name: "place", args: { c: [0, 2] } });
    expect(s.botAction(1, "first")).toEqual(s.legal(1).actions[0]);
    // Con tope de tiempo: mil millones de simulaciones, pero 50 ms.
    const started = performance.now();
    s.botAction(1, "mcts", 1e9, 0.05);
    expect(performance.now() - started).toBeLessThan(1000);
    s.dispose();
  });

  it("partidas aleatorias como `gamehub fuzz`", async () => {
    const g = await game("nim");
    const report = g.playouts({ players: 2, games: 500 });
    expect(report).toMatchObject({ games: 500, completed: 500, truncated: 0, errors: [] });
    expect(report.fingerprint).toMatch(/^[0-9a-f]{16}$/);
    expect(g.playouts({ players: 2, games: 500 }).fingerprint).toBe(report.fingerprint);
  });
});

// --- Con Python: los juegos del catálogo y los plugins nativos --------------------------------

const python =
  process.env.GAMEHUB_SKIP_SERVER_TESTS !== "1" &&
  spawnSync("uv", ["--version"], { stdio: "ignore" }).status === 0;

function uv(args: string[]): string {
  const run = spawnSync("uv", ["run", ...args], { cwd: join(REPO, "python"), encoding: "utf8" });
  if (run.status !== 0) throw new Error(run.stderr);
  return run.stdout;
}

describe.runIf(python)("plugins nativos (con Python)", () => {
  let ir = "";
  beforeAll(() => {
    const out = join(mkdtempSync(join(tmpdir(), "gh-engine-")), "texas-holdem.ir.json");
    uv(["gamehub", "compile", join(REPO, "games/texas-holdem/texas-holdem.game"), "-o", out]);
    ir = readFileSync(out, "utf8");
  }, 120_000);

  it("el plugin de póquer da las mismas partidas que la referencia y que el núcleo nativo", async () => {
    expect(nativeIds(JSON.parse(ir))).toContain("std.poker.hand_value");
    const withPlugin = await engine.game(ir);
    const reference = await engine.game(ir, { natives: false });
    expect(withPlugin.natives).toBe(true);
    expect(reference.natives).toBe(false);
    const options = { players: 3, games: 60, seed: 7 };
    const a = withPlugin.playouts(options);
    const b = reference.playouts(options);
    expect(a.errors).toEqual([]);
    expect(a.fingerprint).toBe(b.fingerprint);
    // El mismo C++ compilado para la máquina (sin plugins) desde Python.
    const script = [
      "import sys, gamehub_core",
      "g = gamehub_core.Game(open(sys.argv[1]).read())",
      "print('%016x' % g.playouts(3, None, 7, 60, 10000)['fingerprint'])",
    ].join("\n");
    const file = join(mkdtempSync(join(tmpdir(), "gh-engine-")), "ir.json");
    writeFileSync(file, ir);
    expect(uv(["python", "-c", script, file]).trim()).toBe(a.fingerprint);
    withPlugin.dispose();
    reference.dispose();
  }, 120_000);
});

describe.runIf(python)("las partidas del Studio (con Python)", () => {
  it.each([
    ["tictactoe", 2, 300, 4],
    ["kuhn-poker", 2, 300, 9],
    ["mentiroso", 3, 40, 2],
    ["nim", 2, 200, 0],
  ] as const)(
    "%s: las mismas cifras y cobertura que gamehub.studio.sim.playouts",
    async (name, players, games, seed) => {
      const g = await game(name);
      const { seconds: _a, ...ours } = g.studioPlayouts({ players, games, seed });
      const script = [
        "import json, sys",
        "from gamehub.engine.game import load_game",
        "from gamehub.studio.sim import playouts",
        "g = load_game(sys.argv[1])",
        "r = playouts(g, games=int(sys.argv[2]), players=int(sys.argv[3]), seed=int(sys.argv[4]),",
        "             time_limit=1e9)",
        "r.pop('seconds')",
        "print(json.dumps(r))",
      ].join("\n");
      const file = join(REPO, "spec/ir/examples", `${name}.ir.json`);
      const theirs = JSON.parse(
        uv(["python", "-c", script, file, String(games), String(players), String(seed)]),
      );
      expect(ours).toEqual(theirs);
      expect(ours.finished).toBeGreaterThan(0);
      // Por tramos (sin bloquear la página), lo mismo.
      const { seconds: _b, ...chunked } = await g.studioPlayoutsChunked(
        { players, games, seed },
        7,
      );
      expect(chunked).toEqual(theirs);
    },
    120_000,
  );
});
