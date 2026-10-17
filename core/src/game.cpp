// SPDX-License-Identifier: Apache-2.0
// Compilación de la IR: expresiones → código de bytes, sentencias → árboles de nodos, y el
// `GameDef` resultante (como `gamehub.engine.game.GameDef`).
#include "gamehub/game.hpp"

#include <algorithm>
#include <functional>
#include <set>

#include "gamehub/errors.hpp"
#include "gamehub/hashing.hpp"
#include "gamehub/stmt.hpp"
#include "gamehub/vm.hpp"

namespace gh {

namespace {

// --- Ámbitos y emisión -------------------------------------------------------------------------

// Ámbito léxico de una unidad de compilación: argumentos y locales → ranuras del marco.
class Scope {
 public:
  explicit Scope(const std::vector<std::string>& args) {
    for (const auto& a : args) args_.emplace_back(a, next_++);
    max_ = next_;
    blocks_.emplace_back();
  }

  uint32_t arg(const std::string& name) const {
    for (const auto& [n, s] : args_) {
      if (n == name) return s;
    }
    throw IrError("argumento desconocido: " + name);
  }

  uint32_t local(const std::string& name) const {
    for (auto b = blocks_.rbegin(); b != blocks_.rend(); ++b) {
      for (auto it = b->rbegin(); it != b->rend(); ++it) {
        if (it->first == name) return it->second;
      }
    }
    throw IrError("variable local no ligada: " + name);
  }

  uint32_t fresh() {
    uint32_t s = next_++;
    max_ = std::max(max_, next_);
    return s;
  }
  uint32_t bind(const std::string& name) {
    uint32_t s = fresh();
    blocks_.back().emplace_back(name, s);
    return s;
  }
  void open() {
    blocks_.emplace_back();
    marks_.push_back(next_);
  }
  void close() {
    blocks_.pop_back();
    next_ = marks_.back();
    marks_.pop_back();
  }
  uint32_t size() const { return max_; }

 private:
  std::vector<std::pair<std::string, uint32_t>> args_;
  std::vector<std::vector<std::pair<std::string, uint32_t>>> blocks_;
  std::vector<uint32_t> marks_;
  uint32_t next_ = 0, max_ = 0;
};

class Emitter {
 public:
  explicit Emitter(Chunk& c) : c_(c) {}
  void emit(uint32_t op, int delta, std::initializer_list<uint32_t> operands = {}) {
    depth_ += delta;
    if (depth_ > 0) c_.max_stack = std::max(c_.max_stack, static_cast<uint32_t>(depth_));
    if (fuse(op)) return;
    last_op_ = here();
    last_code_ = op;
    c_.code.push_back(op);
    for (uint32_t x : operands) c_.code.push_back(x);
  }
  // Una posición a la que se salta: no se fusiona nada a través de ella.
  uint32_t label() {
    barrier_ = here();
    return barrier_;
  }
  uint32_t constant(Value v) {
    c_.consts.push_back(std::move(v));
    return static_cast<uint32_t>(c_.consts.size() - 1);
  }
  uint32_t here() const { return static_cast<uint32_t>(c_.code.size()); }
  // Posición del último operando emitido (para parchear un destino).
  uint32_t last() const { return static_cast<uint32_t>(c_.code.size() - 1); }
  void patch(uint32_t pos, uint32_t target) {
    c_.code[pos] = target;
    barrier_ = std::max(barrier_, target);
  }
  int depth() const { return depth_; }
  void set_depth(int d) { depth_ = d; }

 private:
  // LOAD s + VAR_INDEX v → VAR_INDEX_LOCAL s v; LOAD s + EQ → EQ_LOCAL s; CONST k + EQ → EQ_CONST k.
  bool fuse(uint32_t op) {
    bool adjacent = barrier_ <= last_op_ && last_op_ + 2 == here() && !c_.code.empty();
    if (!adjacent) return false;
    uint32_t operand = c_.code[last_op_ + 1];
    uint32_t fused = UINT32_MAX;
    if (last_code_ == OP_LOAD && op == OP_EQ) fused = OP_EQ_LOCAL;
    if (last_code_ == OP_LOAD && op == OP_NE) fused = OP_NE_LOCAL;
    if (last_code_ == OP_CONST && op == OP_EQ) fused = OP_EQ_CONST;
    if (last_code_ == OP_CONST && op == OP_NE) fused = OP_NE_CONST;
    if (fused != UINT32_MAX) {
      c_.code[last_op_] = fused;
      c_.code[last_op_ + 1] = operand;
      last_code_ = fused;
      return true;
    }
    return false;
  }

 public:
  // Si lo último emitido es un LOAD (sin etiqueta detrás), lo quita y devuelve su ranura.
  uint32_t take_load() {
    bool adjacent = barrier_ <= last_op_ && last_op_ + 2 == here() && last_code_ == OP_LOAD;
    if (!adjacent) return UINT32_MAX;
    uint32_t slot = c_.code[last_op_ + 1];
    c_.code.resize(last_op_);
    last_code_ = UINT32_MAX;
    return slot;
  }

  // VAR_INDEX v justo después de LOAD s: se emite como VAR_INDEX_LOCAL s v.
  bool fuse_var_index(uint32_t var) {
    bool adjacent = barrier_ <= last_op_ && last_op_ + 2 == here() && last_code_ == OP_LOAD;
    if (!adjacent) return false;
    c_.code[last_op_] = OP_VAR_INDEX_LOCAL;
    c_.code.push_back(var);
    last_code_ = OP_VAR_INDEX_LOCAL;
    return true;
  }

