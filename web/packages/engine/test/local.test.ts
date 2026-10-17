// SPDX-License-Identifier: Apache-2.0
/** Partidas locales: la mesa habla el protocolo de las salas y los clientes lo reducen igual. */

import { readFile } from "node:fs/promises";
import { type ClientState, legalOf } from "@gamehub/client";
import type { GameInfo } from "@gamehub/protocol";
import { beforeAll, describe, expect, it } from "vitest";
import { type CoreGame, type LocalClient, LocalTable, loadEngine } from "../src";
import { exampleIr } from "./fixtures";

let tictactoe: CoreGame;
let kuhn: CoreGame;

beforeAll(async () => {
  const engine = await loadEngine({ loadBytes: (url) => readFile(url) });
  tictactoe = await engine.game(exampleIr("tictactoe"));
  kuhn = await engine.game(exampleIr("kuhn-poker"));
});

function info(game: CoreGame): GameInfo {
  return {
    id: game.id,
    version: "1.0.0",
    title: game.title,
    rules_hash: game.rulesHash,
    players: { min: game.minPlayers, max: game.maxPlayers },
  };
}

function until(
  client: LocalClient,
  test: (state: ClientState) => boolean,
  ms = 5000,
): Promise<ClientState> {
  return new Promise((resolve, reject) => {
    if (test(client.getState())) {
      resolve(client.getState());
      return;
    }
    const timer = setTimeout(() => {
      stop();
      reject(new Error("no ha pasado a tiempo"));
    }, ms);
    const stop = client.subscribe(() => {
      if (test(client.getState())) {
        clearTimeout(timer);
        stop();
        resolve(client.getState());
      }
    });
  });
}

const seqOf = (s: ClientState) => s.match?.update?.seq ?? -1;

describe("mesa local", () => {
  it("dos personas en el mismo dispositivo: turnos, rechazos, final y revancha", async () => {
    const table = new LocalTable({
      game: tictactoe,
      info: info(tictactoe),
      seats: [{ name: "Ana" }, { name: "Bea" }],
      seed: 1,
    });
    const [a, b] = [table.client(0), table.client(1)];
    expect(a.getState().session).toMatchObject({ seat: 0, host: true, role: "player" });
    expect(b.getState().session).toMatchObject({ seat: 1, host: false });
    table.start();
    const s0 = a.getState();
    expect(s0.match?.start).toMatchObject({
      seat: 0,
      players: 2,
      seats: [
        { seat: 0, name: "Ana", kind: "human" },
        { seat: 1, name: "Bea", kind: "human" },
      ],
    });
    expect(seqOf(s0)).toBe(0);
    const legal = legalOf(s0);
    expect(legal?.kind).toBe("enumerated");
    expect(legal?.kind === "enumerated" && legal.actions).toHaveLength(9);
    expect(legalOf(b.getState())).toBeNull();

    // No le toca a Bea.
    b.act({ name: "place", args: { c: [0, 0] } });
    let sb = await until(b, (s) => s.match?.rejected !== null);
    expect(sb.match?.rejected?.reason).toBe("not_your_turn");
    // Una casilla que no existe.
    a.act({ name: "place", args: { c: [5, 5] } });
    expect(a.getState().match?.pending).not.toBeNull();
    const rejected = await until(a, (s) => s.match?.rejected !== null);
    expect(rejected.match?.rejected?.reason).toBe("illegal_action");
    expect(rejected.match?.pending).toBeNull();

    // La partida de la traza seed-1: gana X.
    const moves: [number, number, number][] = [
      [0, 1, 2],
      [1, 2, 0],
      [0, 2, 2],
      [1, 0, 1],
      [0, 0, 0],
      [1, 2, 1],
      [0, 0, 2],
    ];
    for (const [seat, r, c] of moves) {
      const client = seat === 0 ? a : b;
      const before = seqOf(client.getState());
      client.act({ name: "place", args: { c: [r, c] } });
      await until(client, (s) => seqOf(s) > before);
    }
    const end = (await until(a, (s) => s.match?.end != null)).match?.end;
    expect(end).toMatchObject({ reason: "terminal", payoffs: [1, -1], ranking: [1, 2] });
    expect(end?.fairness.seed).toBe(1);
    sb = await until(b, (s) => s.match?.end != null);
    expect(sb.match?.log.filter((e) => e.event.type === "action")).toHaveLength(7);
    expect(legalOf(sb)).toBeNull();

    // Revancha: cuando están listos los dos.
    a.ready();
    await Promise.resolve();
    expect(a.getState().match?.end).not.toBeNull();
    b.ready();
    const again = await until(a, (s) => s.match?.end === null);
    expect(again.match?.start.match.number).toBe(2);
    a.close();
    b.close();
  });

  it("contra un bot, con azar e información oculta", async () => {
    const table = new LocalTable({
      game: kuhn,
      info: info(kuhn),
      seats: [{ name: "Ana" }, { name: "Bot", bot: "random" }],
      seed: 5,
      botDelay: 0,
    });
    const a = table.client(0);
    expect(table.humans()).toEqual([0]);
    table.start();
    for (let i = 0; i < 10; i++) {
      const state = await until(a, (s) => s.match?.end != null || legalOf(s) !== null);
      if (state.match?.end) break;
      const legal = legalOf(state);
      if (legal?.kind !== "enumerated") throw new Error("sin acciones");
      const before = seqOf(state);
      a.act(legal.actions[0] ?? { name: "check", args: {} });
      await until(a, (s) => seqOf(s) > before);
    }
    const end = (await until(a, (s) => s.match?.end != null)).match?.end;
    expect(end?.reason).toBe("terminal");
    expect(end?.payoffs).toHaveLength(2);
    // Ana ha visto el reparto (el azar) en su primera actualización, sin la carta del bot.
    const deal = (a.getState().match?.log ?? [])
      .filter((e) => e.seq === 0 && e.event.type === "move")
      .map((e) => e.event.items);
    expect(deal).toHaveLength(2);
    expect(deal[0]).not.toEqual([{ $hidden: true }]);
    expect(deal[1]).toEqual([{ $hidden: true }]);
    a.close();
  });

  it("acciones progresivas cuando hay demasiadas", async () => {
    const table = new LocalTable({
      game: tictactoe,
      info: info(tictactoe),
      seats: [{ name: "Ana" }, { name: "Bea" }],
      legalLimit: 3,
    });
    table.start();
    const a = table.client(0);
    expect(legalOf(a.getState())).toEqual({ kind: "progressive", names: ["place"] });
    expect(await a.queryActions()).toEqual(["place"]);
    expect(await a.queryActions("place")).toHaveLength(9);
    expect(await table.client(1).queryActions("place")).toEqual([]);
    table.dispose();
  });

  it("los parámetros se comprueban al crear la mesa", () => {
    expect(
      () =>
        new LocalTable({
          game: tictactoe,
          info: info(tictactoe),
          seats: [{ name: "Ana" }, { name: "Bea" }],
          params: { nope: 1 },
        }),
    ).toThrow();
  });
});
