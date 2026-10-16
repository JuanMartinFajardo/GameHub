// SPDX-License-Identifier: Apache-2.0
/**
 * GameHub Studio: el juego se diseña como diagrama, como texto o con los dos a la vez, y se
 * prueba en el mismo sitio. Las dos vistas son proyecciones del mismo árbol sintáctico: lo que se
 * hace en el diagrama o en el inspector llega al texto (conservando el resto, comentarios
 * incluidos) y lo que se escribe en el texto se ve en el diagrama.
 */

import { pickText, plural, useLocale, useMessages } from "@gamehub/i18n";
import { useTheme } from "@gamehub/shell";
import { Badge, Button, cx, Spinner } from "@gamehub/ui-kit";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { StudioApi, studioToken } from "./api";
import { lspUrl, StudioConnection } from "./connection";
import { StudioContext, useStudio } from "./context";
import { Diagram, type DiagramHandle } from "./diagram/Diagram";
import { diffModels, withGhosts } from "./diagram/diff";
import { download, toPng, toSvg } from "./diagram/export";
import { type DiagramOptions, problemsByNode } from "./diagram/graph";
import { Palette } from "./diagram/Palette";
import { TextEditor } from "./editor/TextEditor";
import { Inspector } from "./inspector/Inspector";
import { messages } from "./messages";
import { AnalysisPanel } from "./panels/analysis";
import { DiffPanel, PlayoutsPanel, ProblemsPanel, TreePanel } from "./panels/panels";
import { Simulator } from "./sim/Simulator";
import { type Panel, Studio, type View } from "./store";
import { DesignerDialog, NewGameDialog } from "./tools/dialogs";
import type { GameModel } from "./types";

export interface StudioAppProps {
  /** Para tests: una API y una conexión ya hechas. */
  studio?: Studio;
}

export function StudioApp(props: StudioAppProps) {
  const t = useMessages(messages);
  const [studio, setStudio] = useState<Studio | null>(props.studio ?? null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (props.studio) return;
    let cancelled = false;
    (async () => {
      const token = studioToken();
      const api = new StudioApi("", token);
      const workspace = await api.workspace();
      const connection = new StudioConnection({
        url: lspUrl(window.location, token),
        rootUri: workspace.rootUri,
      });
      const created = new Studio(connection, api);
      created.set({ workspace });
      await connection.connect();
      if (cancelled) return;
      setStudio(created);
      const initial =
        new URLSearchParams(window.location.search).get("file") ??
        workspace.open ??
        workspace.files[0]?.path;
      if (initial) await created.open(initial);
    })().catch((e) => setError((e as Error).message));
    return () => {
      cancelled = true;
    };
  }, [props.studio]);
  if (error) {
    return (
      <div className="gh-studio-splash" role="alert">
        <h1>GameHub Studio</h1>
        <p>{error}</p>
      </div>
    );
  }
  if (!studio) {
    return (
      <div className="gh-studio-splash">
        <Spinner label={t("connecting")} />
        <p>{t("connecting")}</p>
      </div>
    );
  }
  return (
    <StudioContext.Provider value={studio}>
      <Workbench />
    </StudioContext.Provider>
  );
}

