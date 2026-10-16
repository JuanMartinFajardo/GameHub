// SPDX-License-Identifier: Apache-2.0
/**
 * Los formularios del juego: título, jugadores, estado, opciones, tipos, funciones, pistas de la
 * interfaz, tests e invariantes.
 */

import { useMessages } from "@gamehub/i18n";
import { Button } from "@gamehub/ui-kit";
import { useMemo, useState } from "react";
import { useStudio } from "../context";
import { messages } from "../messages";
import type { GameModel, Op, TestReport } from "../types";
import { CodeField, IconButton, Section, TextField } from "./fields";
import { namesOf } from "./names";

function text(value: unknown, lang: "es" | "en"): string {
  if (typeof value === "string") return value;
  if (value && typeof value === "object")
    return String((value as Record<string, string>)[lang] ?? "");
  return "";
}

export function GameForm(props: { game: GameModel; onDesigner: () => void }) {
  const { game } = props;
  const t = useMessages(messages);
  const [, studio] = useStudio();
  const [tab, setTab] = useState<"state" | "params" | "types" | "functions" | "ui" | "tests">(
    "state",
  );
  const title = game.meta.title;
  const setTitle = (lang: "es" | "en", value: string): Op[] => {
    const other = lang === "es" ? "en" : "es";
    const next: Record<string, string> = {};
    const keep = text(title, other);
    if (lang === "es" && value) next.es = value;
    if (keep) next[other] = keep;
    if (lang === "en" && value) next.en = value;
    return [{ op: "setMeta", key: "title", value: Object.keys(next).length ? next : null }];
  };
  return (
    <div className="gh-sd-form" data-form="game">
      <header className="gh-sd-form__head">
        <span className="gh-sd-form__kind">game</span>
        <h2>{game.name}</h2>
      </header>
      {game.extends ? <p className="gh-sd-note">extends {game.extends}</p> : null}
      <TextField
        label={t("titleEs")}
        value={text(title, "es")}
        failureKey="meta:title:es"
        ops={(v) => setTitle("es", v)}
      />
      <TextField
        label={t("titleEn")}
        value={text(title, "en")}
        failureKey="meta:title:en"
        ops={(v) => setTitle("en", v)}
      />
      <TextField
        label={t("version")}
        value={text(game.meta.version, "es")}
        mono
        failureKey="meta:version"
        ops={(v) => [{ op: "setMeta", key: "version", value: v || null }]}
      />
      <div className="gh-sd-row">
        <PlayersField game={game} />
      </div>
      <div className="gh-sd-tabs" role="tablist">
        {(["state", "params", "types", "functions", "ui", "tests"] as const).map((k) => (
          <button
            key={k}
            type="button"
            role="tab"
            aria-selected={tab === k}
            className={tab === k ? "is-active" : ""}
            onClick={() => setTab(k)}
          >
            {t(k === "ui" ? "hints" : k)}
          </button>
        ))}
      </div>
      {tab === "state" ? <StateTable game={game} /> : null}
      {tab === "params" ? <ParamsTable game={game} /> : null}
      {tab === "types" ? <TypesTable game={game} /> : null}
      {tab === "functions" ? <FunctionsTable game={game} /> : null}
      {tab === "ui" ? <UiTable game={game} /> : null}
      {tab === "tests" ? <TestsTable game={game} /> : null}
      <div className="gh-sd-row">
        <Button size="sm" variant="ghost" onClick={props.onDesigner}>
          🧩 {t("designer")}
        </Button>
        <Button size="sm" variant="ghost" onClick={() => studio.select({ kind: "game" })}>
          ↺
        </Button>
      </div>
    </div>
  );
}

function PlayersField(props: { game: GameModel }) {
  const t = useMessages(messages);
  const [, studio] = useStudio();
  const players = props.game.players ?? { min: 2, max: 2, local: true };
  const set = (min: number, max: number) =>
    studio.tryApply([{ op: "setPlayers", min, max: Math.max(min, max) }], "players");
  return (
    <fieldset className="gh-sd-players">
      <legend>{t("players")}</legend>
      <label>
        {t("min")}
        <input
          type="number"
          min={1}
          max={16}
          className="gh-sd-input"
          value={players.min}
          onChange={(e) => set(Number(e.target.value), players.max)}
        />
      </label>
      <label>
        {t("max")}
        <input
          type="number"
          min={1}
          max={16}
          className="gh-sd-input"
          value={players.max}
          onChange={(e) => set(players.min, Number(e.target.value))}
        />
      </label>
    </fieldset>
  );
}

