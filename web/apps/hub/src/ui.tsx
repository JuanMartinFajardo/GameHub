// SPDX-License-Identifier: AGPL-3.0-or-later
/** Piezas comunes de las páginas del hub: tarjetas de repositorio, etiquetas, fechas, errores. */

import { type Translate, useLocale, useMessages } from "@gamehub/i18n";
import { Link } from "@gamehub/shell";
import { Badge, Spinner } from "@gamehub/ui-kit";
import { type ReactNode, useEffect, useState } from "react";
import { errorText, type HubEvent, type Repo } from "./api";
import { type MessageKey, messages } from "./messages";

export interface Loaded<T> {
  data: T | null;
  error: string | null;
  reload: () => void;
}

/** Carga algo (otra vez si cambia `key` o con `reload`). */
export function useLoad<T>(key: string | null, load: () => Promise<T>): Loaded<T> {
  const [state, setState] = useState<{ data: T | null; error: string | null }>({
    data: null,
    error: null,
  });
  const [tick, setTick] = useState(0);
  // biome-ignore lint/correctness/useExhaustiveDependencies: `key` y `tick` deciden cuándo cargar.
  useEffect(() => {
    if (key === null) return;
    let live = true;
    load().then(
      (data) => live && setState({ data, error: null }),
      (e: unknown) => live && setState({ data: null, error: errorText(e) }),
    );
    return () => {
      live = false;
    };
  }, [key, tick]);
  return { ...state, reload: () => setTick((n) => n + 1) };
}

export function Loading(props: { error: string | null; children?: ReactNode }) {
  const t = useMessages(messages);
  if (props.error) return <p className="gh-shell-error">{props.error}</p>;
  return <Spinner label={t("loading")} />;
}

export function ago(time: number, locale: string): string {
  const seconds = Date.now() / 1000 - time;
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  const steps: [number, Intl.RelativeTimeFormatUnit][] = [
    [60, "second"],
    [3600, "minute"],
    [86400, "hour"],
    [86400 * 30, "day"],
    [86400 * 365, "month"],
  ];
  let unit: Intl.RelativeTimeFormatUnit = "year";
  let size = 86400 * 365;
  for (const [limit, u] of steps) {
    if (seconds < limit) {
      unit = u;
      break;
    }
  }
  const sizes: Record<string, number> = {
    second: 1,
    minute: 60,
    hour: 3600,
    day: 86400,
    month: 86400 * 30,
    year: 86400 * 365,
  };
  size = sizes[unit] ?? size;
  return rtf.format(-Math.round(seconds / size), unit);
}

export function When(props: { time: number }) {
  const { locale } = useLocale();
  return (
    <time
      dateTime={new Date(props.time * 1000).toISOString()}
      title={new Date(props.time * 1000).toLocaleString(locale)}
    >
      {ago(props.time, locale)}
    </time>
  );
}

export function Hash(props: { value: string | null | undefined }) {
  if (!props.value) return null;
  const short = props.value.replace(/^sha256:/, "").slice(0, 12);
  return (
    <code className="hub-hash" title={props.value}>
      {short}
    </code>
  );
}

export function Labels(props: { labels: string[] | undefined }) {
  if (!props.labels?.length) return null;
  return (
    <span className="hub-labels">
      {props.labels.map((l) => (
        <Badge key={l}>{l}</Badge>
      ))}
    </span>
  );
}

export function LevelBadge(props: { level: string | null | undefined }) {
  const t = useMessages(messages);
  if (!props.level) return null;
  const tone = props.level === "major" ? "danger" : props.level === "minor" ? "accent" : "neutral";
  const text =
    props.level === "major"
      ? t("levelMajor")
      : props.level === "minor"
        ? t("levelMinor")
        : t("levelPatch");
  return <Badge tone={tone}>{text}</Badge>;
}

export function RepoCard(props: { repo: Repo }) {
  const t = useMessages(messages);
  const r = props.repo;
  const release = r.release;
  return (
    <article className="hub-card">
      <header className="hub-card__head">
        <Link to={`/${r.full_name}`} className="hub-card__title">
          {r.full_name}
        </Link>
        {r.kind === "library" && <Badge tone="warning">{t("library")}</Badge>}
        <span className="gh-shell-spacer" />
        <span className="gh-muted" title={t("stars")}>
          ★ {r.stars}
        </span>
      </header>
      {r.description && <p className="hub-card__text">{r.description}</p>}
      {release ? (
        <p className="hub-card__meta">
          <Badge tone="accent">v{release.version}</Badge>{" "}
          <Labels labels={release.properties.labels} />
        </p>
      ) : (
        <p className="hub-card__meta gh-muted">{t("noReleases")}</p>
      )}
      {r.parent && (
        <p className="hub-card__meta gh-muted">
          {t("forkOf")} <Link to={`/${r.parent}`}>{r.parent}</Link>
        </p>
      )}
    </article>
  );
}

export function EventList(props: { events: HubEvent[]; showRepo?: boolean }) {
  const t = useMessages(messages);
  if (!props.events.length) return <p className="gh-muted">{t("noActivity")}</p>;
  return (
    <ul className="hub-events">
      {props.events.map((e, i) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: la actividad no se reordena
        <li key={`${e.time}-${i}`}>
          {e.who ? (
            <Link to={`/${e.who}`}>{e.who}</Link>
          ) : (
            <span className="gh-muted">GameHub</span>
          )}{" "}
          {eventText(t, e)}
          {props.showRepo && e.repo && (
            <>
              {" · "}
              <Link to={`/${e.repo}`}>{e.repo}</Link>
            </>
          )}{" "}
          <span className="gh-muted">
            <When time={e.time} />
          </span>
        </li>
      ))}
    </ul>
  );
}

function eventText(t: Translate<MessageKey>, e: HubEvent): string {
  switch (e.kind) {
    case "created":
      return t("evCreated");
    case "forked":
      return t("evForked", { from: e.data.from });
    case "fork":
      return t("evFork", { to: e.data.to });
    case "pushed":
      return t("evPushed", { n: Object.keys(e.data.refs ?? {}).length });
    case "commit":
      return t("evCommit", { branch: e.data.branch, message: e.data.message || "…" });
    case "published":
      return t("evPublished", { version: e.data.version });
    case "pull_opened":
      return t("evPullOpened", { n: e.data.number, title: e.data.title });
    case "pull_merged":
      return t("evPullMerged", { n: e.data.number });
    case "pull_closed":
      return t("evPullClosed", { n: e.data.number });
    case "page":
      return t("evPage", { name: e.data.name });
    case "yanked":
      return t("evYanked", { version: e.data.version });
    default:
      return e.kind;
  }
}
