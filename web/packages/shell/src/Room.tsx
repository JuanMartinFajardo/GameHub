// SPDX-License-Identifier: Apache-2.0
/** Una sala: entrar, lobby (asientos, invitaciones, listo, configuración), partida y revancha. */

import { AutoGame, type GameModel, type PlayerInfo } from "@gamehub/auto-ui";
import { type ClientState, endpoints, type GameClient, legalOf } from "@gamehub/client";
import { pickText, useLocale, useMessages } from "@gamehub/i18n";
import { type ActionData, displayCode, type Room, type SeatInfo } from "@gamehub/protocol";
import { Badge, Button, Field, Panel, PlayerBadge, Spinner, seatColor } from "@gamehub/ui-kit";
import { type FormEvent, useEffect, useMemo, useState } from "react";
import {
  DEFAULT_SETTINGS,
  ParamsForm,
  SettingsForm,
  type SettingsValue,
  settingsPatch,
} from "./forms";
import { loadRoomModel, useLoaded } from "./games";
import type { GameUiRegistry } from "./gameui";
import { messages } from "./messages";
import { Link, navigate } from "./router";
import { savedName, useRoomConnection } from "./useRoom";

export function RoomPage(props: { server: string; code: string; customUis?: GameUiRegistry }) {
  const t = useMessages(messages);
  const conn = useRoomConnection(props.server, props.code);
  const model = useLoaded(
    conn.preview || conn.state.room ? `${props.server}|${props.code}` : null,
    () => loadRoomModel(props.server, props.code),
  );
  if (conn.missing) {
    return (
      <div className="gh-shell-page gh-shell-narrow">
        <p className="gh-shell-error">{t("roomMissing", { code: displayCode(props.code) })}</p>
        <Link to="/">{t("back")}</Link>
      </div>
    );
  }
  const { client, state } = conn;
  if (client === null || state.session === null) {
    if (conn.resuming) return <Spinner label={t("loading")} />;
    return (
      <JoinForm preview={conn.preview} model={model.data} error={conn.error} onJoin={conn.join} />
    );
  }
  if (state.room === null || model.data === null) return <Spinner label={t("loading")} />;
  return (
    <RoomView
      server={props.server}
      client={client}
      state={state}
      model={model.data}
      customUis={props.customUis}
      onLeave={() => {
        if (state.room?.status !== "running" || confirm(t("leaveConfirm"))) {
          conn.leave();
          navigate("/");
        }
      }}
      onReconnect={conn.reconnect}
    />
  );
}

function JoinForm(props: {
  preview: Room | null;
  model: GameModel | null;
  error: string | null;
  onJoin: (name: string, role: "player" | "spectator") => Promise<void>;
}) {
  const t = useMessages(messages);
  const { locale } = useLocale();
  const [name, setName] = useState(savedName);
  const [busy, setBusy] = useState(false);
  const room = props.preview;
  const go = async (role: "player" | "spectator") => {
    setBusy(true);
    await props.onJoin(name.trim() || "Anónimo", role);
    setBusy(false);
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    void go("player");
  };
  const free = room?.seats.some((s) => s.kind === "open") ?? true;
  return (
    <form className="gh-shell-page gh-shell-narrow" onSubmit={submit}>
      <h1>{props.model ? pickText(props.model.title, locale) : (room?.game.title ?? "…")}</h1>
      {room && <p className="gh-shell-code-big">{displayCode(room.code)}</p>}
      <Panel title={t("joinAs")}>
        <div className="gh-shell-form">
          <Field label={t("yourName")}>
            <input
              className="gh-input"
              value={name}
              maxLength={32}
              autoComplete="nickname"
              onChange={(e) => setName(e.target.value)}
            />
          </Field>
          <div className="gh-shell-row">
            <Button type="submit" variant="primary" disabled={busy || !free}>
              {t("play")}
            </Button>
            {room?.settings.spectators !== false && (
              <Button disabled={busy} onClick={() => void go("spectator")}>
                {t("watch")}
              </Button>
            )}
          </div>
          {props.error && (
            <p className="gh-shell-error">
              {props.error === "sessionLost"
                ? t("sessionLost")
                : t("error", { message: props.error })}
            </p>
          )}
        </div>
      </Panel>
    </form>
  );
}

