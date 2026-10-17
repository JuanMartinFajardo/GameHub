// SPDX-License-Identifier: Apache-2.0
/**
 * Partida en un mismo dispositivo («hot-seat»): se juega en el navegador con el núcleo C++ en
 * WebAssembly (@gamehub/engine), sin sala en el servidor; si no se puede cargar, una sala con una
 * conexión por asiento humano, todas en esta pestaña. Se enseña la UI de quien tiene el turno y,
 * si el juego tiene información oculta, se tapa la pantalla entre turnos.
 */

import { AutoGame, type GameModel } from "@gamehub/auto-ui";
import { type ClientState, createRoom, GameClient, legalOf } from "@gamehub/client";
import { pickText, useLocale, useMessages } from "@gamehub/i18n";
import type { ActionData } from "@gamehub/protocol";
import { Button, Field, Panel, Spinner } from "@gamehub/ui-kit";
import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { defaultParams, ParamsForm } from "./forms";
import { loadGameModel, useLoaded } from "./games";
import type { GameUiRegistry } from "./gameui";
import { messages } from "./messages";
import { playersOf } from "./Room";
import { navigate, queryParam } from "./router";

/** Lo que la partida necesita de un cliente (uno del servidor o uno local). */
type SeatClient = Pick<
  GameClient,
  "subscribe" | "getState" | "act" | "queryActions" | "ready" | "close"
>;

interface Local {
  seat: number;
  name: string;
  client: SeatClient;
}

/**
 * Bots: al azar o los que piensan (solo con el motor en el navegador). MCTS y alfa-beta ven el
 * estado entero: se ofrecen en juegos sin información oculta; con ella, los que juegan sobre
 * determinizaciones (ISMCTS, PIMC). El de reglas usa la heurística del juego en los dos casos.
 */
type BotChoice = "random" | "greedy" | "mcts" | "alphabeta" | "ismcts" | "pimc";

const BOT_LABELS: Record<BotChoice, string> = {
  random: "bot",
  greedy: "reglas",
  mcts: "MCTS",
  alphabeta: "alfa-beta",
  ismcts: "ISMCTS",
  pimc: "PIMC",
};

interface SetupChoice {
  players: number;
  names: string[];
  bots: (BotChoice | null)[];
  params: Record<string, unknown>;
}

/** La partida en el navegador: una mesa local con el núcleo WebAssembly. */
async function startInBrowser(model: GameModel, choice: SetupChoice): Promise<Local[]> {
  const { engineSupported, loadEngine, LocalTable } = await import("@gamehub/engine");
  if (!engineSupported()) throw new Error("WebAssembly no disponible");
  const engine = await loadEngine();
  const game = await engine.game(model.ir);
  const seats = Array.from({ length: choice.players }, (_, seat) => {
    const name = choice.names[seat]?.slice(0, 32) || String(seat + 1);
    const bot = choice.bots[seat];
    return bot ? { name: `${name} (${BOT_LABELS[bot]})`, bot } : { name };
  });
  let table: InstanceType<typeof LocalTable>;
  try {
    table = new LocalTable({
      game,
      ownsGame: true,
      info: {
        id: model.id,
        version: model.ir.game.version,
        title: game.title,
        rules_hash: game.rulesHash,
        players: model.ir.players,
      },
      seats,
      params: choice.params,
    });
  } catch (e) {
    game.dispose();
    throw e;
  }
  const locals = table.humans().map((seat) => ({
    seat,
    name: seats[seat]?.name ?? String(seat + 1),
    client: table.client(seat),
  }));
  table.start();
  return locals;
}

/** La partida en el servidor: una sala con una conexión por asiento humano. */
async function startOnServer(
  server: string,
  model: GameModel,
  choice: SetupChoice,
): Promise<Local[]> {
  const { players, names, bots, params } = choice;
  const locals: Local[] = [];
  try {
    const created = await createRoom(server, {
      game: model.id,
      players,
      params,
      name: names[0]?.slice(0, 32) || "1",
    });
    const host = new GameClient({ server, name: names[0] ?? "1", token: created.token });
    await host.connect();
    host.sit(0);
    locals.push({ seat: 0, name: names[0] ?? "1", client: host });
    for (let seat = 1; seat < players; seat++) {
      if (bots[seat]) {
        host.setSeat(seat, "bot", { bot: bots[seat] ?? "random" });
        continue;
      }
      const name = names[seat]?.slice(0, 32) || String(seat + 1);
      const c = new GameClient({ server, name });
      await c.connect();
      await c.join(created.code, { seat });
      locals.push({ seat, name, client: c });
    }
    for (const l of locals) l.client.ready();
    return locals;
  } catch (e) {
    for (const l of locals) l.client.close();
    throw e;
  }
}

