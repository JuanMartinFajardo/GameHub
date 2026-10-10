// SPDX-License-Identifier: Apache-2.0
import type { ServerMessage } from "@gamehub/protocol";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ClientError, GameClient, legalOf, myTurn } from "../src";
import { FakeServer, SESSION } from "./fake";

const START = {
  match: { id: "m1", number: 1 },
  seat: 0,
  players: 2,
  params: {},
  seats: [
    { seat: 0, name: "Ana", kind: "human" },
    { seat: 1, name: "Luis", kind: "human" },
  ],
  fairness: { scheme: "gamehub-fair/1", commitment: "0".repeat(64), client_seeds: ["", ""] },
  clock: { kind: "none" },
};

function update(seq: number, legal = true, events: object[] = [{ type: "node", node: "Move" }]) {
  return {
    type: "update",
    data: {
      seq,
      view: { node: "Move", status: "decision", active: [legal ? 0 : 1], state: { turn: 0 } },
      events,
      ...(legal
        ? { legal: { kind: "enumerated", actions: [{ name: "take", args: { n: 1 } }] } }
        : {}),
    },
  } as Omit<ServerMessage, "v">;
}

function client(server: FakeServer, extra: object = {}) {
  return new GameClient({
    server: "localhost:7420",
    name: "Ana",
    heartbeat: 0,
    webSocket: server.factory,
    ...extra,
  });
}

afterEach(() => {
  vi.useRealTimers();
});

describe("conexión", () => {
  it("saluda con el límite de acciones legales y el nombre del programa", async () => {
    const server = FakeServer.welcoming();
    const c = client(server, { legalLimit: 300 });
    const welcome = await c.connect();
    expect(welcome.server.name).toBe("Prueba");
    expect(server.sockets[0]?.url).toBe("ws://localhost:7420/ws");
    const hello = server.received[0];
    expect(hello?.type).toBe("hello");
    expect(hello?.data).toEqual({
      client: { name: "gamehub-web", kind: "human" },
      legal_limit: 300,
    });
    expect(hello?.id).toMatch(/^[0-9a-f]{8}-1$/);
    expect(c.getState().status).toBe("connected");
  });

  it("retoma la sesión con el token y tolera que haya caducado", async () => {
    const server = new FakeServer();
    server.handler = (socket, msg) => {
      if (msg.type !== "hello") return;
      socket.push({
        type: "error",
        re: msg.id,
        data: { code: "invalid_token", message: "caducada" },
      } as Omit<ServerMessage, "v">);
      socket.push({
        type: "welcome",
        re: msg.id,
        data: { server: { name: "Prueba", version: "0" } },
      } as Omit<ServerMessage, "v">);
    };
    const c = client(server, { token: "viejo" });
    await c.connect();
    expect(server.received[0]?.data).toMatchObject({ token: "viejo" });
    expect(c.getState().token).toBeNull();
  });

  it("falla si no hay servidor", async () => {
    const server = new FakeServer();
    server.refuse = true;
    const c = client(server);
    await expect(c.connect()).rejects.toBeInstanceOf(ClientError);
    expect(c.getState().status).toBe("closed");
  });

  it("los ids de mensaje no se repiten entre clientes", async () => {
    const a = client(FakeServer.welcoming());
    const b = client(FakeServer.welcoming());
    await a.connect();
    await b.connect();
    expect(a.send("ping", {})).not.toBe(b.send("ping", {}));
  });
});

