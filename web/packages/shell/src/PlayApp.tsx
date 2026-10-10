// SPDX-License-Identifier: Apache-2.0
/** La app para jugar: cabecera (idioma, tema) y las páginas según la ruta. */

import { LOCALES, type Locale, LocaleProvider, useLocale, useMessages } from "@gamehub/i18n";
import { normalizeCode } from "@gamehub/protocol";
import type { ReactNode } from "react";
import type { GameUiRegistry } from "./gameui";
import { Home } from "./Home";
import { HotSeat } from "./HotSeat";
import { messages } from "./messages";
import { NewRoom } from "./NewRoom";
import { ReplayPage } from "./Replay";
import { RoomPage } from "./Room";
import { Link, type Route, useRoute } from "./router";
import { type Theme, useTheme } from "./theme";

export interface PlayAppProps {
  /** El servidor de partidas ("" = el que sirve la página). */
  server?: string;
  /** UIs propias por id de juego (en vez de la genérica). */
  customUis?: GameUiRegistry;
  /** Solo este juego en el inicio (para desarrollar una UI propia). */
  only?: string;
  /** Páginas extra (p. ej. la galería del kit en /kit). */
  extra?: (route: Route) => ReactNode | null;
  /** Nombre en la cabecera. */
  brand?: string;
}

export function PlayApp(props: PlayAppProps) {
  return (
    <LocaleProvider>
      <div className="gh-root gh-shell">
        <Header brand={props.brand} />
        <main className="gh-shell-main">
          <Pages {...props} />
        </main>
      </div>
    </LocaleProvider>
  );
}

function Header(props: { brand?: string | undefined }) {
  const t = useMessages(messages);
  const { locale, setLocale } = useLocale();
  const [theme, setTheme] = useTheme();
  return (
    <header className="gh-shell-header">
      <Link to="/" className="gh-shell-logo">
        <span className="gh-shell-logo__mark" aria-hidden="true">
          ◆
        </span>
        {props.brand ?? t("brand")}
      </Link>
      <span className="gh-shell-spacer" />
      <select
        className="gh-select gh-shell-mini"
        aria-label={t("language")}
        value={locale}
        onChange={(e) => setLocale(e.target.value as Locale)}
      >
        {LOCALES.map((l) => (
          <option key={l} value={l}>
            {l.toUpperCase()}
          </option>
        ))}
      </select>
      <select
        className="gh-select gh-shell-mini"
        aria-label={t("theme")}
        value={theme}
        onChange={(e) => setTheme(e.target.value as Theme)}
      >
        <option value="auto">{t("themeAuto")}</option>
        <option value="light">{t("themeLight")}</option>
        <option value="dark">{t("themeDark")}</option>
      </select>
    </header>
  );
}

function Pages(props: PlayAppProps) {
  const t = useMessages(messages);
  const route = useRoute();
  const server = props.server ?? "";
  const extra = props.extra?.(route);
  if (extra) return <>{extra}</>;
  switch (route.page) {
    case "home":
      return <Home server={server} only={props.only} />;
    case "room": {
      const code = normalizeCode(route.code);
      if (code === null) return <p className="gh-shell-error">{t("badCode")}</p>;
      return <RoomPage key={code} server={server} code={code} customUis={props.customUis} />;
    }
    case "new":
      return <NewRoom key={route.game} server={server} game={route.game} />;
    case "local":
      return (
        <HotSeat key={route.game} server={server} game={route.game} customUis={props.customUis} />
      );
    case "replay":
      return <ReplayPage key={route.id} server={server} id={route.id} />;
    default:
      return (
        <div className="gh-shell-page">
          <p>{t("missingPage")}</p>
          <Link to="/">{t("home")}</Link>
        </div>
      );
  }
}
