// SPDX-License-Identifier: Apache-2.0
// Semántica operacional del flujo (como `gamehub.engine.state`): avanzar hasta la quietud,
// transiciones por grupos, fases con on_enter/on_exit y `$exit`, decisiones, nodos simultáneos,
// ventanas, azar y terminales; vistas, eventos, instantáneas y estados de información.
#include "gamehub/state.hpp"

#include <algorithm>

#include "gamehub/errors.hpp"
#include "gamehub/sha256.hpp"
#include "gamehub/stmt.hpp"

namespace gh {

namespace {

// Las transiciones tomadas en este hilo (la cobertura del Studio), si alguien las pide.
thread_local std::vector<const TransitionDef*>* g_transition_trace = nullptr;

constexpr int MAX_ARRIVALS = 10'000;

const JsonPtr HIDDEN_PTR = std::make_shared<const Json>(Json(JsonObject{{"$hidden", Json(true)}}));
const Json& hidden() { return *HIDDEN_PTR; }

Ctx query_ctx(const StateNode& s) {
  Ctx ctx;
  ctx.game = s.game.get();
  ctx.store = const_cast<ValueVec*>(&s.store);  // las consultas no escriben
  ctx.params = &s.match->params;
  ctx.n = s.n;
  ctx.path = s.path;
  ctx.memo = &s.memo;
  ctx.seats = s.match->seats;
  return ctx;
}

// --- Enumeración de acciones -------------------------------------------------------------------

// Acciones legales de `a` para `actor`: parámetros en orden, valores en orden del dominio,
// filtradas por `requires`. Devuelve false si `visit` pidió parar.
// Los argumentos ya elegidos están en las ranuras 0..i-1 de `frame` (un marco compartido por
// todos los dominios y el `requires` de la acción).
bool complete_in(const ActionDef& a, Ctx& ctx, Frame& frame, size_t i,
                 const std::function<bool(const Action&)>& visit) {
  Vm& machine = ctx.machine();
  if (i == a.params.size()) {
    if (a.requires_expr.defined) {
      Value ok = machine.eval(a.requires_expr.chunk, ctx, frame);
      bool b = ok.tag == Tag::Bool ? ok.i != 0 : expect_bool(ok, "requires", ctx);
      if (!b) return true;
    }
    return visit(Action{&a, Args(std::span<const Value>(frame.slots, i))});
  }
  Value domain = machine.eval(a.params[i].domain.chunk, ctx, frame);
  Items it = iterate(domain, "dominio", ctx);
  for (size_t k = 0; k < it.size; ++k) {
    frame.slots[i] = it[k];
    if (!complete_in(a, ctx, frame, i + 1, visit)) return false;
  }
  frame.slots[i] = Value();
  return true;
}

bool complete(const ActionDef& a, Ctx& ctx, int actor, const ValueVec& args, size_t i,
              const std::function<bool(const Action&)>& visit) {
  ScopedFrame scope(ctx.machine(), a.query_frame);
  scope.frame.actor = actor;
  for (size_t k = 0; k < i; ++k) scope.frame.slots[k] = args[k];
  return complete_in(a, ctx, scope.frame, i, visit);
}

bool enumerate_node(const NodeDef& node, Ctx& ctx, int actor,
                    const std::function<bool(const Action&)>& visit) {
  ValueVec none;
  for (const auto& a : node.actions) {
    if (!complete(a, ctx, actor, none, 0, visit)) return false;
  }
  return true;
}

// ¿Pertenece `v` al dominio del parámetro `i` (sin enumerarlo cuando se puede)? Devuelve el valor
// canónico (los subconjuntos, ordenados).
bool member(const ActionParamDef& p, Ctx& ctx, int actor, const ValueVec& args,
            const Value& v, Value& canonical) {
  auto argc = static_cast<uint32_t>(args.size());
  canonical = v;
  switch (p.member) {
    case DomainKind::Subsets: {
      if (!v.is_tuple_like()) return false;
      size_t len = v.tuple_size();
      ValueVec sorted;
      for (size_t k = 0; k < len; ++k) sorted.push_back(v.tuple_at(k));
      std::stable_sort(sorted.begin(), sorted.end(), canonical_less);
      Value lo = eval_expr(p.lo, ctx, actor, args.data(), argc);
      expect_num(lo, "subsets", ctx);
      bool ok = lo.as_rational().compare(Rational::integer(int64_t(len))) <= 0;
      if (ok) {
        Value hi = eval_expr(p.hi, ctx, actor, args.data(), argc);
        expect_num(hi, "subsets", ctx);
        ok = Rational::integer(int64_t(len)).compare(hi.as_rational()) <= 0;
      }
      if (ok) {
        Items pool = iterate(eval_expr(p.coll, ctx, actor, args.data(), argc), "subsets", ctx);
        PoolVec<bool> used(pool.size, false);
        for (size_t k = 0; k < len && ok; ++k) {
          Value x = v.tuple_at(k);
          bool found = false;
          for (size_t j = 0; j < pool.size; ++j) {
            if (!used[j] && equals(pool[j], x)) {
              used[j] = true;
              found = true;
              break;
            }
          }
          ok = found;
        }
      }
      canonical = Value::tuple(std::move(sorted));
      return ok;
    }
    case DomainKind::Range: {
      if (v.tag != Tag::Int) return false;
      Value lo = eval_expr(p.lo, ctx, actor, args.data(), argc);
      if (compare_ir(lo, v, "range", ctx) > 0) return false;
      Value hi = eval_expr(p.hi, ctx, actor, args.data(), argc);
      return compare_ir(v, hi, "range", ctx) <= 0;
    }
    case DomainKind::EnumValues:
      return v.tag == Tag::Enum && v.x == p.enum_type;
    case DomainKind::Generic: {
      Items it = iterate(eval_expr(p.domain, ctx, actor, args.data(), argc), "dominio", ctx);
      for (size_t k = 0; k < it.size; ++k) {
        if (equals(it[k], v)) return true;
      }
      return false;
    }
  }
  return false;
}

Json pending_json(const GameDef& g, const Pending& p) {
  JsonArray order, submitted;
  for (int s : p.order) order.push_back(Json(int64_t(s)));
  for (const auto& [s, a] : p.submitted) {
    submitted.push_back(Json(JsonArray{Json(int64_t(s)), a.to_json(g)}));
  }
  JsonObject out;
  out.emplace_back("order", Json(std::move(order)));
  out.emplace_back("submitted", Json(std::move(submitted)));
  return Json(std::move(out));
}

// --- Transacción -------------------------------------------------------------------------------

struct EnvRef {
  int actor = NO_SEAT;
  const Value* args = nullptr;
  uint32_t argc = 0;
};

struct Candidates {
  const std::vector<TransitionDef>* transitions;
  EnvRef env;
};

// Transacción mutable que calcula el estado siguiente (como `_Tx`). No sobrevive al paso.
class Tx {
 public:
  Tx(const std::shared_ptr<const GameDef>& game, const std::shared_ptr<const Match>& match,
     const ValueVec& store, int node, const std::shared_ptr<const Pending>& pending,
     Draws* draws, bool record)
      : gp_(game), g_(*gp_), match_(match), store_(store), pending_(pending), record_(record) {
    ctx_.game = &g_;
    ctx_.store = &store_;
    ctx_.params = &match_->params;
    ctx_.n = match_->n;
    ctx_.path = path_;
    ctx_.draws = draws;
    ctx_.events = record ? &events_ : nullptr;
    ctx_.memo = &memo_;
    ctx_.seats = match_->seats;
    set_node(node);
  }
  Tx(const Tx&) = delete;
  Tx& operator=(const Tx&) = delete;

