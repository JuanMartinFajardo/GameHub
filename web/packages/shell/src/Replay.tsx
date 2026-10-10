// SPDX-License-Identifier: Apache-2.0
/** Una partida terminada, paso a paso, vista como cualquier asiento, un espectador o con todo. */

import { AutoGame, buildModel, type GameIr } from "@gamehub/auto-ui";
import { type LoggedEvent, replayFrames } from "@gamehub/client";
import { pickText, useLocale, useMessages } from "@gamehub/i18n";
import type { MatchEnd } from "@gamehub/protocol";
import { Button, Field, Spinner } from "@gamehub/ui-kit";
import { useEffect, useMemo, useState } from "react";
import { useLoaded } from "./games";
import { messages } from "./messages";
import { Link } from "./router";

export function ReplayPage(props: { server: string; id: string }) {
  const t = useMessages(messages);
  const { locale } = useLocale();
  const [seat, setSeat] = useState("all");
  const data = useLoaded(`${props.server}|${props.id}|${seat}`, () =>
    replayFrames(props.server, props.id, seat),
  );
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const frames = data.data?.frames ?? [];
  const last = Math.max(0, frames.length - 1);
  const model = useMemo(
    () => (data.data ? buildModel(data.data.ir as unknown as GameIr) : null),
    [data.data],
  );

  useEffect(() => {
    if (!playing) return;
    const timer = setInterval(() => {
      setIndex((i) => {
        if (i >= last) {
          setPlaying(false);
          return i;
        }
        return i + 1;
      });
    }, 800);
    return () => clearInterval(timer);
  }, [playing, last]);

  useEffect(() => {
    const keys = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement) return;
      if (e.key === "ArrowRight") setIndex((i) => Math.min(last, i + 1));
      if (e.key === "ArrowLeft") setIndex((i) => Math.max(0, i - 1));
    };
    window.addEventListener("keydown", keys);
    return () => window.removeEventListener("keydown", keys);
  }, [last]);

  if (data.error) return <p className="gh-shell-error">{t("error", { message: data.error })}</p>;
  if (!data.data || !model) return <Spinner label={t("loading")} />;
  const frame = frames[Math.min(index, last)];
  if (!frame) return null;
  const log: LoggedEvent[] = frames
    .slice(0, index + 1)
    .flatMap((f) => f.events.map((event) => ({ seq: f.step, event })));
  const result = data.data.result;
  const players = data.data.players.map((p, seat) => ({ seat, name: p.name, kind: p.kind }));
  const end: MatchEnd | null =
    index === last && result
      ? {
          match: { id: props.id, number: 0 },
          reason: result.reason ?? "terminal",
          payoffs: result.payoffs ?? null,
          ranking: result.ranking ?? [],
          forfeited: result.forfeited ?? [],
          view: frame.view,
          fairness: { scheme: "gamehub-fair/1", commitment: "", client_seeds: [] },
          replay: props.id,
        }
      : null;
  return (
    <div className="gh-shell-page">
      <h1>
        {pickText(model.title, locale)} · {t("replayTitle", { id: props.id.slice(0, 8) })}
      </h1>
      <div className="gh-shell-replaybar">
        <Button size="sm" onClick={() => setIndex(0)} aria-label={t("first")}>
          ⏮
        </Button>
        <Button
          size="sm"
          onClick={() => setIndex((i) => Math.max(0, i - 1))}
          aria-label={t("previous")}
        >
          ◀
        </Button>
        <Button
          size="sm"
          variant="primary"
          onClick={() => setPlaying((p) => !p)}
          aria-label={t("playPause")}
        >
          {playing ? "⏸" : "▶"}
        </Button>
        <Button
          size="sm"
          onClick={() => setIndex((i) => Math.min(last, i + 1))}
          aria-label={t("next")}
        >
          ▶▶
        </Button>
        <Button size="sm" onClick={() => setIndex(last)} aria-label={t("last")}>
          ⏭
        </Button>
        <input
          className="gh-shell-grow"
          type="range"
          min={0}
          max={last}
          value={index}
          aria-label={t("step", { n: index, total: last })}
          onChange={(e) => setIndex(Number(e.target.value))}
        />
        <span className="gh-muted">{t("step", { n: index, total: last })}</span>
        <Field label={t("perspective")}>
          <select className="gh-select" value={seat} onChange={(e) => setSeat(e.target.value)}>
            <option value="all">{t("perspectiveAll")}</option>
            <option value="public">{t("perspectivePublic")}</option>
            {players.map((p) => (
              <option key={p.seat} value={String(p.seat)}>
                {p.name}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <AutoGame
        game={model}
        view={frame.view}
        seat={/^\d+$/.test(seat) ? Number(seat) : null}
        players={players}
        params={data.data.params}
        log={log}
        end={end}
      />
      <p>
        <Link to="/">{t("back")}</Link>
      </p>
    </div>
  );
}
