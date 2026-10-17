# gamehub-core

GameHub's C++ core (Phase 8): a bytecode VM for the GameIR with the same semantics as the Python
reference engine, compact states with automatic Zobrist hashing, and search algorithms. It is
used from Python through `gamehub.engine.core` (`pip install 'gamehub[core]'`) and in the browser
as WebAssembly.

```bash
cd ../python
uv sync                       # builds and installs gamehub-core (editable: rebuilt on import)
uv run pytest tests/test_core*.py
```

See `docs/wiki/engine.md` (C++ core) and ADR-075 onwards in `docs/wiki/decisions.md`.
