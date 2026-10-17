# Game theory module

> Status: **v1 implemented** (Phase 7, 2026-10-17) in
> [`python/src/gamehub/analysis`](../../python/src/gamehub/analysis), on the reference engine, in
> exact arithmetic, with bridges to Gambit and OpenSpiel; at scale in C++ (Phases 8–9). Decisions:
> [ADR-068 to 074](decisions.md). §7 says what is implemented and how to use it.

## 1. Philosophy: compute only what is feasible, and know beforehand whether it is

Before launching a computation, the **feasibility advisor** classifies the game and estimates its
size:

1. Static **classification** ([formal model §5](formal-model.md)): players, chance, perfect
   information, simultaneity, zero-sum, horizon.
2. **Size estimation:** branching and depth from playouts; tree size with **Knuth's estimator**
   (1975); distinct states by hashing; number of information sets.
3. **Recommendation** (indicative thresholds, to be calibrated):

| Size | What is feasible |
|---|---|
| ≤ 10⁶ states | Exact solution in Python (full tree, matrix, Nash) |
| ≤ 10⁹ states | Exact in C++ (alpha-beta with transposition tables, retrograde analysis) |
| ≤ 10⁷ information sets | Tabular CFR in C++ |
| Larger | Approximate: MCTS/ISMCTS, MCCFR, heuristics, RL; empirical metrics |

```bash
gamehub analyze games/chess --feasibility
# 2 jugadores · determinista · información perfecta · por turnos · suma cero
# ramificación ≈ 22.5 · duración ≈ 346.5 pasos (máx. 543) · árbol ≈ 10^658.4 nodos (Knuth)
# → solución exacta inviable: alfa-beta con heurística, MCTS, arena de bots (F9)
```

(Random games are much longer than real ones, hence 10⁶⁵⁸ rather than the usual 10¹²⁰; the CLI
speaks Spanish until [question 24](open-questions.md) is answered.)

## 2. Representations

Tree (extensive form) · DAG with transpositions · state graph (cyclic games) · **normal form
(matrix)** · sequence form · public tree (FOSG) · characteristic-function form (cooperative games).

## 3. Algorithm catalog by game class

