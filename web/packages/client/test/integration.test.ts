// SPDX-License-Identifier: Apache-2.0
/** El SDK contra el servidor de partidas de Python de verdad (ver `server.ts`). */

import { afterAll, beforeAll, describe, expect, it } from "vitest";
import {
  type ClientState,
  createRoom,
  GameClient,
  getRoom,
  legalOf,
  listMatches,
  roomIr,
  serverInfo,
  type WebSocketLike,
} from "../src";
import { type RunningServer, serverAvailable, startServer } from "./server";

let server: RunningServer;

function until(
  client: GameClient,
  test: (state: ClientState) => boolean,
  what: string,
  ms = 10_000,
): Promise<ClientState> {
  return new Promise((resolve, reject) => {
    if (test(client.getState())) {
      resolve(client.getState());
      return;
    }
    const timer = setTimeout(() => {
      stop();
      reject(new Error(`no ha pasado a tiempo: ${what}`));
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

/** Juega la primera acción legal cada vez que le toca, hasta el final de la partida. */
function autoplay(client: GameClient): () => void {
  const play = () => {
    const state = client.getState();
    const legal = legalOf(state);
    if (legal?.kind === "enumerated" && state.match?.pending === null) {
      const first = legal.actions[0];
      if (first !== undefined) client.act(first);
    }
  };
  const stop = client.subscribe(play);
  play();
  return stop;
}

describe.skipIf(!serverAvailable)("con el servidor de Python", () => {
  beforeAll(async () => {
    server = await startServer(["tictactoe", "nim"]);
  }, 90_000);

  afterAll(async () => {
    await server?.stop();
  });

  it("informa del catálogo y de las salas por REST", async () => {
    const info = await serverInfo(server.url);
    expect(info.protocol).toBe(1);
    expect(info.games.map((g) => g.id).sort()).toEqual(["nim", "tictactoe"]);
    const created = await createRoom(server.url, { game: "nim", name: "Ana" });
    expect(created.code).toMatch(/^[0-9A-Z]{6}$/);
    const room = await getRoom(server.url, created.code);
    expect(room.game.id).toBe("nim");
    const ir = await roomIr(server.url, created.code);
    expect((ir.game as { id: string }).id).toBe("nim");
    await expect(getRoom(server.url, "ZZZZZZ")).rejects.toMatchObject({ code: "unknown_room" });
  });

  it("dos clientes juegan una partida entera, con una caída y un espectador", async () => {
    const created = await createRoom(server.url, { game: "tictactoe", name: "Ana" });
    // El anfitrión retoma la sesión que ha creado la sala y se sienta.
    const sockets: WebSocketLike[] = [];
    const ana = new GameClient({ server: server.url, name: "Ana", token: created.token });
    const luis = new GameClient({
      server: server.url,
      name: "Luis",
      webSocket: (url) => {
        const ws = new WebSocket(url) as unknown as WebSocketLike;
        sockets.push(ws);
        return ws;
      },
    });
    const eva = new GameClient({ server: server.url, name: "Eva" });
    try {
      const welcome = await ana.connect();
      expect(welcome.session).toMatchObject({ host: true, role: "spectator" });
      ana.sit(0);
      await until(ana, (s) => s.session?.seat === 0, "Ana se sienta");
      await luis.connect();
      const joined = await luis.join(created.code);
      expect(joined.session.seat).toBe(1);
      await eva.connect();
      await eva.join(created.code, { role: "spectator" });
      ana.ready();
      luis.ready();
      await until(ana, (s) => s.match?.update !== null && s.match !== null, "empieza la partida");
      const stopAna = autoplay(ana);
      // Luis juega una vez, se le cae la conexión y vuelve solo (resume) para seguir jugando.
      await until(luis, (s) => s.match?.update !== null && s.match !== null, "Luis ve la partida");
      await until(luis, (s) => legalOf(s) !== null, "le toca a Luis");
      const first = legalOf(luis.getState());
      if (first?.kind !== "enumerated" || first.actions[0] === undefined) throw new Error("legal");
      luis.act(first.actions[0]);
      await until(luis, (s) => (s.match?.update?.seq ?? 0) >= 2, "la jugada de Luis se aplica");
      sockets[0]?.close();
      await until(luis, (s) => s.status === "reconnecting", "Luis se queda sin conexión");
      await until(luis, (s) => s.status === "connected", "Luis vuelve", 15_000);
      const stopLuis = autoplay(luis);
      const end = await until(ana, (s) => s.match?.end != null, "termina la partida");
      stopAna();
      stopLuis();
      expect(end.match?.end?.reason).toBe("terminal");
      expect(end.match?.end?.payoffs).toHaveLength(2);
      const watched = await until(eva, (s) => s.match?.end != null, "Eva ve el final");
      expect(watched.session?.role).toBe("spectator");
      expect(watched.match?.log.some((e) => e.event.type === "action")).toBe(true);
      // Los registros de Ana y de Luis cuentan las mismas actualizaciones.
      const seqs = (c: GameClient) => [...new Set(c.getState().match?.log.map((e) => e.seq))];
      expect(seqs(luis)).toEqual(seqs(ana));
      const matches = await listMatches(server.url);
      expect(matches.some((m) => m.id === end.match?.end?.match.id)).toBe(true);
    } finally {
      ana.close();
      luis.close();
      eva.close();
    }
  }, 60_000);

  it("con muchas acciones, se construyen paso a paso", async () => {
    const created = await createRoom(server.url, { game: "nim", name: "Ana", players: 2 });
    const ana = new GameClient({ server: server.url, name: "Ana", legalLimit: 1 });
    const luis = new GameClient({ server: server.url, name: "Luis", legalLimit: 1 });
    try {
      await ana.connect();
      await ana.join(created.code);
      await luis.connect();
      await luis.join(created.code);
      ana.ready();
      luis.ready();
      const state = await until(ana, (s) => legalOf(s) !== null, "le toca a Ana");
      expect(legalOf(state)).toEqual({ kind: "progressive", names: ["take"] });
      expect(await ana.queryActions()).toEqual(["take"]);
      const heaps = await ana.queryActions("take");
      expect(heaps).toEqual([0, 1, 2]);
      const counts = await ana.queryActions("take", { heap: 2 });
      expect(counts).toEqual([1, 2, 3, 4, 5, 6, 7]);
      ana.act({ name: "take", args: { heap: 2, count: 7 } });
      await until(luis, (s) => legalOf(s) !== null, "le toca a Luis");
      expect(luis.getState().match?.update?.view.state).toMatchObject({ heaps: [3, 5, 0] });
      // Una jugada ilegal vuelve como rechazo.
      luis.act({ name: "take", args: { heap: 2, count: 1 } });
      const rejected = await until(luis, (s) => s.match?.rejected != null, "rechazo");
      expect(rejected.match?.rejected?.reason).toBe("illegal_action");
    } finally {
      ana.close();
      luis.close();
    }
  }, 60_000);
});
