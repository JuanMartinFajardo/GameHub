// SPDX-License-Identifier: Apache-2.0
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// En desarrollo (`pnpm dev:studio`), la API y el WebSocket del LSP van a `gamehub studio`
// (puerto 7421; otro con GAMEHUB_STUDIO=http://host:puerto). Ábrelo con el token que muestra
// `gamehub studio` (o arráncalo con GAMEHUB_STUDIO_TOKEN fijo): http://localhost:5175/?token=…
const studio = process.env.GAMEHUB_STUDIO ?? "http://127.0.0.1:7421";

export default defineConfig({
  plugins: [react()],
  resolve: { dedupe: ["react", "react-dom", "@codemirror/state", "@codemirror/view"] },
  server: {
    port: 5175,
    proxy: {
      "/api": { target: studio, changeOrigin: true },
      "/lsp": { target: studio.replace(/^http/, "ws"), ws: true, changeOrigin: true },
    },
  },
  build: { outDir: "dist", emptyOutDir: true, chunkSizeWarningLimit: 4000 },
});
