// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * El diagrama de un juego como imagen SVG estática (el mismo dibujo que el Studio, sin editar).
 * Con `base`, el diff visual de una propuesta: lo añadido en verde, lo quitado en rojo
 * (discontinuo, como fantasma) y lo cambiado en ámbar.
 */

import { useMessages } from "@gamehub/i18n";
import {
  autoLayout,
  buildGraph,
  diffModels,
  type GameModel,
  type ModelDiff,
  place,
  toSvg,
  withGhosts,
} from "@gamehub/studio";
import { Spinner } from "@gamehub/ui-kit";
import { useEffect, useState } from "react";
import { messages } from "./messages";

export function GameDiagram(props: { game: GameModel; base?: GameModel | null; title?: string }) {
  const t = useMessages(messages);
  const [svg, setSvg] = useState<string | null>(null);
  const [diff, setDiff] = useState<ModelDiff | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { game, base, title } = props;

  useEffect(() => {
    let live = true;
    setSvg(null);
    const changes = base ? diffModels(base, game) : null;
    const model = changes ? withGhosts(game, changes) : game;
    const graph = buildGraph(model, { diff: changes?.status ?? null });
    autoLayout(graph).then(
      (auto) => {
        if (!live) return;
        setSvg(toSvg(graph, place(graph, undefined, auto), title ?? ""));
        setDiff(changes);
      },
      (e: unknown) => live && setError(e instanceof Error ? e.message : String(e)),
    );
    return () => {
      live = false;
    };
  }, [game, base, title]);

  if (error) return <p className="gh-shell-error">{error}</p>;
  if (!svg) return <Spinner label={t("loading")} />;
  return (
    <div className="hub-diagram">
      {diff && (
        <p className="hub-diff-summary">
          <span className="hub-diff hub-diff--added">
            {t("diffAdded", { n: diff.summary.added.length })}
          </span>
          <span className="hub-diff hub-diff--removed">
            {t("diffRemoved", { n: diff.summary.removed.length })}
          </span>
          <span className="hub-diff hub-diff--changed">
            {t("diffChanged", { n: diff.summary.changed.length })}
          </span>
          {[...diff.summary.added, ...diff.summary.removed, ...diff.summary.changed].length > 0 && (
            <span className="gh-muted">
              {" "}
              (
              {[...diff.summary.added, ...diff.summary.removed, ...diff.summary.changed].join(", ")}
              )
            </span>
          )}
        </p>
      )}
      <img
        className="hub-diagram__img"
        alt={t("diagramAlt", { name: game.name })}
        src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`}
      />
    </div>
  );
}
