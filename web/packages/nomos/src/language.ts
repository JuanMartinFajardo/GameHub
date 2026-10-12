// SPDX-License-Identifier: Apache-2.0
/**
 * Nomos para CodeMirror: un analizador léxico por líneas (StreamLanguage) para el resaltado, la
 * sangría por llaves y el plegado de bloques. El análisis de verdad (errores, tipos,
 * autocompletado) lo hace el servidor de lenguaje de Python; esto solo tiene que ser rápido y
 * aguantar el texto a medias.
 */

import {
  foldService,
  type IndentContext,
  LanguageSupport,
  StreamLanguage,
  type StreamParser,
  type StringStream,
} from "@codemirror/language";
import type { EditorState } from "@codemirror/state";

/** Palabras reservadas de Nomos (las mismas que `gamehub.lang.lexer.KEYWORDS`). */
export const KEYWORDS: ReadonlySet<string> = new Set([
  "action",
  "and",
  "assert",
  "auto",
  "case",
  "chance",
  "deal",
  "decision",
  "div",
  "else",
  "emit",
  "enum",
  "exit",
  "extend",
  "extends",
  "fail",
  "false",
  "flip",
  "flow",
  "fn",
  "for",
  "game",
  "if",
  "import",
  "in",
  "invariant",
  "let",
  "match",
  "meta",
  "move",
  "none",
  "not",
  "or",
  "override",
  "params",
  "phase",
  "players",
  "remove",
  "requires",
  "reveal",
  "reward",
  "shuffle",
  "simultaneous",
  "start",
  "state",
  "struct",
  "terminal",
  "test",
  "true",
  "when",
  "window",
]);

export const NODE_KINDS = [
  "decision",
  "simultaneous",
  "window",
  "chance",
  "auto",
  "phase",
  "terminal",
] as const;
export type NodeKind = (typeof NODE_KINDS)[number];

const ATOMS = new Set(["true", "false", "none"]);
const CONTEXT = new Set(["actor", "seats", "num_players", "viewer", "owner", "face_up"]);
const TYPES = new Set([
  "Bool",
  "Int",
  "Real",
  "Text",
  "Seat",
  "Cell",
  "List",
  "Set",
  "Map",
  "Zone",
  "Bag",
  "Grid",
  "per_player",
]);
/** Palabras de contexto que son claves en su sitio (miembros de nodos, `ui`, tests…). */
const MEMBERS = new Set([
  "actor",
  "actors",
  "eligible",
  "mode",
  "order",
  "payoff",
  "rank",
  "resolve",
  "on_enter",
  "on_exit",
  "ui",
]);

export interface NomosState {
  /** Dentro de un comentario `/* … *\/` que sigue en la línea siguiente. */
  comment: boolean;
  /** Llaves abiertas (para la sangría). */
  depth: number;
  /** El último token significativo (para saber qué es la palabra siguiente). */
  last: string;
}

