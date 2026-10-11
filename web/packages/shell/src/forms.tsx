// SPDX-License-Identifier: Apache-2.0
/** Formularios: opciones del juego y configuración de la sala. */

import type { GameModel, TypeRef } from "@gamehub/auto-ui";
import { pickText, useLocale, useMessages } from "@gamehub/i18n";
import type { Clock, OnTimeout, SettingsPatch } from "@gamehub/protocol";
import { Field } from "@gamehub/ui-kit";
import { useId } from "react";
import { constValue } from "./games";
import { messages } from "./messages";

/** Valores iniciales de las opciones: los dados o los de la IR. */
export function defaultParams(model: GameModel): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const p of model.params) {
    const v = constValue(p.default);
    if (v !== undefined) out[p.name] = v;
  }
  return out;
}

function listText(value: unknown): string {
  return Array.isArray(value) ? value.join(", ") : value === undefined ? "" : String(value);
}

export function ParamsForm(props: {
  model: GameModel;
  values: Record<string, unknown>;
  onChange: (values: Record<string, unknown>) => void;
  disabled?: boolean;
}) {
  const { locale } = useLocale();
  const { model, values } = props;
  if (model.params.length === 0) return null;
  const set = (name: string, value: unknown) => props.onChange({ ...values, [name]: value });
  return (
    <div className="gh-shell-form">
      {model.params.map((p) => (
        <Field
          key={p.name}
          label={pickText(p.label, locale)}
          hint={p.doc && p.doc !== p.label ? pickText(p.doc, locale) : undefined}
        >
          <ParamInput
            type={p.type}
            value={values[p.name]}
            disabled={props.disabled}
            onChange={(v) => set(p.name, v)}
          />
        </Field>
      ))}
    </div>
  );
}

function ParamInput(props: {
  type: TypeRef;
  value: unknown;
  disabled?: boolean;
  onChange: (value: unknown) => void;
}) {
  const { type, value, onChange } = props;
  switch (type.kind) {
    case "Bool":
      return (
        <input
          type="checkbox"
          checked={value === true}
          disabled={props.disabled}
          onChange={(e) => onChange(e.target.checked)}
        />
      );
    case "Int":
    case "Seat":
      return (
        <input
          className="gh-input"
          type="number"
          step={1}
          value={typeof value === "number" ? value : ""}
          disabled={props.disabled}
          onChange={(e) =>
            onChange(e.target.value === "" ? undefined : Math.trunc(Number(e.target.value)))
          }
        />
      );
    case "Real":
      return (
        <input
          className="gh-input"
          type="text"
          inputMode="decimal"
          value={value === undefined ? "" : String(value)}
          disabled={props.disabled}
          onChange={(e) => {
            const text = e.target.value.trim().replace(",", ".");
            onChange(text === "" ? undefined : /^-?\d+$/.test(text) ? Number(text) : text);
          }}
        />
      );
    case "enum":
      return (
        <select
          className="gh-select"
          value={typeof value === "string" ? value : ""}
          disabled={props.disabled}
          onChange={(e) => onChange(e.target.value)}
        >
          {type.values.map((v) => (
            <option key={v} value={v}>
              {v}
            </option>
          ))}
        </select>
      );
    case "list":
    case "set":
      if (type.inner.kind === "Int") {
        return (
          <input
            className="gh-input"
            type="text"
            value={listText(value)}
            disabled={props.disabled}
            onChange={(e) =>
              onChange(
                e.target.value
                  .split(/[,\s]+/)
                  .filter((x) => x !== "")
                  .map((x) => Math.trunc(Number(x)))
                  .filter((x) => Number.isFinite(x)),
              )
            }
          />
        );
      }
      break;
    case "Text":
      return (
        <input
          className="gh-input"
          type="text"
          value={typeof value === "string" ? value : ""}
          disabled={props.disabled}
          onChange={(e) => onChange(e.target.value)}
        />
      );
    default:
      break;
  }
  return (
    <input
      className="gh-input"
      type="text"
      defaultValue={value === undefined ? "" : JSON.stringify(value)}
      disabled={props.disabled}
      onBlur={(e) => {
        try {
          onChange(JSON.parse(e.target.value));
        } catch {
          // Se queda como estaba.
        }
      }}
    />
  );
}

