// SPDX-License-Identifier: Apache-2.0
import "@gamehub/ui-kit/styles.css";
import "@gamehub/auto-ui/styles.css";
import "@gamehub/studio/styles.css";
import { LocaleProvider } from "@gamehub/i18n";
import { StudioApp } from "@gamehub/studio";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

const root = document.getElementById("root");
if (root) {
  createRoot(root).render(
    <StrictMode>
      <LocaleProvider>
        <StudioApp />
      </LocaleProvider>
    </StrictMode>,
  );
}
