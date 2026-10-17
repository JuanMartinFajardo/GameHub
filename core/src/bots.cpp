// SPDX-License-Identifier: Apache-2.0
#include "gamehub/bots.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <limits>
#include <map>
#include <optional>
#include <unordered_map>

#include "gamehub/errors.hpp"
#include "gamehub/search.hpp"
#include "gamehub/vm.hpp"

namespace gh {

namespace {

using Clock = std::chrono::steady_clock;

double elapsed(Clock::time_point since) {
  return std::chrono::duration<double>(Clock::now() - since).count();
}

double payoff_of(const State& s, int seat) {
  return to_double(s.payoffs()[static_cast<size_t>(seat)].as_rational());
}

// --- Huecos ocultos ----------------------------------------------------------------------------

std::string type_key(const Type& t) {
  std::string k = std::to_string(static_cast<int>(t.kind)) + ":" + std::to_string(t.id);
  for (const auto& a : t.args) k += "(" + type_key(*a) + ")";
  return k;
}

bool holds_zones(const Type& t) {
  const Type* x = &t;
  while (x->kind == Type::Kind::List) x = &x->inner();
  return x->kind == Type::Kind::Zone || x->kind == Type::Kind::Bag;
}

// Recorre el almacén como las vistas (`redact`): primero reúne los elementos ocultos de zonas y
// bolsas por tipo y cuenta los demás valores ocultos; después reconstruye los valores con los
// elementos barajados y los valores nuevos.
class HiddenWalk {
 public:
  HiddenWalk(const State& s, int seat) : s_(s), ctx_(state_query_ctx(s)) {
    frame_.viewer = seat;
  }

  void collect() {
    const GameDef& g = s_.game();
    for (const auto& var : g.vars) collect(s_.data().store[var.index], *var.type, var);
  }

  bool any() const { return wholes > 0 || pooled > 0; }

  // Reconstruye el almacén: `fresh` (o nullptr) es el de una repetición con el azar nuevo.
  ValueVec rebuild(Pcg32& rng, const ValueVec* fresh) {
    for (auto& [key, pool] : pools_) {
      for (size_t k = pool.size(); k > 1; --k) std::swap(pool[k - 1], pool[rng.below(k)]);
    }
    cursors_.clear();
    const GameDef& g = s_.game();
    ValueVec store;
    store.reserve(g.vars.size());
    for (const auto& var : g.vars) {
      const Value* f = fresh != nullptr ? &(*fresh)[var.index] : nullptr;
      store.push_back(rebuild(s_.data().store[var.index], f, *var.type, var));
    }
    return store;
  }

  size_t wholes = 0;  // valores ocultos que no están en zonas
  size_t pooled = 0;  // elementos ocultos de zonas

 private:
  bool item_hidden(const VarDef& var, const ArrayObj* z, uint32_t k) {
    frame_.face_up = static_cast<int8_t>(z->faces()[k]);
    bool shown = var.policy.allows(ctx_, frame_);
    frame_.face_up = -1;
    return !shown;
  }

  void collect(const Value& v, const Type& t, const VarDef& var) {
    if (t.kind == Type::Kind::PerPlayer) {
      int32_t saved = frame_.owner;
      for (size_t s = 0; s < v.tuple_size(); ++s) {
        frame_.owner = static_cast<int32_t>(s);
        collect(v.tuple_at(s), t.inner(), var);
      }
      frame_.owner = saved;
      return;
    }
    if (t.kind == Type::Kind::Zone || t.kind == Type::Kind::Bag) {
      const ArrayObj* z = v.arr();
      std::string key = type_key(t.inner());
      for (uint32_t k = 0; k < z->n; ++k) {
        if (item_hidden(var, z, k)) {
          pools_[key].push_back(z->items()[k]);
          ++pooled;
        }
      }
      return;
    }
    if (t.kind == Type::Kind::List && holds_zones(t)) {
      for (size_t k = 0; k < v.tuple_size(); ++k) collect(v.tuple_at(k), t.inner(), var);
      return;
    }
    if (!var.policy.allows(ctx_, frame_)) ++wholes;
  }

