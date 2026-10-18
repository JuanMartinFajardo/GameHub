// SPDX-License-Identifier: AGPL-3.0-or-later
/** La página de un juego (o librería): cabecera, acciones y sus pestañas. */

import { useMessages } from "@gamehub/i18n";
import { Link, navigate } from "@gamehub/shell";
import { Badge, Button, Field, Panel } from "@gamehub/ui-kit";
import { type ReactNode, useState } from "react";
import {
  api,
  type Built,
  errorText,
  type FamilyNode,
  get,
  type HubEvent,
  type InterfaceChange,
  type MatchRecord,
  type Page,
  post,
  type Rating,
  type Release,
  type Repo,
} from "../api";
import { GameDiagram } from "../GameDiagram";
import { Markdown } from "../Markdown";
import { messages } from "../messages";
import { REPO_TABS, type RepoTab, repoUrl } from "../routes";
import { useSession } from "../session";
import { EventList, Hash, Labels, LevelBadge, Loading, useLoad, When } from "../ui";
import { ReportButton } from "./Account";
import { AnalysisTab } from "./Analysis";
import { CodeTab } from "./Code";
import { MatchList } from "./Explore";
import { PullsTab } from "./Pull";

type RepoRoute = { owner: string; name: string; tab: RepoTab; ref: string | null; path: string };

export interface RepoContext {
  repo: Repo;
  releases: Release[];
  reload: () => void;
}

export function RepoPage(props: { route: RepoRoute }) {
  const t = useMessages(messages);
  const full = `${props.route.owner}/${props.route.name}`;
  const [tick, setTick] = useState(0);
  const data = useLoad(`${full}#${tick}`, async () => {
    const [repo, releases] = await Promise.all([
      get<Repo>(`/repos/${full}`),
      get<{ releases: Release[] }>(`/repos/${full}/releases`),
    ]);
    return { repo, releases: releases.releases };
  });
  if (!data.data) return <Loading error={data.error} />;
  const ctx: RepoContext = { ...data.data, reload: () => setTick((n) => n + 1) };
  const { repo } = ctx;
  return (
    <div className="gh-shell-page">
      <RepoHeader ctx={ctx} />
      <nav className="hub-tabs" aria-label={t("sections")}>
        {REPO_TABS.filter(
          (tab) => repo.kind === "game" || !["ratings", "interfaces"].includes(tab),
        ).map((tab) => (
          <Link
            key={tab}
            to={repoUrl(repo.full_name, tab)}
            className={tab === props.route.tab ? "hub-tab hub-tab--active" : "hub-tab"}
            aria-current={tab === props.route.tab ? "page" : undefined}
          >
            {t(`tab_${tab}`)}
            {tab === "pulls" && repo.open_pulls ? <Badge>{repo.open_pulls}</Badge> : null}
            {tab === "versions" && ctx.releases.length ? (
              <Badge>{ctx.releases.length}</Badge>
            ) : null}
          </Link>
        ))}
      </nav>
      <Tab ctx={ctx} route={props.route} />
    </div>
  );
}

function Tab(props: { ctx: RepoContext; route: RepoRoute }) {
  switch (props.route.tab) {
    case "rules":
      return <RulesTab ctx={props.ctx} refName={props.route.ref} />;
    case "code":
      return <CodeTab ctx={props.ctx} refName={props.route.ref} path={props.route.path} />;
    case "versions":
      return <VersionsTab ctx={props.ctx} />;
    case "pulls":
      return <PullsTab ctx={props.ctx} />;
    case "analysis":
      return <AnalysisTab ctx={props.ctx} />;
    case "ratings":
      return <RatingsTab ctx={props.ctx} />;
    case "interfaces":
      return <InterfacesTab ctx={props.ctx} />;
    case "variants":
      return <VariantsTab ctx={props.ctx} />;
    case "activity":
      return <ActivityTab ctx={props.ctx} />;
    default:
      return null;
  }
}

