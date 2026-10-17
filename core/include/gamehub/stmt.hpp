// SPDX-License-Identifier: Apache-2.0
// Sentencias (efectos) de la IR: árboles de nodos C++ cuyas expresiones son código de bytes.
// Modifican el almacén de la transacción en sitio (con copia-al-escribir de los contenedores
// compartidos con el estado anterior) y añaden eventos. Como `gamehub.engine.stmt`.
#pragma once

#include <memory>
#include <string>
#include <vector>

#include "gamehub/game.hpp"
#include "gamehub/vm.hpp"

namespace gh {

struct Stmt {
  virtual ~Stmt() = default;
  virtual void exec(Ctx& ctx, Frame& frame) const = 0;
};

// Una ubicación modificable: variable raíz y pasos (índice o campo).
struct LStep {
  bool is_field = false;
  Chunk key;           // índice
  uint32_t field = 0;  // id del nombre del campo
  bool per_player = false;  // el contenedor de este paso es un per_player (el índice es el dueño)
};

struct LValue {
  uint32_t var = 0;
  std::vector<LStep> steps;
  TypeRef type;  // tipo estático de la ubicación

  // Las claves de los pasos, evaluadas en orden (comprobando cada nivel como `get`).
  std::vector<Value> keys(Ctx& ctx, Frame& frame) const;
  Value get(Ctx& ctx, Frame& frame) const;
  Value get_with(Ctx& ctx, const std::vector<Value>& keys) const;
  void set_with(Ctx& ctx, const std::vector<Value>& keys, Value value) const;
  // (variable, dueño): el dueño es el índice del último paso por un per_player.
  int32_t owner(const std::vector<Value>& keys) const;
};

// Escribe una variable de estado (invalida el memo "state").
void write_var(Ctx& ctx, uint32_t var, Value value);
// Adapta un valor al tipo declarado (listas → zonas, bolsas o conjuntos…), como `coerce`.
Value coerce(Value v, const Type& t, const Ctx& ctx);
// Una rejilla a partir de la lista de sus filas.
Value grid_from_rows(const Value& rows, int64_t width, int64_t height, const Type& t,
                     const Ctx& ctx);

struct Selector {
  enum class Kind : uint8_t { All, Top, Bottom, At, Value, Values } kind = Kind::All;
  Chunk arg;
  bool has_arg = false;
  std::vector<size_t> select(Ctx& ctx, Frame& frame, const Value& zone) const;
};

// --- Sentencias --------------------------------------------------------------------------------

struct AssignStmt : Stmt {
  LValue target;
  Chunk value;
  void exec(Ctx& ctx, Frame& frame) const override;
};

struct LetStmt : Stmt {
  uint32_t slot;
  Chunk value;
  void exec(Ctx& ctx, Frame& frame) const override;
};

struct IfStmt : Stmt {
  Chunk cond;
  Block then, other;
  void exec(Ctx& ctx, Frame& frame) const override;
};

struct ForStmt : Stmt {
  uint32_t slot;
  Chunk coll;
  Block body;
  void exec(Ctx& ctx, Frame& frame) const override;
};

struct FailStmt : Stmt {
  std::string message;
  void exec(Ctx& ctx, Frame& frame) const override;
};

struct MoveStmt : Stmt {
  LValue src, dst;
  Selector sel;
  bool to_top = true;
  void exec(Ctx& ctx, Frame& frame) const override;
};

struct FlipStmt : Stmt {
  LValue target;
  Selector sel;
  Chunk face;
  void exec(Ctx& ctx, Frame& frame) const override;
};

struct ShuffleStmt : Stmt {
  LValue target;
  void exec(Ctx& ctx, Frame& frame) const override;
};

struct RollStmt : Stmt {
  LValue target;
  Chunk sides;
  void exec(Ctx& ctx, Frame& frame) const override;
};

struct RandomChoiceStmt : Stmt {
  LValue target;
  Chunk coll;
  void exec(Ctx& ctx, Frame& frame) const override;
};

struct SampleStmt : Stmt {
  LValue target;
  Chunk dist;
  void exec(Ctx& ctx, Frame& frame) const override;
};

struct RevealStmt : Stmt {
  Chunk value, seats;
  bool has_label = false;
  Json label;
  void exec(Ctx& ctx, Frame& frame) const override;
};

struct EmitStmt : Stmt {
  std::string name;
  std::vector<std::pair<std::string, Chunk>> fields;
  Policy policy;
  void exec(Ctx& ctx, Frame& frame) const override;
};

struct RewardStmt : Stmt {
  Chunk seat, amount;
  void exec(Ctx& ctx, Frame& frame) const override;
};

// Ubicación de un evento: {"var": raíz} o {"var": raíz, "seat": dueño}.
Json location_json(const GameDef& game, uint32_t var, int32_t owner);

}  // namespace gh
