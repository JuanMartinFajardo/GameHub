// SPDX-License-Identifier: Apache-2.0
/** Paneles de abajo: problemas, partidas masivas (cobertura), árbol del juego y comparación. */

import { useMessages } from "@gamehub/i18n";
import { Badge, Button, cx } from "@gamehub/ui-kit";
import { useEffect, useState } from "react";
import { useStudio } from "../context";
import { diffModels } from "../diagram/diff";
import { elementAt } from "../diagram/graph";
import { messages } from "../messages";
import type { GameModel, Problem, TreeNode } from "../types";

function reveal(studio: ReturnType<typeof useStudio>[1], from: number | undefined) {
  const view = studio.editor;
  if (!view || from === undefined) return;
  const at = Math.min(from, view.state.doc.length);
  view.dispatch({ selection: { anchor: at }, scrollIntoView: true });
  view.focus();
}

export function ProblemsPanel(props: { game: GameModel | null }) {
  const t = useMessages(messages);
  const [state, studio] = useStudio();
  const analysis = state.analysis;
  const problems = analysis?.problems ?? [];
  const select = (p: Problem) => {
    if (props.game && p.from !== undefined) {
      const found = elementAt(props.game, p.from);
      if (found) studio.select(found);
    }
    reveal(studio, p.from);
  };
  return (
    <div className="gh-sd-problems">
      <div className="gh-sd-row">
        {analysis?.classification
          ? analysis.classification.labels.map((label) => (
              <Badge key={label} tone="accent">
                {label}
              </Badge>
            ))
          : null}
        <span className="gh-sd-spacer" />
        <span className="gh-sd-muted">{t("size")}:</span>
        {state.estimate?.states ? (
          <span>
            {t("states", { n: state.estimate.states })} ·{" "}
            {t("meanLength", { n: (state.estimate.meanLength ?? 0).toFixed(1) })}
            {state.estimate.meanBranching
              ? ` · ${t("branching", { n: state.estimate.meanBranching.toFixed(1) })}`
              : ""}
          </span>
        ) : null}
        <Button
          size="sm"
          disabled={!analysis?.compiled || state.busy}
          onClick={() => studio.runEstimate()}
        >
          {t("estimate")}
        </Button>
      </div>
      {problems.length === 0 ? <p className="gh-sd-note">{t("noProblems")}</p> : null}
      <ul className="gh-sd-problem-list">
        {problems.map((p, i) => (
          // biome-ignore lint/suspicious/noArrayIndexKey: problemas en orden, sin clave propia.
          <li key={i} className={cx("gh-sd-problem", `is-${p.severity}`)}>
            <button type="button" onClick={() => select(p)}>
              <span className="gh-sd-problem__code">{p.code}</span> {p.message}
              {p.help ? <span className="gh-sd-muted"> · {p.help}</span> : null}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function PlayoutsPanel(props: { game: GameModel }) {
  const t = useMessages(messages);
  const [state, studio] = useStudio();
  const [games, setGames] = useState(200);
  const [seed, setSeed] = useState(1);
  const stats = state.playouts;
  const uncoveredNodes = stats
    ? props.game.flow.nodes.filter((n) => !(stats.coverage.nodes[n.id] ?? 0)).map((n) => n.id)
    : [];
  return (
    <div className="gh-sd-playouts">
      <form
        className="gh-sd-row"
        onSubmit={(e) => {
          e.preventDefault();
          studio.runPlayouts(games, seed);
        }}
      >
        <label className="gh-sd-inline">
          {t("games")}
          <input
            type="number"
            className="gh-sd-input"
            min={1}
            max={100000}
            value={games}
            onChange={(e) => setGames(Number(e.target.value))}
          />
        </label>
        <label className="gh-sd-inline">
          {t("seed")}
          <input
            type="number"
            className="gh-sd-input"
            value={seed}
            onChange={(e) => setSeed(Number(e.target.value))}
          />
        </label>
        <Button type="submit" variant="primary" disabled={!state.analysis?.compiled || state.busy}>
          ▶ {t("play")}
        </Button>
        {stats ? (
          <label className="gh-sd-inline">
            <input
              type="checkbox"
              checked={state.showCoverage}
              onChange={(e) => studio.set({ showCoverage: e.target.checked })}
            />
            {t("coverage")}
          </label>
        ) : null}
      </form>
      {stats ? (
        <>
          <p>
            <Badge tone="success">{t("finished", { n: stats.finished })}</Badge>{" "}
            {stats.truncated ? (
              <Badge tone="warning">{t("truncated", { n: stats.truncated })}</Badge>
            ) : null}{" "}
            {stats.errorCount ? (
              <Badge tone="danger">{t("ruleErrors", { n: stats.errorCount })}</Badge>
            ) : null}{" "}
            <span className="gh-sd-muted">
              {t("length")}: {stats.length.min ?? "—"} / {stats.length.mean?.toFixed(1) ?? "—"} /{" "}
              {stats.length.max ?? "—"} · {stats.seconds}s
            </span>{" "}
            {stats.drawRate ? (
              <span className="gh-sd-muted">
                · {t("drawRate", { p: Math.round(stats.drawRate * 100) })}
              </span>
            ) : null}
          </p>
          <table className="gh-sd-stats">
            <thead>
              <tr>
                <th />
                {stats.winRate.map((_, s) => (
                  // biome-ignore lint/suspicious/noArrayIndexKey: un asiento por columna.
                  <th key={s}>{t("seat", { n: s + 1 })}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr>
                <th>{t("winRate")}</th>
                {stats.winRate.map((w, s) => (
                  // biome-ignore lint/suspicious/noArrayIndexKey: un asiento por columna.
                  <td key={s}>{w === null ? "—" : `${Math.round(w * 100)} %`}</td>
                ))}
              </tr>
              <tr>
                <th>{t("payoffMean")}</th>
                {stats.payoffMean.map((p, s) => (
                  // biome-ignore lint/suspicious/noArrayIndexKey: un asiento por columna.
                  <td key={s}>{p === null ? "—" : p.toFixed(2)}</td>
                ))}
              </tr>
            </tbody>
          </table>
          {uncoveredNodes.length ? (
            <p className="gh-sd-note">⚠ {uncoveredNodes.join(", ")}: 0</p>
          ) : null}
          <ul className="gh-sd-problem-list">
            {stats.errors.map((e) => (
              <li key={e.game} className="gh-sd-problem is-error">
                <button
                  type="button"
                  onClick={() => {
                    const node = e.message.split(":")[0]?.trim();
                    if (node && props.game.flow.nodes.some((n) => n.id === node))
                      studio.select({ kind: "node", node });
                  }}
                >
                  #{e.game}: {e.message}
                </button>
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </div>
  );
}

export function TreePanel() {
  const t = useMessages(messages);
  const [state, studio] = useStudio();
  const sim = state.sim;
  const [nodes, setNodes] = useState<Map<string, TreeNode>>(new Map());
  const [count, setCount] = useState<string | null>(null);
  const [counting, setCounting] = useState(false);
  const index = sim?.snapshot.index ?? 0;
  const session = sim?.session;
  const load = async (path: number[]) => {
    if (!session) return;
    const node = await studio.connection.request<TreeNode>("gamehub/sim.tree", {
      session,
      index,
      path,
    });
    setNodes((current) => new Map(current).set(path.join("."), node));
  };
  // biome-ignore lint/correctness/useExhaustiveDependencies: se recarga al cambiar de paso.
  useEffect(() => {
    setNodes(new Map());
    setCount(null);
    if (session) load([]).catch(() => undefined);
  }, [session, index]);
  if (!sim)
    return (
      <p className="gh-sd-note">
        {t("start")} · {t("sim")}
      </p>
    );
  const render = (path: number[]) => {
    const node = nodes.get(path.join("."));
    if (!node) return null;
    return (
      <ul className="gh-sd-tree">
        {node.children.map((child, i) => {
          const childPath = [...path, i];
          const key = childPath.join(".");
          const label =
            child.kind === "chance"
              ? `🎲 [${child.outcome?.join(", ") ?? child.label}] ${child.probability ?? ""}`
              : `${t("seat", { n: (child.seat ?? 0) + 1 })}: ${child.action?.name}(${Object.values(
                  child.action?.args ?? {},
                )
                  .map((v) => JSON.stringify(v))
                  .join(", ")})`;
          const open = nodes.has(key);
          const sub = nodes.get(key);
          return (
            <li key={key}>
              <button
                type="button"
                className="gh-sd-tree__item"
                disabled={child.truncated}
                onClick={() =>
                  open
                    ? setNodes((m) => {
                        const next = new Map(m);
                        for (const k of [...next.keys()])
                          if (k === key || k.startsWith(`${key}.`)) next.delete(k);
                        return next;
                      })
                    : load(childPath)
                }
              >
                {open ? "▾" : "▸"} {label}
                {sub?.payoffs ? (
                  <span className="gh-sd-muted"> → {JSON.stringify(sub.payoffs)}</span>
                ) : null}
                {sub && !sub.payoffs ? <span className="gh-sd-muted"> · {sub.node}</span> : null}
              </button>
              {open ? render(childPath) : null}
            </li>
          );
        })}
      </ul>
    );
  };
  return (
    <div className="gh-sd-treepanel">
      <div className="gh-sd-row">
        <span className="gh-sd-muted">{t("stepOf", { i: index, n: sim.snapshot.length - 1 })}</span>
        <Button
          size="sm"
          disabled={counting}
          onClick={async () => {
            setCounting(true);
            setCount(null);
            try {
              const result = await studio.connection.request<{
                complete: boolean;
                states: number;
                terminals: number;
                depth: number;
              }>("gamehub/sim.count", { session, index, budget: 1_000_000, timeLimit: 5 });
              setCount(
                result.complete
                  ? t("complete", { n: result.states, t: result.terminals, d: result.depth })
                  : t("incomplete", { n: result.states }),
              );
            } catch (error) {
              setCount((error as Error).message);
            } finally {
              setCounting(false);
            }
          }}
        >
          {counting ? t("counting") : t("count")}
        </Button>
        {count ? <span>{count}</span> : null}
      </div>
      {render([])}
    </div>
  );
}

export function DiffPanel(props: { game: GameModel }) {
  const t = useMessages(messages);
  const [state, studio] = useStudio();
  const [history, setHistory] = useState<{ rev: string; date: string; subject: string }[] | null>(
    null,
  );
  const [rev, setRev] = useState("");
  const [other, setOther] = useState("");
  const [error, setError] = useState<string | null>(null);
  const file = state.file;
  // biome-ignore lint/correctness/useExhaustiveDependencies: la historia del archivo abierto.
  useEffect(() => {
    if (file)
      studio.api
        .history(file.path)
        .then(setHistory)
        .catch(() => setHistory([]));
  }, [file?.path]);
  const diff = state.diff ? diffModels(state.diff.base, props.game) : null;
  const run = async (label: string, text: Promise<string>) => {
    try {
      setError(null);
      await studio.compareWith(label, await text);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <div className="gh-sd-diff">
      <div className="gh-sd-row">
        <select
          className="gh-sd-input"
          aria-label={t("gitVersion")}
          value={rev}
          onChange={(e) => setRev(e.target.value)}
        >
          <option value="">{history?.length === 0 ? t("noHistory") : `${t("gitVersion")}…`}</option>
          {(history ?? []).map((c) => (
            <option key={c.rev} value={c.rev}>
              {c.date} · {c.subject}
            </option>
          ))}
        </select>
        <Button
          size="sm"
          disabled={!rev || !file}
          onClick={() =>
            file &&
            run(
              rev.slice(0, 7),
              studio.api.show(file.path, rev).then((r) => r.text),
            )
          }
        >
          {t("diff")}
        </Button>
        <select
          className="gh-sd-input"
          aria-label={t("otherFile")}
          value={other}
          onChange={(e) => setOther(e.target.value)}
        >
          <option value="">{t("otherFile")}…</option>
          {(state.workspace?.files ?? [])
            .filter((f) => f.path !== file?.path)
            .map((f) => (
              <option key={f.path} value={f.path}>
                {f.path}
              </option>
            ))}
        </select>
        <Button
          size="sm"
          disabled={!other}
          onClick={() =>
            run(
              other,
              studio.api.read(other).then((r) => r.text),
            )
          }
        >
          {t("diff")}
        </Button>
        {state.diff ? (
          <Button size="sm" variant="ghost" onClick={() => studio.clearDiff()}>
            ✕
          </Button>
        ) : null}
      </div>
      {error ? <p className="gh-sd-field__error">{error}</p> : null}
      {state.diff && diff ? (
        <div>
          <p className="gh-sd-muted">{t("diffWith", { label: state.diff.label })}</p>
          {diff.summary.added.length + diff.summary.removed.length + diff.summary.changed.length ===
          0 ? (
            <p className="gh-sd-note">{t("noDiff")}</p>
          ) : (
            <ul className="gh-sd-difflist">
              {diff.summary.added.length ? (
                <li className="is-added">
                  + {t("added")}: {diff.summary.added.join(", ")}
                </li>
              ) : null}
              {diff.summary.changed.length ? (
                <li className="is-changed">
                  ~ {t("changed")}: {diff.summary.changed.join(", ")}
                </li>
              ) : null}
              {diff.summary.removed.length ? (
                <li className="is-removed">
                  − {t("removed")}: {diff.summary.removed.join(", ")}
                </li>
              ) : null}
            </ul>
          )}
        </div>
      ) : null}
    </div>
  );
}
