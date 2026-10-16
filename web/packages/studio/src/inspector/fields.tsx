// SPDX-License-Identifier: Apache-2.0
/** Piezas de los formularios del inspector. */

import { cx } from "@gamehub/ui-kit";
import { type ReactNode, useEffect, useId, useState } from "react";
import { useStudio } from "../context";
import { MiniEditor } from "../editor/MiniEditor";
import type { NameSource } from "../editor/setup";
import type { Op } from "../types";

export function Section(props: {
  title: ReactNode;
  children: ReactNode;
  actions?: ReactNode;
  open?: boolean;
}) {
  return (
    <details className="gh-sd-section" open={props.open ?? true}>
      <summary>
        <span>{props.title}</span>
        {props.actions ? <span className="gh-sd-section__actions">{props.actions}</span> : null}
      </summary>
      <div className="gh-sd-section__body">{props.children}</div>
    </details>
  );
}

/** El error de la última edición, si la pidió este campo. */
function useFailure(key: string) {
  const [state] = useStudio();
  return state.failure && state.failure.key === key ? state.failure : null;
}

function FailureText(props: { failureKey: string }) {
  const failure = useFailure(props.failureKey);
  if (!failure) return null;
  return (
    <p className="gh-sd-field__error" role="alert">
      {failure.message}
      {failure.errors?.[0]?.help ? <span> · {failure.errors[0].help}</span> : null}
    </p>
  );
}

/** Un campo de Nomos (expresión, tipo o sentencias) que, al confirmarse, aplica `ops(valor)`. */
export function CodeField(props: {
  label: string;
  value: string | null;
  failureKey: string;
  ops: (value: string) => Op[];
  names: NameSource;
  multiline?: boolean;
  placeholder?: string;
  readOnly?: boolean;
  hint?: ReactNode;
}) {
  const [, studio] = useStudio();
  const failure = useFailure(props.failureKey);
  const id = useId();
  return (
    <div className={cx("gh-sd-field", failure && "has-error")}>
      <label className="gh-sd-field__label" htmlFor={id}>
        {props.label}
      </label>
      <MiniEditor
        id={id}
        label={props.label}
        value={props.value ?? ""}
        names={props.names}
        multiline={props.multiline}
        placeholder={props.placeholder}
        readOnly={props.readOnly}
        errors={failure?.errors}
        onCommit={(value) => {
          studio.tryApply(props.ops(value), props.failureKey);
        }}
      />
      {props.hint ? <p className="gh-sd-field__hint">{props.hint}</p> : null}
      <FailureText failureKey={props.failureKey} />
    </div>
  );
}

/** Un texto normal (un nombre, un título): se confirma al salir o con Intro. */
export function TextField(props: {
  label: string;
  value: string;
  failureKey: string;
  ops: (value: string) => Op[];
  placeholder?: string;
  readOnly?: boolean;
  mono?: boolean;
}) {
  const [, studio] = useStudio();
  const failure = useFailure(props.failureKey);
  const [value, setValue] = useState(props.value);
  const id = useId();
  useEffect(() => setValue(props.value), [props.value]);
  const commit = () => {
    if (value !== props.value) studio.tryApply(props.ops(value), props.failureKey);
  };
  return (
    <div className={cx("gh-sd-field", failure && "has-error")}>
      <label className="gh-sd-field__label" htmlFor={id}>
        {props.label}
      </label>
      <input
        id={id}
        className={cx("gh-sd-input", props.mono && "is-mono")}
        value={value}
        placeholder={props.placeholder}
        readOnly={props.readOnly}
        onChange={(e) => setValue(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") commit();
          if (e.key === "Escape") setValue(props.value);
        }}
      />
      <FailureText failureKey={props.failureKey} />
    </div>
  );
}

export function SelectField(props: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  const id = useId();
  return (
    <div className="gh-sd-field">
      <label className="gh-sd-field__label" htmlFor={id}>
        {props.label}
      </label>
      <select
        id={id}
        className="gh-sd-input"
        value={props.value}
        disabled={props.disabled}
        onChange={(e) => props.onChange(e.target.value)}
      >
        {props.options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

export function IconButton(props: {
  label: string;
  onClick: () => void;
  children: ReactNode;
  disabled?: boolean;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      className={cx("gh-sd-icon", props.danger && "is-danger")}
      aria-label={props.label}
      title={props.label}
      disabled={props.disabled}
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        props.onClick();
      }}
    >
      {props.children}
    </button>
  );
}
