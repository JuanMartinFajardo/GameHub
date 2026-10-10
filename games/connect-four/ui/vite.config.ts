// SPDX-License-Identifier: Apache-2.0
import { resolve } from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// `pnpm dev` abre la app solo con este juego y esta UI, contra el servidor de partidas local
// (`cd python && uv run gamehub serve ../games`; otro con GAMEHUB_SERVER=http://host:puerto).
const server = process.env.GAMEHUB_SERVER ?? "http://127.0.0.1:7420";

export default defineConfig({
  plugins: [react()],
  resolve: { dedupe: ["react", "react-dom"] },
  server: {
    port: 5174,
    proxy: {
      "/api": server,
      "/ws": { target: server.replace(/^http/, "ws"), ws: true },
    },
    fs: { allow: [resolve(import.meta.dirname, "../../..")] },
  },
});