function useNames(game: GameModel) {
  const [, studio] = useStudio();
  return useMemo(() => namesOf(() => studio.game ?? game), [studio, game]);
}

/** El selector de visibilidad: todos, nadie, el dueño o una condición. */
function VisibilityField(props: {
  value: string | null;
  onChange: (value: string | null) => void;
  owned: boolean;
}) {
  const t = useMessages(messages);
  const mode =
    props.value === null || props.value === "all"
      ? "all"
      : props.value === "none"
        ? "none"
        : props.value === "owner"
          ? "owner"
          : "custom";
  const [custom, setCustom] = useState(mode === "custom" ? (props.value ?? "") : "");
  return (
    <div className="gh-sd-row">
      <select
        className="gh-sd-input"
        aria-label={t("visibility")}
        value={mode}
        onChange={(e) => {
          const v = e.target.value;
          if (v === "custom") props.onChange(custom || "viewer == owner");
          else props.onChange(v === "all" ? null : v);
        }}
      >
        <option value="all">{t("visAll")}</option>
        <option value="none">{t("visNone")}</option>
        {props.owned ? <option value="owner">{t("visOwner")}</option> : null}
        <option value="custom">{t("visCustom")}</option>
      </select>
      {mode === "custom" ? (
        <input
          className="gh-sd-input is-mono"
          aria-label={t("visCustom")}
          value={custom}
          onChange={(e) => setCustom(e.target.value)}
          onBlur={() => props.onChange(custom)}
        />
      ) : null}
    </div>
  );
}

function StateTable(props: { game: GameModel }) {
  const { game } = props;
  const t = useMessages(messages);
  const [, studio] = useStudio();
  const names = useNames(game);
  return (
    <div className="gh-sd-table" data-table="state">
      {game.state.map((v) => (
        <Section
          key={v.name}
          title={
            <code>
              {v.name}: {v.type}
            </code>
          }
          open={false}
          actions={
            v.local ? (
              <IconButton
                label={t("delete")}
                danger
                onClick={() => studio.tryApply([{ op: "deleteState", name: v.name }])}
              >
                ✕
              </IconButton>
            ) : null
          }
        >
          <TextField
            label={t("name")}
            value={v.name}
            mono
            readOnly={!v.local}
            failureKey={`state:${v.name}:name`}
            ops={(name) => [{ op: "rename", key: `state:${v.name}`, name }]}
          />
          <CodeField
            label={t("type")}
            value={v.type}
            names={names}
            readOnly={!v.local}
            failureKey={`state:${v.name}:type`}
            ops={(type) => [{ op: "updateState", name: v.name, type }]}
          />
          <CodeField
            label={t("init")}
            value={v.init ?? ""}
            names={names}
            readOnly={!v.local}
            failureKey={`state:${v.name}:init`}
            ops={(init) => [{ op: "updateState", name: v.name, init: init || null }]}
          />
          <VisibilityField
            value={v.visibility}
            owned={v.type.startsWith("per_player")}
            onChange={(visibility) =>
              studio.tryApply(
                [{ op: "updateState", name: v.name, visibility }],
                `state:${v.name}:visibility`,
              )
            }
          />
        </Section>
      ))}
      <AddRow
        fields={[
          { name: "name", label: t("name"), placeholder: "score" },
          { name: "type", label: t("type"), placeholder: "Int" },
          { name: "init", label: t("init"), placeholder: "0" },
        ]}
        failureKey="state:add"
        ops={(v) => [
          {
            op: "addState",
            name: v.name || undefined,
            type: v.type || "Int",
            init: v.init || null,
          },
        ]}
      />
    </div>
  );
}

function ParamsTable(props: { game: GameModel }) {
  const { game } = props;
  const t = useMessages(messages);
  const [, studio] = useStudio();
  const names = useNames(game);
  return (
    <div className="gh-sd-table" data-table="params">
      {game.params.map((p) => (
        <Section
          key={p.name}
          title={
            <code>
              {p.name}: {p.type} = {p.default}
            </code>
          }
          open={false}
          actions={
            p.local ? (
              <IconButton
                label={t("delete")}
                danger
                onClick={() => studio.tryApply([{ op: "deleteParam", name: p.name }])}
              >
                ✕
              </IconButton>
            ) : null
          }
        >
          <TextField
            label={t("name")}
            value={p.name}
            mono
            readOnly={!p.local}
            failureKey={`param:${p.name}:name`}
            ops={(name) => [{ op: "rename", key: `param:${p.name}`, name }]}
          />
          <CodeField
            label={t("type")}
            value={p.type}
            names={names}
            readOnly={!p.local}
            failureKey={`param:${p.name}:type`}
            ops={(type) => [{ op: "updateParam", name: p.name, type }]}
          />
          <CodeField
            label={t("default")}
            value={p.default}
            names={names}
            readOnly={!p.local}
            failureKey={`param:${p.name}:default`}
            ops={(value) => [{ op: "updateParam", name: p.name, default: value }]}
          />
        </Section>
      ))}
      <AddRow
        fields={[
          { name: "name", label: t("name"), placeholder: "rounds" },
          { name: "type", label: t("type"), placeholder: "Int" },
          { name: "default", label: t("default"), placeholder: "3" },
        ]}
        failureKey="param:add"
        ops={(v) => [
          {
            op: "addParam",
            name: v.name || undefined,
            type: v.type || "Int",
            default: v.default || "0",
          },
        ]}
      />
    </div>
  );
}

