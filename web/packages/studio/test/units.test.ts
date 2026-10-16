// SPDX-License-Identifier: Apache-2.0
/** Las piezas sin servidor: disposición, URLs y token, la API, los campos y los componentes. */

import { describe, expect, it } from "vitest";
import { ApiError, StudioApi, studioToken } from "../src/api";
import { lspUrl } from "../src/connection";
import type { Graph, GraphNode } from "../src/diagram/graph";
import { boxHeight, shorten } from "../src/diagram/graph";
import { fitPhases, layoutKey, type Placements, place, toLayout } from "../src/diagram/layout";
import { parseParams } from "../src/inspector/flow";
import { splitFields, splitNames } from "../src/inspector/game";
import { deckSource, diceSource, graphBoardSource, gridSource } from "../src/tools/components";

function box(id: string, parent: string | null = null, type: GraphNode["type"] = "box"): GraphNode {
  return { id, type, parent, width: 220, height: 60, data: {} as GraphNode["data"] };
}

describe("disposición del diagrama", () => {
  it("guarda los nodos con nombres legibles", () => {
    expect(layoutKey("n:Move")).toBe("Move");
    expect(layoutKey("s:")).toBe("start");
    expect(layoutKey("s:Round")).toBe("start:Round");
    expect(layoutKey("x:Round")).toBe("exit:Round");
  });

  it("respeta lo guardado y pone lo nuevo debajo de quien apunta a ello, sin pisar nada", () => {
    const graph: Graph = {
      nodes: [box("n:A"), box("n:B"), box("n:C")],
      edges: [
        { id: "t:A:0", source: "n:A", sourceHandle: "out", target: "n:C", label: "", data: {} },
      ] as Graph["edges"],
    };
    // B ocupa justo el sitio de debajo de A: C se aparta a un lado.
    const saved = { nodes: { A: { x: 100, y: 100 }, B: { x: 100, y: 216 } } };
    const placed = place(graph, saved, null);
    expect(placed.get("n:A")).toMatchObject({ x: 100, y: 100 });
    const c = placed.get("n:C");
    expect(c?.y).toBe(216);
    expect(c?.x).toBeGreaterThanOrEqual(100 + 220);
    // Lo que se guarda: posiciones redondeadas por nombre.
    const layout = toLayout(placed, { direction: "DOWN" });
    expect(layout.direction).toBe("DOWN");
    expect(Object.keys(layout.nodes ?? {}).sort()).toEqual(["A", "B", "C"]);
  });

  it("sin nada guardado usa la disposición automática", () => {
    const graph: Graph = { nodes: [box("n:A"), box("n:B")], edges: [] };
    const auto: Placements = new Map([
      ["n:A", { x: 5, y: 6, width: 220, height: 60 }],
      ["n:B", { x: 5, y: 120, width: 220, height: 60 }],
    ]);
    expect(place(graph, undefined, auto).get("n:B")).toMatchObject({ x: 5, y: 120 });
  });

  it("una fase abarca a sus hijos", () => {
    const graph: Graph = {
      nodes: [box("n:P", null, "phase"), box("n:X", "n:P"), box("n:Y", "n:P")],
      edges: [],
    };
    const placements: Placements = new Map([
      ["n:P", { x: 0, y: 0, width: 100, height: 100 }],
      ["n:X", { x: 24, y: 44, width: 220, height: 60 }],
      ["n:Y", { x: 300, y: 200, width: 220, height: 60 }],
    ]);
    fitPhases(graph, placements);
    expect(placements.get("n:P")).toMatchObject({ width: 300 + 220 + 24, height: 200 + 60 + 24 });
  });

  it("acorta los textos largos y calcula el alto de cada caja", () => {
    expect(shorten("a   b\n c")).toBe("a b c");
    expect(shorten("x".repeat(40), 10)).toBe(`${"x".repeat(9)}…`);
    expect(boxHeight(0, 0)).toBe(34);
    expect(boxHeight(1, 2)).toBe(34 + 18 + 48 + 8);
  });
});