 private:
  Chunk& c_;
  int depth_ = 0;
  uint32_t last_op_ = 0;
  uint32_t last_code_ = UINT32_MAX;
  uint32_t barrier_ = 0;
};

struct Simple {
  const char* name;
  Op op;
  int arity;  // -1 = variable
};

// Operadores puros de aridad fija: código y número de argumentos.
const Simple SIMPLE[] = {
    {"cell", OP_CELL, 2},           {"sub", OP_SUB, 2},
    {"div", OP_DIV, 2},             {"idiv", OP_IDIV, 2},
    {"mod", OP_MOD, 2},             {"neg", OP_NEG, 1},
    {"abs", OP_ABS, 1},             {"eq", OP_EQ, 2},
    {"ne", OP_NE, 2},               {"lt", OP_LT, 2},
    {"le", OP_LE, 2},               {"gt", OP_GT, 2},
    {"ge", OP_GE, 2},               {"not", OP_NOT, 1},
    {"is_none", OP_IS_NONE, 1},     {"unwrap", OP_UNWRAP, 1},
    {"len", OP_LEN, 1},             {"contains", OP_CONTAINS, 2},
    {"index", OP_INDEX, 2},         {"first", OP_FIRST, 1},
    {"last", OP_LAST, 1},           {"only", OP_ONLY, 1},
    {"append", OP_APPEND, 2},       {"concat", OP_CONCAT, 2},
    {"range", OP_RANGE, 2},         {"slice", OP_SLICE, 3},
    {"reverse", OP_REVERSE, 1},     {"distinct", OP_DISTINCT, 1},
    {"union", OP_UNION, 2},         {"intersection", OP_INTERSECTION, 2},
    {"difference", OP_DIFFERENCE, 2}, {"subsets", OP_SUBSETS, 3},
    {"next_seat", OP_NEXT_SEAT, 1}, {"prev_seat", OP_PREV_SEAT, 1},
    {"other_seat", OP_OTHER_SEAT, 1}, {"seats_from", OP_SEATS_FROM, 1},
    {"cells", OP_CELLS, 1},         {"lines", OP_LINES, 2},
    {"neighbors", OP_NEIGHBORS, 2}, {"in_bounds", OP_IN_BOUNDS, 2},
    {"size", OP_SIZE, 1},           {"items", OP_ITEMS, 1},
    {"top", OP_TOP, 1},             {"ord", OP_ORD, 1},
    {"win_loss", OP_WIN_LOSS, 3},   {"fill", OP_FILL, 1},
};

const std::pair<const char*, IterOp> COMPREHENSIONS[] = {
    {"all", IT_ALL},       {"any", IT_ANY},           {"count", IT_COUNT},
    {"sum", IT_SUM},       {"map", IT_MAP},           {"flat_map", IT_FLAT_MAP},
    {"filter", IT_FILTER}, {"argmax", IT_ARGMAX},     {"argmin", IT_ARGMIN},
    {"max_of", IT_MAX_OF}, {"min_of", IT_MIN_OF},     {"sort_by", IT_SORT_BY},
};

// --- Compilador --------------------------------------------------------------------------------

class Compiler {
 public:
  explicit Compiler(GameDef& g) : g_(g) {}

  Expr expr_site(const Json& e, const std::vector<std::string>& args = {}) {
    Scope scope(args);
    Expr out;
    out.chunk = chunk(e, scope);
    out.frame = scope.size();
    out.defined = true;
    return out;
  }

  Code block_site(const Json* stmts, const std::vector<std::string>& args = {}) {
    Scope scope(args);
    Code out;
    if (stmts != nullptr) out.block = block(*stmts, scope);
    out.frame = scope.size();
    return out;
  }

  Policy policy(const Json* raw, Policy::Kind fallback) {
    Policy p;
    p.kind = fallback;
    if (raw == nullptr) return p;
    if (raw->is_string()) {
      const std::string& s = raw->as_string();
      p.kind = s == "all" ? Policy::Kind::All
               : s == "none" ? Policy::Kind::None
               : s == "owner" ? Policy::Kind::Owner
                              : throw IrError("visibilidad desconocida: " + s);
      return p;
    }
    p.kind = Policy::Kind::Pred;
    p.pred = expr_site(raw->at("when"));
    return p;
  }

 private:
  GameDef& g_;

  // Una expresión como fragmento independiente (termina con RETURN) en el ámbito dado.
  Chunk chunk(const Json& e, Scope& scope) {
    Chunk c;
    Emitter em(c);
    expr(e, em, scope);
    em.emit(OP_RETURN, -1);
    return c;
  }

  Value literal(const Json& j) {
    switch (j.kind()) {
      case Json::Kind::Null:
        return Value::none();
      case Json::Kind::Bool:
        return Value::boolean(j.as_bool());
      case Json::Kind::Int:
        return Value::integer(j.as_int());
      case Json::Kind::String:
        return Value::text(j.as_string());
      case Json::Kind::Array: {
        ValueVec items;
        for (const auto& x : j.as_array()) items.push_back(literal(x));
        return Value::tuple(std::move(items));
      }
      case Json::Kind::Object:
        break;
    }
    throw IrError("constante no admitida: " + j.dump());
  }

  uint32_t field_id(const std::string& name) {
    for (size_t k = 0; k < g_.field_names.size(); ++k) {
      if (g_.field_names[k] == name) return static_cast<uint32_t>(k);
    }
    g_.field_names.push_back(name);
    std::vector<int> slots;
    for (const auto& s : g_.types.structs()) slots.push_back(s.field_index(name));
    g_.field_slots.push_back(std::move(slots));
    return static_cast<uint32_t>(g_.field_names.size() - 1);
  }

