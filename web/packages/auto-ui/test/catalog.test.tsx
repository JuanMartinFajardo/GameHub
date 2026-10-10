// SPDX-License-Identifier: Apache-2.0
/**
 * Aceptación de la UI genérica: cada juego del catálogo se juega entero contra el servidor de
 * Python de verdad, con una UI genérica por asiento y solo pulsando sus controles (al azar, con
 * semilla): casillas, cartas, botones de acción y de valores, listas desplegables.
 */

import {
  type ClientState,
  createRoom,
  GameClient,
  gameIr,
  legalOf,
  serverInfo,
  type WebSocketLike,
} from "@gamehub/client";
import { LocaleProvider } from "@gamehub/i18n";
import type { GameInfo } from "@gamehub/protocol";
import { fireEvent, render } from "@testing-library/react";
import { useSyncExternalStore } from "react";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { WebSocket } from "ws";
import { type RunningServer, serverAvailable, startServer } from "../../client/test/server";
import { AutoGame, type GameIr } from "../src";

// Los mensajes del servidor llegan fuera de act(): React no debe quejarse por ello.
(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = false;

// En jsdom, el WebSocket del navegador simulado (undici) choca con su clase Event: se usa `ws`.
const webSocket = (url: string) => new WebSocket(url) as unknown as WebSocketLike;

const CONTROLS =
  "[data-gh-act], [data-gh-choice], [data-gh-target], [data-gh-confirm], .gh-grid__hit, button.gh-card";

function Seat(props: { client: GameClient; ir: GameIr }) {
  const { client } = props;
  const state: ClientState = useSyncExternalStore(client.subscribe, client.getState);
  const match = state.match;
  if (!match?.update) return <p>esperando</p>;
  return (
    <AutoGame
      game={props.ir}
      view={match.update.view}
      seat={state.session?.seat ?? null}
      players={match.start.seats.map((s) => ({ seat: s.seat, name: s.name, kind: s.kind }))}
      legal={legalOf(state)}
      busy={match.pending !== null}
      rejected={match.rejected}
      onAct={(a) => client.act(a)}
      queryActions={(name, args) => client.queryActions(name, args)}
      params={match.start.params}
      end={match.end}
      clocks={match.update.clocks ?? null}
      showLog={false}
    />
  );
}

/** Generador con semilla (mulberry32): las partidas se pueden repetir. */
function random(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function until(test: () => boolean, what: string, ms = 15_000): Promise<void> {
  const deadline = Date.now() + ms;
  while (!test()) {
    if (Date.now() > deadline) throw new Error(`no ha pasado a tiempo: ${what}`);
    await sleep(5);
  }
}

/** Juega pulsando controles de la UI de quien tenga el turno hasta el final de la partida. */
async function playThroughUi(
  game: string,
  clients: GameClient[],
  roots: HTMLElement[],
  seed: number,
) {
  const rng = random(seed);
  let clicks = 0;
  let idle = 0;
  while (!clients.every((c) => c.getState().match?.end != null)) {
    if (clicks > 20_000) throw new Error(`${game}: demasiados clics sin terminar`);
    const ready = clients
      .map((c, i) => [c.getState(), i] as const)
      .filter(([s]) => legalOf(s) !== null && s.match?.pending === null && s.match?.end == null)
      .map(([, i]) => i);
    if (ready.length === 0) {
      await sleep(2);
      continue;
    }
    const i = ready[Math.floor(rng() * ready.length)] as number;
    const root = roots[i] as HTMLElement;
    const controls = [...root.querySelectorAll<HTMLElement>(CONTROLS)].filter(
      (el) => !(el as HTMLButtonElement).disabled,
    );
    if (controls.length === 0) {
      idle += 1;
      if (idle > 2000) {
        const state = clients[i]?.getState();
        throw new Error(
          `${game}: el asiento ${i} tiene acciones legales pero ningún control en la UI\n` +
            `legal: ${JSON.stringify(legalOf(state as ClientState)).slice(0, 400)}\n` +
            `html: ${root.innerHTML.slice(0, 1500)}`,
        );
      }
      await sleep(2);
      continue;
    }
    idle = 0;
    // Confirmar en cuanto se pueda, para no marcar y desmarcar sin fin.
    const confirm = controls.find((el) => el.hasAttribute("data-gh-confirm"));
    const el =
      confirm && rng() < 0.6
        ? confirm
        : (controls[Math.floor(rng() * controls.length)] as HTMLElement);
    if (el instanceof HTMLSelectElement) {
      const options = [...el.options].filter((o) => !o.disabled);
      const option = options[Math.floor(rng() * options.length)];
      if (option) fireEvent.change(el, { target: { value: option.value } });
    } else {
      fireEvent.click(el);
    }
    clicks += 1;
    await sleep(0);
  }
  return clicks;
}

/** Los paquetes del catálogo (games/): un juego por paquete. */
const CATALOG = [
  "battle-of-the-sexes",
  "chicken",
  "connect-four",
  "dudo",
  "iterated-pd",
  "kuhn-poker",
  "leduc-poker",
  "matching-pennies",
  "mentiroso",
  "nim",
  "prisoners-dilemma",
  "rock-paper-scissors",
  "stag-hunt",
  "tictactoe",
  "two-by-two",
];

let server: RunningServer;
let games: GameInfo[] = [];

describe.skipIf(!serverAvailable)("todo el catálogo con la UI genérica", () => {
  beforeAll(async () => {
    server = await startServer([""]);
    games = (await serverInfo(server.url)).games;
  }, 120_000);

  afterAll(async () => {
    await server?.stop();
  });

  it("el servidor tiene los juegos del catálogo", () => {
    expect(games.map((g) => g.id).sort()).toEqual(CATALOG);
  });

  it.each(CATALOG)(
    "%s se juega entero solo con la UI genérica",
    async (id) => {
      const info = games.find((g) => g.id === id);
      expect(info, `el servidor no tiene ${id}`).toBeDefined();
      if (!info) return;
      const ir = (await gameIr(server.url, id)) as unknown as GameIr;
      const n = info.players.min;
      const created = await createRoom(server.url, { game: id, players: n, name: "Anfitrión" });
      const clients = Array.from(
        { length: n },
        (_, s) =>
          new GameClient({ server: server.url, name: `J${s + 1}`, heartbeat: 0, webSocket }),
      );
      try {
        for (const c of clients) {
          await c.connect();
          await c.join(created.code);
        }
        for (const c of clients) c.ready();
        const roots = clients.map(
          (c) =>
            render(
              <LocaleProvider initial="es">
                <Seat client={c} ir={ir} />
              </LocaleProvider>,
            ).container,
        );
        await until(
          () => clients.every((c) => c.getState().match?.update != null),
          `${id} empieza`,
        );
        const clicks = await playThroughUi(id, clients, roots, id.length * 7919);
        const end = clients[0]?.getState().match?.end;
        expect(end?.reason).toBe("terminal");
        expect(clicks).toBeGreaterThan(0);
        // Al terminar, cada UI enseña el resultado.
        await until(
          () => roots.every((r) => r.textContent?.includes("Resultado") ?? false),
          "resultado",
        );
      } finally {
        for (const c of clients) c.close();
      }
    },
    180_000,
  );
});
