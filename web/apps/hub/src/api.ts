// SPDX-License-Identifier: AGPL-3.0-or-later
/** La API del hub (`/api/v1`): peticiones con la cookie de sesión y los tipos de lo que vuelve. */

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

export async function api<T = unknown>(
  method: string,
  path: string,
  body?: unknown,
  options: { raw?: BodyInit; contentType?: string } = {},
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  let payload: BodyInit | undefined;
  if (options.raw !== undefined) {
    payload = options.raw;
    headers["Content-Type"] = options.contentType ?? "application/octet-stream";
  } else if (body !== undefined) {
    payload = JSON.stringify(body);
    headers["Content-Type"] = "application/json";
  }
  const response = await fetch(`/api/v1${path}`, {
    method,
    headers,
    body: payload,
    credentials: "same-origin",
  });
  const text = await response.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }
  if (!response.ok) {
    const err = (data as { error?: { code?: string; message?: string } } | null)?.error;
    throw new ApiError(response.status, err?.code ?? "error", err?.message ?? response.statusText);
  }
  return data as T;
}

export const get = <T>(path: string) => api<T>("GET", path);
export const post = <T>(path: string, body: unknown = {}) => api<T>("POST", path, body);

export function query(
  params: Record<string, string | number | boolean | null | undefined>,
): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== null && v !== undefined && v !== "") q.set(k, String(v));
  }
  const text = q.toString();
  return text ? `?${text}` : "";
}

export function errorText(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

// --- tipos ----------------------------------------------------------------------------------------

export interface HubInfo {
  name: string;
  version: string;
  signup: boolean;
  terms_version: string;
  oauth: { name: string; title: string }[];
}

export interface User {
  name: string;
  kind: "user" | "org";
  display: string;
  bio: string;
  created: number;
  admin?: boolean;
  suspended?: boolean;
  email?: string | null;
  terms?: string | null;
  terms_current?: boolean;
  orgs?: string[];
}

export interface ReleaseSummary {
  version: string;
  title: string;
  rules_hash: string | null;
  game: string | null;
  created: number;
}

export interface Repo {
  owner: string;
  owner_kind: string;
  name: string;
  full_name: string;
  kind: "game" | "library";
  description: string;
  parent: string | null;
  default_branch: string;
  stars: number;
  forks: number;
  size: number;
  hidden: boolean;
  created: number;
  updated: number;
  latest: ReleaseSummary | null;
  starred: boolean;
  can_write: boolean;
  can_admin: boolean;
  clone_url?: string;
  empty?: boolean;
  open_pulls?: number;
  release?: Release;
}

export interface Classification {
  players: { min: number; max: number };
  chance: boolean;
  perfect_information: boolean;
  simultaneous: boolean;
  zero_sum: boolean | null;
  labels?: string[];
}

export interface Release {
  repo: string;
  version: string;
  ref: string;
  commit: string;
  level: "major" | "minor" | "patch" | null;
  game: string | null;
  title: string;
  rules_hash: string | null;
  interface_hash: string | null;
  properties: Partial<Classification> & {
    labels?: string[];
    files?: number;
    analysis?: {
      tree_log10: number;
      leaves_log10: number;
      branching: number;
      depth_mean: number;
      depth_max: number;
      exact: Record<string, number>;
    };
    recommendations?: { code: string; text: string; phase: string | null }[];
  };
  manifest: { name: string; version: string; license: string | null; authors: string[] };
  dependencies: { repo: string; requirement: string }[];
  notes: string;
  publisher: string | null;
  yanked: boolean;
  created: number;
  pages?: Page[];
}

export interface Built {
  commit: string;
  problems: string[];
  entry: string | null;
  // biome-ignore lint/suspicious/noExplicitAny: el modelo del Studio (sus tipos están en @gamehub/studio).
  model: { game: any } | null;
  games: string[];
  game?: string;
  rules_hash?: string;
  interface_hash?: string;
  classification?: Classification & { labels: string[] };
  rules?: string;
  meta?: Record<string, unknown>;
}

export interface TreeEntry {
  name: string;
  path: string;
  type: "file" | "dir";
  size: number | null;
}

export interface Commit {
  id: string;
  parents: string[];
  author: string;
  time: number;
  subject: string;
  body: string;
}

export interface Pull {
  number: number;
  repo: string;
  source: string;
  head: string;
  base: string;
  title: string;
  body: string;
  author: string;
  state: "open" | "merged" | "closed";
  head_commit: string;
  base_commit: string;
  merge_commit: string | null;
  mergeable: boolean | null;
  balance_job: number | null;
  comments: { author: string; body: string; created: number }[];
  created: number;
  updated: number;
  can_merge: boolean;
  can_close: boolean;
  balance?: Job;
}

export interface SemanticChange {
  op: "+" | "-" | "~";
  path: string;
  old?: string;
  new?: string;
}

export interface InterfaceChange {
  op: "+" | "-" | "~";
  path: string;
  breaking: boolean;
}

export interface PullDiff {
  text: {
    patch: string;
    files: { path: string; added: number | null; removed: number | null }[];
    truncated: boolean;
  };
  base_problems: string[];
  head_problems: string[];
  semantic: {
    same_rules?: boolean;
    old_hash?: string;
    new_hash?: string;
    changes: SemanticChange[];
    interface: InterfaceChange[];
    level?: "major" | "minor" | "patch" | null;
  } | null;
  // biome-ignore lint/suspicious/noExplicitAny: modelos del Studio.
  visual: { base: { game: any } | null; head: { game: any } | null };
}

export interface Job {
  id: number;
  kind: string;
  status: "queued" | "running" | "done" | "failed";
  account: string | null;
  error: string | null;
  seconds: number | null;
  created: number;
  position: number | null;
  version?: string;
  pull?: number;
  // biome-ignore lint/suspicious/noExplicitAny: cada tipo de trabajo tiene su resultado.
  result?: any;
}

export interface Page {
  name: string;
  repo: string;
  interface_hash: string;
  files: number;
  size: number;
  versions: string[];
  url: string;
  created: number;
}

export interface HubEvent {
  kind: string;
  who: string | null;
  // biome-ignore lint/suspicious/noExplicitAny: cada suceso tiene sus datos.
  data: any;
  time: number;
  repo?: string;
}

export interface Rating {
  account: string;
  elo: number;
  glicko: number;
  glicko_rd: number;
  trueskill: number;
  games: number;
}

export interface MatchRecord {
  id: string;
  game: string;
  players: { name: string; kind: string; account: string | null }[];
  result: { reason: string; ranking: number[]; payoffs: unknown[] | null };
  rated: boolean;
  humans_only: boolean;
  created: number;
}

export interface FamilyNode {
  repo: string;
  description: string;
  stars: number;
  version: string | null;
  current: boolean;
  children: FamilyNode[];
}

export interface Ticket {
  id: string;
  game: string;
  players: number;
  status: "waiting" | "matched";
  waiting: number;
  room: string | null;
  token: string | null;
  seat: number | null;
}