function RoomView(props: {
  server: string;
  client: GameClient;
  state: ClientState;
  model: GameModel;
  customUis?: GameUiRegistry;
  onLeave: () => void;
  onReconnect: () => void;
}) {
  const t = useMessages(messages);
  const { locale } = useLocale();
  const { state, client, model } = props;
  const room = state.room as Room;
  const match = state.match;
  const playing = room.status === "running" && match?.update != null && match.end === null;
  return (
    <div className="gh-shell-room">
      <header className="gh-shell-room__bar">
        <strong>{pickText(model.title, locale)}</strong>
        <span className="gh-shell-code-chip">{displayCode(room.code)}</span>
        <ConnectionBadge state={state} onReconnect={props.onReconnect} />
        <span className="gh-shell-spacer" />
        {playing && state.session?.seat != null && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => confirm(t("resignConfirm")) && client.resign()}
          >
            {t("resign")}
          </Button>
        )}
        <Button variant="ghost" size="sm" onClick={props.onLeave}>
          {t("leave")}
        </Button>
      </header>
      <div className="gh-shell-room__main">
        <div className="gh-shell-room__game">
          {playing || (match?.end && room.status === "running") ? (
            <MatchArea client={client} state={state} model={model} customUis={props.customUis} />
          ) : (
            <Lobby server={props.server} client={client} state={state} model={model} />
          )}
        </div>
        <aside className="gh-shell-room__side">
          <Chat client={client} state={state} />
          {room.spectators.length > 0 && (
            <Panel title={t("spectatorsList")}>
              <ul className="gh-shell-list">
                {room.spectators.map((s) => (
                  <li key={s.participant}>
                    <PlayerBadge name={s.name} away={!s.connected} />
                    {s.host && <Badge>{t("host")}</Badge>}
                  </li>
                ))}
              </ul>
            </Panel>
          )}
        </aside>
      </div>
    </div>
  );
}

function ConnectionBadge(props: { state: ClientState; onReconnect: () => void }) {
  const t = useMessages(messages);
  const { state } = props;
  if (state.error?.code === "replaced") return <Badge tone="danger">{t("replaced")}</Badge>;
  if (state.status === "reconnecting") return <Badge tone="warning">{t("reconnecting")}</Badge>;
  if (state.status === "closed") {
    return (
      <span className="gh-shell-row">
        <Badge tone="danger">{t("disconnected")}</Badge>
        <Button size="sm" onClick={props.onReconnect}>
          {t("reconnect")}
        </Button>
      </span>
    );
  }
  return null;
}

// --- Lobby -------------------------------------------------------------------------------------

function Lobby(props: {
  server: string;
  client: GameClient;
  state: ClientState;
  model: GameModel;
}) {
  const t = useMessages(messages);
  const { client, state, model } = props;
  const room = state.room as Room;
  const me = state.session;
  const mySeat = room.seats.find((s) => s.participant === me?.participant);
  const host = me?.host ?? false;
  const end = state.match?.end ?? null;
  return (
    <div className="gh-shell-lobby">
      {end && <LastResult state={state} model={model} />}
      <Share server={props.server} code={room.code} />
      <Panel title={t("seats")}>
        <ul className="gh-shell-seats">
          {room.seats.map((seat) => (
            <SeatRow key={seat.seat} seat={seat} client={client} state={state} host={host} />
          ))}
        </ul>
        <div className="gh-shell-ready">
          {mySeat ? (
            <Button
              variant={mySeat.ready ? "secondary" : "primary"}
              size="lg"
              onClick={() => client.ready(!mySeat.ready)}
            >
              {mySeat.ready ? t("notReady") : end ? t("rematch") : t("ready")}
            </Button>
          ) : (
            <p className="gh-muted">{t("youAreSpectator")}</p>
          )}
          <p className="gh-muted">
            {end && mySeat?.ready ? t("rematchWaiting") : t("waitingPlayers")}
          </p>
        </div>
      </Panel>
      {host && <HostSettings client={client} room={room} model={model} />}
      <p className="gh-muted gh-shell-small" title={room.commitment}>
        {t("fairness")} · {t("commitmentOnly", { commitment: room.commitment.slice(0, 16) })}
      </p>
    </div>
  );
}

