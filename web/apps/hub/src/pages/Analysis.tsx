// SPDX-License-Identifier: AGPL-3.0-or-later
/** El análisis de un juego: tamaño, ramificación y duración (de cada versión publicada), qué
 * métodos tienen sentido, y los trabajos que se pueden pedir: análisis, balance y arena de bots. */

import { useMessages } from "@gamehub/i18n";
import { Badge, Button, Field, Panel } from "@gamehub/ui-kit";
import { useEffect, useState } from "react";
import { errorText, get, type Job, post } from "../api";
import { Markdown } from "../Markdown";
import { messages } from "../messages";
import { useSession } from "../session";
import { Loading, useLoad, When } from "../ui";
import type { RepoContext } from "./Repo";

export function AnalysisTab(props: { ctx: RepoContext }) {
  const t = useMessages(messages);
  const { user } = useSession();
  const { repo, releases } = props.ctx;
  const latest = releases.find((r) => !r.yanked && r.game);
  const [tick, setTick] = useState(0);
  const jobs = useLoad(`${repo.full_name}#${tick}`, () =>
    get<{ jobs: Job[] }>(`/repos/${repo.full_name}/jobs`),
  );
  const [open, setOpen] = useState<number | null>(null);
  const [entrants, setEntrants] = useState("greedy, random, mcts:seconds=0.05");
  const [games, setGames] = useState(10);
  const [error, setError] = useState<string | null>(null);
  const pending = jobs.data?.jobs.some((j) => j.status === "queued" || j.status === "running");
  useEffect(() => {
    if (!pending) return;
    const timer = setTimeout(() => setTick((n) => n + 1), 3000);
    return () => clearTimeout(timer);
  }, [pending]);
  if (!latest) return <p className="gh-muted">{t("noReleases")}</p>;
  const a = latest.properties.analysis;
  const run = (body: unknown) =>
    post<Job>(`/repos/${repo.full_name}/jobs`, body)
      .then((j) => {
        setOpen(j.id);
        setTick((n) => n + 1);
      })
      .catch((e: unknown) => setError(errorText(e)));
  return (
    <div className="hub-columns">
      <div>
        <Panel title={`${t("analysisOf")} v${latest.version}`}>
          {a ? (
            <dl className="hub-facts">
              <dt>{t("treeSize")}</dt>
              <dd>
                {a.exact?.positions
                  ? `${a.exact.positions} ${t("positions")}`
                  : `≈ 10^${a.tree_log10}`}
                {a.exact?.games ? ` · ${a.exact.games} ${t("matchesWord")}` : ""}
              </dd>
              <dt>{t("branching")}</dt>
              <dd>{a.branching}</dd>
              <dt>{t("length")}</dt>
              <dd>
                {a.depth_mean} ({t("max")} {a.depth_max})
              </dd>
            </dl>
          ) : (
            <p className="gh-muted">{t("analysisPending")}</p>
          )}
          {latest.properties.recommendations && latest.properties.recommendations.length > 0 && (
            <>
              <h3 className="gh-shell-h2">{t("recommendations")}</h3>
              <ul>
                {latest.properties.recommendations.map((r) => (
                  <li key={r.code}>{r.text}</li>
                ))}
              </ul>
            </>
          )}
        </Panel>
        <h2 className="gh-shell-h2">{t("jobs")}</h2>
        {jobs.data ? (
          jobs.data.jobs.length ? (
            jobs.data.jobs.map((j) => (
              <JobRow
                key={j.id}
                job={j}
                open={open === j.id}
                onToggle={() => setOpen(open === j.id ? null : j.id)}
              />
            ))
          ) : (
            <p className="gh-muted">{t("noJobs")}</p>
          )
        ) : (
          <Loading error={jobs.error} />
        )}
      </div>
      <aside>
        {user ? (
          <>
            <Panel title={t("runJob")}>
              <p className="gh-muted">{t("jobsHelp")}</p>
              <p className="hub-actions">
                <Button onClick={() => run({ kind: "analyze", version: latest.version })}>
                  {t("jobAnalyze")}
                </Button>
                <Button
                  onClick={() =>
                    run({ kind: "balance", version: latest.version, options: { games: 100 } })
                  }
                >
                  {t("jobBalance")}
                </Button>
              </p>
            </Panel>
            <Panel title={t("jobArena")}>
              <Field label={t("entrants")} hint={t("entrantsHint")}>
                <input
                  className="gh-input"
                  value={entrants}
                  onChange={(e) => setEntrants(e.target.value)}
                />
              </Field>
              <Field label={t("gamesPerTable")}>
                <input
                  className="gh-input"
                  type="number"
                  min={1}
                  max={400}
                  value={games}
                  onChange={(e) => setGames(Number(e.target.value))}
                />
              </Field>
              <Button
                variant="primary"
                onClick={() =>
                  run({
                    kind: "arena",
                    version: latest.version,
                    entrants: entrants
                      .split(",")
                      .map((s) => s.trim())
                      .filter(Boolean),
                    options: { games },
                  })
                }
              >
                {t("runArena")}
              </Button>
            </Panel>
            {error && <p className="gh-shell-error">{error}</p>}
          </>
        ) : (
          <p className="gh-muted">{t("loginForJobs")}</p>
        )}
      </aside>
    </div>
  );
}

function JobRow(props: { job: Job; open: boolean; onToggle: () => void }) {
  const t = useMessages(messages);
  const j = props.job;
  const full = useLoad(props.open && j.status === "done" ? `job${j.id}` : null, () =>
    get<Job>(`/jobs/${j.id}`),
  );
  const tone = j.status === "done" ? "success" : j.status === "failed" ? "danger" : "warning";
  return (
    <Panel
      title={
        <>
          {t(`kind_${j.kind}` as "kind_analyze")} {j.version && `v${j.version}`}{" "}
          <Badge tone={tone}>{t(`job_${j.status}`)}</Badge>
        </>
      }
      actions={
        j.status === "done" ? (
          <Button size="sm" variant="ghost" onClick={props.onToggle}>
            {props.open ? t("hide") : t("show")}
          </Button>
        ) : undefined
      }
    >
      <p className="gh-muted">
        {j.account ?? "GameHub"} · <When time={j.created} />
        {j.seconds !== null && ` · ${j.seconds.toFixed(1)} s`}
      </p>
      {j.error && <p className="gh-shell-error">{j.error}</p>}
      {props.open && full.data?.result && <JobResult job={full.data} />}
    </Panel>
  );
}

function JobResult(props: { job: Job }) {
  const r = props.job.result;
  if (props.job.kind === "analyze")
    return <pre className="hub-code">{(r.lines ?? []).join("\n")}</pre>;
  if (props.job.kind === "arena") return <pre className="hub-code">{r.table}</pre>;
  return <Markdown source={r.markdown ?? ""} />;
}
