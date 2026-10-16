// SPDX-License-Identifier: Apache-2.0
/**
 * El simulador: jugar el juego que se diseña como cualquier asiento (o dejar que juegue solo),
 * ver lado a lado lo que ve cada asiento y la vista omnisciente, ir paso a paso hacia delante y
 * hacia atrás (viaje en el tiempo), elegir el azar y parar en puntos de ruptura.
 */

import { AutoGame, buildModel, eventText, type PlayerInfo } from "@gamehub/auto-ui";
import { plural, useLocale, useMessages } from "@gamehub/i18n";
import type { MatchEnd } from "@gamehub/protocol";
import { Badge, Button, cx } from "@gamehub/ui-kit";
import { useMemo, useState } from "react";
import { useStudio } from "../context";
import { messages } from "../messages";
import type { Policy } from "../store";
import type { GameModel } from "../types";

export function Simulator(props: { game: GameModel }) {
  const [state] = useStudio();
  const sim = state.sim;
  if (!sim) return <SimStart game={props.game} />;
  return <SimRunning />;
}

function SimStart(props: { game: GameModel }) {
  const t = useMessages(messages);
  const { locale } = useLocale();
  const errorCount = (problems: { severity: string }[]) => {
    const n = problems.filter((p) => p.severity === "error").length;
    return plural(locale, n, t("errorOne", { n }), t("errors", { n }));
  };
  const [state, studio] = useStudio();
  const range = props.game.players ?? { min: 2, max: 2 };
  const [players, setPlayers] = useState(range.min);
  const [seed, setSeed] = useState(0);
  const compiled = state.analysis?.compiled ?? false;
  return (
    <div className="gh-sd-sim gh-sd-sim--start">
      <div className="gh-sd-row">
        {range.max > range.min ? (
          <label className="gh-sd-inline">
            {t("players")}
            <input
              type="number"
              className="gh-sd-input"
              min={range.min}
              max={range.max}
              value={players}
              onChange={(e) => setPlayers(Number(e.target.value))}
            />
          </label>
        ) : null}
        <label className="gh-sd-inline">
          {t("seed")}
          <input
            type="number"
            className="gh-sd-input"
            value={seed}
            onChange={(e) => setSeed(Number(e.target.value))}
          />
        </label>
        <Button
          variant="primary"
          disabled={!compiled || state.busy}
          onClick={() => studio.startSim({ players, seed })}
        >
          ▶ {t("start")}
        </Button>
      </div>
      {!compiled ? (
        <p className="gh-sd-note">
          {state.analysis?.syntaxOk ? errorCount(state.analysis.problems) : t("syntaxErrors")}
        </p>
      ) : null}
    </div>
  );
}

