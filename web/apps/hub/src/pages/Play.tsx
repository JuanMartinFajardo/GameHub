// SPDX-License-Identifier: AGPL-3.0-or-later
/** Jugar a una versión publicada: crear una sala (y compartir el código) o buscar partida con
 * el emparejamiento del hub (partidas puntuables entre personas con cuenta). */

import { saveSession } from "@gamehub/client";
import { useMessages } from "@gamehub/i18n";
import { Link, NewRoom, navigate } from "@gamehub/shell";
import { Button, Field, Panel, Spinner } from "@gamehub/ui-kit";
import { useEffect, useState } from "react";
import { api, errorText, get, post, type Release, type Ticket } from "../api";
import { messages } from "../messages";
import type { PlayMode } from "../routes";
import { useSession } from "../session";
import { Loading, useLoad } from "../ui";

type PlayRoute = { owner: string; name: string; version: string | null; mode: PlayMode };

export function PlayPage(props: { route: PlayRoute }) {
  const t = useMessages(messages);
  const full = `${props.route.owner}/${props.route.name}`;
  const release = useLoad(`${full}@${props.route.version ?? "latest"}`, () =>
    get<Release>(`/repos/${full}/releases/${props.route.version ?? "latest"}`),
  );
  if (!release.data) return <Loading error={release.error} />;
  const r = release.data;
  return (
    <div className="gh-shell-page">
      <p className="gh-muted">
        <Link to={`/${full}`}>{full}</Link> · v{r.version} ·{" "}
        {props.route.mode === "match" ? (
          <Link to={`/${full}/play${props.route.version ? `?version=${r.version}` : ""}`}>
            {t("createRoomInstead")}
          </Link>
        ) : (
          <Link to={`/${full}/match`}>{t("findMatch")}</Link>
        )}
      </p>
      {props.route.mode === "match" ? (
        <Matchmaking release={r} />
      ) : (
        <NewRoom server="" game={r.ref} />
      )}
    </div>
  );
}

function Matchmaking(props: { release: Release }) {
  const t = useMessages(messages);
  const { user } = useSession();
  const r = props.release;
  const min = r.properties.players?.min ?? 2;
  const max = r.properties.players?.max ?? min;
  const [players, setPlayers] = useState(min);
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ticket || ticket.status === "matched") return;
    const timer = setInterval(() => {
      get<Ticket>(`/matchmaking/${ticket.id}`).then(setTicket, (e: unknown) =>
        setError(errorText(e)),
      );
    }, 1000);
    return () => clearInterval(timer);
  }, [ticket]);

  useEffect(() => {
    if (ticket?.status === "matched" && ticket.room && ticket.token && user) {
      saveSession("", ticket.room, ticket.token, user.display || user.name);
      navigate(`/r/${ticket.room}`);
    }
  }, [ticket, user]);

  if (!user) {
    return (
      <Panel title={t("findMatch")}>
        <p>{t("matchNeedsAccount")}</p>
        <Link to={`/login?next=${encodeURIComponent(location.pathname)}`}>{t("login")}</Link>
      </Panel>
    );
  }
  return (
    <Panel title={`${t("findMatch")} · ${r.title || r.repo}`}>
      <p className="gh-muted">{t("matchHelp")}</p>
      {ticket ? (
        <div className="hub-waiting">
          <Spinner label={t("waitingPlayers")} />
          <p>{t("waitingFor", { n: ticket.waiting, total: ticket.players })}</p>
          <Button
            onClick={() =>
              api("DELETE", `/matchmaking/${ticket.id}`)
                .then(() => setTicket(null))
                .catch((e: unknown) => setError(errorText(e)))
            }
          >
            {t("cancel")}
          </Button>
        </div>
      ) : (
        <>
          {max > min && (
            <Field label={t("players")}>
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
          <Button
            variant="primary"
            onClick={() =>
              post<Ticket>("/matchmaking", { game: r.ref, players }).then(setTicket, (e: unknown) =>
                setError(errorText(e)),
              )
            }
          >
            {t("searchMatch")}
          </Button>
        </>
      )}
      {error && <p className="gh-shell-error">{error}</p>}
    </Panel>
  );
}