  void many(const JsonArray& args, size_t from, Emitter& em, Scope& scope) {
    for (size_t k = from; k < args.size(); ++k) expr(args[k], em, scope);
  }

  void expr(const Json& e, Emitter& em, Scope& scope) {
    const JsonArray& a = e.as_array();
    const std::string& op = a.at(0).as_string();
    if (op == "index" && a.size() == 3 && a[1].is_array() && a[1].size() == 2 &&
        a[1][0].is_string() && a[1][0].as_string() == "var") {
      auto it = g_.var_index.find(a[1][1].as_string());
      if (it == g_.var_index.end()) throw IrError("variable desconocida: " + a[1][1].as_string());
      expr(a[2], em, scope);
      if (!em.fuse_var_index(it->second)) em.emit(OP_VAR_INDEX, 0, {it->second});
      return;
    }
    for (const auto& s : SIMPLE) {
      if (op == s.name) {
        if (static_cast<int>(a.size()) - 1 != s.arity) {
          throw IrError("'" + op + "' con un número de argumentos inválido");
        }
        many(a, 1, em, scope);
        em.emit(s.op, 1 - s.arity);
        return;
      }
    }
    for (const auto& [name, it] : COMPREHENSIONS) {
      if (op == name) {
        comprehension(it, a, em, scope);
        return;
      }
    }
    if (op == "const") {
      em.emit(OP_CONST, 1, {em.constant(literal(a.at(1)))});
    } else if (op == "rat") {
      int64_t n = a.at(1).as_int(), d = a.at(2).as_int();
      if (d <= 0) {
        throw RuleError("racional con denominador no positivo: " + std::to_string(n) + "/" +
                        std::to_string(d));
      }
      em.emit(OP_CONST, 1, {em.constant(Value::number(Rational::of(n, d)))});
    } else if (op == "enum") {
      em.emit(OP_CONST, 1,
              {em.constant(g_.types.enum_value(a.at(1).as_string(), a.at(2).as_string()))});
    } else if (op == "var") {
      auto it = g_.var_index.find(a.at(1).as_string());
      if (it == g_.var_index.end()) throw IrError("variable desconocida: " + a.at(1).as_string());
      em.emit(OP_VAR, 1, {it->second});
    } else if (op == "param") {
      auto it = g_.param_index.find(a.at(1).as_string());
      if (it == g_.param_index.end()) throw IrError("parámetro desconocido: " + a.at(1).as_string());
      em.emit(OP_PARAM, 1, {it->second});
    } else if (op == "arg") {
      em.emit(OP_LOAD, 1, {scope.arg(a.at(1).as_string())});
    } else if (op == "local") {
      em.emit(OP_LOAD, 1, {scope.local(a.at(1).as_string())});
    } else if (op == "actor") {
      em.emit(OP_ACTOR, 1);
    } else if (op == "viewer") {
      em.emit(OP_VIEWER, 1);
    } else if (op == "owner") {
      em.emit(OP_OWNER, 1);
    } else if (op == "item_face_up") {
      em.emit(OP_FACE_UP, 1);
    } else if (op == "seats") {
      em.emit(OP_SEATS, 1);
    } else if (op == "at") {
      auto it = g_.node_index.find(a.at(1).as_string());
      if (it == g_.node_index.end()) throw IrError("nodo desconocido: " + a.at(1).as_string());
      em.emit(OP_AT, 1, {static_cast<uint32_t>(it->second)});
    } else if (op == "list" || op == "tuple") {
      many(a, 1, em, scope);
      auto n = static_cast<uint32_t>(a.size() - 1);
      em.emit(OP_LIST, 1 - static_cast<int>(n), {n});
    } else if (op == "set") {
      many(a, 1, em, scope);
      auto n = static_cast<uint32_t>(a.size() - 1);
      em.emit(OP_SET, 1 - static_cast<int>(n), {n});
    } else if (op == "struct") {
      const std::string& type = a.at(1).as_string();
      int id = g_.types.struct_id(type);
      if (id < 0) throw IrError("struct desconocido: " + type);
      const StructDecl& decl = g_.types.structs()[static_cast<size_t>(id)];
      for (const auto& f : decl.fields) expr(a.at(2).at(f), em, scope);
      auto n = static_cast<uint32_t>(decl.fields.size());
      em.emit(OP_STRUCT, 1 - static_cast<int>(n), {static_cast<uint32_t>(id), n});
    } else if (op == "add" || op == "mul" || op == "min" || op == "max") {
      many(a, 1, em, scope);
      auto n = static_cast<uint32_t>(a.size() - 1);
      Op code = op == "add" ? OP_ADD : op == "mul" ? OP_MUL : op == "min" ? OP_MIN : OP_MAX;
      em.emit(code, 1 - static_cast<int>(n), {n});
    } else if (op == "and" || op == "or") {
      // Cortocircuito: cada operando debe ser booleano.
      Op test = op == "and" ? OP_AND_TEST : OP_OR_TEST;
      int start = em.depth();
      std::vector<uint32_t> exits;
      for (size_t k = 1; k < a.size(); ++k) {
        expr(a[k], em, scope);
        em.emit(test, -1, {0});
        exits.push_back(em.last());
      }
      em.emit(OP_CONST, 1, {em.constant(Value::boolean(op == "and"))});
      for (uint32_t pos : exits) em.patch(pos, em.here());
      em.set_depth(start + 1);
    } else if (op == "if") {
      int start = em.depth();
      expr(a.at(1), em, scope);
      em.emit(OP_JUMP_IF_FALSE, -1, {0, 0});
      uint32_t to_else = em.last() - 1;
      expr(a.at(2), em, scope);
      em.emit(OP_JUMP, 0, {0});
      uint32_t to_end = em.last();
      em.set_depth(start);
      em.patch(to_else, em.here());
      expr(a.at(3), em, scope);
      em.patch(to_end, em.here());
      em.set_depth(start + 1);
    } else if (op == "case") {
      int start = em.depth();
      std::vector<uint32_t> ends;
      for (const auto& pair : a.at(1).as_array()) {
        em.set_depth(start);
        expr(pair.at(0), em, scope);
        em.emit(OP_JUMP_IF_FALSE, -1, {0, 1});
        uint32_t to_next = em.last() - 1;
        expr(pair.at(1), em, scope);
        em.emit(OP_JUMP, 0, {0});
        ends.push_back(em.last());
        em.patch(to_next, em.here());
      }
      em.set_depth(start);
      expr(a.at(2), em, scope);
      for (uint32_t pos : ends) em.patch(pos, em.here());
      em.set_depth(start + 1);
    } else if (op == "let") {
      expr(a.at(2), em, scope);
      scope.open();
      uint32_t slot = scope.bind(a.at(1).as_string());
      em.emit(OP_STORE, -1, {slot});
      expr(a.at(3), em, scope);
      scope.close();
    } else if (op == "field") {
      expr(a.at(1), em, scope);
      em.emit(OP_FIELD, 0, {field_id(a.at(2).as_string())});
    } else if (op == "enum_values") {
      int id = g_.types.enum_id(a.at(1).as_string());
      if (id < 0) throw IrError("enumerado desconocido: " + a.at(1).as_string());
      ValueVec values;
      size_t count = g_.types.enums()[static_cast<size_t>(id)].values.size();
      for (size_t k = 0; k < count; ++k) {
        values.push_back(Value::enumeration(static_cast<uint32_t>(id), int64_t(k)));
      }
      em.emit(OP_CONST, 1, {em.constant(Value::tuple(std::move(values)))});
    } else if (op == "call") {
      const std::string& name = a.at(1).as_string();
      auto it = g_.function_index.find(name);
      if (it == g_.function_index.end()) throw IrError("función desconocida: " + name);
      many(a, 2, em, scope);
      auto argc = static_cast<uint32_t>(a.size() - 2);
      em.emit(OP_CALL, 1 - static_cast<int>(argc), {it->second, argc});
    } else {
      throw IrError("operador sin implementar: " + op);
    }
  }