function RepoHeader(props: { ctx: RepoContext }) {
  const t = useMessages(messages);
  const { user } = useSession();
  const { repo, releases } = props.ctx;
  const [error, setError] = useState<string | null>(null);
  const [forking, setForking] = useState(false);
  const [forkName, setForkName] = useState(repo.name);
  const latest = releases.find((r) => !r.yanked) ?? null;
  const playable = repo.kind === "game" && latest?.game;
  const star = () =>
    api(repo.starred ? "DELETE" : "PUT", `/repos/${repo.full_name}/star`)
      .then(props.ctx.reload)
      .catch((e: unknown) => setError(errorText(e)));
  const fork = () =>
    post<Repo>(`/repos/${repo.full_name}/forks`, { name: forkName })
      .then((r) => navigate(`/${r.full_name}`))
      .catch((e: unknown) => setError(errorText(e)));
  return (
    <header className="hub-repo-head">
      <div className="hub-repo-head__title">
        <h1>
          <Link to={`/${repo.owner}`}>{repo.owner}</Link> / <strong>{repo.name}</strong>{" "}
          {repo.kind === "library" && <Badge tone="warning">{t("library")}</Badge>}
          {repo.hidden && <Badge tone="danger">{t("hidden")}</Badge>}
          {latest && <Badge tone="accent">v{latest.version}</Badge>}
        </h1>
        {repo.parent && (
          <p className="gh-muted">
            {t("forkOf")} <Link to={`/${repo.parent}`}>{repo.parent}</Link>
          </p>
        )}
        {repo.description && <p>{repo.description}</p>}
        {latest && <Labels labels={latest.properties.labels} />}
      </div>
      <div className="hub-repo-head__actions">
        {playable && (
          <>
            <Button variant="primary" onClick={() => navigate(`/${repo.full_name}/play`)}>
              ▶ {t("playOnline")}
            </Button>
            <Button onClick={() => navigate(`/${repo.full_name}/match`)}>{t("findMatch")}</Button>
            <Button onClick={() => navigate(`/${repo.full_name}/local`)}>{t("playHere")}</Button>
          </>
        )}
        {user && (
          <Button onClick={star} selected={repo.starred}>
            ★ {repo.stars}
          </Button>
        )}
        {user &&
          (forking ? (
            <form
              className="hub-inline"
              onSubmit={(e) => {
                e.preventDefault();
                fork();
              }}
            >
              <input
                className="gh-input"
                value={forkName}
                aria-label={t("forkName")}
                onChange={(e) => setForkName(e.target.value.toLowerCase())}
              />
              <Button type="submit" variant="primary">
                {t("fork")}
              </Button>
            </form>
          ) : (
            <Button onClick={() => setForking(true)}>
              ⑂ {t("fork")} ({repo.forks})
            </Button>
          ))}
        {user && !repo.can_write && <ReportButton target={`repo:${repo.full_name}`} />}
      </div>
      {error && <p className="gh-shell-error">{error}</p>}
    </header>
  );
}

// --- reglas -----------------------------------------------------------------------------------------

function RulesTab(props: { ctx: RepoContext; refName: string | null }) {
  const t = useMessages(messages);
  const { repo, releases } = props.ctx;
  const latest = releases.find((r) => !r.yanked);
  const [choice, setChoice] = useState<string>(
    props.refName
      ? `ref:${props.refName}`
      : latest
        ? `v:${latest.version}`
        : `ref:${repo.default_branch}`,
  );
  const built = useLoad(`${repo.full_name}|${choice}`, () =>
    choice.startsWith("v:")
      ? get<Built>(`/repos/${repo.full_name}/releases/${choice.slice(2)}/view`)
      : get<Built>(`/repos/${repo.full_name}/compiled?ref=${encodeURIComponent(choice.slice(4))}`),
  );
  if (repo.empty) return <EmptyRepo repo={repo} />;
  return (
    <div className="hub-rules">
      <div className="hub-toolbar">
        <Field label={t("showVersion")}>
          <select className="gh-select" value={choice} onChange={(e) => setChoice(e.target.value)}>
            {releases.map((r) => (
              <option key={r.version} value={`v:${r.version}`}>
                v{r.version}
                {r.yanked ? ` (${t("yanked")})` : ""}
              </option>
            ))}
            <option value={`ref:${repo.default_branch}`}>
              {t("branch")} {repo.default_branch} ({t("unpublished")})
            </option>
          </select>
        </Field>
      </div>
      {built.data ? (
        built.data.problems.length ? (
          <Panel title={t("doesNotCompile")}>
            <pre className="hub-code">{built.data.problems.join("\n\n")}</pre>
          </Panel>
        ) : (
          <div className="hub-columns hub-columns--rules">
            <div>
              {built.data.rules ? (
                <Markdown source={built.data.rules} />
              ) : (
                <p className="gh-muted">{t("libraryNoRules")}</p>
              )}
            </div>
            <aside>
              {built.data.model?.game && (
                <Panel title={t("diagram")}>
                  <GameDiagram game={built.data.model.game} />
                </Panel>
              )}
              {built.data.rules_hash && (
                <Panel title={t("identity")}>
                  <p>
                    {t("rulesHash")} <Hash value={built.data.rules_hash} />
                  </p>
                  <p>
                    {t("interfaceHash")} <Hash value={built.data.interface_hash} />
                  </p>
                  <p className="gh-muted">
                    {t("commit")} <code>{built.data.commit.slice(0, 12)}</code>
                  </p>
                </Panel>
              )}
            </aside>
          </div>
        )
      ) : (
        <Loading error={built.error} />
      )}
    </div>
  );
}

