// SPDX-License-Identifier: Apache-2.0
import "@gamehub/ui-kit/styles.css";
import "@gamehub/auto-ui/styles.css";
import "@gamehub/shell/styles.css";
import { type GameUi, PlayApp, registry } from "@gamehub/shell";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Kit } from "./Kit";

// Las UIs propias de los juegos del catálogo (games/<juego>/ui): se registran solas.
const customUis = registry(
  import.meta.glob<{ default: GameUi }>("../../../../games/*/ui/src/index.tsx", { eager: true }),
);

const root = document.getElementById("root");
if (root) {
  createRoot(root).render(
    <StrictMode>
      <PlayApp customUis={customUis} extra={(route) => (route.page === "kit" ? <Kit /> : null)} />
    </StrictMode>,
  );
}