  void comprehension(IterOp it, const JsonArray& a, Emitter& em, Scope& scope) {
    const std::string& binder = a.at(1).as_string();
    int start = em.depth();
    scope.open();
    uint32_t coll = scope.fresh(), idx = scope.fresh();
    bool nonempty = it == IT_ARGMAX || it == IT_ARGMIN || it == IT_MAX_OF || it == IT_MIN_OF;
    // Lo que prepara el bucle va antes de la colección (no depende de ella y no falla), para que
    // una colección que es una local se lea directamente de su ranura.
    uint32_t acc = 0, best = 0, best_key = 0;
    switch (it) {
      case IT_COUNT:
      case IT_SUM:
        acc = scope.fresh();
        em.emit(OP_CONST, 1, {em.constant(Value::integer(0))});
        em.emit(OP_STORE, -1, {acc});
        break;
      case IT_ARGMAX:
      case IT_ARGMIN:
        best = scope.fresh();
        best_key = scope.fresh();
        break;
      case IT_MAP:
      case IT_FILTER:
      case IT_FLAT_MAP:
      case IT_MAX_OF:
      case IT_MIN_OF:
      case IT_SORT_BY:
        em.emit(OP_BUILD_BEGIN, 0);
        break;
      default:
        break;
    }
    expr(a.at(2), em, scope);
    uint32_t source = em.take_load();
    if (source != UINT32_MAX) em.set_depth(em.depth() - 1);
    uint32_t slot = scope.bind(binder);
    em.emit(OP_ITER_FIRST, source == UINT32_MAX ? -1 : 0,
            {static_cast<uint32_t>(it), coll, idx, nonempty ? 1u : 0u, slot, 0, source});
    uint32_t to_exit = em.last() - 1;
    uint32_t body = em.label();
    expr(a.at(3), em, scope);
    uint32_t to_short = 0;
    switch (it) {
      case IT_ALL:
        em.emit(OP_ALL_LOOP, -1, {0, coll, idx, slot, body});
        to_short = em.last() - 4;
        break;
      case IT_ANY:
        em.emit(OP_ANY_LOOP, -1, {0, coll, idx, slot, body});
        to_short = em.last() - 4;
        break;
      case IT_COUNT:
        em.emit(OP_COUNT_LOOP, -1, {acc, coll, idx, slot, body});
        break;
      case IT_SUM:
        em.emit(OP_SUM_LOOP, -1, {acc, coll, idx, slot, body});
        break;
      case IT_MAP:
      case IT_MAX_OF:
      case IT_MIN_OF:
        em.emit(OP_PUSH_LOOP, -1, {0, coll, idx, slot, body});
        break;
      case IT_FILTER:
        em.emit(OP_FILTER_LOOP, -1, {0, coll, idx, slot, body});
        break;
      case IT_FLAT_MAP:
        em.emit(OP_FLAT_STEP, -1);
        em.emit(OP_ITER_LOOP, 0, {coll, idx, slot, body});
        break;
      case IT_ARGMAX:
      case IT_ARGMIN:
        em.emit(OP_ARGBEST_STEP, -1, {it == IT_ARGMAX ? 1u : 0u, best, best_key, slot});
        em.emit(OP_ITER_LOOP, 0, {coll, idx, slot, body});
        break;
      case IT_SORT_BY:
        em.emit(OP_SORT_PUSH, -1, {slot});
        em.emit(OP_ITER_LOOP, 0, {coll, idx, slot, body});
        break;
    }
    em.patch(to_exit, em.here());
    em.set_depth(start);
    switch (it) {
      case IT_ALL:
      case IT_ANY: {
        // Al agotar la colección: True (all) o False (any); al cortocircuitar, lo contrario.
        em.emit(OP_CONST, 1, {em.constant(Value::boolean(it == IT_ALL))});
        em.emit(OP_JUMP, 0, {0});
        uint32_t to_end = em.last();
        em.set_depth(start);
        em.patch(to_short, em.here());
        em.emit(OP_CONST, 1, {em.constant(Value::boolean(it != IT_ALL))});
        em.patch(to_end, em.here());
        break;
      }
      case IT_COUNT:
      case IT_SUM:
        em.emit(OP_LOAD, 1, {acc});
        break;
      case IT_MAP:
      case IT_FILTER:
      case IT_FLAT_MAP:
        em.emit(OP_BUILD_LIST, 1);
        break;
      case IT_ARGMAX:
      case IT_ARGMIN:
        em.emit(OP_LOAD, 1, {best});
        break;
      case IT_MAX_OF:
      case IT_MIN_OF:
        em.emit(OP_BEST_OF, 1, {it == IT_MAX_OF ? 1u : 0u});
        break;
      case IT_SORT_BY:
        em.emit(OP_SORT_BY, 1);
        break;
    }
    em.set_depth(start + 1);
    scope.close();
  }

