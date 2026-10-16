// SPDX-License-Identifier: Apache-2.0
// Servidor de desarrollo de la UI: la app de GameHub solo con este juego y con esta UI.
import "@gamehub/ui-kit/styles.css";
import "@gamehub/auto-ui/styles.css";
import "@gamehub/shell/styles.css";
import { PlayApp } from "@gamehub/shell";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import ui from "./index";

const root = document.getElementById("root");
if (root) {
  createRoot(root).render(
    <StrictMode>
      <PlayApp customUis={{ [ui.game]: ui }} only={ui.game} brand="Wizard · UI propia" />
    </StrictMode>,
  );
}
