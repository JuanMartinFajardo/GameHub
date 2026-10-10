// SPDX-License-Identifier: Apache-2.0
/** La UI genérica: cualquier juego dibujado a partir de su IR, su vista y sus acciones legales. */

import type { LoggedEvent } from "@gamehub/client";
import { pickText, useLocale, useMessages } from "@gamehub/i18n";
import type { ActionData, Clocks, Legal, MatchEnd, View } from "@gamehub/protocol";
import {
  ActionBar,
  Badge,
  Button,
  Clock,
  cx,
  Panel,
  PlayerBadge,
  Scoreboard,
  Spinner,
  seatColor,
} from "@gamehub/ui-kit";
import { type ReactNode, useEffect, useMemo, useRef } from "react";
import { type Builder, useActionBuilder } from "./builder";
import { Auto, type AutoContext, useAuto } from "./context";
import { eventText } from "./events";
import { valueText } from "./format";
import { buildModel, type GameIr, type GameModel, type StateVarModel } from "./ir";
import { messages } from "./messages";
import { ValueView, VarWidget } from "./values";

export interface PlayerInfo {
  seat: number;
  name: string;
  kind?: "human" | "bot";
  connected?: boolean;
}

export interface AutoGameProps {
  /** La IR del juego (o el modelo ya analizado con `buildModel`). */
  game: GameIr | GameModel;
  view: View;
  /** El asiento de quien mira; null para un espectador. */
  seat: number | null;
  players: PlayerInfo[];
  /** Mis acciones legales (si me toca). */
  legal?: Legal | null;
  /** Hay una jugada enviada sin respuesta. */
  busy?: boolean;
  rejected?: { detail: string } | null;
  onAct?: (action: ActionData) => void;
  queryActions?: (name?: string, args?: Record<string, unknown>) => Promise<unknown[]>;
  log?: LoggedEvent[];
  clocks?: Clocks | null;
  /** Las opciones de la partida. */
  params?: Record<string, unknown>;
  end?: MatchEnd | null;
  /** Mostrar el registro de eventos (por defecto, sí). */
  showLog?: boolean;
  className?: string;
}

function isModel(game: GameIr | GameModel): game is GameModel {
  return "vars" in game && "nodes" in game && game.nodes instanceof Map;
}

export function AutoGame(props: AutoGameProps) {
  const { locale } = useLocale();
  const model = useMemo(
    () => (isModel(props.game) ? props.game : buildModel(props.game)),
    [props.game],
  );
  const names = useMemo(() => new Map(props.players.map((p) => [p.seat, p.name])), [props.players]);
  const ctx: AutoContext = useMemo(
    () => ({
      model,
      locale,
      seat: props.seat,
      seatName: (s) =>
        names.get(s) ?? (model.seatNames?.[s] ? pickText(model.seatNames[s], locale) : `#${s + 1}`),
      seatColor: (s) => seatColor(s, model.seatColors),
      params: props.params ?? {},
    }),
    [model, locale, props.seat, names, props.params],
  );
  const builder = useActionBuilder({
    model,
    view: props.view,
    seat: props.seat,
    legal: props.legal ?? null,
    params: props.params ?? {},
    onAct: props.onAct,
    queryActions: props.queryActions,
    busy: props.busy,
  });
  return (
    <Auto.Provider value={ctx}>
      <div className={cx("gh-auto", props.className)}>
        <TopBar view={props.view} builder={builder} end={props.end ?? null} />
        <div className="gh-auto__main">
          <TableArea view={props.view} builder={builder} />
          <SeatsArea
            view={props.view}
            builder={builder}
            players={props.players}
            clocks={props.clocks ?? null}
            end={props.end ?? null}
          />
        </div>
        {props.end ? (
          <ResultView end={props.end} players={props.players} />
        ) : (
          <ActionPanel
            builder={builder}
            busy={props.busy ?? false}
            rejected={props.rejected ?? null}
          />
        )}
        {(props.showLog ?? true) && props.log !== undefined && <EventLog log={props.log} />}
      </div>
    </Auto.Provider>
  );
}

// --- Barra de estado ---------------------------------------------------------------------------