  // --- Sentencias -------------------------------------------------------------------------------

  Block block(const Json& stmts, Scope& scope) {
    Block b;
    scope.open();
    for (const auto& s : stmts.as_array()) b.stmts.push_back(stmt(s, scope));
    scope.close();
    return b;
  }

  LValue lvalue(const Json& e, Scope& scope) {
    const JsonArray& a = e.as_array();
    const std::string& op = a.at(0).as_string();
    if (op == "var") {
      LValue lv;
      auto it = g_.var_index.find(a.at(1).as_string());
      if (it == g_.var_index.end()) throw IrError("variable desconocida: " + a.at(1).as_string());
      lv.var = it->second;
      lv.type = g_.vars[it->second].type;
      return lv;
    }
    LValue lv = lvalue(a.at(1), scope);
    LStep step;
    if (op == "index") {
      step.key = chunk(a.at(2), scope);
      const Type& base = *lv.type;
      step.per_player = base.kind == Type::Kind::PerPlayer;
      lv.type = base.kind == Type::Kind::Map ? base.args.at(1) : base.args.at(0);
    } else if (op == "field") {
      step.is_field = true;
      const std::string& name = a.at(2).as_string();
      step.field = field_id(name);
      const Type& base = *lv.type;
      if (base.kind != Type::Kind::Struct) throw IrError("'field' sobre algo que no es un struct");
      const StructDecl& decl = g_.types.structs()[base.id];
      int k = decl.field_index(name);
      if (k < 0) throw IrError(decl.name + " no tiene el campo " + name);
      lv.type = decl.types[static_cast<size_t>(k)];
    } else {
      throw RuleError("no es una ubicación modificable: " + op);
    }
    lv.steps.push_back(std::move(step));
    return lv;
  }

  Selector selector(const Json& sel, Scope& scope) {
    Selector s;
    const std::string& kind = sel.at(0).as_string();
    using K = Selector::Kind;
    s.kind = kind == "all"      ? K::All
             : kind == "top"    ? K::Top
             : kind == "bottom" ? K::Bottom
             : kind == "at"     ? K::At
             : kind == "value"  ? K::Value
             : kind == "values" ? K::Values
                                : throw IrError("selector desconocido: " + kind);
    if (sel.size() > 1) {
      s.arg = chunk(sel.at(1), scope);
      s.has_arg = true;
    }
    return s;
  }

