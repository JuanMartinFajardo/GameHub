// SPDX-License-Identifier: AGPL-3.0-or-later
/** Propuestas de cambio: la lista de un repositorio, abrir una nueva y su página con las cuatro
 * capas de diff (texto, semántica, diagrama y balance), la conversación y fusionar. */

import { useMessages } from "@gamehub/i18n";
import { Link, navigate } from "@gamehub/shell";
import { Badge, Button, Field, Panel } from "@gamehub/ui-kit";
import { useEffect, useState } from "react";
import { errorText, type FamilyNode, get, type Pull, type PullDiff, post, type Repo } from "../api";
import { GameDiagram } from "../GameDiagram";
import { Markdown } from "../Markdown";
import { messages } from "../messages";
import { splitPatch } from "../patch";
import type { PullTab } from "../routes";
import { useSession } from "../session";
import { Hash, LevelBadge, Loading, useLoad, When } from "../ui";
import { InterfaceChanges, type RepoContext } from "./Repo";

function StateBadge(props: { state: Pull["state"] }) {
  const t = useMessages(messages);
  const tone = props.state === "open" ? "success" : props.state === "merged" ? "accent" : "neutral";
  return <Badge tone={tone}>{t(`pull_${props.state}`)}</Badge>;
}

export function PullsTab(props: { ctx: RepoContext }) {
  const t = useMessages(messages);
  const { user } = useSession();
  const { repo } = props.ctx;
  const [state, setState] = useState("open");
  const pulls = useLoad(`${repo.full_name}|${state}`, () =>
    get<{ pulls: Pull[] }>(`/repos/${repo.full_name}/pulls?state=${state}`),
  );
  return (
    <div>
      <div className="hub-toolbar">
        <select className="gh-select" value={state} onChange={(e) => setState(e.target.value)}>
          <option value="open">{t("pull_open")}</option>
          <option value="merged">{t("pull_merged")}</option>
          <option value="closed">{t("pull_closed")}</option>
          <option value="all">{t("all")}</option>
        </select>
        <span className="gh-shell-spacer" />
        {user && (
          <Button variant="primary" onClick={() => navigate(`/${repo.full_name}/pulls/new`)}>
            {t("newProposal")}
          </Button>
        )}
      </div>
      <p className="gh-muted">{t("pullsHelp")}</p>
      {pulls.data ? (
        pulls.data.pulls.length ? (
          <ul className="hub-pulls">
            {pulls.data.pulls.map((p) => (
              <li key={p.number}>
                <StateBadge state={p.state} />{" "}
                <Link to={`/${repo.full_name}/pulls/${p.number}`}>
                  #{p.number} {p.title}
                </Link>
                <br />
                <span className="gh-muted">
                  {p.author} · {p.source}:{p.head} → {p.base} · <When time={p.created} />
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="gh-muted">{t("noPulls")}</p>
        )
      ) : (
        <Loading error={pulls.error} />
      )}
    </div>
  );
}

function flatten(node: FamilyNode): string[] {
  return [node.repo, ...node.children.flatMap(flatten)];
}

export function NewPullPage(props: { owner: string; name: string }) {
  const t = useMessages(messages);
  const { user } = useSession();
  const full = `${props.owner}/${props.name}`;
  const params = new URLSearchParams(location.search);
  const target = useLoad(full, () => get<Repo>(`/repos/${full}`));
  const family = useLoad(full, () => get<{ root: FamilyNode }>(`/repos/${full}/family`));
  const [source, setSource] = useState(params.get("source") ?? "");
  const [head, setHead] = useState(params.get("head") ?? "");
  const [base, setBase] = useState("");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);
  const mine = (family.data ? flatten(family.data.root) : []).filter((r) => {
    const owner = r.split("/")[0];
    return owner === user?.name || (user?.orgs ?? []).includes(owner ?? "");
  });
  const chosen = source || mine.find((r) => r !== full) || full;
  const branches = useLoad(chosen ? `b|${chosen}` : null, () =>
    get<{ branches: Record<string, string> }>(`/repos/${chosen}/branches`),
  );
  const baseBranches = useLoad(`b|${full}`, () =>
    get<{ branches: Record<string, string> }>(`/repos/${full}/branches`),
  );
  if (!user) return <p className="gh-shell-error">{t("loginFirst")}</p>;
  if (!target.data) return <Loading error={target.error} />;
  const headBranch = head || Object.keys(branches.data?.branches ?? {})[0] || "";
  const baseBranch = base || target.data.default_branch;
  const submit = () =>
    post<Pull>(`/repos/${full}/pulls`, {
      source: chosen,
      head: headBranch,
      base: baseBranch,
      title,
      body,
    })
      .then((p) => navigate(`/${full}/pulls/${p.number}`))
      .catch((e: unknown) => setError(errorText(e)));
  return (
    <div className="gh-shell-page hub-narrow">
      <h1>
        {t("newProposal")} · <Link to={`/${full}`}>{full}</Link>
      </h1>
      <Panel>
        <div className="hub-form">
          <div className="hub-inline">
            <Field label={t("fromRepo")}>
              <select
                className="gh-select"
                value={chosen}
                onChange={(e) => setSource(e.target.value)}
              >
                {[...new Set([chosen, ...mine])].map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
            </Field>
            <Field label={t("branch")}>
              <select
                className="gh-select"
                value={headBranch}
                onChange={(e) => setHead(e.target.value)}
              >
                {Object.keys(branches.data?.branches ?? {}).map((b) => (
                  <option key={b} value={b}>
                    {b}
                  </option>
                ))}
              </select>
            </Field>
            <span aria-hidden="true">→</span>
            <Field label={t("intoBranch")}>
              <select
                className="gh-select"
                value={baseBranch}
                onChange={(e) => setBase(e.target.value)}
              >
                {Object.keys(baseBranches.data?.branches ?? {}).map((b) => (
                  <option key={b} value={b}>
                    {b}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <Field label={t("title")}>
            <input className="gh-input" value={title} onChange={(e) => setTitle(e.target.value)} />
          </Field>
          <Field label={t("descriptionField")}>
            <textarea
              className="gh-input"
              rows={5}
              value={body}
              onChange={(e) => setBody(e.target.value)}
            />
          </Field>
          {error && <p className="gh-shell-error">{error}</p>}
          <Button variant="primary" onClick={submit} disabled={!title || !headBranch}>
            {t("openProposal")}
          </Button>
        </div>
      </Panel>
    </div>
  );
}

type PullRoute = { owner: string; name: string; number: number; tab: PullTab };

export function PullPage(props: { route: PullRoute }) {
  const t = useMessages(messages);
  const { user } = useSession();
  const full = `${props.route.owner}/${props.route.name}`;
  const base = `/${full}/pulls/${props.route.number}`;
  const [tick, setTick] = useState(0);
  const pull = useLoad(`${base}#${tick}`, () => get<Pull>(`/repos${base}`));
  const diff = useLoad(
    pull.data ? `${base}|${pull.data.head_commit}|${pull.data.base_commit}` : null,
    () => get<PullDiff>(`/repos${base}/diff`),
  );
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const waiting =
    pull.data?.balance?.status === "queued" || pull.data?.balance?.status === "running";
  // Mientras el balance se calcula, se vuelve a preguntar cada pocos segundos.
  useEffect(() => {
    if (!waiting) return;
    const timer = setTimeout(() => setTick((n) => n + 1), 3000);
    return () => clearTimeout(timer);
  }, [waiting]);
  if (!pull.data) return <Loading error={pull.error} />;
  const p = pull.data;
  const act = (path: string, payload: unknown = {}) => {
    setBusy(true);
    setError(null);
    post(`/repos${base}/${path}`, payload)
      .then(() => setTick((n) => n + 1))
      .catch((e: unknown) => setError(errorText(e)))
      .finally(() => setBusy(false));
  };
  const tabs: PullTab[] = ["conversation", "text", "semantic", "visual", "balance"];
  return (
    <div className="gh-shell-page">
      <header className="hub-repo-head">
        <div>
          <p className="gh-muted">
            <Link to={`/${full}/pulls`}>{full}</Link>
          </p>
          <h1>
            {p.title} <span className="gh-muted">#{p.number}</span>
          </h1>
          <p>
            <StateBadge state={p.state} /> <Link to={`/${p.author}`}>{p.author}</Link>{" "}
            {t("proposes")}{" "}
            <code>
              {p.source}:{p.head}
            </code>{" "}
            → <code>{p.base}</code> · <When time={p.created} />
          </p>
        </div>
        <div className="hub-repo-head__actions">
          {p.can_merge && (
            <Button
              variant="primary"
              disabled={busy || p.mergeable === false}
              onClick={() => act("merge")}
            >
              {t("merge")}
            </Button>
          )}
          {p.can_close && (
            <Button disabled={busy} onClick={() => act("close")}>
              {t("closeProposal")}
            </Button>
          )}
          {p.state === "merged" && p.can_merge === false && user && (
            <Button onClick={() => navigate(`/${full}/versions`)}>{t("publishNow")}</Button>
          )}
        </div>
      </header>
      {p.state === "open" && p.mergeable === false && (
        <p className="gh-shell-error">{t("conflicts")}</p>
      )}
      {p.state === "merged" && (
        <p className="hub-notice">
          {t("mergedNotice")} <Link to={`/${full}/versions`}>{t("publishNow")}</Link>
        </p>
      )}
      {error && <p className="gh-shell-error">{error}</p>}
      <nav className="hub-tabs">
        {tabs.map((tab) => (
          <Link
            key={tab}
            to={tab === "conversation" ? base : `${base}/${tab}`}
            className={tab === props.route.tab ? "hub-tab hub-tab--active" : "hub-tab"}
          >
            {t(`ptab_${tab}`)}
            {tab === "text" && diff.data && <Badge>{diff.data.text.files.length}</Badge>}
            {tab === "semantic" && diff.data?.semantic && (
              <Badge>{diff.data.semantic.changes.length}</Badge>
            )}
            {tab === "balance" && p.balance && <Badge>{t(`job_${p.balance.status}`)}</Badge>}
          </Link>
        ))}
      </nav>
      {props.route.tab === "conversation" && (
        <div className="hub-conversation">
          <Panel title={p.author}>
            {p.body ? (
              <Markdown source={p.body} />
            ) : (
              <p className="gh-muted">{t("noDescription")}</p>
            )}
          </Panel>
          {diff.data?.semantic && (
            <Panel title={t("summary")}>
              <SemanticSummary diff={diff.data} />
            </Panel>
          )}
          {p.comments.map((c, i) => (
            <Panel
              // biome-ignore lint/suspicious/noArrayIndexKey: los comentarios no se reordenan
              key={`${c.created}-${i}`}
              title={
                <>
                  <Link to={`/${c.author}`}>{c.author}</Link>{" "}
                  <span className="gh-muted">
                    <When time={c.created} />
                  </span>
                </>
              }
            >
              <Markdown source={c.body} />
            </Panel>
          ))}
          {user && (
            <Panel title={t("comment")}>
              <textarea
                className="gh-input"
                rows={4}
                value={comment}
                onChange={(e) => setComment(e.target.value)}
              />
              <Button
                disabled={!comment.trim() || busy}
                onClick={() => {
                  act("comments", { body: comment });
                  setComment("");
                }}
              >
                {t("send")}
              </Button>
            </Panel>
          )}
        </div>
      )}
      {props.route.tab === "text" &&
        (diff.data ? <TextDiff diff={diff.data} /> : <Loading error={diff.error} />)}
      {props.route.tab === "semantic" &&
        (diff.data ? <SemanticDiff diff={diff.data} /> : <Loading error={diff.error} />)}
      {props.route.tab === "visual" &&
        (diff.data ? (
          diff.data.visual.head?.game ? (
            <Panel title={t("visualDiff")}>
              <GameDiagram
                game={diff.data.visual.head.game}
                base={diff.data.visual.base?.game ?? null}
              />
            </Panel>
          ) : (
            <p className="gh-muted">{t("noDiagram")}</p>
          )
        ) : (
          <Loading error={diff.error} />
        ))}
      {props.route.tab === "balance" && <BalanceTab pull={p} />}
    </div>
  );
}

function SemanticSummary(props: { diff: PullDiff }) {
  const t = useMessages(messages);
  const s = props.diff.semantic;
  if (!s) return null;
  return (
    <p>
      {s.same_rules ? t("sameRules") : t("rulesChange", { n: s.changes.length })}{" "}
      {s.level && (
        <>
          · {t("wouldRequire")} <LevelBadge level={s.level} />
        </>
      )}
    </p>
  );
}

function TextDiff(props: { diff: PullDiff }) {
  const t = useMessages(messages);
  const files = splitPatch(props.diff.text.patch);
  return (
    <div>
      <p className="gh-muted">
        {props.diff.text.files
          .map((f) => `${f.path} (+${f.added ?? "?"} −${f.removed ?? "?"})`)
          .join(" · ")}
      </p>
      {files.map((f) => (
        <Panel key={f.name} title={f.name}>
          <pre className="hub-patch">
            {f.lines.map((line, i) => (
              <span
                // biome-ignore lint/suspicious/noArrayIndexKey: las líneas de un parche no se reordenan
                key={`${f.name}-${i}`}
                className={
                  line.startsWith("+")
                    ? "hub-patch__add"
                    : line.startsWith("-")
                      ? "hub-patch__del"
                      : line.startsWith("@@")
                        ? "hub-patch__hunk"
                        : undefined
                }
              >
                {line}
                {"\n"}
              </span>
            ))}
          </pre>
        </Panel>
      ))}
      {props.diff.text.truncated && <p className="gh-muted">{t("truncated")}</p>}
    </div>
  );
}

function SemanticDiff(props: { diff: PullDiff }) {
  const t = useMessages(messages);
  const d = props.diff;
  if (d.head_problems.length) {
    return (
      <Panel title={t("doesNotCompile")}>
        <pre className="hub-code">{d.head_problems.join("\n\n")}</pre>
      </Panel>
    );
  }
  const s = d.semantic;
  if (!s) return <p className="gh-muted">{t("noSemantic")}</p>;
  return (
    <div className="hub-columns">
      <Panel title={t("ruleChanges")}>
        <SemanticSummary diff={d} />
        {s.old_hash && (
          <p className="gh-muted">
            <Hash value={s.old_hash} /> → <Hash value={s.new_hash} />
          </p>
        )}
        <ul className="hub-changes">
          {s.changes.map((c, i) => (
            <li
              // biome-ignore lint/suspicious/noArrayIndexKey: los cambios no se reordenan
              key={`${c.path}-${i}`}
              className={`hub-change hub-change--${c.op === "+" ? "add" : c.op === "-" ? "del" : "mod"}`}
            >
              <strong>
                {c.op} {c.path}
              </strong>
              {c.old !== undefined && <pre className="hub-patch__del">{c.old}</pre>}
              {c.new !== undefined && <pre className="hub-patch__add">{c.new}</pre>}
            </li>
          ))}
        </ul>
      </Panel>
      <aside>
        <Panel title={t("interfaceChanges")}>
          <InterfaceChanges changes={s.interface} />
        </Panel>
      </aside>
    </div>
  );
}

function BalanceTab(props: { pull: Pull }) {
  const t = useMessages(messages);
  const job = props.pull.balance;
  if (!job) return <p className="gh-muted">{t("noBalance")}</p>;
  if (job.status === "queued" || job.status === "running") {
    return (
      <p className="gh-muted">
        {t(`job_${job.status}`)}
        {job.position !== null &&
          job.status === "queued" &&
          ` · ${t("queuePosition", { n: job.position + 1 })}`}
      </p>
    );
  }
  if (job.status === "failed") return <p className="gh-shell-error">{job.error}</p>;
  return (
    <div>
      {job.result.regressions.length > 0 && (
        <p className="gh-shell-error">{t("regressions", { n: job.result.regressions.length })}</p>
      )}
      <Markdown source={job.result.markdown} />
      <p className="gh-muted">
        {t("balanceHelp")} {job.seconds !== null && `(${job.seconds.toFixed(1)} s)`}
      </p>
    </div>
  );
}
