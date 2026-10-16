# GameHub · web

Monorepo TypeScript del cliente web de GameHub (Fase 4): el SDK para hablar con el servidor de
partidas, la interfaz genérica que dibuja cualquier juego a partir de su IR, el kit de componentes
y la app para jugar en el navegador.

| Paquete | Qué es |
|---|---|
| [`@gamehub/protocol`](packages/protocol) | Tipos del protocolo v1 (generados desde [`spec/protocol`](../spec/protocol) con `gamehub protocol types --write`) y utilidades (códigos de sala) |
| [`@gamehub/i18n`](packages/i18n) | Español e inglés: textos traducibles de la IR, catálogos de mensajes, idioma elegido |
| [`@gamehub/ui-kit`](packages/ui-kit) | Componentes de React: rejilla, carta, mano, montón, mazo, dado, ficha, recorrido, grafo, marcador, reloj, barra de acciones; estilos con variables CSS (tema claro y oscuro) |
| [`@gamehub/client`](packages/client) | SDK cliente: conexión WebSocket con reconexión y `resume`, estado de la sala y la partida (inmutable, apto para React), acciones legales y progresivas, sesiones guardadas, API REST |
| [`@gamehub/react`](packages/react) | Hooks de React sobre el SDK: sala, partida, vista, acciones legales, jugar, IR de la sala |
| [`@gamehub/auto-ui`](packages/auto-ui) | **UI genérica**: cualquier juego dibujado y jugable a partir de su IR (tipos, dominios de las acciones y pistas `ui`), con registro de eventos y resultado |
| [`@gamehub/shell`](packages/shell) | La experiencia de jugar como librería: inicio, crear y entrar en salas, lobby (invitar con código, enlace o QR; asientos, bots, configuración), partida con la UI genérica o una propia, chat, revancha, replays paso a paso y partidas en un mismo dispositivo |
| [`apps/play`](apps/play) | La app web (Vite) que sirve `gamehub serve`: registra sola las UIs propias de `games/*/ui` y tiene una galería del kit en `/kit` |
| [`@gamehub/nomos`](packages/nomos) | Nomos (el lenguaje `.game`) para CodeMirror 6: resaltado, sangría, plegado y tema claro/oscuro |
| [`@gamehub/studio`](packages/studio) | **El Studio** como librería de React: conexión con `gamehub studio` (LSP y métodos propios por WebSocket), diagrama (React Flow + ELK), editor de texto y campos de Nomos (CodeMirror), inspector, diseñador de componentes, simulador, partidas masivas, árbol, comparar y exportar |
| [`apps/studio`](apps/studio) | La app del Studio (Vite) que sirve `gamehub studio` |

## Requisitos

- **Node 22** (`nvm use` en la raíz lee `.nvmrc`).
- **pnpm**, mediante corepack: `corepack enable` una vez (o `corepack pnpm …` sin activarlo).

El workspace de pnpm está en la **raíz del repositorio** (`pnpm-workspace.yaml`): incluye
`web/packages/*`, `web/apps/*` y las UIs propias de los juegos (`games/<juego>/ui`). Los comandos
se ejecutan desde la raíz.

## Comandos

```bash
pnpm install          # dependencias (versiones exactas en el catálogo de pnpm-workspace.yaml)
pnpm test             # tests de todos los paquetes (Vitest); los de integración arrancan
                      # `gamehub serve` o `gamehub studio` con uv (GAMEHUB_SKIP_SERVER_TESTS=1
                      # los salta)
pnpm typecheck        # TypeScript estricto
pnpm lint             # Biome: lint y formato (pnpm format para corregir)
pnpm build            # compila las apps (web/apps/play/dist y web/apps/studio/dist), que luego
                      # sirven gamehub serve y gamehub studio
pnpm dev              # la app con recarga en caliente (http://localhost:5173), contra un
                      # servidor de partidas local: cd python && uv run gamehub serve ../games
pnpm dev:studio       # el Studio con recarga en caliente (http://localhost:5175/?token=…),
                      # contra `GAMEHUB_STUDIO_TOKEN=… uv run gamehub studio ../games`
```

Para jugar en el navegador basta con compilar una vez y arrancar el servidor:

```bash
pnpm install && pnpm build
cd python && uv run gamehub serve ../games --open
```

## UIs propias

`gamehub ui new games/<juego>` crea una UI de React para un juego en `games/<juego>/ui`, con los
tipos del juego (`gamehub sdk ts`), un tablero inicial, un test y un servidor de desarrollo
(`pnpm dev` en su carpeta: la app solo con ese juego). La app web registra sola las UIs de
`games/*/ui`. Ejemplos: [tres en raya](../games/tictactoe/ui), [Conecta 4](../games/connect-four/ui)
y [Dudo](../games/dudo/ui).
