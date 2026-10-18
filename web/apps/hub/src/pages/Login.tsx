// SPDX-License-Identifier: AGPL-3.0-or-later
/** Entrar, registrarse (aceptando las condiciones de uso) y las propias condiciones. */

import { useMessages } from "@gamehub/i18n";
import { Link, navigate } from "@gamehub/shell";
import { Button, Field, Panel } from "@gamehub/ui-kit";
import { type FormEvent, useState } from "react";
import { errorText, get, post } from "../api";
import { Markdown } from "../Markdown";
import { messages } from "../messages";
import { useSession } from "../session";
import { Loading, useLoad } from "../ui";

export function LoginPage(props: { mode: "login" | "signup" }) {
  const t = useMessages(messages);
  const { info, refresh } = useSession();
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [email, setEmail] = useState("");
  const [accept, setAccept] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const signup = props.mode === "signup";
  const next = new URLSearchParams(location.search).get("next") ?? "/";

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (signup) {
        await post("/auth/signup", {
          name,
          password,
          email: email || undefined,
          terms: accept ? info?.terms_version : undefined,
        });
      } else {
        await post("/auth/login", { name, password });
      }
      await refresh();
      navigate(next.startsWith("/") && !next.startsWith("//") ? next : "/");
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="gh-shell-page hub-narrow">
      <h1>{signup ? t("signupTitle") : t("loginTitle")}</h1>
      <Panel>
        <form className="hub-form" onSubmit={submit}>
          <Field label={t("username")} hint={signup ? t("usernameHint") : undefined}>
            <input
              className="gh-input"
              autoComplete="username"
              value={name}
              onChange={(e) => setName(e.target.value.toLowerCase())}
              required
            />
          </Field>
          <Field label={t("password")} hint={signup ? t("passwordHint") : undefined}>
            <input
              className="gh-input"
              type="password"
              autoComplete={signup ? "new-password" : "current-password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </Field>
          {signup && (
            <>
              <Field label={t("email")} hint={t("emailHint")}>
                <input
                  className="gh-input"
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </Field>
              <label className="hub-check">
                <input
                  type="checkbox"
                  checked={accept}
                  onChange={(e) => setAccept(e.target.checked)}
                />{" "}
                {t("acceptTerms")} <Link to="/terms">{t("terms")}</Link>
              </label>
            </>
          )}
          {error && <p className="gh-shell-error">{error}</p>}
          <Button type="submit" variant="primary" disabled={busy || (signup && !accept)}>
            {signup ? t("signup") : t("login")}
          </Button>
        </form>
        {info && info.oauth.length > 0 && (
          <div className="hub-oauth">
            <p className="gh-muted">{t("orWith")}</p>
            {info.oauth.map((p) => (
              <a
                key={p.name}
                className="gh-button gh-button--secondary"
                href={`/auth/${p.name}/login?next=${encodeURIComponent(next)}`}
              >
                {t("continueWith", { provider: p.title })}
              </a>
            ))}
          </div>
        )}
        <p className="gh-muted">
          {signup ? (
            <>
              {t("haveAccount")} <Link to="/login">{t("login")}</Link>
            </>
          ) : (
            info?.signup !== false && (
              <>
                {t("noAccount")} <Link to="/signup">{t("signup")}</Link>
              </>
            )
          )}
        </p>
      </Panel>
    </div>
  );
}

export function TermsPage() {
  const t = useMessages(messages);
  const { user, refresh } = useSession();
  const terms = useLoad("terms", () => get<{ version: string; text: string }>("/terms"));
  const [error, setError] = useState<string | null>(null);
  if (!terms.data) return <Loading error={terms.error} />;
  const outdated = user !== null && user.terms_current === false;
  return (
    <div className="gh-shell-page hub-narrow">
      <p className="gh-muted">
        {t("termsVersion")} {terms.data.version}
      </p>
      <Markdown source={terms.data.text} />
      {outdated && (
        <p>
          <Button
            variant="primary"
            onClick={() =>
              post("/me/terms", { version: terms.data?.version })
                .then(refresh)
                .catch((e: unknown) => setError(errorText(e)))
            }
          >
            {t("acceptNewTerms")}
          </Button>
        </p>
      )}
      {error && <p className="gh-shell-error">{error}</p>}
    </div>
  );
}