  std::shared_ptr<StateNode> commit(const std::shared_ptr<const StateNode>& parent, Step step,
                                    bool history) {
    auto s = std::allocate_shared<StateNode>(PoolAllocator<StateNode>());
    s->game = gp_;
    s->n = match_->n;
    s->match = match_;
    s->store = std::move(store_);
    s->node = node_;
    s->pending = std::move(pending_);
    s->terminal = terminal_;
    s->payoffs = std::move(payoffs_);
    s->depth = parent ? parent->depth + 1 : 0;
    if (history) s->parent = parent;
    step.events = std::move(events_);
    s->step = std::move(step);
    s->path = path_;
    s->memo = std::move(memo_);
    return s;
  }

  void keep_payoffs(bool terminal, const ValueVec& payoffs) {
    terminal_ = terminal;
    payoffs_ = payoffs;
  }
  Ctx& ctx() { return ctx_; }

  // --- flujo ---

  void start() {
    run_code(g_.setup, ctx_);
    ctx_.draws = nullptr;
    descend(g_.start);
    drain();
  }

  void run_chance() {
    if (node_ < 0) {
      start();
      return;
    }
    const NodeDef& node = g_.node(node_);
    run_code(node.effects, ctx_);
    ctx_.draws = nullptr;
    take({{&node.transitions, {}}}, node_);
    drain();
  }

  void act(int actor, const Action& action) {
    const NodeDef& node = g_.node(node_);
    switch (node.kind) {
      case NodeKind::Decision:
        perform(node, actor, action, true);
        break;
      case NodeKind::Simultaneous: {
        auto p = std::allocate_shared<Pending>(PoolAllocator<Pending>(), *pending_);
        p->submitted.emplace_back(actor, action);
        bool complete = p->submitted.size() == p->order.size();
        pending_ = p;
        emit_shared({{"type", Json("submitted")}, {"seat", Json(int64_t(actor))}});
        if (complete) resolve_simultaneous();
        break;
      }
      case NodeKind::Window:
        respond(node, actor, action);
        break;
      default:
        throw RuleError("no se puede actuar en este nodo", node.id);
    }
    drain();
  }

 private:
  struct Jump {
    enum class Kind : uint8_t { None, Transfer, Exit } kind = Kind::None;
    std::vector<int> active;
    int target = -1;
  };

  // Referencias a los del estado de partida (vivo mientras dura la transacción).
  const std::shared_ptr<const GameDef>& gp_;
  const GameDef& g_;
  const std::shared_ptr<const Match>& match_;
  ValueVec store_;
  int node_ = -1;
  const std::vector<int>* path_ = nullptr;
  std::shared_ptr<const Pending> pending_;
  bool terminal_ = false;
  ValueVec payoffs_;
  MemoTable memo_;
  std::vector<Event> events_;
  bool record_;
  Ctx ctx_;
  int arrivals_ = 0;
  Jump next_;

  void set_node(int node) {
    node_ = node;
    path_ = g_.path(node);
    ctx_.path = path_;
  }

  void emit_shared(JsonObject payload) {
    if (!record_) return;
    events_.push_back(Event::shared(Json(std::move(payload)), match_->n));
  }

  void drain() {
    while (next_.kind != Jump::Kind::None) {
      Jump j = std::move(next_);
      next_ = Jump{};
      if (j.kind == Jump::Kind::Exit) {
        exit_phase(j.target);
      } else {
        transfer(j.active, j.target);
      }
    }
  }

  void descend(int node_id) {
    const NodeDef* node = &g_.node(node_id);
    while (node->kind == NodeKind::Phase) {
      set_node(node->index);
      if (node->has_on_enter) run_code(node->on_enter, ctx_);
      node = &g_.node(node->start);
    }
    arrive(node->index);
  }

  void transfer(const std::vector<int>& active, int target) {
    const std::vector<int>& chain = g_.node(target).ancestors;
    size_t common = 0;
    while (common < std::min(active.size(), chain.size()) && active[common] == chain[common]) {
      ++common;
    }
    for (size_t k = active.size(); k-- > common;) exit_actions(active[k]);
    for (size_t k = common; k < chain.size(); ++k) {
      set_node(chain[k]);
      const NodeDef& phase = g_.node(chain[k]);
      if (phase.has_on_enter) run_code(phase.on_enter, ctx_);
    }
    descend(target);
  }

  void exit_actions(int phase) {
    set_node(phase);
    const NodeDef& p = g_.node(phase);
    if (p.has_on_exit) run_code(p.on_exit, ctx_);
  }

  void exit_phase(int phase) {
    exit_actions(phase);
    take({{&g_.node(phase).transitions, {}}}, phase);
  }

  // Primera transición aplicable (por orden de grupo y de declaración) y la sigue.
  void take(std::initializer_list<Candidates> candidates, int origin) {
    for (const auto& group : candidates) {
      for (const auto& t : *group.transitions) {
        if (t.when.defined) {
          Value ok = eval_expr(t.when, ctx_, group.env.actor, group.env.args, group.env.argc);
          if (!expect_bool(ok, "when", ctx_)) continue;
        }
        if (g_transition_trace != nullptr) g_transition_trace->push_back(&t);
        run_code(t.effects, ctx_, group.env.actor, group.env.args, group.env.argc);
        const NodeDef& o = g_.node(origin);
        if (t.to < 0) {
          next_ = Jump{Jump::Kind::Exit, {}, o.parent()};
        } else {
          next_ = Jump{Jump::Kind::Transfer, o.ancestors, t.to};
        }
        return;
      }
    }
    throw RuleError("ninguna transición aplicable", g_.node(origin).id);
  }

