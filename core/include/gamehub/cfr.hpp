// SPDX-License-Identifier: Apache-2.0
// Forma extensiva y CFR en C++ (F8): el mismo árbol que `gamehub.analysis.tree.build_tree`
// (preorden, azar agrupado por estado y eventos, conjuntos de información por la clave SHA-256 de
// lo observado con recuerdo perfecto) y el mismo CFR/CFR+ que `gamehub.analysis.cfr`, con las
// mismas operaciones en coma flotante: las estrategias coinciden con las de Python.
#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "gamehub/state.hpp"

namespace gh {

struct TreeNodeEF {
  enum class Kind : uint8_t { Terminal, Chance, Decision } kind = Kind::Terminal;
  int player = -1;
  int infoset = -1;
  std::vector<uint32_t> children;
  std::vector<double> probs;    // azar
  std::vector<double> payoffs;  // finales
};

struct InfoSetEF {
  int player = 0;
  std::string key;  // SHA-256 (hex) de lo observado
  size_t actions = 0;
  std::vector<uint32_t> nodes;
};

struct GameTreeEF {
  int num_players = 0;
  std::vector<TreeNodeEF> nodes;
  std::vector<InfoSetEF> infosets;
};

// La forma extensiva desde `root` (lanza EngineError si supera `max_nodes`).
GameTreeEF build_tree(const State& root, size_t max_nodes = 10'000'000,
                      size_t chance_limit = 100'000);

using PolicyEF = std::vector<std::vector<double>>;

class CfrSolver {
 public:
  CfrSolver(const GameTreeEF& tree, bool plus);
  void run(int iterations, int measure_every = 0);
  PolicyEF average() const;
  int iteration() const { return iteration_; }
  const std::vector<std::pair<int, double>>& convergence() const { return convergence_; }

 private:
  double traverse(uint32_t h, int player, double pi_i, double pi_o);
  void current_all();
  const GameTreeEF& tree_;
  bool plus_;
  int iteration_ = 0;
  std::vector<std::vector<double>> regret_, strategy_sum_, sigma_;
  std::vector<std::pair<int, double>> convergence_;
};

// Pago esperado de cada asiento, mejor respuesta y explotabilidad (convención de OpenSpiel).
std::vector<double> expected_values(const GameTreeEF& tree, const PolicyEF& policy);
double best_response_value(const GameTreeEF& tree, const PolicyEF& policy, int player);
double exploitability(const GameTreeEF& tree, const PolicyEF& policy);

}  // namespace gh
