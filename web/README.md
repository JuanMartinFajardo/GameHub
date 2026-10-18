# GameHub · web

The TypeScript monorepo of GameHub's web client (Phase 4) and Studio (Phase 5): the SDK to talk to
the match server, the generic interface that draws any game from its IR, the component kit, the
app to play in the browser and the visual editor.

| Package | What it is |
|---|---|
| [`@gamehub/protocol`](packages/protocol) | Protocol v1 types (generated from [`spec/protocol`](../spec/protocol) with `gamehub protocol types --write`) and utilities (room codes) |
| [`@gamehub/i18n`](packages/i18n) | Spanish and English: translatable texts from the IR, message catalogs, chosen language |
| [`@gamehub/ui-kit`](packages/ui-kit) | React components: grid, card, hand, pile, deck, die, token, track, graph, scoreboard, clock, action bar; styles with CSS variables (light and dark themes) |
| [`@gamehub/client`](packages/client) | Client SDK: WebSocket connection with reconnection and `resume`, room and match state (immutable, React-friendly), legal and progressive actions, stored sessions, REST API |
| [`@gamehub/react`](packages/react) | React hooks on top of the SDK: room, match, view, legal actions, playing, the room's IR |
| [`@gamehub/engine`](packages/engine) | The C++ core in **WebAssembly** (built by `gamehub wasm --write`, checked in): games and sessions from the IR, native plugins, the Studio's playouts and local matches without a server that speak the room protocol |
| [`@gamehub/auto-ui`](packages/auto-ui) | **Generic UI**: any game drawn and playable from its IR (types, action domains and `ui` hints), with an event log and the result |
| [`@gamehub/shell`](packages/shell) | The play experience as a library: home, creating and joining rooms, lobby (invite with a code, link or QR code; seats, bots, settings), match with the generic UI or a custom one, chat, rematch, step-by-step replays and matches on a single device |
| [`apps/play`](apps/play) | The web app (Vite) served by `gamehub serve`: it registers the custom UIs in `games/*/ui` by itself and has a kit gallery at `/kit` |
| [`@gamehub/nomos`](packages/nomos) | Nomos (the `.game` language) for CodeMirror 6: highlighting, indentation, folding and light/dark theme |
| [`@gamehub/studio`](packages/studio) | **The Studio** as a React library: connection to `gamehub studio` (LSP and its own methods over WebSocket), diagram (React Flow + ELK), text editor and Nomos fields (CodeMirror), inspector, component designer, simulator, batch runs, tree, compare and export |
| [`apps/studio`](apps/studio) | The Studio app (Vite) served by `gamehub studio` |
| [`apps/hub`](apps/hub) | The hub's website (Vite) served by `gamehub hub serve` (AGPL-3.0-or-later) |

## Requirements

- **Node 22** (`nvm use` at the root reads `.nvmrc`).
- **pnpm**, through corepack: `corepack enable` once (or `corepack pnpm …` without enabling it).

The pnpm workspace lives at the **repository root** (`pnpm-workspace.yaml`): it includes
`web/packages/*`, `web/apps/*` and the games' custom UIs (`games/<game>/ui`). Commands are run
from the root.

## Commands

```bash
pnpm install          # dependencies (exact versions in the pnpm-workspace.yaml catalog)
pnpm test             # tests of every package (Vitest); integration tests start
                      # `gamehub serve` or `gamehub studio` with uv (GAMEHUB_SKIP_SERVER_TESTS=1
                      # skips them)
pnpm typecheck        # strict TypeScript
pnpm lint             # Biome: lint and formatting (pnpm format to fix)
pnpm build            # builds the apps (web/apps/{play,studio,hub}/dist), which gamehub serve,
                      # gamehub studio and gamehub hub serve then serve
pnpm dev              # the app with hot reload (http://localhost:5173), against a local match
                      # server: cd python && uv run gamehub serve ../games
pnpm dev:studio       # the Studio with hot reload (http://localhost:5175/?token=…), against
                      # `GAMEHUB_STUDIO_TOKEN=… uv run gamehub studio ../games`
pnpm dev:hub          # the hub's website with hot reload (http://localhost:5176), against
                      # `uv run gamehub hub serve --data hub-data` (port 7430)
```

To play in the browser, it is enough to build once and start the server:

```bash
pnpm install && pnpm build
cd python && uv run gamehub serve ../games --open
```

## Custom UIs

`gamehub ui new games/<game>` creates a React UI for a game in `games/<game>/ui`, with the game's
types (`gamehub sdk ts`), a starting board, a test and a development server (`pnpm dev` in its
folder: the app with only that game). The web app registers the UIs in `games/*/ui` by itself.
Examples: [tic-tac-toe](../games/tictactoe/ui), [Connect Four](../games/connect-four/ui),
[Dudo](../games/dudo/ui), [chess](../games/chess/ui), [Texas Hold'em](../games/texas-holdem/ui),
[Wizard](../games/wizard/ui) and [Parchís](../games/parchis/ui).