  void arrive(int node_id) {
    const NodeDef& node = g_.node(node_id);
    if (++arrivals_ > MAX_ARRIVALS) {
      throw RuleError("bucle sin progreso: más de " + std::to_string(MAX_ARRIVALS) +
                          " nodos en un paso",
                      node.id);
    }
    set_node(node_id);
    pending_.reset();
    emit_shared({{"type", Json("node")}, {"node", Json(node.id)}});
    int n = match_->n;
    switch (node.kind) {
      case NodeKind::Auto:
        if (node.has_effects) run_code(node.effects, ctx_);
        take({{&node.transitions, {}}}, node_id);
        break;
      case NodeKind::Chance:
      case NodeKind::Phase:
        break;
      case NodeKind::Terminal: {
        Items it = iterate(eval_expr(node.payoff, ctx_), "payoff", ctx_);
        ValueVec payoffs;
        for (size_t k = 0; k < it.size; ++k) payoffs.push_back(expect_num(it[k], "payoff", ctx_));
        if (static_cast<int>(payoffs.size()) != n) {
          throw RuleError("el pago tiene " + std::to_string(payoffs.size()) + " valores para " +
                              std::to_string(n) + " asientos",
                          node.id);
        }
        terminal_ = true;
        payoffs_ = payoffs;
        if (record_) emit_shared({{"type", Json("end")}, {"payoffs", payoffs_json(g_, payoffs_)}});
        break;
      }
      case NodeKind::Decision: {
        int actor = static_cast<int>(expect_seat(eval_expr(node.actor, ctx_), n, "actor", ctx_));
        auto p = std::allocate_shared<Pending>(PoolAllocator<Pending>());
        p->order.push_back(actor);
        pending_ = p;
        require_choice(node, actor);
        break;
      }
      case NodeKind::Simultaneous: {
        Items it = iterate(eval_expr(node.actors, ctx_), "iteración", ctx_);
        std::vector<int> actors;
        for (size_t k = 0; k < it.size; ++k) {
          actors.push_back(static_cast<int>(expect_seat(it[k], n, "actors", ctx_)));
        }
        std::sort(actors.begin(), actors.end());
        actors.erase(std::unique(actors.begin(), actors.end()), actors.end());
        for (int s : actors) require_choice(node, s);
        auto p = std::allocate_shared<Pending>(PoolAllocator<Pending>());
        p->order.assign(actors.begin(), actors.end());
        pending_ = p;
        if (actors.empty()) resolve_simultaneous();
        break;
      }
      case NodeKind::Window: {
        Items el = iterate(eval_expr(node.eligible, ctx_), "iteración", ctx_);
        std::vector<int> eligible;
        for (size_t k = 0; k < el.size; ++k) {
          eligible.push_back(static_cast<int>(expect_seat(el[k], n, "eligible", ctx_)));
        }
        std::vector<int> order;
        if (node.order.defined) {
          Items pr = iterate(eval_expr(node.order, ctx_), "iteración", ctx_);
          for (size_t k = 0; k < pr.size; ++k) {
            int s = static_cast<int>(expect_seat(pr[k], n, "order", ctx_));
            if (std::find(eligible.begin(), eligible.end(), s) != eligible.end()) order.push_back(s);
          }
        }
        for (int s : eligible) {
          if (std::find(order.begin(), order.end(), s) == order.end()) order.push_back(s);
        }
        std::vector<int> unique;
        for (int s : order) {
          if (std::find(unique.begin(), unique.end(), s) == unique.end()) unique.push_back(s);
        }
        auto p = std::allocate_shared<Pending>(PoolAllocator<Pending>());
        p->order.assign(unique.begin(), unique.end());
        pending_ = p;
        if (unique.empty()) close_window(NO_SEAT, nullptr);
        break;
      }
    }
  }

  void require_choice(const NodeDef& node, int actor) {
    // Como la sonda de Python: un estado con el almacén actual en el nodo, sin escribir nada.
    bool found = false;
    enumerate_node(node, ctx_, actor, [&](const Action&) {
      found = true;
      return false;
    });
    if (!found) {
      throw RuleError("el asiento " + std::to_string(actor) + " no tiene ninguna acción legal",
                      node.id);
    }
  }

  void perform(const NodeDef& node, int actor, const Action& action, bool node_actor) {
    const ActionDef& a = *action.def;
    auto argc = static_cast<uint32_t>(action.args.size());
    run_code(a.effects, ctx_, actor, action.args.data(), argc);
    action_event(a, actor, action);
    EnvRef with_args{actor, action.args.data(), argc};
    EnvRef node_env{node_actor ? actor : NO_SEAT, nullptr, 0};
    take({{&a.transitions, with_args}, {&node.transitions, node_env}}, node.index);
  }

  void resolve_simultaneous() {
    const NodeDef& node = g_.node(node_);
    PoolVec<std::pair<int, Action>> submitted = pending_->submitted;
    std::stable_sort(submitted.begin(), submitted.end(),
                     [](const auto& x, const auto& y) { return x.first < y.first; });
    for (const auto& [actor, action] : submitted) {
      const ActionDef& a = *action.def;
      run_code(a.effects, ctx_, actor, action.args.data(),
               static_cast<uint32_t>(action.args.size()));
      action_event(a, actor, action);
    }
    if (node.has_resolve) run_code(node.resolve, ctx_);
    take({{&node.transitions, {}}}, node.index);
  }

