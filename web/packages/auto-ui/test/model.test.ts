// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import { buildModel, cardReader, enumLook, eventText, valueText } from "../src";
import { IR } from "./fixtures";

describe("modelo del juego", () => {
  it("deduce cómo dibujar cada variable y cómo elegir cada argumento", () => {
    const ttt = buildModel(IR.tictactoe);
    expect(ttt.vars.map((v) => [v.name, v.widget, v.place])).toEqual([
      ["board", "grid", "table"],
      ["turn", "seat", "table"],
    ]);
    expect(ttt.nodes.get("Move")?.actions.get("place")?.params[0]?.input).toEqual({
      kind: "cell",
      of: "board",
    });
    const m = buildModel(IR.mentiroso);
    const byName = new Map(m.vars.map((v) => [v.name, v]));
    expect(byName.get("hand")).toMatchObject({ widget: "hand", place: "seats", perPlayer: true });
    expect(byName.get("deck")).toMatchObject({ widget: "deck", secret: true });
    expect(m.nodes.get("Play")?.actions.get("play")?.params[0]?.input).toEqual({
      kind: "pick",
      of: "hand",
      seat: ["actor"],
      many: true,
      min: 1,
      max: { param: "max_play" },
    });
    expect(buildModel(IR.rps).nodes.get("Show")?.actions.get("show")?.params[0]?.input).toEqual({
      kind: "choice",
    });
  });

  it("usa las pistas ui por encima de lo deducido", () => {
    const ir = structuredClone(IR.tictactoe);
    ir.ui = {
      state: { turn: { widget: "hidden" }, board: { label: { es: "Tablero", en: "Board" } } },
      types: { Mark: { symbols: { X: "✕", O: "◯" }, labels: { X: { es: "Cruz" } } } },
      actions: { place: { label: "Marcar" } },
      nodes: { Move: { label: "Jugada" } },
      seats: { colors: ["#111111", "#222222"] },
    };
    const model = buildModel(ir);
    expect(model.vars.find((v) => v.name === "turn")?.widget).toBe("hidden");
    expect(model.vars.find((v) => v.name === "board")?.label).toEqual({
      es: "Tablero",
      en: "Board",
    });
    expect(enumLook(model, "Mark", "X", "es")).toEqual({ text: "Cruz", symbol: "✕" });
    expect(model.nodes.get("Move")?.label).toBe("Jugada");
    expect(model.seatColors).toEqual(["#111111", "#222222"]);
  });

  it("reconoce cartas y las escribe", () => {
    const m = buildModel(IR.mentiroso);
    const card = m.vars.find((v) => v.name === "deck")?.base;
    const inner = card && "inner" in card ? card.inner : undefined;
    expect(inner?.kind).toBe("struct");
    const read = inner ? cardReader(m, inner, "es") : null;
    expect(read?.({ suit: "Hearts", rank: "Queen" })).toMatchObject({
      rank: "Q",
      suit: { symbol: "♥" },
    });
    expect(valueText(m, { suit: "Spades", rank: "Ace" }, "es", String)).toBe("A♠");
    expect(valueText(m, { size: 3, items: [] }, "es", String)).toBe("+3 ▒");
    const kuhn = buildModel(IR.kuhn);
    const hand = kuhn.vars.find((v) => v.name === "hand")?.base;
    expect(hand && "inner" in hand && cardReader(kuhn, hand.inner, "es")?.("K").rank).toBe("K");
  });

  it("cuenta los eventos con nombres de jugador", () => {
    const m = buildModel(IR.nim);
    const names = ["Ana", "Luis"];
    const opts = { model: m, locale: "es" as const, seatName: (s: number) => names[s] ?? "?" };
    expect(
      eventText({ type: "action", seat: 1, name: "take", args: { heap: 2, count: 3 } }, opts),
    ).toBe("Luis: Take (Heap: 2, Count: 3)");
    expect(eventText({ type: "action", seat: 0 }, opts)).toBe("Ana juega (oculto)");
    expect(eventText({ type: "end", payoffs: [1, -1] }, opts)).toBe("Fin · Ana 1 · Luis -1");
    expect(eventText({ type: "node", node: "Take" }, opts)).toBeNull();
    const mm = buildModel(IR.mentiroso);
    const move = {
      type: "move",
      from: { var: "deck" },
      to: { var: "hand", seat: 1 },
      count: 1,
      items: [{ $hidden: true }],
    };
    expect(eventText(move, { ...opts, model: mm })).toBe("1 de Deck → Hand (Luis)");
  });
});
