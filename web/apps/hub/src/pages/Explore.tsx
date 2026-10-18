// SPDX-License-Identifier: AGPL-3.0-or-later
/** Inicio y explorar: búsqueda por texto y por propiedades matemáticas, populares, recientes. */

import { useMessages } from "@gamehub/i18n";
import { Link, navigate } from "@gamehub/shell";
import { Button, Field, Panel } from "@gamehub/ui-kit";
import { type FormEvent, useState } from "react";
import { get, type HubEvent, type MatchRecord, query, type Repo } from "../api";
import { messages } from "../messages";
import { useSession } from "../session";
import { EventList, Loading, RepoCard, useLoad, When } from "../ui";

interface ExploreData {
  popular: Repo[];
  recent: Repo[];
  events: HubEvent[];
  matches: MatchRecord[];
}

export function HomePage() {
  const t = useMessages(messages);
  const { user, info } = useSession();
  const data = useLoad("home", () => get<ExploreData>("/explore"));
  return (
    <div className="gh-shell-page">
      <section className="hub-hero">
        <h1>{t("heroTitle")}</h1>
        <p>{t("heroText")}</p>
        <p className="hub-hero__actions">
          <Button variant="primary" onClick={() => navigate("/explore")}>
            {t("exploreGames")}
          </Button>
          {user ? (
            <Button onClick={() => navigate("/new")}>{t("newRepo")}</Button>
          ) : (
            info?.signup !== false && (
              <Button onClick={() => navigate("/signup")}>{t("signup")}</Button>
            )
          )}
        </p>
      </section>
      {data.data ? (
        <div className="hub-columns">
          <div>
            <h2 className="gh-shell-h2">{t("popular")}</h2>
            <div className="hub-grid">
              {data.data.popular.map((r) => (
                <RepoCard key={r.full_name} repo={r} />
              ))}
              {!data.data.popular.length && <p className="gh-muted">{t("noRepos")}</p>}
            </div>
            <h2 className="gh-shell-h2">{t("recent")}</h2>
            <div className="hub-grid">
              {data.data.recent.map((r) => (
                <RepoCard key={r.full_name} repo={r} />
              ))}
            </div>
          </div>
          <aside>
            <Panel title={t("activity")}>
              <EventList events={data.data.events} showRepo />
            </Panel>
            <Panel title={t("recentMatches")}>
              <MatchList matches={data.data.matches} />
            </Panel>
          </aside>
        </div>
      ) : (
        <Loading error={data.error} />
      )}
    </div>
  );
}

export function MatchList(props: { matches: MatchRecord[] }) {
  const t = useMessages(messages);
  if (!props.matches.length) return <p className="gh-muted">{t("noMatches")}</p>;
  return (
    <ul className="hub-events">
      {props.matches.map((m) => (
        <li key={m.id}>
          <Link to={`/${m.game.split("@")[0]}`}>{m.game}</Link>:{" "}
          {m.players
            .map((p, i) => `${p.account ?? p.name}${m.result.ranking[i] === 1 ? " 🏆" : ""}`)
            .join(" · ")}{" "}
          {m.rated && <span className="gh-muted">({t("rated")})</span>}{" "}
          <span className="gh-muted">
            <When time={m.created} />
          </span>{" "}
          <Link to={`/replay/${m.id}`}>{t("watch")}</Link>
        </li>
      ))}
    </ul>
  );
}

interface SearchResult {
  total: number;
  filters: Record<string, unknown>;
  text: string;
  results: Repo[];
}

type Tri = "" | "1" | "0";

export function ExplorePage(props: { q: string }) {
  const t = useMessages(messages);
  const params = new URLSearchParams(location.search);
  const [q, setQ] = useState(props.q);
  const [players, setPlayers] = useState(params.get("players") ?? "");
  const [chance, setChance] = useState<Tri>((params.get("chance") as Tri) ?? "");
  const [perfect, setPerfect] = useState<Tri>((params.get("perfect_information") as Tri) ?? "");
  const [simultaneous, setSimultaneous] = useState<Tri>((params.get("simultaneous") as Tri) ?? "");
  const [zeroSum, setZeroSum] = useState<Tri>((params.get("zero_sum") as Tri) ?? "");
  const [branching, setBranching] = useState(params.get("max_branching") ?? "");
  const [kind, setKind] = useState(params.get("kind") ?? "");
  const [sort, setSort] = useState(params.get("sort") ?? "stars");
  const filters = {
    q,
    players,
    chance,
    perfect_information: perfect,
    simultaneous,
    zero_sum: zeroSum,
    max_branching: branching,
    kind,
    sort: sort === "stars" ? "" : sort,
  };
  const key = location.search;
  const results = useLoad(key, () => get<SearchResult>(`/search${location.search}`));
  const submit = (e: FormEvent) => {
    e.preventDefault();
    navigate(`/explore${query(filters)}`);
  };
  const tri = (label: string, value: Tri, set: (v: Tri) => void, yes: string, no: string) => (
    <Field label={label}>
      <select className="gh-select" value={value} onChange={(e) => set(e.target.value as Tri)}>
        <option value="">{t("any")}</option>
        <option value="1">{yes}</option>
        <option value="0">{no}</option>
      </select>
    </Field>
  );
  return (
    <div className="gh-shell-page">
      <h1>{t("explore")}</h1>
      <form className="hub-filters" onSubmit={submit}>
        <Field label={t("search")} hint={t("searchHint")}>
          <input className="gh-input" value={q} onChange={(e) => setQ(e.target.value)} />
        </Field>
        <Field label={t("players")}>
          <input
            className="gh-input"
            type="number"
            min={1}
            value={players}
            onChange={(e) => setPlayers(e.target.value)}
          />
        </Field>
        {tri(t("chance"), chance, setChance, t("withChance"), t("deterministic"))}
        {tri(t("information"), perfect, setPerfect, t("perfectInfo"), t("hiddenInfo"))}
        {tri(t("turns"), simultaneous, setSimultaneous, t("simultaneous"), t("sequential"))}
        {tri(t("zeroSum"), zeroSum, setZeroSum, t("yes"), t("no"))}
        <Field label={t("maxBranching")}>
          <input
            className="gh-input"
            type="number"
            min={1}
            step="any"
            value={branching}
            onChange={(e) => setBranching(e.target.value)}
          />
        </Field>
        <Field label={t("kind")}>
          <select className="gh-select" value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="">{t("any")}</option>
            <option value="game">{t("games")}</option>
            <option value="library">{t("libraries")}</option>
          </select>
        </Field>
        <Field label={t("sortBy")}>
          <select className="gh-select" value={sort} onChange={(e) => setSort(e.target.value)}>
            <option value="stars">{t("sortStars")}</option>
            <option value="recent">{t("sortRecent")}</option>
            <option value="name">{t("sortName")}</option>
            <option value="players">{t("sortPlayers")}</option>
          </select>
        </Field>
        <Button type="submit" variant="primary">
          {t("search")}
        </Button>
      </form>
      {results.data ? (
        <>
          <p className="gh-muted">
            {t("resultCount", { n: results.data.total })}
            {Object.keys(results.data.filters).length > 0 &&
              ` · ${t("understood")}: ${Object.entries(results.data.filters)
                .map(([k, v]) => `${k} = ${String(v)}`)
                .join(", ")}`}
          </p>
          <div className="hub-grid">
            {results.data.results.map((r) => (
              <RepoCard key={r.full_name} repo={r} />
            ))}
          </div>
        </>
      ) : (
        <Loading error={results.error} />
      )}
    </div>
  );
}
