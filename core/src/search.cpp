// SPDX-License-Identifier: Apache-2.0
#include "gamehub/search.hpp"

#include <algorithm>
#include <cmath>
#include <deque>
#include <memory>

#include "gamehub/errors.hpp"

namespace gh {

// --- Claves ------------------------------------------------------------------------------------

StateKey state_key(const State& s) {
  const StateNode& d = s.data();
  StateKey k;
  k.a = s.hash();
  uint64_t b = mix64(0x6b65793273ULL ^ static_cast<uint64_t>(d.node + 3));
  for (size_t i = 0; i < d.store.size(); ++i) {
    b ^= mix64(hash_value2(d.store[i]) + 0x9e3779b97f4a7c15ULL * (i + 11));
  }
  if (d.pending) {
    uint64_t p = 0x70656e6432ULL;
    for (int seat : d.pending->order) p = mix64(p + static_cast<uint64_t>(seat) + 1);
    for (const auto& [seat, a] : d.pending->submitted) {
      p = mix64(p ^ (static_cast<uint64_t>(seat) << 40) ^ a.hash());
    }
    b ^= p;
  }
  if (d.terminal) {
    for (size_t i = 0; i < d.payoffs.size(); ++i) {
      b ^= mix64(hash_value2(d.payoffs[i]) + 977 * (i + 1));
    }
  }
  k.b = b;
  return k;
}

// --- Perft -------------------------------------------------------------------------------------

namespace {

bool skipped(const State& s, const Action& a, const std::vector<std::string>& skip) {
  if (skip.empty()) return false;
  const std::string& name = a.name(s.game());
  return std::find(skip.begin(), skip.end(), name) != skip.end();
}

std::vector<Action> moves(const State& s, const std::vector<std::string>& skip) {
  std::vector<Action> out;
  s.for_each_legal(s.first_active(), [&](const Action& a) {
    if (!skipped(s, a, skip)) out.push_back(a);
    return true;
  });
  return out;
}

}  // namespace

uint64_t perft(const State& s, int depth, const std::vector<std::string>& skip) {
  if (s.is_terminal()) return 0;
  if (s.status() == Status::Chance) {
    uint64_t total = 0;
    for (const auto& [o, p] : s.chance_outcomes()) total += perft(s.apply_chance(o, SEARCH), depth, skip);
    return total;
  }
  if (depth == 0) return 1;
  int seat = s.first_active();
  if (depth == 1) {
    uint64_t count = 0;
    s.for_each_legal(seat, [&](const Action& a) {
      if (!skipped(s, a, skip)) ++count;
      return true;
    });
    return count;
  }
  uint64_t total = 0;
  for (const auto& a : moves(s, skip)) total += perft(s.apply_action(seat, a, SEARCH), depth - 1, skip);
  return total;
}

std::vector<std::pair<Action, uint64_t>> perft_divide(const State& s, int depth,
                                                      const std::vector<std::string>& skip) {
  std::vector<std::pair<Action, uint64_t>> out;
  int seat = s.first_active();
  for (const auto& a : moves(s, skip)) {
    out.emplace_back(a, perft(s.apply_action(seat, a, SEARCH), depth - 1, skip));
  }
  return out;
}

// --- Alfa-beta ---------------------------------------------------------------------------------

namespace {

// Un valor con ±∞ (las cotas iniciales de la ventana).
struct Ext {
  int8_t inf = 0;  // -1 = -∞, 1 = +∞
  Rational r;
  static Ext minus() { return Ext{-1, {}}; }
  static Ext plus() { return Ext{1, {}}; }
  static Ext of(const Rational& x) { return Ext{0, x}; }
  int compare(const Ext& o) const {
    if (inf != 0 || o.inf != 0) return (inf > o.inf) - (inf < o.inf);
    return r.compare(o.r);
  }
};

enum Flag : uint8_t { EXACT, LOWER, UPPER };

struct Entry {
  Rational v;
  Flag flag;
  int32_t hint;
};

class Search {
 public:
  explicit Search(uint64_t max_nodes) : max_nodes_(max_nodes) {}

