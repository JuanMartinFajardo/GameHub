// SPDX-License-Identifier: Apache-2.0
#include "gamehub/heuristic.hpp"

#include <algorithm>
#include <numeric>

#include "gamehub/vm.hpp"

namespace gh {

namespace {

// Los argumentos de una regla: `me` y los de la acción.
struct RuleArgs {
  Value slots[8];
  ValueVec more;
  const Value* data() const { return more.empty() ? slots : more.data(); }
  RuleArgs(int seat, const Action& a, uint32_t arity) {
    if (a.args.size() != arity) throw EngineError("la regla de la heurística no encaja con la acción");
    if (arity + 1 <= 8) {
      slots[0] = Value::integer(seat);
      for (uint32_t k = 0; k < arity; ++k) slots[k + 1] = a.args[k];
    } else {
      more.push_back(Value::integer(seat));
      for (uint32_t k = 0; k < arity; ++k) more.push_back(a.args[k]);
    }
  }
};

}  // namespace

double to_double(const Rational& r) {
  return static_cast<double>(r.num) / static_cast<double>(r.den);
}

std::vector<Value> feature_values(const State& s, const HeuristicDef& h, int seat) {
  Ctx ctx = state_query_ctx(s);
  Value me = Value::integer(seat);
  std::vector<Value> out;
  out.reserve(h.features.size());
  for (const auto& f : h.features) out.push_back(eval_expr(f.body, ctx, NO_SEAT, &me, 1));
  return out;
}

Rational evaluate_exact(const State& s, const HeuristicDef& h, int seat) {
  Ctx ctx = state_query_ctx(s);
  Value me = Value::integer(seat);
  Rational total = Rational::integer(0);
  for (const auto& f : h.features) {
    total = total + f.weight * eval_expr(f.body, ctx, NO_SEAT, &me, 1).as_rational();
  }
  return total;
}

double evaluate(const State& s, const HeuristicDef& h, int seat) {
  Ctx ctx = state_query_ctx(s);
  Value me = Value::integer(seat);
  double total = 0;
  for (const auto& f : h.features) {
    total += to_double(f.weight) * to_double(eval_expr(f.body, ctx, NO_SEAT, &me, 1).as_rational());
  }
  return total;
}

int action_priority(const State& s, const HeuristicDef& h, int seat, const Action& a) {
  if (a.is_pass() || h.prefer.empty()) return NO_PRIORITY;
  Ctx ctx = state_query_ctx(s);
  for (size_t k = 0; k < h.prefer.size(); ++k) {
    const HeuristicRule& rule = h.prefer[k];
    if (rule.action != a.def->name_id) continue;
    RuleArgs args(seat, a, rule.arity);
    if (eval_expr(rule.expr, ctx, NO_SEAT, args.data(), rule.arity + 1).truthy()) {
      return static_cast<int>(k);
    }
  }
  return NO_PRIORITY;
}

Rational action_score_exact(const State& s, const HeuristicDef& h, int seat, const Action& a) {
  Rational total = Rational::integer(0);
  if (a.is_pass() || h.order.empty()) return total;
  Ctx ctx = state_query_ctx(s);
  for (const auto& rule : h.order) {
    if (rule.action != a.def->name_id) continue;
    RuleArgs args(seat, a, rule.arity);
    total = total + eval_expr(rule.expr, ctx, NO_SEAT, args.data(), rule.arity + 1).as_rational();
  }
  return total;
}

double action_score(const State& s, const HeuristicDef& h, int seat, const Action& a) {
  if (a.is_pass() || h.order.empty()) return 0;
  return to_double(action_score_exact(s, h, seat, a));
}

ActionKey action_key(const State& s, const HeuristicDef& h, int seat, const Action& a) {
  return ActionKey{action_priority(s, h, seat, a), action_score(s, h, seat, a)};
}

std::vector<size_t> order_actions(const State& s, const HeuristicDef& h, int seat,
                                  const std::vector<Action>& actions) {
  std::vector<ActionKey> keys;
  keys.reserve(actions.size());
  for (const auto& a : actions) keys.push_back(action_key(s, h, seat, a));
  std::vector<size_t> order(actions.size());
  std::iota(order.begin(), order.end(), 0);
  std::stable_sort(order.begin(), order.end(), [&](size_t x, size_t y) { return keys[x] < keys[y]; });
  return order;
}

}  // namespace gh