| Class | Algorithms | Result |
|---|---|---|
| Perfect information, deterministic, 2-player zero-sum | Minimax, negamax, **alpha-beta** (+ iterative deepening, Zobrist transposition tables, move ordering), **retrograde analysis**, proof-number search | Game value, optimal strategy, "solved" |
| Perfect information with chance | Expectimax, *-minimax (Star1/Star2), value iteration | Expected value, optimal policy |
| Perfect information, n players / general-sum | **Backward induction → subgame-perfect equilibrium**; max^n, paranoid | SPE profile |
| Normal form | Pure equilibria, **iterated elimination of dominated strategies**, support enumeration, **Lemke–Howson**, **LP for zero-sum**, **correlated equilibrium** (LP), **Pareto** frontier, social optimum, price of anarchy/stability, ESS, replicator dynamics, fictitious play, QRE (logit) | Equilibria, dominance, efficiency |
| Imperfect information (extensive form) | Sequence-form LP (2-player zero-sum, exact), **CFR / CFR+ / DCFR / MCCFR**, best response, **exploitability / NashConv**, ISMCTS, PIMC | Approximate equilibrium with an error bound |
| Single player (MDP/POMDP) | Dynamic programming, A*/IDA*, beam search, search with determinization | Optimal policy, % of winnable games (Solitaire) |
| Repeated games | **Axelrod-style tournaments**, strategies as automata, evolutionary dynamics (Moran) | Rankings, evolutionary stability |
| Combinatorial (CGT) | **Sprague–Grundy** (Grundy values, mex, nim-sum), outcome classes (N, P, L, R), canonical forms, temperature; sums of games | Game value, winning moves |
| Cooperative (characteristic function) | Derived v(C) (the coalition's maxmin value), **Shapley value**, **core** (LP), **nucleolus**, Banzhaf index, Nash bargaining solution | Stable/fair allocations |

## 4. Visualizations (Studio and notebooks)

- Collapsible **tree explorer**, with linked information sets and values at each node.
- **Matrix view** with best responses underlined and equilibria highlighted.
- **Convergence** chart (exploitability vs. CFR iterations).
- **Pareto** and social-welfare charts.
- Grundy tables; strategy profiles as tables per information set.

## 5. Interoperability

- **Gambit:** export `.efg` / `.nfg` and use `pygambit` (its n-player solvers are mature).
- **OpenSpiel:** wrap any GameHub game as a `pyspiel` game → access to its whole algorithm catalog
  from day one.
- **CGSuite:** export positions of combinatorial games for complex canonical forms.

## 6. Reference results (validation tests)

| Game | Known result |
|---|---|
| Tic-tac-toe | Value = draw; 5,478 legal positions; 255,168 possible games |
| Prisoner's dilemma | Unique NE (D, D), Pareto-dominated by (C, C) |
| Rock-paper-scissors | Unique mixed NE (1/3, 1/3, 1/3), value 0 |
| Matching pennies | Mixed NE (1/2, 1/2), value 0 |
| Kuhn poker | Value for the first player = −1/18 |
| Nim | P-position ⇔ nim-sum (XOR) = 0 |
| Connect Four (7×6) | First player wins (Allis / Allen, 1988) |
| Chess (perft from the initial position) | 20 · 400 · 8,902 · 197,281 · 4,865,609 (verified in Phase 6) |

## 7. Implementation (v1)

Everything runs on the reference engine (no second implementation of the rules) and in exact
arithmetic (`Fraction`), except CFR (floating point). Modules of `gamehub.analysis`:

| Module | What it does |
|---|---|
| `feasibility` | The advisor of §1: classification, Knuth's estimator (importance sampling at chance; equivalent outcomes merged), exact counts or a bounded probe, recommendations with stable codes (ADR-071) |
| `tree` | `build_tree`: the extensive form, with the engine's information sets (perfect recall) and merged chance outcomes; `state_graph`: distinct states by digest (positions, games) (ADR-068) |
| `normal_form` | `NormalForm` (from matrices, from a function, or `normal_form(game)` with **reduced** pure strategies) |
| `lp` | Linear programming: exact two-phase simplex in rationals; HiGHS for large programs (`gamehub[analysis]`) (ADR-069) |
| `nash` | Pure equilibria, support enumeration, Lemke–Howson, zero-sum maximin, iterated dominance (strict/weak, pure/mixed), correlated equilibrium, Pareto, utilitarian and egalitarian optimum, price of anarchy and of stability |
| `search` | Perfect information: backward induction (subgame-perfect equilibrium, n players, chance) and alpha-beta with a transposition table (+ expectimax; depth limit with an evaluation function) |
| `policy`, `cfr`, `sequence_form` | Behavioral strategies, expected values, best response, NashConv and exploitability; CFR and CFR+; the exact sequence-form LP for two-player constant-sum games |
| `cgt` | `mex`, `nim_sum`, Grundy values (normal play checked), N/P outcome classes, L/R/N/P for partizan games from both starts, Grundy tables over a parameter |
| `coop` | Characteristic function (maximin of each coalition), Shapley, Banzhaf, core and least core, nucleolus, Nash bargaining |
| `repeated` | Axelrod round-robin tournaments with 11 classic strategies (TFT, GRIM, PAVLOV, GTFT, JOSS…), noise, and the ecological simulation |
| `export`, `openspiel` | Gambit `.efg`/`.nfg`; any game as a `pyspiel.Game` (ADR-072) |
| `report`, `widgets` | `gamehub analyze`'s JSON report (also the Studio's "Analysis" tab) and HTML views for notebooks |

