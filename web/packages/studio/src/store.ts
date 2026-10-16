// SPDX-License-Identifier: Apache-2.0
/**
 * El estado del Studio: el archivo abierto, el último análisis del servidor, lo seleccionado, la
 * disposición del diagrama, los puntos de ruptura y el simulador. Un objeto con estado inmutable
 * que React lee con `useSyncExternalStore` (como el SDK de F4).
 *
 * El texto vive en el editor (CodeMirror): toda edición del diagrama o de un formulario se pide
 * al servidor (`gamehub/edit`), que contesta con cambios de texto, y se aplica en el editor; así
 * el deshacer del editor deshace también lo hecho en el diagrama.
 */

import { redo, undo } from "@codemirror/commands";
import { ChangeSet } from "@codemirror/state";
import type { EditorView } from "@codemirror/view";
import type { GameIr } from "@gamehub/auto-ui";
import { type ApiError, StudioApi } from "./api";
import { type ConnectionStatus, RequestError, StudioConnection } from "./connection";
import type {
  Analysis,
  EditFailure,
  Focus,
  GameLayout,
  GameModel,
  LayoutFile,
  Op,
  OpenedFile,
  PlayoutStats,
  Selection,
  SimSnapshot,
  SizeEstimate,
  TheoryOptions,
  TheoryReport,
  WorkspaceInfo,
} from "./types";

export type View = "split" | "diagram" | "text";
export type Panel = "problems" | "sim" | "playouts" | "tree" | "analysis" | "diff";
export type Policy = "human" | "random" | "first";

export interface SimState {
  session: string;
  players: number;
  ir: GameIr;
  snapshot: SimSnapshot;
  policies: Record<number, Policy>;
  /** Asientos cuyas vistas se ven lado a lado. */
  seats: number[];
  omniscient: boolean;
  running: boolean;
  message: string | null;
  params: Record<string, unknown>;
  seed: number;
}

export interface DiffState {
  label: string;
  base: GameModel;
}

export interface StudioState {
  status: ConnectionStatus;
  workspace: WorkspaceInfo | null;
  file: OpenedFile | null;
  dirty: boolean;
  saving: boolean;
  analysis: Analysis | null;
  /** El último análisis con modelo (para seguir dibujando mientras el texto está roto). */
  lastModel: GameModel | null;
  selection: Selection;
  layout: LayoutFile;
  collapsed: string[];
  breakpoints: string[];
  conditions: string[];
  view: View;
  panel: Panel | null;
  failure: EditFailure | null;
  busy: boolean;
  notice: { kind: "info" | "error"; text: string } | null;
  sim: SimState | null;
  playouts: PlayoutStats | null;
  showCoverage: boolean;
  estimate: SizeEstimate | null;
  /** Teoría de juegos: el informe acumulado de lo analizado sobre el archivo abierto. */
  theory: TheoryReport | null;
  /** Los análisis que se están calculando. */
  theoryRunning: string[];
  diff: DiffState | null;
  relayout: number;
}

const INITIAL: StudioState = {
  status: "closed",
  workspace: null,
  file: null,
  dirty: false,
  saving: false,
  analysis: null,
  lastModel: null,
  selection: { kind: "game" },
  layout: {},
  collapsed: [],
  breakpoints: [],
  conditions: [],
  view: "split",
  panel: null,
  failure: null,
  busy: false,
  notice: null,
  sim: null,
  playouts: null,
  showCoverage: false,
  estimate: null,
  theory: null,
  theoryRunning: [],
  diff: null,
  relayout: 0,
};

/** Junta un informe nuevo con el anterior del mismo juego (lo nuevo manda). */
export function mergeReports(previous: TheoryReport | null, next: TheoryReport): TheoryReport {
  if (!previous || previous.game.id !== next.game.id) return next;
  const errors = { ...previous.errors };
  for (const key of Object.keys(next)) delete errors[key];
  return { ...previous, ...next, errors: { ...errors, ...next.errors } };
}

