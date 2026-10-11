// SPDX-License-Identifier: Apache-2.0
/** Piezas básicas: botón, insignia, panel, campo y spinner. */

import type { ButtonHTMLAttributes, ReactNode } from "react";

export function cx(...names: (string | false | null | undefined)[]): string {
  return names.filter(Boolean).join(" ");
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
  selected?: boolean;
}

export function Button({
  variant = "secondary",
  size = "md",
  selected = false,
  className,
  type = "button",
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      className={cx(
        "gh-button",
        `gh-button--${variant}`,
        size !== "md" && `gh-button--${size}`,
        selected && "gh-button--selected",
        className,
      )}
      aria-pressed={selected || undefined}
      {...rest}
    />
  );
}

export function Badge(props: {
  tone?: "neutral" | "accent" | "success" | "warning" | "danger";
  children: ReactNode;
  title?: string;
}) {
  const tone = props.tone ?? "neutral";
  return (
    <span className={cx("gh-badge", tone !== "neutral" && `gh-badge--${tone}`)} title={props.title}>
      {props.children}
    </span>
  );
}

export function Panel(props: {
  title?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={cx("gh-panel", props.className)}>
      {(props.title !== undefined || props.actions !== undefined) && (
        <header className="gh-panel__header">
          <h3 className="gh-panel__title">{props.title}</h3>
          {props.actions}
        </header>
      )}
      {props.children !== null && props.children !== undefined && props.children !== false && (
        <div className={cx("gh-panel__body", props.bodyClassName)}>{props.children}</div>
      )}
    </section>
  );
}

export function Field(props: { label: ReactNode; children: ReactNode; hint?: ReactNode }) {
  return (
    // biome-ignore lint/a11y/noLabelWithoutControl: el control llega como hijo.
    <label className="gh-field">
      <span className="gh-field__label">{props.label}</span>
      {props.children}
      {props.hint !== undefined && <span className="gh-muted">{props.hint}</span>}
    </label>
  );
}

export function Spinner(props: { label?: string }) {
  return (
    <span className="gh-spinner-wrap">
      <span className="gh-spinner" aria-hidden="true" />
      {props.label !== undefined && <span className="gh-visually-hidden">{props.label}</span>}
    </span>
  );
}
