# Heuristics, bots, arena and AI

> Status: **implemented** (Phase 9, 2026-10-17): heuristic blocks in both engines, the core's
> bots with determinization, the arena with ratings, bot packages and sandboxing, balance
> analytics with a Balance CI and weight tuning. AI (RL, Deep RL, LLM) is Phase 11. Decisions:
> ADR-083 to 089 in [decisions](decisions.md).

## 1. Heuristics as first-class artifacts

A heuristic is knowledge about the game that is **not** a rule: an evaluation, priorities and an
order for the actions. It lives in the game (or in a variant that `extends` it), is written in
Nomos, is evaluated by both engines and has its own hash; it does **not** count for the rules
hash, so improving it changes neither replays nor ratings.

```game
/// Win if you can, block if you must, create threats and play the centre.
heuristic Threats {
  /// The cells of the `connect`-long segments through (r, c): options only, so computed once
  fn segments(r: Int, c: Int) -> List<List<Cell>> = …
  fn wins_at(x0: Cell, d: Disc) -> Bool =
    any(seg in segments(x0[0], x0[1]) : all(x in seg : x == x0 or board[x] == d))
  feature threats = open(disc(me)) - open(disc(other(me)))     // `me`: the seat evaluated
  feature center = central(disc(me)) - central(disc(other(me)))
  weights { threats: 0.05, center: 0.005 }                       // 1 when missing; tunable
  prefer drop(c) when wins_at(cell(landing(c), c), disc(me))     // priority 0
  prefer drop(c) when wins_at(cell(landing(c), c), disc(other(me)))  // priority 1
  order drop(c) by 2 * threats_at(cell(landing(c), c), disc(me)) + columns - abs(2 * c - 6)
}
```

| Member | Meaning |
|---|---|
| `fn` | Functions of the heuristic only (not rules; the rules cannot call them) |
| `feature name = expr` | A number measured from the seat `me` |
| `weights { name: n, … }` | The evaluation is Σ weight · feature (exact); 1 when missing |
| `prefer action(p, …) when cond` | Priority rules, in order: an action's priority is the first rule it meets |
| `order action(p, …) by key` | Its score (higher first; 0 without a rule) |

The key of an action is (priority, −score): the rule-based bot plays the best one, the searches
explore in that order and MCTS follows it in its simulations. The pattern names the action's
parameters by position. Variants inherit heuristics and may add, `override` or `remove heuristic`
them. In the IR: `heuristics: [{name, functions?, features, prefer, order}]` ([ir](ir.md)).
`gamehub heuristics GAME [--evaluate]` lists them with their hashes.

**Every catalog game has one**: Connect Four (threats), tic-tac-toe (lines), Nim (Bouton's
nim-sum, also misère), Kuhn and Leduc (hand strength), Hold'em (hand category before and after the
flop), Dudo (probabilities of the hidden dice), Bullshit (honesty and impossible claims), Skat
(bidding by jacks and long suit, cheapest winning card), Wizard (promised tricks, need),
Parchís (captures, goal, safe squares), Solitaire (foundations first, uncover cards), chess
(material, centre, MVV-LVA), the 2×2 family (best response to a random rival; ties are random,
which is the equilibrium of matching pennies), rock-paper-scissors (uniform) and the prisoner's
dilemma (the dominant defection).

## 2. Bots

| Kind | What it does |
|---|---|
| `random`, `first` | Uniform (PCG32(seed, 1000 + seat), like the reference) / the first legal action |
| `greedy` | Priority rules: the best key; ties broken one move ahead (payoff or evaluation) |
| `alphabeta` | Paranoid minimax (n players), expectimax at chance, iterative deepening, transposition table, heuristic ordering, evaluation at the horizon |
| `mcts` | Open-loop UCT: heuristic expansion order, simulations that follow the heuristic with probability `greedy`, the evaluation at `max_rollout` |
| `ismcts` | Information-set MCTS: one determinization per simulation, availability counts |
| `pimc` | The mean of alpha-beta (or MCTS) over `samples` determinizations |

Options: `seconds` (per move), `depth`, `iterations`, `c`, `samples`, `greedy`, `max_rollout`,
`heuristic` (or `none`). They are written `alphabeta:seconds=0.5,depth=6`.

**They only use what their seat sees.** They run in-process with the real state, but with hidden
information they decide on **determinizations** (`gamehub_core.determinize`): the hidden items of
zones and bags are pooled by type and dealt back at random (the seat cannot tell the cards it does
not see apart); the other hidden values (dice) come from a replay of the match with chance drawn
again; other seats' pending submissions are forgotten. Limits: what play reveals (a void in a
suit) is not used, and search bots cannot play over the network (the protocol only carries views).

Where they play: `gamehub play GAME --seats human,alphabeta:seconds=1`, the server's seat bots
(`/bot ismcts`, `set_seat`), "On this device" in the browser (rule-based, MCTS and alpha-beta with
perfect information; rule-based, ISMCTS and PIMC with hidden information), the arena and Python
(`gamehub.bots.agents.make_bot`, the `Agent` interface; on the reference engine the agent replays
the match in C++).

```python
from gamehub.bots.agents import make_bot
agents = [make_bot(game, "pimc:samples=8", 0), make_bot(game, "greedy", 1)]
play_match(game, agents, seed=3)
```

Common interface (Python; equivalents in C++ and TS), the same in process and over the network
([ADR-043](decisions.md)):

