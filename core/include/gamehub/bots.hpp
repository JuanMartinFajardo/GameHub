// SPDX-License-Identifier: Apache-2.0
// Bots (F9, ADR-084): reglas de prioridad, alfa-beta con heurística, MCTS/ISMCTS de bucle
// abierto y PIMC, y la determinización con la que juegan sin ver lo oculto.
#pragma once

#include <cstdint>
#include <memory>
#include <string>
#include <vector>

#include "gamehub/heuristic.hpp"
#include "gamehub/rng.hpp"
#include "gamehub/state.hpp"

namespace gh {

// --- Determinización ---------------------------------------------------------------------------

// ¿Hay algo que `seat` no vea (valores, cartas o envíos de otros)?
bool has_hidden(const State& s, int seat);

// Una muestra del estado coherente con lo que ve `seat`:
// - los elementos ocultos de zonas y bolsas (cartas) se reparten al azar entre los huecos
//   ocultos, por tipo (se conservan: son los mismos que `seat` no ve);
// - los demás valores ocultos (dados, números) se toman de una repetición de la partida con el
//   azar sorteado de nuevo y las mismas jugadas (si alguna deja de ser legal, se queda el valor);
// - los envíos pendientes de otros asientos (nodos simultáneos, ventanas `collect`) se olvidan.
// Si no hay nada oculto devuelve el mismo estado.
State determinize(const State& s, int seat, Pcg32& rng);

// --- Bots --------------------------------------------------------------------------------------

struct BotSpec {
  // random · first · greedy · alphabeta · mcts · ismcts · pimc
  std::string kind = "random";
  std::string heuristic;      // nombre ("" = la primera del juego, si tiene)
  bool use_heuristic = true;  // false: sin heurística aunque el juego tenga
  int depth = 0;              // alfa-beta: profundidad máxima (0 = la que dé el tiempo)
  uint64_t iterations = 0;    // MCTS/ISMCTS: simulaciones (0 = las que dé el tiempo)
  double seconds = 0.2;       // tiempo por jugada (0 = sin límite: depth/iterations mandan)
  double c = 1.4;             // exploración de UCT
  int samples = 8;            // PIMC: determinizaciones por jugada
  double greedy = 0.8;        // MCTS: probabilidad de seguir la heurística en las simulaciones
  int max_rollout = 2'000;    // MCTS: pasos máximos de una simulación
  int chance_samples = 6;     // alfa-beta: resultados de azar muestreados si no se enumeran
  uint64_t seed = 0;
};

// Lo que hizo el bot en su última jugada.
struct BotStats {
  uint64_t nodes = 0;        // alfa-beta: nodos; MCTS: simulaciones
  int depth = 0;             // alfa-beta: profundidad completada
  double value = 0;          // valor estimado de la jugada elegida
  double seconds = 0;
};

class Bot {
 public:
  Bot(std::shared_ptr<const GameDef> game, BotSpec spec, int seat);
  // Elige una acción legal para `seat` en `s` (el estado real: el bot solo usa lo que ve el
  // asiento; con información oculta, juega sobre determinizaciones).
  Action act(const State& s);
  const BotStats& stats() const { return stats_; }
  const BotSpec& spec() const { return spec_; }
  const HeuristicDef* heuristic() const { return h_; }

 private:
  Action greedy(const State& s, const std::vector<Action>& legal);
  std::vector<double> alphabeta_values(const State& s, const std::vector<Action>& legal,
                                       double seconds);
  std::vector<double> mcts_values(const State& s, const std::vector<Action>& legal,
                                  bool determinize_each, double seconds);

  std::shared_ptr<const GameDef> game_;
  BotSpec spec_;
  int seat_;
  const HeuristicDef* h_ = nullptr;
  Pcg32 rng_;
  BotStats stats_;
};

// Un paso de una partida registrada (análisis de balance).
struct StepTrace {
  int seat = -1;            // -1 = azar
  uint32_t legal = 0;       // acciones legales que tenía
  std::string action;       // nombre de la acción elegida
  std::vector<double> eval; // evaluación de la heurística para cada asiento tras el paso
};

// Una partida completa entre bots (el azar con PCG32(seed, 1), como `play_match`).
struct BotMatch {
  std::vector<StepTrace> trace;          // con `trace`
  std::vector<std::string> transitions;  // claves de las transiciones tomadas (con `trace`)
  ValueVec payoffs;
  std::vector<double> payoff_doubles;
  std::vector<int> ranking;  // posición de cada asiento (0 = primero)
  int steps = 0;
  bool truncated = false;
  std::vector<double> seconds;  // tiempo de cada asiento pensando
  std::string error;            // un RuleError (la partida no termina)
};
// Con `trace`, registra cada paso y las transiciones tomadas; con `eval` (el nombre de una
// heurística), también su evaluación de cada asiento después de cada paso o, con `features`, los
// valores de sus rasgos (asiento a asiento, uno detrás de otro).
BotMatch play_bots(const Game& game, int num_players, const Json& params,
                   const std::vector<BotSpec>& seats, uint64_t seed, int max_steps = 100'000,
                   bool trace = false, const std::string& eval = "", bool features = false);

// Kingmaking (n ≥ 3 jugadores): en las decisiones del último tramo de una partida entre bots
// (después de la fracción `late` de sus pasos), para el asiento que decide se estima con
// `rollouts` simulaciones por acción (bots codiciosos si el juego tiene heurística, al azar si
// no) su probabilidad de quedar primero y quién queda primero. Es un caso de kingmaking si con
// ninguna acción pasa del 5 % y la distribución del ganador cambia (distancia de variación total
// ≥ 0,25) según lo que elija.
struct KingmakingReport {
  int probes = 0;   // decisiones examinadas
  int events = 0;   // decisiones de kingmaking
  int steps = 0;
  std::string error;
};
KingmakingReport kingmaking(const Game& game, int num_players, const Json& params,
                            const std::vector<BotSpec>& seats, uint64_t seed, int rollouts = 24,
                            double late = 0.66, int max_steps = 100'000);

}  // namespace gh
