// SPDX-License-Identifier: Apache-2.0
#include "gamehub/cfr.hpp"

#include <functional>
#include <unordered_map>

#include "gamehub/errors.hpp"
#include "gamehub/search.hpp"
#include "gamehub/sha256.hpp"

namespace gh {

namespace {

double to_double(const Rational& r) {
  return static_cast<double>(r.num) / static_cast<double>(r.den);
}

std::string observe(const State& s, int seat) {
  return Json(JsonObject{{"view", s.view(seat)}, {"events", s.events(seat)}}).dump();
}

struct TreeFrame {
  State state;
  int parent;
  double prob;  // < 0 = no es hijo de un nodo de azar
  std::vector<Sha256> keys;
};

}  // namespace

GameTreeEF build_tree(const State& root, size_t max_nodes, size_t chance_limit) {
  GameTreeEF tree;
  int n = root.num_players();
  tree.num_players = n;
  std::unordered_map<std::string, int> by_key;  // asiento + clave → conjunto
  std::vector<std::vector<Action>> set_actions;
  ApplyOptions full;  // con eventos e historial: las observaciones los necesitan
  full.history = false;
  std::vector<Sha256> root_keys(static_cast<size_t>(n));
  for (int s = 0; s < n; ++s) root_keys[static_cast<size_t>(s)].update(observe(root, s));
  std::vector<TreeFrame> stack;
  stack.push_back(TreeFrame{root, -1, -1.0, std::move(root_keys)});
  auto extend = [&](const std::vector<Sha256>& keys, const State& child) {
    std::vector<Sha256> out = keys;
    for (int s = 0; s < n; ++s) out[static_cast<size_t>(s)].update(observe(child, s));
    return out;
  };
  while (!stack.empty()) {
    TreeFrame f = std::move(stack.back());
    stack.pop_back();
    auto index = static_cast<uint32_t>(tree.nodes.size());
    if (index >= max_nodes) throw EngineError("el árbol del juego supera el límite de nodos");
    tree.nodes.emplace_back();
    if (f.parent >= 0) {
      TreeNodeEF& up = tree.nodes[static_cast<size_t>(f.parent)];
      up.children.push_back(index);
      if (f.prob >= 0) up.probs.push_back(f.prob);
    }
    const State& state = f.state;
    std::vector<TreeFrame> children;
    if (state.is_terminal()) {
      TreeNodeEF& node = tree.nodes.back();
      for (const auto& p : state.payoffs()) node.payoffs.push_back(to_double(p.as_rational()));
      continue;
    }
    if (state.status() == Status::Chance) {
      tree.nodes.back().kind = TreeNodeEF::Kind::Chance;
      // Resultados que llevan al mismo estado con los mismos eventos: uno solo.
      std::vector<std::pair<State, Rational>> merged;
      std::unordered_map<std::string, size_t> where;
      for (const auto& [o, p] : state.chance_outcomes(chance_limit)) {
        State child = state.apply_chance(o, full);
        std::string key = child.snapshot_text() + "|" + child.events(NO_SEAT).dump();
        auto it = where.find(key);
        if (it == where.end()) {
          where[key] = merged.size();
          merged.emplace_back(child, p);
        } else {
          merged[it->second].second = merged[it->second].second + p;
        }
      }
      for (auto& [child, p] : merged) {
        children.push_back(TreeFrame{child, static_cast<int>(index), to_double(p), extend(f.keys, child)});
      }
    } else {
      int seat = state.first_active();
      std::vector<Action> actions = state.legal_actions(seat);
      Sha256 copy = f.keys[static_cast<size_t>(seat)];
      std::string key = std::to_string(seat) + ":" + copy.hexdigest();
      auto it = by_key.find(key);
      int sid;
      if (it == by_key.end()) {
        sid = static_cast<int>(tree.infosets.size());
        by_key[key] = sid;
        InfoSetEF info;
        info.player = seat;
        info.key = key.substr(key.find(':') + 1);
        info.actions = actions.size();
        tree.infosets.push_back(std::move(info));
        set_actions.push_back(actions);
      } else {
        sid = it->second;
        if (!(set_actions[static_cast<size_t>(sid)] == actions)) {
          throw EngineError("el asiento " + std::to_string(seat) +
                            " tiene acciones legales distintas en estados que no puede distinguir");
        }
      }
      tree.infosets[static_cast<size_t>(sid)].nodes.push_back(index);
      TreeNodeEF& node = tree.nodes.back();
      node.kind = TreeNodeEF::Kind::Decision;
      node.player = seat;
      node.infoset = sid;
      for (const auto& action : actions) {
        State child = state.apply_action(seat, action, full);
        children.push_back(TreeFrame{child, static_cast<int>(index), -1.0, extend(f.keys, child)});
      }
    }
    for (auto it = children.rbegin(); it != children.rend(); ++it) stack.push_back(std::move(*it));
  }
  return tree;
}

// --- CFR ---------------------------------------------------------------------------------------

CfrSolver::CfrSolver(const GameTreeEF& tree, bool plus) : tree_(tree), plus_(plus) {
  for (const auto& s : tree.infosets) {
    regret_.emplace_back(s.actions, 0.0);
    strategy_sum_.emplace_back(s.actions, 0.0);
  }
  sigma_.resize(tree.infosets.size());
}

void CfrSolver::current_all() {
  for (size_t i = 0; i < regret_.size(); ++i) {
    const auto& r = regret_[i];
    std::vector<double>& out = sigma_[i];
    out.assign(r.size(), 0.0);
    double total = 0.0;
    for (double x : r) total += x > 0 ? x : 0.0;
    if (total > 0) {
      for (size_t a = 0; a < r.size(); ++a) out[a] = (r[a] > 0 ? r[a] : 0.0) / total;
    } else {
      for (size_t a = 0; a < r.size(); ++a) out[a] = 1.0 / static_cast<double>(r.size());
    }
  }
}

double CfrSolver::traverse(uint32_t h, int player, double pi_i, double pi_o) {
  const TreeNodeEF& node = tree_.nodes[h];
  switch (node.kind) {
    case TreeNodeEF::Kind::Terminal:
      return node.payoffs[static_cast<size_t>(player)];
    case TreeNodeEF::Kind::Chance: {
      double v = 0.0;
      for (size_t k = 0; k < node.children.size(); ++k) {
        double p = node.probs[k];
        v += p * traverse(node.children[k], player, pi_i, pi_o * p);
      }
      return v;
    }
    case TreeNodeEF::Kind::Decision:
      break;
  }
  auto info = static_cast<size_t>(node.infoset);
  const std::vector<double>& strategy = sigma_[info];
  if (node.player != player) {
    double v = 0.0;
    for (size_t k = 0; k < node.children.size(); ++k) {
      double q = strategy[k];
      if (q > 0) v += q * traverse(node.children[k], player, pi_i, pi_o * q);
    }
    return v;
  }
  std::vector<double> values(node.children.size());
  for (size_t k = 0; k < node.children.size(); ++k) {
    values[k] = traverse(node.children[k], player, pi_i * strategy[k], pi_o);
  }
  double v = 0.0;
  for (size_t k = 0; k < values.size(); ++k) v += strategy[k] * values[k];
  std::vector<double>& regret = regret_[info];
  for (size_t a = 0; a < values.size(); ++a) regret[a] += pi_o * (values[a] - v);
  double weight = pi_i * (plus_ ? iteration_ : 1);
  if (weight != 0.0) {
    std::vector<double>& acc = strategy_sum_[info];
    for (size_t a = 0; a < strategy.size(); ++a) acc[a] += weight * strategy[a];
  }
  return v;
}

void CfrSolver::run(int iterations, int measure_every) {
  for (int k = 0; k < iterations; ++k) {
    ++iteration_;
    for (int player = 0; player < tree_.num_players; ++player) {
      current_all();
      traverse(0, player, 1.0, 1.0);
      if (plus_) {
        for (size_t i = 0; i < tree_.infosets.size(); ++i) {
          if (tree_.infosets[i].player != player) continue;
          for (double& r : regret_[i]) r = r > 0 ? r : 0.0;
        }
      }
    }
    if (measure_every > 0 && (iteration_ % measure_every == 0 || k + 1 == iterations)) {
      convergence_.emplace_back(iteration_, exploitability(tree_, average()));
    }
  }
}

PolicyEF CfrSolver::average() const {
  PolicyEF out;
  for (const auto& acc : strategy_sum_) {
    double total = 0.0;
    for (double x : acc) total += x;
    std::vector<double> probs(acc.size());
    for (size_t a = 0; a < acc.size(); ++a) {
      probs[a] = total > 0 ? acc[a] / total : 1.0 / static_cast<double>(acc.size());
    }
    out.push_back(std::move(probs));
  }
  return out;
}

// --- Mejor respuesta y explotabilidad ----------------------------------------------------------

std::vector<double> expected_values(const GameTreeEF& tree, const PolicyEF& policy) {
  std::vector<double> totals(static_cast<size_t>(tree.num_players), 0.0);
  std::vector<std::pair<uint32_t, double>> stack{{0, 1.0}};
  while (!stack.empty()) {
    auto [h, reach] = stack.back();
    stack.pop_back();
    if (reach == 0.0) continue;
    const TreeNodeEF& node = tree.nodes[h];
    if (node.kind == TreeNodeEF::Kind::Terminal) {
      for (size_t k = 0; k < totals.size(); ++k) totals[k] += reach * node.payoffs[k];
    } else if (node.kind == TreeNodeEF::Kind::Chance) {
      for (size_t k = 0; k < node.children.size(); ++k) {
        stack.emplace_back(node.children[k], reach * node.probs[k]);
      }
    } else {
      const auto& q = policy[static_cast<size_t>(node.infoset)];
      for (size_t k = 0; k < node.children.size(); ++k) stack.emplace_back(node.children[k], reach * q[k]);
    }
  }
  return totals;
}

double best_response_value(const GameTreeEF& tree, const PolicyEF& policy, int player) {
  size_t count = tree.nodes.size();
  std::vector<double> reach(count, 0.0);
  reach[0] = 1.0;
  for (size_t h = 0; h < count; ++h) {  // los padres van antes que los hijos (preorden)
    const TreeNodeEF& node = tree.nodes[h];
    if (node.kind == TreeNodeEF::Kind::Terminal || reach[h] == 0.0) continue;
    for (size_t k = 0; k < node.children.size(); ++k) {
      double w;
      if (node.kind == TreeNodeEF::Kind::Chance) {
        w = node.probs[k];
      } else if (node.player == player) {
        w = 1.0;
      } else {
        w = policy[static_cast<size_t>(node.infoset)][k];
      }
      reach[node.children[k]] = reach[h] * w;
    }
  }
  std::vector<double> value(count, 0.0);
  std::vector<char> known(count, 0);
  std::vector<int> choice(tree.infosets.size(), -1);
  // Valores en orden inverso (los hijos antes que los padres); la elección de cada conjunto se
  // hace cuando ya se conocen todos sus nodos hijos.
  std::function<double(uint32_t)> eval;
  std::function<int(int)> choose = [&](int infoset) {
    auto i = static_cast<size_t>(infoset);
    if (choice[i] >= 0) return choice[i];
    const InfoSetEF& info = tree.infosets[i];
    int best = 0;
    double best_score = 0.0;
    for (size_t a = 0; a < info.actions; ++a) {
      double score = 0.0;
      for (uint32_t h : info.nodes) score += reach[h] * eval(tree.nodes[h].children[a]);
      if (a == 0 || score > best_score) {
        best_score = score;
        best = static_cast<int>(a);
      }
    }
    choice[i] = best;
    return best;
  };
  eval = [&](uint32_t h) -> double {
    if (known[h]) return value[h];
    const TreeNodeEF& node = tree.nodes[h];
    double out = 0.0;
    if (node.kind == TreeNodeEF::Kind::Terminal) {
      out = node.payoffs[static_cast<size_t>(player)];
    } else if (node.kind == TreeNodeEF::Kind::Chance) {
      for (size_t k = 0; k < node.children.size(); ++k) out += node.probs[k] * eval(node.children[k]);
    } else if (node.player == player) {
      out = eval(node.children[static_cast<size_t>(choose(node.infoset))]);
    } else {
      const auto& q = policy[static_cast<size_t>(node.infoset)];
      for (size_t k = 0; k < node.children.size(); ++k) {
        if (q[k] != 0.0) out += q[k] * eval(node.children[k]);
      }
    }
    value[h] = out;
    known[h] = 1;
    return out;
  };
  return eval(0);
}

double exploitability(const GameTreeEF& tree, const PolicyEF& policy) {
  std::vector<double> on_policy = expected_values(tree, policy);
  double conv = 0.0;
  for (int k = 0; k < tree.num_players; ++k) {
    conv += best_response_value(tree, policy, k) - on_policy[static_cast<size_t>(k)];
  }
  return conv / tree.num_players;
}

}  // namespace gh
