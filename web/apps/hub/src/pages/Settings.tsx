// SPDX-License-Identifier: AGPL-3.0-or-later
/** Ajustes de la cuenta: perfil, tokens de API (para la CLI y git) y organizaciones. */

import { useMessages } from "@gamehub/i18n";
import { Link, navigate } from "@gamehub/shell";
import { Button, Field, Panel } from "@gamehub/ui-kit";
import { type FormEvent, useState } from "react";
import { api, errorText, get, post } from "../api";
import { messages } from "../messages";
import { useSession } from "../session";
import { Loading, useLoad, When } from "../ui";

interface Token {
  id: number;
  name: string;
  created: number;
  used: number | null;
}

export function SettingsPage() {
  const t = useMessages(messages);
  const { user, ready, refresh } = useSession();
  const [display, setDisplay] = useState(user?.display ?? "");
  const [bio, setBio] = useState(user?.bio ?? "");
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const tokens = useLoad(user ? "tokens" : null, () => get<{ tokens: Token[] }>("/me/tokens"));
  const [tokenName, setTokenName] = useState("cli");
  const [fresh, setFresh] = useState<string | null>(null);
  const [org, setOrg] = useState("");

  if (!ready) return <Loading error={null} />;
  if (!user) {
    navigate("/login?next=/settings", { replace: true });
    return null;
  }
  const run = (work: () => Promise<unknown>) => {
    setError(null);
    work().catch((e: unknown) => setError(errorText(e)));
  };
  const saveProfile = (e: FormEvent) => {
    e.preventDefault();
    run(async () => {
      await api("PATCH", "/me", { display, bio });
      await refresh();
      setSaved(true);
    });
  };
  const host = location.origin;
  return (
    <div className="gh-shell-page hub-narrow">
      <h1>{t("settings")}</h1>
      {error && <p className="gh-shell-error">{error}</p>}
      <Panel title={t("profile")}>
        <form className="hub-form" onSubmit={saveProfile}>
          <Field label={t("displayName")}>
            <input
              className="gh-input"
              value={display}
              onChange={(e) => setDisplay(e.target.value)}
            />
          </Field>
          <Field label={t("bio")}>
            <textarea
              className="gh-input"
              rows={3}
              value={bio}
              onChange={(e) => setBio(e.target.value)}
            />
          </Field>
          <Button type="submit" variant="primary">
            {t("save")}
          </Button>
          {saved && <span className="gh-muted">{t("saved")}</span>}
        </form>
      </Panel>
      <Panel title={t("tokens")}>
        <p className="gh-muted">{t("tokensHelp")}</p>
        <pre className="hub-code">
          <code>{`gamehub login --hub ${host} --token …\ngit clone ${host}/${user.name}/<repo>.git`}</code>
        </pre>
        {fresh && (
          <p className="hub-token">
            {t("tokenOnce")} <code>{fresh}</code>
          </p>
        )}
        {tokens.data ? (
          <ul className="hub-events">
            {tokens.data.tokens.map((tk) => (
              <li key={tk.id}>
                <strong>{tk.name}</strong> · {t("created")} <When time={tk.created} />
                {tk.used && (
                  <>
                    {" "}
                    · {t("lastUsed")} <When time={tk.used} />
                  </>
                )}{" "}
                <Button
                  size="sm"
                  variant="danger"
                  onClick={() =>
                    run(() => api("DELETE", `/me/tokens/${tk.id}`).then(tokens.reload))
                  }
                >
                  {t("revoke")}
                </Button>
              </li>
            ))}
          </ul>
        ) : (
          <Loading error={tokens.error} />
        )}
        <form
          className="hub-inline"
          onSubmit={(e) => {
            e.preventDefault();
            run(async () => {
              const created = await post<{ token: string }>("/me/tokens", { name: tokenName });
              setFresh(created.token);
              tokens.reload();
            });
          }}
        >
          <input
            className="gh-input"
            value={tokenName}
            onChange={(e) => setTokenName(e.target.value)}
          />
          <Button type="submit">{t("newToken")}</Button>
        </form>
      </Panel>
      <Panel title={t("organizations")}>
        <ul className="hub-events">
          {(user.orgs ?? []).map((o) => (
            <li key={o}>
              <Link to={`/${o}`}>{o}</Link>
            </li>
          ))}
        </ul>
        <form
          className="hub-inline"
          onSubmit={(e) => {
            e.preventDefault();
            run(async () => {
              await post("/orgs", { name: org });
              await refresh();
              navigate(`/${org}`);
            });
          }}
        >
          <input
            className="gh-input"
            placeholder={t("orgName")}
            value={org}
            onChange={(e) => setOrg(e.target.value.toLowerCase())}
          />
          <Button type="submit">{t("newOrg")}</Button>
        </form>
      </Panel>
    </div>
  );
}
