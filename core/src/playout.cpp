// SPDX-License-Identifier: Apache-2.0
#include "gamehub/playout.hpp"

#include <chrono>

#include "gamehub/errors.hpp"

namespace gh {

namespace {

constexpr ApplyOptions LEAN{false, false, false};

}  // namespace

State random_playout(const Game& game, int n, const Json& params, uint64_t seed, int max_steps,
                     uint64_t& steps, bool& truncated) {
  State state = game.new_state(n, params, LEAN);
  Pcg32 chance(seed, STREAM_CHANCE);
  std::vector<Pcg32> agents;
  for (int s = 0; s < n; ++s) agents.emplace_back(seed, STREAM_AGENT_BASE + static_cast<uint64_t>(s));
  steps = 0;
  truncated = false;
  std::vector<Action> legal;
  while (!state.is_terminal()) {
    if (steps >= static_cast<uint64_t>(max_steps)) {
      truncated = true;
      return state;
    }
    if (state.status() == Status::Chance) {
      Outcome o = state.sample_chance(chance);
      state = state.apply_chance(o, LEAN);
    } else {
      int seat = state.active_seats().front();
      legal.clear();
      state.for_each_legal(seat, [&](const Action& a) {
        legal.push_back(a);
        return true;
      });
      const Action& a = legal[agents[static_cast<size_t>(seat)].below(legal.size())];
      state = state.apply_action(seat, a, LEAN);
    }
    ++steps;
  }
  return state;
}

PlayoutReport random_playouts(const Game& game, int n, const Json& params, uint64_t seed,
                              uint64_t games, int max_steps) {
  PlayoutReport report;
  report.payoff_sums.assign(static_cast<size_t>(n), Rational::integer(0));
  auto started = std::chrono::steady_clock::now();
  for (uint64_t i = 0; i < games; ++i) {
    uint64_t match_seed = seed + i;
    ++report.games;
    uint64_t steps = 0;
    bool truncated = false;
    try {
      State final = random_playout(game, n, params, match_seed, max_steps, steps, truncated);
      report.steps += steps;
      uint64_t h = mix64(match_seed ^ (steps << 20));
      if (truncated) {
        ++report.truncated;
        report.fingerprint ^= h;
        continue;
      }
      ++report.completed;
      for (size_t s = 0; s < final.payoffs().size(); ++s) {
        report.payoff_sums[s] = report.payoff_sums[s] + final.payoffs()[s].as_rational();
        h ^= positional_hash(s, hash_value(final.payoffs()[s]));
      }
      report.fingerprint ^= mix64(h);
    } catch (const RuleError& e) {
      report.errors.emplace_back(match_seed, e.what());
    }
  }
  report.seconds =
      std::chrono::duration<double>(std::chrono::steady_clock::now() - started).count();
  return report;
}

}  // namespace gh
