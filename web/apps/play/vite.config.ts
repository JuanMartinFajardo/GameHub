// SPDX-License-Identifier: Apache-2.0
import { resolve } from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// En desarrollo (`pnpm dev`), la API y el WebSocket van al servidor de partidas local
// (`gamehub serve ../games`, puerto 7420; otro con GAMEHUB_SERVER=http://host:puerto).
const server = process.env.GAMEHUB_SERVER ?? "http://127.0.0.1:7420";

export default defineConfig({
  plugins: [react()],
  resolve: { dedupe: ["react", "react-dom"] },
  server: {
    port: 5173,
    proxy: {
      "/api": server,
      "/ws": { target: server.replace(/^http/, "ws"), ws: true },
    },
    // Las UIs propias viven en el paquete de cada juego (games/<juego>/ui).
    fs: {
      allow: [
        resolve(import.meta.dirname, "../.."),
        resolve(import.meta.dirname, "../../../games"),
      ],
    },
  },
  build: { outDir: "dist", emptyOutDir: true, chunkSizeWarningLimit: 900 },
});