  void respond(const NodeDef& node, int actor, const Action& action) {
    auto p = std::allocate_shared<Pending>(PoolAllocator<Pending>(), *pending_);
    p->submitted.emplace_back(actor, action);
    bool complete = p->submitted.size() == p->order.size();
    pending_ = p;
    if (node.mode == WindowMode::Collect) {
      emit_shared({{"type", Json("responded")}, {"seat", Json(int64_t(actor))}});
      if (!complete) return;
      auto response = [&](int s) -> const Action& {
        for (const auto& [seat, a] : p->submitted) {
          if (seat == s) return a;
        }
        throw RuleError("respuesta ausente");
      };
      if (record_) {
        JsonArray responses;
        for (int s : p->order) {
          responses.push_back(Json(JsonObject{{"seat", Json(int64_t(s))},
                                              {"name", Json(response(s).name(g_))}}));
        }
        emit_shared({{"type", Json("responses")}, {"responses", Json(std::move(responses))}});
      }
      for (int s : p->order) {
        const Action& a = response(s);
        if (!a.is_pass()) {
          Action chosen = a;
          close_window(s, &chosen);
          return;
        }
      }
      close_window(NO_SEAT, nullptr);
      return;
    }
    if (action.is_pass()) {
      emit_shared({{"type", Json("action")},
                   {"seat", Json(int64_t(actor))},
                   {"name", Json("pass")},
                   {"args", Json::object()}});
      if (complete) close_window(NO_SEAT, nullptr);
      return;
    }
    close_window(actor, &action);
  }

  void close_window(int actor, const Action* action) {
    const NodeDef& node = g_.node(node_);
    if (actor == NO_SEAT || action == nullptr) {
      take({{&node.transitions, {}}}, node.index);
    } else {
      perform(node, actor, *action, false);
    }
  }

