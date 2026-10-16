# Glossary

| Term | Definition in GameHub |
|---|---|
| Action | A seat's choice at a decision point: name + parameters with a domain. |
| Action builder | The part of the generic UI that composes an action argument by argument with the values the legal actions allow (enumerated or with `query_actions`). |
| Agent / bot | A program that plays: `act(observation, legal actions) → action`. The same agent plays in process or over the network. |
| Bag | An unordered zone (a multiset), typical for hands; whoever cannot see its contents only sees its size. |
| Chance / nature | The pseudo-player that resolves `chance` nodes according to explicit distributions. |
| Combinator | A game built from another one by transforming its IR: `repeat(G, rounds: n)`, `best_of(G, rounds: n)`. |
| Configuration | The engine's complete state: values + active nodes + pending submissions + history + clocks. |
| Conformance trace | A replay with a fixed seed that every engine must reproduce bit for bit (`spec/conformance`). |
| Core / resolved IR | The sugar-free IR that engines run; the Nomos compiler generates it. |
| Current turn | From the update in which a seat can act until it acts or another node is reached; an `act` decided earlier is rejected (`stale_seq`). |
| Custom UI | A hand-made interface for a game (`games/<game>/ui`, with `defineGameUi`); the app uses it instead of the generic one. |
| Deadline / clock | Time to decide: fixed per turn (`move`) or a total time per seat with an increment (`match`); when it runs out, `on_timeout` applies. |
| Decision point | A configuration in which one or more seats must act. |
| Diagnostic | A compiler error or warning with a code, position, explanation and help (rustc style). |
| Digest | SHA-256 of a state's snapshot; it allows comparing engines step by step. |
| Edit operation (Studio) | A change from the diagram or a form (`addNode`, `addTransition`, `updateAction`…) applied to the tree of the `.game`; the text is rewritten only where it changed. |
| Effect | A statement that modifies the state (`assign`, `move`, `reveal`…). Only in effect blocks. |
| Effective suit | In `std.tricktaking`, the suit a card counts as in a trick (an integer; −1 = it can always be played, like Wizard's wizards and jesters). |
| Event | A record of something that happened (a move, a reveal…), with its visibility. |
| Flow | The game's flow chart: a hierarchical statechart of nodes and transitions. |
| Forfeit | Resigning, leaving during a match or running out of time with `on_timeout: forfeit`: the seat ends up last and a bot plays for it until the end. |
| GameIR | The canonical intermediate representation (JSON) of the game; the source of truth. |
| Generated code | IR expressions and functions written as Python code and compiled with `exec` (`gamehub.engine.codegen`): same results as the reference closures, about twice as fast. |
| Generic UI | The interface that draws and lets you play any game from its IR, without writing anything (`@gamehub/auto-ui`). |
| Guard | A pure boolean condition of an action (`requires`) or a transition (`when`). |
| Host | The participant who administers a room: configures it, opens or reserves seats, adds bots, kicks someone out. |
| Hot-seat | Several people taking turns on the same screen; in the web app, with one connection per seat and the screen covered between turns if there is hidden information. |
| Information leak | Hidden data reaching someone who should not see it (through the state, an event, the path taken or the legal moves); `gamehub check` warns about it (W405). |
| Information set | Histories a player cannot tell apart (same information state). |
| Information state | The sequence of a player's observations and own actions. |
| Interface hash | A digest of the view/action/event schemas; compatibility of UIs and bots. |
| Invariant | A condition that must hold in every reachable state; `gamehub test` checks it in tests and random matches. |
| Language server (LSP) | `gamehub lsp`: diagnostics, completion, hover, definition, rename… for any editor; the Studio uses the same one over WebSocket. |
| Layout (of the diagram) | Where each box of the Studio diagram goes: ELK computes it and the user adjusts it; it is stored in `<game>.layout.json`, outside the rules. |
| Legal action | An action whose parameters are within their domain and whose guard holds. |
| Location | An addressable part of the state (variable, zone, size, attribute) on which visibility is defined. |
| Lockfile | `game.lock`: the exact commit of each git dependency of a package. |
| Match | A concrete run of a game: parameters + seed + actions. |
| Memoization (of functions) | Results of IR functions kept according to what they depend on: forever if only on their arguments (*static*), while the state does not change if they read it (*state*). |
| Mod / variant | A game that extends another one (`extends`) with `override`, `remove` and `extend node`. |
| Module | A `.game` file whose declarations (`enum`, `struct`, `fn`, games) are used with `import`. |
| Native plugin | A WebAssembly implementation of a `@native("m.f")` function, which must give exactly the same results as its Nomos body (the reference). ABI `gamehub-native/1`. |
| Node | A box of the flow: `decision`, `simultaneous`, `window`, `chance`, `auto`, `phase`, `terminal` (`call`, later). |
| Nomos | GameHub's game description language (`.game` files). |
| Observation | What a player receives after a step: redacted view + visible events (public + private). |
| Operator catalog | `spec/ir/v0/ops.json`: the closed list of IR expressions, statements and selectors. |
| Package | A game's directory with its `game.toml` (name, version, dependencies). |
| Participant | A person or bot in a room: a player (seated) or a spectator. |
| Payoffs | The utility vector at a terminal node. |
| Perft | The number of sequences of legal moves up to a depth (`gamehub perft`); in chess, the standard test of a move generator (*perft(5)* = 4,865,609). |
| Progressive action building | Choosing the parameters of an action one by one, asking for the legal ones at each step. |
| Provably fair | Committing to the server seed before playing, players' seeds and revealing it at the end (`gamehub-fair/1`): nobody can choose the chance outcomes and anyone can check them. |
| Public observer | Whoever holds no seat (`PUBLIC` in the engine): sees what visibility allows to someone who owns nothing. |
| Reaction window | A `window` node: several seats can respond to an event ("Bullshit!"). |
| Rematch | Another match in the same room with the same seats, once everyone declares themselves ready again. |
| Replay | A tuple (rules hash, parameters, seed, actions) that reproduces an exact match. |
| Room | A hosted instance of a game with its code, seats, settings and chained matches. |
| Room code | 6 Crockford base32 characters (`K7F-Q2P`) to join a room. |
| Rule coverage | How many times each node, action and transition was visited in the simulator's batch runs; whatever was never used is marked on the diagram. |
| Rules hash | A digest of the resolved IR; it identifies exactly one version of the rules. |
| Seat | A position in the rules (0..n-1). A participant occupies it. |
| Session | Someone's participation in a room, identified by a secret token that allows reconnecting. |
| Snapshot | The complete configuration of a state as canonical JSON (including card faces and pending submissions). |
| Spectator | A participant without a seat: sees the public view (or the omniscient one, if the room allows it), with an optional delay. |
| Standard library | The `std.…` modules that come with GameHub (`std.cards`, `std.dice`, `std.grid`, `std.graph`, `std.boards`, `std.tricktaking`, `std.bidding`, `std.betting`, `std.poker`). |
| Statechart | A hierarchical state machine (Harel); the model of the flow. |
| Studio | GameHub's visual editor (`gamehub studio`): diagram and text at once, inspector, simulator and tools. |
| Test | A game's `test "…" { … }` block: a scripted match with checks (`play`, `expect`, `chance where`, `set`). |
| UI hints | A game's `ui { … }` section: how to draw its variables, translated names, symbols, colors, cards, how to pick arguments. They are not rules: they do not count for the hash. |
| Update | A server message with what happened (an action and the chance that follows it) and the resulting state for the recipient; numbered with `seq` without gaps. |
| View | The state redacted for a specific seat. |
| Warning | A diagnostic that does not prevent compiling (`W…`): unreachable node, possible information leak, unused declaration… |
| Zone | An ordered collection of components with public positions (deck, pile, row). See also *bag*. |
