// SPDX-License-Identifier: Apache-2.0
import type { ErrorInfo } from "@gamehub/protocol";

/** Códigos de error del cliente: los del protocolo más los de la conexión y la API REST. */
export type ClientErrorCode = ErrorInfo["code"] | "connection" | "timeout" | "http" | "closed";

/** Un error del servidor (con el `code` del protocolo) o de la conexión. */
export class ClientError extends Error {
  readonly code: ClientErrorCode;

  constructor(code: ClientErrorCode, message: string) {
    super(message);
    this.name = "ClientError";
    this.code = code;
  }
}
