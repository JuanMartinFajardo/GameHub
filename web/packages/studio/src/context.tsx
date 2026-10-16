// SPDX-License-Identifier: Apache-2.0
/** El Studio para los componentes: `useStudio()` da el estado (y se redibuja al cambiar) y el objeto. */

import { createContext, useContext, useSyncExternalStore } from "react";
import type { Studio, StudioState } from "./store";

export const StudioContext = createContext<Studio | null>(null);

export function useStudio(): [StudioState, Studio] {
  const studio = useContext(StudioContext);
  if (!studio) throw new Error("useStudio fuera de <StudioContext>");
  const state = useSyncExternalStore(studio.subscribe, studio.getState);
  return [state, studio];
}
