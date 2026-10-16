# Game theory module

> Status: **design v0.1**. v1 in Python with bridges to Gambit/OpenSpiel (Phase 7); at scale in
> C++ (Phases 8–9).

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
gamehub analyze chess --feasibility
# perfect-info · deterministic · zero-sum · branching≈31 · depth≈80
# tree ≈ 10^120 → exact solution infeasible. Recommended: alpha-beta + heuristic, MCTS, arena.
```

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

## 7. Usage examples

```bash
gamehub analyze prisoners-dilemma --nash --pareto
gamehub analyze tictactoe --solve
gamehub analyze kuhn-poker --cfr 100000 --exploitability
gamehub analyze nim --grundy --params heaps=3,5,7
gamehub analyze wizard --feasibility
gamehub export kuhn-poker --to gambit-efg
```

```python
from gamehub import load
from gamehub.analysis import normal_form, nash

g = load("prisoners-dilemma")
M = normal_form(g)              # 2×2×2 payoff matrix
print(nash.support_enumeration(M))   # [((0,1), (0,1))]  → (Defect, Defect)
```