function TopBar(props: { view: View; builder: Builder; end: MatchEnd | null }) {
  const ctx = useAuto();
  const t = useMessages(messages);
  const { view } = props;
  const node = view.node ? ctx.model.nodes.get(view.node) : undefined;
  const responded = new Set(view.responded ?? []);
  const waiting = view.active.filter((s) => !responded.has(s));
  let status: ReactNode;
  if (props.end || view.status === "terminal") status = <Badge>{t("finished")}</Badge>;
  else if (view.status === "chance") status = <Badge>{t("chance")}</Badge>;
  else if (ctx.seat !== null && waiting.includes(ctx.seat)) {
    status = (
      <Badge tone="accent">
        {node?.kind === "simultaneous" ? t("yourTurnSimultaneous") : t("yourTurn")}
      </Badge>
    );
  } else {
    const names = waiting.map(ctx.seatName).join(", ");
    status = (
      <Badge>
        {node?.kind === "decision" ? t("turnOf", { names }) : t("waitingFor", { names })}
      </Badge>
    );
  }
  const top = ctx.model.vars.filter((v) => v.place === "top" && v.widget !== "hidden");
  return (
    <header className="gh-auto__top">
      <div className="gh-auto__title">
        <strong>{pickText(ctx.model.title, ctx.locale)}</strong>
        {node && <span className="gh-muted">{pickText(node.label, ctx.locale)}</span>}
      </div>
      <div className="gh-auto__status">{status}</div>
      {top.length > 0 && (
        <div className="gh-auto__vars">
          {top.map((v) => (
            <span key={v.name} className="gh-auto__var-chip">
              <span className="gh-muted">{pickText(v.label, ctx.locale)}</span>{" "}
              <ValueView type={v.type} value={view.state[v.name]} />
            </span>
          ))}
        </div>
      )}
    </header>
  );
}

// --- Mesa y asientos ---------------------------------------------------------------------------

function visible(v: StateVarModel): boolean {
  return v.widget !== "hidden" && !v.secret;
}