function SimRunning() {
  const t = useMessages(messages);
  const { locale } = useLocale();
  const [state, studio] = useStudio();
  const sim = state.sim;
  const ir = sim?.ir;
  const model = useMemo(() => (ir ? buildModel(ir) : null), [ir]);
  if (!sim || !model) return null;
  const snap = sim.snapshot;
  const players: PlayerInfo[] = Array.from({ length: sim.players }, (_, s) => ({
    seat: s,
    name: t("seat", { n: s + 1 }),
    kind: sim.policies[s] === "human" ? "human" : "bot",
  }));
  const end =
    snap.status === "terminal"
      ? ({
          reason: "terminal",
          payoffs: snap.payoffs ?? null,
          ranking: snap.ranking ?? [],
          forfeited: [],
          view: snap.omniscient,
        } as unknown as MatchEnd)
      : null;
  const seatName = (s: number) => t("seat", { n: s + 1 });
  const lines = snap.allEvents
    .map((e) => eventText(e as never, { model, locale, seatName, nodes: true }))
    .filter((x): x is string => !!x);
  const message = sim.message;
  return (
    <div className="gh-sd-sim">
      <div className="gh-sd-sim__bar">
        <Button
          size="sm"
          title={t("first")}
          disabled={sim.running || snap.index === 0}
          onClick={() => studio.simGoto(0)}
        >
          ⏮
        </Button>
        <Button
          size="sm"
          title={t("back")}
          disabled={sim.running || snap.index === 0}
          onClick={() => studio.simGoto(snap.index - 1)}
        >
          ◀
        </Button>
        <Button
          size="sm"
          title={t("forward")}
          disabled={sim.running || snap.status === "terminal"}
          onClick={() =>
            snap.index < snap.length - 1 ? studio.simGoto(snap.index + 1) : studio.simRun(1)
          }
        >
          ▶
        </Button>
        <Button
          size="sm"
          variant="primary"
          title={t("run")}
          disabled={sim.running || snap.status === "terminal"}
          onClick={() => studio.simRun()}
        >
          ⏩ {t("run")}
        </Button>
        <input
          type="range"
          className="gh-sd-sim__timeline"
          aria-label={t("step")}
          min={0}
          max={Math.max(0, snap.length - 1)}
          value={snap.index}
          onChange={(e) => studio.simGoto(Number(e.target.value))}
        />
        <span className="gh-sd-muted">{t("stepOf", { i: snap.index, n: snap.length - 1 })}</span>
        <span className="gh-sd-spacer" />
        <Button size="sm" variant="ghost" onClick={() => studio.simReload()} disabled={sim.running}>
          ⟳ {t("reload")}
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={() =>
            studio.startSim({ players: sim.players, params: sim.params, seed: sim.seed })
          }
        >
          ↺ {t("restart")}
        </Button>
        <Button size="sm" variant="ghost" onClick={() => studio.stopSim()}>
          ✕
        </Button>
      </div>
      <div className="gh-sd-sim__status">
        <Badge
          tone={
            snap.status === "terminal" ? "success" : snap.status === "chance" ? "warning" : "accent"
          }
        >
          {snap.status === "terminal"
            ? t("terminal")
            : snap.status === "chance"
              ? t("chance")
              : snap.path.join(" › ") || "—"}
        </Badge>
        {snap.error ? (
          <span className="gh-sd-error">{t("ruleError", { message: snap.error.message })}</span>
        ) : null}
        {message ? <span className="gh-sd-muted">{describe(message, t)}</span> : null}
      </div>
      <div className="gh-sd-sim__seats">
        {players.map((p) => (
          <label
            key={p.seat}
            className={cx("gh-sd-seat", snap.active.includes(p.seat) && "is-active")}
          >
            <input
              type="checkbox"
              checked={sim.seats.includes(p.seat)}
              onChange={(e) =>
                studio.setSim({
                  seats: e.target.checked
                    ? [...sim.seats, p.seat].sort()
                    : sim.seats.filter((s) => s !== p.seat),
                })
              }
            />
            {p.name}
            <select
              className="gh-sd-input"
              aria-label={`${p.name}: política`}
              value={sim.policies[p.seat] ?? "human"}
              onChange={(e) =>
                studio.setSim({ policies: { ...sim.policies, [p.seat]: e.target.value as Policy } })
              }
            >
              <option value="human">{t("human")}</option>
              <option value="random">{t("random")}</option>
              <option value="first">{t("firstLegal")}</option>
            </select>
          </label>
        ))}
        <label className="gh-sd-seat">
          <input
            type="checkbox"
            checked={sim.omniscient}
            onChange={(e) => studio.setSim({ omniscient: e.target.checked })}
          />
          {t("omniscient")}
        </label>
      </div>
      {snap.status === "chance" ? <ChanceChooser /> : null}
      <div className="gh-sd-sim__views">
        {sim.omniscient ? (
          <section className="gh-sd-view">
            <h4>{t("omniscient")}</h4>
            <AutoGame
              game={model}
              view={snap.omniscient}
              seat={null}
              players={players}
              params={sim.params}
              end={end}
              showLog={false}
            />
          </section>
        ) : null}
        {sim.seats.map((seat) => {
          const legal = snap.legal[String(seat)];
          return (
            <section
              key={seat}
              className={cx("gh-sd-view", snap.active.includes(seat) && "is-active")}
            >
              <h4>{seatName(seat)}</h4>
              <AutoGame
                game={model}
                view={snap.views[String(seat)] ?? snap.public}
                seat={seat}
                players={players}
                legal={legal ?? null}
                busy={sim.running}
                params={sim.params}
                end={end}
                showLog={false}
                onAct={(action) => studio.simAct(seat, action)}
                queryActions={(name, args) =>
                  studio.connection.request<unknown[]>("gamehub/sim.options", {
                    session: sim.session,
                    index: snap.index,
                    seat,
                    name,
                    args,
                  })
                }
              />
            </section>
          );
        })}
      </div>
      <details className="gh-sd-sim__events" open>
        <summary>{t("events")}</summary>
        <ol>
          {lines.map((line, i) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: eventos de un paso, en orden.
            <li key={i}>{line}</li>
          ))}
        </ol>
      </details>
      <Conditions />
    </div>
  );
}

