// SPDX-License-Identifier: Apache-2.0
/** El inspector: el formulario de lo seleccionado (el juego, un nodo, una acción, una transición). */

import { useMessages } from "@gamehub/i18n";
import { useStudio } from "../context";
import { messages } from "../messages";
import type { GameModel } from "../types";
import { ActionForm, NodeForm, TransitionList } from "./flow";
import { GameForm } from "./game";

export function Inspector(props: { game: GameModel; onDesigner: () => void }) {
  const { game } = props;
  const t = useMessages(messages);
  const [state, studio] = useStudio();
  const selection = state.selection;
  if (selection.kind === "game") return <GameForm game={game} onDesigner={props.onDesigner} />;
  const node = game.flow.nodes.find((n) => n.id === selection.node);
  if (!node) {
    return (
      <div className="gh-sd-form">
        <p className="gh-sd-note">{t("selectNode")}</p>
      </div>
    );
  }
  if (selection.kind === "node") return <NodeForm game={game} node={node} />;
  const action =
    "action" in selection && selection.action
      ? node.actions.find((a) => a.name === selection.action)
      : null;
  if (selection.kind === "action") {
    return action ? (
      <ActionForm game={game} node={node} action={action} />
    ) : (
      <NodeForm game={game} node={node} />
    );
  }
  // Una transición: la lista de su nodo o acción, con ella resaltada.
  return (
    <div className="gh-sd-form" data-form="transition">
      <header className="gh-sd-form__head">
        <button
          type="button"
          className="gh-sd-back"
          onClick={() =>
            studio.select(
              action
                ? { kind: "action", node: node.id, action: action.name }
                : { kind: "node", node: node.id },
            )
          }
        >
          ← {action ? `${node.id}.${action.name}` : node.id}
        </button>
        <h2>{t("transition")}</h2>
      </header>
      <TransitionList
        game={game}
        node={node}
        action={action ?? null}
        list={action ? action.transitions : node.transitions}
        targets={game.flow.nodes}
        editable={(action ?? node).local}
      />
    </div>
  );
}