function failureOf(error: unknown): EditFailure {
  if (error instanceof RequestError) {
    const data = error.data as Partial<EditFailure> | undefined;
    return { message: data?.message ?? error.message, field: data?.field, errors: data?.errors };
  }
  return { message: error instanceof Error ? error.message : String(error) };
}

export class Studio {
  private state: StudioState = INITIAL;
  private listeners = new Set<() => void>();
  editor: EditorView | null = null;
  private layoutTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(
    readonly connection: StudioConnection,
    readonly api: StudioApi,
  ) {
    connection.onStatus((status) => this.set({ status }));
    connection.onAnalysis((analysis) => this.onAnalysis(analysis));
  }

  // --- estado ---------------------------------------------------------------------------------

  getState = (): StudioState => this.state;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  set(patch: Partial<StudioState>): void {
    this.state = { ...this.state, ...patch };
    for (const listener of this.listeners) listener();
  }

  get game(): GameModel | null {
    return this.state.analysis?.model?.game ?? this.state.lastModel;
  }

  private onAnalysis(analysis: Analysis): void {
    if (analysis.uri !== this.state.file?.uri) return;
    const model = analysis.model?.game ?? null;
    this.set({ analysis, lastModel: model ?? this.state.lastModel });
  }

  // --- espacio de trabajo y archivos ------------------------------------------------------------

  async loadWorkspace(): Promise<WorkspaceInfo> {
    const workspace = await this.api.workspace();
    this.set({ workspace });
    return workspace;
  }

  async open(path: string): Promise<void> {
    const file = await this.api.read(path);
    const memory = loadDebug(path);
    this.set({
      file,
      dirty: false,
      analysis: this.connection.analyses.get(file.uri) ?? null,
      lastModel: null,
      selection: { kind: "game" },
      layout: file.layout ?? {},
      collapsed: memory.collapsed,
      breakpoints: memory.breakpoints,
      conditions: memory.conditions,
      failure: null,
      sim: null,
      playouts: null,
      estimate: null,
      theory: null,
      theoryRunning: [],
      diff: null,
    });
    try {
      history.replaceState(null, "", `?file=${encodeURIComponent(path)}`);
    } catch {
      // Sin historial (tests): no importa.
    }
  }

  markDirty(): void {
    if (!this.state.dirty) this.set({ dirty: true });
  }

  async save(force = false): Promise<boolean> {
    const file = this.state.file;
    if (!file || !this.editor) return false;
    this.set({ saving: true });
    try {
      const text = this.editor.state.doc.toString();
      const saved = await this.api.save(file.path, text, force ? null : file.mtime);
      this.set({ file: { ...file, mtime: saved.mtime, text }, dirty: false, saving: false });
      return true;
    } catch (error) {
      const status = (error as ApiError).status;
      this.set({
        saving: false,
        notice: {
          kind: "error",
          text: status === 409 ? "conflict" : `save: ${(error as Error).message}`,
        },
      });
      return false;
    }
  }

  async newGame(name: string, template: string, title?: string): Promise<void> {
    const made = await this.api.newGame(name, template, title);
    await this.loadWorkspace();
    await this.open(made.path);
  }

  // --- ediciones ------------------------------------------------------------------------------

