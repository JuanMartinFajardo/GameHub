// SPDX-License-Identifier: Apache-2.0
// Mide partidas aleatorias por segundo de un juego (su IR en JSON): gamehub_bench JUEGO.ir.json
// [partidas] [jugadores]. Para perfilar el núcleo sin pasar por Python.
#include <cstdio>
#include <fstream>
#include <sstream>

#include "gamehub/playout.hpp"

int main(int argc, char** argv) {
  if (argc < 2) {
    std::fprintf(stderr, "uso: %s JUEGO.ir.json [partidas] [jugadores]\n", argv[0]);
    return 2;
  }
  std::ifstream in(argv[1]);
  std::stringstream text;
  text << in.rdbuf();
  gh::Game game = gh::Game::from_text(text.str());
  uint64_t games = argc > 2 ? std::strtoull(argv[2], nullptr, 10) : 10000;
  int n = argc > 3 ? std::atoi(argv[3]) : game.def().min_players;
  gh::PlayoutReport r = gh::random_playouts(game, n, gh::Json::object(), 0, games, 10000);
  std::printf("%s: %llu partidas en %.2f s (%.0f/s), %.1f pasos de media, %zu errores\n",
              game.def().id.c_str(), static_cast<unsigned long long>(r.games), r.seconds,
              r.games / r.seconds, double(r.steps) / double(r.games), r.errors.size());
  return 0;
}
