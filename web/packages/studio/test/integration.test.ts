// SPDX-License-Identifier: Apache-2.0
/**
 * El Studio contra `gamehub studio` de verdad (ver `studio.ts`): el estado de la app, el editor de
 * texto (CodeMirror con el cliente LSP), las ediciones del diagrama, el simulador y las
 * herramientas, sin la interfaz de React.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { EditorState } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { diffModels, withGhosts } from "../src/diagram/diff";
import { toSvg } from "../src/diagram/export";
import { buildGraph, elementAt, problemsByNode } from "../src/diagram/graph";
import { autoLayout, place } from "../src/diagram/layout";
import { mainSetup } from "../src/editor/setup";
import type { Studio } from "../src/store";
import { deckSource, diceSource, gridSource } from "../src/tools/components";
import type { GameModel, TestReport } from "../src/types";
import {
  analysisOf,
  connectStudio,
  type RunningStudio,
  serverAvailable,
  startStudio,
  until,
} from "./studio";

const TICTACTOE = "tictactoe/tictactoe.game";
const DUDO = "dudo/dudo.game";

let server: RunningStudio;
let studio: Studio;
let view: EditorView | null = null;

/** Abre un archivo como lo abre la app: el estado y un editor de texto conectado al LSP. */
async function open(path: string): Promise<GameModel> {
  view?.destroy();
  await studio.open(path);
  const file = studio.getState().file;
  if (!file) throw new Error("no se ha abierto");
  view = new EditorView({
    parent: document.body,
    state: EditorState.create({
      doc: file.text,
      extensions: [
        mainSetup(),
        studio.connection.client.plugin(file.uri, "nomos"),
        // Como el editor de la app: cualquier cambio deja el archivo sin guardar.
        EditorView.updateListener.of((update) => {
          if (update.docChanged) studio.markDirty();
        }),
      ],
    }),
  });
  studio.editor = view;
  const analysis = await analysisOf(studio);
  const game = analysis.model?.game;
  if (!game) throw new Error("sin modelo");
  return game;
}

function text(): string {
  return view?.state.doc.toString() ?? "";
}