  /** Aplica operaciones del diagrama o de un formulario; devuelve lo creado o cambiado. `key`
   * dice qué campo del formulario las pidió (para enseñar allí un error). */
  async apply(ops: Op[], key?: string): Promise<Focus | null> {
    const file = this.state.file;
    const view = this.editor;
    if (!file || !view) throw new Error("no hay ningún archivo abierto");
    this.set({ busy: true, failure: null });
    const before = view.state.doc;
    try {
      const version = this.connection.version(file.uri);
      const result = await this.connection.request<{
        edits: { from: number; to: number; insert: string }[];
        focus: Focus | null;
      }>("gamehub/edit", { uri: file.uri, version, ops });
      if (view.state.doc !== before) {
        // Se escribió mientras tanto: se vuelve a pedir sobre el texto nuevo.
        this.set({ busy: false });
        return this.apply(ops, key);
      }
      const changes = ChangeSet.of(result.edits, before.length);
      view.dispatch({ changes, userEvent: "input.studio" });
      // Sin esperar a la sincronización automática (medio segundo): el servidor analiza esta
      // versión en seguida y el diagrama se pone al día.
      this.connection.client.sync();
      this.set({ busy: false, failure: null });
      if (result.focus) this.focus(result.focus);
      return result.focus;
    } catch (error) {
      const failure = { ...failureOf(error), key };
      this.set({ busy: false, failure });
      throw error;
    }
  }

  /** Aplica y, si falla, deja el error en `failure` sin propagarlo (para los formularios). */
  async tryApply(ops: Op[], key?: string): Promise<boolean> {
    try {
      await this.apply(ops, key);
      return true;
    } catch {
      return false;
    }
  }

  clearFailure(): void {
    if (this.state.failure) this.set({ failure: null });
  }

  focus(focus: Focus): void {
    if (focus.node && focus.action && focus.transition !== undefined) {
      this.select({
        kind: "transition",
        node: focus.node,
        action: focus.action,
        index: focus.transition,
      });
    } else if (focus.node && focus.transition !== undefined) {
      this.select({ kind: "transition", node: focus.node, index: focus.transition });
    } else if (focus.node && focus.action) {
      this.select({ kind: "action", node: focus.node, action: focus.action });
    } else if (focus.node) {
      this.select({ kind: "node", node: focus.node });
    }
  }

  select(selection: Selection): void {
    this.set({ selection, failure: null });
  }

  undo(): void {
    if (this.editor) undo(this.editor);
  }

  redo(): void {
    if (this.editor) redo(this.editor);
  }

  // --- disposición, plegado y puntos de ruptura ------------------------------------------------

  setGameLayout(layout: GameLayout): void {
    const game = this.game?.name;
    const file = this.state.file;
    if (!game || !file) return;
    const next: LayoutFile = {
      version: 1,
      ...this.state.layout,
      games: {
        ...(this.state.layout.games ?? {}),
        [game]: { ...layout, collapsed: this.state.collapsed },
      },
    };
    this.set({ layout: next });
    if (this.layoutTimer) clearTimeout(this.layoutTimer);
    this.layoutTimer = setTimeout(() => {
      this.api.saveLayout(file.path, next).catch(() => undefined);
    }, 500);
  }

  gameLayout(): GameLayout | undefined {
    const game = this.game?.name;
    return game ? this.state.layout.games?.[game] : undefined;
  }

  relayout(): void {
    this.set({ relayout: this.state.relayout + 1 });
  }

  toggleCollapse(phase: string): void {
    const collapsed = this.state.collapsed.includes(phase)
      ? this.state.collapsed.filter((p) => p !== phase)
      : [...this.state.collapsed, phase];
    this.set({ collapsed });
    this.remember();
  }

  toggleBreakpoint(node: string): void {
    const breakpoints = this.state.breakpoints.includes(node)
      ? this.state.breakpoints.filter((b) => b !== node)
      : [...this.state.breakpoints, node];
    this.set({ breakpoints });
    this.remember();
  }

  setConditions(conditions: string[]): void {
    this.set({ conditions });
    this.remember();
  }

  private remember(): void {
    const path = this.state.file?.path;
    if (!path) return;
    saveDebug(path, {
      collapsed: this.state.collapsed,
      breakpoints: this.state.breakpoints,
      conditions: this.state.conditions,
    });
  }

  // --- simulador ------------------------------------------------------------------------------