describe("sala y partida", () => {
  async function seated() {
    const server = FakeServer.welcoming();
    server.handler = (socket, msg) => {
      if (msg.type === "hello") {
        socket.push({
          type: "welcome",
          re: msg.id,
          data: { server: { name: "Prueba", version: "0" } },
        } as Omit<ServerMessage, "v">);
      } else if (msg.type === "join") {
        socket.push({
          type: "joined",
          re: msg.id,
          data: { token: "t0k3n", session: SESSION },
        } as Omit<ServerMessage, "v">);
      }
    };
    const c = client(server);
    await c.connect();
    await c.join("k7f-q2p");
    return { server, c, socket: server.last };
  }

  it("entra en la sala con el código normalizado", async () => {
    const { server, c } = await seated();
    expect(server.received[1]).toMatchObject({
      type: "join",
      data: { room: "K7FQ2P", role: "player", name: "Ana" },
    });
    expect(c.getState().token).toBe("t0k3n");
    expect(c.getState().session?.seat).toBe(0);
  });

  it("sigue el asiento propio en los mensajes de sala", async () => {
    const { c, socket } = await seated();
    socket.push({
      type: "room",
      data: {
        seats: [{ seat: 1, kind: "human", participant: "p1", connected: true, ready: false }],
        spectators: [],
      },
    } as unknown as Omit<ServerMessage, "v">);
    expect(c.getState().session).toMatchObject({ seat: 1, role: "player" });
  });

  it("acumula los eventos, refresca sin repetirlos y pide resync si falta alguno", async () => {
    const { server, c, socket } = await seated();
    socket.push({ type: "match_start", data: START } as Omit<ServerMessage, "v">);
    socket.push(update(0));
    socket.push(update(1, false, [{ type: "action", seat: 0, name: "take", args: { n: 1 } }]));
    expect(c.getState().match?.log.map((e) => e.seq)).toEqual([0, 1]);
    socket.push(update(1, false, []));
    expect(c.getState().match?.log).toHaveLength(2);
    expect(c.getState().stale).toBe(false);
    socket.push(update(3, true));
    expect(c.getState().stale).toBe(true);
    expect(server.received.filter((m) => m.type === "resync")).toHaveLength(1);
    socket.push(update(4, true));
    expect(server.received.filter((m) => m.type === "resync")).toHaveLength(1);
    socket.push({ type: "match_start", data: START } as Omit<ServerMessage, "v">);
    expect(c.getState().stale).toBe(false);
  });

  it("marca la jugada pendiente y recoge el rechazo", async () => {
    const { server, c, socket } = await seated();
    socket.push({ type: "match_start", data: START } as Omit<ServerMessage, "v">);
    socket.push(update(0));
    const legal = legalOf(c.getState());
    expect(legal?.kind).toBe("enumerated");
    expect(myTurn(c.getState())).toBe(true);
    const id = c.act({ name: "take", args: { n: 1 } });
    expect(server.received.at(-1)).toMatchObject({ type: "act", id, data: { seq: 0 } });
    expect(myTurn(c.getState())).toBe(false);
    socket.push({
      type: "rejected",
      re: id,
      data: { seq: 0, reason: "illegal_action", detail: "no" },
    } as Omit<ServerMessage, "v">);
    expect(c.getState().match?.pending).toBeNull();
    expect(c.getState().match?.rejected).toMatchObject({ reason: "illegal_action", re: id });
    expect(myTurn(c.getState())).toBe(true);
    socket.push(update(1, false));
    expect(c.getState().match?.rejected).toBeNull();
  });

  it("construye acciones progresivas con query_actions", async () => {
    const { server, c, socket } = await seated();
    server.handler = (s, msg) => {
      if (msg.type === "query_actions") {
        s.push({
          type: "actions",
          re: msg.id,
          data: { seq: 0, name: "take", args: {}, options: [0, 1, 2] },
        } as Omit<ServerMessage, "v">);
      }
    };
    socket.push({ type: "match_start", data: START } as Omit<ServerMessage, "v">);
    socket.push(update(0));
    await expect(c.queryActions("take", {})).resolves.toEqual([0, 1, 2]);
  });

  it("los errores de una petición rechazan su promesa", async () => {
    const { server, c } = await seated();
    server.handler = (s, msg) => {
      if (msg.type === "join") {
        s.push({
          type: "error",
          re: msg.id,
          data: { code: "room_full", message: "llena" },
        } as Omit<ServerMessage, "v">);
      }
    };
    await expect(c.join("AAAAAA")).rejects.toMatchObject({ code: "room_full" });
    expect(c.getState().error).toBeNull();
  });

  it("vence el plazo si el servidor no responde", async () => {
    const server = new FakeServer();
    const c = client(server, { timeout: 20 });
    await expect(c.connect()).rejects.toMatchObject({ code: "timeout" });
  });
});

describe("reconexión", () => {
  it("vuelve a conectar y retoma la partida donde estaba", async () => {
    vi.useFakeTimers();
    const server = FakeServer.welcoming();
    server.handler = (socket, msg) => {
      if (msg.type === "hello") {
        socket.push({
          type: "welcome",
          re: msg.id,
          data: { server: { name: "Prueba", version: "0" }, session: SESSION },
        } as Omit<ServerMessage, "v">);
      }
    };
    const c = client(server, { token: "t0k3n" });
    const connecting = c.connect();
    await vi.advanceTimersByTimeAsync(0);
    await connecting;
    server.last.push({ type: "match_start", data: START } as Omit<ServerMessage, "v">);
    server.last.push(update(0));
    c.act({ name: "take", args: { n: 1 } });
    server.last.drop();
    expect(c.getState().status).toBe("reconnecting");
    await vi.advanceTimersByTimeAsync(300);
    expect(server.sockets).toHaveLength(2);
    const hello = server.received.filter((m) => m.type === "hello").at(-1);
    expect(hello?.data).toMatchObject({ token: "t0k3n", resume: { match: "m1", seq: 0 } });
    expect(c.getState().status).toBe("connected");
    // La jugada enviada antes del corte se olvida: si llegó, la actualización lo dirá.
    expect(c.getState().match?.pending).toBeNull();
  });

  it("no reconecta si otra conexión ha tomado la sesión", async () => {
    vi.useFakeTimers();
    const server = FakeServer.welcoming(SESSION);
    const c = client(server, { token: "t0k3n" });
    const connecting = c.connect();
    await vi.advanceTimersByTimeAsync(0);
    await connecting;
    server.last.push({
      type: "error",
      data: { code: "replaced", message: "otra pestaña" },
    } as Omit<ServerMessage, "v">);
    await vi.advanceTimersByTimeAsync(10_000);
    expect(server.sockets).toHaveLength(1);
    expect(c.getState().status).toBe("closed");
    expect(c.getState().error?.code).toBe("replaced");
  });

  it("sin token no hay nada que retomar", async () => {
    const server = FakeServer.welcoming();
    const c = client(server);
    await c.connect();
    server.last.drop();
    expect(c.getState().status).toBe("closed");
  });

  it("el latido detecta una conexión muerta", async () => {
    vi.useFakeTimers();
    const server = FakeServer.welcoming(SESSION);
    const c = client(server, { token: "t0k3n", heartbeat: 1000 });
    const connecting = c.connect();
    await vi.advanceTimersByTimeAsync(0);
    await connecting;
    server.handler = () => {}; // el servidor deja de contestar
    await vi.advanceTimersByTimeAsync(3500);
    expect(server.received.some((m) => m.type === "ping")).toBe(true);
    expect(server.sockets.length).toBeGreaterThan(1);
  });
});