  Value rebuild(const Value& v, const Value* fresh, const Type& t, const VarDef& var) {
    if (t.kind == Type::Kind::PerPlayer) {
      int32_t saved = frame_.owner;
      ValueVec parts;
      bool same = fresh != nullptr && fresh->is_tuple_like() && fresh->tuple_size() == v.tuple_size();
      for (size_t s = 0; s < v.tuple_size(); ++s) {
        frame_.owner = static_cast<int32_t>(s);
        Value f;
        if (same) f = fresh->tuple_at(s);
        parts.push_back(rebuild(v.tuple_at(s), same ? &f : nullptr, t.inner(), var));
      }
      frame_.owner = saved;
      return Value::tuple(std::move(parts));
    }
    if (t.kind == Type::Kind::Zone || t.kind == Type::Kind::Bag) {
      const ArrayObj* z = v.arr();
      std::string key = type_key(t.inner());
      ValueVec items;
      ByteVec faces;
      bool changed = false;
      for (uint32_t k = 0; k < z->n; ++k) {
        faces.push_back(z->faces()[k]);
        if (item_hidden(var, z, k)) {
          items.push_back(pools_[key][cursors_[key]++]);
          changed = true;
        } else {
          items.push_back(z->items()[k]);
        }
      }
      if (!changed) return v;
      return Value::zone(std::move(items), std::move(faces), z->a != 0);
    }
    if (t.kind == Type::Kind::List && holds_zones(t)) {
      ValueVec parts;
      bool same = fresh != nullptr && fresh->is_tuple_like() && fresh->tuple_size() == v.tuple_size();
      for (size_t k = 0; k < v.tuple_size(); ++k) {
        Value f;
        if (same) f = fresh->tuple_at(k);
        parts.push_back(rebuild(v.tuple_at(k), same ? &f : nullptr, t.inner(), var));
      }
      return Value::tuple(std::move(parts));
    }
    if (fresh != nullptr && !var.policy.allows(ctx_, frame_)) return *fresh;
    return v;
  }

  const State& s_;
  Ctx ctx_;
  Frame frame_;
  std::map<std::string, std::vector<Value>> pools_;
  std::map<std::string, size_t> cursors_;
};

bool others_submitted(const State& s, int seat) {
  const auto& pending = s.data().pending;
  if (!pending) return false;
  for (const auto& [who, a] : pending->submitted) {
    if (who != seat) return true;
  }
  return false;
}

// La partida repetida con el azar sorteado de nuevo y las mismas jugadas, o nada si alguna deja
// de ser legal (o el estado no guarda su historia).
std::optional<State> replay_fresh(const State& s, Pcg32& rng) {
  std::vector<State> path = s.path();
  if (path.size() < 2) return std::nullopt;
  State r = path[0];
  ApplyOptions opt{false, false, true};
  for (size_t k = 1; k < path.size(); ++k) {
    const Step& step = path[k].step();
    switch (step.kind) {
      case Step::Kind::Chance:
        if (r.status() != Status::Chance) return std::nullopt;
        r = r.sample_and_apply(rng, opt);
        break;
      case Step::Kind::Action:
        if (r.status() != Status::Decision || !r.is_active(step.seat)) return std::nullopt;
        if (r.illegal_reason(step.seat, step.action)) return std::nullopt;
        r = r.apply_action(step.seat, step.action, opt);
        break;
      default:
        return std::nullopt;
    }
  }
  if (r.node() != s.node()) return std::nullopt;
  return r;
}

}  // namespace

bool has_hidden(const State& s, int seat) {
  if (others_submitted(s, seat)) return true;
  HiddenWalk walk(s, seat);
  walk.collect();
  return walk.any();
}

State determinize(const State& s, int seat, Pcg32& rng) {
  HiddenWalk walk(s, seat);
  walk.collect();
  bool pending = others_submitted(s, seat);
  if (!walk.any() && !pending) return s;
  std::optional<State> fresh;
  if (walk.wholes > 0) {
    for (int attempt = 0; attempt < 4 && !fresh; ++attempt) fresh = replay_fresh(s, rng);
  }
  const StateNode& d = s.data();
  auto node = std::allocate_shared<StateNode>(PoolAllocator<StateNode>());
  node->game = d.game;
  node->n = d.n;
  node->match = d.match;
  node->store = walk.rebuild(rng, fresh ? &fresh->data().store : nullptr);
  node->node = d.node;
  node->pending = d.pending;
  if (pending) {
    auto mine = std::make_shared<Pending>();
    mine->order = d.pending->order;
    for (const auto& [who, a] : d.pending->submitted) {
      if (who == seat) mine->submitted.emplace_back(who, a);
    }
    node->pending = mine;
  }
  node->terminal = d.terminal;
  node->payoffs = d.payoffs;
  node->parent = d.parent;
  node->step = d.step;
  node->depth = d.depth;
  node->path = d.path;
  return State(node);
}

// --- Alfa-beta con heurística ------------------------------------------------------------------

namespace {

constexpr double WIN = 1e6;  // escala de los pagos finales frente a la evaluación heurística
constexpr double INF = std::numeric_limits<double>::infinity();

struct Timeout {};

class AbSearch {
 public:
  AbSearch(const HeuristicDef* h, int root, Pcg32& rng, Clock::time_point deadline, bool timed,
           int chance_samples)
      : h_(h), root_(root), rng_(rng), deadline_(deadline), timed_(timed),
        chance_samples_(chance_samples) {}

