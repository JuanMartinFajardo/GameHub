// SPDX-License-Identifier: Apache-2.0
/** Extensiones comunes de los editores de Nomos (el principal y los de los formularios). */

import {
  autocompletion,
  type CompletionContext,
  type CompletionResult,
  closeBrackets,
  closeBracketsKeymap,
  completionKeymap,
} from "@codemirror/autocomplete";
import { defaultKeymap, history, historyKeymap, indentWithTab } from "@codemirror/commands";
import {
  bracketMatching,
  foldGutter,
  foldKeymap,
  indentOnInput,
  indentUnit,
} from "@codemirror/language";
import { lintKeymap } from "@codemirror/lint";
import { highlightSelectionMatches, searchKeymap } from "@codemirror/search";
import { type Extension, StateEffect, StateField } from "@codemirror/state";
import {
  Decoration,
  type DecorationSet,
  drawSelection,
  EditorView,
  highlightActiveLine,
  highlightActiveLineGutter,
  keymap,
  lineNumbers,
} from "@codemirror/view";
import { nomos, nomosTheme } from "@gamehub/nomos";

/** El editor principal: números de línea, plegado, historia, búsqueda, autocompletado… */
export function mainSetup(): Extension {
  return [
    lineNumbers(),
    highlightActiveLineGutter(),
    foldGutter(),
    drawSelection(),
    indentOnInput(),
    bracketMatching(),
    closeBrackets(),
    highlightActiveLine(),
    highlightSelectionMatches(),
    history(),
    indentUnit.of("  "),
    nomos(),
    nomosTheme(),
    elementHighlight,
    keymap.of([
      ...closeBracketsKeymap,
      ...defaultKeymap,
      ...searchKeymap,
      ...historyKeymap,
      ...foldKeymap,
      ...completionKeymap,
      ...lintKeymap,
      indentWithTab,
    ]),
  ];
}

// --- Resaltado del elemento seleccionado en el diagrama ------------------------------------------

export const setElementHighlight = StateEffect.define<{ from: number; to: number } | null>();

const highlightMark = Decoration.mark({ class: "gh-sd-text-highlight" });

export const elementHighlight = StateField.define<DecorationSet>({
  create: () => Decoration.none,
  update(value, tr) {
    let next = value.map(tr.changes);
    for (const effect of tr.effects) {
      if (effect.is(setElementHighlight)) {
        next =
          effect.value && effect.value.to > effect.value.from
            ? Decoration.set([highlightMark.range(effect.value.from, effect.value.to)])
            : Decoration.none;
      }
    }
    return next;
  },
  provide: (field) => EditorView.decorations.from(field),
});

// --- Editores pequeños (formularios) -----------------------------------------------------------

/** Nombres para completar en un formulario (sin servidor: los del modelo y lo predefinido). */
export type NameSource = () => { label: string; detail?: string; type?: string }[];

export function nameCompletion(names: NameSource): Extension {
  const source = (context: CompletionContext): CompletionResult | null => {
    const word = context.matchBefore(/[A-Za-z_][A-Za-z0-9_]*/);
    if (!word || (word.from === word.to && !context.explicit)) return null;
    return {
      from: word.from,
      options: names().map((n) => ({
        label: n.label,
        detail: n.detail,
        type: n.type ?? "variable",
      })),
      validFor: /^[A-Za-z0-9_]*$/,
    };
  };
  return autocompletion({ override: [source], activateOnTyping: true });
}

export function miniSetup(names: NameSource, multiline: boolean): Extension {
  return [
    drawSelection(),
    bracketMatching(),
    closeBrackets(),
    history(),
    indentUnit.of("  "),
    nomos(),
    nomosTheme(),
    nameCompletion(names),
    multiline ? [] : EditorView.lineWrapping,
    keymap.of([...closeBracketsKeymap, ...defaultKeymap, ...historyKeymap, ...completionKeymap]),
  ];
}
