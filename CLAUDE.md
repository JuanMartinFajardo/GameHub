# GameHub — instructions for Claude

## Language
- Talk to the user in **Spanish**.
- Documentation (wiki, READMEs, `log.md`, this file), code, identifiers and the keywords of the
  `.game` language are in **English** (ADR-067). Games may ship Spanish as an optional translation
  of their texts (`{ en: …, es: … }`); UIs keep their es/en catalogs.
- Until [question 24](docs/wiki/open-questions.md) is answered, code comments, CLI messages and
  commit messages keep their current language (Spanish); do not translate them piecemeal.

## Mandatory maintenance (the user's explicit request)
- At the end of every block of work:
  1. Add an entry **at the top** of `log.md` (date, what was done, decisions, next steps,
     progress %).
  2. Update the wiki in `docs/wiki/`: the "Project status" in `docs/wiki/README.md`, the
     checkboxes in `docs/wiki/roadmap.md` and the affected pages.
  3. Record architecture decisions in `docs/wiki/decisions.md` (ADR format) and move answered
     questions in `docs/wiki/open-questions.md` to "Answered".

## Project priorities
1. Designing games: the `.game` language + the visual editor (Studio), everything very modular.
2. Playing: server/protocol + UIs that connect to the endpoints (local, LAN, online).
3. Then: catalog, game theory, C++ core, heuristics, web hub.
4. Last: AI (RL, Deep RL, LLM).

## Commands (from `python/`)
- `uv run pytest` · `uv run ruff check .` · `uv run ruff format .` · `uv run pyright`
- `uv run gamehub ir check ../spec/ir/examples/*.ir.json` (validate the IR)
- `uv run gamehub ir schemas --write` after touching `spec/ir/v0/ops.json` (the expr/stmt schemas
  are generated)
- `uv run gamehub conformance --write` after changing the engine's semantics or an example (and
  explain why in the commit: the traces are the contract with other engines)
- `uv run gamehub play|fuzz|replay|perft …` (see `docs/wiki/engine.md`; `fuzz --jobs N` in
  parallel)
- `uv run gamehub analyze|export …`: game theory (see `docs/wiki/game-theory.md`); the
  `gamehub[analysis]` (HiGHS) and `gamehub[openspiel]` extras are in the dev group
- `uv run pytest -m slow`: the long tests (deep chess perft), outside the normal suite
- `uv run gamehub natives build --check` (the `.wasm` files in `stdlib/std/native` are their
  compiled `.wat`; `--write` after touching a `.wat`) · `uv run gamehub natives check`
  (plugin = reference)
- After changing the rules of a game with a custom UI: `pnpm types` in `games/<game>/ui`
- Comment separators `# --- Title ---…` of at most 100 columns (ruff E501).

## Git (policy agreed on 2026-10-09)
- **One commit per finished task**, with a message in Spanish and the co-authorship trailer.
- `main` holds what has been approved. Each phase is worked on in its own branch
  (`f1/motor-referencia`, …) and merged into `main` only with the user's approval. Never push
  unless asked.
- Before each commit: tests, `ruff`, `pyright` and `gamehub ir check` green.

## References
- Semantics: `docs/wiki/formal-model.md` · Syntax: `docs/wiki/language.md` · IR:
  `docs/wiki/ir.md` · Architecture: `docs/wiki/architecture.md` · Roadmap: `docs/wiki/roadmap.md`.
- `structure.py` is the user's original prototype: do not modify it (analysis in
  `docs/wiki/structure-py-analysis.md`).