/** ¿Tiene el juego algo que no ven todos (variables, acciones o argumentos ocultos)? */
export function hasHiddenInformation(model: GameModel): boolean {
  const hidden = (v: unknown) => v !== undefined && v !== "all";
  if (model.ir.state.some((v) => hidden(v.visibility))) return true;
  const walk = (nodes: GameModel["ir"]["flow"]["nodes"]): boolean =>
    nodes.some(
      (n) =>
        (n.actions ?? []).some(
          (a) =>
            hidden((a as { visibility?: unknown }).visibility) ||
            (a.params ?? []).some((p) => hidden(p.visibility)),
        ) || walk(n.nodes ?? []),
    );
  return walk(model.ir.flow.nodes);
}

export function HotSeat(props: { server: string; game: string; customUis?: GameUiRegistry }) {
  const t = useMessages(messages);
  const { locale } = useLocale();
  const model = useLoaded(`${props.server}|${props.game}`, () =>
    loadGameModel(props.server, props.game),
  );
  const [locals, setLocals] = useState<Local[] | null>(null);
  useEffect(
    () => () => {
      for (const l of locals ?? []) l.client.close();
    },
    [locals],
  );
  if (model.error) return <p className="gh-shell-error">{t("error", { message: model.error })}</p>;
  if (!model.data) return <Spinner label={t("loading")} />;
  return (
    <div className="gh-shell-page">
      <h1>{t("localTitle", { game: pickText(model.data.title, locale) })}</h1>
      {locals === null ? (
        <Setup server={props.server} model={model.data} onStart={setLocals} />
      ) : (
        <LocalMatch model={model.data} locals={locals} customUis={props.customUis} />
      )}
    </div>
  );
}

