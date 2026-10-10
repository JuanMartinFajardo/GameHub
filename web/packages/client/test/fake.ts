// SPDX-License-Identifier: Apache-2.0
/** Un servidor falso en memoria para probar el cliente sin red. */

import type { ClientMessage, ServerMessage } from "@gamehub/protocol";
import type { WebSocketLike } from "../src";

type Handler = (socket: FakeSocket, msg: ClientMessage) => void;

export class FakeSocket implements WebSocketLike {
  readyState = 0;
  onopen: ((event: unknown) => void) | null = null;
  onmessage: ((event: { data: unknown }) => void) | null = null;
  onclose: ((event: { code: number; reason: string }) => void) | null = null;
  onerror: ((event: unknown) => void) | null = null;
  readonly sent: ClientMessage[] = [];

  constructor(
    readonly url: string,
    private readonly server: FakeServer,
  ) {
    queueMicrotask(() => {
      if (server.refuse) {
        this.readyState = 3;
        this.onclose?.({ code: 1006, reason: "" });
      } else {
        this.readyState = 1;
        this.onopen?.({});
      }
    });
  }

  send(data: string): void {
    const msg = JSON.parse(data) as ClientMessage;
    this.sent.push(msg);
    this.server.received.push(msg);
    this.server.handler?.(this, msg);
  }

  close(): void {
    if (this.readyState === 3) return;
    this.readyState = 3;
    this.onclose?.({ code: 1000, reason: "" });
  }

  /** El servidor envía un mensaje. */
  push(msg: Omit<ServerMessage, "v">): void {
    this.onmessage?.({ data: JSON.stringify({ v: 1, ...msg }) });
  }

  /** Se corta la conexión sin despedirse. */
  drop(): void {
    this.readyState = 3;
    this.onclose?.({ code: 1006, reason: "" });
  }
}

export class FakeServer {
  readonly sockets: FakeSocket[] = [];
  readonly received: ClientMessage[] = [];
  refuse = false;
  handler: Handler | null = null;

  factory = (url: string): FakeSocket => {
    const socket = new FakeSocket(url, this);
    this.sockets.push(socket);
    return socket;
  };

  get last(): FakeSocket {
    const socket = this.sockets.at(-1);
    if (socket === undefined) throw new Error("sin conexiones");
    return socket;
  }

  /** Responde al `hello` con `welcome` (con la sesión, si se dan datos de sesión). */
  static welcoming(session?: object): FakeServer {
    const server = new FakeServer();
    server.handler = (socket, msg) => {
      if (msg.type === "hello") {
        const data = { server: { name: "Prueba", version: "0" }, ...(session ? { session } : {}) };
        socket.push({ type: "welcome", re: msg.id, data } as Omit<ServerMessage, "v">);
      }
    };
    return server;
  }
}

export const SESSION = {
  room: "K7FQ2P",
  participant: "p1",
  name: "Ana",
  role: "player",
  seat: 0,
  host: true,
} as const;