  async startSim(
    options: { players?: number; params?: Record<string, unknown>; seed?: number } = {},
  ) {
    const file = this.state.file;
    if (!file) return;
    const previous = this.state.sim;
    if (previous)
      this.connection
        .request("gamehub/sim.stop", { session: previous.session })
        .catch(() => undefined);
    this.set({ panel: "sim", busy: true });
    try {
      const started = await this.connection.request<{
        session: string;
        players: number;
        ir: GameIr;
        snapshot: SimSnapshot;
      }>("gamehub/sim.start", {
        uri: file.uri,
        players: options.players,
        params: options.params,
        seed: options.seed ?? 0,
      });
      const seats = Array.from({ length: started.players }, (_, i) => i);
      this.set({
        busy: false,
        sim: {
          session: started.session,
          players: started.players,
          ir: started.ir,
          snapshot: started.snapshot,
          policies: Object.fromEntries(seats.map((s) => [s, "human" as Policy])),
          seats,
          omniscient: false,
          running: false,
          message: null,
          params: options.params ?? {},
          seed: options.seed ?? 0,
        },
      });
    } catch (error) {
      this.set({ busy: false, notice: { kind: "error", text: failureOf(error).message } });
    }
  }

  private updateSim(patch: Partial<SimState>): void {
    const sim = this.state.sim;
    if (sim) this.set({ sim: { ...sim, ...patch } });
  }

  private async simCall(method: string, params: Record<string, unknown>): Promise<void> {
    const sim = this.state.sim;
    if (!sim) return;
    this.updateSim({ running: true, message: null });
    try {
      const snapshot = await this.connection.request<SimSnapshot>(method, {
        session: sim.session,
        ...params,
      });
      this.updateSim({ snapshot, running: false });
    } catch (error) {
      this.updateSim({ running: false, message: failureOf(error).message });
    }
  }

  simAct(seat: number, action: unknown): Promise<void> {
    const index = this.state.sim?.snapshot.index ?? 0;
    return this.simCall("gamehub/sim.act", { index, seat, action });
  }

  simChance(outcome?: number[]): Promise<void> {
    const index = this.state.sim?.snapshot.index ?? 0;
    return this.simCall("gamehub/sim.chance", outcome ? { index, outcome } : { index });
  }

  simGoto(index: number): Promise<void> {
    return this.simCall("gamehub/sim.snapshot", { index });
  }

  async simRun(maxSteps = 10_000): Promise<void> {
    const sim = this.state.sim;
    if (!sim) return;
    const humans = Object.entries(sim.policies)
      .filter(([, p]) => p === "human")
      .map(([s]) => Number(s));
    const policies = Object.fromEntries(
      Object.entries(sim.policies).map(([s, p]) => [s, p === "first" ? "first" : "random"]),
    );
    const breakpoints = [
      ...this.state.breakpoints.map((node) => ({ node })),
      ...this.state.conditions.filter((c) => c.trim()).map((expr) => ({ expr })),
    ];
    this.updateSim({ running: true, message: null });
    try {
      const result = await this.connection.request<{
        reason: string;
        label: string | null;
        snapshot: SimSnapshot;
      }>("gamehub/sim.run", {
        session: sim.session,
        index: sim.snapshot.index,
        policies,
        breakpoints,
        humans: maxSteps === 1 ? [] : humans,
        maxSteps,
      });
      this.updateSim({
        snapshot: result.snapshot,
        running: false,
        message:
          result.reason === "breakpoint" ? `breakpoint:${result.label ?? ""}` : result.reason,
      });
    } catch (error) {
      this.updateSim({ running: false, message: failureOf(error).message });
    }
  }

  async simReload(): Promise<void> {
    const sim = this.state.sim;
    if (!sim) return;
    this.updateSim({ running: true });
    try {
      const result = await this.connection.request<{
        kept: number;
        ir: GameIr;
        snapshot: SimSnapshot;
      }>("gamehub/sim.reload", { session: sim.session });
      this.updateSim({
        ir: result.ir,
        snapshot: result.snapshot,
        running: false,
        message: `reloaded:${result.kept}`,
      });
    } catch (error) {
      this.updateSim({ running: false, message: failureOf(error).message });
    }
  }

