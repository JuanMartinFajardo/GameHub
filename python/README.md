# gamehub (Python package)

GameHub's tools in Python: the **Nomos** language (compiler, formatter, tests, analysis, language
server), the GameIR, the reference engine (with native WebAssembly plugins), the **Studio** (a
visual editor with a simulator), the **match server** (which also serves the web app to play in
the browser), the client SDK, network play from the terminal and the tools to build custom
interfaces.

```bash
uv sync                                          # development environment
uv run pytest                                    # tests (LAN/mDNS ones: GAMEHUB_LAN_TESTS=1)
uv run pytest -m slow                            # the long ones (deep chess perft)
uv run gamehub check ../games                    # compile and analyze the games
uv run gamehub test ../games                     # their tests and invariants
uv run gamehub play ../games/nim --seats human,random
uv run gamehub new my-game --template tablero    # a new game from a template (board)
uv run gamehub perft ../games/chess --depth 4    # count legal move sequences
uv run gamehub fuzz ../games/chess --games 1000 --jobs 6   # random matches in parallel
uv run gamehub analyze ../games/kuhn-poker        # game theory: feasibility, equilibria, CFR…

# The C++ core (gamehub-core, built by `uv sync`; pip install 'gamehub[core]')
uv run gamehub bench ../games/tictactoe           # matches/s: reference engine vs C++ (×57)
uv run gamehub fuzz ../games/chess --games 100000 --engine cpp --jobs 8
uv run gamehub differential ../games/dudo --games 100000 --jobs 6   # C++ vs reference, step by step
uv run gamehub perft ../games/chess --depth 5 --engine cpp          # 4,865,609 in 18 s
uv run gamehub analyze ../games/nim --retrograde  # exact analyses in C++ (--engine auto|cpp|python)
uv run gamehub wasm --check                       # the core for the browser is up to date (--write: Emscripten)
uv run gamehub web export ../site                 # static site: the play app + the games, no server
uv run gamehub export ../games/kuhn-poker --to gambit-efg   # to Gambit (.efg / .nfg)

uv run gamehub studio ../games --open            # the Studio: diagram + text + simulator
uv run gamehub lsp                               # language server (for your editor)

uv run gamehub serve ../games --open             # match server + web app in the browser
uv run gamehub host ../games/dudo --players 4    # open a room on the LAN and play
uv run gamehub join K7F-Q2P                      # join from another computer (or open the link)
uv run gamehub bot run random --room K7F-Q2P     # a bot in the room

uv run gamehub ui new ../games/nim               # a custom React UI (games/nim/ui)
uv run gamehub sdk ts ../games/nim -o types.ts   # a game's TypeScript types
uv run gamehub natives check                     # native plugins = their Nomos reference
```

Native plugins need `wasmtime` (`pip install gamehub[wasm]`; it is in the development group);
without it, the Nomos reference implementation is used.
Game theory works without extras; `pip install gamehub[analysis]` adds HiGHS for large linear
programs and `gamehub[openspiel]` the OpenSpiel wrapper (both in the development group).

The web apps are built with `pnpm install && pnpm build` at the repository root; `gamehub serve`,
`gamehub host` and `gamehub studio` find them by themselves (and the wheel ships them if they were
built when it was made). `gamehub studio` prints a link with a token: without it, the Studio does
not let you in.

Project documentation: [`docs/wiki`](../docs/wiki/README.md) (language, engine, protocol, web
client, Studio).
