// SPDX-License-Identifier: Apache-2.0
// Algoritmos sobre el motor C++ (F8): perft, alfa-beta con tabla de transposiciones, MCTS,
// análisis retrógrado y CFR. Los estados son inmutables y comparten estructura con su padre, así
// que "deshacer" una jugada es volver al estado anterior (sin copiar), y cada estado tiene un hash
// estructural de 128 bits (Zobrist automático) para las tablas de transposiciones.
#pragma once

#include <cstdint>
#include <functional>
#include <optional>
#include <string>
#include <unordered_map>
#include <vector>

#include "gamehub/state.hpp"

namespace gh {

// Opciones de las transiciones de búsqueda: sin eventos, sin historial, sin validar (las acciones
// salen de legal_actions del mismo estado).
constexpr ApplyOptions SEARCH{false, false, false};

// Clave de 128 bits de un estado (dos hashes estructurales independientes).
struct StateKey {
  uint64_t a = 0, b = 0;
  bool operator==(const StateKey& o) const { return a == o.a && b == o.b; }
};
struct StateKeyHash {
  size_t operator()(const StateKey& k) const { return static_cast<size_t>(k.a ^ (k.b * 31)); }
};
StateKey state_key(const State& s);

// --- Perft -------------------------------------------------------------------------------------

// Secuencias de jugadas legales hasta `depth` (como gamehub.analysis.perft): cada nivel es una
// jugada del primer asiento activo; el azar suma todos sus resultados; `skip`, nombres de
// acciones que no cuentan.
uint64_t perft(const State& s, int depth, const std::vector<std::string>& skip = {});
std::vector<std::pair<Action, uint64_t>> perft_divide(const State& s, int depth,
                                                      const std::vector<std::string>& skip = {});

// --- Alfa-beta ---------------------------------------------------------------------------------

struct AlphaBetaResult {
  Rational value;             // para el asiento 0
  Rational total;             // la suma constante de los pagos
  std::vector<size_t> best;   // índices (en legal_actions) de las jugadas óptimas en la raíz
  std::vector<std::string> pv;  // variación principal (JSON de cada jugada, o "azar:…")
  uint64_t states = 0;        // entradas de la tabla de transposiciones
  uint64_t nodes = 0;         // nodos visitados
};

// Minimax con poda alfa-beta para dos jugadores de suma constante, expectimax en el azar y tabla
// de transposiciones (como gamehub.analysis.search.alphabeta, en aritmética exacta). Lanza
// EngineError si los pagos no suman siempre lo mismo o si se superan `max_nodes`.
AlphaBetaResult alphabeta(const State& root, uint64_t max_nodes = 100'000'000);

// --- Ganar, empatar o perder ------------------------------------------------------------------

struct WdlResult {
  int outcome = 0;           // para el asiento 0: 1 gana, 0 tablas, -1 pierde
  uint64_t nodes = 0;
  uint64_t table_hits = 0;
  double seconds = 0;
  std::vector<int> best;     // en la raíz: las jugadas que consiguen el resultado (si se piden)
};

// Resuelve un juego determinista de dos jugadores y suma cero en términos de ganar, empatar o
// perder (el signo de la diferencia de pagos) con búsquedas de ventana nula, una tabla de
// transposiciones de tamaño fijo (2^table_bits entradas, claves de 128 bits) y la heurística de
// historia para ordenar las jugadas; con `heuristic` (el nombre de una heurística del juego, F9),
// sus prioridades y su orden van antes que la historia. `threads` > 1: varios hilos comparten la
// tabla (Lazy SMP); cada uno con su copia del juego. `moves`: resuelve la posición a la que se
// llega con esas jugadas (el JSON de cada acción) en vez de la inicial.
WdlResult solve_wdl(const Game& game, int num_players, const Json& params, int table_bits = 24,
                    int threads = 1, uint64_t max_nodes = UINT64_MAX, double max_seconds = 0,
                    const std::string& heuristic = "", const std::vector<Json>& moves = {});

// --- MCTS --------------------------------------------------------------------------------------

struct MctsResult {
  std::vector<Action> actions;     // las acciones legales de la raíz
  std::vector<uint64_t> visits;    // visitas de cada una
  std::vector<double> values;      // valor medio para quien decide en la raíz
  size_t best = 0;                 // la más visitada
  uint64_t simulations = 0;
};

// UCT con partidas aleatorias hasta el final: n jugadores (cada nodo maximiza el pago de quien
// decide), azar muestreado. Determinista con la semilla; con `max_seconds` > 0 para además al
// pasar ese tiempo (al menos una simulación).
MctsResult mcts(const State& root, uint64_t simulations, double c = 1.4, uint64_t seed = 0,
                int max_rollout = 10'000, double max_seconds = 0);

// --- Análisis retrógrado -----------------------------------------------------------------------

struct RetroResult {
  // Resultado de la raíz para quien decide en ella: 1 gana, 0 tablas, -1 pierde.
  int outcome = 0;
  uint64_t positions = 0;
  uint64_t wins = 0, draws = 0, losses = 0;  // posiciones según quien decide en ellas
  int depth = 0;  // distancia (en jugadas) del resultado con juego óptimo desde la raíz
};

// Juegos deterministas de dos jugadores y suma cero (ganar, perder o empatar según el signo de
// los pagos), con ciclos o sin ellos: se recorre todo el grafo de estados y se etiqueta hacia
// atrás desde los finales; lo que queda sin etiquetar (repeticiones infinitas) son tablas.
RetroResult retrograde(const State& root, uint64_t max_positions = 50'000'000);

}  // namespace gh
