# The Hub — "GitHub for games"

> Status: **design v0.1** (Phase 0). Local v0 (Phase 2), full web version (Phase 10).

## 1. Idea

Every game is a **git repository** with a `game.toml`. The hub **does not reinvent git**: it uses
it underneath (an embedded Forgejo/Gitea or any git host) and adds on top everything that
understands games: rendered rules, diagrams, matches, analyses, bots, interfaces and semantic
diffs.

## 2. Local-first flow (CLI)

```bash
gamehub new my-game --template cards           # creates a package with game.toml + .game + tests
gamehub check && gamehub test                  # verify
gamehub publish                                # uploads a version (semver) to the registry
gamehub clone juanma/wizard                    # = git clone + dependency resolution
gamehub fork juanma/wizard --as wizard-without-jesters
gamehub diff v1.2.0..main                      # semantic diff of the rules
gamehub host wizard --players 4                # play
```

Branches, commits and merges are plain git. `gamehub` adds the steps git does not know how to do.

## 3. Entities

| Entity | Description |
|---|---|
| Repository | A game or a **library** (reusable modules: decks, tricks, betting) |
| Version (release) | semver + **rules hash** + interface hash; immutable |
| Branch / fork | Variants and mods (git) |
| Proposal (PR) | A rules change with a textual, **semantic**, **visual** and **balance** diff |
| Match / replay | Tied to the exact rules hash |
| Bot | A published agent, with ratings per rules version |
| Analysis | A cached result (Nash, tree, metrics) indexed by rules hash |
| Interface (Pages) | A static UI hosted by the hub, compatible with an interface hash |

## 4. A game's page

`Rules` (generated rulebook + interactive diagram) · `Code` · **`Play`** (create a room with one
click) · `Analysis` (classification, size, equilibria when feasible) · `Bots` (arena ranking) ·
`Interfaces` (compatible UIs) · `Variants` (the game's **family tree**: forks and ancestors, e.g.
Whist → Oh Hell → Wizard) · `Matches` · `Issues` · `Proposals`.

## 5. Semantic diff and "Balance CI"

A rules PR is reviewed in four layers:

1. **Text diff** (plain git).
2. **Semantic IR diff:** "action `bid`: domain `0..round` → `0..round+1`", "node
   `DealerChoosesTrump` removed", "payoff of `Exact`: `20+10·w` → `30+10·w`".
3. **Visual diff:** the diagram with added/removed/modified nodes and arrows colored.
4. **Behavioral diff (Balance CI):** the same set of bots plays N matches with each version and
   the metrics are compared: advantage per seat, length, draw rate, rule coverage, the gap between
   strong and random bots (skill vs. luck)… Just like a performance CI, but for game design.

## 6. Automatic versioning

By comparing the **interface hash** between versions, the hub detects changes that are
incompatible for UIs and bots (e.g. a new action with different parameters) and **requires a
major version bump**. Rules changes that do not touch the interface are *minor*; cosmetic ones,
*patch*.

## 7. Dependencies

`game.toml` declares dependencies (`std = ">=0.3, <0.4"`, `juanma/tricktaking = "^1.2"`);
`game.lock` pins versions and hashes. Cargo/npm-style resolution.

```toml
[game]
id = "wizard"
version = "1.0.0"
authors = ["…"]
license = "CC-BY-4.0"
players = "3..6"
tags = ["cards", "tricks", "bidding"]

[dependencies]
std = ">=0.3, <0.4"
```

## 8. Search by mathematical properties

Since every game is classified automatically, you can search for: *"2 players, zero-sum, perfect
information, branching < 10"*, *"cooperative games with hidden information"*, *"trick-taking games
for 4 with teams"*. Author tags + derived properties + estimated size.

## 9. Hosted matches and community

Online rooms with codes, matchmaking, human ratings per game/version, tournaments, profiles,
organizations (clubs, courses), stars, followers.

## 10. Intellectual property (note)

A game's mechanics are usually treated as unprotectable ideas, but **the text of a rulebook, the
art and the trademarks are protected** (e.g. trade names of published games). The official
catalog should use rules written by us, our own art and, where needed, generic names. A legal
review is advisable before opening the hub to the public.

## 11. Stages

| Stage | Contents |
|---|---|
| **v0** (Phase 2) | `game.toml`, dependencies, `clone`/`fork` over git URLs, semantic `diff` in the CLI |
| **v1** (Phase 10) | Web: accounts, repos, explore, game page, play, publish, registry |
| **v2** (Phases 10–12) | PRs with semantic/visual/balance diffs, arena, Pages, search by properties, family tree |
