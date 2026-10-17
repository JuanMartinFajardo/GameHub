// SPDX-License-Identifier: Apache-2.0
/** Inicio: entrar con un código, crear salas, salas abiertas y partidas recientes. */

import type { GameModel } from "@gamehub/auto-ui";
import { listMatches, listRooms, type MatchListing } from "@gamehub/client";
import { pickText, useLocale, useMessages } from "@gamehub/i18n";
import { displayCode, type GameInfo, normalizeCode, type Room } from "@gamehub/protocol";
import { Badge, Button, Panel, Spinner } from "@gamehub/ui-kit";
import { type FormEvent, useEffect, useState } from "react";
import { loadGameModel, loadServerInfo, useLoaded } from "./games";
import { messages } from "./messages";
import { Link, navigate } from "./router";
import { tagText } from "./tags";

export function Home(props: { server: string; only?: string }) {
  const t = useMessages(messages);
  const info = useLoaded(`info|${props.server}`, () => loadServerInfo(props.server));
  const games = (info.data?.games ?? []).filter(
    (g) => props.only === undefined || g.id === props.only,
  );
  // Sin servidor de partidas (una exportación estática): solo se juega en este dispositivo.
  const offline = info.data?.offline === true;
  return (
    <div className="gh-shell-home">
      <section className="gh-shell-hero">
        <div>
          <h1>{t("heroTitle")}</h1>
          <p className="gh-muted">{offline ? t("heroOffline") : t("heroText")}</p>
        </div>
        {!offline && <JoinBox />}
      </section>
      {info.error && <p className="gh-shell-error">{t("serverUnreachable")}</p>}
      <section>
        <h2 className="gh-shell-h2">{t("games")}</h2>
        {info.data === null && info.error === null && <Spinner label={t("loading")} />}
        <div className="gh-shell-games">
          {games.map((g) => (
            <GameCard key={g.id} server={props.server} game={g} offline={offline} />
          ))}
        </div>
      </section>
      {!offline && (
        <div className="gh-shell-columns">
          <OpenRooms server={props.server} />
          <RecentMatches server={props.server} games={info.data?.games ?? []} />
        </div>
      )}
    </div>
  );
}

function JoinBox() {
  const t = useMessages(messages);
  const [text, setText] = useState("");
  const [bad, setBad] = useState(false);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const code = normalizeCode(text);
    if (code === null) {
      setBad(true);
      return;
    }
    navigate(`/r/${code}`);
  };
  return (
    <form className="gh-shell-join" onSubmit={submit}>
      <h2 className="gh-shell-h2">{t("joinTitle")}</h2>
      <div className="gh-shell-row">
        <input
          className="gh-input gh-shell-code-input"
          value={text}
          placeholder={t("codePlaceholder")}
          aria-label={t("codePlaceholder")}
          autoCapitalize="characters"
          autoComplete="off"
          spellCheck={false}
          onChange={(e) => {
            setText(e.target.value);
            setBad(false);
          }}
        />
        <Button type="submit" variant="primary">
          {t("enter")}
        </Button>
      </div>
      {bad && <p className="gh-shell-error">{t("badCode")}</p>}
    </form>
  );
}

function GameCard(props: { server: string; game: GameInfo; offline: boolean }) {
  const t = useMessages(messages);
  const { locale } = useLocale();
  const [model, setModel] = useState<GameModel | null>(null);
  useEffect(() => {
    let live = true;
    loadGameModel(props.server, props.game.id).then(
      (m) => live && setModel(m),
      () => {},
    );
    return () => {
      live = false;
    };
  }, [props.server, props.game.id]);
  const { min, max } = props.game.players;
  const title = model ? pickText(model.title, locale) : props.game.title;
  const tags = model?.ir.meta?.tags ?? [];
  return (
    <article className="gh-shell-game">
      <header>
        <h3>{title}</h3>
        <Badge>{min === max ? t("playersOne", { n: min }) : t("players", { min, max })}</Badge>
      </header>
      {model?.description !== undefined && (
        <p className="gh-shell-game__text">{pickText(model.description, locale)}</p>
      )}
      {tags.length > 0 && (
        <p className="gh-shell-tags">
          {tags.slice(0, 4).map((tag) => (
            <span key={tag} className="gh-shell-tag">
              {tagText(tag, locale)}
            </span>
          ))}
        </p>
      )}
      <footer>
        {!props.offline && (
          <Button variant="primary" onClick={() => navigate(`/new/${props.game.id}`)}>
            {t("createRoom")}
          </Button>
        )}
        <Button
          variant={props.offline ? "primary" : "ghost"}
          onClick={() => navigate(`/local/${props.game.id}`)}
        >
          {t("playHere")}
        </Button>
      </footer>
    </article>
  );
}

function useRefreshing<T>(load: () => Promise<T>, every: number): T | null {
  const [data, setData] = useState<T | null>(null);
  // biome-ignore lint/correctness/useExhaustiveDependencies: se refresca con el intervalo.
  useEffect(() => {
    let live = true;
    const run = () =>
      load().then(
        (d) => live && setData(d),
        () => {},
      );
    void run();
    const timer = setInterval(run, every);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, [every]);
  return data;
}

function OpenRooms(props: { server: string }) {
  const t = useMessages(messages);
  const rooms = useRefreshing(() => listRooms(props.server).then((r) => r.rooms), 5000);
  return (
    <Panel title={t("openRooms")}>
      {rooms === null ? (
        <Spinner label={t("loading")} />
      ) : rooms.length === 0 ? (
        <p className="gh-muted">{t("noRooms")}</p>
      ) : (
        <ul className="gh-shell-list">
          {rooms.map((room) => (
            <RoomRow key={room.code} room={room} />
          ))}
        </ul>
      )}
    </Panel>
  );
}

function RoomRow(props: { room: Room }) {
  const t = useMessages(messages);
  const { room } = props;
  const free = room.seats.filter((s) => s.kind === "open" || s.kind === "reserved").length;
  return (
    <li>
      <Link to={`/r/${room.code}`} className="gh-shell-code-link">
        {displayCode(room.code)}
      </Link>
      <span>{room.game.title}</span>
      <span className="gh-muted">
        {room.status === "running" ? t("roomStatusRunning") : t("roomStatusLobby")}
        {room.status === "lobby" && free > 0 && ` · ${t("seatsFree", { n: free })}`}
      </span>
    </li>
  );
}

function RecentMatches(props: { server: string; games: GameInfo[] }) {
  const t = useMessages(messages);
  const matches = useRefreshing(() => listMatches(props.server), 15000);
  return (
    <Panel title={t("recentMatches")}>
      {matches === null ? (
        <Spinner label={t("loading")} />
      ) : matches.length === 0 ? (
        <p className="gh-muted">{t("noMatches")}</p>
      ) : (
        <ul className="gh-shell-list">
          {matches.slice(0, 12).map((m) => (
            <MatchRow
              key={m.id}
              match={m}
              title={props.games.find((g) => g.id === m.game.id)?.title ?? m.game.id}
            />
          ))}
        </ul>
      )}
    </Panel>
  );
}

function MatchRow(props: { match: MatchListing; title: string }) {
  const t = useMessages(messages);
  const { match } = props;
  const winners = match.players.filter((_, seat) => match.ranking?.[seat] === 1).map((p) => p.name);
  return (
    <li>
      <span>{props.title}</span>
      <span className="gh-muted">
        {match.players.map((p) => p.name).join(", ")}
        {winners.length > 0 && ` · 🏆 ${winners.join(", ")}`}
      </span>
      <Link to={`/replay/${match.id}`}>{t("watchReplay")}</Link>
    </li>
  );
}