function Setup(props: { server: string; model: GameModel; onStart: (locals: Local[]) => void }) {
  const t = useMessages(messages);
  const { min, max } = props.model.ir.players;
  const asked = Number(queryParam("players"));
  const [players, setPlayers] = useState(asked >= min && asked <= max ? asked : min);
  const [names, setNames] = useState<string[]>(() =>
    Array.from({ length: max }, (_, i) => t("playerName", { n: i + 1 })),
  );
  const [bots, setBots] = useState<(BotChoice | null)[]>(() =>
    Array.from({ length: max }, () => null),
  );
  const [params, setParams] = useState(() => defaultParams(props.model));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // MCTS y alfa-beta juegan viendo el estado entero: solo en juegos sin información oculta.
  const secret = useMemo(() => hasHiddenInformation(props.model), [props.model]);
  const thinking: BotChoice[] = secret
    ? ["greedy", "ismcts", "pimc"]
    : ["greedy", "mcts", "alphabeta"];

  const start = async () => {
    setBusy(true);
    setError(null);
    const choice = { players, names, bots, params };
    try {
      let locals: Local[];
      try {
        locals = await startInBrowser(props.model, choice);
      } catch (local) {
        // Lo que dice el motor (parámetros no válidos…) valdría igual en el servidor.
        if (local instanceof Error && local.name === "EngineError") throw local;
        // Sin el motor en el navegador, en el servidor.
        console.warn("partida local en el servidor:", local);
        locals = await startOnServer(props.server, props.model, choice);
      }
      props.onStart(locals);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };

  return (
    <div className="gh-shell-narrow">
      <p className="gh-muted">{t("localIntro")}</p>
      <Panel title={t("seats")}>
        <div className="gh-shell-form">
          {min !== max && (
            <Field label={t("seats")}>
              <select
                className="gh-select"
                value={players}
                onChange={(e) => setPlayers(Number(e.target.value))}
              >
                {Array.from({ length: max - min + 1 }, (_, i) => min + i).map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </Field>
          )}
          {Array.from({ length: players }, (_, seat) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: un campo por asiento.
            <div key={seat} className="gh-shell-row">
              <input
                className="gh-input gh-shell-grow"
                value={names[seat] ?? ""}
                maxLength={32}
                aria-label={t("playerName", { n: seat + 1 })}
                disabled={bots[seat] != null}
                onChange={(e) =>
                  setNames((all) => all.map((n, i) => (i === seat ? e.target.value : n)))
                }
              />
              {seat > 0 && (
                <label className="gh-shell-check">
                  <input
                    type="checkbox"
                    checked={bots[seat] != null}
                    onChange={(e) => {
                      const bot = e.target.checked ? "random" : null;
                      setBots((all) => all.map((b, i) => (i === seat ? bot : b)));
                    }}
                  />
                  {t("bot")}
                </label>
              )}
              {seat > 0 && bots[seat] != null && (
                <select
                  className="gh-select gh-shell-mini"
                  aria-label={t("botKind")}
                  value={bots[seat] ?? "random"}
                  onChange={(e) => {
                    const bot = e.target.value as BotChoice;
                    setBots((all) => all.map((b, i) => (i === seat ? bot : b)));
                  }}
                >
                  <option value="random">{t("botRandom")}</option>
                  {thinking.map((kind) => (
                    <option key={kind} value={kind}>
                      {t(
                        (
                          {
                            greedy: "botGreedy",
                            mcts: "botMcts",
                            alphabeta: "botAlphabeta",
                            ismcts: "botIsmcts",
                            pimc: "botPimc",
                          } as const
                        )[kind as Exclude<BotChoice, "random">],
                      )}
                    </option>
                  ))}
                </select>
              )}
            </div>
          ))}
        </div>
      </Panel>
      {props.model.params.length > 0 && (
        <Panel title={t("options")}>
          <ParamsForm model={props.model} values={params} onChange={setParams} />
        </Panel>
      )}
      {error && <p className="gh-shell-error">{t("error", { message: error })}</p>}
      <div className="gh-shell-row">
        <Button variant="primary" size="lg" disabled={busy} onClick={() => void start()}>
          {t("start")}
        </Button>
        <Button variant="ghost" onClick={() => navigate("/")}>
          {t("back")}
        </Button>
      </div>
    </div>
  );
}

/** Se vuelve a dibujar cuando cambia el estado de cualquiera de los clientes. */
function useClients(locals: Local[]): ClientState[] {
  const subscribe = useMemo(
    () => (listener: () => void) => {
      const stops = locals.map((l) => l.client.subscribe(listener));
      return () => {
        for (const stop of stops) stop();
      };
    },
    [locals],
  );
  const snapshot = useMemo(() => {
    let cache: ClientState[] = [];
    return () => {
      const next = locals.map((l) => l.client.getState());
      if (next.length !== cache.length || next.some((s, i) => s !== cache[i])) cache = next;
      return cache;
    };
  }, [locals]);
  return useSyncExternalStore(subscribe, snapshot, snapshot);
}

function LocalMatch(props: { model: GameModel; locals: Local[]; customUis?: GameUiRegistry }) {
  const t = useMessages(messages);
  const { locale } = useLocale();
  const { model, locals } = props;
  const states = useClients(locals);
  // Tapar la pantalla entre turnos solo tiene sentido si se la pasan varias personas.
  const secret = useMemo(
    () => locals.length > 1 && hasHiddenInformation(model),
    [model, locals.length],
  );
  const [revealed, setRevealed] = useState<number | null>(null);
  const first = states[0];
  const ended = first?.match?.end ?? null;
  // Quién juega ahora en esta pantalla: el primer asiento local con acciones y sin jugada pendiente.
  const turn = locals.findIndex((_, i) => {
    const s = states[i];
    return s !== undefined && legalOf(s) !== null && s.match?.pending === null;
  });
  const shown =
    turn >= 0
      ? turn
      : Math.max(
          0,
          locals.findIndex((l) => l.seat === revealed),
        );
  const local = locals[shown];
  const state = states[shown];
  useEffect(() => {
    if (!secret && turn >= 0) setRevealed(locals[turn]?.seat ?? null);
  }, [secret, turn, locals]);
  const match = state?.match;
  const update = match?.update;
  if (!local || !state || !match || !update) return <Spinner label={t("loading")} />;
  if (ended) {
    return (
      <div className="gh-shell-local">
        <AutoGame
          game={model}
          view={ended.view}
          seat={null}
          players={playersOf(state)}
          params={match.start.params}
          end={ended}
          log={first?.match?.log ?? []}
        />
        <div className="gh-shell-row">
          <Button
            variant="primary"
            onClick={() => {
              setRevealed(null);
              for (const l of locals) l.client.ready();
            }}
          >
            {t("playAgain")}
          </Button>
          <Button variant="ghost" onClick={() => navigate("/")}>
            {t("back")}
          </Button>
        </div>
      </div>
    );
  }
  if (secret && turn >= 0 && revealed !== local.seat) {
    return (
      <div className="gh-shell-privacy">
        <h2>{t("passDevice", { name: local.name })}</h2>
        <p className="gh-muted">{t("passDeviceText", { name: local.name })}</p>
        <Button variant="primary" size="lg" onClick={() => setRevealed(local.seat)}>
          {t("showMyTurn", { name: local.name })}
        </Button>
      </div>
    );
  }
  const Custom = props.customUis?.[model.id]?.component;
  const legal = legalOf(state);
  const common = {
    seat: local.seat,
    players: playersOf(state),
    legal,
    busy: match.pending !== null,
    rejected: match.rejected,
    log: match.log,
    clocks: update.clocks ?? null,
    params: match.start.params,
    end: null,
  };
  const act = (action: ActionData) => void local.client.act(action);
  const queryActions = (name?: string, args?: Record<string, unknown>) =>
    local.client.queryActions(name, args);
  return (
    <div className="gh-shell-local">
      <p className="gh-shell-local__who">
        {pickText(model.title, locale)} · {local.name}
      </p>
      {Custom ? (
        <Custom
          {...common}
          model={model}
          view={update.view}
          actions={legal?.kind === "enumerated" ? legal.actions : null}
          act={act}
          queryActions={queryActions}
          locale={locale}
        />
      ) : (
        <AutoGame
          {...common}
          game={model}
          view={update.view}
          onAct={act}
          queryActions={queryActions}
        />
      )}
    </div>
  );
}
