# Custom UI for Wizard

A React interface to play Wizard on GameHub. The web app uses it instead of the generic UI
(with a button to switch between the two).

## Development

From the repository root:

```bash
pnpm install                                  # links this package with GameHub's
cd python && uv run gamehub serve ../games    # the match server (in another terminal)
cd games/wizard/ui && pnpm dev          # the app with only this game: http://localhost:5174
```

Edit `src/Board.tsx`: the page reloads by itself. Create a room with bots to try it.

- `src/game.ts` has the game's types (view, actions, options), generated from the rules. If the
  rules change, regenerate them with `pnpm types` and TypeScript will tell you what to change.
- The `@gamehub/ui-kit` components (grid, cards, hands, dice, tokens, clocks…) and their style
  variables (`--gh-…`) are in the app's gallery: http://localhost:5174/kit.
- `pnpm test` runs the tests (`test/`) and `pnpm typecheck`, the types; formatting and lint, from
  the repository root: `pnpm lint`.

To use it in the real app, build the web app (`pnpm build` at the root): the UIs in `games/*/ui`
are registered by themselves.