  std::unique_ptr<Stmt> stmt(const Json& s, Scope& scope) {
    const JsonArray& a = s.as_array();
    const std::string& op = a.at(0).as_string();
    if (op == "assign") {
      auto st = std::make_unique<AssignStmt>();
      st->target = lvalue(a.at(1), scope);
      st->value = chunk(a.at(2), scope);
      return st;
    }
    if (op == "let") {
      auto st = std::make_unique<LetStmt>();
      st->value = chunk(a.at(2), scope);
      st->slot = scope.bind(a.at(1).as_string());
      return st;
    }
    if (op == "if") {
      auto st = std::make_unique<IfStmt>();
      st->cond = chunk(a.at(1), scope);
      st->then = block(a.at(2), scope);
      if (a.size() > 3 && !a[3].is_null()) st->other = block(a[3], scope);
      return st;
    }
    if (op == "for") {
      auto st = std::make_unique<ForStmt>();
      st->coll = chunk(a.at(2), scope);
      scope.open();
      st->slot = scope.bind(a.at(1).as_string());
      st->body = block(a.at(3), scope);
      scope.close();
      return st;
    }
    if (op == "fail") {
      auto st = std::make_unique<FailStmt>();
      const Json& text = a.at(1);
      st->message = text.is_string() ? text.as_string() : text.as_object().at(0).second.as_string();
      return st;
    }
    if (op == "move") {
      auto st = std::make_unique<MoveStmt>();
      st->src = lvalue(a.at(1), scope);
      st->dst = lvalue(a.at(2), scope);
      st->sel = selector(a.at(3), scope);
      st->to_top = a.size() <= 4 || a[4].as_string() == "top";
      return st;
    }
    if (op == "flip") {
      auto st = std::make_unique<FlipStmt>();
      st->target = lvalue(a.at(1), scope);
      st->sel = selector(a.at(2), scope);
      st->face = chunk(a.at(3), scope);
      return st;
    }
    if (op == "shuffle") {
      auto st = std::make_unique<ShuffleStmt>();
      st->target = lvalue(a.at(1), scope);
      return st;
    }
    if (op == "roll") {
      auto st = std::make_unique<RollStmt>();
      st->target = lvalue(a.at(1), scope);
      st->sides = chunk(a.at(2), scope);
      return st;
    }
    if (op == "random_choice") {
      auto st = std::make_unique<RandomChoiceStmt>();
      st->target = lvalue(a.at(1), scope);
      st->coll = chunk(a.at(2), scope);
      return st;
    }
    if (op == "sample") {
      auto st = std::make_unique<SampleStmt>();
      st->target = lvalue(a.at(1), scope);
      st->dist = chunk(a.at(2), scope);
      return st;
    }
    if (op == "reveal") {
      auto st = std::make_unique<RevealStmt>();
      st->value = chunk(a.at(1), scope);
      st->seats = chunk(a.at(2), scope);
      if (a.size() > 3 && !a[3].is_null()) {
        st->has_label = true;
        st->label = a[3];
      }
      return st;
    }
    if (op == "emit") {
      auto st = std::make_unique<EmitStmt>();
      st->name = a.at(1).as_string();
      for (const auto& [k, v] : a.at(2).as_object()) st->fields.emplace_back(k, chunk(v, scope));
      st->policy = policy(a.size() > 3 && !a[3].is_null() ? &a[3] : nullptr, Policy::Kind::All);
      return st;
    }
    if (op == "reward") {
      auto st = std::make_unique<RewardStmt>();
      st->seat = chunk(a.at(1), scope);
      st->amount = chunk(a.at(2), scope);
      return st;
    }
    throw IrError("sentencia sin implementar: " + op);
  }
};

// --- Clasificación de las funciones para el memo (como `_memo_kinds`) -------------------------

const std::set<std::string> CONTEXTUAL = {"at", "actor", "viewer", "owner", "item_face_up"};
const std::set<std::string> STATEFUL = {"var",        "param",     "seats", "next_seat",
                                        "prev_seat",  "other_seat", "seats_from", "win_loss",
                                        "fill"};
const std::set<std::string> LOOPS = {"all",    "any",    "count",   "sum",    "map",
                                     "flat_map", "filter", "argmax", "argmin", "max_of",
                                     "min_of", "sort_by", "subsets", "cells", "lines"};

std::unordered_map<std::string, MemoKind> memo_kinds(const Json& functions) {
  std::unordered_map<std::string, std::set<std::string>> calls;
  std::set<std::string> contextual, stateful, heavy;
  std::function<void(const Json&, const std::string&)> walk = [&](const Json& node,
                                                                  const std::string& name) {
    if (node.is_array() && node.size() > 0) {
      const JsonArray& a = node.as_array();
      bool headed = a[0].is_string();
      std::string head = headed ? a[0].as_string() : "";
      if (headed && head == "const") return;
      if (CONTEXTUAL.count(head)) contextual.insert(name);
      if (STATEFUL.count(head)) stateful.insert(name);
      if (LOOPS.count(head)) heavy.insert(name);
      if (head == "call" && a.size() > 1 && a[1].is_string()) {
        calls[name].insert(a[1].as_string());
        heavy.insert(name);
      }
      for (size_t k = headed ? 1 : 0; k < a.size(); ++k) walk(a[k], name);
    } else if (node.is_object()) {
      for (const auto& [k, v] : node.as_object()) walk(v, name);
    }
  };
  for (const auto& f : functions.as_array()) {
    const std::string& name = f["name"].as_string();
    calls[name];
    walk(f["body"], name);
  }
  bool changed = true;
  while (changed) {
    changed = false;
    for (auto& [name, callees] : calls) {
      for (auto* marks : {&contextual, &stateful}) {
        if (marks->count(name)) continue;
        for (const auto& c : callees) {
          if (marks->count(c)) {
            marks->insert(name);
            changed = true;
            break;
          }
        }
      }
    }
  }
  std::unordered_map<std::string, MemoKind> kinds;
  for (const auto& [name, callees] : calls) {
    if (contextual.count(name) || !heavy.count(name)) {
      kinds[name] = MemoKind::None;
    } else {
      kinds[name] = stateful.count(name) ? MemoKind::State : MemoKind::Static;
    }
  }
  return kinds;
}

bool has_chance(const Json& node) {
  if (!node.is_array()) return false;
  const JsonArray& a = node.as_array();
  if (!a.empty() && a[0].is_string()) {
    const std::string& h = a[0].as_string();
    if (h == "shuffle" || h == "roll" || h == "random_choice" || h == "sample") return true;
  }
  for (const auto& x : a) {
    if (has_chance(x)) return true;
  }
  return false;
}

std::string text_of(const Json* v) {
  if (v == nullptr || v->is_null()) return "";
  if (v->is_string()) return v->as_string();
  if (const Json* es = v->find("es")) return es->as_string();
  if (v->size() > 0) return v->as_object().front().second.as_string();
  return "";
}

const Json* opt(const Json& obj, const char* key) {
  const Json* v = obj.find(key);
  return v != nullptr && !v->is_null() ? v : nullptr;
}

const Json EMPTY_ARRAY = Json::array();

const Json& list_or_empty(const Json& obj, const char* key) {
  const Json* v = opt(obj, key);
  return v != nullptr ? *v : EMPTY_ARRAY;
}

}  // namespace

// --- GameDef -----------------------------------------------------------------------------------

GameDef::~GameDef() = default;

Expr GameDef::compile_expression(const Json& e) const {
  // Solo puede añadir nombres de campo (mutables): no cambia nada de lo ya compilado.
  Compiler c(const_cast<GameDef&>(*this));
  return c.expr_site(e);
}

uint32_t GameDef::action_name_id(const std::string& name) const {
  for (size_t k = 0; k < action_names.size(); ++k) {
    if (action_names[k] == name) return static_cast<uint32_t>(k);
  }
  return UINT32_MAX;
}

GameDef::GameDef(const Json& ir_doc) : ir(ir_doc), static_memo(std::make_unique<MemoTable>()) {
  rules_hash = gh::rules_hash(ir);
  id = ir["game"]["id"].as_string();
  version = ir["game"]["version"].as_string();
  const Json* meta = opt(ir, "meta");
  title = meta != nullptr ? text_of(opt(*meta, "title")) : "";
  if (title.empty()) title = id;
  min_players = static_cast<int>(ir["players"]["min"].as_int());
  max_players = static_cast<int>(ir["players"]["max"].as_int());
  types = TypeTable(list_or_empty(ir, "types"));

  // Índices de nombres antes de compilar nada (las expresiones los usan).
  const Json& state = list_or_empty(ir, "state");
  for (size_t k = 0; k < state.size(); ++k) var_index[state[k]["name"].as_string()] = uint32_t(k);
  params.push_back(ParamDef{"num_players", nullptr, {}});
  param_index["num_players"] = 0;
  for (const auto& p : list_or_empty(ir, "params").as_array()) {
    param_index[p["name"].as_string()] = static_cast<uint32_t>(params.size());
    params.push_back(ParamDef{p["name"].as_string(), types.parse(p["type"]), {}});
  }
  const Json& fns = list_or_empty(ir, "functions");
  for (size_t k = 0; k < fns.size(); ++k) function_index[fns[k]["name"].as_string()] = uint32_t(k);
  const Json& flow = ir["flow"];
  std::vector<const Json*> raw_nodes;  // en preorden: el índice de cada nodo
  std::function<void(const Json&)> collect = [&](const Json& list) {
    for (const auto& n : list.as_array()) {
      node_index[n["id"].as_string()] = static_cast<int>(raw_nodes.size());
      raw_nodes.push_back(&n);
      if (n["kind"].as_string() == "phase") collect(n["nodes"]);
    }
  };
  collect(flow["nodes"]);
  // Nombres de acción (los de todos los nodos y `pass`).
  for (const Json* n : raw_nodes) {
    for (const auto& a : list_or_empty(*n, "actions").as_array()) {
      if (action_name_id(a["name"].as_string()) == UINT32_MAX) {
        action_names.push_back(a["name"].as_string());
      }
    }
  }
  pass_id = action_name_id("pass");
  if (pass_id == UINT32_MAX) {
    action_names.push_back("pass");
    pass_id = static_cast<uint32_t>(action_names.size() - 1);
  }

  Compiler c(*this);
  auto kinds = memo_kinds(fns);
  for (const auto& f : fns.as_array()) {
    FunctionDef fd;
    fd.name = f["name"].as_string();
    std::vector<std::string> args;
    for (const auto& p : f["params"].as_array()) args.push_back(p.at(0).as_string());
    fd.arity = static_cast<uint32_t>(args.size());
    fd.body = c.expr_site(f["body"], args);
    fd.memo = kinds[fd.name];
    if (const Json* native = opt(f, "native")) fd.native = native->as_string();
    functions.push_back(std::move(fd));
  }
  for (size_t k = 0; k < state.size(); ++k) {
    const Json& v = state[k];
    VarDef vd;
    vd.name = v["name"].as_string();
    vd.index = static_cast<uint32_t>(k);
    vd.type = types.parse(v["type"]);
    vd.init = c.expr_site(v["init"]);
    vd.policy = c.policy(opt(v, "visibility"), Policy::Kind::All);
    vd.size_policy = c.policy(opt(v, "size_visibility"), Policy::Kind::All);
    vars.push_back(std::move(vd));
  }
  {
    size_t k = 1;
    for (const auto& p : list_or_empty(ir, "params").as_array()) {
      params[k++].default_value = c.expr_site(p["default"]);
    }
  }
  for (const auto& con : list_or_empty(ir, "constraints").as_array()) {
    std::string message = text_of(opt(con, "message"));
    if (message.empty()) message = "restricción incumplida";
    constraints.push_back(ConstraintDef{c.expr_site(con["expr"]), message});
  }
  setup = c.block_site(opt(flow, "setup"));
  setup_is_random = has_chance(list_or_empty(flow, "setup"));

  // Nodos.
  nodes.resize(raw_nodes.size());
  std::function<void(const Json&, const std::vector<int>&)> compile_nodes =
      [&](const Json& list, const std::vector<int>& ancestors) {
        for (const auto& raw : list.as_array()) {
          int index = node_index.at(raw["id"].as_string());
          NodeDef& node = nodes[static_cast<size_t>(index)];
          node.id = raw["id"].as_string();
          node.index = index;
          node.ancestors = ancestors;
          const std::string& kind = raw["kind"].as_string();
          node.kind = kind == "decision"       ? NodeKind::Decision
                      : kind == "simultaneous" ? NodeKind::Simultaneous
                      : kind == "window"       ? NodeKind::Window
                      : kind == "chance"       ? NodeKind::Chance
                      : kind == "auto"         ? NodeKind::Auto
                      : kind == "phase"        ? NodeKind::Phase
                      : kind == "terminal"     ? NodeKind::Terminal
                                               : throw IrError("tipo de nodo desconocido: " + kind);
          auto transitions = [&](const Json& raw_list, std::vector<std::string> owner,
                                 const std::vector<std::string>& args) {
            std::vector<TransitionDef> out;
            size_t i = 0;
            for (const auto& t : raw_list.as_array()) {
              TransitionDef td;
              const std::string& to = t["to"].as_string();
              td.to = to == "$exit" ? -1 : node_index.at(to);
              if (const Json* when = opt(t, "when")) td.when = c.expr_site(*when, args);
              td.effects = c.block_site(opt(t, "effects"), args);
              td.key = owner;
              td.key.push_back(std::to_string(i++));
              out.push_back(std::move(td));
            }
            return out;
          };
          node.transitions = transitions(list_or_empty(raw, "transitions"), {"node", node.id}, {});
          for (const auto& ra : list_or_empty(raw, "actions").as_array()) {
            ActionDef ad;
            ad.name = ra["name"].as_string();
            ad.name_id = action_name_id(ad.name);
            ad.node = index;
            std::vector<std::string> args;
            for (const auto& p : list_or_empty(ra, "params").as_array()) {
              args.push_back(p["name"].as_string());
            }
            for (const auto& p : list_or_empty(ra, "params").as_array()) {
              ActionParamDef pd;
              pd.name = p["name"].as_string();
              pd.type = types.parse(p["type"]);
              const Json& domain = p["domain"];
              pd.domain = c.expr_site(domain, args);
              const std::string& head = domain.at(0).as_string();
              if (head == "subsets") {
                pd.member = DomainKind::Subsets;
                pd.coll = c.expr_site(domain.at(1), args);
                pd.lo = c.expr_site(domain.at(2), args);
                pd.hi = c.expr_site(domain.at(3), args);
              } else if (head == "range") {
                pd.member = DomainKind::Range;
                pd.lo = c.expr_site(domain.at(1), args);
                pd.hi = c.expr_site(domain.at(2), args);
              } else if (head == "enum_values") {
                pd.member = DomainKind::EnumValues;
                int e = types.enum_id(domain.at(1).as_string());
                if (e < 0) throw IrError("enumerado desconocido: " + domain.at(1).as_string());
                pd.enum_type = static_cast<uint32_t>(e);
              }
              pd.policy = c.policy(opt(p, "visibility"), Policy::Kind::All);
              pd.size_policy = c.policy(opt(p, "size_visibility"), Policy::Kind::All);
              ad.params.push_back(std::move(pd));
            }
            if (const Json* req = opt(ra, "requires")) ad.requires_expr = c.expr_site(*req, args);
            ad.effects = c.block_site(opt(ra, "effects"), args);
            ad.transitions =
                transitions(list_or_empty(ra, "transitions"), {"action", node.id, ad.name}, args);
            ad.policy = c.policy(opt(ra, "visibility"), Policy::Kind::All);
            ad.query_frame = std::max<uint32_t>(ad.requires_expr.frame,
                                                static_cast<uint32_t>(ad.params.size()));
            for (const auto& p : ad.params) {
              ad.query_frame = std::max(ad.query_frame, p.domain.frame);
            }
            node.actions.push_back(std::move(ad));
          }
          if (const Json* e = opt(raw, "actor")) node.actor = c.expr_site(*e);
          if (const Json* e = opt(raw, "actors")) node.actors = c.expr_site(*e);
          if (const Json* e = opt(raw, "eligible")) node.eligible = c.expr_site(*e);
          if (const Json* e = opt(raw, "order")) node.order = c.expr_site(*e);
          if (const Json* e = opt(raw, "payoff")) node.payoff = c.expr_site(*e);
          if (const Json* e = opt(raw, "rank")) node.rank = c.expr_site(*e);
          if (const Json* b = opt(raw, "resolve")) {
            node.resolve = c.block_site(b);
            node.has_resolve = true;
          }
          if (const Json* b = opt(raw, "effects")) {
            node.effects = c.block_site(b);
            node.has_effects = true;
          }
          if (const Json* b = opt(raw, "on_enter")) {
            node.on_enter = c.block_site(b);
            node.has_on_enter = true;
          }
          if (const Json* b = opt(raw, "on_exit")) {
            node.on_exit = c.block_site(b);
            node.has_on_exit = true;
          }
          if (const Json* m = opt(raw, "mode")) {
            const std::string& mode = m->as_string();
            node.mode = mode == "priority"  ? WindowMode::Priority
                        : mode == "collect" ? WindowMode::Collect
                        : mode == "race"    ? WindowMode::Race
                                            : throw IrError("modo de ventana desconocido: " + mode);
          }
          if (const Json* s = opt(raw, "start")) node.start = node_index.at(s->as_string());
          if (node.kind == NodeKind::Phase) {
            std::vector<int> inner = ancestors;
            inner.push_back(index);
            compile_nodes(raw["nodes"], inner);
          }
        }
      };
  compile_nodes(flow["nodes"], {});
  start = node_index.at(flow["start"].as_string());
  for (const auto& node : nodes) {
    std::vector<int> path = node.ancestors;
    path.push_back(node.index);
    paths.push_back(std::move(path));
  }
}

}  // namespace gh
