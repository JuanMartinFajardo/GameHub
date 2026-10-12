// SPDX-License-Identifier: Apache-2.0
/**
 * Un campo de Nomos para los formularios (una expresión, un tipo, unas sentencias): un editor
 * pequeño con resaltado y autocompletado de los nombres del juego. El valor se confirma al salir
 * del campo, con Intro (en los de una línea) o con Ctrl/Cmd+Intro; Esc lo deja como estaba. Si
 * el servidor rechaza lo escrito, el error se marca en el sitio.
 */

import { EditorState, Prec } from "@codemirror/state";
import { Decoration, EditorView, keymap } from "@codemirror/view";
import { cx } from "@gamehub/ui-kit";
import { useEffect, useRef } from "react";
import type { FragmentError } from "../types";
import { miniSetup, type NameSource } from "./setup";

export interface MiniEditorProps {
  value: string;
  onCommit: (value: string) => void;
  names: NameSource;
  multiline?: boolean;
  placeholder?: string;
  label: string;
  errors?: FragmentError[];
  readOnly?: boolean;
  id?: string;
}

const errorMark = Decoration.mark({ class: "gh-sd-mini-error" });

export function MiniEditor(props: MiniEditorProps) {
  const host = useRef<HTMLDivElement>(null);
  const view = useRef<EditorView | null>(null);
  const committed = useRef(props.value);
  const latest = useRef(props);
  latest.current = props;

  // biome-ignore lint/correctness/useExhaustiveDependencies: el editor se crea una vez por campo.
  useEffect(() => {
    if (!host.current) return;
    const commit = () => {
      const current = view.current?.state.doc.toString() ?? "";
      if (current !== committed.current) {
        committed.current = current;
        latest.current.onCommit(current);
      }
      return true;
    };
    const revert = () => {
      const v = view.current;
      if (!v) return false;
      v.dispatch({ changes: { from: 0, to: v.state.doc.length, insert: committed.current } });
      return true;
    };
    const keys = keymap.of([
      { key: "Mod-Enter", run: commit },
      { key: "Escape", run: revert },
      ...(props.multiline ? [] : [{ key: "Enter", run: commit }]),
    ]);
    view.current = new EditorView({
      parent: host.current,
      state: EditorState.create({
        doc: props.value,
        extensions: [
          Prec.highest(keys),
          miniSetup(() => latest.current.names(), props.multiline ?? false),
          EditorState.readOnly.of(props.readOnly ?? false),
          EditorView.contentAttributes.of({
            "aria-label": props.label,
            ...(props.id ? { id: props.id } : {}),
          }),
          EditorView.domEventHandlers({ blur: () => commit() }),
          EditorView.decorations.of((v) => {
            const errors = latest.current.errors ?? [];
            const length = v.state.doc.length;
            const marks = errors
              .filter((e) => e.offset <= length)
              .map((e) =>
                errorMark.range(
                  Math.min(e.offset, Math.max(0, length - 1)),
                  Math.min(length, Math.max(e.offset + Math.max(e.length, 1), e.offset + 1)),
                ),
              )
              .filter((r) => r.to > r.from);
            return Decoration.set(marks, true);
          }),
        ],
      }),
    });
    return () => {
      view.current?.destroy();
      view.current = null;
    };
  }, []);

  // Cuando cambia el valor desde fuera (otra edición, otro elemento), se actualiza; si se está
  // escribiendo algo sin confirmar, no se pisa.
  useEffect(() => {
    const v = view.current;
    if (!v) return;
    const doc = v.state.doc.toString();
    if (doc === props.value) {
      committed.current = props.value;
      return;
    }
    if (!v.hasFocus || doc === committed.current) {
      committed.current = props.value;
      v.dispatch({ changes: { from: 0, to: doc.length, insert: props.value } });
    }
  }, [props.value]);

  // Las marcas de error se leen de `latest`: basta una transacción vacía para repintarlas.
  // biome-ignore lint/correctness/useExhaustiveDependencies: se repinta cuando cambian los errores.
  useEffect(() => {
    view.current?.dispatch({});
  }, [props.errors]);

  return (
    <div
      ref={host}
      className={cx(
        "gh-sd-mini",
        props.multiline && "is-multiline",
        (props.errors?.length ?? 0) > 0 && "has-error",
      )}
      data-placeholder={props.placeholder}
    />
  );
}