function describe(
  message: string,
  t: ReturnType<typeof useMessages<keyof (typeof messages)["es"]>>,
): string {
  if (message === "end") return t("stoppedEnd");
  if (message === "human") return t("stoppedHuman");
  if (message === "limit") return t("stoppedLimit");
  if (message.startsWith("breakpoint:"))
    return t("stoppedBreakpoint", { label: message.slice(11) });
  if (message.startsWith("reloaded:")) return t("reloaded", { n: message.slice(9) });
  return message;
}

function ChanceChooser() {
  const t = useMessages(messages);
  const [state, studio] = useStudio();
  const chance = state.sim?.snapshot.chance;
  return (
    <div className="gh-sd-chance">
      <span>{t("pickOutcome")}</span>
      <Button size="sm" variant="primary" onClick={() => studio.simChance()}>
        🎲 {t("randomOutcome")}
      </Button>
      {chance?.enumerable
        ? chance.outcomes?.slice(0, 60).map((o) => (
            <Button key={o.outcome.join(",")} size="sm" onClick={() => studio.simChance(o.outcome)}>
              [{o.outcome.join(", ")}] · {o.probability}
            </Button>
          ))
        : null}
    </div>
  );
}

function Conditions() {
  const t = useMessages(messages);
  const [state, studio] = useStudio();
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const add = async () => {
    if (!draft.trim() || !state.file) return;
    try {
      await studio.connection.request("gamehub/sim.condition", {
        uri: state.file.uri,
        expr: draft,
      });
      studio.setConditions([...state.conditions, draft]);
      setDraft("");
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <details className="gh-sd-sim__conditions">
      <summary>
        {t("conditions")} ({state.breakpoints.length + state.conditions.length})
      </summary>
      <ul>
        {state.breakpoints.map((b) => (
          <li key={`n:${b}`}>
            <code>at({b})</code>
            <button
              type="button"
              className="gh-sd-icon"
              onClick={() => studio.toggleBreakpoint(b)}
              aria-label={t("delete")}
            >
              ✕
            </button>
          </li>
        ))}
        {state.conditions.map((c, i) => (
          <li key={`c:${c}`}>
            <code>{c}</code>
            <button
              type="button"
              className="gh-sd-icon"
              aria-label={t("delete")}
              onClick={() => studio.setConditions(state.conditions.filter((_, j) => j !== i))}
            >
              ✕
            </button>
          </li>
        ))}
      </ul>
      <form
        className="gh-sd-row"
        onSubmit={(e) => {
          e.preventDefault();
          add();
        }}
      >
        <input
          className="gh-sd-input is-mono"
          placeholder={t("conditionHint")}
          aria-label={t("conditions")}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
        />
        <Button size="sm" type="submit">
          {t("add")}
        </Button>
      </form>
      {error ? <p className="gh-sd-field__error">{error}</p> : null}
    </details>
  );
}
