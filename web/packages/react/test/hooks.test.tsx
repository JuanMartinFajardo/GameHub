// SPDX-License-Identifier: Apache-2.0
import { GameClient, type WebSocketLike } from "@gamehub/client";
import type { ServerMessage } from "@gamehub/protocol";
import { act, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { GameClientProvider, useAct, useLegalActions, useMyTurn, useView } from "../src";

class Socket implements WebSocketLike {
  readyState = 1;
  onopen: ((event: unknown) => void) | null = null;
  onmessage: ((event: { data: unknown }) => void) | null = null;
  onclose: ((event: { code: number; reason: string }) => void) | null = null;
  onerror: ((event: unknown) => void) | null = null;
  sent: { type: string; data: unknown }[] = [];
  constructor() {
    queueMicrotask(() => this.onopen?.({}));
  }
  send(data: string) {
    const msg = JSON.parse(data);
    this.sent.push(msg);
    if (msg.type === "hello")
      this.push({ type: "welcome", re: msg.id, data: { server: { name: "s", version: "0" } } });
  }
  close() {}
  push(msg: object) {
    this.onmessage?.({ data: JSON.stringify({ v: 1, ...msg }) });
  }
}

function Board() {
  const view = useView<{ heaps: number[] }>();
  const legal = useLegalActions();
  const mine = useMyTurn();
  const play = useAct();
  return (
    <div>
      <p>montones: {view?.state.heaps.join(",") ?? "—"}</p>
      <p>{mine ? "me toca" : "espera"}</p>
      {legal?.map((a) => (
        <button key={JSON.stringify(a.args)} type="button" onClick={() => play(a)}>
          {a.name} {String(a.args.n)}
        </button>
      ))}
    </div>
  );
}

describe("hooks", () => {
  it("siguen la partida y juegan", async () => {
    const socket = new Socket();
    const client = new GameClient({
      server: "localhost:7420",
      heartbeat: 0,
      webSocket: () => socket,
    });
    await client.connect();
    render(
      <GameClientProvider client={client}>
        <Board />
      </GameClientProvider>,
    );
    expect(screen.getByText("montones: —")).toBeTruthy();
    act(() => {
      socket.push({
        type: "match_start",
        data: {
          match: { id: "m", number: 1 },
          seat: 0,
          players: 2,
          params: {},
          seats: [],
          fairness: { scheme: "gamehub-fair/1", commitment: "0", client_seeds: [] },
          clock: { kind: "none" },
        },
      } as Omit<ServerMessage, "v">);
      socket.push({
        type: "update",
        data: {
          seq: 0,
          view: { node: "Take", status: "decision", active: [0], state: { heaps: [3, 4] } },
          events: [],
          legal: { kind: "enumerated", actions: [{ name: "take", args: { n: 1 } }] },
        },
      });
    });
    expect(screen.getByText("montones: 3,4")).toBeTruthy();
    expect(screen.getByText("me toca")).toBeTruthy();
    act(() => screen.getByRole("button", { name: "take 1" }).click());
    expect(socket.sent.at(-1)).toMatchObject({
      type: "act",
      data: { seq: 0, action: { name: "take" } },
    });
    expect(screen.getByText("espera")).toBeTruthy();
  });
});
