// SPDX-License-Identifier: Apache-2.0
// Números globales de acción (ADR-079): la especificación la calcula
// `gamehub.analysis.action_space` desde la IR (bloques por firma, universos de los parámetros) y
// aquí se codifica y descodifica rápido (para el puente con OpenSpiel y el aprendizaje).
#pragma once

#include <cstdint>
#include <memory>
#include <optional>
#include <string>
#include <vector>

#include "gamehub/state.hpp"

namespace gh {

struct Universe {
  enum class Kind : uint8_t { Bool, Enum, Int, Cell, Struct, Tuple, Option, Subset } kind;
  int64_t size = 0;
  uint32_t type = 0;               // enum / struct
  std::vector<int64_t> ordinals;   // enum: los valores admitidos (ordinales)
  int64_t lo = 0, hi = 0;          // int, subset (tamaños)
  int64_t rows = 0, cols = 0;      // cell
  std::vector<Universe> parts;     // struct / tuple; option y subset: parts[0]
  std::vector<int64_t> strides;    // struct / tuple (base mixta, el primero más significativo)

  int64_t rank(const Value& v) const;  // -1 si el valor no está en el universo
  Value unrank(int64_t k) const;
};

class ActionSpace {
 public:
  ActionSpace(std::shared_ptr<const GameDef> game, const Json& spec);

  int64_t size() const { return size_; }
  // El número de una acción del nodo dado (-1 si queda fuera del espacio).
  int64_t encode(int node, const Action& action) const;
  // La acción de un número en el nodo dado (nullopt si el número no es de ese nodo).
  std::optional<Action> decode(int node, int64_t id) const;
  // Los números de las acciones legales de un asiento (en el orden de legal_actions).
  std::vector<int64_t> legal_ids(const State& state, int seat) const;

 private:
  struct Block {
    std::string name;
    int64_t offset = 0, size = 0;
    std::vector<Universe> params;
    std::vector<int64_t> strides;
  };
  struct Entry {
    const ActionDef* def;  // nullptr = pass
    size_t block;
  };
  std::shared_ptr<const GameDef> game_;
  std::vector<Block> blocks_;
  std::vector<std::vector<Entry>> nodes_;  // por índice de nodo
  int64_t size_ = 0;
};

}  // namespace gh