```python
class Agent:
    def act(self, observation, legal) -> Action: ...    # required
    def reset(self, observation): ...                   # optional: at the start of each match
    def observe(self, observation): ...                 # optional: when it is not its turn
    def end(self, result): ...                          # optional: at the end
```

## 3. Bot packages and sandboxing

```toml
[bot]
name = "c4-deep"            # identified as c4-deep@1.0.0
version = "1.0.0"
game = "connect-four"
rules = "sha256:…"          # optional: the rules it was written for
kind = "alphabeta"          # or random, first, greedy, mcts, ismcts, pimc, python
heuristic = "Threats"
entry = "agent.py"          # kind = "python"

[options]
seconds = 0.5

[limits]                    # kind = "python"
seconds_per_move = 2.0
cpu_seconds = 600
memory_mb = 1024
```

The core's kinds are trusted code. A Python bot runs in a **child process** with OS limits
(CPU time, memory where the OS allows it, no core dumps), an empty environment and a per-move
deadline, and only sees its observation; if it times out, crashes or answers something illegal,
it is killed and its seat plays at random until the end (recorded as a failure). The same file
plays in a room over the network: `gamehub bot run PACKAGE --room K7FQ2P`.

## 4. Arena

```bash
gamehub arena games/connect-four greedy alphabeta:seconds=0.05 mcts:seconds=0.05 --games 20
gamehub arena games/parchis greedy random first --players 4 --tournament gauntlet --db arena.json
gamehub sprt games/connect-four alphabeta:seconds=0.1 alphabeta:seconds=0.05 --elo1 20
```

- Round-robin (every table of n different entrants), Swiss and gauntlet; **mirror** matches (each
  seed with every rotation of the seats and the same chance).
- **Elo** (maximum likelihood), **Glicko-2** and **TrueSkill** (n players, draws), always **per
  rules hash** (`--db` accumulates matches per hash). A match of n players counts as all its pairs
  for Elo and Glicko-2.
- **SPRT** (`gamehub sprt`): Wald's sequential test with fishtest's trinomial model: is A better
  than B by at least `elo1`?
- Matches of the core's bots run in C++ threads; Python bots in their processes.

## 5. Design analytics ("is my game balanced?")

`gamehub balance GAME [--bot greedy] [--games 200] [--players N]` writes a Markdown (or JSON)
report from bot matches:

| Metric | How |
|---|---|
| Advantage per seat | Self-play of the reference bot: mean payoff and first places per seat, 95 % intervals |
| Draws, length | Matches with a tie at the top; steps and decisions per match |
| Branching profile | Legal actions per decision by tenths of the match; forced decisions |
| **Skill vs. luck** | The reference bot against random ones: (P(first) − 1/n) / (1 − 1/n) |
| **Skill chain** | A ladder of bots (random, greedy, MCTS 100/400/1600): steps that significantly beat the previous one |
| Tension | Lead changes by the heuristic's evaluation; when the winner takes the lead for good |
| **Dominant strategies** | Actions whose use lifts the win rate by more than 25 points |
| **Rule coverage** | Actions and transitions never taken (only the match's, not the bots' searches) |
| *Kingmaking* (n ≥ 3) | Late decisions of a seat that cannot win whose choice changes who wins |

**Balance CI:** `gamehub balance NEW --against OLD [--fail-on-regression]` runs both versions with
the same seeds and flags regressions (a seat advantage that appears, more draws, much longer
matches, less skill, a shorter chain, rules that stop being used, new dominant actions, more
kingmaking). These reports feed the hub's PRs (F10).

## 6. Weight tuning

```bash
gamehub tune games/connect-four --method texel --games 200 --bot greedy
gamehub tune games/connect-four --method cmaes --bot alphabeta:depth=2,seconds=0 --write
```

CMA-ES and SPSA maximize the first places of the bot with candidate weights against the current
weights in mirror matches; Texel fits a logistic model of the result on the features of self-play
positions. `--write` rewrites the `weights` block; the arena with SPRT says whether it helps.

## 7. Connect Four 7×6

`gamehub solve games/connect-four --heuristic Threats --threads 4` solves small boards and
positions with the heuristic ordering (5–6× fewer nodes than the history heuristic alone), but the
empty 7×6 board is still several orders of magnitude away with the generic VM (ADR-089, question
28).

## 8. AI (Phase 11)

- **Automatic tensorization** from the IR: zones and boards → one-hot planes, counters →
  normalized scalars, actions → indices with a legality mask (the action ids come from F8). Any
  game in the catalog can be trained on without writing encoding code.
- **Adapters:** Gymnasium (1 agent), PettingZoo (AEC/parallel), OpenSpiel.
- **Vectorized environments in C++** (thousands of matches in parallel).
- **Algorithms:** PPO, DQN; **AlphaZero** (MCTS in C++ + a PyTorch network); MuZero; imperfect
  information: NFSP, Deep CFR, PSRO, R-NaD, ReBeL.
- **ONNX export** → inference in C++ and in the browser (onnxruntime-web).
- **LLM agents:** observation and rules as text; tools = legal actions.
- **AI-assisted design:** rules in natural language → a `.game` draft; explaining rules; balance
  suggestions based on the analytics.

## 9. Fair play, humans vs. bots

- **Memory games:** the bot's *recall* policy (`recall: none | last(k) | perfect`); without it a
  bot never forgets and the game loses its point.
- **Speed games:** minimum reaction time/jitter for bots at `race` nodes.
- Rated matches flagged as "with bots" or "humans only".
