// SPDX-License-Identifier: Apache-2.0
/**
 * La conexión con `gamehub studio`: un WebSocket con el servidor de lenguaje (LSP) de Nomos y los
 * métodos propios del Studio (`gamehub/…`). Usa el cliente LSP de CodeMirror: el editor de texto
 * se engancha a él (`client.plugin(uri)`) y el resto de la app le hace peticiones propias con
 * `request` (siempre tras sincronizar el texto, para que el servidor vea la última versión).
 */

import { LSPClient, languageServerExtensions, type Transport } from "@codemirror/lsp-client";
import type { Analysis } from "./types";

export type ConnectionStatus = "connecting" | "open" | "closed";

/** Lo mínimo de un WebSocket (el del navegador o el del paquete `ws` en los tests). */
export interface SocketLike {
  readyState: number;
  send(data: string): void;
  close(): void;
  onopen: ((ev: unknown) => void) | null;
  onclose: ((ev: unknown) => void) | null;
  onerror: ((ev: unknown) => void) | null;
  onmessage: ((ev: { data: unknown }) => void) | null;
}

/** Error de una petición: el del servidor (código, mensaje y datos) o uno local. */
export class RequestError extends Error {
  constructor(
    message: string,
    readonly code: number,
    readonly data?: unknown,
  ) {
    super(message);
    this.name = "RequestError";
  }
}

function asError(error: unknown): RequestError {
  if (error instanceof RequestError) return error;
  if (error && typeof error === "object" && "message" in error) {
    const e = error as { message: string; code?: number; data?: unknown };
    return new RequestError(String(e.message), typeof e.code === "number" ? e.code : -1, e.data);
  }
  return new RequestError(String(error), -1);
}

export interface ConnectionOptions {
  url: string;
  rootUri?: string;
  /** Cómo abrir el WebSocket (por defecto, el del navegador). */
  webSocket?: (url: string) => SocketLike;
  timeout?: number;
}

export class StudioConnection {
  readonly client: LSPClient;
  readonly analyses = new Map<string, Analysis>();
  status: ConnectionStatus = "closed";
  private socket: SocketLike | null = null;
  private handlers: ((value: string) => void)[] = [];
  private analysisListeners = new Set<(analysis: Analysis) => void>();
  private statusListeners = new Set<(status: ConnectionStatus) => void>();

  constructor(private readonly options: ConnectionOptions) {
    this.client = new LSPClient({
      rootUri: options.rootUri,
      timeout: options.timeout ?? 120_000,
      extensions: languageServerExtensions(),
      notificationHandlers: {
        "gamehub/analysis": (_client, params: Analysis) => {
          this.analyses.set(params.uri, params);
          for (const listener of this.analysisListeners) listener(params);
          return true;
        },
      },
    });
  }

  /** Abre el WebSocket e inicializa el servidor de lenguaje. */
  async connect(): Promise<void> {
    this.setStatus("connecting");
    const open = this.options.webSocket ?? ((url: string) => new WebSocket(url) as SocketLike);
    const socket = open(this.options.url);
    this.socket = socket;
    await new Promise<void>((resolve, reject) => {
      socket.onopen = () => resolve();
      socket.onerror = () => reject(new RequestError("no se pudo conectar con el Studio", -1));
      socket.onclose = () => reject(new RequestError("la conexión con el Studio se cerró", -1));
    });
    socket.onmessage = (event) => {
      const data = typeof event.data === "string" ? event.data : String(event.data);
      for (const handler of this.handlers) handler(data);
    };
    socket.onclose = () => {
      if (this.socket === socket) {
        this.socket = null;
        this.client.disconnect();
        this.setStatus("closed");
      }
    };
    socket.onerror = null;
    const transport: Transport = {
      send: (message) => {
        if (socket.readyState !== 1) {
          // Una petición falla (el cliente la rechaza); una notificación se pierde sin más: la
          // conexión se está cerrando y el estado ya lo dice.
          if ((JSON.parse(message) as { id?: unknown }).id !== undefined) {
            throw new Error("conexión cerrada");
          }
          return;
        }
        socket.send(message);
      },
      subscribe: (handler) => {
        this.handlers.push(handler);
      },
      unsubscribe: (handler) => {
        this.handlers = this.handlers.filter((h) => h !== handler);
      },
    };
    this.client.connect(transport);
    await this.client.initializing;
    this.setStatus("open");
  }

  close(): void {
    const socket = this.socket;
    this.socket = null;
    this.client.disconnect();
    socket?.close();
    this.setStatus("closed");
  }

  /** Una petición propia (`gamehub/…`) o del LSP, con el texto ya sincronizado. */
  async request<T>(method: string, params: unknown): Promise<T> {
    if (this.status !== "open") throw new RequestError("sin conexión con el Studio", -1);
    this.client.sync();
    try {
      return await this.client.request<unknown, T>(method, params);
    } catch (error) {
      throw asError(error);
    }
  }

  /** La versión del documento que tiene el servidor (tras sincronizar). */
  version(uri: string): number | null {
    this.client.sync();
    return this.client.workspace.getFile(uri)?.version ?? null;
  }

  onAnalysis(listener: (analysis: Analysis) => void): () => void {
    this.analysisListeners.add(listener);
    return () => this.analysisListeners.delete(listener);
  }

  onStatus(listener: (status: ConnectionStatus) => void): () => void {
    this.statusListeners.add(listener);
    return () => this.statusListeners.delete(listener);
  }

  private setStatus(status: ConnectionStatus) {
    this.status = status;
    for (const listener of this.statusListeners) listener(status);
  }
}

/** La URL del WebSocket del Studio en la misma máquina que la página (con el token si se da). */
export function lspUrl(location: { protocol: string; host: string }, token: string | null): string {
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${location.host}/lsp${token ? `?token=${encodeURIComponent(token)}` : ""}`;
}
