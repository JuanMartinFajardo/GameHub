// SPDX-License-Identifier: AGPL-3.0-or-later
/** Las rutas de la app del hub (se enrutan en el navegador; el servidor sirve siempre la app). */

export type RepoTab =
  | "rules"
  | "code"
  | "versions"
  | "pulls"
  | "analysis"
  | "ratings"
  | "interfaces"
  | "variants"
  | "activity";

export const REPO_TABS: readonly RepoTab[] = [
  "rules",
  "code",
  "versions",
  "pulls",
  "analysis",
  "ratings",
  "interfaces",
  "variants",
  "activity",
];

export type HubRoute =
  | { page: "home" }
  | { page: "explore"; q: string }
  | { page: "login"; mode: "login" | "signup" }
  | { page: "terms" }
  | { page: "settings" }
  | { page: "new" }
  | { page: "admin" }
  | { page: "room"; code: string }
  | { page: "replay"; id: string }
  | { page: "account"; name: string }
  | { page: "repo"; owner: string; name: string; tab: RepoTab; ref: string | null; path: string }
  | { page: "edit"; owner: string; name: string; ref: string | null; path: string }
  | { page: "pull"; owner: string; name: string; number: number; tab: PullTab }
  | { page: "newPull"; owner: string; name: string }
  | { page: "play"; owner: string; name: string; version: string | null; mode: PlayMode }
  | { page: "missing"; path: string };

export type PullTab = "conversation" | "text" | "semantic" | "visual" | "balance";
export type PlayMode = "online" | "local" | "match";

const SIMPLE: Record<string, HubRoute> = {
  "": { page: "home" },
  terms: { page: "terms" },
  settings: { page: "settings" },
  new: { page: "new" },
  admin: { page: "admin" },
  login: { page: "login", mode: "login" },
  signup: { page: "login", mode: "signup" },
};

const PULL_TABS: readonly PullTab[] = ["conversation", "text", "semantic", "visual", "balance"];

export function parseHubRoute(pathname: string, search = ""): HubRoute {
  const parts = pathname
    .split("/")
    .filter((p) => p !== "")
    .map((p) => {
      try {
        return decodeURIComponent(p);
      } catch {
        return p;
      }
    });
  const params = new URLSearchParams(search);
  const [first = "", second, third, fourth] = parts;
  if (parts.length <= 1 && first in SIMPLE) return SIMPLE[first] as HubRoute;
  if (first === "explore" && parts.length === 1)
    return { page: "explore", q: params.get("q") ?? "" };
  if (first === "r" && second && parts.length === 2) return { page: "room", code: second };
  if (first === "replay" && second && parts.length === 2) return { page: "replay", id: second };
  if (parts.length === 1) return { page: "account", name: first };
  if (second === undefined) return { page: "missing", path: pathname };
  const owner = first;
  const name = second;
  const ref = params.get("ref");
  if (parts.length === 2) {
    return { page: "repo", owner, name, tab: "rules", ref, path: "" };
  }
  if (third === "pulls" && fourth === "new" && parts.length === 4) {
    return { page: "newPull", owner, name };
  }
  if (third === "pulls" && fourth !== undefined && /^\d+$/.test(fourth)) {
    const tab = parts[4] as PullTab | undefined;
    return {
      page: "pull",
      owner,
      name,
      number: Number(fourth),
      tab: tab && PULL_TABS.includes(tab) ? tab : "conversation",
    };
  }
  if (third === "play" || third === "local" || third === "match") {
    const mode: PlayMode = third === "play" ? "online" : third;
    return { page: "play", owner, name, version: params.get("version"), mode };
  }
  if (third === "edit") {
    return { page: "edit", owner, name, ref, path: parts.slice(3).join("/") };
  }
  if (third === "code") {
    return { page: "repo", owner, name, tab: "code", ref, path: parts.slice(3).join("/") };
  }
  if (third && (REPO_TABS as readonly string[]).includes(third) && parts.length === 3) {
    return { page: "repo", owner, name, tab: third as RepoTab, ref, path: "" };
  }
  return { page: "missing", path: pathname };
}

/** La URL de una pestaña de un repositorio. */
export function repoUrl(full: string, tab: RepoTab = "rules", extra = ""): string {
  const base = `/${full}`;
  if (tab === "rules") return base + extra;
  return `${base}/${tab}${extra}`;
}

export function enc(path: string): string {
  return path
    .split("/")
    .map((p) => encodeURIComponent(p))
    .join("/");
}
