// SPDX-License-Identifier: Apache-2.0
/**
 * Sesiones guardadas en el navegador (localStorage): el token de cada sala, para volver al mismo
 * asiento al recargar la página o tras cerrar la pestaña (como `sessions.json` en la terminal).
 */

export interface SavedSession {
  token: string;
  name: string;
  /** Milisegundos desde la época. */
  savedAt: number;
}

const PREFIX = "gamehub:session:";
/** Las sesiones caducan a los 7 días (el servidor cierra antes las salas sin nadie). */
const MAX_AGE = 7 * 24 * 3600 * 1000;

function storage(): Storage | null {
  try {
    return typeof localStorage === "undefined" ? null : localStorage;
  } catch {
    return null;
  }
}

function key(server: string, code: string): string {
  return `${PREFIX}${server}|${code}`;
}

export function saveSession(server: string, code: string, token: string, name: string): void {
  const value: SavedSession = { token, name, savedAt: Date.now() };
  try {
    storage()?.setItem(key(server, code), JSON.stringify(value));
  } catch {
    // Sin almacenamiento (modo privado, cuota): la sesión dura lo que la pestaña.
  }
}

export function loadSession(server: string, code: string): SavedSession | null {
  try {
    const raw = storage()?.getItem(key(server, code));
    if (raw == null) return null;
    const value = JSON.parse(raw) as SavedSession;
    if (typeof value.token !== "string" || Date.now() - value.savedAt > MAX_AGE) {
      forgetSession(server, code);
      return null;
    }
    return value;
  } catch {
    return null;
  }
}

export function forgetSession(server: string, code: string): void {
  try {
    storage()?.removeItem(key(server, code));
  } catch {
    // Nada que hacer.
  }
}
