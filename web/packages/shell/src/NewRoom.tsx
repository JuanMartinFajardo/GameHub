// SPDX-License-Identifier: Apache-2.0
/** Crear una sala: jugadores, opciones del juego, reloj y bots. */

import { createRoom, endpoints, saveSession } from "@gamehub/client";
import { pickText, useLocale, useMessages } from "@gamehub/i18n";
import { Button, Field, Panel, Spinner } from "@gamehub/ui-kit";
import { type FormEvent, useEffect, useState } from "react";
import { DEFAULT_SETTINGS, defaultParams, ParamsForm, SettingsForm, settingsPatch } from "./forms";
import { loadGameModel, useLoaded } from "./games";
import { messages } from "./messages";
import { navigate } from "./router";
import { planSetup, rememberName, savedName } from "./useRoom";

export function NewRoom(props: { server: string; game: string }) {
  const t = useMessages(messages);
  const { locale } = useLocale();
  const model = useLoaded(`${props.server}|${props.game}`, () =>
    loadGameModel(props.server, props.game),
  );
  const [name, setName] = useState(savedName);
  const [players, setPlayers] = useState<number | null>(null);
  const [params, setParams] = useState<Record<string, unknown>>({});
  const [settings, setSettings] = useState(DEFAULT_SETTINGS);
  const [bots, setBots] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const m = model.data;

  useEffect(() => {
    if (m) {
      setPlayers((p) => p ?? m.ir.players.min);
      setParams(defaultParams(m));
    }
  }, [m]);

  if (model.error) return <p className="gh-shell-error">{t("error", { message: model.error })}</p>;
  if (!m || players === null) return <Spinner label={t("loading")} />;
  const { min, max } = m.ir.players;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const host = name.trim() || "Anfitrión";
    rememberName(host);
    try {
      const created = await createRoom(props.server, {
        game: props.game,
        players,
        params,
        settings: settingsPatch(settings),
        name: host.slice(0, 32),
      });
      saveSession(endpoints(props.server).http, created.code, created.token, host);
      planSetup(created.code, { sit: true, bots: Math.min(bots, players - 1) });
      navigate(`/r/${created.code}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  };

  return (
    <form className="gh-shell-page gh-shell-narrow" onSubmit={submit}>
      <h1>{t("newRoomTitle", { game: pickText(m.title, locale) })}</h1>
      <Panel>
        <div className="gh-shell-form">
          <Field label={t("yourName")}>
            <input
              className="gh-input"
              value={name}
              maxLength={32}
              onChange={(e) => setName(e.target.value)}
              autoComplete="nickname"
            />
          </Field>
          {min !== max && (
            <Field label={t("seats")}>
              <select
                className="gh-select"
                value={players}
                onChange={(e) => setPlayers(Number(e.target.value))}
              >
                {Array.from({ length: max - min + 1 }, (_, i) => min + i).map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </Field>
          )}
          <Field label={t("botSeats")}>
            <select
              className="gh-select"
              value={bots}
              onChange={(e) => setBots(Number(e.target.value))}
            >
              {Array.from({ length: players }, (_, i) => i).map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </Field>
        </div>
      </Panel>
      {m.params.length > 0 && (
        <Panel title={t("options")}>
          <ParamsForm model={m} values={params} onChange={setParams} />
        </Panel>
      )}
      <Panel title={t("roomSettings")}>
        <SettingsForm value={settings} onChange={setSettings} />
      </Panel>
      {error && <p className="gh-shell-error">{t("error", { message: error })}</p>}
      <div className="gh-shell-row">
        <Button type="submit" variant="primary" size="lg" disabled={busy}>
          {busy ? t("creating") : t("create")}
        </Button>
        <Button variant="ghost" onClick={() => navigate("/")}>
          {t("back")}
        </Button>
      </div>
    </form>
  );
}