function TypesTable(props: { game: GameModel }) {
  const { game } = props;
  const t = useMessages(messages);
  const [, studio] = useStudio();
  return (
    <div className="gh-sd-table" data-table="types">
      {game.types.map((ty) => (
        <Section
          key={ty.name}
          title={<code>{ty.kind === "enum" ? `enum ${ty.name}` : `struct ${ty.name}`}</code>}
          open={false}
          actions={
            ty.local ? (
              <IconButton
                label={t("delete")}
                danger
                onClick={() => studio.tryApply([{ op: "deleteType", name: ty.name }])}
              >
                ✕
              </IconButton>
            ) : null
          }
        >
          <TextField
            label={t("name")}
            value={ty.name}
            mono
            readOnly={!ty.local}
            failureKey={`type:${ty.name}:name`}
            ops={(name) => [{ op: "rename", key: `type:${ty.name}`, name }]}
          />
          {ty.kind === "enum" ? (
            <TextField
              label={t("values")}
              value={ty.values.join(", ")}
              mono
              readOnly={!ty.local}
              failureKey={`type:${ty.name}:values`}
              ops={(value) => [{ op: "updateEnum", name: ty.name, values: splitNames(value) }]}
            />
          ) : (
            <TextField
              label={t("fields")}
              value={ty.fields.map((f) => `${f.name}: ${f.type}`).join(", ")}
              mono
              readOnly={!ty.local}
              failureKey={`type:${ty.name}:fields`}
              ops={(value) => [{ op: "updateStruct", name: ty.name, fields: splitFields(value) }]}
            />
          )}
        </Section>
      ))}
      <AddRow
        fields={[
          { name: "name", label: t("name"), placeholder: "Mark" },
          { name: "values", label: `${t("values")} (enum)`, placeholder: "X, O" },
        ]}
        failureKey="type:add"
        ops={(v) => [
          { op: "addEnum", name: v.name || undefined, values: splitNames(v.values || "A, B") },
        ]}
      />
      <AddRow
        fields={[
          { name: "name", label: t("name"), placeholder: "Card" },
          {
            name: "fields",
            label: `${t("fields")} (struct)`,
            placeholder: "suit: Suit, rank: Rank",
          },
        ]}
        failureKey="type:addStruct"
        ops={(v) => [
          {
            op: "addStruct",
            name: v.name || undefined,
            fields: splitFields(v.fields || "value: Int"),
          },
        ]}
      />
    </div>
  );
}

function FunctionsTable(props: { game: GameModel }) {
  const { game } = props;
  const t = useMessages(messages);
  const [, studio] = useStudio();
  const names = useNames(game);
  return (
    <div className="gh-sd-table" data-table="functions">
      {game.functions.map((f) => (
        <Section
          key={f.name}
          title={
            <code>
              fn {f.name}({f.params.map((p) => `${p.name}: ${p.type}`).join(", ")}) → {f.returns}
            </code>
          }
          open={false}
          actions={
            f.local ? (
              <IconButton
                label={t("delete")}
                danger
                onClick={() => studio.tryApply([{ op: "deleteFn", name: f.name }])}
              >
                ✕
              </IconButton>
            ) : null
          }
        >
          <TextField
            label={t("name")}
            value={f.name}
            mono
            readOnly={!f.local}
            failureKey={`fn:${f.name}:name`}
            ops={(name) => [{ op: "rename", key: `fn:${f.name}`, name }]}
          />
          <TextField
            label={t("parameters")}
            value={f.params.map((p) => `${p.name}: ${p.type}`).join(", ")}
            mono
            readOnly={!f.local}
            failureKey={`fn:${f.name}:params`}
            ops={(value) => [{ op: "updateFn", name: f.name, params: splitFields(value) }]}
          />
          <CodeField
            label={t("returns")}
            value={f.returns}
            names={names}
            readOnly={!f.local}
            failureKey={`fn:${f.name}:returns`}
            ops={(returns) => [{ op: "updateFn", name: f.name, returns }]}
          />
          <CodeField
            label={t("body")}
            value={f.body}
            names={names}
            multiline
            readOnly={!f.local}
            failureKey={`fn:${f.name}:body`}
            ops={(body) => [{ op: "updateFn", name: f.name, body }]}
          />
        </Section>
      ))}
      <AddRow
        fields={[
          { name: "name", label: t("name"), placeholder: "wins" },
          { name: "params", label: t("parameters"), placeholder: "m: Mark" },
          { name: "returns", label: t("returns"), placeholder: "Bool" },
          { name: "body", label: t("body"), placeholder: "true" },
        ]}
        failureKey="fn:add"
        ops={(v) => [
          {
            op: "addFn",
            name: v.name || undefined,
            params: v.params ? splitFields(v.params) : [],
            returns: v.returns || "Bool",
            body: v.body || "true",
          },
        ]}
      />
    </div>
  );
}

