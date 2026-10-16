# Game catalog

> Status: **waves 1 and 2 complete** (Phases 2 and 6, 2026-10-16). The 22 packages (23 games) are
> written in Nomos in [`games/`](../../games), each with its tests, and are played in the terminal
> (`gamehub play`), over the network and in the browser.
> The order is designed so that each wave forces **new engine capabilities** incrementally.

Legend: **Ch** = chance · **Hi** = hidden information · **Si** = simultaneity/windows.

## Wave 1 — Minimal engine and language (Phases 1–2)

| Game | Players | Ch | Hi | Si | What it tests |
|---|---|:-:|:-:|:-:|---|
| Tic-tac-toe (and *m,n,k*) | 2 | | | | Grid, lines, terminals, size parameters; **solving by minimax** |
| Rock-paper-scissors | 2 | | | ✓ | `simultaneous` node; mixed NE |
| Prisoner's dilemma (+ iterated) | 2 | | | ✓ | Parameters with `assert`; payoff table; the `repeat` combinator; Axelrod tournament |
| 2×2 family (matching pennies, chicken, stag hunt, battle of the sexes) | 2 | | | ✓ | One game parameterized by a matrix; variants with `extends` |
| Nim | 2 | | | | Heap parameters; **Sprague–Grundy** |
| Connect Four | 2 | | | | "Gravity", a larger state; alpha-beta with a heuristic |
| Kuhn poker | 2 | ✓ | ✓ | | Chance, private hands (bags), redacted views; **CFR** (value −1/18) |
| Leduc poker | 2 | ✓ | ✓ | | Two rounds, a public card; standard CFR benchmark |
| Dudo / *Liar's dice* | 2–4 | ✓ | ✓ | | Hidden dice, increasing bids, challenge; uses `std.dice` |
| **Bullshit** (*Mentiroso*) | 3–6 | ✓ | ✓ | ✓ | Bags, hidden action parameters (`subsets`), the "Bullshit!" **reaction window**, `reveal`. Brought forward from wave 2: it was already in IR |

Since Phase 4 every one of them can be played in the browser with the [generic UI](web-client.md)
(each package carries its `ui { … }` hints), and tic-tac-toe, Connect Four and Dudo also have a
**custom UI** (`games/<game>/ui`).

## Wave 2 — The requested games (Phase 6)

| Game | Package | Players | Ch | Hi | Si | What it tests |
|---|---|---|:-:|:-:|:-:|---|
| **Parchís** | [`parchis`](../../games/parchis) | 2–4 (pairs) | ✓ | | | Tracks with `std.boards`, safe squares, blockades, captures (+20), reaching home (+10), three sixes, chained bonuses |
| **Wizard** | [`wizard`](../../games/wizard) | 3–6 | ✓ | ✓ | | Tricks (`std.tricktaking`), bids, trump, wizards and jesters, rounds of 1 to 60/n cards |
| **Solitaire** (Klondike) | [`solitaire`](../../games/solitaire) | 1 | ✓ | ✓ | | Single player (POMDP), face-down cards in a list of zones, many actions |
| **Chess** | [`chess`](../../games/chess) | 2 | | | | Full legality (check, pins, castling, en passant, promotion), history (repetitions, 50/75 moves), **perft** |
| No-limit Texas Hold'em **poker** | [`texas-holdem`](../../games/texas-holdem) | 2–10 | ✓ | ✓ | | Betting rounds, minimum raises, **side pots** (`std.betting`), evaluator (`std.poker`, native plugin) |
| **Skat** | [`skat`](../../games/skat) | 3 (4 with the dealer sitting out) | ✓ | ✓ | | **Bidding** (*Reizen*), the skat, suit / Grand / Null, Hand, Schneider, Schwarz, Ouvert, matadors, overbidding |

Bullshit, the seventh requested game, arrived in wave 1. Chess, poker, Wizard and Parchís also have
a **custom UI** (`games/<game>/ui`); Skat and Solitaire are played with the generic UI.

Libraries that came out of this wave: `std.cards` (also `skat32()` and the Wizard deck,
`wizard60()`), `std.boards` (directions, rays and jumps within the board, tracks),
`std.tricktaking`, `std.bidding`, `std.betting` (pots and side pots) and `std.poker` (the value of
a hand, with a native WebAssembly plugin).

