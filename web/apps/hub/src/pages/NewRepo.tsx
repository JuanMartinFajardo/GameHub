// SPDX-License-Identifier: AGPL-3.0-or-later
/** Un repositorio nuevo: un juego desde una plantilla, vacío (para empujar con git) o una
 * librería. */

import { pickText, useLocale, useMessages } from "@gamehub/i18n";
import { navigate } from "@gamehub/shell";
import { Button, Field, Panel } from "@gamehub/ui-kit";
import { type FormEvent, useState } from "react";
import { errorText, get, post, type Repo } from "../api";
import { messages } from "../messages";
import { useSession } from "../session";
import { Loading, useLoad } from "../ui";

interface Template {
  id: string;
  title: string | Record<string, string>;
  description: string | Record<string, string>;
}

export function NewRepoPage() {
  const t = useMessages(messages);
  const { locale } = useLocale();
  const { user, ready } = useSession();
  const templates = useLoad("templates", () =>
    get<{ templates: Template[]; default: string }>("/templates"),
  );
  const [owner, setOwner] = useState("");
  const [name, setName] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [kind, setKind] = useState<"game" | "library">("game");
  const [start, setStart] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!ready) return <Loading error={null} />;
  if (!user) {
    navigate("/login?next=/new", { replace: true });
    return null;
  }
  const chosen = start || templates.data?.default || "";
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const repo = await post<Repo>("/repos", {
        owner: owner || user.name,
        name,
        kind,
        description,
        title: title || undefined,
        template: kind === "game" && chosen !== "empty" ? chosen : undefined,
      });
      navigate(`/${repo.full_name}`);
    } catch (err) {
      setError(errorText(err));
      setBusy(false);
    }
  };
  return (
    <div className="gh-shell-page hub-narrow">
      <h1>{t("newRepo")}</h1>
      <Panel>
        <form className="hub-form" onSubmit={submit}>
          <div className="hub-inline">
            <Field label={t("owner")}>
              <select
                className="gh-select"
                value={owner || user.name}
                onChange={(e) => setOwner(e.target.value)}
              >
                {[user.name, ...(user.orgs ?? [])].map((o) => (
                  <option key={o} value={o}>
                    {o}
                  </option>
                ))}
              </select>
            </Field>
            <Field label={t("repoName")} hint={t("usernameHint")}>
              <input
                className="gh-input"
                value={name}
                onChange={(e) => setName(e.target.value.toLowerCase())}
                required
              />
            </Field>
          </div>
          <Field label={t("kind")}>
            <select
              className="gh-select"
              value={kind}
              onChange={(e) => setKind(e.target.value as "game" | "library")}
            >
              <option value="game">{t("game")}</option>
              <option value="library">{t("library")}</option>
            </select>
          </Field>
          <Field label={t("description")}>
            <input
              className="gh-input"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </Field>
          {kind === "game" && (
            <>
              <Field label={t("gameTitle")}>
                <input
                  className="gh-input"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                />
              </Field>
              <fieldset className="hub-templates">
                <legend>{t("startFrom")}</legend>
                {templates.data?.templates.map((tp) => (
                  <label key={tp.id} className="hub-template">
                    <input
                      type="radio"
                      name="template"
                      value={tp.id}
                      checked={chosen === tp.id}
                      onChange={() => setStart(tp.id)}
                    />
                    <strong>{pickText(tp.title, locale)}</strong>
                    <span className="gh-muted">{pickText(tp.description, locale)}</span>
                  </label>
                ))}
                <label className="hub-template">
                  <input
                    type="radio"
                    name="template"
                    value="empty"
                    checked={chosen === "empty"}
                    onChange={() => setStart("empty")}
                  />
                  <strong>{t("emptyRepo")}</strong>
                  <span className="gh-muted">{t("emptyRepoHelp")}</span>
                </label>
              </fieldset>
            </>
          )}
          {error && <p className="gh-shell-error">{error}</p>}
          <Button type="submit" variant="primary" disabled={busy || !name}>
            {t("create")}
          </Button>
        </form>
      </Panel>
    </div>
  );
}
