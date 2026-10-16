// SPDX-License-Identifier: Apache-2.0
/** Los formularios del flow: un nodo, una acción y sus transiciones. */

import { useLocale, useMessages } from "@gamehub/i18n";
import { NODE_KINDS } from "@gamehub/nomos";
import { Button, cx } from "@gamehub/ui-kit";
import { useMemo, useState } from "react";
import { useStudio } from "../context";
import { kindName } from "../diagram/nodes";
import { messages } from "../messages";
import type { ActionModel, GameModel, NodeModel, Op, TransitionModel } from "../types";
import { CodeField, IconButton, Section, SelectField, TextField } from "./fields";
import { namesOf } from "./names";

function docText(doc: unknown): string {
  if (typeof doc === "string") return doc;
  if (doc && typeof doc === "object")
    return String((doc as Record<string, string>).es ?? Object.values(doc)[0] ?? "");
  return "";
}

function useNames(game: GameModel, locals: string[] = []) {
  const [, studio] = useStudio();
  // biome-ignore lint/correctness/useExhaustiveDependencies: los nombres se leen al completar.
  return useMemo(
    () =>
      namesOf(
        () => studio.game ?? game,
        () => locals,
      ),
    [studio, locals.join(",")],
  );
}

const MEMBER_LABELS = {
  actor: "actor",
  actors: "actors",
  eligible: "eligible",
  order: "order",
  payoff: "payoff",
  rank: "rank",
} as const;

