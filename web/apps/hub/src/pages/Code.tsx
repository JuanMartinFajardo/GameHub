// SPDX-License-Identifier: AGPL-3.0-or-later
/** El código de un repositorio: árbol, archivos (con Nomos resaltado), commits y editar desde la
 * web (en una rama nueva o en un fork propio, para proponer el cambio después). */

import { useMessages } from "@gamehub/i18n";
import { Link, navigate } from "@gamehub/shell";
import { Button, Field, Panel } from "@gamehub/ui-kit";
import { useState } from "react";
import { type Commit, errorText, get, post, type Repo, type TreeEntry } from "../api";
import { CodeEditor } from "../CodeEditor";
import { Markdown } from "../Markdown";
import { messages } from "../messages";
import { enc } from "../routes";
import { useSession } from "../session";
import { Loading, useLoad, When } from "../ui";
import { EmptyRepo, type RepoContext } from "./Repo";

interface FileData {
  commit: string;
  path: string;
  size: number;
  text?: string;
  base64?: string;
}

export function CodeTab(props: { ctx: RepoContext; refName: string | null; path: string }) {
  const t = useMessages(messages);
  const { repo } = props.ctx;
  const ref = props.refName ?? repo.default_branch;
  const branches = useLoad(repo.full_name, () =>
    get<{ branches: Record<string, string>; tags: Record<string, string> }>(
      `/repos/${repo.full_name}/branches`,
    ),
  );
  const isFile = /\.[A-Za-z0-9]+$/.test(props.path);
  const tree = useLoad(isFile || repo.empty ? null : `${ref}|${props.path}`, () =>
    get<{ entries: TreeEntry[]; commit: string }>(
      `/repos/${repo.full_name}/tree?ref=${encodeURIComponent(ref)}&path=${encodeURIComponent(props.path)}`,
    ),
  );
  const file = useLoad(isFile ? `${ref}|${props.path}` : null, () =>
    get<FileData>(
      `/repos/${repo.full_name}/file?ref=${encodeURIComponent(ref)}&path=${encodeURIComponent(props.path)}`,
    ),
  );
  const readme = useLoad(
    !isFile && tree.data?.entries.some((e) => e.name.toLowerCase() === "readme.md")
      ? `${ref}|readme`
      : null,
    () =>
      get<FileData>(
        `/repos/${repo.full_name}/file?ref=${encodeURIComponent(ref)}&path=${encodeURIComponent(
          props.path ? `${props.path}/README.md` : "README.md",
        )}`,
      ),
  );
  const commits = useLoad(repo.empty ? null : ref, () =>
    get<{ commits: Commit[] }>(
      `/repos/${repo.full_name}/commits?ref=${encodeURIComponent(ref)}&limit=12`,
    ),
  );
  if (repo.empty) return <EmptyRepo repo={repo} />;
  const crumbs = props.path ? props.path.split("/") : [];
  const at = (path: string) =>
    `/${repo.full_name}/code${path ? `/${enc(path)}` : ""}${ref !== repo.default_branch ? `?ref=${encodeURIComponent(ref)}` : ""}`;
  return (
    <div className="hub-columns">
      <div>
        <div className="hub-toolbar">
          <select
            className="gh-select"
            aria-label={t("branch")}
            value={ref}
            onChange={(e) =>
              navigate(
                `/${repo.full_name}/code${props.path ? `/${enc(props.path)}` : ""}?ref=${encodeURIComponent(e.target.value)}`,
              )
            }
          >
            {Object.keys(branches.data?.branches ?? { [ref]: "" }).map((b) => (
              <option key={b} value={b}>
                {b}
              </option>
            ))}
            {Object.keys(branches.data?.tags ?? {}).map((b) => (
              <option key={`t${b}`} value={b}>
                {b}
              </option>
            ))}
          </select>
          <nav className="hub-crumbs">
            <Link to={at("")}>{repo.name}</Link>
            {crumbs.map((c, i) => (
              // biome-ignore lint/suspicious/noArrayIndexKey: una ruta puede repetir nombres
              <span key={`${c}-${i}`}>
                {" / "}
                <Link to={at(crumbs.slice(0, i + 1).join("/"))}>{c}</Link>
              </span>
            ))}
          </nav>
          <span className="gh-shell-spacer" />
          {isFile ? (
            <Button
              size="sm"
              onClick={() =>
                navigate(
                  `/${repo.full_name}/edit/${enc(props.path)}?ref=${encodeURIComponent(ref)}`,
                )
              }
            >
              ✎ {t("edit")}
            </Button>
          ) : (
            <Button
              size="sm"
              onClick={() =>
                navigate(
                  `/${repo.full_name}/edit/${props.path ? `${enc(props.path)}/` : ""}?ref=${encodeURIComponent(ref)}`,
                )
              }
            >
              + {t("newFile")}
            </Button>
          )}
        </div>
        {isFile ? (
          file.data ? (
            file.data.text !== undefined ? (
              <CodeEditor
                key={`${ref}|${props.path}`}
                path={props.path}
                text={file.data.text}
                readOnly
              />
            ) : (
              <p className="gh-muted">{t("binaryFile", { n: file.data.size })}</p>
            )
          ) : (
            <Loading error={file.error} />
          )
        ) : tree.data ? (
          <>
            <ul className="hub-tree-list">
              {tree.data.entries.map((e) => (
                <li key={e.path}>
                  <span aria-hidden="true">{e.type === "dir" ? "📁" : "📄"}</span>{" "}
                  <Link to={at(e.path)}>{e.name}</Link>
                  {e.size !== null && <span className="gh-muted"> · {e.size} B</span>}
                </li>
              ))}
            </ul>
            {readme.data?.text && (
              <Panel title="README.md">
                <Markdown source={readme.data.text} skipMermaid={false} />
              </Panel>
            )}
          </>
        ) : (
          <Loading error={tree.error} />
        )}
      </div>
      <aside>
        <Panel title={t("clone")}>
          <pre className="hub-code">
            <code>{`git clone ${repo.clone_url}\ngamehub clone ${repo.full_name}`}</code>
          </pre>
        </Panel>
        <Panel title={t("commits")}>
          {commits.data ? (
            <ul className="hub-events">
              {commits.data.commits.map((c) => (
                <li key={c.id}>
                  <code>{c.id.slice(0, 7)}</code> {c.subject}
                  <br />
                  <span className="gh-muted">
                    {c.author} · <When time={c.time} />
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <Loading error={commits.error} />
          )}
        </Panel>
      </aside>
    </div>
  );
}

type EditRoute = { owner: string; name: string; ref: string | null; path: string };

/** Editar (o crear) un archivo y guardarlo como un commit. Sin permiso de escritura, primero un
 * fork propio; en una rama nueva, después se propone el cambio. */
export function EditPage(props: { route: EditRoute }) {
  const t = useMessages(messages);
  const { user, ready } = useSession();
  const full = `${props.route.owner}/${props.route.name}`;
  const creating = props.route.path === "" || props.route.path.endsWith("/");
  const repo = useLoad(full, () => get<Repo>(`/repos/${full}`));
  const ref = props.route.ref ?? repo.data?.default_branch ?? "main";
  const file = useLoad(repo.data && !creating ? `${ref}|${props.route.path}` : null, () =>
    get<FileData>(
      `/repos/${full}/file?ref=${encodeURIComponent(ref)}&path=${encodeURIComponent(props.route.path)}`,
    ),
  );
  const [text, setText] = useState<string | null>(null);
  const [path, setPath] = useState(props.route.path);
  const [message, setMessage] = useState("");
  const [branch, setBranch] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<{ branch: string } | null>(null);
  const [busy, setBusy] = useState(false);

  if (!ready || !repo.data) return <Loading error={repo.error} />;
  if (!user) {
    navigate(`/login?next=${encodeURIComponent(location.pathname + location.search)}`, {
      replace: true,
    });
    return null;
  }
  const r = repo.data;
  if (!r.can_write) {
    return (
      <Panel title={t("forkToEdit")}>
        <p>{t("forkToEditText")}</p>
        <Button
          variant="primary"
          onClick={() =>
            post<Repo>(`/repos/${full}/forks`, {})
              .then((fork) => navigate(`/${fork.full_name}/edit/${enc(props.route.path)}`))
              .catch((e: unknown) => setError(errorText(e)))
          }
        >
          ⑂ {t("fork")}
        </Button>
        {error && <p className="gh-shell-error">{error}</p>}
      </Panel>
    );
  }
  if (!creating && !file.data) return <Loading error={file.error} />;
  const original = creating ? "" : (file.data?.text ?? "");
  const target = branch.trim() || ref;
  const save = () => {
    setBusy(true);
    setError(null);
    post<{ commit: string }>(`/repos/${full}/files`, {
      branch: target,
      base: branch.trim() ? ref : undefined,
      message: message || t("defaultCommitMessage", { path }),
      expected: branch.trim() || creating ? undefined : file.data?.commit,
      changes: { [path]: text ?? original },
    })
      .then(() => setDone({ branch: target }))
      .catch((e: unknown) => setError(errorText(e)))
      .finally(() => setBusy(false));
  };
  if (done) {
    const proposeTo = r.parent ?? (done.branch !== r.default_branch ? r.full_name : null);
    return (
      <Panel title={t("saved")}>
        <p>{t("savedIn", { branch: done.branch })}</p>
        <p className="hub-actions">
          <Button
            onClick={() =>
              navigate(`/${full}/code/${enc(path)}?ref=${encodeURIComponent(done.branch)}`)
            }
          >
            {t("viewFile")}
          </Button>
          {proposeTo && (
            <Button
              variant="primary"
              onClick={() =>
                navigate(
                  `/${proposeTo}/pulls/new?source=${encodeURIComponent(full)}&head=${encodeURIComponent(done.branch)}`,
                )
              }
            >
              {t("openProposal")}
            </Button>
          )}
        </p>
      </Panel>
    );
  }
  return (
    <div className="gh-shell-page">
      <h1>
        <Link to={`/${full}/code`}>{full}</Link> · {creating ? t("newFile") : t("edit")}
      </h1>
      <Field label={t("path")}>
        <input
          className="gh-input"
          value={path}
          onChange={(e) => setPath(e.target.value)}
          readOnly={!creating}
        />
      </Field>
      <CodeEditor path={path || "nuevo.game"} text={original} onChange={setText} />
      <Panel title={t("commitChanges")}>
        <Field label={t("commitMessage")}>
          <input
            className="gh-input"
            placeholder={t("defaultCommitMessage", { path })}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
          />
        </Field>
        <Field label={t("newBranchOptional")} hint={t("newBranchHint", { branch: ref })}>
          <input className="gh-input" value={branch} onChange={(e) => setBranch(e.target.value)} />
        </Field>
        <Button
          variant="primary"
          onClick={save}
          disabled={busy || !path || (text === null && !creating)}
        >
          {t("commit")}
        </Button>
        {error && <p className="gh-shell-error">{error}</p>}
      </Panel>
    </div>
  );
}
