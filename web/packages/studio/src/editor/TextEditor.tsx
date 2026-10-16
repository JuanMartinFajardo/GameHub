// SPDX-License-Identifier: Apache-2.0
/**
 * El editor de texto del Studio: CodeMirror con Nomos y el servidor de lenguaje (diagnósticos,
 * autocompletado, hover, ir a la definición, renombrar, formato). Resalta lo seleccionado en el
 * diagrama y, al mover el cursor, selecciona en el diagrama lo que hay bajo él.
 */

import { EditorState } from "@codemirror/state";
import { EditorView, keymap } from "@codemirror/view";
import { useEffect, useRef } from "react";
import { elementAt } from "../diagram/graph";
import type { Studio } from "../store";
import type { GameModel, Selection, Span } from "../types";
import { mainSetup, setElementHighlight } from "./setup";

export interface TextEditorProps {
  studio: Studio;
  uri: string;
  text: string;
  selection: Selection;
  game: GameModel | null;
  hidden?: boolean;
}

/** Dónde está en el texto lo seleccionado. */
export function spanOf(game: GameModel | null, selection: Selection): Span | null {
  if (!game || selection.kind === "game") return null;
  const node = game.flow.nodes.find((n) => n.id === selection.node);
  if (!node) return null;
  if (selection.kind === "node") return node.fullSpan ?? node.span;
  const action =
    "action" in selection && selection.action
      ? node.actions.find((a) => a.name === selection.action)
      : null;
  if (selection.kind === "action") return action?.span ?? null;
  const list = action ? action.transitions : node.transitions;
  return list[selection.index]?.span ?? null;
}

export function TextEditor(props: TextEditorProps) {
  const host = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);
  const { studio, uri, text } = props;
  const latest = useRef(props);
  latest.current = props;

  // Un editor por archivo: al cambiar de archivo se crea otro (y el LSP abre el documento nuevo).
  // biome-ignore lint/correctness/useExhaustiveDependencies: el texto inicial solo cuenta al abrir.
  useEffect(() => {
    if (!host.current) return;
    let cursorTimer: ReturnType<typeof setTimeout> | null = null;
    const view = new EditorView({
      parent: host.current,
      state: EditorState.create({
        doc: text,
        extensions: [
          mainSetup(),
          studio.connection.client.plugin(uri, "nomos"),
          keymap.of([
            {
              key: "Mod-s",
              preventDefault: true,
              run: () => {
                studio.save().catch(() => undefined);
                return true;
              },
            },
          ]),
          EditorView.updateListener.of((update) => {
            if (update.docChanged) studio.markDirty();
            const user = update.transactions.some(
              (tr) =>
                tr.isUserEvent("select") || tr.isUserEvent("input") || tr.isUserEvent("delete"),
            );
            if (
              update.selectionSet &&
              user &&
              !update.transactions.some((tr) => tr.isUserEvent("input.studio"))
            ) {
              if (cursorTimer) clearTimeout(cursorTimer);
              const offset = update.state.selection.main.head;
              cursorTimer = setTimeout(() => {
                const game = latest.current.game;
                const found = game ? elementAt(game, offset) : null;
                if (found) studio.select(found);
              }, 250);
            }
          }),
        ],
      }),
    });
    viewRef.current = view;
    studio.editor = view;
    return () => {
      if (cursorTimer) clearTimeout(cursorTimer);
      if (studio.editor === view) studio.editor = null;
      view.destroy();
      viewRef.current = null;
    };
  }, [uri, studio]);

  // Lo seleccionado en el diagrama se resalta (y se enseña) en el texto.
  useEffect(() => {
    const view = viewRef.current;
    if (!view) return;
    const span = spanOf(props.game, props.selection);
    const length = view.state.doc.length;
    if (!span || span[1] > length) {
      view.dispatch({ effects: setElementHighlight.of(null) });
      return;
    }
    const [from, to] = span;
    const head = view.state.selection.main.head;
    const effects = [setElementHighlight.of({ from, to })];
    if (head < from || head > to)
      effects.push(EditorView.scrollIntoView(from, { y: "center" }) as never);
    view.dispatch({ effects });
  }, [props.selection, props.game]);

  return <div ref={host} className="gh-sd-text" hidden={props.hidden} data-testid="text-editor" />;
}