function TableArea(props: { view: View; builder: Builder }) {
  const ctx = useAuto();
  const vars = ctx.model.vars.filter((v) => v.place === "table" && visible(v));
  if (vars.length === 0) return null;
  const boards = vars.filter((v) => v.widget === "grid");
  const rest = vars.filter((v) => v.widget !== "grid");
  return (
    <section className="gh-auto__table" aria-label={pickText(ctx.model.title, ctx.locale)}>
      {boards.map((v) => (
        <div key={v.name} className="gh-auto__board">
          <VarWidget v={v} value={props.view.state[v.name]} grid={props.builder.grid(v.name)} />
        </div>
      ))}
      {rest.length > 0 && (
        <div className="gh-auto__items">
          {rest.map((v) => (
            <div key={v.name} className="gh-auto__item">
              {v.widget !== "counter" && (
                <span className="gh-auto__label">{pickText(v.label, ctx.locale)}</span>
              )}
              <VarWidget
                v={v}
                value={props.view.state[v.name]}
                grid={props.builder.grid(v.name)}
                pick={props.builder.pick(v.name, null)}
              />
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function SeatsArea(props: {
  view: View;
  builder: Builder;
  players: PlayerInfo[];
  clocks: Clocks | null;
  end: MatchEnd | null;
}) {
  const ctx = useAuto();
  const vars = ctx.model.vars.filter((v) => v.place === "seats" && visible(v));
  const seats = props.players.map((p) => p.seat).sort((a, b) => a - b);
  // Quien juega, primero.
  const ordered = ctx.seat === null ? seats : [ctx.seat, ...seats.filter((s) => s !== ctx.seat)];
  const active = new Set(props.view.active);
  return (
    <section className="gh-auto__seats">
      {ordered.map((s) => {
        const player = props.players.find((p) => p.seat === s);
        const clock = props.clocks;
        const ms = clock?.remaining_ms[s];
        const rank = props.end?.ranking[s];
        return (
          <Panel
            key={s}
            className={cx("gh-auto__seat", active.has(s) && "gh-auto__seat--active")}
            title={
              <PlayerBadge
                name={ctx.seatName(s)}
                color={ctx.seatColor(s)}
                active={active.has(s) && !props.end}
                you={s === ctx.seat}
                bot={player?.kind === "bot"}
                away={player?.connected === false}
              />
            }
            actions={
              <span className="gh-auto__seat-extra">
                {rank !== undefined && (
                  <Badge tone={rank === 1 ? "success" : "neutral"}>#{rank}</Badge>
                )}
                {ms !== undefined && ms !== null && (
                  <Clock ms={ms} running={clock?.running.includes(s) ?? false} />
                )}
              </span>
            }
          >
            {vars.length === 0 ? null : (
              <div className="gh-auto__seat-vars">
                {vars.map((v) => {
                  const all = props.view.state[v.name];
                  const value = Array.isArray(all) ? all[s] : all;
                  return (
                    <div key={v.name} className="gh-auto__item">
                      {v.widget !== "counter" && (
                        <span className="gh-auto__label">{pickText(v.label, ctx.locale)}</span>
                      )}
                      <VarWidget
                        v={v}
                        value={value}
                        compact={false}
                        grid={null}
                        pick={props.builder.pick(v.name, s)}
                      />
                    </div>
                  );
                })}
              </div>
            )}
          </Panel>
        );
      })}
    </section>
  );
}

// --- Acciones ----------------------------------------------------------------------------------

function ActionPanel(props: {
  builder: Builder;
  busy: boolean;
  rejected: { detail: string } | null;
}) {
  const ctx = useAuto();
  const t = useMessages(messages);
  const b = props.builder;
  if (props.busy) {
    return (
      <ActionBar sticky>
        <Spinner />
        <span>{t("sending")}</span>
      </ActionBar>
    );
  }
  if (!b.ready) {
    return props.rejected ? (
      <ActionBar sticky>
        <Badge tone="danger">{t("rejected", { detail: props.rejected.detail })}</Badge>
      </ActionBar>
    ) : null;
  }
  const label = (name: string, fallback: string) =>
    name === "pass" ? t("pass") : pickText(fallback, ctx.locale);
  const zoneLabel = (name: string) => {
    const v = ctx.model.vars.find((x) => x.name === name);
    return v ? pickText(v.label, ctx.locale) : name;
  };
  const step = b.step;
  let hint: string | null = null;
  if (step?.kind === "board") {
    hint =
      step.input === "cell"
        ? t("chooseCell")
        : step.input === "column"
          ? t("chooseColumn")
          : t("chooseRow");
  } else if (step?.kind === "pick") {
    const [lo, hi] = b.pickRange ?? [undefined, undefined];
    hint = step.many
      ? t("chooseMany", {
          zone: zoneLabel(step.zone),
          range:
            lo !== undefined && hi !== undefined
              ? `${lo}–${hi}`
              : lo !== undefined
                ? `≥ ${lo}`
                : "…",
          action: label(step.action.name, step.action.label as string),
        })
      : t("chooseFrom", { zone: zoneLabel(step.zone) });
  }
  return (
    <ActionBar sticky>
      {props.rejected && (
        <Badge tone="danger">{t("rejected", { detail: props.rejected.detail })}</Badge>
      )}
      {b.chosen && b.current && b.current.input.kind === "choice" ? (
        <ChoiceStep builder={b} />
      ) : (
        <>
          {hint && <span className="gh-auto__hint">{hint}</span>}
          {b.actions
            .filter(
              (a) =>
                a !== b.pickAction &&
                (a.params.length === 0 || a.params[0]?.input.kind === "choice"),
            )
            .map((a) => (
              <Button
                key={a.name}
                variant={a.params.length === 0 ? "primary" : "secondary"}
                data-gh-act=""
                onClick={() => b.choose(a.name)}
              >
                {label(a.name, a.label as string)}
                {a.params.length > 0 && "…"}
              </Button>
            ))}
          {b.pickAction && (
            <Button
              variant="primary"
              disabled={!b.pickValid}
              data-gh-confirm=""
              onClick={b.confirmPick}
            >
              {label(b.pickAction.name, b.pickAction.label as string)}
              {b.picked.length > 0 && ` (${b.picked.length})`}
            </Button>
          )}
          {b.chosen && (
            <Button variant="ghost" onClick={b.cancel}>
              {t("cancel")}
            </Button>
          )}
        </>
      )}
    </ActionBar>
  );
}

const MANY = 16;

function ChoiceStep(props: { builder: Builder }) {
  const ctx = useAuto();
  const t = useMessages(messages);
  const b = props.builder;
  const param = b.current;
  const action = b.chosen;
  if (!param || !action) return null;
  const candidates = b.candidates;
  const actionLabel = action.name === "pass" ? t("pass") : pickText(action.label, ctx.locale);
  const chosen = action.params
    .filter((p) => p.name in b.args)
    .map((p) => valueText(ctx.model, b.args[p.name], ctx.locale, ctx.seatName, p.type));
  return (
    <>
      <span className="gh-auto__hint">
        <strong>{actionLabel}</strong>
        {chosen.length > 0 && ` (${chosen.join(", ")})`} · {pickText(param.label, ctx.locale)}:
      </span>
      {candidates === null ? (
        <Spinner label={t("loading")} />
      ) : candidates.length > MANY ? (
        <select
          className="gh-select"
          aria-label={pickText(param.label, ctx.locale)}
          data-gh-choice=""
          defaultValue=""
          onChange={(e) => {
            const index = Number(e.target.value);
            if (Number.isInteger(index) && index >= 0) b.setValue(candidates[index]);
          }}
        >
          <option value="" disabled>
            …
          </option>
          {candidates.map((c, i) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: el índice es el valor de la opción.
            <option key={i} value={i}>
              {valueText(ctx.model, c, ctx.locale, ctx.seatName, param.type)}
            </option>
          ))}
        </select>
      ) : (
        candidates.map((c, i) => (
          <Button
            // biome-ignore lint/suspicious/noArrayIndexKey: candidatos en orden fijo.
            key={i}
            data-gh-choice=""
            onClick={() => b.setValue(c)}
          >
            <ValueView type={param.type} value={c} size="sm" />
          </Button>
        ))
      )}
      <span className="gh-actionbar__spacer" />
      <Button variant="ghost" onClick={b.cancel}>
        {t("cancel")}
      </Button>
    </>
  );
}

// --- Registro y resultado ----------------------------------------------------------------------

export function EventLog(props: { log: LoggedEvent[]; nodes?: boolean; limit?: number }) {
  const ctx = useAuto();
  const t = useMessages(messages);
  const end = useRef<HTMLLIElement | null>(null);
  const lines = actionsFirst(props.log)
    .map((e, i) => ({
      key: i,
      seq: e.seq,
      text: eventText(e.event, {
        model: ctx.model,
        locale: ctx.locale,
        seatName: ctx.seatName,
        nodes: props.nodes,
      }),
    }))
    .filter((x): x is { key: number; seq: number; text: string } => x.text !== null)
    .slice(-(props.limit ?? 200));
  useEffect(() => {
    end.current?.scrollIntoView?.({ block: "nearest" });
  });
  return (
    <Panel title={t("log")} className="gh-auto__log">
      <ol className="gh-auto__log-list">
        {lines.map((line, i) => (
          <li key={line.key} ref={i === lines.length - 1 ? end : undefined}>
            {line.text}
          </li>
        ))}
      </ol>
    </Panel>
  );
}

export function ResultView(props: { end: MatchEnd; players: PlayerInfo[] }) {
  const ctx = useAuto();
  const t = useMessages(messages);
  const { end } = props;
  const seats = props.players
    .map((p) => p.seat)
    .sort((a, b) => (end.ranking[a] ?? 99) - (end.ranking[b] ?? 99));
  const reason =
    end.reason === "terminal"
      ? t("reasonTerminal")
      : end.reason === "forfeit"
        ? t("reasonForfeit")
        : t("reasonAborted");
  return (
    <Panel title={t("result")} className="gh-auto__result">
      <p className="gh-muted">{reason}</p>
      <Scoreboard
        columns={[t("player"), t("rank"), t("payoff")]}
        rows={seats.map((s) => ({
          name: ctx.seatName(s),
          color: ctx.seatColor(s),
          highlight: s === ctx.seat,
          values: [`#${end.ranking[s] ?? "?"}`, end.payoffs?.[s] ?? "—"],
        }))}
      />
    </Panel>
  );
}

/** En cada actualización, la jugada antes que lo que provoca (el motor emite primero los
 * efectos, como lo que se revela, y después la propia acción). */
function actionsFirst(log: LoggedEvent[]): LoggedEvent[] {
  const out: LoggedEvent[] = [];
  let group: LoggedEvent[] = [];
  const flush = () => {
    const actions = group.filter((e) => e.event.type === "action");
    const rest = group.filter((e) => e.event.type !== "action");
    // Un único jugador en el paso: su jugada va delante de sus efectos.
    out.push(...(actions.length === 1 ? [...actions, ...rest] : group));
    group = [];
  };
  for (const entry of log) {
    if (group.length > 0 && group[0]?.seq !== entry.seq) flush();
    group.push(entry);
  }
  flush();
  return out;
}