export function NodeForm(props: { game: GameModel; node: NodeModel }) {
  const { game, node } = props;
  const t = useMessages(messages);
  const { locale } = useLocale();
  const [state, studio] = useStudio();
  const names = useNames(game);
  const editable = node.local;
  const key = (field: string) => `node:${node.id}:${field}`;
  const others = game.flow.nodes.filter((n) => n.id !== node.id);
  const children = game.flow.nodes.filter((n) => n.parent === node.id);
  const members: (keyof typeof MEMBER_LABELS)[] =
    node.kind === "decision"
      ? ["actor"]
      : node.kind === "simultaneous"
        ? ["actors"]
        : node.kind === "window"
          ? ["eligible", "order"]
          : node.kind === "terminal"
            ? ["payoff", "rank"]
            : [];
  return (
    <div className="gh-sd-form" data-form={`node:${node.id}`}>
      <header className="gh-sd-form__head">
        <span className="gh-sd-form__kind">{kindName(node.kind, locale)}</span>
        <h2>{node.id}</h2>
        <div className="gh-sd-form__tools">
          <IconButton label={t("breakpoint")} onClick={() => studio.toggleBreakpoint(node.id)}>
            <span className={cx("gh-sd-dot", state.breakpoints.includes(node.id) && "is-on")} />
          </IconButton>
          {editable ? (
            <IconButton
              label={t("delete")}
              danger
              onClick={() => studio.tryApply([{ op: "deleteNode", node: node.id }], key("delete"))}
            >
              🗑
            </IconButton>
          ) : null}
        </div>
      </header>
      {!editable ? <p className="gh-sd-note">{t("inherited")}</p> : null}
      <TextField
        label={t("name")}
        value={node.id}
        mono
        readOnly={!editable}
        failureKey={key("name")}
        ops={(name) => [{ op: "rename", key: `node:${node.id}`, name }]}
      />
      <SelectField
        label={t("kind")}
        value={node.kind}
        disabled={!editable}
        options={NODE_KINDS.map((k) => ({ value: k, label: kindName(k, locale) }))}
        onChange={(kind) =>
          studio.tryApply([{ op: "setNodeKind", node: node.id, kind }], key("kind"))
        }
      />
      <TextField
        label={t("doc")}
        value={docText(node.doc)}
        readOnly={!editable}
        failureKey={key("doc")}
        ops={(doc) => [{ op: "setDoc", target: { node: node.id }, doc: doc || null }]}
      />
      {node.kind === "window" ? (
        <SelectField
          label={t("mode")}
          value={node.members.mode ?? "priority"}
          disabled={!editable}
          options={["priority", "collect", "race"].map((m) => ({ value: m, label: m }))}
          onChange={(mode) =>
            studio.tryApply(
              [{ op: "setMember", node: node.id, key: "mode", value: mode }],
              key("mode"),
            )
          }
        />
      ) : null}
      {node.kind === "terminal" ? <LetsField game={game} node={node} /> : null}
      {members.map((m) => (
        <CodeField
          key={m}
          label={t(m)}
          value={node.members[m] ?? ""}
          names={names}
          readOnly={!editable}
          failureKey={key(m)}
          ops={(value) => [
            { op: "setMember", node: node.id, key: MEMBER_LABELS[m], value: value || null },
          ]}
        />
      ))}
      {node.kind === "phase" ? (
        <>
          <SelectField
            label={t("phaseStart")}
            value={node.start?.target ?? ""}
            disabled={!editable}
            options={[
              { value: "", label: "—" },
              ...children.map((c) => ({ value: c.id, label: c.id })),
            ]}
            onChange={(target) =>
              target && studio.tryApply([{ op: "setStart", phase: node.id, target }], key("start"))
            }
          />
          {(["on_enter", "on_exit"] as const).map((block) => (
            <CodeField
              key={block}
              label={t(block === "on_enter" ? "onEnter" : "onExit")}
              value={node.blocks[block] ?? ""}
              names={names}
              multiline
              readOnly={!editable}
              failureKey={key(block)}
              ops={(value) => [{ op: "setBlock", node: node.id, key: block, value: value || null }]}
            />
          ))}
        </>
      ) : null}
      {node.kind === "simultaneous" ? (
        <CodeField
          label={t("resolve")}
          value={node.blocks.resolve ?? ""}
          names={names}
          multiline
          readOnly={!editable}
          failureKey={key("resolve")}
          ops={(value) => [{ op: "setBlock", node: node.id, key: "resolve", value: value || null }]}
        />
      ) : null}
      {node.kind === "chance" || node.kind === "auto" ? (
        <CodeField
          label={t("effects")}
          value={node.effects ?? ""}
          names={names}
          multiline
          readOnly={!editable}
          failureKey={key("effects")}
          ops={(value) => [{ op: "setBlock", node: node.id, key: "effects", value }]}
        />
      ) : null}
      {node.kind === "decision" || node.kind === "simultaneous" || node.kind === "window" ? (
        <Section
          title={t("actions")}
          actions={
            editable ? (
              <IconButton
                label={t("addAction")}
                onClick={() =>
                  studio.tryApply([{ op: "addAction", node: node.id }], key("addAction"))
                }
              >
                ＋
              </IconButton>
            ) : null
          }
        >
          {node.actions.length === 0 ? <p className="gh-sd-note">—</p> : null}
          <ul className="gh-sd-list">
            {node.actions.map((a, i) => (
              <li key={a.name}>
                <button
                  type="button"
                  className="gh-sd-list__main"
                  onClick={() => studio.select({ kind: "action", node: node.id, action: a.name })}
                >
                  <code>
                    {a.name}({a.params.map((p) => p.name).join(", ")})
                  </code>
                </button>
                {editable ? (
                  <span className="gh-sd-list__tools">
                    <IconButton
                      label={t("up")}
                      disabled={i === 0}
                      onClick={() =>
                        studio.tryApply([
                          { op: "moveAction", node: node.id, action: a.name, index: i - 1 },
                        ])
                      }
                    >
                      ↑
                    </IconButton>
                    <IconButton
                      label={t("delete")}
                      danger
                      onClick={() =>
                        studio.tryApply([{ op: "deleteAction", node: node.id, action: a.name }])
                      }
                    >
                      ✕
                    </IconButton>
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        </Section>
      ) : null}
      {node.kind !== "terminal" ? (
        <TransitionList
          game={game}
          node={node}
          action={null}
          list={node.transitions}
          targets={others.length ? game.flow.nodes : []}
          editable={editable}
        />
      ) : null}
    </div>
  );
}

function LetsField(props: { game: GameModel; node: NodeModel }) {
  const { node } = props;
  const t = useMessages(messages);
  const names = useNames(props.game);
  const text = node.lets.map((l) => `${l.name} = ${l.value}`).join("\n");
  return (
    <CodeField
      label={t("lets")}
      value={text}
      names={names}
      multiline
      readOnly={!node.local}
      failureKey={`node:${node.id}:lets`}
      placeholder="x = expresión"
      ops={(value) => [
        {
          op: "setLets",
          node: node.id,
          lets: value
            .split("\n")
            .filter((l) => l.trim())
            .map((l) => {
              const at = l.indexOf("=");
              return { name: l.slice(0, at).trim(), value: l.slice(at + 1).trim() };
            }),
        },
      ]}
    />
  );
}

/** Las transiciones de un nodo o de una acción, en orden, con su destino, condición y efectos. */
export function TransitionList(props: {
  game: GameModel;
  node: NodeModel;
  action: ActionModel | null;
  list: TransitionModel[];
  targets: NodeModel[];
  editable: boolean;
}) {
  const { game, node, action, list, editable } = props;
  const t = useMessages(messages);
  const [state, studio] = useStudio();
  const names = useNames(game, action ? action.params.map((p) => p.name) : []);
  const [target, setTarget] = useState("");
  const base = (index: number): Op => {
    const op: Op = { op: "updateTransition", node: node.id, index };
    if (action) op.action = action.name;
    return op;
  };
  const selected = state.selection.kind === "transition" ? state.selection : null;
  const targets = [...game.flow.nodes.map((n) => n.id), ...(node.parent ? ["exit"] : [])];
  const key = (i: number, field: string) =>
    `transition:${node.id}:${action?.name ?? ""}:${i}:${field}`;
  return (
    <Section title={t("transitions")}>
      <ol className="gh-sd-transitions">
        {list.map((tr, i) => {
          const isSelected =
            selected?.node === node.id &&
            (selected.action ?? null) === (action?.name ?? null) &&
            selected.index === i;
          return (
            <li
              // biome-ignore lint/suspicious/noArrayIndexKey: una transición no tiene más identidad que su lugar en la lista.
              key={`${i}:${tr.target}`}
              className={cx("gh-sd-transition", isSelected && "is-selected")}
            >
              <div className="gh-sd-transition__head">
                <span className="gh-sd-transition__order">{i + 1}.</span>
                <select
                  className="gh-sd-input"
                  aria-label={t("target")}
                  value={tr.target}
                  disabled={!editable}
                  onChange={(e) =>
                    studio.tryApply([{ ...base(i), target: e.target.value }], key(i, "target"))
                  }
                >
                  {targets.map((id) => (
                    <option key={id} value={id}>
                      → {id}
                    </option>
                  ))}
                </select>
                {editable ? (
                  <span className="gh-sd-list__tools">
                    <IconButton
                      label={t("up")}
                      disabled={i === 0}
                      onClick={() => {
                        const op: Op = { op: "moveTransition", node: node.id, index: i, to: i - 1 };
                        if (action) op.action = action.name;
                        studio.tryApply([op]);
                      }}
                    >
                      ↑
                    </IconButton>
                    <IconButton
                      label={t("down")}
                      disabled={i === list.length - 1}
                      onClick={() => {
                        const op: Op = { op: "moveTransition", node: node.id, index: i, to: i + 1 };
                        if (action) op.action = action.name;
                        studio.tryApply([op]);
                      }}
                    >
                      ↓
                    </IconButton>
                    <IconButton
                      label={t("delete")}
                      danger
                      onClick={() => {
                        const op: Op = { op: "deleteTransition", node: node.id, index: i };
                        if (action) op.action = action.name;
                        studio.tryApply([op]);
                      }}
                    >
                      ✕
                    </IconButton>
                  </span>
                ) : null}
              </div>
              <CodeField
                label={t("when")}
                value={tr.when ?? ""}
                names={names}
                readOnly={!editable}
                placeholder={list.length > 1 && i === list.length - 1 ? t("otherwise") : ""}
                failureKey={key(i, "when")}
                ops={(value) => [{ ...base(i), when: value || null }]}
              />
              <CodeField
                label={t("effects")}
                value={tr.effects ?? ""}
                names={names}
                multiline
                readOnly={!editable}
                failureKey={key(i, "effects")}
                ops={(value) => [{ ...base(i), effects: value || null }]}
              />
            </li>
          );
        })}
      </ol>
      {editable ? (
        <div className="gh-sd-row">
          <select
            className="gh-sd-input"
            aria-label={t("target")}
            value={target}
            onChange={(e) => setTarget(e.target.value)}
          >
            <option value="">{t("target")}…</option>
            {targets.map((id) => (
              <option key={id} value={id}>
                → {id}
              </option>
            ))}
          </select>
          <Button
            size="sm"
            disabled={!target}
            onClick={() => {
              const op: Op = { op: "addTransition", node: node.id, target };
              if (action) op.action = action.name;
              studio.tryApply([op], key(list.length, "add")).then(() => setTarget(""));
            }}
          >
            {t("addTransition")}
          </Button>
        </div>
      ) : null}
    </Section>
  );
}

export function ActionForm(props: { game: GameModel; node: NodeModel; action: ActionModel }) {
  const { game, node, action } = props;
  const t = useMessages(messages);
  const [, studio] = useStudio();
  const editable = action.local;
  const names = useNames(
    game,
    action.params.map((p) => p.name),
  );
  const key = (field: string) => `action:${node.id}:${action.name}:${field}`;
  const paramsText = action.params
    .map(
      (p) =>
        `${p.visibility ? `@visible(${p.visibility}) ` : ""}${p.name}${p.type ? `: ${p.type}` : ""}${p.domain ? ` in ${p.domain}` : ""}`,
    )
    .join("\n");
  return (
    <div className="gh-sd-form" data-form={`action:${node.id}.${action.name}`}>
      <header className="gh-sd-form__head">
        <button
          type="button"
          className="gh-sd-back"
          onClick={() => studio.select({ kind: "node", node: node.id })}
        >
          ← {node.id}
        </button>
        <h2>
          <code>{action.name}</code>
        </h2>
        {editable ? (
          <div className="gh-sd-form__tools">
            <IconButton
              label={t("delete")}
              danger
              onClick={() =>
                studio.tryApply([{ op: "deleteAction", node: node.id, action: action.name }])
              }
            >
              🗑
            </IconButton>
          </div>
        ) : null}
      </header>
      <TextField
        label={t("name")}
        value={action.name}
        mono
        readOnly={!editable}
        failureKey={key("name")}
        ops={(name) => [{ op: "rename", key: `action:${action.name}`, name }]}
      />
      <TextField
        label={t("doc")}
        value={docText(action.doc)}
        readOnly={!editable}
        failureKey={key("doc")}
        ops={(doc) => [
          { op: "setDoc", target: { node: node.id, action: action.name }, doc: doc || null },
        ]}
      />
      <CodeField
        label={t("parameters")}
        value={paramsText}
        names={names}
        multiline
        readOnly={!editable}
        placeholder="c in cells(board)"
        hint="nombre: Tipo in dominio — uno por línea"
        failureKey={key("params")}
        ops={(value) => [
          { op: "updateAction", node: node.id, action: action.name, params: parseParams(value) },
        ]}
      />
      <CodeField
        label={t("requires")}
        value={action.requires ?? ""}
        names={names}
        readOnly={!editable}
        failureKey={key("requires")}
        ops={(value) => [
          { op: "updateAction", node: node.id, action: action.name, requires: value || null },
        ]}
      />
      <CodeField
        label={t("effects")}
        value={action.effects ?? ""}
        names={names}
        multiline
        readOnly={!editable}
        failureKey={key("effects")}
        ops={(value) => [
          { op: "updateAction", node: node.id, action: action.name, effects: value || null },
        ]}
      />
      {node.kind !== "simultaneous" ? (
        <TransitionList
          game={game}
          node={node}
          action={action}
          list={action.transitions}
          targets={game.flow.nodes}
          editable={editable}
        />
      ) : null}
    </div>
  );
}

/** `@visible(none) cards in subsets(...)`, `c: Choice`, `n: Int in 1..6` → parámetros de la edición. */
export function parseParams(text: string): Record<string, string | null>[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      let rest = line;
      let visibility: string | null = null;
      const vis = rest.match(/^@visible\((.*?)\)\s*/);
      if (vis) {
        visibility = vis[1] ?? null;
        rest = rest.slice(vis[0].length);
      }
      const inAt = rest.search(/\sin\s/);
      const head = inAt >= 0 ? rest.slice(0, inAt) : rest;
      const domain = inAt >= 0 ? rest.slice(inAt + 4).trim() : null;
      const colon = head.indexOf(":");
      const name = (colon >= 0 ? head.slice(0, colon) : head).trim();
      const type = colon >= 0 ? head.slice(colon + 1).trim() : null;
      return { name, type, domain, visibility };
    });
}