  Rational value(const State& s, Ext alpha, Ext beta) {
    if (s.is_terminal()) return terminal(s);
    StateKey key = state_key(s);
    int32_t hint = -1;
    auto found = table.find(key);
    if (found != table.end()) {
      const Entry& e = found->second;
      hint = e.hint;
      Ext v = Ext::of(e.v);
      if (e.flag == EXACT) return e.v;
      if (e.flag == LOWER && v.compare(beta) >= 0) return e.v;
      if (e.flag == UPPER && v.compare(alpha) <= 0) return e.v;
    }
    if (++nodes > max_nodes_) throw EngineError("la búsqueda alfa-beta supera el límite de nodos");
    if (s.status() == Status::Chance) {
      Rational v = Rational::integer(0);
      for (const auto& [o, p] : s.chance_outcomes()) {
        v = v + p * value(s.apply_chance(o, SEARCH), Ext::minus(), Ext::plus());
      }
      table[key] = Entry{v, EXACT, -1};
      return v;
    }
    int seat = s.first_active();
    std::vector<Action> actions = s.legal_actions(seat);
    std::vector<size_t> order(actions.size());
    for (size_t k = 0; k < order.size(); ++k) order[k] = k;
    if (hint >= 0 && static_cast<size_t>(hint) < actions.size()) {
      order.erase(order.begin() + hint);
      order.insert(order.begin(), static_cast<size_t>(hint));
    }
    bool maximizing = seat == 0;
    Ext a0 = alpha, b0 = beta;
    Ext best = maximizing ? Ext::minus() : Ext::plus();
    size_t best_index = order.front();
    for (size_t k : order) {
      Ext v = Ext::of(value(s.apply_action(seat, actions[k], SEARCH), alpha, beta));
      if ((maximizing && v.compare(best) > 0) || (!maximizing && v.compare(best) < 0)) {
        best = v;
        best_index = k;
      }
      if (maximizing) {
        if (v.compare(alpha) > 0) alpha = v;
      } else if (v.compare(beta) < 0) {
        beta = v;
      }
      if (alpha.compare(beta) >= 0) break;
    }
    Flag flag = EXACT;
    if (best.compare(a0) <= 0) {
      flag = UPPER;
    } else if (best.compare(b0) >= 0) {
      flag = LOWER;
    }
    table[key] = Entry{best.r, flag, static_cast<int32_t>(best_index)};
    return best.r;
  }

  std::unordered_map<StateKey, Entry, StateKeyHash> table;
  std::optional<Rational> total;
  uint64_t nodes = 0;

