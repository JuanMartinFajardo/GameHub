// SPDX-License-Identifier: Apache-2.0
#include "gamehub/playout.hpp"

#include <algorithm>
#include <chrono>

#include "gamehub/errors.hpp"

namespace gh {

namespace {

constexpr ApplyOptions LEAN{false, false, false};

}  // namespace

State random_playout(const Game& game, int n, const Json& params, uint64_t seed, int max_steps,
                     uint64_t& steps, bool& truncated) {
  std::vector<Action> scratch;
  return random_playout(game, n, params, seed, max_steps, steps, truncated, scratch);
}

State random_playout(const Game& game, int n, const Json& params, uint64_t seed, int max_steps,
                     uint64_t& steps, bool& truncated, std::vector<Action>& legal) {
  State state = game.new_state(n, params, LEAN);
  Pcg32 chance(seed, STREAM_CHANCE);
  std::vector<Pcg32> agents;
  for (int s = 0; s < n; ++s) agents.emplace_back(seed, STREAM_AGENT_BASE + static_cast<uint64_t>(s));
  steps = 0;
  truncated = false;
  while (!state.is_terminal()) {
    if (steps >= static_cast<uint64_t>(max_steps)) {
      truncated = true;
      return state;
    }
    if (state.status() == Status::Chance) {
      state = state.sample_and_apply(chance, LEAN);
    } else {
      int seat = state.first_active();
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
  std::vector<Action> scratch;
  scratch.reserve(64);
  for (uint64_t i = 0; i < games; ++i) {
    uint64_t match_seed = seed + i;
    ++report.games;
    uint64_t steps = 0;
    bool truncated = false;
    try {
      State final =
          random_playout(game, n, params, match_seed, max_steps, steps, truncated, scratch);
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

namespace {

void add_step(CoverageReport& r, const State& state, const std::vector<const TransitionDef*>& trace,
              const Action* action, int node) {
  const GameDef& g = state.game();
  Json events = state.events(NO_SEAT);
  for (const auto& e : events.as_array()) {
    const Json* type = e.find("type");
    if (type != nullptr && type->is_string() && type->as_string() == "node") {
      ++r.nodes[e["node"].as_string()];
    }
  }
  for (const TransitionDef* t : trace) {
    std::string key;
    for (const auto& part : t->key) {
      if (!key.empty()) key += '/';
      key += part;
    }
    ++r.transitions[key];
  }
  if (action != nullptr && node >= 0 && action->name(g) != "pass") {
    ++r.actions[g.node(node).id + "." + action->name(g)];
  }
}

// Pone y quita el rastro de transiciones del hilo.
struct TraceScope {
  explicit TraceScope(std::vector<const TransitionDef*>* trace) { set_transition_trace(trace); }
  ~TraceScope() { set_transition_trace(nullptr); }
};

}  // namespace

CoverageReport coverage_playouts(const Game& game, int n, const Json& params, uint64_t seed,
                                 uint64_t games, int max_steps, double time_limit) {
  CoverageReport r;
  r.totals.assign(static_cast<size_t>(n), Rational::integer(0));
  r.wins.assign(static_cast<size_t>(n), 0);
  auto started = std::chrono::steady_clock::now();
  auto elapsed = [&] {
    return std::chrono::duration<double>(std::chrono::steady_clock::now() - started).count();
  };
  std::vector<const TransitionDef*> trace;
  TraceScope scope(&trace);
  for (uint64_t g = 0; g < games; ++g) {
    if (time_limit > 0 && elapsed() > time_limit) break;
    ++r.games;
    Pcg32 chance(seed + g, STREAM_CHANCE);
    Pcg32 agents(seed + g, STREAM_AGENT_BASE);
    trace.clear();
    try {
      State state = game.new_state(n, params);
      add_step(r, state, trace, nullptr, -1);
      uint64_t steps = 0;
      while (!state.is_terminal() && steps < static_cast<uint64_t>(max_steps)) {
        trace.clear();
        if (state.status() == Status::Chance) {
          Outcome o = state.sample_chance(chance);
          state = state.apply_chance(o);
          add_step(r, state, trace, nullptr, -1);
        } else {
          int seat = state.first_active();
          std::vector<Action> legal = state.legal_actions(seat);
          Action action = legal[agents.below(legal.size())];
          int node = state.node();
          state = state.apply_action(seat, action);
          add_step(r, state, trace, &action, node);
        }
        ++steps;
      }
      if (!state.is_terminal()) {
        ++r.truncated;
        continue;
      }
      ++r.finished;
      r.lengths.push_back(steps);
      const ValueVec& payoffs = state.payoffs();
      for (size_t s = 0; s < payoffs.size() && s < r.totals.size(); ++s) {
        r.totals[s] = r.totals[s] + payoffs[s].as_rational();
      }
      auto ranking = state.ranking();
      std::vector<int> ranks = ranking ? *ranking : std::vector<int>{};
      bool all_first = !ranks.empty() &&
                       std::all_of(ranks.begin(), ranks.end(), [](int x) { return x == 1; });
      if (all_first) {
        ++r.draws;
      } else {
        for (size_t s = 0; s < ranks.size() && s < r.wins.size(); ++s) {
          if (ranks[s] == 1) ++r.wins[s];
        }
      }
    } catch (const RuleError& e) {
      if (r.errors.size() < 20) r.errors.emplace_back(g, e.what());
    }
  }
  r.seconds = elapsed();
  return r;
}

}  // namespace gh