function UiTable(props: { game: GameModel }) {
  const { game } = props;
  const t = useMessages(messages);
  const [, studio] = useStudio();
  return (
    <div className="gh-sd-table" data-table="ui">
      {game.ui.map((entry) => (
        <div key={entry.target} className="gh-sd-row">
          <TextField
            label={entry.target}
            value={entry.hints}
            mono
            readOnly={!entry.local}
            failureKey={`ui:${entry.target}`}
            ops={(hints) => [{ op: "setUiEntry", target: entry.target, hints: hints || null }]}
          />
          {entry.local ? (
            <IconButton
              label={t("delete")}
              danger
              onClick={() =>
                studio.tryApply([{ op: "setUiEntry", target: entry.target, hints: null }])
              }
            >
              ✕
            </IconButton>
          ) : null}
        </div>
      ))}
      <AddRow
        fields={[
          { name: "target", label: t("target"), placeholder: "board" },
          { name: "hints", label: t("hintsText"), placeholder: 'grid, label("Tablero")' },
        ]}
        failureKey="ui:add"
        ops={(v) => [{ op: "setUiEntry", target: v.target, hints: v.hints || "hidden" }]}
      />
    </div>
  );
}

/** Los tests del juego (nombre y pasos) y sus invariantes; se pueden ejecutar desde aquí. */
function TestsTable(props: { game: GameModel }) {
  const { game } = props;
  const t = useMessages(messages);
  const [state, studio] = useStudio();
  const names = useNames(game);
  const [report, setReport] = useState<TestReport | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = async () => {
    const file = state.file;
    if (!file) return;
    setRunning(true);
    setError(null);
    try {
      setReport(
        await studio.connection.request<TestReport>("gamehub/tests", {
          uri: file.uri,
          playouts: 100,
        }),
      );
    } catch (e) {
      setReport(null);
      setError((e as Error).message);
    } finally {
      setRunning(false);
    }
  };
  // Las operaciones cuentan solo los tests e invariantes de este archivo (no los de la base).
  const localTests = game.tests.filter((x) => x.local);
  const localInvariants = game.invariants.filter((x) => x.local);
  const passed = report?.tests.filter((r) => r.ok).length ?? 0;
  return (
    <div className="gh-sd-table" data-table="tests">
      <div className="gh-sd-row">
        <Button
          size="sm"
          variant="primary"
          disabled={running || !state.analysis?.compiled}
          onClick={() => run()}
        >
          ▶ {t("runTests")}
        </Button>
        {report ? (
          <span className={passed === report.tests.length ? "gh-sd-ok" : "gh-sd-error"}>
            {t("testsSummary", { n: passed, total: report.tests.length })}
          </span>
        ) : null}
      </div>
      {report && !report.playouts.failure && report.invariants ? (
        <p className="gh-sd-note">
          {report.invariants === 1
            ? t("invariantOneSummary", { games: report.playouts.games })
            : t("invariantsSummary", {
                invariants: report.invariants,
                games: report.playouts.games,
              })}
        </p>
      ) : null}
      {error ? (
        <p className="gh-sd-field__error" role="alert">
          {error}
        </p>
      ) : null}
      {report?.playouts.failure ? (
        <p className="gh-sd-field__error" role="alert">
          {report.playouts.failure.message}
        </p>
      ) : null}
      {game.tests.map((test) => {
        const index = localTests.indexOf(test);
        const result = report?.tests.find((r) => r.name === test.name);
        return (
          <Section
            key={test.name}
            title={
              <span>
                {result ? (result.ok ? "✓ " : "✗ ") : ""}
                {test.name}
              </span>
            }
            open={result ? !result.ok : false}
            actions={
              test.local ? (
                <IconButton
                  label={t("delete")}
                  danger
                  onClick={() => studio.tryApply([{ op: "deleteTest", index }])}
                >
                  ✕
                </IconButton>
              ) : null
            }
          >
            <TextField
              label={t("name")}
              value={test.name}
              readOnly={!test.local}
              failureKey={`test:${index}:name`}
              ops={(name) => [{ op: "updateTest", index, name }]}
            />
            <CodeField
              label={t("steps")}
              value={test.body}
              names={names}
              multiline
              readOnly={!test.local}
              failureKey={`test:${index}:body`}
              ops={(body) => [{ op: "updateTest", index, body }]}
              hint="play …, chance …, expect …, expect legal …"
            />
            {result?.failure ? (
              <div className="gh-sd-field__error" role="alert">
                <p>{result.failure.message}</p>
                {(result.failure.notes ?? []).map((note) => (
                  <p key={note} className="gh-sd-muted">
                    {note}
                  </p>
                ))}
              </div>
            ) : null}
          </Section>
        );
      })}
      <AddRow
        fields={[{ name: "name", label: t("name"), placeholder: "X gana en diagonal" }]}
        failureKey="test:add"
        ops={(v) => [{ op: "addTest", name: v.name || undefined }]}
      />
      <h4 className="gh-sd-subtitle">{t("invariants")}</h4>
      {game.invariants.map((inv, i) => {
        const index = localInvariants.indexOf(inv);
        return (
          // biome-ignore lint/suspicious/noArrayIndexKey: un invariante no tiene más identidad que su lugar.
          <div key={i} className="gh-sd-row gh-sd-row--top">
            <CodeField
              label={`invariant ${i + 1}`}
              value={inv.expr}
              names={names}
              multiline
              readOnly={!inv.local}
              failureKey={`invariant:${index}`}
              ops={(expr) => [{ op: "updateInvariant", index, expr }]}
            />
            {inv.local ? (
              <IconButton
                label={t("delete")}
                danger
                onClick={() => studio.tryApply([{ op: "deleteInvariant", index }])}
              >
                ✕
              </IconButton>
            ) : null}
          </div>
        );
      })}
      <AddRow
        fields={[{ name: "expr", label: t("expression"), placeholder: "score[0] >= 0" }]}
        failureKey="invariant:add"
        ops={(v) => [{ op: "addInvariant", expr: v.expr || "true" }]}
      />
    </div>
  );
}