  uint64_t nodes = 0;

  double search(const State& s, int depth, double alpha, double beta, int ply) {
    if (s.is_terminal()) {
      double p = payoff_of(s, root_);
      return p * WIN - (p > 0 ? ply : p < 0 ? -ply : 0);
    }
    if (++nodes % 256 == 0 && timed_ && Clock::now() > deadline_) throw Timeout{};
    if (s.status() == Status::Chance) return chance(s, depth, ply);
    if (depth <= 0) return h_ != nullptr && !h_->features.empty() ? evaluate(s, *h_, root_) : 0.0;
    StateKey key = state_key(s);
    auto found = table_.find(key);
    int hint = -1;
    if (found != table_.end()) {
      const Entry& e = found->second;
      hint = e.best;
      if (e.depth >= depth) {
        if (e.flag == EXACT) return e.value;
        if (e.flag == LOWER && e.value >= beta) return e.value;
        if (e.flag == UPPER && e.value <= alpha) return e.value;
      }
    }
    int seat = s.first_active();
    std::vector<Action> actions = s.legal_actions(seat);
    std::vector<size_t> order = ordering(s, seat, actions, hint);
    bool maximizing = seat == root_;
    double a0 = alpha, b0 = beta;
    double best = maximizing ? -INF : INF;
    int best_move = static_cast<int>(order.front());
    for (size_t k : order) {
      double v = search(s.apply_action(seat, actions[k], SEARCH), depth - 1, alpha, beta, ply + 1);
      if (maximizing ? v > best : v < best) {
        best = v;
        best_move = static_cast<int>(k);
      }
      if (maximizing) {
        alpha = std::max(alpha, v);
      } else {
        beta = std::min(beta, v);
      }
      if (alpha >= beta) break;
    }
    uint8_t flag = best <= a0 ? UPPER : best >= b0 ? LOWER : EXACT;
    if (table_.size() > 2'000'000) table_.clear();
    table_[key] = Entry{depth, best, flag, best_move};
    return best;
  }

  std::vector<size_t> ordering(const State& s, int seat, const std::vector<Action>& actions,
                               int hint) {
    std::vector<size_t> order;
    if (h_ != nullptr && (!h_->prefer.empty() || !h_->order.empty())) {
      order = order_actions(s, *h_, seat, actions);
    } else {
      order.resize(actions.size());
      for (size_t k = 0; k < actions.size(); ++k) order[k] = k;
    }
    if (hint >= 0 && static_cast<size_t>(hint) < actions.size()) {
      auto it = std::find(order.begin(), order.end(), static_cast<size_t>(hint));
      order.erase(it);
      order.insert(order.begin(), static_cast<size_t>(hint));
    }
    return order;
  }

 private:
  enum : uint8_t { EXACT, LOWER, UPPER };
  struct Entry {
    int depth;
    double value;
    uint8_t flag;
    int best;
  };

  double chance(const State& s, int depth, int ply) {
    try {
      auto outcomes = s.chance_outcomes(32);
      double total = 0;
      for (const auto& [o, p] : outcomes) {
        total += to_double(p) * search(s.apply_chance(o, SEARCH), depth, -INF, INF, ply);
      }
      return total;
    } catch (const NotEnumerable&) {
      double total = 0;
      for (int k = 0; k < chance_samples_; ++k) {
        total += search(s.sample_and_apply(rng_, SEARCH), depth, -INF, INF, ply);
      }
      return total / chance_samples_;
    }
  }

