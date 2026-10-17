// SPDX-License-Identifier: Apache-2.0
// Heurísticas (ADR-083): rasgos ponderados, prioridades y orden de las acciones, evaluados con
// la VM sobre un estado (como `gamehub.bots.heuristic`).
#pragma once

#include <vector>

#include "gamehub/state.hpp"

namespace gh {

// Prioridad de una acción que no cumple ninguna regla `prefer`.
constexpr int NO_PRIORITY = 1 << 30;

// Valores de los rasgos desde `seat` (en el orden de la heurística).
std::vector<Value> feature_values(const State& s, const HeuristicDef& h, int seat);
// Suma ponderada de los rasgos, exacta y como double (las búsquedas usan esta).
Rational evaluate_exact(const State& s, const HeuristicDef& h, int seat);
double evaluate(const State& s, const HeuristicDef& h, int seat);
// Índice de la primera regla `prefer` que cumple la acción, o NO_PRIORITY.
int action_priority(const State& s, const HeuristicDef& h, int seat, const Action& a);
// Suma de las claves `order` de la acción (0 si no tiene).
Rational action_score_exact(const State& s, const HeuristicDef& h, int seat, const Action& a);
double action_score(const State& s, const HeuristicDef& h, int seat, const Action& a);

// Clave de orden de una acción: menor = mejor.
struct ActionKey {
  int priority = NO_PRIORITY;
  double score = 0;
  bool operator<(const ActionKey& o) const {
    if (priority != o.priority) return priority < o.priority;
    return score > o.score;
  }
};
ActionKey action_key(const State& s, const HeuristicDef& h, int seat, const Action& a);
// Índices de `actions` de mejor a peor (estable: a igual clave, el orden legal).
std::vector<size_t> order_actions(const State& s, const HeuristicDef& h, int seat,
                                  const std::vector<Action>& actions);

double to_double(const Rational& r);

}  // namespace gh