/** Una fila para añadir algo nuevo: unos campos de texto y un botón. */
function AddRow(props: {
  fields: { name: string; label: string; placeholder?: string }[];
  ops: (values: Record<string, string>) => Op[];
  failureKey: string;
}) {
  const t = useMessages(messages);
  const [state, studio] = useStudio();
  const [values, setValues] = useState<Record<string, string>>({});
  const failure = state.failure?.key === props.failureKey ? state.failure : null;
  return (
    <form
      className="gh-sd-add"
      onSubmit={(e) => {
        e.preventDefault();
        studio.tryApply(props.ops(values), props.failureKey).then((ok) => ok && setValues({}));
      }}
    >
      {props.fields.map((f) => (
        <input
          key={f.name}
          className="gh-sd-input is-mono"
          aria-label={f.label}
          placeholder={f.placeholder ?? f.label}
          value={values[f.name] ?? ""}
          onChange={(e) => setValues({ ...values, [f.name]: e.target.value })}
        />
      ))}
      <Button size="sm" type="submit">
        {t("add")}
      </Button>
      {failure ? (
        <p className="gh-sd-field__error" role="alert">
          {failure.message}
        </p>
      ) : null}
    </form>
  );
}

export function splitNames(value: string): string[] {
  return value
    .split(/[,\s]+/)
    .map((v) => v.trim())
    .filter(Boolean);
}

/** `a: Int, b: List<Card>` → campos (respetando las comas de dentro de <…>). */
export function splitFields(value: string): { name: string; type: string }[] {
  const out: { name: string; type: string }[] = [];
  let depth = 0;
  let current = "";
  const flush = () => {
    const at = current.indexOf(":");
    if (current.trim()) {
      out.push({ name: current.slice(0, at).trim(), type: current.slice(at + 1).trim() });
    }
    current = "";
  };
  for (const ch of value) {
    if (ch === "<" || ch === "(" || ch === "[") depth += 1;
    if (ch === ">" || ch === ")" || ch === "]") depth -= 1;
    if (ch === "," && depth === 0) flush();
    else current += ch;
  }
  flush();
  return out;
}