describe("conexión y API", () => {
  it("el WebSocket va a la misma máquina que la página, con el token", () => {
    expect(lspUrl({ protocol: "http:", host: "127.0.0.1:7421" }, "a b")).toBe(
      "ws://127.0.0.1:7421/lsp?token=a%20b",
    );
    expect(lspUrl({ protocol: "https:", host: "studio.local" }, null)).toBe(
      "wss://studio.local/lsp",
    );
  });

  it("el token de la URL se recuerda en la pestaña", () => {
    sessionStorage.clear();
    expect(studioToken({ search: "?token=abc&file=x.game" })).toBe("abc");
    expect(studioToken({ search: "" })).toBe("abc");
    sessionStorage.clear();
    expect(studioToken({ search: "" })).toBeNull();
  });

  it("la API manda el token y JSON, y convierte los errores", async () => {
    const calls: { url: string; init: RequestInit }[] = [];
    const fetcher = (async (url: string, init: RequestInit) => {
      calls.push({ url, init });
      if (init.method === "PUT") {
        return new Response(JSON.stringify({ error: "el archivo cambió en el disco" }), {
          status: 409,
        });
      }
      return new Response(JSON.stringify({ files: [] }), { status: 200 });
    }) as typeof fetch;
    const api = new StudioApi("http://studio", "secreto", fetcher);
    await api.workspace();
    const [first] = calls;
    expect(first?.url).toBe("http://studio/api/workspace");
    expect(first?.init.headers).toMatchObject({ "x-gamehub-token": "secreto" });
    const error = await api.save("a.game", "texto", 3).catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 409, message: "el archivo cambió en el disco" });
    expect(JSON.parse(String(calls[1]?.init.body))).toEqual({
      path: "a.game",
      text: "texto",
      mtime: 3,
    });
    await api.read("dir/con espacio.game");
    expect(calls[2]?.url).toBe("http://studio/api/file?path=dir%2Fcon%20espacio.game");
  });
});

describe("los campos del inspector", () => {
  it("separa nombres y campos (respetando los tipos con comas)", () => {
    expect(splitNames("X, O  Empty")).toEqual(["X", "O", "Empty"]);
    expect(splitFields("a: Int, b: Map<Seat, List<Card>>, c: (Int, Int)")).toEqual([
      { name: "a", type: "Int" },
      { name: "b", type: "Map<Seat, List<Card>>" },
      { name: "c", type: "(Int, Int)" },
    ]);
  });

  it("lee los parámetros de una acción, uno por línea", () => {
    expect(parseParams("c in cells(board)\n@visible(owner) card: Card in hand[actor]\n")).toEqual([
      { name: "c", type: null, domain: "cells(board)", visibility: null },
      { name: "card", type: "Card", domain: "hand[actor]", visibility: "owner" },
    ]);
  });
});

describe("el diseñador de componentes", () => {
  it("una baraja propia: palos, valores, la carta y el mazo", () => {
    const deck = deckSource({
      french: false,
      suits: "oros copas",
      ranks: "1, 2, rey",
      card: "naipe",
    });
    expect(deck.imports).toBeUndefined();
    expect(deck.items).toContain("enum NaipeSuit { Oros, Copas }");
    expect(deck.items).toContain("enum NaipeRank { Rey }");
    expect(deck.items).toContain("struct Naipe { suit: NaipeSuit, rank: NaipeRank }");
    expect(deck.items).toContain("deck: Zone<Naipe> = naipeDeck()");
    const french = deckSource({ french: true, suits: "", ranks: "", card: "" });
    expect(french.imports?.path).toEqual(["std", "cards"]);
  });

  it("tableros y dados", () => {
    expect(gridSource({ width: 3, height: 3, cell: "Mark?" }).items).toContain(
      "board: Grid[3, 3] of Mark? = none",
    );
    const graph = graphBoardSource({ squares: "a b c", edges: "a-b, b-c, c-z" });
    expect(graph.items).toContain("enum Square { A, B, C }");
    expect(graph.items).toContain("[(A, B), (B, C)]");
    const dice = diceSource({ count: 2, faces: 6, next: "Turn" }).items;
    expect(dice).toContain("dice: List<Int> = [1, 1]");
    expect(dice).toContain("    -> Turn\n");
    expect(diceSource({ count: 1, faces: 6 }).items).toContain("-> RollDice");
  });
});