export function EmptyRepo(props: { repo: Repo }) {
  const t = useMessages(messages);
  return (
    <Panel title={t("emptyTitle")}>
      <p>{t("emptyText")}</p>
      <pre className="hub-code">
        <code>{`git remote add hub ${props.repo.clone_url}\ngit push hub main\ngamehub publish --repo ${props.repo.full_name}`}</code>
      </pre>
    </Panel>
  );
}

// --- versiones ---------------------------------------------------------------------------------------

interface Plan {
  commit: string;
  previous: string | null;
  level: "major" | "minor" | "patch" | null;
  version: string | null;
  interface_changes: InterfaceChange[];
  rules_hash: string | null;
  problems: string[];
}

function VersionsTab(props: { ctx: RepoContext }) {
  const t = useMessages(messages);
  const { repo, releases } = props.ctx;
  const [plan, setPlan] = useState<Plan | null>(null);
  const [version, setVersion] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const check = () => {
    setError(null);
    setBusy(true);
    post<Plan>(`/repos/${repo.full_name}/releases`, {
      dry_run: true,
      version: version || undefined,
    })
      .then(setPlan, (e: unknown) => setError(errorText(e)))
      .finally(() => setBusy(false));
  };
  const publish = () => {
    setBusy(true);
    post<Release>(`/repos/${repo.full_name}/releases`, {
      ref: plan?.commit,
      version: version || undefined,
      notes,
    })
      .then(() => {
        setPlan(null);
        props.ctx.reload();
      })
      .catch((e: unknown) => setError(errorText(e)))
      .finally(() => setBusy(false));
  };
  return (
    <div className="hub-columns">
      <div>
        {releases.length === 0 && <p className="gh-muted">{t("noReleases")}</p>}
        {releases.map((r) => (
          <Panel
            key={r.version}
            title={
              <>
                v{r.version} <LevelBadge level={r.level} />{" "}
                {r.yanked && <Badge tone="danger">{t("yanked")}</Badge>}
              </>
            }
            actions={
              r.game && !r.yanked ? (
                <Link to={`/${repo.full_name}/play?version=${r.version}`}>▶ {t("play")}</Link>
              ) : undefined
            }
          >
            <p className="gh-muted">
              {r.publisher && (
                <>
                  <Link to={`/${r.publisher}`}>{r.publisher}</Link> ·{" "}
                </>
              )}
              <When time={r.created} /> · {t("commit")} <code>{r.commit.slice(0, 12)}</code>
            </p>
            {r.rules_hash && (
              <p>
                {t("rulesHash")} <Hash value={r.rules_hash} /> · {t("interfaceHash")}{" "}
                <Hash value={r.interface_hash} />
              </p>
            )}
            {r.dependencies.length > 0 && (
              <p>
                {t("dependsOn")}{" "}
                {r.dependencies.map((d) => (
                  <span key={d.repo}>
                    <Link to={`/${d.repo}`}>{d.repo}</Link> <code>{d.requirement}</code>{" "}
                  </span>
                ))}
              </p>
            )}
            {r.notes && <Markdown source={r.notes} />}
            {repo.can_admin && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() =>
                  post(`/repos/${repo.full_name}/releases/${r.version}/yank`, { yanked: !r.yanked })
                    .then(props.ctx.reload)
                    .catch((e: unknown) => setError(errorText(e)))
                }
              >
                {r.yanked ? t("unyank") : t("yank")}
              </Button>
            )}
          </Panel>
        ))}
      </div>
      <aside>
        {repo.can_write && (
          <Panel title={t("publishTitle")}>
            <p className="gh-muted">{t("publishHelp")}</p>
            <Field label={t("versionOptional")}>
              <input
                className="gh-input"
                placeholder={t("automatic")}
                value={version}
                onChange={(e) => setVersion(e.target.value)}
              />
            </Field>
            <Button onClick={check} disabled={busy}>
              {t("checkRelease")}
            </Button>
            {plan && (
              <div className="hub-plan">
                {plan.problems.length ? (
                  <pre className="hub-code">{plan.problems.join("\n\n")}</pre>
                ) : (
                  <>
                    <p>
                      {t("wouldPublish")} <strong>v{plan.version}</strong>{" "}
                      {plan.previous && <LevelBadge level={plan.level} />}
                      {plan.previous && (
                        <span className="gh-muted">
                          {" "}
                          ({t("previous")} v{plan.previous})
                        </span>
                      )}
                    </p>
                    <InterfaceChanges changes={plan.interface_changes} />
                    <Field label={t("releaseNotes")}>
                      <textarea
                        className="gh-input"
                        rows={3}
                        value={notes}
                        onChange={(e) => setNotes(e.target.value)}
                      />
                    </Field>
                    <Button variant="primary" onClick={publish} disabled={busy}>
                      {t("publish")} v{plan.version}
                    </Button>
                  </>
                )}
              </div>
            )}
          </Panel>
        )}
        {error && <p className="gh-shell-error">{error}</p>}
        <Panel title={t("semverTitle")}>
          <p className="gh-muted">{t("semverHelp")}</p>
        </Panel>
      </aside>
    </div>
  );
}

