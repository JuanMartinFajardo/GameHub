// SPDX-License-Identifier: Apache-2.0
import { resolve } from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// En desarrollo (`pnpm dev:hub`), la API, git, las Pages y el WebSocket van a un hub local
// (`gamehub hub serve`, puerto 7430; otro con GAMEHUB_HUB=http://host:puerto).
const hub = process.env.GAMEHUB_HUB ?? "http://127.0.0.1:7430";

export default defineConfig({
  plugins: [react()],
  resolve: { dedupe: ["react", "react-dom"] },
  server: {
    port: 5175,
    proxy: {
      "/api": hub,
      "/auth": hub,
      "/pages": hub,
      "/ws": { target: hub.replace(/^http/, "ws"), ws: true },
    },
    // Las UIs propias de los juegos del catálogo viven en games/<juego>/ui.
    fs: {
      allow: [
        resolve(import.meta.dirname, "../.."),
        resolve(import.meta.dirname, "../../../games"),
      ],
    },
  },
  build: { outDir: "dist", emptyOutDir: true, chunkSizeWarningLimit: 1500 },
});
