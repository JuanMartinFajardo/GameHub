# Decision record (ADR)

> Every architecture decision is recorded here with its context. Statuses: **Accepted** (firm),
> **Proposed** (a recommendation, waiting for your approval), **Pending** (information missing).
> Those accepted "without objections" were proposed and the user asked to go ahead on top of them.

| ADR | Decision | Status |
|---|---|---|
| 001 | The GameIR is the single source of truth; text and diagram are views | Accepted (2026-10-09, no objections) |
| 002 | A pure, typed and total expression language (no Python lambdas) | Accepted (2026-10-09, no objections) |
| 003 | Chance only in `chance` nodes; seeded RNG; total determinism | Accepted (2026-10-09, no objections) |
| 004 | Immutable states, no singletons; the match loop outside the engine | Accepted (2026-10-09, no objections) |
| 005 | Declarative visibility per location; derived views; authoritative server | Accepted (2026-10-09, no objections) |
| 006 | The flow is a hierarchical statechart with a closed set of node kinds | Accepted (2026-10-09, no objections) |
| 007 | Reference engine in Python first; C++ later, with differential conformance | Accepted (2026-10-09, no objections) |
| 008 | Git as the versioning backend; GameHub adds the semantic layer | Accepted (2026-10-09, no objections) |
| 009 | WebSocket + JSON protocol, contracts in JSON Schema | Accepted (2026-10-09, no objections) |
| 010 | Interoperate with OpenSpiel / Gambit / PettingZoo before reimplementing | Accepted (2026-10-09, no objections) |
| 011 | Monorepo (spec, python, core, web, stdlib, games, docs) | Accepted (2026-10-09, no objections) |
| 012 | Web in TypeScript + React (+ React Flow, Monaco; Monaco → CodeMirror in ADR-054) | Accepted (2026-10-09, no objections) |
| 013 | Software in Python 3 and C++ (C++ for heavy computation) | **Accepted** (user's decision) |
| 014 | `.game` file extension | **Accepted** (user's decision) |
| 015 | Documentation in Spanish; code and identifiers in English (superseded by ADR-067) | Superseded (2026-10-16) |
| 016 | Licenses: Apache-2.0 / AGPL-3.0 (hub) / CC-BY-4.0 (games) | **Accepted** (2026-10-09) |
| 017 | The language is called **Nomos** (`.game` files) | **Accepted** (2026-10-09) |
| 018 | Syntax with braces and English keywords | **Accepted** (2026-10-09) |
| 019 | IR v0.1: visibility by predicates; ordered zones vs. bags; no hidden identities | Accepted (2026-10-09, no objections) |
| 020 | The operator catalog (`ops.json`) as the single source; generated schemas | Accepted (2026-10-09, no objections) |
| 021 | Phase 0 specifies only the core (resolved) IR; the authoring IR comes with the compiler (F2) | Accepted (2026-10-09, no objections) |
| 022 | PCG32 (the reference C implementation) is the normative RNG of every engine | Accepted (2026-10-09, F1) |
| 023 | Validation with JSON Schema + our own checker (no pydantic); the engine compiles the IR into functions | Accepted (2026-10-09, F1) |
| 024 | `$exit`: first the phase's `on_exit` and then its transitions | Accepted (2026-10-09, F1) |
| 025 | The rules hash ignores explicit default values (empty lists, `all` visibility) | Accepted (2026-10-09, F1) |
| 026 | Each phase in its branch (`fN/…`); one commit per task; merge into `main` with approval | Accepted (2026-10-09, user) |
| 027 | A hand-written (recursive descent) Nomos parser, not Lark | Accepted (2026-10-10, user) |
| 028 | No local name shadows a global of the game, except in module functions | Accepted (2026-10-10, user) |
| 029 | Type-directed sugar; checking and translation to the IR in a single pass | Accepted (2026-10-10, user) |
| 030 | Tests and invariants outside the IR, with their own execution semantics | Accepted (2026-10-10, user) |
| 031 | Modules: external declarations with pruning; resolution std → dependencies → relative | Accepted (2026-10-10, user) |
| 032 | Mods on the model (AST) and combinators as IR transformations | Accepted (2026-10-10, user) |
| 033 | Packages with `game.toml` and `game.lock` (git commits), without a central registry | Accepted (2026-10-10, user) |
| 034 | Static analyses on the IR, located in the text through a source map | Accepted (2026-10-10, user) |
| 035 | Prettier-style canonical formatting; the parser allows continuing after `=`, `requires`, `when` | Accepted (2026-10-10, user) |
| 036 | Match server on Starlette + uvicorn (no FastAPI or pydantic); contracts in JSON Schema | Accepted (2026-10-10, user) |
| 037 | A pure room core (no I/O or clock of its own) and a thin transport | Accepted (2026-10-10, user) |
| 038 | One update per input, `seq` without gaps and rejection by current turn | Accepted (2026-10-10, user) |
| 039 | A public observer in the engine: spectators hold no seat | Accepted (2026-10-10, user) |
| 040 | Provably fair chance `gamehub-fair/1`: commitment, players' seeds and a 53-bit seed | Accepted (2026-10-10, user) |
| 041 | Forfeiting = last place and a bot plays for the seat; the match ends when one is left | Accepted (2026-10-10, user) |
| 042 | LAN: port 7420, `/r/CODE` link with a QR code, mDNS announcement `_gamehub._tcp` and stored sessions | Accepted (2026-10-10, user) |
| 043 | Network bots with the same `Agent` interface as in process | Accepted (2026-10-10, user) |
| 044 | Web client: pnpm workspace at the root (web/ and games/*/ui), TypeScript 7, React 19, Vite 8, Biome, Vitest | Accepted (2026-10-11, user) |
| 045 | Protocol TS types with the same generator as the Python ones | Accepted (2026-10-11, user) |
| 046 | The match server serves the web app (same origin; the link and the QR code open the app) | Accepted (2026-10-11, user) |
| 047 | `ui { … }` presentation hints: a closed catalog, checked and outside the rules hash | Accepted (2026-10-11, user) |
| 048 | A generic UI driven by the types and the action domains; action builder | Accepted (2026-10-11, user) |
| 049 | Matches on a single device with one connection per seat against the server | Accepted (2026-10-11, user) |
| 050 | Custom UIs as packages in games/<game>/ui, registered automatically; template and per-game types | Accepted (2026-10-11, user) |
| 051 | No state or i18n dependencies: pure reducer + useSyncExternalStore, our own catalogs | Accepted (2026-10-11, user) |
| 052 | Studio: the `.game` is the only thing saved; the diagram and forms edit the tree with operations and a checked minimal rewrite | Accepted (2026-10-16, user) |
| 053 | Language server with pygls: `gamehub lsp` over stdio and the same server, with `gamehub/…` methods, over the Studio's WebSocket | Accepted (2026-10-16, user) |
| 054 | Text editor and fields with CodeMirror 6 and its LSP client, not Monaco | Accepted (2026-10-16, user) |
| 055 | Diagram with React Flow + ELK (layered, cycles by text order); layout in `<game>.layout.json` | Accepted (2026-10-16, user) |
| 056 | The checker's symbol index (name positions, resolved uses, types) for the LSP and for renaming | Accepted (2026-10-16, user) |
| 057 | Studio security: local only, token, Host and Origin checked, `.game` files from the working directory | Accepted (2026-10-16, user) |
| 058 | A server-side simulator on the reference engine: immutable history, transition trace and Knuth's estimator | Accepted (2026-10-16, user) |
| 059 | Tests and invariants editable and runnable from the Studio; templates shared with `gamehub new --template` | Accepted (2026-10-16, user) |
| 060 | Memoization of IR functions: forever for those that only depend on their arguments, while the state does not change for those that read it | Accepted (2026-10-16, user) |
| 061 | `gamehub perft` and `gamehub fuzz --jobs` (several processes, the same report); long tests marked `slow` | Accepted (2026-10-16, user) |
| 062 | Native plugins: `@native("m.f")` with the body as the mandatory reference; WebAssembly without imports (ABI `gamehub-native/1`) and optional `wasmtime` | Accepted (2026-10-16, user) |
| 063 | IR expressions are compiled to Python code (`codegen`); the closures remain the reference | Accepted (2026-10-16, user) |
| 064 | Card-game libraries without generics: suits and strengths as integers in `std.tricktaking`; decks in `std.cards` | Accepted (2026-10-16, user) |
| 065 | Wave-2 rules: FIDE, ISkO without Kontra or Ramsch, Spanish Parchís, Amigo's Wizard, no-limit Hold'em and Klondike with a move cap | Accepted (2026-10-16, user) |
| 066 | F6 language adjustments: modules do not see the game's names, a grid is assigned with its rows, lists of zones are redacted zone by zone | Accepted (2026-10-16, user) |
| 067 | Documentation in English; Spanish only as an optional translation shipped by each game | Accepted (2026-10-16, user) |
| 068 | Game theory on the reference engine, in exact arithmetic, over explicit representations: the extensive form (with the engine's information sets) and the state graph | Accepted (2026-10-17, user) |
| 069 | Linear programming: an exact rational simplex by default; HiGHS (optional `gamehub[analysis]` extra) for large programs, in floating point | Accepted (2026-10-17, user) |
| 070 | Solution concepts per class: reduced normal form, support enumeration + Lemke–Howson, sequence form (exact), CFR/CFR+ (floating point), exploitability as OpenSpiel defines it | Accepted (2026-10-17, user) |
| 071 | Feasibility advisor: classification + Knuth's estimator (importance sampling at chance, merged outcomes) + bounded exact probes + recommendation codes; the Studio's estimator uses it | Accepted (2026-10-17, user) |
| 072 | Interoperability: Gambit `.efg`/`.nfg` (ASCII labels, rationals) and an OpenSpiel wrapper with global action ids found by exploring the game | Accepted (2026-10-17, user) |
| 073 | `gamehub analyze`: one JSON report for the CLI and the Studio's "Analysis" tab, with per-analysis errors and size guards | Accepted (2026-10-17, user) |
| 074 | Connect Four 7×6 is solved in F8 (C++); in F7 it is verified on small boards against an independent solver | Accepted (2026-10-17, user) |

---

### ADR-001 — Canonical IR as the source of truth
- **Context:** we want to design with text *and* diagrams, run in Python, C++ and the browser, and
  analyze. With several "sources" there would be divergences.
- **Decision:** everything produces or consumes the GameIR (canonical, versioned JSON with a hash).
- **Alternatives:** the text as the source (the diagram would be read-only); Python code as the
  source (not portable).
- **Consequences:** a stable schema and migrations have to be maintained; in exchange, any new tool
  only needs to read the IR.

### ADR-002 — Pure, typed and total expressions
- **Context:** `structure.py` used arbitrary Python functions.
- **Decision:** our own language without effects in expressions, without general recursion, with
  loops only over finite collections. Escape hatch: pure native plugins with a declared signature.
- **Consequences:** portability, security, static analysis (types, leaks, termination) and
  compilation to C++. Some exotic games will need plugins.

### ADR-003 — Explicit chance and determinism
- **Decision:** only `chance` nodes (and the initial setup) introduce randomness, with explicit
  distributions; execution uses a seeded RNG.
- **Consequences:** exact replays, reproducible tests, provably fair chance online and algorithms
  that distinguish enumerable chance nodes from sampleable ones.

### ADR-004 — Immutable states
- **Decision:** `apply(s, a)` returns a new state (with structural sharing). No singletons. The
  engine does no I/O.
- **Consequences:** tree search, parallel simulation, time travel and a multi-room server without
  tricks. The C++ engine may use incremental *undo* internally.

### ADR-005 — Declarative visibility
- **Decision:** who sees each location of the state (and each action parameter and event) is
  declared; views are derived; the server only sends redacted views; hidden components do not
  expose an identity (details in ADR-019).
- **Consequences:** it is impossible to "forget" to hide something in the UI; leak analysis
  becomes possible.

### ADR-006 — Hierarchical statechart
- **Decision:** a closed set of node kinds: `decision`, `simultaneous`, `window`, `chance`,
  `auto`, `phase`, `call`, `terminal`.
- **Alternatives:** a flat diagram (does not scale to rounds/tricks); BGA/boardgame.io state
  machines (not very formal).
- **Consequences:** readable, collapsible diagrams; a direct correspondence with the extensive
  form.

### ADR-007 — Python first, C++ later
- **Context:** the priority is to design and play as soon as possible; performance matters for
  analysis and AI.
- **Decision:** a reference engine in Python (clarity, development speed); a C++ core in Phase 8,
  verified against the reference with golden traces.
- **Consequences:** the MVP arrives sooner; the IR must avoid any "Python-only" semantics.

### ADR-008 — Git as the backend
- **Decision:** each game is a git repository; the hub uses git (Forgejo or similar) and adds
  semantic diffs, matches, analyses and the arena.
- **Consequences:** branches/forks/merges without reinventing anything; integration with
  GitHub/GitLab for free.

### ADR-009 — WebSocket + JSON + JSON Schema
- **Decision:** WebSocket transport with JSON in v1; contracts in JSON Schema with generated
  types.
- **Consequences:** any technology can be a client; MessagePack/WebRTC remain as improvements.

### ADR-010 — Interoperability first
- **Decision:** export to OpenSpiel and Gambit from Phase 7 to get their algorithms; implement in
  our own C++ whatever is used the most.

### ADR-011 / 012 / 015 — Organization
- Monorepo; web in TypeScript + React; documentation in Spanish and identifiers in English.
  ADR-015 was superseded on 2026-10-16 by ADR-067 (documentation in English).

### ADR-016 — Licenses (accepted, 2026-10-09)
- **Decision:** Apache-2.0 for everything by default (engine, Nomos, specifications, SDKs, tools,
  documentation); AGPL-3.0-or-later for the hub server (it prevents someone from running a closed
  hub with this code); CC-BY-4.0 for the content of the official games. Third-party games carry
  the license their author chooses.
- **Consequences:** `LICENSE` (the canonical Apache-2.0 text), `LICENSING.md` with the split by
  directory, and SPDX headers in the code.

### ADR-017 — Nomos (accepted, 2026-10-09)
- The game description language is called **Nomos** (νόμος, "law, rule"; a nod to the game
  *Nomic*). The file extension remains `.game` (ADR-014).

### ADR-018 — Syntax (accepted, 2026-10-09)
- Blocks with braces and English keywords; texts visible to players are translatable. By default
  (absent objections): a Python-style conditional `x if c else y` and exact (rational) payoffs in
  the IR.

### ADR-019 — IR v0.1 visibility model
- **Context:** the draft proposed *opaque handles* re-anonymized on shuffling. On analysis, a
  stable handle leaks information: if I pass a Q♠ to an opponent and later they play a card face
  down from their hand, the handle would tell me whether it is "my" Q♠ (at a real table I would
  not know).
- **Decision:**
  1. Visibility is a **predicate** with `viewer`, `owner` and `item_face_up` bound (with the
     shortcuts `all`, `none`, `owner`); it is evaluated on the current state.
  2. Two kinds of zone: **`zone`** (ordered: decks, piles, Memory rows; positions are public) and
     **`bag`** (a multiset: hands; order is not part of the state).
  3. Whoever cannot see a zone's contents only sees its **size** (if `size_visibility` allows it)
     and, in ordered zones, **a gap per position**. In hidden bags, only the size. Hidden
     components have **no visible identity**.
  4. `reveal` is an **event** (it shows values to certain seats) and does not change the persistent
     visibility; cards that stay face up use `flip` + `item_face_up`.
  5. The visibility of an action parameter applies to the **other** seats: the actor always sees
     their own action.
- **Consequences:** no leaks through identifiers or order; legitimate tracking (by public position
  or by memory of what was revealed) remains possible.

### ADR-020 — The operator catalog as the single source
- **Decision:** `spec/ir/v0/ops.json` defines each expression, statement and selector (arity,
  argument types, whether it is random, documentation). `expr.schema.json` and `stmt.schema.json`
  are generated (`gamehub ir schemas --write`) and a test/CI checks that they are up to date.
- **Consequences:** every future engine (Python, C++, WASM) can verify automatically that it
  implements the whole catalog; the operator documentation can be generated from the same file.

### ADR-021 — Core IR first
- **Decision:** Phase 0 fixes the **resolved IR** (the one engines run). The authoring IR (with
  sugar: loops in phases, `deal`, payoff tables, sub-flow `call`s) depends on the concrete syntax
  and will be specified together with the compiler in Phase 2.
- **Consequences:** the reference engine (F1) can start right away against a stable contract.

### ADR-022 — PCG32 as the normative RNG
- **Context:** "same seed ⇒ same match" must hold across engines (Python, C++, WASM). Python's
  `random` (Mersenne Twister with its own seeding) is not reproducible outside Python.
- **Decision:** PCG32 (XSH-RR 64/32) exactly like `pcg32_srandom_r`, `pcg32_random_r` and
  `pcg32_boundedrand_r` from the reference C implementation; streams per purpose; Fisher–Yates from
  the end; exact weighted sampling with a common denominator. See [engine §4](engine.md).
- **Consequences:** conformance traces comparable bit for bit; replays also store the draws, so
  they do not depend on the RNG.

### ADR-023 — No pydantic model layer
- **Decision:** the IR is validated with the JSON Schema and the well-formedness checker; the
  engine compiles it directly into Python functions (closures).
- **Alternatives:** pydantic models (they would duplicate the schema and add a dependency).
- **Consequences:** a single definition of the format (the schema); Python's static types are used
  where they help (the engine), not in the format.

### ADR-024 — Order of `$exit`
- **Decision:** when leaving a phase with `$exit`, its `on_exit` runs first and then its
  transitions are evaluated.
- **Reason:** it allows "at the end of the round, score; if someone reaches 500, end; otherwise,
  another round" without duplicating computations in the guards.

### ADR-025 — A hash insensitive to default values
- **Decision:** before computing the rules hash, empty lists and explicit `all` visibilities are
  removed (as well as `meta`, `doc` and constraint messages).
- **Consequences:** two IRs with the same semantics written differently (by hand, with the
  builder, from Nomos or from the Studio) have the same hash.

### ADR-027 — A hand-written parser
- **Context:** the roadmap planned Lark. The language needs clear error messages with
  suggestions, recovery to report every error in a file, and preserving comments for the
  formatter.
- **Decision:** our own lexer and parser (recursive descent with precedences); comments are
  *trivia* attached to the tokens; each token knows its bracket depth and recovery skips to the
  next element of its own block.
- **Alternatives:** Lark (a declarative grammar, but generic errors and poor recovery).
- **Consequences:** ~1,500 lines without dependencies; quality errors (rustc style); the grammar
  lives in the code and in the [reference](language.md), not in a separate file.

### ADR-028 — No shadowing of global names
- **Decision:** a parameter, a `let` or a comprehension variable cannot be named like a state
  variable, an option, a function, a type, an enum value or a context name (`seats`, `actor`…) of
  the game (E204). Exception: inside a module function, the game's state and options do not exist,
  so their names are free.
- **Reason:** in game rules, mistaking `turn` (state) for a local `turn` is a hard-to-spot bug;
  modules, on the other hand, are written without knowing the games that will use them.

### ADR-029 — Type-directed sugar
- **Decision:** the checker elaborates and translates each expression in a single pass (it returns
  IR and a type). The convenient forms are translated according to the type: `+`/`-`/`in` on lists
  (`concat`, `difference`, `contains`), `+=`, the `move` selector (`value` or `values`), `deal`,
  `match` to `case`, default initial values. `a + b + c` chains are flattened.
- **Consequences:** the IR only has catalog operators and the decompiler can go back to the text
  exactly (tested on every game).

### ADR-030 — Tests and invariants outside the IR
- **Decision:** `test` and `invariant` are compiled separately (they do not change the rules hash)
  and `gamehub test` runs them: pending chance is resolved with a seed before each step;
  `chance where c` picks with the conditional probability; after a `set`, invariants are no longer
  checked; invariants are also checked on random matches.
- **Consequences:** games bring their own tests without cluttering the rules; each failure is
  explained with the values involved.

### ADR-031 — Modules
- **Decision:** top-level declarations (local or imported) are external: they only reach the IR
  if the game uses them. `import` looks in the standard library, then in the package's
  dependencies and then next to the file; importing a name brings what it needs. The IR does not
  keep modules: it stays self-contained.
- **Consequences:** variants and libraries do not bloat the IR; an engine does not need to know
  anything about modules.

### ADR-032 — Mods and combinators
- **Decision:** `extends` merges models (AST) before checking: the variant is compiled as a
  complete game and the base does not change. `repeat` and `best_of` transform the base's IR (a
  phase per round, terminals that record the result). To extend a combinator, its IR is
  decompiled.
- **Consequences:** variants have errors located in their own text; combinators work for any
  game, including one written in IR.

### ADR-033 — Packages
- **Decision:** each game is a directory with `game.toml` (name, version, main file, dependencies
  by `path` or `git` + `rev`) and `game.lock` (the exact commit of each git dependency), with a
  local cache. `gamehub new`, `fetch`, `clone` and `fork` (which records `forked_from`).
- **Alternatives:** a central registry (it comes with the hub, F10); resolved semantic versions
  (for now, git revisions).
- **Consequences:** consistent with git as the backend (ADR-008); reproducible builds.

### ADR-034 — Static analyses on the IR
- **Decision:** `gamehub check`'s warnings (reachability, exhaustiveness, termination, loops
  without progress, information leaks, unused declarations) and the classification are computed
  on the IR, walked generically with the operator catalog; the compiler places them in the text
  with a source map.
- **Consequences:** they work the same for Nomos, hand-written IR or the future visual editor. The
  v1 leak analysis is conservative (it may warn too much); it understands visible sizes, one's own
  part of an `@visible(owner)` variable and `reveal … to all`.

### ADR-035 — Canonical formatting
- **Decision:** `gamehub fmt` uses a Wadler/Prettier-style document algebra (100 columns, 2-space
  indentation): arithmetic chains fill lines, `and`/`or` chains go one per line, a value that
  starts with a bracket opens next to the `=` if it does not fit on the next line. The parser
  allows a value to start on the next line after `=`, `requires`, `when` and `key:`, so that
  everything the formatter writes is read back the same (tested by formatting every game at widths
  from 24 to 100 columns).

### ADR-036 — Server on Starlette + uvicorn
- **Context:** the roadmap and the architecture proposed FastAPI. Its added value is validating
  with pydantic and documenting with OpenAPI, but the project's contracts are already JSON Schema
  (ADR-009, ADR-023) and almost the whole protocol goes over WebSocket, which OpenAPI does not
  describe.
- **Decision:** Starlette (FastAPI's foundation) on uvicorn, with `websockets` as the
  implementation and as the client. Messages are validated with the `spec/protocol/v1` schema and
  the Python types (`TypedDict`) are generated from it.
- **Alternatives:** FastAPI (it would duplicate the contracts in pydantic models), aiohttp
  (server and client in one, less widespread).
- **Consequences:** three lightweight dependencies; a single definition of each message for
  Python, TypeScript (F4) and the documentation. The hub (F10) can use FastAPI if it needs it.

### ADR-037 — A pure room core
- **Decision:** `Room`/`Match` open no connections and do not read the time: each operation
  receives `now`, leaves the messages in an outbox (with their delivery time, for the spectators'
  delay) and says when it has to be called again (`next_wakeup`: bots, deadlines). The transport
  layer only validates, delivers and schedules timers; everything runs on the event loop, without
  locks.
- **Consequences:** the whole semantics (turns, clocks, bots, spectators, forfeits, reconnection)
  is tested without a network and with a simulated clock; the same core will serve the Studio's
  simulator and tournaments.

### ADR-038 — Updates and turns
- **Decision:** each input (an action, a bot or an expired deadline) produces **one** update with
  the action and the chance that follows it; `seq` numbers updates without gaps. An `act` is
  rejected with `stale_seq` only if its `seq` is older than the start of the seat's **current
  turn**: the turn lasts while the seat can act, has not acted and no node is reached.
- **Alternatives:** rejecting any `act` whose `seq` is not the latest (spurious rejections in
  simultaneous nodes and windows, where other seats' submissions do not change your decision).
- **Consequences:** the protection against moves decided on an old state does not get in the way
  in simultaneous nodes; gaps in `seq` reveal lost messages.

### ADR-039 — Public observer
- **Decision:** the engine offers the view and events of a spectator (`PUBLIC`), who holds no
  seat: policies are evaluated with a `viewer` that matches no `owner`, and a predicate that cannot
  be evaluated without a seat counts as false. Of the events, it sees the public ones and whatever
  is revealed to all seats.
- **Alternatives:** the intersection of what all seats see (not the same thing: what each one sees
  separately is not public).
- **Consequences:** spectators without cheating; `@visible(viewer != owner)` (Hanabi) is visible
  from outside, as at the table. It does not change the conformance traces.

### ADR-040 — Provably fair chance
- **Decision:** scheme `gamehub-fair/1`: a SHA-256 commitment to the server seed published in the
  lobby; optional players' seeds when they declare themselves ready; match seed = SHA-256 of the
  canonical JSON of everything, truncated to 53 bits (exact in JSON and JavaScript); revealed at
  the end; the replay carries everything needed to verify it. The server's chance that is not part
  of the rules (the move when a deadline expires, server bots) comes from other PCG32 streams of
  the same seed.
- **Consequences:** nobody (neither the server nor a player) can choose the chance outcomes;
  anyone can check a match with `gamehub replay`.

### ADR-041 — Forfeits
- **Decision:** whoever forfeits (resigning, leaving during a match or an expired deadline with
  `forfeit`) ends up last and a bot plays for their seat until the end; if only one seat is left
  without forfeiting, the match ends without payoffs (`reason: forfeit`).
- **Alternatives:** always ending the match (unfair to the others in games of 3 or more); pausing
  it (it blocks everyone).
- **Consequences:** multiplayer matches survive someone leaving; the final place reflects the
  forfeit.

### ADR-042 — Playing on the LAN
- **Decision:** `gamehub host` starts the server on port 7420 of every interface and shares the
  room in three ways: the code (6 characters), the link `http://IP:7420/r/CODE` (the room's page)
  and its QR code in the terminal; it also announces it over mDNS (`_gamehub._tcp`, with
  `zeroconf`) so that `gamehub join CODE` finds it without typing IPs. mDNS is optional: if the
  network does not allow it, the link is enough. The client stores each room's token to go back
  to it after closing the terminal.
- **Alternatives:** only IP and port (awkward); a central server (not needed at home).
- **Consequences:** two small dependencies (`zeroconf`, `segno` for the QR code). The mDNS tests
  depend on the network: they run with `GAMEHUB_LAN_TESTS=1`.

### ADR-043 — Network bots with the usual interface
- **Decision:** a remote bot implements the same `Agent` as in process (`act(observation,
  legal)`), with an observation with the same names (`seat`, `view`, `events`, plus `clock` and
  `game`) and the actions already decoded with the game's types (`Action`), lazily. The SDK takes
  care of the network: reconnection, progressive actions, `act` in a thread so as not to block.
- **Consequences:** the same agent plays in the arena, in `play_match` and against people over the
  network without changing a line; `gamehub bot run` loads a `.py` file with `make_agent`, an
  `Agent` class or an `act` function.

### ADR-044 — Web client: stack and workspace
- **Context:** Phase 4 creates the JavaScript side of the monorepo: web packages and custom UIs
  that live inside each game package (`games/<game>/ui`, as the [architecture](architecture.md)
  foresees).
- **Decision:** a **pnpm workspace at the repository root** with `web/packages/*`, `web/apps/*`
  and `games/*/ui`, Node 22, strict **TypeScript 7** (the native compiler), **React 19**,
  **Vite 8**, **Biome** for lint and formatting (ruff's equivalent) and **Vitest**. Exact versions
  in a `pnpm-workspace.yaml` catalog; internal packages export their TypeScript code, without a
  build step.
- **Alternatives:** the workspace inside `web/` (pnpm does not find it when working inside
  `games/<game>/ui`, which does not hang from `web/`); ESLint + Prettier (two tools and more
  configuration); TypeScript 6 (slower, same result).
- **Consequences:** `pnpm install`, `test`, `lint`, `typecheck` and `build` from the root;
  `pnpm dev` works inside each UI. The root gains `package.json`, `pnpm-workspace.yaml`,
  `pnpm-lock.yaml`, `biome.json` and `.nvmrc`.

### ADR-045 — Protocol types generated once
- **Decision:** `gamehub protocol types` generates from `spec/protocol/v1` both the Python
  `TypedDict`s and the TypeScript `interface`s (`@gamehub/protocol`), with each ecosystem's
  formatting; `--check` checks both in CI. To avoid clashing with JavaScript globals, `Number`,
  `Event` and `Error` are renamed `ExactNumber`, `GameEvent` and `ErrorInfo` in the schema (the
  messages on the wire do not change).
- **Alternatives:** `json-schema-to-typescript` (another tool, another output style).
- **Consequences:** a single source of truth for the messages in every client.

### ADR-046 — The server serves the web app
- **Decision:** `gamehub serve` and `gamehub host` serve the built app (the repository's, the one
  shipped in the wheel, or `GAMEHUB_WEB_DIR`); the app's routes return its `index.html` and
  `/r/CODE` still gives the room as JSON to whoever asks for it that way. New endpoints: the room's
  QR code as SVG and state-by-state replays (`/frames?seat=`).
- **Alternatives:** the app on another server (CORS, two addresses to remember).
- **Consequences:** same origin, no CORS; a room's link and QR code open the app, also on phones;
  nothing to install to play in the browser.

### ADR-047 — `ui { … }` presentation hints
- **Decision:** a Nomos section with `target: hint, hint…` entries (variables, options, types,
  actions and their parameters, nodes, seats) and a **closed catalog** of hints (how to draw,
  where, translated names, symbols, colors, cards, how to pick an argument, seat colors and names),
  checked by the compiler (E701–E704). They reach the IR in an optional `ui` key that **does not
  count for the rules hash**; in variants, each hint replaces the one in the same slot. Without
  changing `ir_version`, since it is optional.
- **Alternatives:** free-form hints in `meta` (unchecked: errors would only show on screen); a
  separate style sheet (another file to keep in sync with the rules).
- **Consequences:** changing the presentation changes neither the rules nor their replays;
  misspelled hints fail at compile time, with suggestions.

### ADR-048 — A generic UI driven by types and domains
- **Decision:** the look of each variable comes from its type and its hints, and how each argument
  is picked, from the shape of its **domain** in the IR (`cells(G)` → click squares;
  `subsets(items(Z), a, b)` → mark items of Z; `items(Z)` → pick one) or from a hint. An **action
  builder** picks the arguments in order with the values given by the legal actions (enumerated
  or with `query_actions`), computed once per update; to mark several items with progressive
  actions, it validates the size instead of asking for every subset. The web enumerates up to 500
  legal actions by default.
- **Consequences:** the 15 catalog games (22 packages since F6) are played without writing an
  interface (a test checks it by playing each one only with the UI); a new game is playable as
  soon as it compiles.

### ADR-049 — Matches on a single device
- **Decision:** local mode creates a room on the server that serves the app and opens one
  connection per human seat in the same tab; it shows the UI of whoever has the turn and, if the
  game hides information, covers the screen between turns.
- **Alternatives:** an engine in the browser (there is none until the WASM core, F8; Pyodide
  weighs tens of megabytes).
- **Consequences:** the same protocol and the same rules as over the network; without a server
  there is no local mode until F8.

### ADR-050 — Custom UIs
- **Decision:** a custom UI is a package in `games/<game>/ui` that exports `defineGameUi` (a
  component that receives the view, the typed legal actions and `act`); the app registers it by
  itself (`import.meta.glob`) and lets you switch to the generic one. `gamehub ui new` creates it
  from a template that already works (the game's types with `gamehub sdk ts`, a starting board, a
  test and a development server with the app only for that game).
- **Alternatives:** UIs inside `web/` (separated from the rules they belong to).
- **Consequences:** each game carries its rules and its interface together; if the rules change,
  TypeScript points at what needs to be touched (and a test does, if the types were not
  regenerated).

### ADR-051 — No state or i18n libraries
- **Decision:** the state of each connection is kept by the SDK with a pure, immutable reducer, and
  React reads it with `useSyncExternalStore`; texts, with our own es/en catalogs checked by
  TypeScript (the same keys in both languages).
- **Alternatives:** Redux or Zustand; i18next.
- **Consequences:** the SDK works the same outside React (bots in Node, other frameworks); fewer
  dependencies to maintain.

### ADR-052 — Studio: the text is what gets saved; the diagram edits the tree
- **Context:** the Studio edits the same game as a diagram, with forms and as text. The `.game`
  carries comments, formatting and order that matter to whoever writes it, and it is what gets
  versioned with git (ADR-008).
- **Decision:** the `.game` file is the only thing saved; the diagram and the forms are
  projections of its syntax tree (the authoring IR, ADR-001/021). Each gesture is a list of
  **operations** (`addNode`, `addTransition`, `updateAction`…) that the server applies to a copy
  of the tree; the text is rewritten **only where it changed** (what is unchanged keeps its text,
  with formatting and comments; what is new, with the formatter) and the result is checked by
  parsing it again (same tree and same comments); if the partial rewrite cannot cope, the whole
  file is formatted. The editor receives the minimal changes, which are undone like any edit.
- **Alternatives:** generating the whole text from the IR (it would lose comments and formatting);
  a separate diagram model synchronized with the text (two sources that diverge); editing the text
  directly from the browser with templates (fragile against any formatting).
- **Consequences:** the git diffs of a change made in the diagram are one or a few lines; property
  tests (random edits on every catalog game preserve comments and leave valid text) guard the
  guarantee; the operations live in Python (`gamehub.studio.edits`) and any client can use them.

### ADR-053 — A pygls language server, also for the Studio
- **Decision:** the Nomos language server is written with **pygls** on top of the reference
  compiler: diagnostics, completion (with the tokens up to the cursor, it works on half-written
  text), hover, definition, references, highlighting, rename, formatting, outline, folding,
  signature help and quick fixes. Two transports: standard input (`gamehub lsp`, for editors) and
  the Studio's WebSocket, where its own methods (`gamehub/edit`, `gamehub/analysis`,
  `gamehub/sim.*`, `gamehub/tests`…) are handled before pygls. Each document is analyzed in a
  thread 150 ms after the last change (immediately if the change comes from a Studio edit).
- **Alternatives:** a language server in TypeScript (it would duplicate the compiler); a separate
  protocol for the Studio (another client to maintain; LSP already handles document
  synchronization and versions).
- **Consequences:** a single compiler for everything; any editor with LSP works (`gamehub lsp`);
  the Studio speaks a single protocol over a single WebSocket.

### ADR-054 — CodeMirror 6 instead of Monaco
- **Context:** ADR-012 planned Monaco. The Studio needs a main editor and dozens of small editors
  in the forms (each condition, effect or type), with highlighting, completion and errors in place.
- **Decision:** **CodeMirror 6** with `@codemirror/lsp-client` (the official LSP client) for the
  editor and for the fields; Nomos as a CodeMirror language in `@gamehub/nomos`.
- **Alternatives:** Monaco (about 5 MB and web workers; designed for one editor per page, not for
  dozens of fields; the LSP bridge is third-party).
- **Consequences:** a lighter app (the Studio weighs ~1 MB without ELK); the fields and the editor
  share theme and language; versions live in the pnpm catalog, with a single copy of
  `@codemirror/state`, `@codemirror/view` and `@lezer/highlight` (with two, the editor breaks).

### ADR-055 — Diagram with React Flow + ELK; layout kept separately
- **Decision:** the canvas is **React Flow** (`@xyflow/react`): boxes per node kind, phases as
  collapsible containers, ordered arrows. The automatic layout is computed by **ELK** (`elkjs`,
  layered algorithm, cycles broken by text order so that the flow starts at the top), loaded
  separately the first time; whatever the user moves is stored in `<game>.layout.json` next to
  the game, with nodes by name.
- **Alternatives:** dagre (no subgraphs, worse with phases); positions inside the `.game` (it mixes
  presentation with rules and clutters diffs).
- **Consequences:** the `.game` and the rules hash do not change when boxes are moved; elkjs is
  **EPL-2.0** (it is distributed unmodified inside the built app; see `LICENSING.md`).

### ADR-056 — The checker's symbol index
- **Decision:** the tree stores the position of each name (`name_spans`) and the checker, when
  given an index, records each declaration, each resolved use (state, option, local, enum value,
  field, node, action and its parameters, also in `ui` and in tests) and the type of each
  expression. Hover, definition, references and **rename** come from there; renaming recompiles and
  is rejected if it clashes with another name or the game stops compiling. For the editor, the
  compiler skips the JSON Schema (`schema=False`), which was 90 % of the time.
- **Alternatives:** searching by text (it fails with locals, fields and names repeated in
  different scopes).
- **Consequences:** renaming every symbol of every catalog game there and back leaves the file
  unchanged (test); compiling a catalog game for the editor takes milliseconds.

### ADR-057 — Studio security
- **Decision:** `gamehub studio` listens only on 127.0.0.1 by default; it requires a random
  **token** (in the link; the app moves it into a cookie for this origin or into the
  `x-gamehub-token` header); it checks the **Host** header (against DNS rebinding) and the
  **Origin** of WebSockets; it only opens and saves `.game` files inside the working directory,
  with conflict detection on save. With `--host` reachable from outside the machine, it warns.
- **Alternatives:** no token locally (any page open in the browser could write files through
  localhost).
- **Consequences:** opening the Studio means opening the link it prints; `GAMEHUB_STUDIO_TOKEN`
  fixes it (for Vite's development server and the tests).

### ADR-058 — A server-side simulator
- **Decision:** the simulator uses the reference engine in the Studio's server. The whole history
  is kept (immutable states, ADR-004): time travel, branches that truncate the history, reloading
  the rules by replaying it. Each engine transition knows who it is (`TransitionDef.key`) and can
  be **traced** (`engine.state.TRACE`), which gives the arrows of the last step and the
  **coverage** of batch runs, without changing the semantics (the conformance traces do not
  change). The size of the tree is estimated with **Knuth's estimator** (random walks weighted by
  1/P); the exact count, with state and time limits.
- **Alternatives:** simulating in the browser (there is no engine until F8's WASM).
- **Consequences:** the rules being simulated are exactly the ones the server compiles; without a
  server, there is no simulator until F8.

### ADR-059 — Tests and invariants in the Studio; shared templates
- **Decision:** the game's tests and invariants are edited from the inspector (the `addTest`,
  `updateTest`, `deleteTest` operations and those for invariants) and run with `gamehub/tests`
  (tests plus invariants on random matches). The game templates (empty, race, board, cards, dice,
  2×2 matrix) live in the Python package and are used by `gamehub new --template` and the Studio;
  all of them compile without warnings and pass their tests.
- **Context:** without being able to touch the tests from the diagram, the empty template stopped
  compiling as soon as its action was changed (its test names it) and a game could not be designed
  only with the diagram.
- **Consequences:** tic-tac-toe is created from scratch only with the diagram and the forms, with
  its tests (acceptance test).

### ADR-060 — Memoization of IR functions
- **Context:** chess asks the same things a thousand times per position (where the king is,
  whether there is a check, which pieces are pinned, the squares of a ray) and each call
  recomputed everything: *perft(3)* took 52 s.
- **Decision:** the engine keeps the result of IR functions according to what they depend on
  (`game._memo_kinds`, a transitive static analysis):
  - **static**: only on their arguments (no state, options, seats or context). They are kept for
    every match of the game (chess's ray and jump tables, the value of a poker hand).
  - **state**: on the state and the options, but not on the current node (`at`) or the context
    seats. They are kept in the state (`State.memo`) and every write to the store in a transaction
    empties the memo, so there is no invalidation to forget.
  - None: those that depend on the context and those without loops or calls (storing them would
    cost more than computing them).
- **Alternatives:** letting the designer mark what to keep (human error, and it does not change
  the semantics: better automatic); keys with the whole state (each lookup would hash the state).
- **Consequences:** it is a cache: the conformance traces do not change. Together with the integer
  shortcuts, *perft(3)* goes down to 1.2 s and *perft(5)* (4,865,609) to 131 s with 6 processes. A
  game can be written "like in a real engine" (a move generator with pins and check lines) without
  worrying about how many times each function is called.

### ADR-061 — *Perft* and random matches in parallel
- **Decision:** `gamehub perft GAME --depth N` counts the sequences of legal moves (chance points
  add up all their outcomes; `--skip` leaves out actions such as claiming a draw; `--divide`
  splits by first move) and `gamehub fuzz --jobs N` spreads the matches over processes with the
  same report as with one (seeds `seed + i`). Both load the game in each process. Tests that take
  minutes are marked `slow` and only run with `pytest -m slow`.
- **Consequences:** the acceptance runs (10⁵ matches per game, *perft(5)*) take minutes or hours
  on a laptop, not days; *perft* works for any game (tic-tac-toe's is in the tests).

### ADR-062 — Native plugins in WebAssembly
- **Context:** the roadmap asked for an escape hatch for computations that are slow in Nomos (the
  poker hand evaluator), without losing portability: the same game has to work in the reference
  engine, in the browser and in the future C++ engine.
- **Decision:** a function is marked `@native("module.function")`; **its Nomos body is the
  reference implementation and it is mandatory**. An engine may replace it with a plugin that
  gives exactly the same result for any input. Plugins are **WebAssembly modules without
  imports** (ABI `gamehub-native/1`: arguments and result as i32 words in a buffer; `Bool`, `Int`,
  `Seat`, `Cell`, enums, structs, tuples, lists and options; E211 if the signature uses anything
  else), with a computation limit per call (`wasmtime` fuel). The `std.poker` one is hand-written
  in WAT (`stdlib/std/native/std.poker.wat`, with its compiled `.wasm` checked in CI). In Python,
  `wasmtime` is used if installed (the `gamehub[wasm]` extra); otherwise, or with
  `GAMEHUB_NATIVES=0`, the reference. `gamehub natives check` compares plugin and reference on
  random inputs.
- **Alternatives:** Python plugins (they do not work in the browser or in C++); native functions
  without a reference (a game would depend on a binary); generating the WASM from Nomos (that is
  what the F8 C++ engine will do).
- **Consequences:** 0 differences between the plugin and the reference on thousands of random card
  lists, also with repeated cards or fewer than five. In Python, a `wasmtime` call costs ~25 µs,
  so the gain is modest (×3); the value lies in having the interface and a binary that will work
  just the same in the browser (F8).

### ADR-063 — IR expressions are compiled to Python code
- **Context:** with memoization, the cost lay in the interpreter itself: each node of an
  expression was a closure call and each local, a new dictionary (about 3 µs per call to an IR
  function). 10⁵ chess or solitaire matches meant days of computation.
- **Decision:** `gamehub.engine.codegen` writes each IR expression and function as Python source
  code (one `def` per function, with locals and arguments as variables; `let` and comprehensions
  as lambdas) and compiles it with `exec`. It calls **the same per-operator functions** as the
  closures, so it gives the same results and the same errors. The closures remain the reference
  implementation: they are used if something cannot be generated, with `GAMEHUB_CODEGEN=0` or with
  `Game(ir, codegen=False)`.
- **Alternatives:** compiling to our own bytecode (that is the C++ core's job, F8); typing the
  expressions to generate specialized code (the IR has no per-expression types).
- **Consequences:** about twice as fast in every game; one test requires the generator to cover
  the whole operator catalog and another, that in every game random matches give the same digest
  at every step with both compilers.

### ADR-064 — Card-game libraries without generics
- **Context:** Nomos has no generics and each trick-taking game has its own deck and order (in
  Skat the jacks are trump; in Wizard, wizards and jesters have no suit).
- **Decision:** `std.tricktaking` works with what each game computes for each card: its
  **effective suit** (an integer; −1 = a card that can always be played) and its **strength**.
  With that it gives who may play what (`can_play`), each card's key in the trick (`trick_key`) and
  who wins it (`trick_winner`). Decks go in `std.cards`: Skat's reuses `Card` (French, from seven
  to ace) and Wizard's is `WizardCard` (4 suits × 15 ranks: the jester, 2 to ace and the wizard).
  `std.betting` does the same with bets (lists of integers per seat) and `std.boards` with boards
  (directions, bounded rays and jumps, tracks).
- **Alternatives:** generics in the language (a big change for a single phase); one library per
  deck (it would duplicate the trick rules).
- **Consequences:** Wizard and Skat share the trick mechanics; a new trick-taking game only writes
  how it sees its cards.

### ADR-065 — Rules of the second-wave games
- **Decision** (the recommendations of question 9, applied):
  - **Chess:** FIDE rules. Stalemate, insufficient material, fivefold repetition and 75 moves are
    automatic draws; threefold repetition and 50 moves, claimable by the player to move. En
    passant only counts for repetition if it is legal. There is no resignation or draw offer in
    the rules: leaving is up to the server (ADR-041), and losing on time is the room's `forfeit`
    option (which is why the IR's `on_timeout` is not needed, question 19).
  - **Skat:** the international Skatordnung (ISkO), for 3 or 4 players (the dealer sits out).
    Without Kontra or Re; if everyone passes, the deal is not played (no Ramsch). Seeger-Fabian
    tournament scoring as an option.
  - **Parchís:** the usual Spanish rules (leaving home with a five is mandatory, capturing gives 20
    and reaching home 10, blockades, a six counts seven with no pawns at home, three sixes), with
    two players on opposite colors and pairs as an option.
  - **Wizard:** Amigo's rules, with the "hook" variant as an option.
  - **Poker:** no-limit Texas Hold'em for 2 to 10 players, with fixed blinds.
  - **Solitaire:** Klondike with draw one or three and passes through the waste as an option; the
    game ends when the foundations are complete, when it gets stuck or at a maximum number of moves
    (1,000 by default).
- **Consequences:** each special rule has its Nomos test; variants are options (`params`) or a
  few-line `extends`.

### ADR-066 — Language adjustments requested by the F6 games
- **Decision:**
  - Inside a module function, the names declared by the game that imports it do not exist: a
    stdlib parameter `led` no longer clashes with a game function `led` (previously, E204).
  - A grid can be **assigned the list of its rows** (`board = [[…], …]`), also in tests' `set`;
    the dimensions are checked at run time.
  - A **list of zones** with `@visible(face_up)` (Solitaire's columns) is redacted zone by zone.
  - The leak analysis (W405) understands `@visible(viewer == owner or …)` as "the owner sees their
    part", like `@visible(owner)`.
  - The compiler gives the IR of a module without a game (its types and functions), so that tools
    can call them.
- **Consequences:** chess test positions are written as boards; no false leak warnings in the Skat
  hand.

### ADR-067 — Documentation in English
- **Context:** ADR-015 set Spanish for the documentation. The user asked, once F6 was finished, to
  translate all the documentation into English: the project has to be professional. Supporting
  Spanish in the games is welcome (a platform that uses the games as an API has to be
  translatable), but that is part of the information each game ships, and it is optional.
- **Decision:** the wiki, the READMEs, `log.md`, `CLAUDE.md` and the other documentation are
  written in English (wiki pages renamed accordingly: `engine.md`, `language.md`,
  `decisions.md`…). Games keep their translatable texts (`{ en: …, es: … }`) and UIs their
  es/en catalogs. Communication with the user stays in Spanish. The scope beyond the documentation
  (code comments, CLI messages, the default language of games and UIs, commit messages) is
  [question 24](open-questions.md).
- **Consequences:** historical entries (log, ADRs) are translated as well; commit messages already
  in the history stay as they are.

### ADR-068 — Game theory on the reference engine, in exact arithmetic
- **Context:** F7 asks for game theory on any game written in Nomos, with the reference results of
  [game theory §6](game-theory.md#6-reference-results-validation-tests) reproduced exactly
  (Kuhn's −1/18, not −0.0555…).
- **Decision:** everything is computed with the reference engine (no second implementation of the
  rules) over two explicit representations built from it (`gamehub.analysis.tree`):
  - The **extensive form** (`build_tree`): chance nodes with exact probabilities, decision nodes
    grouped into **information sets keyed by the engine's information state** (the SHA-256 of what
    the seat has observed, views and events, since the start: perfect recall), computed
    incrementally (same keys as `State.information_state`, without its quadratic cost), and
    terminals with rational payoffs. Simultaneous nodes are played one seat after another: the
    submissions are hidden, so the later seat does not know what the earlier one chose and the
    game is the same. Chance outcomes that lead to the same state with the same events are
    **merged** (shuffling J J Q Q K K gives 720 draws but 90 distinct orders): Leduc goes from
    millions of nodes to 74,251 (288 information sets, the standard count).
  - The **state graph** (`state_graph`): distinct states by digest, for counting positions and
    games and for backward induction (tic-tac-toe: 5,478 positions, 255,168 games).
  Payoffs and probabilities are `Fraction`s; only CFR works in floating point.
- **Alternatives:** going through OpenSpiel for everything (pyspiel works in floating point and
  would need the wrapper for every analysis); a tree representation in C++ (that is F8).
- **Consequences:** exact results for the games Python can traverse (≲ 10⁶ nodes); the bigger
  ones wait for the C++ core (F8) or approximate methods (F9). The information sets are exactly
  the engine's, so any game with hidden information gets them right without annotations.

### ADR-069 — Exact linear programming, HiGHS for large programs
- **Decision:** `gamehub.analysis.lp.linprog` solves `min/max c·x` with `≤`, `=` and free
  variables with a **two-phase simplex in rationals** (Dantzig's rule, switching to Bland's after
  a streak of degenerate pivots: the programs of games are very degenerate). With
  `backend="highs"` (or `"auto"` above 60,000 cells and with `highspy` installed: the
  `gamehub[analysis]` extra) it uses HiGHS and returns floats. Zero-sum games, dominance by mixed
  strategies, correlated equilibria, the sequence form, the core and the nucleolus all use it.
- **Alternatives:** HiGHS only (no exact values); `fractions` with an off-the-shelf library
  (there is none maintained for exact LP in pure Python).
- **Consequences:** Kuhn's zero-sum LP over its 27 × 64 reduced normal form takes 0.08 s and gives
  −1/18; Leduc's sequence form goes to HiGHS (−0.0856, the value in the literature).

### ADR-070 — Solution concepts per class of game
- **Decision:**
  - **Normal form** (`normal_form`): **reduced** pure strategies (plans of action: a choice only at
    the information sets the plan itself lets you reach), payoffs by bit masks over the terminals
    consistent with each plan. Kuhn: 27 × 64, the same as Gambit computes from our `.efg`.
  - **Two players:** support enumeration with equal-size supports (all equilibria of a
    nondegenerate game; used while there are at most 20,000 pairs of supports) and Lemke–Howson
    with the lexicographic ratio test (does not cycle on degenerate games), exact. n players: pure
    equilibria and correlated equilibria (LP).
  - **Zero-sum:** maximin by LP; with imperfect information, the **sequence form** (Koller,
    Megiddo and von Stengel), exact and of the size of the tree.
  - **Perfect information:** backward induction over the state graph (subgame-perfect equilibrium
    with n players, general sum and chance, ties to the first action) and alpha-beta with a
    transposition table for two players of constant sum (expectimax at chance).
  - **CFR / CFR+** with alternating updates in floats; **best response** in one pass thanks to
    perfect recall; **NashConv** = Σ (best response − value) and **exploitability** = NashConv / n,
    OpenSpiel's convention (uniform Kuhn: 11/24, the same as OpenSpiel).
  - **CGT:** Grundy values checking the normal-play convention at every terminal (misère is
    refused); N/P classes with alpha-beta. **Cooperative:** v(C) as the coalition's maxmin, exact
    Shapley, Banzhaf, core and least core by LP, nucleolus by successive LPs, Nash bargaining over
    the convex hull. **Repeated games:** Axelrod round-robin with classic automata and the
    ecological simulation.
- **Consequences:** every reference result of §6 except Connect Four 7×6 (ADR-074) is a test.
  Left for later: QRE, replicator dynamics and fictitious play, ESS, Moran, *-minimax, proof-number
  search, partizan canonical forms and temperature, DCFR/MCCFR (F8–F9).

### ADR-071 — Feasibility advisor
- **Decision:** `feasibility(game)` = the static classification + **Knuth's estimator** (each
  random walk weights each depth by the product of the branching factors; at chance, by the
  inverse of the sampled outcome's probability, i.e. importance sampling, merging equivalent
  outcomes when there are at most 5,000) + an **exact count** if the estimate is small or a bounded
  probe (10,000 nodes, 5 s; a perfect-information game may have far fewer states than its tree
  suggests: Nim 3-5-7 has 10⁷·⁶ nodes and 376 positions) + **recommendations** with stable codes
  (`solve`, `grundy`, `normal_form`, `nash`, `sequence_form`, `cfr`, `tournament`, `cpp_exact`,
  `cpp_cfr`, `approximate`) and the phase that brings them when they do not exist yet. Sampling
  stops after a time budget (20 s, at least 20 samples). The Studio's size estimate (F5,
  ADR-058) now uses the same estimator.
- **Consequences:** the estimate is close to the truth where it can be checked (tic-tac-toe
  10⁵·⁷ vs 549,946 nodes; Leduc 10⁴·⁹ vs 74,251) and the advisor answers in seconds for small
  games and in under half a minute for chess, Wizard or Skat.

### ADR-072 — Gambit and OpenSpiel
- **Decision:** `gamehub export GAME --to gambit-efg|gambit-nfg` writes Gambit's formats: nodes in
  preorder, information sets numbered per player, rational probabilities and payoffs, and labels
  transliterated to printable ASCII (Gambit rejects anything else). `to_openspiel(game)` wraps a
  game as a `pyspiel.Game` (sequential, explicit chance, terminal rewards): action ids are global,
  found by exploring the state graph or the tree (so only games that fit in memory can be
  wrapped), chance outcomes are numbered per chance node, the information-state string is a
  perfect-recall key of the seat's observations and the observation string its current view; the
  state shares the immutable engine state, so OpenSpiel's `deepcopy` clones copy nothing.
  `open-spiel` is an optional extra (`gamehub[openspiel]`) and a dev dependency.
- **Verification:** pygambit 16.7 (on Python 3.13; there are no 3.14 wheels) reads our Kuhn
  `.efg` with 27 × 64 strategies and 6 + 6 information sets and its LP gives −1/18; its equilibria
  of the 2×2 games coincide with ours. With the wrapped Kuhn, OpenSpiel's `random_sim_test`
  passes, the uniform policy's exploitability equals that of its native `kuhn_poker`, its CFR+
  converges to −1/18 and its alpha-beta gives tic-tac-toe as a draw.

### ADR-073 — `gamehub analyze` and the Studio's "Analysis" tab
- **Decision:** `gamehub.analysis.report.analyze(game, analyses)` runs the requested analyses and
  returns one JSON document (rationals as exact strings: `"-1/18"`); `auto` = the advisor plus what
  it recommends when it takes seconds. An analysis that does not apply (alpha-beta with hidden
  information, Grundy on a misère game, a normal form that would not fit) does not break the
  report: it goes to `errors` with its reason. Before building a tree, a quick estimate refuses
  what would not fit (tic-tac-toe's normal form fails in half a second instead of minutes). The
  CLI renders the report as text (`--json` for the document) and the Studio asks for it with
  `gamehub/analyze` and draws it in the **Analysis** tab: the advisor with a button per
  recommendation, the payoff matrix with best responses underlined and pure equilibria boxed,
  equilibria, efficiency, the strategy per information set, CFR's convergence, Grundy, the
  characteristic function and the tournament with its ecological simulation. The `repeat`
  combinator now tags its games `repeated` (and `best_of`, `best-of`) so that the advisor proposes
  a tournament.
- **Consequences:** one implementation for the terminal, notebooks (`_repr_html_` on the normal
  form, the tree, the tournament and the advisor) and the Studio.

### ADR-074 — Connect Four 7×6 is solved in F8
- **Context:** §6 lists "Connect Four (7×6): the first player wins". The reference engine solves
  about 1,600 states per second with alpha-beta; the 7×6 board needs hundreds of millions of
  positions even with the best move ordering (5×4 already took 7 minutes).
- **Decision:** in F7 the alpha-beta search is checked on small boards against an independent
  solver written directly in the test (3×3, 4×3 and 3×4 with three in a row; 4×4 with four,
  a draw, among the `slow` tests). The 7×6 result moves to F8's acceptance (C++ core, bitboards
  and transposition tables); its test is in place, skipped with that reason.
- **Consequences:** F7's acceptance is met for every reference result except that one, which
  depends on F8.

