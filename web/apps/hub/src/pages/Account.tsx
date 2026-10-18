// SPDX-License-Identifier: AGPL-3.0-or-later
/** El perfil de una persona o de una organización: repositorios, miembros y actividad. */

import { useMessages } from "@gamehub/i18n";
import { Link } from "@gamehub/shell";
import { Badge, Button, Panel } from "@gamehub/ui-kit";
import { useState } from "react";
import { api, errorText, get, type HubEvent, type Repo, type User } from "../api";
import { messages } from "../messages";
import { useSession } from "../session";
import { EventList, Loading, RepoCard, useLoad, When } from "../ui";

interface AccountData extends User {
  repos: Repo[];
  members?: { name: string; display: string; role: string }[];
  role?: string | null;
  orgs?: string[];
  events: HubEvent[];
  can_write: boolean;
}

export function AccountPage(props: { name: string }) {
  const t = useMessages(messages);
  const { user } = useSession();
  const data = useLoad(props.name, () =>
    get<AccountData>(`/accounts/${encodeURIComponent(props.name)}`),
  );
  const [member, setMember] = useState("");
  const [error, setError] = useState<string | null>(null);
  if (!data.data) return <Loading error={data.error} />;
  const a = data.data;
  const isOrg = a.kind === "org";
  const addMember = () =>
    api("PUT", `/orgs/${a.name}/members/${member}`, { role: "member" })
      .then(() => {
        setMember("");
        data.reload();
      })
      .catch((e: unknown) => setError(errorText(e)));
  return (
    <div className="gh-shell-page">
      <header className="hub-profile">
        <span className="hub-avatar" aria-hidden="true">
          {(a.display || a.name).slice(0, 1).toUpperCase()}
        </span>
        <div>
          <h1>
            {a.display || a.name} <span className="gh-muted">@{a.name}</span>{" "}
            {isOrg && <Badge tone="accent">{t("organization")}</Badge>}
            {a.admin && <Badge tone="warning">{t("moderator")}</Badge>}
          </h1>
          {a.bio && <p>{a.bio}</p>}
          <p className="gh-muted">
            {t("since")} <When time={a.created} />
          </p>
        </div>
      </header>
      <div className="hub-columns">
        <div>
          <h2 className="gh-shell-h2">
            {t("repositories")} ({a.repos.length})
          </h2>
          <div className="hub-grid">
            {a.repos.map((r) => (
              <RepoCard key={r.full_name} repo={r} />
            ))}
            {!a.repos.length && <p className="gh-muted">{t("noRepos")}</p>}
          </div>
        </div>
        <aside>
          {isOrg && (
            <Panel title={t("members")}>
              <ul className="hub-events">
                {a.members?.map((m) => (
                  <li key={m.name}>
                    <Link to={`/${m.name}`}>{m.display || m.name}</Link>{" "}
                    {m.role === "owner" && <Badge>{t("owner")}</Badge>}
                  </li>
                ))}
              </ul>
              {a.role === "owner" && (
                <form
                  className="hub-inline"
                  onSubmit={(e) => {
                    e.preventDefault();
                    addMember();
                  }}
                >
                  <input
                    className="gh-input"
                    placeholder={t("username")}
                    value={member}
                    onChange={(e) => setMember(e.target.value.toLowerCase())}
                  />
                  <Button type="submit">{t("addMember")}</Button>
                </form>
              )}
              {error && <p className="gh-shell-error">{error}</p>}
            </Panel>
          )}
          {!isOrg && a.orgs && a.orgs.length > 0 && (
            <Panel title={t("organizations")}>
              {a.orgs.map((o) => (
                <p key={o}>
                  <Link to={`/${o}`}>{o}</Link>
                </p>
              ))}
            </Panel>
          )}
          {!isOrg && (
            <Panel title={t("activity")}>
              <EventList events={a.events} showRepo />
            </Panel>
          )}
          {user && user.name !== a.name && <ReportButton target={`account:${a.name}`} />}
        </aside>
      </div>
    </div>
  );
}

export function ReportButton(props: { target: string }) {
  const t = useMessages(messages);
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (done) return <p className="gh-muted">{t("reported")}</p>;
  if (!open) {
    return (
      <Button size="sm" variant="ghost" onClick={() => setOpen(true)}>
        ⚑ {t("report")}
      </Button>
    );
  }
  return (
    <form
      className="hub-form"
      onSubmit={(e) => {
        e.preventDefault();
        api("POST", "/reports", { target: props.target, reason })
          .then(() => setDone(true))
          .catch((err: unknown) => setError(errorText(err)));
      }}
    >
      <textarea
        className="gh-input"
        rows={3}
        placeholder={t("reportReason")}
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        required
      />
      <Button type="submit" size="sm" variant="danger">
        {t("sendReport")}
      </Button>
      {error && <p className="gh-shell-error">{error}</p>}
    </form>
  );
}