function SeatRow(props: { seat: SeatInfo; client: GameClient; state: ClientState; host: boolean }) {
  const t = useMessages(messages);
  const { seat, client, state, host } = props;
  const mine = seat.participant !== undefined && seat.participant === state.session?.participant;
  const color = seatColor(seat.seat);
  const name =
    seat.kind === "open"
      ? t("open")
      : seat.kind === "reserved"
        ? `${t("reserved")}: ${seat.name ?? ""}`
        : (seat.name ?? "?");
  return (
    <li className="gh-shell-seat">
      <span className="gh-shell-seat__n">{seat.seat + 1}</span>
      <PlayerBadge
        name={name}
        color={seat.kind === "open" ? undefined : color}
        you={mine}
        bot={seat.kind === "bot"}
        away={seat.kind === "human" && !seat.connected}
      />
      {seat.host && <Badge>{t("host")}</Badge>}
      {seat.ready && <Badge tone="success">✓</Badge>}
      <span className="gh-shell-spacer" />
      {seat.kind === "open" && !mine && (
        <Button size="sm" onClick={() => client.sit(seat.seat)}>
          {t("sitHere")}
        </Button>
      )}
      {mine && (
        <Button size="sm" variant="ghost" onClick={() => client.stand()}>
          {t("stand")}
        </Button>
      )}
      {host && seat.kind === "open" && (
        <Button
          size="sm"
          variant="ghost"
          onClick={() => client.setSeat(seat.seat, "bot", { bot: "random" })}
        >
          {t("makeBot")}
        </Button>
      )}
      {host && seat.kind === "bot" && (
        <Button size="sm" variant="ghost" onClick={() => client.setSeat(seat.seat, "open")}>
          {t("makeOpen")}
        </Button>
      )}
      {host && seat.kind === "human" && !mine && seat.participant && (
        <Button size="sm" variant="ghost" onClick={() => client.kick(seat.participant as string)}>
          {t("kick")}
        </Button>
      )}
    </li>
  );
}

function HostSettings(props: { client: GameClient; room: Room; model: GameModel }) {
  const t = useMessages(messages);
  const { client, room, model } = props;
  const [params, setParams] = useState<Record<string, unknown>>(room.params);
  const settings: SettingsValue = {
    ...DEFAULT_SETTINGS,
    clock: room.settings.clock,
    on_timeout: room.settings.on_timeout,
    spectators: room.settings.spectators,
    spectator_view: room.settings.spectator_view,
    private: room.settings.private,
  };
  useEffect(() => setParams(room.params), [room.params]);
  const { min, max } = model.ir.players;
  return (
    <Panel title={t("roomSettings")}>
      <div className="gh-shell-form">
        {min !== max && (
          <Field label={t("seats")}>
            <select
              className="gh-select"
              value={room.settings.players}
              onChange={(e) => client.configure({ players: Number(e.target.value) })}
            >
              {Array.from({ length: max - min + 1 }, (_, i) => min + i).map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </Field>
        )}
        {model.params.length > 0 && (
          <ParamsForm
            model={model}
            values={params}
            onChange={(next) => {
              setParams(next);
              client.configure({ params: next });
            }}
          />
        )}
        <SettingsForm
          value={settings}
          onChange={(next) => client.configure({ settings: settingsPatch(next) })}
        />
      </div>
    </Panel>
  );
}

function Share(props: { server: string; code: string }) {
  const t = useMessages(messages);
  const [copied, setCopied] = useState(false);
  const base = endpoints(props.server).http;
  const link = `${typeof location !== "undefined" && props.server === "" ? location.origin : base}/r/${props.code}`;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Sin portapapeles: el enlace está a la vista.
    }
  };
  return (
    <Panel title={t("share")}>
      <div className="gh-shell-share">
        <img
          className="gh-shell-qr"
          src={`${base}/api/v1/rooms/${props.code}/qr.svg`}
          alt={link}
          width={148}
          height={148}
        />
        <div className="gh-shell-share__text">
          <p className="gh-muted">{t("shareText")}</p>
          <p className="gh-shell-code-big">{displayCode(props.code)}</p>
          <p className="gh-shell-link">
            <a href={link}>{link}</a>
          </p>
          <Button size="sm" onClick={() => void copy()}>
            {copied ? t("copied") : t("copyLink")}
          </Button>
        </div>
      </div>
    </Panel>
  );
}

