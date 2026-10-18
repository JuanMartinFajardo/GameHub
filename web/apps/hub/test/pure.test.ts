// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from "vitest";
import { parseMarkdown } from "../src/Markdown";
import { splitPatch } from "../src/patch";
import { enc, parseHubRoute, repoUrl } from "../src/routes";

describe("rutas del hub", () => {
  it("reconoce páginas, perfiles, repositorios y propuestas", () => {
    expect(parseHubRoute("/")).toEqual({ page: "home" });
    expect(parseHubRoute("/explore", "?q=suma+cero")).toEqual({ page: "explore", q: "suma cero" });
    expect(parseHubRoute("/signup")).toEqual({ page: "login", mode: "signup" });
    expect(parseHubRoute("/r/K7FQ2P")).toEqual({ page: "room", code: "K7FQ2P" });
    expect(parseHubRoute("/ana")).toEqual({ page: "account", name: "ana" });
    expect(parseHubRoute("/ana/nim")).toMatchObject({ page: "repo", tab: "rules", ref: null });
    expect(parseHubRoute("/ana/nim/versions")).toMatchObject({ page: "repo", tab: "versions" });
    expect(parseHubRoute("/ana/nim/code/src/a%20b.game", "?ref=dev")).toMatchObject({
      page: "repo",
      tab: "code",
      ref: "dev",
      path: "src/a b.game",
    });
    expect(parseHubRoute("/ana/nim/edit/nim.game")).toMatchObject({
      page: "edit",
      path: "nim.game",
    });
    expect(parseHubRoute("/ana/nim/pulls/3/visual")).toEqual({
      page: "pull",
      owner: "ana",
      name: "nim",
      number: 3,
      tab: "visual",
    });
    expect(parseHubRoute("/ana/nim/pulls/3/otra")).toMatchObject({ tab: "conversation" });
    expect(parseHubRoute("/ana/nim/pulls/new")).toEqual({
      page: "newPull",
      owner: "ana",
      name: "nim",
    });
    expect(parseHubRoute("/ana/nim/play", "?version=1.1.0")).toMatchObject({
      page: "play",
      mode: "online",
      version: "1.1.0",
    });
    expect(parseHubRoute("/ana/nim/match")).toMatchObject({ page: "play", mode: "match" });
    expect(parseHubRoute("/ana/nim/nada")).toMatchObject({ page: "missing" });
    expect(repoUrl("ana/nim")).toBe("/ana/nim");
    expect(repoUrl("ana/nim", "pulls")).toBe("/ana/nim/pulls");
    expect(enc("a b/c#d")).toBe("a%20b/c%23d");
  });
});

describe("markdown", () => {
  it("separa títulos, listas, tablas y código (y no interpreta HTML)", () => {
    const blocks = parseMarkdown(
      "# Nim\n\nTexto <b>sin</b> HTML\nseguido.\n\n- uno\n- dos\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n```mermaid\nflowchart\n```\n",
    );
    expect(blocks.map((b) => b.kind)).toEqual(["heading", "paragraph", "list", "table", "code"]);
    expect(blocks[1]).toEqual({ kind: "paragraph", text: "Texto <b>sin</b> HTML seguido." });
    expect(blocks[3]).toEqual({ kind: "table", header: ["a", "b"], rows: [["1", "2"]] });
    expect(blocks[4]).toMatchObject({ lang: "mermaid", text: "flowchart" });
  });
});

describe("parches", () => {
  it("trocea un diff de git por archivo", () => {
    const patch = [
      "diff --git a/nim.game b/nim.game",
      "index 1..2 100644",
      "--- a/nim.game",
      "+++ b/nim.game",
      "@@ -1 +1 @@",
      "-misere: Bool = false",
      "+misere: Bool = true",
      "diff --git a/README.md b/README.md",
      "new file mode 100644",
      "+hola",
      "",
    ].join("\n");
    expect(splitPatch(patch)).toEqual([
      { name: "nim.game", lines: ["@@ -1 +1 @@", "-misere: Bool = false", "+misere: Bool = true"] },
      { name: "README.md", lines: ["+hola"] },
    ]);
  });
});
