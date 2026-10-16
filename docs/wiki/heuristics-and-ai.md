# Heuristics, bots, arena and AI

> Status: **design v0.1**. Heuristics and classical bots in Phase 9; AI (RL, Deep RL, LLM) in
> Phase 11, as requested: last.

## 1. Heuristics as first-class artifacts

A heuristic is knowledge about the game that is **not** a rule: evaluation functions, move
ordering, simulation policies, decision rules. They live in the game's repository
(`heuristics/`) and are versioned, compared and published like everything else.

They are written **in the same expression language** (so they run on the C++ engine at full
speed) or as a plugin (Python, C++, an ONNX neural network):

```game
heuristic Material for Chess {
  feature material(s) = sum(p in pieces(s, me)  : value(p.kind))
                      - sum(p in pieces(s, opp) : value(p.kind))
  feature mobility(s) = len(legal_moves(s, me)) - len(legal_moves(s, opp))
  feature center(s)   = count(p in pieces(s, me) : p.square in {d4, d5, e4, e5})

  eval = 1.0 * material + 0.1 * mobility + 0.3 * center      // tunable weights
  order moves by captured_value desc, then checks first        // ordering for alpha-beta
}
```

**Uses:** evaluation at the minimax/expectimax cutoff · *prior* and *rollout* policy in MCTS ·
leaf evaluation in ISMCTS/PIMC · direct policies for rule-based bots.

**Weight tuning:** CMA-ES, SPSA, *Texel tuning* (logistic regression over results), genetic
algorithms; the arena measures whether a tuning really is an improvement (with SPRT).

## 2. Kinds of bots

| Kind | Examples | When |
|---|---|---|
| Random | Uniform over the legal actions | Fuzzing, baseline |
| Rule-based | A priority list ("if you can win the trick with your lowest card, do it") | Card games, tutorials |
| Search | Minimax/alpha-beta, expectimax, MCTS, **ISMCTS**, **PIMC** (determinization, used in Skat) | Perfect / imperfect information |
| Game theory | Equilibrium strategy (CFR) | Small imperfect-information games |
| Learned | PPO, DQN, AlphaZero, NFSP, Deep CFR | Phase 11 |
| LLM | Reads the generated rules and the observation as text | Phase 11 |

Common interface (Python; equivalents in C++ and TS), implemented in Phase 3 and **the same in
process and over the network** ([ADR-043](decisions.md)):

```python
class Agent:
    def act(self, observation, legal) -> Action: ...    # required
    def reset(self, observation): ...                   # optional: at the start of each match
    def observe(self, observation): ...                 # optional: when it is not its turn
    def end(self, result): ...                          # optional: at the end
```

`observation` has `seat`, `view` and `events` (and, over the network, `clock` and `game`); `legal`
are the legal actions as `Action`s. `gamehub bot run agent.py --room K7F-Q2P` plays with a file
that defines `make_agent(game, seat)`, an `Agent` class or an `act` function.

## 3. Arena

- Round-robin, Swiss and gauntlet tournaments; mirror matches (same deals with rotated seats) to
  reduce variance in games of chance.
- **Elo / Glicko-2** ratings (2 players) and **TrueSkill** (n players, teams), always **per rules
  hash**.
- Third-party bots sandboxed (process/container/WASM) with CPU, memory and time limits.
- Local bots or bots connected through the protocol (a bot is just another client).

## 4. Design analytics ("is my game balanced?")

| Metric | Question it answers |
|---|---|
| Advantage per seat | Does the first player win too often? |
| Draw rate, length | Are matches too long or too drawish? |
| Branching profile | Are there stretches without real decisions? |
| **Skill depth** (*skill chain*) | How many distinct levels of play fit in? |
| **Skill vs. luck** | How much better does a strong bot do than a random one? |
| Lead changes, decisiveness | Is there tension until the end? |
| **Dominant strategies** | Is there an action that always pays off? |
| **Rule coverage** | Are there rules that never come up in real matches? |
| *Kingmaking* (n players) | Does a player who can no longer win decide who wins? |

These metrics feed the **Balance CI** of [hub](hub.md) PRs.

## 5. AI (Phase 11)

- **Automatic tensorization** from the IR: zones and boards → one-hot planes, counters →
  normalized scalars, actions → indices with a legality mask. Any game in the catalog can be
  trained on without writing encoding code.
- **Adapters:** Gymnasium (1 agent), PettingZoo (AEC/parallel), OpenSpiel.
- **Vectorized environments in C++** (thousands of matches in parallel).
- **Algorithms:** PPO, DQN; **AlphaZero** (MCTS in C++ + a PyTorch network); MuZero; imperfect
  information: NFSP, Deep CFR, PSRO, R-NaD, ReBeL.
- **ONNX export** → inference in C++ and in the browser (onnxruntime-web).
- **LLM agents:** observation and rules as text; tools = legal actions.
- **AI-assisted design:** rules in natural language → a `.game` draft; explaining rules; balance
  suggestions based on the analytics.

## 6. Fair play, humans vs. bots

- **Memory games:** the bot's *recall* policy (`recall: none | last(k) | perfect`); without it a
  bot never forgets and the game loses its point.
- **Speed games:** minimum reaction time/jitter for bots at `race` nodes.
- Rated matches flagged as "with bots" or "humans only".
