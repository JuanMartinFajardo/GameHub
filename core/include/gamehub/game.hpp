// SPDX-License-Identifier: Apache-2.0
// La IR compilada (`GameDef`, como en `gamehub.engine.game`): tipos, variables, funciones y
// nodos con sus expresiones en código de bytes y sus efectos como árboles de sentencias.
#pragma once

#include <memory>
#include <string>
#include <unordered_map>
#include <vector>

#include "gamehub/bytecode.hpp"
#include "gamehub/json.hpp"
#include "gamehub/types.hpp"

namespace gh {

struct Stmt;
struct Ctx;
struct Frame;

// Un bloque de sentencias.
struct Block {
  std::vector<std::unique_ptr<Stmt>> stmts;
  bool empty() const { return stmts.empty(); }
  void run(Ctx& ctx, Frame& frame) const;
};

// Un punto de compilación independiente: su código y el tamaño de su marco.
struct Expr {
  Chunk chunk;
  uint32_t frame = 0;
  bool defined = false;
};

struct Code {
  Block block;
  uint32_t frame = 0;
};

struct Policy {
  enum class Kind : uint8_t { All, None, Owner, Pred } kind = Kind::All;
  Expr pred;
  // ¿Lo ve el observador del marco? (`viewer` sin definir = vista omnisciente.)
  bool allows(Ctx& ctx, Frame& frame) const;
};

struct VarDef {
  std::string name;
  uint32_t index;
  TypeRef type;
  Expr init;
  Policy policy, size_policy;
  Expr range_lo, range_hi;  // `@range` (defined = false si no tiene)
};

struct ParamDef {
  std::string name;
  TypeRef type;
  Expr default_value;
};

enum class MemoKind : uint8_t { None, Static, State };

struct FunctionDef {
  std::string name;
  uint32_t arity = 0;
  Expr body;
  MemoKind memo = MemoKind::None;
  std::string native;
  // Memo adaptativo: si tras muchas consultas casi nunca acierta, se deja de memorizar (es una
  // caché; no cambia ningún resultado).
  mutable uint32_t memo_lookups = 0;
  mutable uint32_t memo_hits = 0;
  mutable bool memo_off = false;
};

struct TransitionDef {
  int to = -1;  // índice del nodo destino; -1 = `$exit`
  Expr when;    // `defined` = false si no tiene guarda
  Code effects;
  std::vector<std::string> key;  // ("node", nodo, i) o ("action", nodo, acción, i)
};

// Cómo se comprueba la pertenencia de un argumento a su dominio sin enumerarlo.
enum class DomainKind : uint8_t { Generic, Subsets, Range, EnumValues };

struct ActionParamDef {
  std::string name;
  TypeRef type;
  Expr domain;
  DomainKind member = DomainKind::Generic;
  Expr lo, hi, coll;      // subsets(coll, lo, hi) / range(lo, hi)
  uint32_t enum_type = 0;  // enum_values
  Policy policy, size_policy;
};

struct ActionDef {
  std::string name;
  uint32_t name_id = 0;
  int node = 0;
  std::vector<ActionParamDef> params;
  Expr requires_expr;  // `requires` (palabra reservada en C++20)
  Code effects;
  std::vector<TransitionDef> transitions;
  Policy policy;
  // Ranuras que bastan para cualquier dominio y el `requires` (los argumentos en 0..k-1): la
  // enumeración de acciones legales usa un solo marco para todos.
  uint32_t query_frame = 0;
};

enum class NodeKind : uint8_t { Decision, Simultaneous, Window, Chance, Auto, Phase, Terminal };
enum class WindowMode : uint8_t { None, Priority, Collect, Race };

struct NodeDef {
  std::string id;
  NodeKind kind;
  int index = 0;
  std::vector<int> ancestors;  // fases que lo contienen (de fuera adentro)
  std::vector<TransitionDef> transitions;
  std::vector<ActionDef> actions;
  Expr actor, actors, eligible, order, payoff, rank;
  Code resolve, effects, on_enter, on_exit;
  bool has_resolve = false, has_effects = false, has_on_enter = false, has_on_exit = false;
  WindowMode mode = WindowMode::None;
  int start = -1;  // fases

  int parent() const { return ancestors.empty() ? -1 : ancestors.back(); }
  const ActionDef* action(uint32_t name_id) const {
    for (const auto& a : actions) {
      if (a.name_id == name_id) return &a;
    }
    return nullptr;
  }
};

struct ConstraintDef {
  Expr expr;
  std::string message;
};

class MemoTable;

class GameDef {
 public:
  explicit GameDef(const Json& ir);
  ~GameDef();
  GameDef(const GameDef&) = delete;
  GameDef& operator=(const GameDef&) = delete;

  Json ir;
  std::string rules_hash;
  std::string id, version, title;
  int min_players = 1, max_players = 1;
  TypeTable types;
  std::vector<VarDef> vars;
  std::unordered_map<std::string, uint32_t> var_index;
  std::vector<ParamDef> params;  // el índice 0 es `num_players`
  std::unordered_map<std::string, uint32_t> param_index;
  std::vector<ConstraintDef> constraints;
  std::vector<FunctionDef> functions;
  std::unordered_map<std::string, uint32_t> function_index;
  std::vector<NodeDef> nodes;
  std::unordered_map<std::string, int> node_index;
  Code setup;
  bool setup_is_random = false;
  int start = 0;
  // Nombres de acción del juego (`pass` incluido) y de los campos de struct (para `field`).
  std::vector<std::string> action_names;
  uint32_t pass_id = 0;
  // Mutables: compilar una expresión nueva (`compile_expression`) puede añadir nombres.
  mutable std::vector<std::string> field_names;
  // field_slots[nombre][id de struct] = índice del campo, o -1.
  mutable std::vector<std::vector<int>> field_slots;
  // Resultados de las funciones "static" (valen para todas las partidas del juego).
  std::unique_ptr<MemoTable> static_memo;
  // `cells(g)` y `lines(g, k)` solo dependen de las dimensiones: (tipo, ancho, alto, k) → valor.
  mutable std::unordered_map<uint64_t, Value> grid_cache;
  // Ruta (fases activas y el nodo) de cada nodo; la del índice -1 (antes de empezar), vacía.
  std::vector<std::vector<int>> paths;
  const std::vector<int>* path(int node) const {
    static const std::vector<int> none;
    return node < 0 ? &none : &paths[static_cast<size_t>(node)];
  }

  uint32_t action_name_id(const std::string& name) const;  // UINT32_MAX si no existe
  // Una expresión de la IR fuera de las reglas (tests, invariantes, herramientas).
  Expr compile_expression(const Json& e) const;
  const NodeDef& node(int i) const { return nodes[static_cast<size_t>(i)]; }
};

}  // namespace gh