function word(stream: StringStream, state: NomosState): string {
  const text = stream.current();
  const last = state.last;
  state.last = text;
  if (last === "->" || (last === "start" && text !== "{")) return "labelName";
  if (ATOMS.has(text)) return "atom";
  if (KEYWORDS.has(text)) {
    return (NODE_KINDS as readonly string[]).includes(text) ? "definitionKeyword" : "keyword";
  }
  if ((NODE_KINDS as readonly string[]).includes(last) || last === "fn" || last === "game") {
    return "definition(variableName)";
  }
  if (TYPES.has(text)) return "typeName";
  if (MEMBERS.has(text) && stream.match(/^\s*[:{]/, false)) return "propertyName";
  if (CONTEXT.has(text)) return "variableName.special";
  if (/^[A-Z]/.test(text)) return "typeName";
  if (stream.match(/^\s*\(/, false)) return "function(variableName)";
  return "variableName";
}

export const nomosParser: StreamParser<NomosState> = {
  name: "nomos",
  startState: () => ({ comment: false, depth: 0, last: "" }),
  copyState: (s) => ({ ...s }),
  token(stream, state) {
    if (state.comment) {
      if (stream.skipTo("*/")) {
        stream.match("*/");
        state.comment = false;
      } else {
        stream.skipToEnd();
      }
      return "blockComment";
    }
    if (stream.eatSpace()) return null;
    if (stream.match("///")) {
      stream.skipToEnd();
      return "docComment";
    }
    if (stream.match("//")) {
      stream.skipToEnd();
      return "lineComment";
    }
    if (stream.match("/*")) {
      state.comment = true;
      if (stream.skipTo("*/")) {
        stream.match("*/");
        state.comment = false;
      } else {
        stream.skipToEnd();
      }
      return "blockComment";
    }
    if (stream.match(/^"(?:[^"\\]|\\.)*"?/)) {
      state.last = '"';
      return "string";
    }
    if (stream.match(/^\d[\d_]*(?:\.\d[\d_]*)?/)) {
      state.last = "0";
      return "number";
    }
    if (stream.match(/^@[A-Za-z_]\w*/)) {
      state.last = "@";
      return "meta";
    }
    if (stream.match(/^[A-Za-z_]\w*/)) return word(stream, state);
    const op = stream.match(/^(?:->|=>|==|!=|<=|>=|\.\.<|\.\.|\+=|-=|\*=)/);
    if (op) {
      state.last = stream.current();
      return "operator";
    }
    const ch = stream.next() ?? "";
    state.last = ch;
    if (ch === "{") {
      state.depth += 1;
      return "brace";
    }
    if (ch === "}") {
      state.depth = Math.max(0, state.depth - 1);
      return "brace";
    }
    if (ch === "(" || ch === ")") return "paren";
    if (ch === "[" || ch === "]") return "squareBracket";
    if (ch === "," || ch === ";" || ch === ":" || ch === ".") return "punctuation";
    return "operator";
  },
  indent(state: NomosState, textAfter: string, context: IndentContext) {
    const closing = /^\s*\}/.test(textAfter) ? 1 : 0;
    return Math.max(0, state.depth - closing) * context.unit;
  },
  languageData: {
    commentTokens: { line: "//", block: { open: "/*", close: "*/" } },
    closeBrackets: { brackets: ["(", "[", "{", '"'] },
    indentOnInput: /^\s*\}$/,
    wordChars: "_",
  },
};

export const nomosLanguage = StreamLanguage.define(nomosParser);

/**
 * Plegado por llaves: una línea que acaba en `{` se pliega hasta su `}` (contando las llaves y
 * sin tener en cuenta las de los textos ni los comentarios).
 */
export const nomosFolding = foldService.of(
  (state: EditorState, lineStart: number, lineEnd: number) => {
    const line = state.doc.sliceString(lineStart, lineEnd);
    const trimmed = line.replace(/\/\/.*$/, "").trimEnd();
    if (!trimmed.endsWith("{")) return null;
    const open = lineStart + trimmed.length;
    const close = matchingBrace(state.doc.toString(), open);
    if (close === null) return null;
    if (state.doc.lineAt(close).number <= state.doc.lineAt(open).number) return null;
    return { from: open, to: close };
  },
);

/** Posición de la `}` que cierra la llave que acaba en `afterOpen` (o null). */
export function matchingBrace(text: string, afterOpen: number): number | null {
  let depth = 1;
  let i = afterOpen;
  while (i < text.length) {
    const ch = text[i];
    if (ch === '"') {
      i += 1;
      while (i < text.length && text[i] !== '"') i += text[i] === "\\" ? 2 : 1;
    } else if (ch === "/" && text[i + 1] === "/") {
      while (i < text.length && text[i] !== "\n") i += 1;
    } else if (ch === "/" && text[i + 1] === "*") {
      const end = text.indexOf("*/", i + 2);
      i = end < 0 ? text.length : end + 1;
    } else if (ch === "{") {
      depth += 1;
    } else if (ch === "}") {
      depth -= 1;
      if (depth === 0) return i;
    }
    i += 1;
  }
  return null;
}

/** El lenguaje con sus extras (plegado). */
export function nomos(): LanguageSupport {
  return new LanguageSupport(nomosLanguage, [nomosFolding]);
}