export function InterfaceChanges(props: { changes: InterfaceChange[] }) {
  const t = useMessages(messages);
  if (!props.changes.length) return <p className="gh-muted">{t("sameInterface")}</p>;
  return (
    <ul className="hub-changes">
      {props.changes.map((c) => (
        <li
          key={`${c.op}${c.path}`}
          className={`hub-change hub-change--${c.op === "+" ? "add" : c.op === "-" ? "del" : "mod"}`}
        >
          <code>
            {c.op} {c.path}
          </code>{" "}
          {c.breaking && <Badge tone="danger">{t("breaking")}</Badge>}
        </li>
      ))}
    </ul>
  );
}

// --- valoraciones ------------------------------------------------------------------------------------

function RatingsTab(props: { ctx: RepoContext }) {
  const t = useMessages(messages);
  const { repo, releases } = props.ctx;
  const playable = releases.filter((r) => r.game);
  const [version, setVersion] = useState(playable[0]?.version ?? "");
  const data = useLoad(version ? `${repo.full_name}@${version}` : null, () =>
    get<{ ratings: Rating[]; matches: MatchRecord[]; rules_hash: string }>(
      `/repos/${repo.full_name}/ratings?version=${version}`,
    ),
  );
  if (!playable.length) return <p className="gh-muted">{t("noReleases")}</p>;
  return (
    <div className="hub-columns">
      <div>
        <div className="hub-toolbar">
          <Field label={t("showVersion")}>
            <select
              className="gh-select"
              value={version}
              onChange={(e) => setVersion(e.target.value)}
            >
              {playable.map((r) => (
                <option key={r.version} value={r.version}>
                  v{r.version}
                </option>
              ))}
            </select>
          </Field>
          <p className="gh-muted">{t("ratingsPerRules")}</p>
        </div>
        {data.data ? (
          data.data.ratings.length ? (
            <div className="hub-table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>#</th>
                    <th>{t("player")}</th>
                    <th>Elo</th>
                    <th>Glicko-2</th>
                    <th>TrueSkill</th>
                    <th>{t("matchesPlayed")}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.data.ratings.map((r, i) => (
                    <tr key={r.account}>
                      <td>{i + 1}</td>
                      <td>
                        <Link to={`/${r.account}`}>{r.account}</Link>
                      </td>
                      <td>{r.elo}</td>
                      <td>
                        {r.glicko} ± {r.glicko_rd}
                      </td>
                      <td>{r.trueskill}</td>
                      <td>{r.games}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="gh-muted">{t("noRatings")}</p>
          )
        ) : (
          <Loading error={data.error} />
        )}
      </div>
      <aside>
        <Panel title={t("recentMatches")}>
          {data.data ? <MatchList matches={data.data.matches} /> : <Loading error={data.error} />}
        </Panel>
      </aside>
    </div>
  );
}

// --- interfaces (Pages) -------------------------------------------------------------------------------

function InterfacesTab(props: { ctx: RepoContext }) {
  const t = useMessages(messages);
  const { repo } = props.ctx;
  const pages = useLoad(repo.full_name, () =>
    get<{ pages: Page[] }>(`/repos/${repo.full_name}/pages`),
  );
  const [name, setName] = useState("tablero");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const upload = () => {
    if (!file) return;
    api("POST", `/repos/${repo.full_name}/pages?name=${encodeURIComponent(name)}`, undefined, {
      raw: file,
      contentType: "application/gzip",
    })
      .then(pages.reload)
      .catch((e: unknown) => setError(errorText(e)));
  };
  return (
    <div className="hub-columns">
      <div>
        <p className="gh-muted">{t("pagesHelp")}</p>
        {pages.data ? (
          pages.data.pages.length ? (
            pages.data.pages.map((p) => (
              <Panel key={p.name} title={p.name} actions={<a href={p.url}>{t("open")} ↗</a>}>
                <p>
                  {t("interfaceHash")} <Hash value={p.interface_hash} /> ·{" "}
                  {p.versions.length
                    ? `${t("worksWith")} ${p.versions.map((v) => `v${v}`).join(", ")}`
                    : t("noCompatible")}
                </p>
                <p className="gh-muted">
                  {t("filesCount", { n: p.files })} · <When time={p.created} />
                </p>
              </Panel>
            ))
          ) : (
            <p className="gh-muted">{t("noPages")}</p>
          )
        ) : (
          <Loading error={pages.error} />
        )}
      </div>
      {repo.can_write && (
        <aside>
          <Panel title={t("uploadPage")}>
            <Field label={t("pageName")}>
              <input
                className="gh-input"
                value={name}
                onChange={(e) => setName(e.target.value.toLowerCase())}
              />
            </Field>
            <Field label={t("pageArchive")} hint={t("pageArchiveHint")}>
              <input
                type="file"
                accept=".tar.gz,.tgz,application/gzip"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </Field>
            <Button variant="primary" disabled={!file} onClick={upload}>
              {t("upload")}
            </Button>
            {error && <p className="gh-shell-error">{error}</p>}
          </Panel>
        </aside>
      )}
    </div>
  );
}

// --- variantes ----------------------------------------------------------------------------------------

function Tree(props: { node: FamilyNode }): ReactNode {
  const n = props.node;
  return (
    <li>
      <Link to={`/${n.repo}`} className={n.current ? "hub-tree__current" : undefined}>
        {n.repo}
      </Link>{" "}
      {n.version && <Badge>v{n.version}</Badge>} <span className="gh-muted">★ {n.stars}</span>
      {n.description && <span className="gh-muted"> · {n.description}</span>}
      {n.children.length > 0 && (
        <ul>
          {n.children.map((c) => (
            <Tree key={c.repo} node={c} />
          ))}
        </ul>
      )}
    </li>
  );
}

function VariantsTab(props: { ctx: RepoContext }) {
  const t = useMessages(messages);
  const { repo } = props.ctx;
  const family = useLoad(repo.full_name, () =>
    get<{
      root: FamilyNode;
      ancestors: string[];
      dependencies: { repo: string; requirement: string }[];
      dependents: { repo: string }[];
    }>(`/repos/${repo.full_name}/family`),
  );
  if (!family.data) return <Loading error={family.error} />;
  const f = family.data;
  return (
    <div className="hub-columns">
      <Panel title={t("familyTree")}>
        <p className="gh-muted">{t("familyHelp")}</p>
        <ul className="hub-tree">
          <Tree node={f.root} />
        </ul>
      </Panel>
      <aside>
        <Panel title={t("dependencies")}>
          {f.dependencies.length ? (
            f.dependencies.map((d) => (
              <p key={d.repo}>
                <Link to={`/${d.repo}`}>{d.repo}</Link> <code>{d.requirement}</code>
              </p>
            ))
          ) : (
            <p className="gh-muted">{t("none")}</p>
          )}
        </Panel>
        <Panel title={t("dependents")}>
          {f.dependents.length ? (
            f.dependents.map((d) => (
              <p key={d.repo}>
                <Link to={`/${d.repo}`}>{d.repo}</Link>
              </p>
            ))
          ) : (
            <p className="gh-muted">{t("none")}</p>
          )}
        </Panel>
      </aside>
    </div>
  );
}

function ActivityTab(props: { ctx: RepoContext }) {
  const { repo } = props.ctx;
  const events = useLoad(repo.full_name, () =>
    get<{ events: HubEvent[] }>(`/repos/${repo.full_name}/events`),
  );
  if (!events.data) return <Loading error={events.error} />;
  return <EventList events={events.data.events} />;
}