function Workbench() {
  const t = useMessages(messages);
  const { locale, setLocale } = useLocale();
  const [theme, setTheme] = useTheme();
  const [state, studio] = useStudio();
  const [dialog, setDialog] = useState<"new" | "designer" | null>(null);
  const [menu, setMenu] = useState<{ node?: string; edge?: string; x: number; y: number } | null>(
    null,
  );
  const diagram = useRef<DiagramHandle | null>(null);
  const analysis = state.analysis;
  const live = analysis?.model?.game ?? null;
  const game: GameModel | null = live ?? state.lastModel;
  const stale = !live && !!state.lastModel;
  const errors = analysis?.problems.filter((p) => p.severity === "error").length ?? 0;
  const warnings = analysis?.problems.filter((p) => p.severity === "warning").length ?? 0;

  // Atajos: guardar, deshacer y rehacer (fuera del editor de texto, que tiene los suyos).
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const mod = event.metaKey || event.ctrlKey;
      if (!mod) return;
      const inEditor = (event.target as HTMLElement | null)?.closest?.(
        ".cm-editor, input, textarea, select",
      );
      if (event.key === "s") {
        event.preventDefault();
        studio.save();
      } else if (!inEditor && event.key === "z") {
        event.preventDefault();
        if (event.shiftKey) studio.redo();
        else studio.undo();
      } else if (!inEditor && event.key === "y") {
        event.preventDefault();
        studio.redo();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [studio]);

  // Avisar antes de cerrar con cambios sin guardar.
  useEffect(() => {
    const onUnload = (event: BeforeUnloadEvent) => {
      if (studio.getState().dirty) event.preventDefault();
    };
    window.addEventListener("beforeunload", onUnload);
    return () => window.removeEventListener("beforeunload", onUnload);
  }, [studio]);

  // Si el archivo cambió en el disco (otro editor) y aquí no hay cambios, se recarga.
  useEffect(() => {
    const onFocus = async () => {
      const file = studio.getState().file;
      if (!file || !studio.editor) return;
      try {
        const fresh = await studio.api.read(file.path);
        if (fresh.mtime === file.mtime) return;
        if (studio.getState().dirty) {
          studio.set({ notice: { kind: "error", text: "conflict" } });
          return;
        }
        const view = studio.editor;
        view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: fresh.text } });
        studio.set({ file: { ...file, mtime: fresh.mtime, text: fresh.text }, dirty: false });
      } catch {
        // Sin conexión: ya se verá.
      }
    };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [studio]);

  const diff = useMemo(
    () => (state.diff && game ? diffModels(state.diff.base, game) : null),
    [state.diff, game],
  );
  const shown = useMemo(() => (game && diff ? withGhosts(game, diff) : game), [game, diff]);

  const options: DiagramOptions = useMemo(() => {
    const sim = state.sim;
    const taken = new Set<string>();
    for (const key of sim?.snapshot.step.trace ?? []) taken.add(key.join("/"));
    return {
      collapsed: new Set(state.collapsed),
      breakpoints: new Set(state.breakpoints),
      problems: game && analysis ? problemsByNode(game, analysis.problems) : new Map(),
      coverage: state.showCoverage ? (state.playouts?.coverage ?? null) : null,
      active: sim ? sim.snapshot.path : null,
      taken,
      diff: diff?.status ?? null,
    };
  }, [
    state.collapsed,
    state.breakpoints,
    state.sim,
    state.playouts,
    state.showCoverage,
    game,
    analysis,
    diff,
  ]);

  const exportSvg = useCallback(() => {
    const handle = diagram.current;
    if (!handle || !game) return;
    const title = pickText(
      (game.meta.title as string | Record<string, string>) ?? game.name,
      locale,
    );
    download(`${game.name}.svg`, toSvg(handle.graph, handle.placements, title));
  }, [game, locale]);

  const exportPng = useCallback(async () => {
    const handle = diagram.current;
    if (!handle || !game) return;
    const title = pickText(
      (game.meta.title as string | Record<string, string>) ?? game.name,
      locale,
    );
    download(
      `${game.name}.png`,
      await toPng(toSvg(handle.graph, handle.placements, title)),
      "image/png",
    );
  }, [game, locale]);

  const openFile = async (path: string) => {
    if (state.dirty && state.file && !window.confirm(t("discard", { file: state.file.path })))
      return;
    await studio.open(path);
  };

  const panel = state.panel;
  const setPanel = (next: Panel | null) => studio.set({ panel: panel === next ? null : next });
  const editable = !!live && !diff && (analysis?.syntaxOk ?? false);

  return (
    <div className={cx("gh-studio", `is-${state.view}`, panel && "has-panel")} data-testid="studio">
      <header className="gh-studio__bar">
        <strong className="gh-studio__brand">GameHub Studio</strong>
        <span className="gh-studio__file">
          {state.file ? state.file.path : "—"}
          {state.dirty ? <span className="gh-sd-dot is-on" title={t("unsaved")} /> : null}
        </span>
        {analysis ? (
          analysis.compiled ? (
            <Badge tone="success">✓ {t("compiled")}</Badge>
          ) : (
            <Badge tone="danger">
              {plural(locale, errors, t("errorOne", { n: errors }), t("errors", { n: errors }))}
            </Badge>
          )
        ) : null}
        {warnings ? (
          <Badge tone="warning">
            {plural(
              locale,
              warnings,
              t("warningOne", { n: warnings }),
              t("warnings", { n: warnings }),
            )}
          </Badge>
        ) : null}
        {state.status !== "open" ? <Badge tone="danger">{t("disconnected")}</Badge> : null}
        <span className="gh-sd-spacer" />
        <fieldset className="gh-studio__group" aria-label={t("view")}>
          {(["diagram", "split", "text"] as View[]).map((v) => (
            <Button
              key={v}
              size="sm"
              selected={state.view === v}
              onClick={() => studio.set({ view: v })}
            >
              {v === "split" ? t("viewSplit") : v === "diagram" ? t("viewDiagram") : t("viewText")}
            </Button>
          ))}
        </fieldset>
        <Button size="sm" variant="ghost" title={t("undo")} onClick={() => studio.undo()}>
          ↶
        </Button>
        <Button size="sm" variant="ghost" title={t("redo")} onClick={() => studio.redo()}>
          ↷
        </Button>
        <Button size="sm" variant="ghost" onClick={() => studio.relayout()} disabled={!game}>
          {t("relayout")}
        </Button>
        <Button size="sm" variant="ghost" onClick={exportSvg} disabled={!game}>
          SVG
        </Button>
        <Button size="sm" variant="ghost" onClick={() => exportPng()} disabled={!game}>
          PNG
        </Button>
        <Button
          size="sm"
          variant="primary"
          onClick={() => (state.sim ? setPanel("sim") : studio.startSim())}
          disabled={!analysis?.compiled}
        >
          ▶ {t("simulate")}
        </Button>
        <Button size="sm" onClick={() => studio.save()} disabled={!state.dirty || state.saving}>
          {state.saving ? t("saving") : t("save")}
        </Button>
        <select
          className="gh-sd-input gh-studio__lang"
          aria-label={t("language")}
          value={locale}
          onChange={(e) => setLocale(e.target.value as "es" | "en")}
        >
          <option value="es">ES</option>
          <option value="en">EN</option>
        </select>
        <select
          className="gh-sd-input gh-studio__lang"
          aria-label={t("theme")}
          value={theme}
          onChange={(e) => setTheme(e.target.value as "auto" | "light" | "dark")}
        >
          <option value="auto">◐</option>
          <option value="light">☀</option>
          <option value="dark">☾</option>
        </select>
      </header>

      <aside className="gh-studio__files" aria-label={t("files")}>
        <div className="gh-studio__files-head">
          <span>{t("files")}</span>
          <Button size="sm" variant="ghost" onClick={() => setDialog("new")}>
            ＋ {t("newGame")}
          </Button>
        </div>
        <ul>
          {(state.workspace?.files ?? []).map((f) => (
            <li key={f.path}>
              <button
                type="button"
                className={cx("gh-studio__item", state.file?.path === f.path && "is-active")}
                onClick={() => openFile(f.path)}
                title={f.path}
              >
                {f.package ? <span className="gh-sd-muted">{f.package}/</span> : null}
                {f.name}
              </button>
            </li>
          ))}
        </ul>
        {game ? (
          <>
            <div className="gh-studio__files-head">
              <span>{t("nodes")}</span>
            </div>
            <ul className="gh-studio__outline">
              {game.flow.nodes.map((n) => (
                <li key={n.id} style={{ paddingLeft: depth(game, n.id) * 12 }}>
                  <button
                    type="button"
                    className={cx(
                      "gh-studio__item",
                      state.selection.kind !== "game" &&
                        state.selection.node === n.id &&
                        "is-active",
                    )}
                    onClick={() => studio.select({ kind: "node", node: n.id })}
                  >
                    <code>{n.id}</code> <span className="gh-sd-muted">{n.kind}</span>
                  </button>
                </li>
              ))}
            </ul>
          </>
        ) : null}
      </aside>

      <main className="gh-studio__center">
        <section
          className="gh-studio__diagram"
          aria-label={t("viewDiagram")}
          hidden={state.view === "text"}
        >
          {shown ? (
            <>
              <Palette disabled={!editable} />
              {stale ? <p className="gh-studio__overlay">{t("syntaxErrors")}</p> : null}
              {state.diff ? (
                <p className="gh-studio__overlay is-info">
                  {t("diffWith", { label: state.diff.label })}
                </p>
              ) : null}
              <Diagram
                key={`${state.file?.path}:${game?.name}`}
                game={shown}
                layout={studio.gameLayout()}
                options={options}
                selection={state.selection}
                editable={editable}
                relayout={state.relayout}
                onSelect={(s) => studio.select(s)}
                onOps={(ops) => studio.apply(ops)}
                onLayout={(layout) => studio.setGameLayout(layout)}
                onToggleCollapse={(phase) => studio.toggleCollapse(phase)}
                onReady={(handle) => {
                  diagram.current = handle;
                }}
                onContextMenu={(target, point) => setMenu({ ...target, ...point })}
              />
            </>
          ) : (
            <p className="gh-sd-note gh-studio__empty">{state.file ? t("noGame") : t("noFile")}</p>
          )}
        </section>
        <section
          className="gh-studio__text"
          aria-label={t("viewText")}
          hidden={state.view === "diagram"}
        >
          {state.file ? (
            <TextEditor
              studio={studio}
              uri={state.file.uri}
              text={state.file.text}
              selection={state.selection}
              game={game}
            />
          ) : null}
        </section>
      </main>

      <aside className="gh-studio__inspector" aria-label={t("inspector")}>
        {state.failure && !state.failure.key ? (
          <p className="gh-sd-field__error" role="alert">
            {state.failure.message}
          </p>
        ) : null}
        {game ? <Inspector game={game} onDesigner={() => setDialog("designer")} /> : null}
      </aside>

      <section className="gh-studio__panel">
        <div className="gh-studio__tabs" role="tablist">
          {(
            [
              [
                "problems",
                `${t("problems")}${analysis?.problems.length ? ` (${analysis.problems.length})` : ""}`,
              ],
              ["sim", t("sim")],
              ["playouts", t("playouts")],
              ["tree", t("tree")],
              ["analysis", t("analysis")],
              ["diff", t("diff")],
            ] as [Panel, string][]
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={panel === key}
              className={cx(panel === key && "is-active")}
              onClick={() => setPanel(key)}
            >
              {label}
            </button>
          ))}
          {state.notice ? (
            <span className={cx("gh-studio__notice", `is-${state.notice.kind}`)}>
              {state.notice.text === "conflict" ? (
                <>
                  {t("conflict")}{" "}
                  <Button
                    size="sm"
                    onClick={() => studio.save(true).then(() => studio.set({ notice: null }))}
                  >
                    {t("save")}
                  </Button>
                </>
              ) : (
                state.notice.text
              )}
              <button
                type="button"
                className="gh-sd-icon"
                aria-label={t("close")}
                onClick={() => studio.set({ notice: null })}
              >
                ✕
              </button>
            </span>
          ) : null}
        </div>
        {panel ? (
          <div className="gh-studio__panel-body">
            {panel === "problems" ? <ProblemsPanel game={game} /> : null}
            {panel === "sim" && game ? <Simulator game={game} /> : null}
            {panel === "playouts" && game ? <PlayoutsPanel game={game} /> : null}
            {panel === "tree" ? <TreePanel /> : null}
            {panel === "analysis" ? <AnalysisPanel /> : null}
            {panel === "diff" && game ? <DiffPanel game={game} /> : null}
          </div>
        ) : null}
      </section>

      {menu ? (
        <div
          className="gh-sd-menu"
          style={{ left: menu.x, top: menu.y }}
          role="menu"
          onMouseLeave={() => setMenu(null)}
        >
          {menu.node ? (
            <>
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  studio.toggleBreakpoint(menu.node as string);
                  setMenu(null);
                }}
              >
                ● {t("breakpoint")}
              </button>
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  studio.select({ kind: "node", node: menu.node as string });
                  studio.set({ view: state.view === "diagram" ? "split" : state.view });
                  setMenu(null);
                }}
              >
                ⌕ {t("showText")}
              </button>
              {editable ? (
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    studio.tryApply([{ op: "deleteNode", node: menu.node }]);
                    setMenu(null);
                  }}
                >
                  🗑 {t("delete")}
                </button>
              ) : null}
            </>
          ) : null}
          <button type="button" role="menuitem" onClick={() => setMenu(null)}>
            {t("close")}
          </button>
        </div>
      ) : null}

      {dialog === "new" ? <NewGameDialog onClose={() => setDialog(null)} /> : null}
      {dialog === "designer" ? <DesignerDialog onClose={() => setDialog(null)} /> : null}
    </div>
  );
}

function depth(game: GameModel, id: string): number {
  let d = 0;
  let current = game.flow.nodes.find((n) => n.id === id)?.parent ?? null;
  while (current) {
    d += 1;
    current = game.flow.nodes.find((n) => n.id === current)?.parent ?? null;
  }
  return d;
}
