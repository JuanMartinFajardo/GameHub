// SPDX-License-Identifier: AGPL-3.0-or-later
/** Un archivo en CodeMirror con el resaltado de Nomos (el de los editores del Studio); de solo
 * lectura o editable. */

import { EditorState } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { mainSetup } from "@gamehub/studio";
import { useEffect, useRef } from "react";

export function CodeEditor(props: {
  path: string;
  text: string;
  readOnly?: boolean;
  onChange?: (text: string) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const onChange = useRef(props.onChange);
  onChange.current = props.onChange;

  // biome-ignore lint/correctness/useExhaustiveDependencies: un editor por archivo y texto inicial.
  useEffect(() => {
    if (!host.current) return;
    const view = new EditorView({
      parent: host.current,
      state: EditorState.create({
        doc: props.text,
        extensions: [
          mainSetup(),
          EditorState.readOnly.of(props.readOnly ?? false),
          EditorView.editable.of(!props.readOnly),
          EditorView.updateListener.of((u) => {
            if (u.docChanged) onChange.current?.(u.state.doc.toString());
          }),
        ],
      }),
    });
    return () => view.destroy();
  }, [props.path, props.readOnly]);

  return <div className="hub-editor" ref={host} />;
}
