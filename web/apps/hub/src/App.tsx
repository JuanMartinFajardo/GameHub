// SPDX-License-Identifier: AGPL-3.0-or-later
/** La app del hub: cabecera (búsqueda, sesión, idioma, tema) y la página de cada ruta. */

import { LOCALES, type Locale, LocaleProvider, useLocale, useMessages } from "@gamehub/i18n";
import { normalizeCode } from "@gamehub/protocol";
import {
  type GameUiRegistry,
  HotSeat,
  Link,
  navigate,
  ReplayPage,
  RoomPage,
  type Theme,
  useLocation,
  useTheme,
} from "@gamehub/shell";
import { type FormEvent, useState } from "react";
import { messages } from "./messages";
import { AccountPage } from "./pages/Account";
import { AdminPage } from "./pages/Admin";
import { EditPage } from "./pages/Code";
import { ExplorePage, HomePage } from "./pages/Explore";
import { LoginPage, TermsPage } from "./pages/Login";
import { NewRepoPage } from "./pages/NewRepo";
import { PlayPage } from "./pages/Play";
import { NewPullPage, PullPage } from "./pages/Pull";
import { RepoPage } from "./pages/Repo";
import { SettingsPage } from "./pages/Settings";
import { parseHubRoute } from "./routes";
import { SessionProvider, useSession } from "./session";

export function HubApp(props: { customUis?: GameUiRegistry }) {
  return (
    <LocaleProvider>
      <SessionProvider>
        <div className="gh-root gh-shell hub">
          <Header />
          <main className="gh-shell-main">
            <Pages customUis={props.customUis} />
          </main>
          <Footer />
        </div>
      </SessionProvider>
    </LocaleProvider>
  );
}

function Header() {
  const t = useMessages(messages);
  const { locale, setLocale } = useLocale();
  const [theme, setTheme] = useTheme();
  const { user, info, logout } = useSession();
  const [q, setQ] = useState("");
  const search = (e: FormEvent) => {
    e.preventDefault();
    navigate(`/explore?q=${encodeURIComponent(q)}`);
  };
  return (
    <header className="gh-shell-header hub-header">
      <Link to="/" className="gh-shell-logo">
        <span className="gh-shell-logo__mark" aria-hidden="true">
          ◆
        </span>
        {info?.name ?? "GameHub"}
      </Link>
      <form className="hub-search" onSubmit={search}>
        <input
          className="gh-input"
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={t("searchPlaceholder")}
          aria-label={t("search")}
        />
      </form>
      <nav className="hub-nav">
        <Link to="/explore">{t("explore")}</Link>
        {user && <Link to="/new">{t("newRepo")}</Link>}
        {user?.admin && <Link to="/admin">{t("moderation")}</Link>}
      </nav>
      <span className="gh-shell-spacer" />
      {user ? (
        <span className="hub-user">
          <Link to={`/${user.name}`}>{user.display || user.name}</Link>
          <Link to="/settings" aria-label={t("settings")} title={t("settings")}>
            ⚙
          </Link>
          <button
            type="button"
            className="gh-button gh-button--ghost gh-button--sm"
            onClick={() => logout().then(() => navigate("/"))}
          >
            {t("logout")}
          </button>
        </span>
      ) : (
        <span className="hub-user">
          <Link to="/login">{t("login")}</Link>
          <Link to="/signup" className="gh-button gh-button--primary gh-button--sm">
            {t("signup")}
          </Link>
        </span>
      )}
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

function Footer() {
  const t = useMessages(messages);
  const { info } = useSession();
  return (
    <footer className="hub-footer gh-muted">
      {info?.name ?? "GameHub"} {info?.version} · <Link to="/terms">{t("terms")}</Link> ·{" "}
      {t("footerGit")}
    </footer>
  );
}

function Pages(props: { customUis?: GameUiRegistry | undefined }) {
  const t = useMessages(messages);
  const { pathname, search } = useLocation();
  const route = parseHubRoute(pathname, search);
  switch (route.page) {
    case "home":
      return <HomePage />;
    case "explore":
      return <ExplorePage key={search} q={route.q} />;
    case "login":
      return <LoginPage key={route.mode} mode={route.mode} />;
    case "terms":
      return <TermsPage />;
    case "settings":
      return <SettingsPage />;
    case "new":
      return <NewRepoPage />;
    case "admin":
      return <AdminPage />;
    case "room": {
      const code = normalizeCode(route.code);
      if (code === null) return <p className="gh-shell-error">{t("badCode")}</p>;
      return <RoomPage key={code} server="" code={code} customUis={props.customUis} />;
    }
    case "replay":
      return <ReplayPage key={route.id} server="" id={route.id} />;
    case "account":
      return <AccountPage key={route.name} name={route.name} />;
    case "repo":
      return <RepoPage key={`${route.owner}/${route.name}`} route={route} />;
    case "edit":
      return <EditPage key={`${route.owner}/${route.name}/${route.path}`} route={route} />;
    case "pull":
      return <PullPage key={`${route.owner}/${route.name}/${route.number}`} route={route} />;
    case "newPull":
      return <NewPullPage owner={route.owner} name={route.name} />;
    case "play":
      if (route.mode === "local") {
        return (
          <LocalPlay
            game={`${route.owner}/${route.name}${route.version ? `@${route.version}` : ""}`}
            customUis={props.customUis}
          />
        );
      }
      return <PlayPage key={`${route.owner}/${route.name}/${route.mode}`} route={route} />;
    default:
      return (
        <div className="gh-shell-page">
          <h1>{t("missingTitle")}</h1>
          <p>{t("missingText")}</p>
          <Link to="/">{t("home")}</Link>
        </div>
      );
  }
}

function LocalPlay(props: { game: string; customUis?: GameUiRegistry | undefined }) {
  return <HotSeat key={props.game} server="" game={props.game} customUis={props.customUis} />;
}