 private:
  Rational terminal(const State& s) {
    Rational sum = Rational::integer(0);
    for (const auto& p : s.payoffs()) sum = sum + p.as_rational();
    if (!total) {
      total = sum;
    } else if (!(sum == *total)) {
      throw EngineError("los pagos de los finales no suman siempre lo mismo");
    }
    return s.payoffs().at(0).as_rational();
  }
  uint64_t max_nodes_;
};

}  // namespace

AlphaBetaResult alphabeta(const State& root, uint64_t max_nodes) {
  if (root.num_players() != 2) throw EngineError("alfa-beta es para dos jugadores");
  Search search(max_nodes);
  AlphaBetaResult r;
  r.value = search.value(root, Ext::minus(), Ext::plus());
  if (root.status() == Status::Decision) {
    int seat = root.first_active();
    std::vector<Action> actions = root.legal_actions(seat);
    for (size_t k = 0; k < actions.size(); ++k) {
      Rational v = search.value(root.apply_action(seat, actions[k], SEARCH), Ext::minus(),
                                Ext::plus());
      if (v == r.value) r.best.push_back(k);
    }
  }
  // Variación principal: las jugadas de la tabla y, en el azar, el resultado más probable.
  State s = root;
  std::unordered_map<StateKey, bool, StateKeyHash> seen;
  while (!s.is_terminal()) {
    StateKey key = state_key(s);
    if (seen.count(key)) break;
    seen[key] = true;
    if (s.status() == Status::Chance) {
      auto outcomes = s.chance_outcomes();
      size_t best = 0;
      for (size_t k = 1; k < outcomes.size(); ++k) {
        if (outcomes[k].second.compare(outcomes[best].second) > 0) best = k;
      }
      r.pv.push_back("chance:" + std::to_string(best));
      s = s.apply_chance(outcomes[best].first, SEARCH);
      continue;
    }
    auto found = search.table.find(key);
    if (found == search.table.end() || found->second.hint < 0) break;
    int seat = s.first_active();
    std::vector<Action> actions = s.legal_actions(seat);
    r.pv.push_back("action:" + std::to_string(found->second.hint));
    s = s.apply_action(seat, actions[static_cast<size_t>(found->second.hint)], SEARCH);
  }
  r.total = search.total.value_or(Rational::integer(0));
  r.states = search.table.size();
  r.nodes = search.nodes;
  return r;
}

// --- MCTS --------------------------------------------------------------------------------------

namespace {

struct TreeNode {
  State state;
  std::vector<Action> actions;  // decisión: las legales
  std::vector<std::unique_ptr<TreeNode>> children;
  std::vector<std::pair<Outcome, std::unique_ptr<TreeNode>>> chance;  // azar: por resultado
  uint64_t visits = 0;
  std::vector<double> sums;  // pago acumulado de cada asiento
  bool expanded = false;
};

std::vector<double> payoffs_of(const State& s) {
  std::vector<double> out;
  for (const auto& p : s.payoffs()) {
    Rational r = p.as_rational();
    out.push_back(static_cast<double>(r.num) / static_cast<double>(r.den));
  }
  return out;
}

std::vector<double> rollout(State s, Pcg32& rng, int max_steps) {
  std::vector<Action> legal;
  for (int step = 0; step < max_steps && !s.is_terminal(); ++step) {
    if (s.status() == Status::Chance) {
      s = s.sample_and_apply(rng, SEARCH);
      continue;
    }
    int seat = s.first_active();
    legal.clear();
    s.for_each_legal(seat, [&](const Action& a) {
      legal.push_back(a);
      return true;
    });
    s = s.apply_action(seat, legal[rng.below(legal.size())], SEARCH);
  }
  if (!s.is_terminal()) return std::vector<double>(static_cast<size_t>(s.num_players()), 0.0);
  return payoffs_of(s);
}

}  // namespace

MctsResult mcts(const State& root_state, uint64_t simulations, double c, uint64_t seed,
                int max_rollout) {
  if (root_state.status() != Status::Decision) throw EngineError("MCTS empieza en una decisión");
  int n = root_state.num_players();
  Pcg32 rng(seed, 77);
  TreeNode root{root_state, {}, {}, {}, 0, std::vector<double>(static_cast<size_t>(n), 0.0)};
  for (uint64_t sim = 0; sim < simulations; ++sim) {
    std::vector<TreeNode*> path{&root};
    TreeNode* node = &root;
    std::vector<double> result;
    while (true) {
      const State& s = node->state;
      if (s.is_terminal()) {
        result = payoffs_of(s);
        break;
      }
      if (s.status() == Status::Chance) {
        // Azar muestreado: un hijo por resultado distinto.
        Outcome o = s.sample_chance(rng);
        TreeNode* child = nullptr;
        for (auto& [out, ptr] : node->chance) {
          if (out == o) child = ptr.get();
        }
        if (child == nullptr) {
          auto fresh = std::make_unique<TreeNode>();
          fresh->state = s.apply_chance(o, SEARCH);
          fresh->sums.assign(static_cast<size_t>(n), 0.0);
          child = fresh.get();
          node->chance.emplace_back(o, std::move(fresh));
        }
        node = child;
        path.push_back(node);
        continue;
      }
      if (!node->expanded) {
        node->actions = s.legal_actions(s.first_active());
        node->children.resize(node->actions.size());
        node->expanded = true;
      }
      // UCT: primero las no visitadas, en orden; si no, el máximo de la cota superior.
      int seat = s.first_active();
      size_t pick = node->actions.size();
      for (size_t k = 0; k < node->actions.size(); ++k) {
        if (!node->children[k]) {
          pick = k;
          break;
        }
      }
      if (pick < node->actions.size()) {
        auto fresh = std::make_unique<TreeNode>();
        fresh->state = s.apply_action(seat, node->actions[pick], SEARCH);
        fresh->sums.assign(static_cast<size_t>(n), 0.0);
        node->children[pick] = std::move(fresh);
        node = node->children[pick].get();
        path.push_back(node);
        result = rollout(node->state, rng, max_rollout);
        break;
      }
      double best = -INFINITY;
      double log_n = std::log(static_cast<double>(node->visits));
      for (size_t k = 0; k < node->actions.size(); ++k) {
        const TreeNode& ch = *node->children[k];
        double q = ch.sums[static_cast<size_t>(seat)] / static_cast<double>(ch.visits);
        double u = q + c * std::sqrt(log_n / static_cast<double>(ch.visits));
        if (u > best) {
          best = u;
          pick = k;
        }
      }
      node = node->children[pick].get();
      path.push_back(node);
    }
    for (TreeNode* p : path) {
      ++p->visits;
      for (size_t k = 0; k < result.size(); ++k) p->sums[k] += result[k];
    }
  }
  MctsResult r;
  r.actions = root.actions;
  r.simulations = simulations;
  int seat = root_state.first_active();
  uint64_t most = 0;
  for (size_t k = 0; k < root.children.size(); ++k) {
    const auto& ch = root.children[k];
    uint64_t v = ch ? ch->visits : 0;
    r.visits.push_back(v);
    r.values.push_back(v ? ch->sums[static_cast<size_t>(seat)] / static_cast<double>(v) : 0.0);
    if (v > most) {
      most = v;
      r.best = k;
    }
  }
  return r;
}

// --- Análisis retrógrado -----------------------------------------------------------------------

RetroResult retrograde(const State& root, uint64_t max_positions) {
  if (root.num_players() != 2) throw EngineError("el análisis retrógrado es para dos jugadores");
  std::unordered_map<StateKey, uint32_t, StateKeyHash> index;
  std::vector<State> states;
  std::vector<std::vector<uint32_t>> children, parents;
  std::deque<uint32_t> frontier;
  index[state_key(root)] = 0;
  states.push_back(root);
  frontier.push_back(0);
  while (!frontier.empty()) {
    uint32_t i = frontier.front();
    frontier.pop_front();
    State s = states[i];
    children.resize(states.size());
    if (s.is_terminal()) continue;
    if (s.status() == Status::Chance) {
      throw EngineError("el análisis retrógrado es para juegos sin azar");
    }
    int seat = s.first_active();
    std::vector<uint32_t> kids;
    s.for_each_legal(seat, [&](const Action& a) {
      State child = s.apply_action(seat, a, SEARCH);
      StateKey key = state_key(child);
      auto [it, fresh] = index.emplace(key, static_cast<uint32_t>(states.size()));
      if (fresh) {
        if (states.size() >= max_positions) {
          throw EngineError("el análisis retrógrado supera el límite de posiciones");
        }
        states.push_back(child);
        frontier.push_back(it->second);
      }
      kids.push_back(it->second);
      return true;
    });
    children.resize(states.size());
    children[i] = std::move(kids);
  }
  size_t count = states.size();
  children.resize(count);
  parents.assign(count, {});
  for (uint32_t i = 0; i < count; ++i) {
    for (uint32_t c : children[i]) parents[c].push_back(i);
  }
  // Valores para el asiento 0 (1, 0, -1); 2 = sin etiquetar.
  std::vector<int8_t> value(count, 2);
  std::vector<int> depth(count, 0);
  std::vector<int> remaining(count, 0);
  std::deque<uint32_t> queue;
  for (uint32_t i = 0; i < count; ++i) {
    const State& s = states[i];
    if (s.is_terminal()) {
      Rational a = s.payoffs()[0].as_rational(), b = s.payoffs()[1].as_rational();
      int c = a.compare(b);
      value[i] = static_cast<int8_t>(c);
      queue.push_back(i);
    } else {
      remaining[i] = static_cast<int>(children[i].size());
    }
  }
  while (!queue.empty()) {
    uint32_t c = queue.front();
    queue.pop_front();
    for (uint32_t p : parents[c]) {
      if (value[p] != 2) continue;
      int mover = states[p].first_active();
      int good = mover == 0 ? 1 : -1;  // lo que quiere quien decide en p
      if (value[c] == good) {
        value[p] = static_cast<int8_t>(good);
        depth[p] = depth[c] + 1;
        queue.push_back(p);
      } else if (--remaining[p] == 0) {
        // Todas las jugadas ya tienen valor y ninguna gana: lo mejor que queda.
        int8_t best = static_cast<int8_t>(-good);
        int d = 0;
        for (uint32_t k : children[p]) {
          if ((good == 1 && value[k] > best) || (good == -1 && value[k] < best)) best = value[k];
          d = std::max(d, depth[k] + 1);
        }
        value[p] = best;
        depth[p] = d;
        queue.push_back(p);
      }
    }
  }
  RetroResult r;
  r.positions = count;
  for (uint32_t i = 0; i < count; ++i) {
    int8_t v = value[i] == 2 ? 0 : value[i];  // sin etiquetar = tablas por repetición
    if (states[i].is_terminal()) continue;
    int mover = states[i].first_active();
    int mine = mover == 0 ? v : -v;
    if (mine > 0) {
      ++r.wins;
    } else if (mine < 0) {
      ++r.losses;
    } else {
      ++r.draws;
    }
  }
  int8_t v0 = value[0] == 2 ? 0 : value[0];
  if (root.is_terminal()) {
    r.outcome = v0;
  } else {
    r.outcome = root.first_active() == 0 ? v0 : -v0;
  }
  r.depth = depth[0];
  return r;
}

}  // namespace gh
