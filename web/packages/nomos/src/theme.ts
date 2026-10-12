// SPDX-License-Identifier: Apache-2.0
/**
 * Aspecto del editor: colores del resaltado y del propio editor sacados de variables CSS
 * (`--gh-code-…` y las `--gh-…` del kit), así que sigue el tema claro u oscuro de la página.
 */

import { HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import type { Extension } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { tags as t } from "@lezer/highlight";

const v = (name: string, fallback: string) => `var(--gh-code-${name}, ${fallback})`;

export const nomosHighlight = HighlightStyle.define([
  { tag: [t.keyword, t.operatorKeyword], color: v("keyword", "#7c3aed"), fontWeight: "600" },
  { tag: t.definitionKeyword, color: v("node", "#0f766e"), fontWeight: "700" },
  {
    tag: [t.comment, t.lineComment, t.blockComment],
    color: v("comment", "#6b7280"),
    fontStyle: "italic",
  },
  { tag: t.docComment, color: v("doc", "#4b7d5a"), fontStyle: "italic" },
  { tag: t.string, color: v("string", "#b45309") },
  { tag: [t.number, t.atom, t.bool], color: v("number", "#0369a1") },
  { tag: t.typeName, color: v("type", "#be185d") },
  { tag: t.labelName, color: v("node", "#0f766e"), fontWeight: "600" },
  { tag: t.definition(t.variableName), color: v("definition", "#1d4ed8"), fontWeight: "600" },
  { tag: t.function(t.variableName), color: v("function", "#1d4ed8") },
  { tag: t.special(t.variableName), color: v("context", "#9333ea"), fontStyle: "italic" },
  { tag: t.propertyName, color: v("property", "#0e7490") },
  { tag: t.meta, color: v("meta", "#a16207") },
  { tag: [t.operator, t.punctuation], color: v("operator", "#475569") },
]);

export const nomosEditorTheme = EditorView.theme({
  "&": {
    color: "var(--gh-text, #161a26)",
    backgroundColor: "var(--gh-surface, #fff)",
    fontSize: "13px",
  },
  ".cm-content": {
    fontFamily: "var(--gh-mono, monospace)",
    caretColor: "var(--gh-accent, #4f46e5)",
  },
  ".cm-gutters": {
    backgroundColor: "var(--gh-surface-2, #eef0f6)",
    color: "var(--gh-text-muted, #5c6478)",
    border: "none",
  },
  ".cm-activeLine": {
    backgroundColor: "color-mix(in srgb, var(--gh-accent, #4f46e5) 6%, transparent)",
  },
  ".cm-activeLineGutter": { backgroundColor: "var(--gh-surface-3, #e2e6f0)" },
  "&.cm-focused .cm-selectionBackground, .cm-selectionBackground, ::selection": {
    backgroundColor: "color-mix(in srgb, var(--gh-accent, #4f46e5) 22%, transparent)",
  },
  ".cm-tooltip": {
    backgroundColor: "var(--gh-surface, #fff)",
    color: "var(--gh-text, #161a26)",
    border: "1px solid var(--gh-border, #d9dde8)",
    borderRadius: "var(--gh-radius-sm, 6px)",
    boxShadow: "var(--gh-shadow, none)",
  },
  ".cm-panels": {
    backgroundColor: "var(--gh-surface-2, #eef0f6)",
    color: "var(--gh-text, #161a26)",
  },
});

/** Resaltado y tema del editor de Nomos. */
export function nomosTheme(): Extension {
  return [nomosEditorTheme, syntaxHighlighting(nomosHighlight)];
}