### Analysis sheets

`gamehub check` classification and tree size with Knuth's estimator (60 random walks; for trees
this large it is only an order of magnitude). With random agents.

| Game | Classification | States (Knuth) | Average steps | Average branching |
|---|---|---|---:|---:|
| Chess | 2 players, deterministic, perfect information, zero-sum | ~10⁷⁵⁷ | 350 | 21.9 |
| Skat (one deal, 3) | chance, imperfect information | ~10⁶¹ | 40 | 7.2 |
| Texas Hold'em (one hand, 2 / 6) | chance, imperfect information | ~10⁷⁹ / ~10⁸¹ | 4.8 / 9.2 | 74 / 34 |
| Wizard (3, full game / one round) | chance, imperfect information | ~10²⁰⁵⁰ / ~10⁸⁴ | 711 / 7 | 5.4 / 1.5 |
| Parchís (4) | chance, perfect information | ~10⁵¹⁷ | 663 | 2.5 |
| Solitaire (draw one) | 1 player, chance, imperfect information | ~10¹¹²⁷ | 1,000 (cap) | 8.1 |

Exact checks: **perft(5) = 4,865,609** from the initial position and the *perft* counts of
Kiwipete and positions 3 to 6 from the Chess Programming Wiki; Skat game values against the ISkO
examples.

## Wave 3 — Suggestions to extend the engine (later)

| Game | Why it is interesting |
|---|---|
| **Hanabi** | Cooperative with "inverted" information: you see everyone's cards **except your own** (`@visible(all - owner)`) |
| **Mus**, Brisca, Tute, Chinchón | Spanish deck; Mus adds **signals** (limited communication between partners) |
| Memory (Concentration) | A memory game → the bots' *recall* policy |
| Dobble / Snap / Jungle Speed | **Speed** games → `race` nodes with server timestamps |
| Backgammon | Chance + perfect information; doubling cube |
| Go 9×9 | The *ko* rule (history), area scoring |
| Checkers | Mandatory captures, multi-jumps as a compound action |
| Stratego, Battleship | Hidden identities; **secret simultaneous setup** |
| UNO | An "UNO!" window with a penalty |
| Blackjack | Player against the house (a fixed house policy) |
| Diplomacy, Codenames, Catan | Simultaneous orders, communication and negotiation |
| Ultimatum, Centipede, Public goods, Beauty contest (p-guess) | Classics of game theory/experimental economics, parameterizable |

## Chosen rules

- **Bullshit** (confirmed 2026-10-09): cards are placed face down in the center while declaring "3
  fours"; if you are called and it was a lie, you take the whole pile; if it was true, the caller
  takes it. Still to be confirmed ([question 9b](open-questions.md)): rank sequence, who may call,
  who continues after a call, and the deck. Dudo remains the dice version.
- Those of wave 2, with the recommendations of [question 9](open-questions.md)
  ([ADR-065](decisions.md)):
  - **Chess:** FIDE. Automatic draws by stalemate, insufficient material, fivefold repetition and
    75 moves; claimable by threefold repetition and 50 moves. Resigning and losing on time are up
    to the server (leaving, and the room's `forfeit` option).
  - **Skat:** ISkO, without Kontra or Ramsch (if everyone passes, the deal is not played);
    Seeger-Fabian as an option.
  - **Parchís:** Spanish rules; with two players, opposite colors; pairs as an option.
  - **Wizard:** Amigo's rules; the *hook* variant as an option.
  - **Poker:** no-limit Texas Hold'em with fixed blinds; Kuhn and Leduc remain as minimal versions
    for analysis.
  - **Solitaire:** Klondike (draw one or three, passes through the waste as an option, a move
    cap). FreeCell would be perfect information.

## Definition of a "finished" catalog game

1. Rules in `.game` with complete `meta` and a reviewed generated rulebook.
2. Scenario tests covering each special rule (and *perft* or equivalent where it exists).
3. 10⁵ random playouts without rule errors; declared invariants.
4. Playable in the generic UI; a custom UI is optional.
5. A reference bot (at least random + a heuristic one). *Today, only the random one: heuristic
   bots arrive with the `heuristic` blocks of Phase 9.*
6. An analysis sheet: classification, estimated size and whatever could be computed.
