// SPDX-License-Identifier: Apache-2.0
// Forma extensiva y CFR en C++ (F8): el mismo árbol que `gamehub.analysis.tree.build_tree`
// (preorden, azar agrupado por estado y eventos, conjuntos de información por la clave SHA-256 de
// lo observado con recuerdo perfecto) y el mismo CFR/CFR+ que `gamehub.analysis.cfr`, con las
// mismas operaciones en coma flotante: las estrategias coinciden con las de Python.
#pragma once

#include <cstdint>
#include <string>
#include <unordered_map>
#include <vector>

#include "gamehub/sha256.hpp"
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

// MCCFR (Lanctot et al., 2009) sin construir el árbol: los conjuntos de información se identifican
// sobre la marcha con las mismas claves que `build_tree` (SHA-256 encadenado de lo observado).
// Muestreo externo (se exploran todas las acciones de quien actualiza) o de resultados (un solo
// camino por iteración, con pesos de importancia y exploración `epsilon`).
class Mccfr {
 public:
  enum class Sampling : uint8_t { External, Outcome };
  Mccfr(const State& root, Sampling sampling, uint64_t seed = 0, double epsilon = 0.6);
  void run(int iterations);
  // La estrategia media de cada conjunto de información visitado: (asiento, clave, probabilidades).
  struct Entry {
    int player;
    std::string key;
    std::vector<double> average;
  };
  std::vector<Entry> policy() const;
  size_t infosets() const { return table_.size(); }
  // La estrategia media sobre un árbol completo (uniforme donde no se ha visitado).
  PolicyEF on_tree(const GameTreeEF& tree) const;

 private:
  struct Node {
    int player;
    std::vector<double> regret, strategy_sum;
  };
  double external(const State& s, const std::vector<Sha256>& keys, int player);
  double outcome(const State& s, const std::vector<Sha256>& keys, int player, double my_reach,
                 double opp_reach, double sample_reach);
  Node& node(int player, const std::vector<Sha256>& keys, size_t actions, std::string& key);
  std::vector<double> current(const Node& n) const;
  std::vector<Sha256> extend(const std::vector<Sha256>& keys, const State& child) const;
  size_t sample(const std::vector<double>& probs);
  State root_;
  Sampling sampling_;
  Pcg32 rng_;
  double epsilon_;
  std::unordered_map<std::string, Node> table_;
  std::vector<Sha256> root_keys_;
};

// Pago esperado de cada asiento, mejor respuesta y explotabilidad (convención de OpenSpiel).
std::vector<double> expected_values(const GameTreeEF& tree, const PolicyEF& policy);
double best_response_value(const GameTreeEF& tree, const PolicyEF& policy, int player);
double exploitability(const GameTreeEF& tree, const PolicyEF& policy);

}  // namespace gh
