# GameHub specifications

Formal contracts that every component (Python, C++, web) must meet.

| Path | Contents |
|---|---|
| `ir/v0/ops.json` | The GameIR **operator catalog** (expressions, statements, selectors): the single source of truth |
| `ir/v0/ir.schema.json` | Schema of the whole document (game, state, functions, flow, nodes, actions) |
| `ir/v0/common.schema.json`, `type.schema.json` | Identifiers, texts, visibility, blocks and types |
| `ir/v0/expr.schema.json`, `stmt.schema.json` | **Generated** from `ops.json` (`gamehub ir schemas --write`); do not edit by hand |
| `ir/examples/*.ir.json` | Hand-written validation games: tic-tac-toe, prisoner's dilemma, rock-paper-scissors, Nim, Kuhn poker, Bullshit (`mentiroso`) |
| `protocol/v1/protocol.schema.json` | **Match protocol v1**: envelopes and data of each WebSocket message (client → server and server → client) and REST API bodies. The Python and TypeScript types are generated (`gamehub protocol types --write`); semantics in [`protocol.md`](../docs/wiki/protocol.md) |
| `conformance/<game>/seed-<n>.ghr.json` | **Golden traces**: matches with a fixed seed and the state digest at each step; every engine must reproduce them (`gamehub conformance --check`) |

Validate: `cd python && uv run gamehub ir check ../spec/ir/examples/*.ir.json`

The JSON Schema checks the **shape**; `gamehub ir check` adds **well-formedness** checks
(references, contexts, chance only in `chance` nodes, no recursion, node exits). The semantics is
in [`docs/wiki/formal-model.md`](../docs/wiki/formal-model.md) and the IR in
[`docs/wiki/ir.md`](../docs/wiki/ir.md).

The `$id`s use the reserved domain `gamehub.invalid` (RFC 2606): they are identifiers, not URLs.