describe.skipIf(!serverAvailable)("con gamehub studio", () => {
  beforeAll(async () => {
    server = await startStudio();
    studio = await connectStudio(server);
  }, 90_000);

  afterAll(async () => {
    view?.destroy();
    studio?.connection.close();
    await server?.stop();
  });

  it("lista el espacio de trabajo y abre un juego con su modelo y su clasificación", async () => {
    const files = studio.getState().workspace?.files.map((f) => f.path);
    expect(files).toEqual([DUDO, TICTACTOE]);
    const game = await open(TICTACTOE);
    expect(game.name).toBe("TicTacToe");
    expect(game.flow.nodes.map((n) => n.id)).toEqual(["Move", "Win", "Draw"]);
    const analysis = studio.getState().analysis;
    expect(analysis?.compiled).toBe(true);
    expect(analysis?.classification?.perfect_information).toBe(true);
    expect(studio.getState().status).toBe("open");
  });

  it("el grafo del diagrama: cajas, flechas en orden y lo que hay bajo el cursor", async () => {
    const game = await open(TICTACTOE);
    const graph = buildGraph(game);
    expect(graph.nodes.map((n) => n.id)).toEqual(["s:", "n:Move", "n:Win", "n:Draw"]);
    const move = graph.edges.filter((e) => e.source === "n:Move");
    expect(move.map((e) => [e.target, e.label])).toEqual([
      ["n:Win", "wins(mark(turn))"],
      ["n:Draw", "full()"],
      ["n:Move", "si no"],
    ]);
    expect(move.map((e) => e.data.order)).toEqual([1, 2, 3]);
    // El cursor sobre `full()` selecciona esa transición.
    const at = text().indexOf("-> Draw when full()") + 3;
    expect(elementAt(game, at)).toEqual({ kind: "transition", node: "Move", index: 1 });
    expect(elementAt(game, text().indexOf("action place") + 2)).toEqual({
      kind: "action",
      node: "Move",
      action: "place",
    });
  });

  it("las fases plegadas esconden sus nodos y reconducen las flechas", async () => {
    const source = readFileSync(join(server.root, DUDO), "utf8").replace(
      "    start -> Roll\n",
      "    start -> Round\n\n    phase Round {\n      start -> Roll\n    }\n",
    );
    const other = await studio.connection.request<{ model: { game: GameModel } }>(
      "gamehub/modelOf",
      { text: source },
    );
    const game = other.model.game;
    expect(game.flow.nodes.find((n) => n.id === "Round")?.kind).toBe("phase");
    const open = buildGraph(game);
    expect(open.nodes.some((n) => n.id === "s:Round")).toBe(true);
    // Plegada: la fase es una caja más y la flecha de inicio va a ella.
    const folded = buildGraph(game, { collapsed: new Set(["Round"]) });
    expect(folded.nodes.find((n) => n.id === "n:Round")?.type).toBe("box");
    expect(folded.nodes.some((n) => n.id === "s:Round")).toBe(false);
    expect(folded.edges.find((e) => e.id === "st:")?.target).toBe("n:Round");
  });

  it("una edición del diagrama cambia el texto (y se deshace como cualquier otra)", async () => {
    await open(TICTACTOE);
    const before = text();
    const focus = await studio.apply([{ op: "addNode", kind: "terminal", name: "Tie" }]);
    expect(focus).toEqual({ node: "Tie" });
    expect(text()).toContain("terminal Tie { payoff: fill(0) }");
    expect(studio.getState().selection).toEqual({ kind: "node", node: "Tie" });
    expect(studio.getState().dirty).toBe(true);
    const analysis = await analysisOf(studio);
    expect(analysis.model?.game?.flow.nodes.map((n) => n.id)).toContain("Tie");
    // Un nodo nuevo sin flechas que lleguen a él: aviso en su caja.
    const problems = problemsByNode(analysis.model?.game as GameModel, analysis.problems);
    expect(problems.get("Tie")).toBe("warning");
    studio.undo();
    expect(text()).toBe(before);
  });

  it("un error en un campo del inspector vuelve con su campo y su posición", async () => {
    await open(TICTACTOE);
    const ok = await studio.tryApply(
      [{ op: "addTransition", node: "Move", target: "Draw", when: "turn ==" }],
      "transition:new",
    );
    expect(ok).toBe(false);
    const failure = studio.getState().failure;
    expect(failure).toMatchObject({ field: "when", key: "transition:new" });
    expect(failure?.errors?.[0]?.offset).toBeGreaterThan(0);
  });

  it("si el texto cambia mientras se pide una edición, se repite sobre el texto nuevo", async () => {
    await open(TICTACTOE);
    const pending = studio.apply([{ op: "setMeta", key: "version", value: "2.0.0" }]);
    view?.dispatch({ changes: { from: 0, insert: "// nuevo\n" } });
    await pending;
    expect(text().startsWith("// nuevo\n")).toBe(true);
    expect(text()).toContain('version: "2.0.0"');
  });

  it("guarda en el disco (y avisa si el archivo cambió por fuera)", async () => {
    await open(TICTACTOE);
    await studio.apply([{ op: "setMeta", key: "version", value: "1.1.0" }]);
    const saved = await studio.save();
    expect(studio.getState().notice).toBeNull();
    expect(saved).toBe(true);
    const disk = readFileSync(join(server.root, TICTACTOE), "utf8");
    expect(disk).toBe(text());
    expect(studio.getState().dirty).toBe(false);
    // Otro editor lo cambia: guardar sin forzar da conflicto.
    const file = studio.getState().file;
    if (file) studio.set({ file: { ...file, mtime: 1 } });
    await studio.apply([{ op: "setMeta", key: "version", value: "1.2.0" }]);
    expect(await studio.save()).toBe(false);
    expect(studio.getState().notice).toEqual({ kind: "error", text: "conflict" });
    expect(await studio.save(true)).toBe(true);
  });

  it("el simulador: jugar, volver atrás, correr hasta el final y recargar", async () => {
    await open(TICTACTOE);
    await studio.startSim({ seed: 3 });
    const sim = await until(studio, () => studio.getState().sim, "la simulación");
    expect(sim.players).toBe(2);
    expect(sim.snapshot.status).toBe("decision");
    const legal = sim.snapshot.legal["0"];
    const first = legal && "actions" in legal ? legal.actions[0] : undefined;
    await studio.simAct(0, first);
    expect(studio.getState().sim?.snapshot.index).toBe(1);
    expect(studio.getState().sim?.snapshot.step.trace.length).toBeGreaterThan(0);
    await studio.simGoto(0);
    expect(studio.getState().sim?.snapshot.index).toBe(0);
    // Con los dos asientos al azar se juega hasta el final.
    studio.setSim({ policies: { 0: "random", 1: "random" } });
    await studio.simRun();
    const end = studio.getState().sim;
    expect(end?.snapshot.status).toBe("terminal");
    expect(end?.message).toBe("end");
    // Un punto de ruptura en Win o Draw: para antes del final.
    studio.toggleBreakpoint("Move");
    await studio.simGoto(0);
    await studio.simRun();
    expect(studio.getState().sim?.message).toBe("breakpoint:Move");
    studio.toggleBreakpoint("Move");
    // Tras editar el juego, la partida se recarga con las reglas nuevas.
    await studio.apply([{ op: "setMember", node: "Draw", key: "payoff", value: "fill(1)" }]);
    await analysisOf(studio);
    await studio.simReload();
    expect(studio.getState().sim?.message).toMatch(/^reloaded:\d+$/);
    studio.stopSim();
    expect(studio.getState().sim).toBeNull();
  });

  it("partidas masivas: cobertura de nodos y flechas, y tamaño estimado", async () => {
    const game = await open(DUDO);
    await studio.runPlayouts(30, 1);
    const stats = studio.getState().playouts;
    expect(stats?.finished).toBe(30);
    expect(studio.getState().showCoverage).toBe(true);
    const graph = buildGraph(game, { coverage: stats?.coverage });
    const bid = graph.nodes.find((n) => n.id === "n:Bid");
    expect(bid?.data).toMatchObject({ covered: expect.any(Number) });
    expect((bid?.data as { covered: number } | undefined)?.covered).toBeGreaterThan(0);
    expect(graph.edges.every((e) => e.data.start || (e.data.covered ?? 0) > 0)).toBe(true);
    await studio.runEstimate();
    expect(studio.getState().estimate?.log10States).toBeGreaterThan(5);
  });

  it("los tests del juego se ejecutan desde el Studio", async () => {
    await open(TICTACTOE);
    const file = studio.getState().file;
    const report = await studio.connection.request<TestReport>("gamehub/tests", {
      uri: file?.uri,
      playouts: 20,
    });
    expect(report.tests.map((t) => t.ok)).toEqual([true, true, true]);
    expect(report.invariants).toBe(1);
    expect(report.playouts).toMatchObject({ games: 20, failure: null });
  });

  it("comparar con otra versión: nodos añadidos, cambiados y quitados", async () => {
    const original = await open(TICTACTOE);
    const before = text();
    await studio.apply([
      { op: "addNode", kind: "terminal", name: "Tie" },
      { op: "deleteNode", node: "Draw" },
    ]);
    const now = (await analysisOf(studio)).model?.game as GameModel;
    await studio.compareWith("original", before);
    expect(studio.getState().diff?.label).toBe("original");
    const diff = diffModels(original, now);
    expect(diff.summary).toEqual({ added: ["Tie"], removed: ["Draw"], changed: ["Move"] });
    expect(diff.status.get("t:Move:1")).toBe("changed");
    const ghosts = withGhosts(now, diff);
    expect(ghosts.flow.nodes.map((n) => n.id)).toEqual(["Move", "Win", "Tie", "Draw"]);
    expect(ghosts.flow.nodes.at(-1)?.local).toBe(false);
    studio.clearDiff();
  });

  it("disposición automática con ELK y exportación a SVG", async () => {
    const game = await open(DUDO);
    const graph = buildGraph(game);
    const auto = await autoLayout(graph);
    expect([...auto.keys()].sort()).toEqual(graph.nodes.map((n) => n.id).sort());
    const placements = place(graph, undefined, auto);
    // El flujo baja en el orden del texto: inicio, Roll, Bid, End (la vuelta a Roll sube).
    const y = (id: string) => placements.get(id)?.y ?? Number.NaN;
    expect(y("s:")).toBeLessThan(y("n:Roll"));
    expect(y("n:Roll")).toBeLessThan(y("n:Bid"));
    expect(y("n:Bid")).toBeLessThan(y("n:End"));
    const svg = toSvg(graph, placements, "Dudo");
    expect(svg.startsWith("<svg")).toBe(true);
    for (const name of ["Roll", "Bid", "End", "bid(q, f)", "dudo()", "Dudo"]) {
      expect(svg).toContain(name);
    }
    expect(svg).not.toContain("<foreignObject");
  });

  it("lo que genera el diseñador de componentes compila", async () => {
    await studio.newGame("componentes", "vacio", "Componentes");
    expect(studio.getState().file?.path).toBe("componentes/componentes.game");
    await open("componentes/componentes.game");
    // (Una sola baraja por juego: las dos se llaman `deck`.)
    const generated = [
      gridSource({ width: 3, height: 3, cell: "Int?" }),
      deckSource({ french: true, suits: "", ranks: "", card: "" }),
      diceSource({ count: 2, faces: 6, next: "Turn" }),
    ];
    for (const g of generated) {
      const ops: Record<string, unknown>[] = [];
      if (g.imports) ops.push({ op: "addImport", ...g.imports });
      ops.push({ op: "insertSource", source: g.items });
      await studio.apply(ops as never);
    }
    const analysis = await analysisOf(studio);
    expect(analysis.problems.filter((p) => p.severity === "error")).toEqual([]);
    expect(analysis.compiled).toBe(true);
    expect(text()).toContain("import std.cards.{");
    // La baraja propia, en otro juego.
    await studio.newGame("baraja", "vacio", "Baraja");
    await open("baraja/baraja.game");
    const deck = deckSource({ french: false, suits: "oros, copas", ranks: "sota, rey", card: "" });
    await studio.apply([{ op: "insertSource", source: deck.items }]);
    expect((await analysisOf(studio)).compiled).toBe(true);
  });
});
