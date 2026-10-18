// SPDX-License-Identifier: Apache-2.0
/** Enrutado mínimo con la API History: las rutas de la app y enlaces que no recargan la página. */

import { type AnchorHTMLAttributes, type MouseEvent, useEffect, useState } from "react";

export type Route =
  | { page: "home" }
  | { page: "room"; code: string }
  | { page: "new"; game: string }
  | { page: "local"; game: string }
  | { page: "replay"; id: string }
  | { page: "kit" }
  | { page: "missing"; path: string };

export function parseRoute(pathname: string): Route {
  const parts = pathname
    .split("/")
    .filter((p) => p !== "")
    .map(decodeURIComponent);
  const [first, second] = parts;
  if (parts.length === 0) return { page: "home" };
  if (parts.length === 2 && second !== undefined) {
    if (first === "r") return { page: "room", code: second };
    if (first === "new") return { page: "new", game: second };
    if (first === "local") return { page: "local", game: second };
    if (first === "replay") return { page: "replay", id: second };
  }
  if (parts.length === 1 && first === "kit") return { page: "kit" };
  return { page: "missing", path: pathname };
}

const EVENT = "gamehub:navigate";

/** Va a otra ruta de la app (sin recargar). */
export function navigate(to: string, options: { replace?: boolean } = {}): void {
  if (options.replace) history.replaceState(null, "", to);
  else history.pushState(null, "", to);
  window.dispatchEvent(new Event(EVENT));
  window.scrollTo?.(0, 0);
}

/** La ruta actual; se actualiza al navegar y con atrás/adelante. */
export function useRoute(): Route {
  return parseRoute(useLocation().pathname);
}

function readLocation(): { pathname: string; search: string } {
  return { pathname: location.pathname, search: location.search };
}

/** La dirección actual (ruta y consulta), para apps con sus propias rutas (el hub). */
export function useLocation(): { pathname: string; search: string } {
  const [current, setCurrent] = useState(readLocation);
  useEffect(() => {
    const update = () => setCurrent(readLocation());
    window.addEventListener("popstate", update);
    window.addEventListener(EVENT, update);
    return () => {
      window.removeEventListener("popstate", update);
      window.removeEventListener(EVENT, update);
    };
  }, []);
  return current;
}

/** Un parámetro de la URL (`?players=3`). */
export function queryParam(name: string): string | null {
  return new URLSearchParams(location.search).get(name);
}

export function Link(props: AnchorHTMLAttributes<HTMLAnchorElement> & { to: string }) {
  const { to, onClick, ...rest } = props;
  const go = (e: MouseEvent<HTMLAnchorElement>) => {
    onClick?.(e);
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey) return;
    e.preventDefault();
    navigate(to);
  };
  return <a href={to} onClick={go} {...rest} />;
}