  const HeuristicDef* h_;
  int root_;
  Pcg32& rng_;
  Clock::time_point deadline_;
  bool timed_;
  int chance_samples_;
  std::unordered_map<StateKey, Entry, StateKeyHash> table_;
};

// --- MCTS de bucle abierto ---------------------------------------------------------------------

struct MChild;
struct MNode {
  std::vector<MChild> children;
  std::unordered_multimap<uint64_t, size_t> index;  // hash de la acción → hijo
};
struct MChild {
  Action action;
  uint64_t hash = 0;
  double visits = 0, avail = 0;
  std::vector<double> value;  // suma de los pagos de cada asiento
  std::unique_ptr<MNode> next;
};

// Una acción para las simulaciones: la mejor según la heurística (con probabilidad `greedy`) o
// una al azar.
Action rollout_action(const State& s, int seat, const HeuristicDef* h, double greedy, Pcg32& rng) {
  size_t count = s.count_legal(seat);
  bool guided = h != nullptr && (!h->prefer.empty() || !h->order.empty()) && count > 1 &&
                count <= 64 && rng.below(1'000'000) < greedy * 1'000'000;
  if (!guided) {
    // Una al azar sin construir la lista (en Mentiroso hay miles de subconjuntos).
    size_t pick = rng.below(count);
    Action chosen;
    size_t k = 0;
    s.for_each_legal(seat, [&](const Action& a) {
      if (k++ < pick) return true;
      chosen = a;
      return false;
    });
    return chosen;
  }
  std::vector<Action> legal = s.legal_actions(seat);
  std::vector<ActionKey> keys;
  for (const auto& a : legal) keys.push_back(action_key(s, *h, seat, a));
  ActionKey best = *std::min_element(keys.begin(), keys.end());
  std::vector<size_t> top;
  for (size_t k = 0; k < keys.size(); ++k) {
    if (!(best < keys[k])) top.push_back(k);
  }
  return legal[top[rng.below(top.size())]];
}

}  // namespace

// --- Bot ---------------------------------------------------------------------------------------

Bot::Bot(std::shared_ptr<const GameDef> game, BotSpec spec, int seat)
    : game_(std::move(game)), spec_(std::move(spec)), seat_(seat),
      rng_(spec_.seed, STREAM_AGENT_BASE + static_cast<uint64_t>(seat)) {
  if (spec_.use_heuristic) {
    h_ = game_->heuristic(spec_.heuristic);
    if (h_ == nullptr && !spec_.heuristic.empty()) {
      throw EngineError("el juego no tiene la heurística " + spec_.heuristic);
    }
  }
  static const char* kinds[] = {"random", "first", "greedy", "alphabeta", "mcts", "ismcts", "pimc"};
  if (std::find(std::begin(kinds), std::end(kinds), spec_.kind) == std::end(kinds)) {
    throw EngineError("bot desconocido: " + spec_.kind);
  }
}

Action Bot::act(const State& s) {
  auto started = Clock::now();
  stats_ = BotStats{};
  std::vector<Action> legal = s.legal_actions(seat_);
  if (legal.empty()) throw IllegalAction("el asiento no puede actuar");
  Action chosen;
  const std::string& kind = spec_.kind;
  if (kind == "random") {
    chosen = legal[rng_.below(legal.size())];
  } else if (kind == "first" || legal.size() == 1) {
    chosen = legal[0];
  } else if (kind == "greedy") {
    chosen = greedy(s, legal);
  } else {
    std::vector<double> values;
    if (kind == "alphabeta") {
      State d = determinize(s, seat_, rng_);
      values = alphabeta_values(d, legal, spec_.seconds);
    } else if (kind == "mcts") {
      values = mcts_values(s, legal, false, spec_.seconds);
    } else if (kind == "ismcts") {
      values = mcts_values(s, legal, true, spec_.seconds);
    } else {  // pimc
      bool hidden = has_hidden(s, seat_);
      int samples = hidden ? std::max(1, spec_.samples) : 1;
      values.assign(legal.size(), 0.0);
      bool search = h_ != nullptr && !h_->features.empty();
      for (int k = 0; k < samples; ++k) {
        State d = determinize(s, seat_, rng_);
        double budget = spec_.seconds > 0 ? spec_.seconds / samples : 0;
        std::vector<double> v = search ? alphabeta_values(d, legal, budget)
                                       : mcts_values(d, legal, false, budget);
        for (size_t a = 0; a < legal.size(); ++a) values[a] += v[a] / samples;
      }
    }
    double best = -INF;
    std::vector<size_t> top;
    for (size_t a = 0; a < values.size(); ++a) {
      if (values[a] > best + 1e-9) {
        best = values[a];
        top = {a};
      } else if (std::abs(values[a] - best) <= 1e-9) {
        top.push_back(a);
      }
    }
    chosen = legal[top.size() == 1 ? top[0] : top[rng_.below(top.size())]];
    stats_.value = best;
  }
  stats_.seconds = elapsed(started);
  return chosen;
}

Action Bot::greedy(const State& s, const std::vector<Action>& legal) {
  State d = determinize(s, seat_, rng_);
  std::vector<size_t> top;
  if (h_ != nullptr && (!h_->prefer.empty() || !h_->order.empty())) {
    std::vector<ActionKey> keys;
    for (const auto& a : legal) keys.push_back(action_key(d, *h_, seat_, a));
    ActionKey best = *std::min_element(keys.begin(), keys.end());
    for (size_t k = 0; k < keys.size(); ++k) {
      if (!(best < keys[k])) top.push_back(k);
    }
  } else {
    for (size_t k = 0; k < legal.size(); ++k) top.push_back(k);
  }
  if (top.size() > 1) {
    // Desempate mirando una jugada adelante: el pago si termina, la evaluación si no.
    std::vector<size_t> best;
    double best_value = -INF;
    for (size_t k : top) {
      State child = d.apply_action(seat_, legal[k], SEARCH);
      if (child.status() == Status::Chance) child = child.sample_and_apply(rng_, SEARCH);
      double v = 0;
      if (child.is_terminal()) {
        v = payoff_of(child, seat_) * WIN;
      } else if (h_ != nullptr && !h_->features.empty()) {
        v = evaluate(child, *h_, seat_);
      }
      if (v > best_value + 1e-9) {
        best_value = v;
        best = {k};
      } else if (std::abs(v - best_value) <= 1e-9) {
        best.push_back(k);
      }
    }
    top = best;
    stats_.value = best_value;
  }
  return legal[top.size() == 1 ? top[0] : top[rng_.below(top.size())]];
}

std::vector<double> Bot::alphabeta_values(const State& s, const std::vector<Action>& legal,
                                          double seconds) {
  auto started = Clock::now();
  bool timed = seconds > 0;
  auto deadline = started + std::chrono::duration_cast<Clock::duration>(
                                std::chrono::duration<double>(seconds));
  int max_depth = spec_.depth > 0 ? spec_.depth : (timed ? 64 : 4);
  AbSearch search(h_, seat_, rng_, deadline, timed, spec_.chance_samples);
  // Las acciones legales de la determinización (las del bot no dependen de lo oculto; si alguna
  // no lo es aquí, vale -∞).
  std::vector<Action> here = s.legal_actions(seat_);
  std::vector<int> index(legal.size(), -1);
  for (size_t a = 0; a < legal.size(); ++a) {
    for (size_t b = 0; b < here.size(); ++b) {
      if (legal[a] == here[b]) {
        index[a] = static_cast<int>(b);
        break;
      }
    }
  }
  std::vector<double> result(legal.size(), -INF);
  std::vector<size_t> order(legal.size());
  for (size_t a = 0; a < legal.size(); ++a) order[a] = a;
  if (h_ != nullptr && (!h_->prefer.empty() || !h_->order.empty())) {
    order = order_actions(s, *h_, seat_, legal);
  }
  bool exact = spec_.kind == "pimc";  // PIMC promedia: necesita el valor de cada acción
  for (int depth = 1; depth <= max_depth; ++depth) {
    std::vector<double> values(legal.size(), -INF);
    try {
      double alpha = -INF;
      for (size_t a : order) {
        if (index[a] < 0) continue;
        State child = s.apply_action(seat_, legal[a], SEARCH);
        double v = search.search(child, depth - 1, exact ? -INF : alpha, INF, 1);
        values[a] = v;
        alpha = std::max(alpha, v);
      }
    } catch (const Timeout&) {
      if (depth == 1) result = values;  // al menos lo que dio tiempo a ver
      break;
    }
    result = values;
    stats_.depth = depth;
    // La mejor primero en la siguiente iteración.
    std::stable_sort(order.begin(), order.end(),
                     [&](size_t x, size_t y) { return values[x] > values[y]; });
    double best = values[order.front()];
    if (std::abs(best) >= WIN / 2) break;  // un resultado forzado: no hace falta más
    if (!timed && depth >= max_depth) break;
  }
  stats_.nodes += search.nodes;
  return result;
}

std::vector<double> Bot::mcts_values(const State& root, const std::vector<Action>& legal,
                                     bool determinize_each, double seconds) {
  auto started = Clock::now();
  bool timed = seconds > 0;
  uint64_t limit = spec_.iterations > 0 ? spec_.iterations : (timed ? UINT64_MAX : 1000);
  int n = root.num_players();
  bool hidden = has_hidden(root, seat_);
  State fixed = hidden && !determinize_each ? determinize(root, seat_, rng_) : root;
  MNode tree;
  double lo = INF, hi = -INF;
  std::vector<double> payoffs(static_cast<size_t>(n));
  uint64_t done = 0;
  while (done < limit) {
    if (timed && done > 0 && elapsed(started) > seconds) break;
    State s = determinize_each && hidden ? determinize(root, seat_, rng_) : fixed;
    MNode* node = &tree;
    std::vector<MChild*> path;
    bool expanded = false;
    // Selección y expansión.
    while (!expanded) {
      while (s.status() == Status::Chance) s = s.sample_and_apply(rng_, SEARCH);
      if (s.is_terminal()) break;
      int seat = s.first_active();
      std::vector<Action> acts = s.legal_actions(seat);
      auto find = [&](const Action& a) -> MChild* {
        auto [lo_it, hi_it] = node->index.equal_range(a.hash());
        for (auto it = lo_it; it != hi_it; ++it) {
          MChild& c = node->children[it->second];
          if (c.action == a) return &c;
        }
        return nullptr;
      };
      std::vector<size_t> untried;
      for (size_t k = 0; k < acts.size(); ++k) {
        if (find(acts[k]) == nullptr) untried.push_back(k);
      }
      MChild* chosen = nullptr;
      if (!untried.empty()) {
        // Expansión: la mejor según la heurística (o una al azar).
        size_t pick = untried[rng_.below(untried.size())];
        if (h_ != nullptr && (!h_->prefer.empty() || !h_->order.empty()) && untried.size() > 1 &&
            untried.size() <= 64) {
          ActionKey best = action_key(s, *h_, seat, acts[untried.front()]);
          pick = untried.front();
          for (size_t k : untried) {
            ActionKey key = action_key(s, *h_, seat, acts[k]);
            if (key < best) {
              best = key;
              pick = k;
            }
          }
        }
        node->children.push_back(MChild{acts[pick], acts[pick].hash(), 0, 0,
                                        std::vector<double>(static_cast<size_t>(n), 0.0), nullptr});
        node->index.emplace(acts[pick].hash(), node->children.size() - 1);
        chosen = &node->children.back();
        expanded = true;
      } else {
        // Selección: UCB con el número de veces que cada hijo estuvo disponible (ISMCTS).
        double best = -INF;
        double base = hi >= lo ? lo : 0.0;
        double span = hi > lo ? hi - lo : 1.0;
        for (const auto& a : acts) {
          MChild* c = find(a);
          if (chosen == nullptr) chosen = c;
          double mean = (c->value[static_cast<size_t>(seat)] / c->visits - base) / span;
          double ucb = mean + spec_.c * std::sqrt(std::log(std::max(1.0, c->avail + 1)) / c->visits);
          if (ucb > best) {
            best = ucb;
            chosen = c;
          }
        }
      }
      for (const auto& a : acts) {
        if (MChild* c = find(a)) c->avail += 1;
      }
      path.push_back(chosen);
      s = s.apply_action(seat, chosen->action, SEARCH);
      if (!chosen->next) chosen->next = std::make_unique<MNode>();
      node = chosen->next.get();
    }
    // Simulación.
    int steps = 0;
    while (!s.is_terminal() && steps < spec_.max_rollout) {
      if (s.status() == Status::Chance) {
        s = s.sample_and_apply(rng_, SEARCH);
      } else {
        int seat = s.first_active();
        s = s.apply_action(seat, rollout_action(s, seat, h_, spec_.greedy, rng_), SEARCH);
      }
      ++steps;
    }
    if (s.is_terminal()) {
      for (int k = 0; k < n; ++k) payoffs[static_cast<size_t>(k)] = payoff_of(s, k);
    } else if (h_ != nullptr && !h_->features.empty() && s.status() != Status::Chance) {
      // Sin final (horizonte `max_rollout`): la evaluación de la heurística, que en ese caso
      // debe estimar el pago de cada asiento en sus mismas unidades.
      for (int k = 0; k < n; ++k) payoffs[static_cast<size_t>(k)] = evaluate(s, *h_, k);
    } else {
      // Sin final ni evaluación: neutral (el punto medio de los pagos vistos).
      double mid = hi >= lo ? (lo + hi) / 2 : 0.0;
      std::fill(payoffs.begin(), payoffs.end(), mid);
    }
    for (double p : payoffs) {
      lo = std::min(lo, p);
      hi = std::max(hi, p);
    }
    for (MChild* c : path) {
      c->visits += 1;
      for (int k = 0; k < n; ++k) c->value[static_cast<size_t>(k)] += payoffs[static_cast<size_t>(k)];
    }
    ++done;
  }
  stats_.nodes += done;
  std::vector<double> values(legal.size(), -INF);
  for (size_t a = 0; a < legal.size(); ++a) {
    for (const auto& c : tree.children) {
      if (c.action == legal[a] && c.visits > 0) {
        // Las más visitadas primero; el valor medio desempata.
        double base = hi >= lo ? lo : 0.0;
        double span = hi > lo ? hi - lo : 1.0;
        values[a] = c.visits + (c.value[static_cast<size_t>(seat_)] / c.visits - base) / span * 0.5;
      }
    }
  }
  return values;
}

// --- Partidas entre bots -----------------------------------------------------------------------

BotMatch play_bots(const Game& game, int num_players, const Json& params,
                   const std::vector<BotSpec>& seats, uint64_t seed, int max_steps, bool trace,
                   const std::string& eval, bool features) {
  const HeuristicDef* evaluator = nullptr;
  if (!eval.empty()) {
    evaluator = game.def().heuristic(eval);
    if (evaluator == nullptr) throw EngineError("el juego no tiene la heurística " + eval);
  }
  std::vector<const TransitionDef*> taken;
  // Solo las transiciones de la partida (no las de las búsquedas de los bots).
  auto step = [&](auto&& apply) {
    if (trace) set_transition_trace(&taken);
    try {
      apply();
    } catch (...) {
      set_transition_trace(nullptr);
      throw;
    }
    set_transition_trace(nullptr);
  };
  if (static_cast<int>(seats.size()) != num_players) {
    throw EngineError("hace falta un bot por asiento");
  }
  std::vector<Bot> bots;
  for (int k = 0; k < num_players; ++k) {
    BotSpec spec = seats[static_cast<size_t>(k)];
    spec.seed += seed;
    bots.emplace_back(game.def_ptr(), spec, k);
  }
  BotMatch result;
  result.seconds.assign(static_cast<size_t>(num_players), 0.0);
  ApplyOptions opt{false, true, true};
  Pcg32 chance(seed, STREAM_CHANCE);
  try {
    State s = game.new_state(num_players, params, opt);
    while (!s.is_terminal()) {
      if (result.steps >= max_steps) {
        result.truncated = true;
        return result;
      }
      StepTrace st;
      if (s.status() == Status::Chance) {
        step([&] { s = s.sample_and_apply(chance, opt); });
      } else {
        int seat = s.first_active();
        if (trace) {
          st.seat = seat;
          st.legal = static_cast<uint32_t>(s.count_legal(seat));
        }
        auto started = Clock::now();
        Action a = bots[static_cast<size_t>(seat)].act(s);
        result.seconds[static_cast<size_t>(seat)] += elapsed(started);
        if (trace) st.action = a.name(game.def());
        step([&] { s = s.apply_action(seat, a, opt); });
      }
      if (trace) {
        if (evaluator != nullptr && !s.is_terminal() && s.status() != Status::Chance) {
          for (int k = 0; k < num_players; ++k) {
            if (features) {
              for (const auto& v : feature_values(s, *evaluator, k)) {
                st.eval.push_back(to_double(v.as_rational()));
              }
            } else {
              st.eval.push_back(evaluate(s, *evaluator, k));
            }
          }
        }
        result.trace.push_back(std::move(st));
      }
      ++result.steps;
    }
    result.payoffs = s.payoffs();
    for (const auto& p : s.payoffs()) result.payoff_doubles.push_back(to_double(p.as_rational()));
    result.ranking = *s.ranking();
  } catch (const RuleError& e) {
    result.error = e.what();
  }
  for (const TransitionDef* t : taken) {
    std::string key;
    for (const auto& part : t->key) key += (key.empty() ? "" : "/") + part;
    result.transitions.push_back(key);
  }
  return result;
}

// --- Kingmaking ---------------------------------------------------------------------------------

KingmakingReport kingmaking(const Game& game, int num_players, const Json& params,
                            const std::vector<BotSpec>& seats, uint64_t seed, int rollouts,
                            double late, int max_steps) {
  KingmakingReport report;
  std::vector<Bot> bots;
  for (int k = 0; k < num_players; ++k) {
    BotSpec spec = seats[static_cast<size_t>(k)];
    spec.seed += seed;
    bots.emplace_back(game.def_ptr(), spec, k);
  }
  const HeuristicDef* h = game.def().heuristic("");
  BotSpec quick;
  quick.kind = h != nullptr ? "greedy" : "random";
  ApplyOptions opt{false, false, true};
  Pcg32 chance(seed, STREAM_CHANCE);
  Pcg32 rng(seed, 77);
  std::vector<std::pair<State, int>> decisions;  // (estado, asiento que decide)
  try {
    State s = game.new_state(num_players, params, opt);
    while (!s.is_terminal() && report.steps < max_steps) {
      if (s.status() == Status::Chance) {
        s = s.sample_and_apply(chance, opt);
      } else {
        int seat = s.first_active();
        decisions.emplace_back(s, seat);
        s = s.apply_action(seat, bots[static_cast<size_t>(seat)].act(s), opt);
      }
      ++report.steps;
    }
    if (!s.is_terminal()) return report;
    size_t from = static_cast<size_t>(late * static_cast<double>(decisions.size()));
    std::vector<Bot> players;
    for (int k = 0; k < num_players; ++k) {
      BotSpec spec = quick;
      spec.seed = seed * 31 + static_cast<uint64_t>(k);
      players.emplace_back(game.def_ptr(), spec, k);
    }
    // Quién queda primero (−1 si empatan varios) tras jugar desde `st` con los bots rápidos.
    auto winner = [&](State st) {
      int steps = 0;
      while (!st.is_terminal() && steps++ < max_steps) {
        if (st.status() == Status::Chance) {
          st = st.sample_and_apply(rng, SEARCH);
        } else {
          int seat = st.first_active();
          st = st.apply_action(seat, players[static_cast<size_t>(seat)].act(st), SEARCH);
        }
      }
      if (!st.is_terminal()) return -1;
      auto ranks = *st.ranking();
      int first = -1;
      for (int k = 0; k < num_players; ++k) {
        if (ranks[static_cast<size_t>(k)] == 1) first = first < 0 ? k : -1;  // 1 = primero
      }
      return first;
    };
    for (size_t d = from; d < decisions.size(); ++d) {
      const auto& [state, seat] = decisions[d];
      std::vector<Action> legal = state.legal_actions(seat);
      if (legal.size() < 2) continue;
      if (legal.size() > 8) {
        for (size_t k = legal.size(); k > 1; --k) std::swap(legal[k - 1], legal[rng.below(k)]);
        legal.resize(8);
      }
      ++report.probes;
      double best_own = 0;
      std::vector<std::vector<double>> dist;
      for (const auto& a : legal) {
        std::vector<double> counts(static_cast<size_t>(num_players) + 1, 0.0);
        for (int r = 0; r < rollouts; ++r) {
          int w = winner(state.apply_action(seat, a, SEARCH));
          counts[w < 0 ? static_cast<size_t>(num_players) : static_cast<size_t>(w)] += 1.0 / rollouts;
        }
        best_own = std::max(best_own, counts[static_cast<size_t>(seat)]);
        dist.push_back(std::move(counts));
      }
      if (best_own > 0.05) continue;
      double spread = 0;
      for (size_t x = 0; x < dist.size(); ++x) {
        for (size_t y = x + 1; y < dist.size(); ++y) {
          double tv = 0;
          for (size_t k = 0; k < dist[x].size(); ++k) tv += std::abs(dist[x][k] - dist[y][k]) / 2;
          spread = std::max(spread, tv);
        }
      }
      if (spread >= 0.25) ++report.events;
    }
  } catch (const RuleError& e) {
    report.error = e.what();
  }
  return report;
}

}  // namespace gh
