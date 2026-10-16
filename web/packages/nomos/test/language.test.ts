// SPDX-License-Identifier: Apache-2.0
import { foldable, getIndentation } from "@codemirror/language";
import { EditorState } from "@codemirror/state";
import { describe, expect, it } from "vitest";
import { matchingBrace, nomos, nomosLanguage, nomosParser } from "../src";

/** Los tokens de una línea: [texto, estilo]. */
function tokens(line: string, start = nomosParser.startState?.(2)) {
  const state = start ?? { comment: false, depth: 0, last: "" };
  const out: [string, string | null][] = [];
  let pos = 0;
  // StringStream mínimo para probar el analizador sin un editor.
  const stream = {
    string: line,
    pos: 0,
    start: 0,
    eol() {
      return this.pos >= this.string.length;
    },
    sol() {
      return this.pos === 0;
    },
    peek() {
      return this.string.charAt(this.pos) || undefined;
    },
    next() {
      if (this.pos < this.string.length) return this.string.charAt(this.pos++);
      return undefined;
    },
    eat(match: string | RegExp) {
      const ch = this.string.charAt(this.pos);
      const ok = typeof match === "string" ? ch === match : match.test(ch);
      if (ok) {
        this.pos += 1;
        return ch;
      }
      return undefined;
    },
    eatSpace() {
      const start = this.pos;
      while (/\s/.test(this.string.charAt(this.pos))) this.pos += 1;
      return this.pos > start;
    },
    skipToEnd() {
      this.pos = this.string.length;
    },
    skipTo(ch: string) {
      const found = this.string.indexOf(ch, this.pos);
      if (found > -1) {
        this.pos = found;
        return true;
      }
      return false;
    },
    match(pattern: string | RegExp, consume = true) {
      if (typeof pattern === "string") {
        if (this.string.startsWith(pattern, this.pos)) {
          if (consume) this.pos += pattern.length;
          return true;
        }
        return null;
      }
      const m = this.string.slice(this.pos).match(pattern);
      if (m?.index !== 0) return null;
      if (consume) this.pos += m[0].length;
      return m;
    },
    current() {
      return this.string.slice(this.start, this.pos);
    },
  };
  while (pos < line.length) {
    stream.start = stream.pos;
    // biome-ignore lint/suspicious/noExplicitAny: StringStream de prueba.
    const style = nomosParser.token(stream as any, state);
    if (stream.pos === stream.start) break;
    out.push([stream.current(), style]);
    pos = stream.pos;
  }
  return out.filter(([text]) => text.trim() !== "");
}

describe("analizador de Nomos", () => {
  it("distingue palabras clave, nodos, tipos, contexto y nombres", () => {
    expect(tokens("decision Move {")).toEqual([
      ["decision", "definitionKeyword"],
      ["Move", "definition(variableName)"],
      ["{", "brace"],
    ]);
    expect(tokens("  actor: turn")).toEqual([
      ["actor", "propertyName"],
      [":", "punctuation"],
      ["turn", "variableName"],
    ]);
    expect(tokens("-> Win when wins(mark(actor))")).toEqual([
      ["->", "operator"],
      ["Win", "labelName"],
      ["when", "keyword"],
      ["wins", "function(variableName)"],
      ["(", "paren"],
      ["mark", "function(variableName)"],
      ["(", "paren"],
      ["actor", "variableName.special"],
      [")", "paren"],
      [")", "paren"],
    ]);
    expect(tokens("board: Grid[3, 3] of Mark? = none // vacío")).toContainEqual([
      "Grid",
      "typeName",
    ]);
    expect(tokens('title: "Tres en raya"')).toContainEqual(['"Tres en raya"', "string"]);
    expect(tokens("@visible(owner) hand: Bag<Card>")[0]).toEqual(["@visible", "meta"]);
    expect(tokens("/// Documentación")).toEqual([["/// Documentación", "docComment"]]);
    expect(tokens("x = 0.5 + 1_000")).toContainEqual(["0.5", "number"]);
  });

  it("sangra por llaves y pliega bloques", () => {
    const doc = "game G {\n  flow {\n    start -> A\n  }\n}\n";
    const state = EditorState.create({ doc, extensions: [nomos()] });
    expect(getIndentation(state, doc.indexOf("    start"))).toBe(4);
    expect(getIndentation(state, doc.indexOf("  }"))).toBe(2);
    const first = state.doc.line(1);
    expect(foldable(state, first.from, first.to)).toEqual({ from: 8, to: doc.lastIndexOf("}") });
    expect(matchingBrace('{ "}" // }\n }', 1)).toBe(12);
    expect(nomosLanguage.name).toBe("nomos");
  });
});
