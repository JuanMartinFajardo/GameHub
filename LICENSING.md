# GameHub licensing

| Part of the repository | License | File |
|---|---|---|
| Everything, except what is listed below (engine, the Nomos language, specifications, SDKs, tools, documentation) | Apache-2.0 | [`LICENSE`](LICENSE) |
| The hub server (`hub/`, once it exists) | AGPL-3.0-or-later | `hub/LICENSE` (to be added in Phase 10) |
| Content of the official games in `games/` (rules, texts, art) | CC-BY-4.0 | [`games/LICENSE.md`](games/LICENSE.md) |
| Code of the games' interfaces in `games/*/ui/` | Apache-2.0 | [`LICENSE`](LICENSE) |

- Every source file carries its SPDX identifier in the header
  (`SPDX-License-Identifier: Apache-2.0`).
- Games published on the hub by third parties carry the license their author chooses
  (recommended: CC-BY-4.0).
- Decision recorded in [ADR-016](docs/wiki/decisions.md).

## Third-party dependencies in the web apps

The built apps (`web/apps/*/dist`, which also travel in the Python wheel) include dependencies
with their own licenses, unmodified: React, React Flow (`@xyflow/react`), CodeMirror and `marked`
(MIT), and **elkjs (EPL-2.0)**, the Studio's automatic layout, whose source code is at
<https://github.com/kieler/elkjs>. The exact versions are in `pnpm-lock.yaml`.

The optional `wasmtime` dependency (native plugins, the `gamehub[wasm]` extra) is Apache-2.0
with the LLVM exception.

Copyright 2026 Juan Martin Fajardo and GameHub contributors.
