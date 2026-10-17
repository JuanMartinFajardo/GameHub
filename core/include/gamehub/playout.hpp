// SPDX-License-Identifier: Apache-2.0
// Partidas aleatorias en C++: las mismas que `gamehub.engine.match.fuzz` (partida i con la
// semilla `seed + i`, el azar con PCG32(semilla, 1) y el asiento s con PCG32(semilla, 1000 + s)),
// sin eventos ni historial. Sirven para medir el motor y para buscar errores de reglas.
#pragma once

#include <cstdint>
#include <string>
#include <utility>
#include <vector>

#include "gamehub/state.hpp"

namespace gh {

struct PlayoutReport {
  uint64_t games = 0;
  uint64_t completed = 0;
  uint64_t truncated = 0;
  uint64_t steps = 0;
  std::vector<std::pair<uint64_t, std::string>> errors;  // (semilla, mensaje)
  std::vector<Rational> payoff_sums;
  double seconds = 0;
  // Huella de las partidas (XOR de un hash de los pagos y pasos de cada una): dos motores que
  // juegan las mismas partidas dan la misma.
  uint64_t fingerprint = 0;
};

// Una partida aleatoria completa (o hasta `max_steps`). Devuelve el estado final.
State random_playout(const Game& game, int n, const Json& params, uint64_t seed, int max_steps,
                     uint64_t& steps, bool& truncated);
State random_playout(const Game& game, int n, const Json& params, uint64_t seed, int max_steps,
                     uint64_t& steps, bool& truncated, std::vector<Action>& scratch);

PlayoutReport random_playouts(const Game& game, int n, const Json& params, uint64_t seed,
                              uint64_t games, int max_steps);

}  // namespace gh
