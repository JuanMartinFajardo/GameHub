# GameHub · web

Monorepo TypeScript del cliente web de GameHub (Fase 4): el SDK para hablar con el servidor de
partidas, la interfaz genérica que dibuja cualquier juego a partir de su IR, el kit de componentes
y la app para jugar en el navegador.

| Paquete | Qué es |
|---|---|
| [`@gamehub/protocol`](packages/protocol) | Tipos del protocolo v1 (generados desde [`spec/protocol`](../spec/protocol) con `gamehub protocol types --write`) y utilidades (códigos de sala) |
| [`@gamehub/client`](packages/client) | SDK cliente: conexión WebSocket con reconexión y `resume`, estado de la sala y la partida (inmutable, apto para React), acciones legales y progresivas, sesiones guardadas, API REST |

## Requisitos

- **Node 22** (`nvm use` en esta carpeta lee `.nvmrc`).
- **pnpm**, mediante corepack: `corepack enable` una vez (o `corepack pnpm …` sin activarlo).

## Comandos

```bash
cd web
pnpm install          # dependencias (versiones exactas en pnpm-workspace.yaml)
pnpm test             # tests de todos los paquetes (Vitest); los de integración arrancan
                      # `gamehub serve` con uv (GAMEHUB_SKIP_SERVER_TESTS=1 los salta)
pnpm typecheck        # TypeScript estricto
pnpm lint             # Biome: lint y formato (pnpm format para corregir)
```