export interface SettingsValue {
  clock: Clock;
  on_timeout: OnTimeout;
  spectators: boolean;
  spectator_view: "public" | "omniscient";
  private: boolean;
}

export const DEFAULT_SETTINGS: SettingsValue = {
  clock: { kind: "none" },
  on_timeout: "random",
  spectators: true,
  spectator_view: "public",
  private: false,
};

export function settingsPatch(value: SettingsValue): SettingsPatch {
  return { ...value };
}

export function SettingsForm(props: {
  value: SettingsValue;
  onChange: (value: SettingsValue) => void;
  disabled?: boolean;
}) {
  const t = useMessages(messages);
  const id = useId();
  const { value } = props;
  const set = (patch: Partial<SettingsValue>) => props.onChange({ ...value, ...patch });
  const clock = value.clock;
  return (
    <div className="gh-shell-form">
      <Field label={t("clock")}>
        <select
          className="gh-select"
          value={clock.kind}
          disabled={props.disabled}
          onChange={(e) => {
            const kind = e.target.value;
            set({
              clock:
                kind === "move"
                  ? { kind: "move", seconds: 30 }
                  : kind === "match"
                    ? { kind: "match", initial: 300, increment: 5 }
                    : { kind: "none" },
            });
          }}
        >
          <option value="none">{t("clockNone")}</option>
          <option value="move">{t("clockMove")}</option>
          <option value="match">{t("clockMatch")}</option>
        </select>
      </Field>
      {clock.kind === "move" && (
        <Field label={t("seconds")}>
          <input
            className="gh-input"
            type="number"
            min={1}
            value={clock.seconds}
            disabled={props.disabled}
            onChange={(e) =>
              set({ clock: { kind: "move", seconds: Math.max(1, Number(e.target.value)) } })
            }
          />
        </Field>
      )}
      {clock.kind === "match" && (
        <>
          <Field label={t("seconds")}>
            <input
              className="gh-input"
              type="number"
              min={1}
              value={clock.initial}
              disabled={props.disabled}
              onChange={(e) =>
                set({ clock: { ...clock, initial: Math.max(1, Number(e.target.value)) } })
              }
            />
          </Field>
          <Field label={t("increment")}>
            <input
              className="gh-input"
              type="number"
              min={0}
              value={clock.increment}
              disabled={props.disabled}
              onChange={(e) =>
                set({ clock: { ...clock, increment: Math.max(0, Number(e.target.value)) } })
              }
            />
          </Field>
        </>
      )}
      {clock.kind !== "none" && (
        <Field label={t("onTimeout")}>
          <select
            className="gh-select"
            value={value.on_timeout}
            disabled={props.disabled}
            onChange={(e) => set({ on_timeout: e.target.value as OnTimeout })}
          >
            <option value="random">{t("onTimeoutRandom")}</option>
            <option value="pass">{t("onTimeoutPass")}</option>
            <option value="bot">{t("onTimeoutBot")}</option>
            <option value="forfeit">{t("onTimeoutForfeit")}</option>
          </select>
        </Field>
      )}
      <label className="gh-shell-check" htmlFor={`${id}-spectators`}>
        <input
          id={`${id}-spectators`}
          type="checkbox"
          checked={value.spectators}
          disabled={props.disabled}
          onChange={(e) => set({ spectators: e.target.checked })}
        />
        {t("spectators")}
      </label>
      {value.spectators && (
        <label className="gh-shell-check" htmlFor={`${id}-omniscient`}>
          <input
            id={`${id}-omniscient`}
            type="checkbox"
            checked={value.spectator_view === "omniscient"}
            disabled={props.disabled}
            onChange={(e) => set({ spectator_view: e.target.checked ? "omniscient" : "public" })}
          />
          {t("spectatorsSeeAll")}
        </label>
      )}
      <label className="gh-shell-check" htmlFor={`${id}-private`}>
        <input
          id={`${id}-private`}
          type="checkbox"
          checked={value.private}
          disabled={props.disabled}
          onChange={(e) => set({ private: e.target.checked })}
        />
        {t("privateRoom")}
      </label>
    </div>
  );
}
