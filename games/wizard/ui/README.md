# UI propia de Wizard

Una interfaz de React para jugar a Wizard en GameHub. La app web la usa en vez de la UI
genérica (con un botón para cambiar entre las dos).

## Desarrollar

Desde la raíz del repositorio:

```bash
pnpm install                                  # enlaza este paquete con los de GameHub
cd python && uv run gamehub serve ../games    # el servidor de partidas (en otra terminal)
cd games/wizard/ui && pnpm dev          # la app solo con este juego: http://localhost:5174
```

Edita `src/Board.tsx`: la página se recarga sola. Crea una sala con bots para probar.

- `src/game.ts` tiene los tipos del juego (vista, acciones, opciones), generados de las reglas.
  Si cambian las reglas, regenéralos con `pnpm types` y TypeScript te dirá qué hay que tocar.
- Los componentes de `@gamehub/ui-kit` (rejilla, cartas, manos, dados, fichas, relojes…) y sus
  variables de estilo (`--gh-…`) están en la galería de la app: http://localhost:5174/kit.
- `pnpm test` pasa los tests (`test/`) y `pnpm typecheck`, los tipos; el formato y el lint, desde
  la raíz del repositorio: `pnpm lint`.

Para usarla en la app de verdad, compila la app web (`pnpm build` en la raíz): las UIs de
`games/*/ui` se registran solas.
