// SPDX-License-Identifier: Apache-2.0
/** Las flechas del diagrama: una transición, con su número de orden y su condición. */

import { cx } from "@gamehub/ui-kit";
import {
  BaseEdge,
  type Edge,
  EdgeLabelRenderer,
  type EdgeProps,
  getBezierPath,
  getSmoothStepPath,
  Position,
} from "@xyflow/react";
import type { EdgeData } from "./graph";

export type TransitionEdge = Edge<EdgeData, "transition">;

export function TransitionView(props: EdgeProps<TransitionEdge>) {
  const { data, selected, markerEnd, label } = props;
  const loop = props.source === props.target;
  const backwards = props.targetY < props.sourceY - 4;
  const [path, labelX, labelY] =
    loop || backwards
      ? getBezierPath({
          sourceX: props.sourceX,
          sourceY: props.sourceY,
          sourcePosition: loop ? Position.Right : props.sourcePosition,
          targetX: props.targetX,
          targetY: props.targetY,
          targetPosition: loop ? Position.Right : props.targetPosition,
          curvature: loop ? 1.2 : 0.4,
        })
      : getSmoothStepPath({
          sourceX: props.sourceX,
          sourceY: props.sourceY,
          sourcePosition: props.sourcePosition,
          targetX: props.targetX,
          targetY: props.targetY,
          targetPosition: props.targetPosition,
          borderRadius: 10,
        });
  const covered = data?.covered;
  const width = covered ? Math.min(6, 1.5 + Math.log10(covered + 1)) : undefined;
  const className = cx(
    "gh-sd-edge",
    selected && "is-selected",
    data?.taken && "is-taken",
    covered === 0 && "is-uncovered",
    data?.diff && `is-${data.diff}`,
    data?.start && "is-start",
  );
  const text = [data?.order ? `${data.order}.` : null, label ? String(label) : null]
    .filter(Boolean)
    .join(" ");
  return (
    <>
      <BaseEdge
        id={props.id}
        path={path}
        markerEnd={markerEnd}
        className={className}
        style={width ? { strokeWidth: width } : undefined}
        interactionWidth={18}
      />
      {text ? (
        <EdgeLabelRenderer>
          <div
            className={cx(
              "gh-sd-edge-label",
              "nodrag",
              "nopan",
              selected && "is-selected",
              className,
            )}
            style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }}
            title={[data?.when ? `when ${data.when}` : null, data?.effects]
              .filter(Boolean)
              .join("\n")}
            data-edge={props.id}
          >
            {text}
            {covered !== undefined && covered !== null ? (
              <span className="gh-sd-count">{covered}</span>
            ) : null}
          </div>
        </EdgeLabelRenderer>
      ) : null}
    </>
  );
}

export const edgeTypes = { transition: TransitionView };
