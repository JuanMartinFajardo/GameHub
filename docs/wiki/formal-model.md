# Formal model of a GameHub game

> Status: **v0.1** (Phase 0). This document is GameHub's *semantics*: every engine (Python, C++,
> WASM) and every analysis tool must behave exactly like this. Its concrete form as data lives in
> [`spec/ir/v0`](../../spec/ir/v0) ([GameIR](ir.md)).

## 1. Theoretical basis

The model combines three traditions:

- **Extensive-form games** (trees, information sets, chance nodes, payoffs).
- **FOSG** — *Factored-Observation Stochastic Games* (Kovařík, Schmid, Burch, Bowling, Lisý,
  2022): at each step every player receives an observation factored into a **public** and a
  **private** part. It is the basis of modern algorithms for imperfect information (CFR, ReBeL,
  Student of Games).
- **Statecharts** (Harel, 1987): **hierarchical** state machines, which is what the "flow chart"
  of a game really is (match → round → trick → turn).

## 2. Definition

A GameHub game is a tuple

$$\mathcal{G} = \langle \Theta,\ N_\theta,\ R,\ \mathcal{C},\ \Sigma,\ \mathcal{F},\ \mathcal{A},\ \mathrm{Vis},\ u,\ \mathcal{T} \rangle$$

| Symbol | Name | Description |
|---|---|---|
| $\Theta$ | Parameters | Parameter space; $\theta\in\Theta$ is fixed when the match is created (number of players, variants, sizes). |
| $N_\theta=\{0..n-1\}$ | Seats | Positions in the rules. Pseudo-players: **chance** $c$ and **system** $\bot$. A *participant* (human/bot) occupies a seat; they are not the same thing. |
| $R$ | Roles / teams | $\rho: N\to 2^R$. Teams = a partition of $N$. |
| $\mathcal{C}$ | Components | Types (card, token, die…) with finite-domain attributes; instances have identity. |
| $\Sigma$ | State schema | Typed variables (global, per player), **zones** (collections of components) and **boards** (grids, graphs). $S_\theta$ = valuations of $\Sigma$. |
| $\mathcal{F}$ | Flow | Statechart $(V,\kappa,\mathrm{parent},E)$: nodes, node kind, hierarchy, transitions $(v,g,\varepsilon,v')$ with guard $g$ and effect $\varepsilon$. |
| $\mathcal{A}$ | Action schemas | $(\text{name}, \text{parameters with domain } D(s), \text{guard } g(s,i,x), \text{effect } \varepsilon(s,i,x))$. |
| $\mathrm{Vis}$ | Visibility | For each location $\ell$ of the state: $\mathrm{Vis}(\ell,s)\subseteq N$ (who sees it, *state-dependent*). |
| $u$ | Payoffs | $u: Z\to\mathbb{R}^n$ at terminal nodes; optional intermediate rewards $r_i$ (RL). |
| $\mathcal{T}$ | Time | Clocks and deadlines (optional). |

## 3. Elements

### 3.1 Flow nodes

| Kind | Who acts | Semantics |
|---|---|---|
| `decision` | One seat (`actor`) | The actor picks a legal action; it is applied immediately. |
| `simultaneous` | A set (`actors`) | Each actor submits a **hidden** action; once the set is complete they are all resolved at once. |
| `window` | An eligible set | Reaction window ("Bullshit!", calling UNO, claiming a tile in Mahjong). Modes: `priority`, `collect`, `race`. |
| `chance` | Chance $c$ | The only source of randomness: shuffling, rolling dice, random draws. Explicit distribution. |
| `auto` | System | Deterministic computation (scoring, checking for a win) and a transition. |
| `phase` | — | Compound node with its own `start`, `on_enter`, `on_exit`; it can be a loop (`for r in 1..R`, `repeat until …`). |
| `call` | — | Invokes a reusable sub-flow (e.g. `std.tricktaking.Trick`). |
| `terminal` | — | End of the match; defines payoffs, ranking and winners. |

Outgoing **transitions** are evaluated **in order**; the first one whose guard holds wins and its
effect is applied. If none holds, it is a *rule error* (the static checker warns about
non-exhaustive transitions).

### 3.2 Actions

- An action is a **schema** `name(p₁: D₁, …, p_k: D_k)` with domains that may depend on the state
  (`c: Card in hand[actor]`, `n: Int in 0..round`, `cs: subset(hand[actor], 1..4)`).
- **Legality** = parameters within their domain ∧ the guard holds.
- **Compound actions / progressive building:** with $p_1..p_j$ fixed, the engine can enumerate the
  legal values of $p_{j+1}$. This serves UIs (pick a piece → its destinations light up) and RL
  (autoregressive action heads).
- Domains must be **finite and enumerable**. "Continuous" parameters (a bet) are declared with a
  discretization or as an integer interval.
- Each parameter has its own visibility: in *Bullshit* the played cards are private, but the
  number of cards and what is *declared* are public.

### 3.3 Chance

- Only `chance` nodes (and `setup`) contain random effects: `shuffle`, `roll`, `draw_random`,
  `sample(dist)`.
- Each random effect defines an **outcome space** $\Omega(\xi)$ with probabilities. If $|\Omega|$
  is small (a die: 6) it is **enumerable** (exact algorithms walk through it); otherwise
  (shuffling 52 cards: $52!$) it can **only be sampled** (Monte Carlo algorithms).
- The engine samples with a seeded RNG (PCG64, separate streams per purpose) → **determinism and
  replays**.
- Incomplete information "à la Harsanyi" (private types) is modeled as chance that assigns types
  with private visibility.

### 3.4 Information

- **Locations** $\ell$: variable paths (`score[2]`), zone contents, zone sizes, component
  attributes (`face`), event fields.
- **Redaction:** $\mathrm{view}_i(s)$ = $s$ with every $\ell$ such that
  $i\notin\mathrm{Vis}(\ell,s)$ replaced by $\bot$ (keeping the declared public "shape", e.g. the
  size of a hand).
- **Events:** every effect emits events (move, reveal, assignment, chance outcome) with their own
  visibility. The observation of $i$ after a step is
  $o_i = (\mathrm{view}_i(s'), \text{events visible to } i)$, factored into a public and a private
  part.
- **Information state** of $i$: $I_i = (o_i^0, a_i^0, o_i^1, a_i^1, \dots)$. *Perfect recall* by
  construction. Information set = histories with the same $I_i$.
- **Hidden components without identity (leak prevention, [ADR-019](decisions.md)):** there are
  two kinds of zone. An **ordered zone** (deck, pile, Memory row) has public positions: whoever
  cannot see its contents sees a gap per position, and can track "the top card" just like at the
  table. A **bag** (a hand) is a multiset: its order is not part of the state and whoever cannot
  see its contents only sees its size. Hidden components never expose an identifier, so no
  information leaks through IDs or order; whatever a player remembers of what was revealed is
  legitimate information (perfect recall).
- **`reveal` is an event:** it shows values to certain seats without changing the persistent
  visibility. Cards that stay face up use `flip` and the `item_face_up` predicate.
- **Action parameters:** their visibility applies to the other seats; the actor always sees their
  own action.
- **Legality leaks:** if the guard of an action of $i$ depends on locations $i$ cannot see, the
  set of legal actions leaks information to them. The information-flow analysis detects this and
  warns (it can be marked as intentional).
- Visibility is declared **on the data**, not per node: this avoids inconsistencies. Dependence on
  the current node is expressed in the policy itself: `@visible(all if at(Showdown) else owner)`.

### 3.5 Simultaneity, windows and races

- `simultaneous`: hidden submissions go into a buffer $\beta$; once complete, `resolve` runs with
  the joint action (canonical seat order, or the declared one).
- `window` in `priority` mode: seats are asked in order; the first "non-pass" resolves it.
  `collect`: everyone answers in secret; it is resolved by priority. `race`: real time, the first
  valid action according to the **server's** timestamp wins (speed games).
- For analysis, `race` ≡ `collect` with ties broken by priority (a documented approximation).

### 3.6 Time

Per-seat clocks (initial time, increment), per-node deadlines, and `on_timeout` (default action,
pass, random legal action, loss). Time is part of the *match* (the server), not of the analysis,
unless the game models it as discrete state.

### 3.7 History

Rules can only read the current state **plus** history features maintained by the engine and
declared (`history.count(position)`, `history.last(k)`). The configuration remains Markovian.
Examples: threefold repetition in chess, "do not repeat the previous move".

### 3.8 Outcomes

Terminal node → payoff vector $u(z)\in\mathbb{R}^n$, ranking (a partial order) and winners.
Cooperative table games (Hanabi) = a common payoff. Intermediate `reward`s are only for RL.

## 4. Operational semantics

A **configuration** is $\xi = (s, \bar v, \beta, h, t)$: state valuation, stack of active
statechart nodes, buffer of pending submissions, history features and clocks. The engine:

1. **Advances to quiescence:** runs `auto` nodes, `phase` entries/exits and `call`s until it
   reaches a *decision point*, a *chance point* or a *terminal*. (Cycles of automatic nodes
   without progress are detected statically and, at run time, with a step limit.)
2. At a decision point it exposes $\mathrm{Act}(\xi)\subseteq N$ and $L_i(\xi)$ for each active
   $i$.
3. At a chance point it exposes $P(\cdot\mid\xi)$ over $\Omega(\xi)$ (enumerable) or a sampler.
4. Applying an action: validate domain + guard → effect → transitions → `on_exit`/`on_enter` →
   events → back to 1.

**Determinism:** $(\mathcal{G}, \theta, \text{seed}, \text{action sequence}) \Rightarrow$ a unique
trajectory. A *replay* is exactly that tuple.

The exact details (order of evaluation of transitions, `$exit`, windows, chance draws, events)
are in the operational semantics of the [reference engine](engine.md).

## 5. Automatically derived properties

| Property | Definition | How it is determined |
|---|---|---|
| Deterministic | No reachable `chance` nodes | Static |
| Perfect information | Everything visible to everyone and no hidden submissions | Static |
| Zero-sum / constant-sum | $\sum_i u_i(z)=k\ \forall z$ | Symbolic if payoffs are a table or a simple expression; empirical otherwise |
| Common payoff (cooperative) | $u_i=u_j\ \forall i,j$ | Static / symbolic |
| Simultaneous | There are `simultaneous` or `window collect` nodes | Static |
| Impartial (CGT) | 2 alternating players, same options, "normal play" | Static (+ declaration) |
| Finite horizon | Acyclic flow after unrolling bounded loops, or `max_steps` | Static / declared |
| Size | $|S|$, depth, branching, number of information sets | Knuth's estimator + playouts |

## 6. Correspondence with classical formalisms

| Formalism | How it is obtained from a GameHub game |
|---|---|
| Extensive form (EFG) | Unfold configurations; simultaneous moves are sequentialized with information sets |
| Normal form (matrix) | Direct if it is a single simultaneous node; otherwise reduced pure strategies (exponential) |
| FOSG | Direct: public/private observations per step |
| MDP / POMDP | 1 player (Solitaire = a POMDP with chance) |
| Stochastic game | Flow with cycles (no fixed horizon) |
| Combinatorial game theory (CGT) | 2 players, alternating, perfect information, no chance; sums via the `sum` combinator |
| Cooperative game (characteristic function) | A *derived* object $v(C)$ (e.g. the maxmin value of each coalition), not a flow |

## 7. Restrictions that guarantee all of the above

- **Total expressions:** no general recursion; loops only over finite collections.
- **No effects in expressions:** only effect blocks modify the state.
- **No hidden sources of nondeterminism:** neither a clock nor an RNG is reachable from
  expressions.
- **Finite action domains.**
- **Rule errors** (index out of range, no matching transition) abort the match with a located
  diagnostic; tests and fuzzing aim to eliminate them before publishing.

See: [The `.game` language](language.md) · [GameIR](ir.md) · [Game theory](game-theory.md)