```bash
gamehub analyze games/prisoners-dilemma                  # the advisor + what it recommends
gamehub analyze games/prisoners-dilemma --nash --pareto --dominance --correlated --coop
gamehub analyze games/tictactoe --solve --count          # value (0, 0); 5,478 positions; 255,168 games
gamehub analyze games/kuhn-poker --sequence-form         # -1/18, exploitability 0
gamehub analyze games/kuhn-poker --cfr 10000 --json      # CFR+ with its convergence
gamehub analyze games/nim --grundy --param 'sizes=[3,5,7]'
gamehub analyze games/iterated-pd --tournament 200 --noise 0.01
gamehub analyze games/chess --feasibility                # 10^658 nodes: approximate methods (F9)
gamehub export games/kuhn-poker --to gambit-efg -o kuhn.efg
```

```python
from pathlib import Path
from gamehub.lang.compiler import load_nomos
from gamehub.analysis import nash
from gamehub.analysis.normal_form import normal_form
from gamehub.analysis.tree import build_tree
from gamehub.analysis.sequence_form import sequence_form

pd = normal_form(load_nomos(Path("games/prisoners-dilemma/prisoners-dilemma.game")))
nash.pure_equilibria(pd)            # [(1, 1)]  → (Defect, Defect)
nash.pareto_dominators(pd, (1, 1))  # [(0, 0)]  → (Cooperate, Cooperate)
pd                                  # in Jupyter: the matrix, best responses and equilibria

kuhn = build_tree(load_nomos(Path("games/kuhn-poker/kuhn-poker.game")))
sequence_form(kuhn).value           # Fraction(-1, 18)
```

In the **Studio**, the "Analysis" tab runs the same report on the text being edited: the advisor
with a button per recommendation, the payoff matrix (best responses underlined, pure equilibria
boxed), the equilibria, the strategy per information set, CFR's convergence chart, Grundy, the
characteristic function and the tournament with its ecological simulation.

### Reference results: status

| Game | Known result | F7 |
|---|---|---|
| Tic-tac-toe | Draw; 5,478 positions; 255,168 games | ✅ alpha-beta and backward induction; state graph |
| Prisoner's dilemma | Unique NE (D, D), Pareto-dominated by (C, C) | ✅ |
| Rock-paper-scissors | Unique NE (1/3, 1/3, 1/3), value 0 | ✅ support enumeration and LP |
| Matching pennies | NE (1/2, 1/2), value 0 | ✅ |
| Kuhn poker | −1/18 | ✅ exact with the sequence form and with the LP over the 27 × 64 normal form; CFR+ converges; also in Gambit and OpenSpiel |
| Nim | P ⇔ nim-sum 0 | ✅ for every position with heaps ≤ 3 (by search, without Grundy theory); Grundy of sums = XOR |
| Connect Four 7×6 | First player wins | ⏳ F8 (C++); verified on small boards against an independent solver (ADR-074) |
| Chess perft | 20 · 400 · 8,902 · 197,281 · 4,865,609 | ✅ (F6) |

Other checks in the tests: Leduc's sequence form gives −0.0856 (the literature's value) with
exploitability ~10⁻¹⁶; the nucleolus of the three Talmud bankruptcy problems (Aumann and Maschler,
1985); Shapley and the core of the glove game; Aumann's correlated equilibrium of chicken; the
index theorem (an odd number of equilibria) on random nondegenerate games.

### Limitations and what comes next

- Python traverses ~10⁴ states per second: exact methods up to ~10⁶ nodes (Leduc's tree takes
  ~30 s to build). The C++ core (F8) moves those limits; MCCFR, ISMCTS and heuristics come in F9.
- The normal form is only attempted on trees of up to ~10⁴ nodes (reduced strategies explode).
- Not implemented yet: QRE, replicator dynamics, fictitious play, ESS and Moran processes;
  *-minimax and proof-number search; partizan canonical forms and temperature (CGSuite export);
  DCFR, MCCFR and the sequence form for more than two players.
- The OpenSpiel wrapper needs the game to fit in memory (it explores the game to number the
  actions); F8 computes the ids from the IR's action types instead, so it will work on any game.