  void action_event(const ActionDef& a, int actor, const Action& action) {
    if (!record_) return;
    const TypeTable& types = g_.types;
    Json full = action.to_json(g_);
    JsonObject full_obj{{"type", Json("action")},
                        {"seat", Json(int64_t(actor))},
                        {"name", Json(a.name)},
                        {"args", full["args"]}};
    auto full_ptr = std::make_shared<const Json>(Json(std::move(full_obj)));
    // Quien no ve la acción solo sabe que el asiento actuó.
    auto anonymous = std::make_shared<const Json>(
        Json(JsonObject{{"type", Json("action")}, {"seat", Json(int64_t(actor))}}));
    std::vector<JsonPtr> seen;
    int n = match_->n;
    for (int k = 0; k <= n; ++k) {
      int viewer = k == n ? PUBLIC : k;
      Frame probe;
      probe.viewer = viewer;
      probe.owner = actor;
      if (viewer == actor) {
        seen.push_back(full_ptr);
        continue;
      }
      if (!a.policy.allows(ctx_, probe)) {
        seen.push_back(anonymous);
        continue;
      }
      JsonObject args;
      bool everything = true;
      for (size_t i = 0; i < a.params.size(); ++i) {
        const ActionParamDef& p = a.params[i];
        const Value& v = action.args[i];
        if (p.policy.allows(ctx_, probe)) {
          args.emplace_back(p.name, types.to_json(v));
        } else if (p.size_policy.allows(ctx_, probe) && v.is_tuple_like()) {
          args.emplace_back(p.name, Json(JsonObject{{"size", Json(int64_t(v.tuple_size()))}}));
          everything = false;
        } else {
          args.emplace_back(p.name, hidden());
          everything = false;
        }
      }
      if (everything) {
        seen.push_back(full_ptr);
      } else {
        seen.push_back(std::make_shared<const Json>(Json(JsonObject{{"type", Json("action")},
                                                                    {"seat", Json(int64_t(actor))},
                                                                    {"name", Json(a.name)},
                                                                    {"args", Json(std::move(args))}})));
      }
    }
    JsonPtr pub = seen.back();
    seen.pop_back();
    events_.push_back(Event{full_ptr, std::move(seen), pub});
  }
};

std::shared_ptr<const Match> make_match(const GameDef& g, int n, const Json& given);

}  // namespace

// --- Acciones ----------------------------------------------------------------------------------

const char* status_name(Status s) {
  switch (s) {
    case Status::Chance:
      return "chance";
    case Status::Decision:
      return "decision";
    case Status::Terminal:
      return "terminal";
  }
  return "?";
}

Json Action::to_json(const GameDef& g) const {
  JsonObject args_json;
  if (def != nullptr) {
    for (size_t k = 0; k < def->params.size(); ++k) {
      args_json.emplace_back(def->params[k].name, g.types.to_json(args[k]));
    }
  }
  return Json(JsonObject{{"name", Json(name(g))}, {"args", Json(std::move(args_json))}});
}

uint64_t Action::hash() const {
  uint64_t h = mix64(def == nullptr ? 0x70617373ULL : reinterpret_cast<uintptr_t>(def));
  for (size_t k = 0; k < args.size(); ++k) h ^= positional_hash(k, hash_value(args[k]));
  return h;
}

bool Action::operator==(const Action& o) const {
  if (is_pass() || o.is_pass()) return is_pass() && o.is_pass();
  if (def->name != o.def->name || args.size() != o.args.size()) return false;
  for (size_t k = 0; k < args.size(); ++k) {
    if (!equals(args[k], o.args[k])) return false;
  }
  return true;
}

std::vector<int> competition_ranking(const ValueVec& scores) {
  std::vector<int> ranks;
  for (const auto& s : scores) {
    int better = 0;
    for (const auto& o : scores) {
      if (o.as_rational().compare(s.as_rational()) > 0) ++better;
    }
    ranks.push_back(1 + better);
  }
  return ranks;
}

Json payoffs_json(const GameDef& g, const ValueVec& payoffs) {
  JsonArray out;
  for (const auto& p : payoffs) out.push_back(g.types.to_json(p));
  return Json(std::move(out));
}

// --- Creación ----------------------------------------------------------------------------------

namespace {

Value initial_value(const GameDef& g, const Ctx& ctx, Value value, const Type& t) {
  if (t.kind != Type::Kind::Grid) return coerce(std::move(value), t, ctx);
  auto dim = [&](const std::variant<int64_t, std::string>& d) -> int64_t {
    if (std::holds_alternative<int64_t>(d)) return std::get<int64_t>(d);
    return (*ctx.params)[g.param_index.at(std::get<std::string>(d))].i;
  };
  int64_t w = dim(t.width), h = dim(t.height);
  Type::Kind inner = t.inner().kind;
  bool is_rows = value.is_tuple_like() && static_cast<int64_t>(value.tuple_size()) == h &&
                 inner != Type::Kind::List && inner != Type::Kind::Tuple;
  if (is_rows) {
    for (size_t r = 0; r < value.tuple_size(); ++r) {
      Value row = value.tuple_at(r);
      if (!row.is_tuple_like() || static_cast<int64_t>(row.tuple_size()) != w) {
        is_rows = false;
        break;
      }
    }
  }
  if (is_rows) return grid_from_rows(value, w, h, t, ctx);
  Value cell = coerce(std::move(value), t.inner(), ctx);
  ValueVec cells(static_cast<size_t>(w * h), cell);
  return Value::grid(static_cast<uint32_t>(w), static_cast<uint32_t>(h), std::move(cells));
}

std::shared_ptr<const Match> make_match(const GameDef& g, int n, const Json& given) {
  if (n < g.min_players || n > g.max_players) {
    throw InvalidParams("este juego admite de " + std::to_string(g.min_players) + " a " +
                        std::to_string(g.max_players) + " jugadores, no " + std::to_string(n));
  }
  std::vector<std::string> unknown;
  for (const auto& [k, v] : given.as_object()) {
    if (g.param_index.count(k) == 0 || k == "num_players") unknown.push_back(k);
  }
  if (!unknown.empty()) {
    std::sort(unknown.begin(), unknown.end());
    std::string listing;
    for (size_t k = 0; k < unknown.size(); ++k) listing += (k ? ", '" : "'") + unknown[k] + "'";
    throw InvalidParams("parámetros desconocidos: [" + listing + "]");
  }
  auto match = std::make_shared<Match>();
  match->n = n;
  ValueVec seats;
  for (int s = 0; s < n; ++s) seats.push_back(Value::integer(s));
  match->seats = Value::tuple(std::move(seats));
  match->params.assign(g.params.size(), Value());
  match->params[0] = Value::integer(n);
  ValueVec empty_store;
  Ctx ctx;
  ctx.game = &g;
  ctx.store = &empty_store;
  ctx.params = &match->params;
  ctx.n = n;
  ctx.seats = match->seats;
  for (size_t k = 1; k < g.params.size(); ++k) {
    const ParamDef& p = g.params[k];
    if (const Json* j = given.find(p.name)) {
      try {
        match->params[k] = coerce(g.types.decode(*j, *p.type), *p.type, ctx);
      } catch (const std::invalid_argument& exc) {
        throw InvalidParams("parámetro " + p.name + ": valor JSON inválido para " +
                            g.types.describe(*p.type) + ": " + j->dump());
      }
    } else {
      match->params[k] = coerce(eval_expr(p.default_value, ctx), *p.type, ctx);
    }
  }
  for (const auto& c : g.constraints) {
    if (!expect_bool(eval_expr(c.expr, ctx), "restricción", ctx)) throw InvalidParams(c.message);
  }
  return match;
}

ValueVec initial_store(const GameDef& g, const Match& match) {
  ValueVec empty_store;
  Ctx ctx;
  ctx.game = &g;
  ctx.store = &empty_store;
  ctx.params = &match.params;
  ctx.n = match.n;
  ctx.seats = match.seats;
  ValueVec store;
  for (const auto& var : g.vars) {
    if (var.type->kind == Type::Kind::PerPlayer) {
      ValueVec per;
      for (int s = 0; s < match.n; ++s) {
        ScopedFrame scope(ctx.machine(), var.init.frame);
        scope.frame.owner = s;
        Value v = ctx.machine().eval(var.init.chunk, ctx, scope.frame);
        per.push_back(initial_value(g, ctx, std::move(v), var.type->inner()));
      }
      store.push_back(Value::tuple(std::move(per)));
    } else {
      store.push_back(initial_value(g, ctx, eval_expr(var.init, ctx), *var.type));
    }
    if (var.range_lo.defined) check_range(ctx, var.index, store.back());
  }
  return store;
}

}  // namespace

State Game::new_state(int num_players, const Json& params, const ApplyOptions& opt) const {
  auto match = make_match(*def_, num_players, params.is_null() ? Json::object() : params);
  ValueVec store = initial_store(*def_, *match);
  if (def_->setup_is_random) {
    auto s = std::allocate_shared<StateNode>(PoolAllocator<StateNode>());
    s->game = def_;
    s->n = num_players;
    s->match = match;
    s->store = std::move(store);
    return State(s);
  }
  Tx tx(def_, match, store, -1, nullptr, nullptr, opt.events);
  tx.start();
  return State(tx.commit(nullptr, Step{Step::Kind::Start, -1, {}, {}, {}}, opt.history));
}

Action Game::decode_action(int node_index, const Json& data) const {
  return gh::decode_action(*def_, node_index, data);
}

Action decode_action(const GameDef& g, int node_index, const Json& data) {
  const Json* name_j = data.find("name");
  if (node_index < 0) throw IllegalAction("no hay acciones en este estado");
  const NodeDef& node = g.node(node_index);
  std::string name = name_j != nullptr && name_j->is_string() ? name_j->as_string() : "";
  if (node.kind == NodeKind::Window && name == "pass") return Action{};
  uint32_t id = g.action_name_id(name);
  const ActionDef* a = id == UINT32_MAX ? nullptr : node.action(id);
  if (a == nullptr) {
    throw IllegalAction("acción desconocida en " + node.id + ": " +
                        (name_j != nullptr ? name_j->dump() : "None"));
  }
  const Json* given = data.find("args");
  Json empty = Json::object();
  if (given == nullptr) given = &empty;
  if (!given->is_object()) {
    throw IllegalAction("argumentos inválidos para " + name + ": se esperaba un objeto");
  }
  ValueVec values;
  for (const auto& p : a->params) {
    const Json* v = given->find(p.name);
    if (v == nullptr) throw IllegalAction("argumentos inválidos para " + name + ": '" + p.name + "'");
    try {
      values.push_back(g.types.decode(*v, *p.type));
    } catch (const std::invalid_argument& exc) {
      throw IllegalAction("argumentos inválidos para " + name + ": " + exc.what());
    }
  }
  return Action{a, Args(values)};
}

// --- Consultas ---------------------------------------------------------------------------------

Status State::status() const {
  if (s_->terminal) return Status::Terminal;
  if (s_->node < 0 || game().node(s_->node).kind == NodeKind::Chance) return Status::Chance;
  return Status::Decision;
}

std::vector<int> State::active_seats() const {
  std::vector<int> out;
  if (status() != Status::Decision || !s_->pending) return out;
  for (int s : s_->pending->order) {
    if (!s_->pending->responded(s)) out.push_back(s);
  }
  const NodeDef& node = game().node(s_->node);
  if (node.kind == NodeKind::Window && node.mode == WindowMode::Priority && out.size() > 1) {
    out.resize(1);
  }
  return out;
}

bool State::is_active(int seat) const {
  if (status() != Status::Decision || !s_->pending) return false;
  const Pending& p = *s_->pending;
  const NodeDef& node = game().node(s_->node);
  bool priority = node.kind == NodeKind::Window && node.mode == WindowMode::Priority;
  for (int s : p.order) {
    if (p.responded(s)) continue;
    if (s == seat) return true;
    if (priority) return false;  // en prioridad solo actúa el primero que no ha respondido
  }
  return false;
}

int State::first_active() const {
  if (status() != Status::Decision || !s_->pending) return -1;
  for (int s : s_->pending->order) {
    if (!s_->pending->responded(s)) return s;
  }
  return -1;
}

const Value& State::value(const std::string& var) const {
  return s_->store.at(game().var_index.at(var));
}

void State::for_each_legal(int seat, const std::function<bool(const Action&)>& visit) const {
  if (!is_active(seat)) return;
  const NodeDef& node = game().node(s_->node);
  Ctx ctx = query_ctx(*s_);
  if (!enumerate_node(node, ctx, seat, visit)) return;
  if (node.kind == NodeKind::Window) visit(Action{});
}

std::vector<Action> State::legal_actions(int seat) const {
  std::vector<Action> out;
  for_each_legal(seat, [&](const Action& a) {
    out.push_back(a);
    return true;
  });
  return out;
}

size_t State::count_legal(int seat) const {
  size_t count = 0;
  for_each_legal(seat, [&](const Action&) {
    ++count;
    return true;
  });
  return count;
}

std::optional<std::vector<int>> State::ranking() const {
  if (!s_->terminal) return std::nullopt;
  const NodeDef& node = game().node(s_->node);
  if (!node.rank.defined) return competition_ranking(s_->payoffs);
  Ctx ctx = query_ctx(*s_);
  Items it = iterate(eval_expr(node.rank, ctx), "rank", ctx);
  std::vector<int> ranks;
  bool ok = static_cast<int>(it.size) == s_->n;
  for (size_t k = 0; k < it.size; ++k) {
    const Value& r = it[k];
    if (r.tag != Tag::Int || r.i < 1 || r.i > s_->n) ok = false;
    ranks.push_back(r.tag == Tag::Int ? static_cast<int>(r.i) : 0);
  }
  if (!ok) throw RuleError("'rank' debe dar un puesto de 1 a " + std::to_string(s_->n) + " por asiento");
  return ranks;
}

Json State::options(int seat, const std::string* name, const Json* args) const {
  JsonArray out;
  std::vector<int> active = active_seats();
  if (std::find(active.begin(), active.end(), seat) == active.end()) return Json(out);
  const GameDef& g = game();
  const NodeDef& node = g.node(s_->node);
  Ctx ctx = query_ctx(*s_);
  if (name == nullptr) {
    for (const auto& a : node.actions) {
      bool any = false;
      ValueVec scratch;
      complete(a, ctx, seat, scratch, 0, [&](const Action&) {
        any = true;
        return false;
      });
      if (any) out.push_back(Json(a.name));
    }
    if (node.kind == NodeKind::Window) out.push_back(Json("pass"));
    return Json(out);
  }
  uint32_t id = g.action_name_id(*name);
  const ActionDef* a = id == UINT32_MAX ? nullptr : node.action(id);
  if (a == nullptr) return Json(out);
  ValueVec chosen;
  const JsonObject empty;
  const JsonObject& given = args != nullptr && args->is_object() ? args->as_object() : empty;
  size_t i = given.size();
  if (i >= a->params.size()) return Json(out);
  for (size_t k = 0; k < i; ++k) {
    if (given[k].first != a->params[k].name) return Json(out);
    chosen.push_back(g.types.decode(given[k].second, *a->params[k].type));
  }
  Items values = iterate(eval_expr(a->params[i].domain, ctx, seat, chosen.data(),
                                   static_cast<uint32_t>(i)),
                         "dominio", ctx);
  for (size_t k = 0; k < values.size; ++k) {
    ValueVec attempt = chosen;
    attempt.push_back(values[k]);
    bool any = false;
    complete(*a, ctx, seat, attempt, i + 1, [&](const Action&) {
      any = true;
      return false;
    });
    if (any) out.push_back(g.types.to_json(values[k]));
  }
  return Json(out);
}

namespace {

// Comprueba la legalidad y devuelve la acción en forma canónica (como `_canonical`).
Action canonical(const State& st, int seat, const Action& action) {
  if (st.status() != Status::Decision) {
    throw IllegalAction(std::string("no se puede actuar: el estado es ") +
                        status_name(st.status()));
  }
  std::vector<int> active = st.active_seats();
  if (std::find(active.begin(), active.end(), seat) == active.end()) {
    throw IllegalAction("el asiento " + std::to_string(seat) + " no puede actuar ahora");
  }
  const GameDef& g = st.game();
  const NodeDef& node = g.node(st.node());
  if (node.kind == NodeKind::Window && action.is_pass()) return Action{};
  if (action.def == nullptr || action.def->node != node.index) {
    throw IllegalAction("acción desconocida en " + node.id + ": " + action.name(g));
  }
  const ActionDef& a = *action.def;
  Ctx ctx = query_ctx(st.data());
  ValueVec args;
  for (size_t k = 0; k < a.params.size(); ++k) {
    Value canonical_value;
    if (!member(a.params[k], ctx, seat, args, action.args.at(k), canonical_value)) {
      throw IllegalAction(a.name + ": valor no permitido para " + a.params[k].name + ": " +
                          g.types.to_json(action.args[k]).dump());
    }
    args.push_back(std::move(canonical_value));
  }
  if (a.requires_expr.defined) {
    Value ok = eval_expr(a.requires_expr, ctx, seat, args.data(), static_cast<uint32_t>(args.size()));
    if (!expect_bool(ok, "requires", ctx)) {
      throw IllegalAction(a.name + ": no se cumple la condición de la acción");
    }
  }
  return Action{&a, Args(args)};
}

}  // namespace

std::optional<std::string> State::illegal_reason(int seat, const Action& action) const {
  try {
    canonical(*this, seat, action);
  } catch (const IllegalAction& exc) {
    return std::string(exc.what());
  }
  return std::nullopt;
}

Action State::decode_action(const Json& data) const {
  return gh::decode_action(game(), s_->node, data);
}

// --- Transiciones ------------------------------------------------------------------------------

State State::apply_action(int seat, const Action& action, const ApplyOptions& opt) const {
  Action canon = opt.validate ? canonical(*this, seat, action) : action;
  Tx tx(s_->game, s_->match, s_->store, s_->node, s_->pending, nullptr, opt.events);
  tx.act(seat, canon);
  Step step{Step::Kind::Action, seat, canon, {}, {}};
  return State(tx.commit(s_, std::move(step), opt.history));
}

namespace {

void require_chance(const State& st) {
  if (st.status() != Status::Chance) {
    throw IllegalAction(std::string("el estado es ") + status_name(st.status()) + ", no chance");
  }
}

}  // namespace

std::vector<std::pair<Outcome, Rational>> State::chance_outcomes(size_t limit) const {
  require_chance(*this);
  std::vector<std::pair<Outcome, Rational>> results;
  std::vector<std::pair<Outcome, Rational>> pending{{Outcome{}, Rational::integer(1)}};
  while (!pending.empty()) {
    auto [prefix, prob] = std::move(pending.back());
    pending.pop_back();
    ScriptedDraws draws(prefix);
    try {
      Tx tx(s_->game, s_->match, s_->store, s_->node, s_->pending, &draws, false);
      tx.run_chance();
    } catch (NeedDraw& need) {
      size_t options = need.probs.empty() ? static_cast<size_t>(need.n) : need.probs.size();
      if (results.size() + pending.size() + options > limit) {
        throw NotEnumerable("más de " + std::to_string(limit) + " resultados de azar");
      }
      for (size_t d = 0; d < options; ++d) {
        Rational p = need.probs.empty() ? Rational::of(1, need.n) : need.probs[d];
        if (!need.probs.empty() && p.num == 0) continue;
        Outcome next = prefix;
        next.push_back(static_cast<int64_t>(d));
        // Un producto que no cabe en 64 bits se recalcula al final (si el resultado se completa).
        Rational q{0, 0};
        if (prob.den != 0) {
          try {
            q = prob * p;
          } catch (const RuleError&) {
            q = Rational{0, 0};
          }
        }
        pending.emplace_back(std::move(next), q);
      }
      continue;
    }
    results.emplace_back(std::move(prefix), prob);
  }
  // Las probabilidades que no cupieron en 64 bits por el camino: exactas, o un desbordamiento
  // (solo si la enumeración termina; si no, ya se lanzó NotEnumerable como en Python).
  for (auto& [o, p] : results) {
    if (p.den == 0) p = outcome_probability(o);
  }
  std::sort(results.begin(), results.end(), [](const auto& a, const auto& b) {
    if (a.first != b.first) return a.first < b.first;
    return a.second.compare(b.second) < 0;
  });
  return results;
}

Outcome State::sample_chance(Pcg32& rng) const {
  require_chance(*this);
  RngDraws draws(rng);
  Tx tx(s_->game, s_->match, s_->store, s_->node, s_->pending, &draws, false);
  tx.run_chance();
  return draws.taken;
}

State State::apply_chance(const Outcome& outcome, const ApplyOptions& opt) const {
  require_chance(*this);
  ScriptedDraws draws(outcome);
  auto tx = std::make_unique<Tx>(s_->game, s_->match, s_->store, s_->node, s_->pending, &draws,
                                 opt.events);
  try {
    tx->run_chance();
  } catch (const NeedDraw&) {
    std::string listing;
    for (size_t k = 0; k < outcome.size(); ++k) listing += (k ? ", " : "") + std::to_string(outcome[k]);
    throw IllegalAction("resultado de azar incompleto: (" + listing + ")");
  }
  if (!draws.finished()) {
    std::string listing;
    for (size_t k = 0; k < outcome.size(); ++k) listing += (k ? ", " : "") + std::to_string(outcome[k]);
    throw IllegalAction("resultado de azar con sorteos de más: (" + listing + ")");
  }
  Step step{Step::Kind::Chance, -1, {}, outcome, {}};
  return State(tx->commit(s_, std::move(step), opt.history));
}

State State::sample_and_apply(Pcg32& rng, const ApplyOptions& opt) const {
  require_chance(*this);
  RngDraws draws(rng);
  Tx tx(s_->game, s_->match, s_->store, s_->node, s_->pending, &draws, opt.events);
  tx.run_chance();
  Step step{Step::Kind::Chance, -1, {}, draws.taken, {}};
  return State(tx.commit(s_, std::move(step), opt.history));
}

std::optional<std::pair<int64_t, std::vector<Rational>>> State::next_draw(
    const Outcome& prefix) const {
  require_chance(*this);
  ScriptedDraws draws(prefix);
  try {
    Tx tx(s_->game, s_->match, s_->store, s_->node, s_->pending, &draws, false);
    tx.run_chance();
  } catch (NeedDraw& need) {
    return std::make_pair(need.n, need.probs);
  }
  if (!draws.finished()) throw IllegalAction("resultado de azar con sorteos de más");
  return std::nullopt;
}

Rational State::outcome_probability(const Outcome& outcome) const {
  require_chance(*this);
  ScriptedDraws draws(outcome);
  draws.track_probability = true;
  try {
    Tx tx(s_->game, s_->match, s_->store, s_->node, s_->pending, &draws, false);
    tx.run_chance();
  } catch (const NeedDraw&) {
    throw IllegalAction("resultado de azar incompleto");
  }
  return draws.probability;
}

State State::edited(const Json&) const {
  throw EngineError("State.edited no está disponible en el motor C++ (solo para los tests de Nomos)");
}

Value State::evaluate(const Json& expr) const {
  Expr e = game().compile_expression(expr);
  Ctx ctx = query_ctx(*s_);
  return eval_expr(e, ctx);
}

// --- Información -------------------------------------------------------------------------------

namespace {

bool holds_zones(const Type& t) {
  const Type* x = &t;
  while (x->kind == Type::Kind::List) x = &x->inner();
  return x->kind == Type::Kind::Zone || x->kind == Type::Kind::Bag;
}

Json redact_zone(Ctx& ctx, const Value& zone_v, const VarDef& var, Frame& frame) {
  const TypeTable& types = ctx.game->types;
  const ArrayObj* z = zone_v.arr();
  PoolVec<bool> shown;
  for (uint32_t k = 0; k < z->n; ++k) {
    frame.face_up = static_cast<int8_t>(z->faces()[k]);
    shown.push_back(var.policy.allows(ctx, frame));
  }
  frame.face_up = -1;
  bool size_shown = var.size_policy.allows(ctx, frame);
  if (size_shown && z->a != 0) {
    JsonArray items;
    for (uint32_t k = 0; k < z->n; ++k) {
      items.push_back(shown[k] ? types.to_json(z->items()[k]) : hidden());
    }
    return Json(JsonObject{{"size", Json(int64_t(z->n))}, {"items", Json(std::move(items))}});
  }
  JsonArray visible;
  for (uint32_t k = 0; k < z->n; ++k) {
    if (shown[k]) visible.push_back(types.to_json(z->items()[k]));
  }
  if (size_shown) {
    return Json(JsonObject{{"size", Json(int64_t(z->n))}, {"items", Json(std::move(visible))}});
  }
  if (visible.empty()) return hidden();
  return Json(JsonObject{{"items", Json(std::move(visible))}});
}

Json redact(Ctx& ctx, const Value& value, const Type& t, const VarDef& var, Frame& frame) {
  if (t.kind == Type::Kind::PerPlayer) {
    JsonArray out;
    int32_t saved = frame.owner;
    for (size_t s = 0; s < value.tuple_size(); ++s) {
      frame.owner = static_cast<int32_t>(s);
      out.push_back(redact(ctx, value.tuple_at(s), t.inner(), var, frame));
    }
    frame.owner = saved;
    return Json(std::move(out));
  }
  if (t.kind == Type::Kind::Zone || t.kind == Type::Kind::Bag) {
    return redact_zone(ctx, value, var, frame);
  }
  if (t.kind == Type::Kind::List && holds_zones(t)) {
    JsonArray out;
    for (size_t k = 0; k < value.tuple_size(); ++k) {
      out.push_back(redact(ctx, value.tuple_at(k), t.inner(), var, frame));
    }
    return Json(std::move(out));
  }
  return var.policy.allows(ctx, frame) ? ctx.game->types.to_json(value) : hidden();
}

Json snapshot_value(const TypeTable& types, const Value& v) {
  if (v.tag == Tag::Zone) {
    const ArrayObj* z = v.arr();
    JsonArray items, up;
    for (uint32_t k = 0; k < z->n; ++k) {
      items.push_back(types.to_json(z->items()[k]));
      if (z->faces()[k]) up.push_back(Json(int64_t(k)));
    }
    JsonObject snap{{"items", Json(std::move(items))}};
    if (!up.empty()) snap.emplace_back("face_up", Json(std::move(up)));
    return Json(std::move(snap));
  }
  if (v.is_tuple_like()) {
    JsonArray out;
    for (size_t k = 0; k < v.tuple_size(); ++k) out.push_back(snapshot_value(types, v.tuple_at(k)));
    return Json(std::move(out));
  }
  return types.to_json(v);
}

}  // namespace

Json State::view(int seat) const {
  const GameDef& g = game();
  Ctx ctx = query_ctx(*s_);
  JsonObject state;
  for (const auto& var : g.vars) {
    Frame frame;
    frame.viewer = seat;
    state.emplace_back(var.name, redact(ctx, s_->store[var.index], *var.type, var, frame));
  }
  JsonArray active;
  for (int s : active_seats()) active.push_back(Json(int64_t(s)));
  JsonObject view{{"node", s_->node < 0 ? Json(nullptr) : Json(g.node(s_->node).id)},
                  {"status", Json(status_name(status()))},
                  {"active", Json(std::move(active))},
                  {"state", Json(std::move(state))}};
  if (s_->pending && status() == Status::Decision) {
    std::vector<int> responded;
    for (const auto& [s, a] : s_->pending->submitted) responded.push_back(s);
    std::sort(responded.begin(), responded.end());
    responded.erase(std::unique(responded.begin(), responded.end()), responded.end());
    JsonArray r;
    for (int s : responded) r.push_back(Json(int64_t(s)));
    view.emplace_back("responded", Json(std::move(r)));
  }
  if (s_->terminal) view.emplace_back("payoffs", payoffs_json(g, s_->payoffs));
  return Json(std::move(view));
}

Json State::events(int seat) const {
  JsonArray out;
  for (const auto& e : s_->step.events) {
    if (const Json* j = e.for_seat(seat)) out.push_back(*j);
  }
  return Json(std::move(out));
}

Json State::snapshot() const {
  const GameDef& g = game();
  JsonObject store;
  for (const auto& var : g.vars) store.emplace_back(var.name, snapshot_value(g.types, s_->store[var.index]));
  JsonObject snap{{"node", s_->node < 0 ? Json(nullptr) : Json(g.node(s_->node).id)},
                  {"store", Json(std::move(store))}};
  if (s_->pending) snap.emplace_back("pending", pending_json(g, *s_->pending));
  if (s_->terminal) snap.emplace_back("payoffs", payoffs_json(g, s_->payoffs));
  return Json(std::move(snap));
}

std::string State::snapshot_text() const { return snapshot().dump(); }

std::string State::digest() const { return Sha256::hex(snapshot_text()); }

std::vector<State> State::path() const {
  std::vector<State> states;
  for (auto s = s_; s; s = s->parent) states.push_back(State(s));
  std::reverse(states.begin(), states.end());
  return states;
}

std::string State::observation_digest(int seat) const {
  Json observation(JsonObject{{"view", view(seat)}, {"events", events(seat)}});
  return Sha256::hex(observation.dump());
}

std::string State::information_state(int seat) const {
  Sha256 h;
  for (const auto& st : path()) {
    Json observation(JsonObject{{"view", st.view(seat)}, {"events", st.events(seat)}});
    h.update(observation.dump());
  }
  return h.hexdigest();
}

uint64_t State::hash() const {
  uint64_t h = mix64(0x7374617465ULL ^ static_cast<uint64_t>(s_->node + 1));
  for (size_t k = 0; k < s_->store.size(); ++k) h ^= positional_hash(k, hash_value(s_->store[k]));
  if (s_->pending) {
    uint64_t p = mix64(0x70656e64ULL);
    for (int s : s_->pending->order) p = mix64(p ^ static_cast<uint64_t>(s));
    for (const auto& [s, a] : s_->pending->submitted) {
      p = mix64(p ^ (static_cast<uint64_t>(s) << 32) ^ a.hash());
    }
    h ^= p;
  }
  if (s_->terminal) {
    for (size_t k = 0; k < s_->payoffs.size(); ++k) h ^= positional_hash(k + 1000, hash_value(s_->payoffs[k]));
  }
  return h;
}

void set_transition_trace(std::vector<const TransitionDef*>* trace) {
  g_transition_trace = trace;
}

}  // namespace gh