  setSim(patch: Partial<SimState>): void {
    this.updateSim(patch);
  }

  stopSim(): void {
    const sim = this.state.sim;
    if (sim)
      this.connection.request("gamehub/sim.stop", { session: sim.session }).catch(() => undefined);
    this.set({ sim: null });
  }

  async runPlayouts(games: number, seed: number): Promise<void> {
    const file = this.state.file;
    if (!file) return;
    this.set({ busy: true, panel: "playouts" });
    try {
      const stats = await this.connection.request<PlayoutStats>("gamehub/sim.playouts", {
        uri: file.uri,
        games,
        seed,
        players: this.state.sim?.players,
        params: this.state.sim?.params,
      });
      this.set({ playouts: stats, showCoverage: true, busy: false });
    } catch (error) {
      this.set({ busy: false, notice: { kind: "error", text: failureOf(error).message } });
    }
  }

  async runEstimate(): Promise<void> {
    const file = this.state.file;
    if (!file) return;
    this.set({ busy: true });
    try {
      const estimate = await this.connection.request<SizeEstimate>("gamehub/sim.estimate", {
        uri: file.uri,
        samples: 300,
      });
      this.set({ estimate, busy: false });
    } catch (error) {
      this.set({ busy: false, notice: { kind: "error", text: failureOf(error).message } });
    }
  }

  // --- teoría de juegos ---------------------------------------------------------------------------

  /**
   * Pide al servidor los análisis de teoría de juegos (`gamehub/analyze`) del texto actual. Los
   * resultados se acumulan con los anteriores del mismo juego: lo recién calculado sustituye a lo
   * que hubiera de ese análisis.
   */
  async runTheory(analyses: string[], options: TheoryOptions = {}): Promise<void> {
    const file = this.state.file;
    if (!file) return;
    this.set({ theoryRunning: analyses, panel: "analysis" });
    try {
      const report = await this.connection.request<TheoryReport>("gamehub/analyze", {
        uri: file.uri,
        analyses,
        options,
        players: this.state.sim?.players,
        params: this.state.sim?.params,
      });
      if (this.state.file?.uri !== file.uri) return;
      this.set({ theory: mergeReports(this.state.theory, report), theoryRunning: [] });
    } catch (error) {
      this.set({
        theoryRunning: [],
        notice: { kind: "error", text: failureOf(error).message },
      });
    }
  }

  // --- comparar versiones -----------------------------------------------------------------------

  async compareWith(label: string, text: string): Promise<void> {
    const file = this.state.file;
    if (!file) return;
    const result = await this.connection.request<{ model: { game: GameModel | null } }>(
      "gamehub/modelOf",
      {
        text,
        path: file.uri.startsWith("file://")
          ? decodeURIComponent(new URL(file.uri).pathname)
          : undefined,
      },
    );
    if (!result.model.game) throw new Error("esa versión no tiene un juego que comparar");
    this.set({ diff: { label, base: result.model.game }, panel: "diff" });
  }

  clearDiff(): void {
    this.set({ diff: null });
  }
}

// --- lo que se recuerda de cada archivo (en este navegador) -------------------------------------

interface Debug {
  collapsed: string[];
  breakpoints: string[];
  conditions: string[];
}

function loadDebug(path: string): Debug {
  try {
    const raw = localStorage.getItem(`gamehub:studio:${path}`);
    if (raw) return { collapsed: [], breakpoints: [], conditions: [], ...JSON.parse(raw) };
  } catch {
    // Sin almacenamiento.
  }
  return { collapsed: [], breakpoints: [], conditions: [] };
}

function saveDebug(path: string, debug: Debug): void {
  try {
    localStorage.setItem(`gamehub:studio:${path}`, JSON.stringify(debug));
  } catch {
    // Sin almacenamiento: dura lo que la pestaña.
  }
}

export { StudioApi, StudioConnection };