function LastResult(props: { state: ClientState; model: GameModel }) {
  const t = useMessages(messages);
  const match = props.state.match;
  if (!match?.end || !match.update) return null;
  return (
    <div className="gh-shell-last">
      <AutoGame
        game={props.model}
        view={match.end.view}
        seat={props.state.session?.seat ?? null}
        players={playersOf(props.state)}
        params={match.start.params}
        end={match.end}
        log={match.log}
      />
      <p>
        <Link to={`/replay/${match.end.replay}`}>{t("viewReplay")}</Link>
      </p>
    </div>
  );
}

export function playersOf(state: ClientState): PlayerInfo[] {
  const seats = state.match?.start.seats ?? [];
  return seats.map((s) => ({
    seat: s.seat,
    name: s.name,
    kind: s.kind,
    connected: state.room?.seats.find((x) => x.seat === s.seat)?.connected ?? true,
  }));
}

// --- Partida -----------------------------------------------------------------------------------

const UI_KEY = "gamehub:ui:";

function MatchArea(props: {
  client: GameClient;
  state: ClientState;
  model: GameModel;
  customUis?: GameUiRegistry;
}) {
  const t = useMessages(messages);
  const { locale } = useLocale();
  const { client, state, model } = props;
  const match = state.match;
  const custom = props.customUis?.[model.id];
  const [useCustom, setUseCustom] = useState(() => {
    try {
      return localStorage.getItem(UI_KEY + model.id) !== "generic";
    } catch {
      return true;
    }
  });
  const players = useMemo(() => playersOf(state), [state]);
  if (!match?.update) return <Spinner label={t("loading")} />;
  const legal = legalOf(state);
  const act = (action: ActionData) => void client.act(action);
  const queryActions = (name?: string, args?: Record<string, unknown>) =>
    client.queryActions(name, args);
  const common = {
    seat: state.session?.seat ?? null,
    players,
    legal,
    busy: match.pending !== null,
    rejected: match.rejected,
    log: match.log,
    clocks: match.update.clocks ?? null,
    params: match.start.params,
    end: match.end,
  };
  const toggle = (next: boolean) => {
    setUseCustom(next);
    try {
      localStorage.setItem(UI_KEY + model.id, next ? "custom" : "generic");
    } catch {
      // Dura lo que la pestaña.
    }
  };
  const Custom = custom?.component;
  return (
    <div className="gh-shell-match">
      {custom && (
        <div className="gh-shell-uiswitch">
          <Button size="sm" selected={useCustom} onClick={() => toggle(true)}>
            {t("customUi")}
          </Button>
          <Button size="sm" selected={!useCustom} onClick={() => toggle(false)}>
            {t("genericUi")}
          </Button>
        </div>
      )}
      {Custom && useCustom ? (
        <Custom
          {...common}
          model={model}
          view={match.update.view}
          actions={legal?.kind === "enumerated" ? legal.actions : null}
          act={act}
          queryActions={queryActions}
          locale={locale}
        />
      ) : (
        <AutoGame
          {...common}
          game={model}
          view={match.update.view}
          onAct={act}
          queryActions={queryActions}
        />
      )}
    </div>
  );
}

// --- Chat --------------------------------------------------------------------------------------

function Chat(props: { client: GameClient; state: ClientState }) {
  const t = useMessages(messages);
  const [text, setText] = useState("");
  const send = (e: FormEvent) => {
    e.preventDefault();
    const body = text.trim();
    if (body === "") return;
    props.client.chat(body.slice(0, 500));
    setText("");
  };
  return (
    <Panel title={t("chat")} className="gh-shell-chat">
      <ol className="gh-shell-chat__list">
        {props.state.chat.map((c, i) => (
          // biome-ignore lint/suspicious/noArrayIndexKey: mensajes en orden de llegada.
          <li key={i}>
            <strong>{c.sender.name}:</strong> {c.text}
          </li>
        ))}
      </ol>
      <form className="gh-shell-row" onSubmit={send}>
        <input
          className="gh-input gh-shell-grow"
          value={text}
          maxLength={500}
          placeholder={t("chatPlaceholder")}
          aria-label={t("chatPlaceholder")}
          onChange={(e) => setText(e.target.value)}
        />
        <Button type="submit" size="sm">
          {t("send")}
        </Button>
      </form>
    </Panel>
  );
}
