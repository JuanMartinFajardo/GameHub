// SPDX-License-Identifier: AGPL-3.0-or-later
import "@gamehub/ui-kit/styles.css";
import "@gamehub/auto-ui/styles.css";
import "@gamehub/shell/styles.css";
import "./styles.css";
import { type GameUi, registry } from "@gamehub/shell";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { HubApp } from "./App";

// Las UIs propias de los juegos del catálogo (games/<juego>/ui): las usan las salas de las
// versiones del hub con el mismo id de juego.
const customUis = registry(
  import.meta.glob<{ default: GameUi }>("../../../../games/*/ui/src/index.tsx", { eager: true }),
);

const root = document.getElementById("root");
if (root) {
  createRoot(root).render(
    <StrictMode>
      <HubApp customUis={customUis} />
    </StrictMode>,
  );
}
