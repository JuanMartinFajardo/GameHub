// SPDX-License-Identifier: Apache-2.0
/** La API del espacio de trabajo de `gamehub studio` (archivos, disposición, plantillas, git). */

import type { LayoutFile, OpenedFile, WorkspaceInfo } from "./types";

const TOKEN_KEY = "gamehub:studio-token";

/**
 * El token del Studio. Al servir la app, `gamehub studio` lo pone en una cookie; en desarrollo
 * (con el servidor de Vite delante) llega en la URL (`?token=…`) y se guarda para la pestaña.
 */
export function studioToken(location: { search: string } = window.location): string | null {
  const given = new URLSearchParams(location.search).get("token");
  try {
    if (given) sessionStorage.setItem(TOKEN_KEY, given);
    return given ?? sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return given;
  }
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export class StudioApi {
  constructor(
    readonly base = "",
    readonly token: string | null = null,
    private readonly fetcher: typeof fetch = (...args) => fetch(...args),
  ) {}

  private async call<T>(method: string, path: string, body?: unknown): Promise<T> {
    const headers: Record<string, string> = {};
    if (this.token) headers["x-gamehub-token"] = this.token;
    if (body !== undefined) headers["content-type"] = "application/json";
    const response = await this.fetcher(this.base + path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "same-origin",
    });
    const data = (await response.json().catch(() => ({}))) as { error?: string };
    if (!response.ok) throw new ApiError(data.error ?? response.statusText, response.status);
    return data as T;
  }

  workspace(): Promise<WorkspaceInfo> {
    return this.call("GET", "/api/workspace");
  }

  read(path: string): Promise<OpenedFile> {
    return this.call("GET", `/api/file?path=${encodeURIComponent(path)}`);
  }

  save(path: string, text: string, mtime: number | null): Promise<{ path: string; mtime: number }> {
    return this.call("PUT", "/api/file", { path, text, mtime });
  }

  saveLayout(path: string, layout: LayoutFile): Promise<{ ok: boolean }> {
    return this.call("PUT", "/api/layout", { path, layout });
  }

  newGame(name: string, template: string, title?: string): Promise<{ path: string }> {
    return this.call("POST", "/api/new", { name, template, title });
  }

  history(path: string): Promise<{ rev: string; date: string; subject: string }[]> {
    return this.call("GET", `/api/git/log?path=${encodeURIComponent(path)}`);
  }

  show(path: string, rev: string): Promise<{ text: string }> {
    return this.call(
      "GET",
      `/api/git/show?path=${encodeURIComponent(path)}&rev=${encodeURIComponent(rev)}`,
    );
  }
}
