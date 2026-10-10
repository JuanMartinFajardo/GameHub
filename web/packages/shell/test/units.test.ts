// SPDX-License-Identifier: Apache-2.0
import { buildModel, type GameIr } from "@gamehub/auto-ui";
import { describe, expect, it } from "vitest";
import kuhn from "../../../../spec/ir/examples/kuhn-poker.ir.json";
import nim from "../../../../spec/ir/examples/nim.ir.json";
import tictactoe from "../../../../spec/ir/examples/tictactoe.ir.json";
import { constValue, defaultParams, hasHiddenInformation, parseRoute } from "../src";

describe("rutas", () => {
  it("reconoce las páginas de la app", () => {
    expect(parseRoute("/")).toEqual({ page: "home" });
    expect(parseRoute("/r/K7FQ2P")).toEqual({ page: "room", code: "K7FQ2P" });
    expect(parseRoute("/new/dudo")).toEqual({ page: "new", game: "dudo" });
    expect(parseRoute("/local/nim/")).toEqual({ page: "local", game: "nim" });
    expect(parseRoute("/replay/abc123")).toEqual({ page: "replay", id: "abc123" });
    expect(parseRoute("/kit")).toEqual({ page: "kit" });
    expect(parseRoute("/r/a/b")).toEqual({ page: "missing", path: "/r/a/b" });
  });
});

describe("opciones", () => {
  it("lee los valores por defecto constantes de la IR", () => {
    expect(constValue(["const", 3])).toBe(3);
    expect(constValue(["list", ["const", 3], ["const", 5]])).toEqual([3, 5]);
    expect(constValue(["call", "f"])).toBeUndefined();
    expect(defaultParams(buildModel(nim as unknown as GameIr))).toEqual({
      sizes: [3, 5, 7],
      misere: false,
    });
  });

  it("sabe qué juegos esconden información", () => {
    expect(hasHiddenInformation(buildModel(kuhn as unknown as GameIr))).toBe(true);
    expect(hasHiddenInformation(buildModel(tictactoe as unknown as GameIr))).toBe(false);
  });
});

describe("etiquetas", () => {
  it("se traducen al español y se leen en inglés", async () => {
    const { tagText } = await import("../src/tags");
    expect(tagText("zero-sum", "es")).toBe("suma cero");
    expect(tagText("zero-sum", "en")).toBe("zero sum");
    expect(tagText("unknown-tag", "es")).toBe("unknown tag");
  });
});
