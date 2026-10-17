// SPDX-License-Identifier: Apache-2.0
// El intérprete del código de bytes. Cada operador reproduce el de `gamehub.engine.expr`
// (resultados y errores); la documentación de su semántica está en docs/wiki/engine.md.
#include "gamehub/vm.hpp"

#include <algorithm>
#include <numeric>

#include "gamehub/errors.hpp"

namespace gh {

// --- Errores y comprobaciones ------------------------------------------------------------------

void rule_error(const std::string& message) { throw RuleError(message); }

namespace {

std::string repr(const Value& v, const Ctx& ctx) { return ctx.game->types.repr(v); }

}  // namespace

bool expect_bool(const Value& v, const char* op, const Ctx& ctx) {
  if (v.tag == Tag::Bool) return v.i != 0;
  rule_error(std::string("'") + op + "' espera un booleano, recibe " + repr(v, ctx));
}

const Value& expect_num(const Value& v, const char* op, const Ctx& ctx) {
  if (v.tag == Tag::Int || v.tag == Tag::Rat) return v;
  rule_error(std::string("'") + op + "' espera números, recibe " + repr(v, ctx));
}

int64_t expect_seat(const Value& v, int n, const char* op, const Ctx& ctx) {
  if (v.tag != Tag::Int || v.i < 0 || v.i >= n) {
    rule_error(std::string("'") + op + "': asiento inválido " + repr(v, ctx) + " (hay " +
               std::to_string(n) + ")");
  }
  return v.i;
}

Items iterate(const Value& coll, const char* op, const Ctx& ctx) {
  Items it;
  switch (coll.tag) {
    case Tag::Tuple:
    case Tag::Set:
    case Tag::Zone:
      it.holder = coll;
      it.data = coll.arr()->items();
      it.size = coll.arr()->n;
      return it;
    case Tag::Map:
      it.holder = coll;
      it.data = coll.arr()->items();
      it.size = coll.arr()->n / 2;
      it.stride = 2;
      return it;
    case Tag::Cell:
      it.holder = Value::tuple(ValueVec{Value::integer(coll.cell_row()),
                                                  Value::integer(coll.cell_col())});
      it.data = it.holder.arr()->items();
      it.size = 2;
      return it;
    default:
      rule_error(std::string("'") + op + "' espera una colección, recibe " + repr(coll, ctx));
  }
}

Value index_value(const Value& coll, const Value& key, const Ctx& ctx) {
  if (coll.is_tuple_like()) {
    size_t n = coll.tuple_size();
    if (key.tag != Tag::Int || key.i < 0 || static_cast<size_t>(key.i) >= n) {
      rule_error("índice fuera de rango: " + repr(key, ctx) + " (longitud " + std::to_string(n) +
                 ")");
    }
    return coll.tuple_at(static_cast<size_t>(key.i));
  }
  if (coll.tag == Tag::Grid) {
    const ArrayObj* g = coll.arr();
    if (key.tag == Tag::Cell) {
      int64_t r = key.cell_row(), c = key.cell_col();
      if (r >= 0 && r < g->b && c >= 0 && c < g->a) return g->items()[r * g->a + c];
    } else if (key.tag == Tag::Tuple && key.arr()->n == 2) {
      const Value* rc = key.arr()->items();
      if (rc[0].tag == Tag::Int && rc[1].tag == Tag::Int && rc[0].i >= 0 && rc[0].i < g->b &&
          rc[1].i >= 0 && rc[1].i < g->a) {
        return g->items()[rc[0].i * g->a + rc[1].i];
      }
    }
    rule_error("casilla fuera de la rejilla " + std::to_string(g->b) + "×" + std::to_string(g->a) +
               ": " + repr(key, ctx));
  }
  if (coll.tag == Tag::Map) {
    const ArrayObj* m = coll.arr();
    // Claves en orden canónico: búsqueda binaria.
    size_t lo = 0, hi = m->n / 2;
    while (lo < hi) {
      size_t mid = (lo + hi) / 2;
      int c = compare_canonical(m->items()[2 * mid], key);
      if (c == 0) return m->items()[2 * mid + 1];
      if (c < 0) {
        lo = mid + 1;
      } else {
        hi = mid;
      }
    }
    // Por si la clave es igual a otra con distinto orden canónico (True y 1): búsqueda lineal.
    for (size_t k = 0; k < m->n / 2; ++k) {
      if (equals(m->items()[2 * k], key)) return m->items()[2 * k + 1];
    }
    rule_error("clave inexistente en el mapa: " + repr(key, ctx));
  }
  rule_error("no se puede indexar " + repr(coll, ctx));
}

int compare_ir(const Value& a, const Value& b, const char* op, const Ctx& ctx) {
  if (a.tag == Tag::Enum && b.tag == Tag::Enum && a.x == b.x) return (a.i > b.i) - (a.i < b.i);
  if (a.tag == Tag::Text && b.tag == Tag::Text) {
    int c = a.as_text().compare(b.as_text());
    return (c > 0) - (c < 0);
  }
  expect_num(a, op, ctx);
  expect_num(b, op, ctx);
  if (a.tag == Tag::Int && b.tag == Tag::Int) return (a.i > b.i) - (a.i < b.i);
  return a.as_rational().compare(b.as_rational());
}

// --- Azar --------------------------------------------------------------------------------------

namespace {

void check_bound(int64_t n) {
  if (n <= 0) rule_error("sorteo sobre un conjunto vacío");
}

}  // namespace

int64_t RngDraws::uniform(int64_t n) {
  check_bound(n);
  if (n > (int64_t(1) << 32)) throw std::out_of_range("cota fuera de rango");
  int64_t d = rng_.below(static_cast<uint64_t>(n));
  taken.push_back(d);
  return d;
}

int64_t RngDraws::weighted(const std::vector<Rational>& probs) {
  // Denominador común (mcm) de las probabilidades.
  int64_t denominator = 1;
  for (const auto& p : probs) {
    int64_t g = std::gcd(denominator, p.den);
    __int128 lcm = __int128(denominator / g) * p.den;
    if (lcm > (__int128(1) << 32)) {
      rule_error("denominador de probabilidad demasiado grande");
    }
    denominator = static_cast<int64_t>(lcm);
  }
  int64_t r = rng_.below(static_cast<uint64_t>(denominator));
  __int128 acc = 0;
  for (size_t k = 0; k < probs.size(); ++k) {
    acc += __int128(probs[k].num) * (denominator / probs[k].den);
    if (r < acc) {
      taken.push_back(static_cast<int64_t>(k));
      return static_cast<int64_t>(k);
    }
  }
  rule_error("las probabilidades no suman 1");
}

int64_t ScriptedDraws::next(int64_t n) {
  if (pos_ >= draws_.size()) throw NeedDraw{n, {}};
  int64_t d = draws_[pos_];
  if (d < 0 || d >= n) {
    throw IllegalAction("sorteo " + std::to_string(d) + " fuera de rango [0, " +
                        std::to_string(n) + ")");
  }
  ++pos_;
  return d;
}

int64_t ScriptedDraws::uniform(int64_t n) {
  check_bound(n);
  int64_t d = next(n);
  if (track_probability) probability = probability / Rational::integer(n);
  return d;
}

int64_t ScriptedDraws::weighted(const std::vector<Rational>& probs) {
  int64_t i;
  try {
    i = next(static_cast<int64_t>(probs.size()));
  } catch (NeedDraw& need) {
    need.probs = probs;
    throw;
  }
  if (probs[static_cast<size_t>(i)].num == 0) {
    throw IllegalAction("sorteo " + std::to_string(i) + " con probabilidad 0");
  }
  if (track_probability) probability = probability * probs[static_cast<size_t>(i)];
  return i;
}

// --- Eventos -----------------------------------------------------------------------------------

const Json* Event::for_seat(int seat) const {
  if (seat == NO_SEAT) return full.get();
  if (seat == PUBLIC) return pub.get();
  return seen.at(static_cast<size_t>(seat)).get();
}

Event Event::shared(Json payload, int n) {
  auto p = std::make_shared<const Json>(std::move(payload));
  return Event{p, std::vector<JsonPtr>(static_cast<size_t>(n), p), p};
}

// --- Memo --------------------------------------------------------------------------------------

uint64_t MemoTable::key_hash(uint32_t fn, const Value* args, uint32_t argc) {
  uint64_t h = mix64(0x6d656d6fULL ^ fn);
  for (uint32_t k = 0; k < argc; ++k) h = mix64(h ^ hash_value(args[k]));
  return h | 1;
}

const Value* MemoTable::find(uint32_t fn, const Value* args, uint32_t argc, uint64_t hash) const {
  if (table_.empty()) return nullptr;
  size_t mask = table_.size() - 1;
  for (size_t k = hash & mask;; k = (k + 1) & mask) {
    const Entry& e = table_[k];
    if (!live(e)) return nullptr;
    if (e.hash == hash && e.fn == fn && e.argc == argc) {
      bool same = true;
      for (uint32_t a = 0; a < argc; ++a) {
        if (!equals(e.arg(a), args[a])) {
          same = false;
          break;
        }
      }
      if (same) return &e.result;
    }
  }
}

void MemoTable::grow() {
  PoolVec<Entry> old = std::move(table_);
  table_ = PoolVec<Entry>(old.empty() ? 16 : old.size() * 2);
  uint32_t current = generation_;
  generation_ = 1;
  count_ = 0;
  size_t mask = table_.size() - 1;
  for (auto& e : old) {
    if (e.generation != current) continue;
    size_t k = e.hash & mask;
    while (live(table_[k])) k = (k + 1) & mask;
    e.generation = generation_;
    table_[k] = std::move(e);
    ++count_;
  }
}

void MemoTable::insert(uint32_t fn, const Value* args, uint32_t argc, uint64_t hash,
                       const Value& result) {
  if ((count_ + 1) * 4 > table_.size() * 3) grow();
  size_t mask = table_.size() - 1;
  size_t k = hash & mask;
  while (live(table_[k])) k = (k + 1) & mask;
  Entry& e = table_[k];
  e.generation = generation_;
  e.hash = hash;
  e.fn = fn;
  e.argc = argc;
  for (uint32_t a = 0; a < argc && a < INLINE_ARGS; ++a) e.args[a] = args[a];
  e.more.clear();
  for (uint32_t a = INLINE_ARGS; a < argc; ++a) e.more.push_back(args[a]);
  e.result = result;
  ++count_;
}

// --- VM ----------------------------------------------------------------------------------------

namespace {

constexpr size_t STACK_SIZE = 1 << 16;
constexpr size_t SLOTS_SIZE = 1 << 16;
constexpr size_t STATIC_MEMO_LIMIT = 200'000;

}  // namespace

const char* const ITER_OPS[] = {"all",    "any",    "count",  "sum",    "map",
                                "flat_map", "filter", "argmax", "argmin", "max_of",
                                "min_of", "sort_by"};

Vm::Vm()
    : stack_(new Value[STACK_SIZE]),
      stack_end_(stack_.get() + STACK_SIZE),
      sp_(stack_.get()),
      slots_(new Value[SLOTS_SIZE]),
      slots_end_(slots_.get() + SLOTS_SIZE),
      slot_top_(slots_.get()) {}

Vm::~Vm() = default;

Vm& vm() {
  thread_local Vm instance;
  return instance;
}

Value* Vm::push_slots(uint32_t n) {
  if (slot_top_ + n > slots_end_) rule_error("demasiada profundidad de llamadas");
  Value* s = slot_top_;
  slot_top_ += n;
  return s;
}

void Vm::pop_slots(uint32_t n) {
  for (uint32_t k = 0; k < n; ++k) *--slot_top_ = Value();
}

Value Vm::eval(const Chunk& chunk, Ctx& ctx, Frame& frame) {
  Value* base = sp_;
  size_t builders = nbuilders_;
  try {
    return run(chunk, ctx, frame);
  } catch (...) {
    while (sp_ > base) *--sp_ = Value();
    nbuilders_ = builders;
    throw;
  }
}

Value Vm::call(uint32_t fn_index, const Value* args, Ctx& ctx) {
  const GameDef& game = *ctx.game;
  const FunctionDef& fn = game.functions[fn_index];
  MemoTable* memo = nullptr;
  if (fn.memo == MemoKind::Static) {
    memo = game.static_memo.get();
    if (memo->size() > STATIC_MEMO_LIMIT) memo->clear();
  } else if (fn.memo == MemoKind::State && !fn.memo_off) {
    memo = ctx.memo;
  } else if (fn.memo == MemoKind::Match && ctx.match_memo != nullptr) {
    memo = ctx.match_memo;
    if (memo->size() > STATIC_MEMO_LIMIT) memo->clear();
  }
  uint64_t hash = 0;
  if (memo != nullptr) {
    hash = MemoTable::key_hash(fn_index, args, fn.arity);
    ++fn.memo_lookups;
    if (const Value* found = memo->find(fn_index, args, fn.arity, hash)) {
      ++fn.memo_hits;
      return *found;
    }
    if (fn.memo == MemoKind::State && fn.memo_lookups >= 4096) {
      // Menos de un acierto de cada 16: memorizarla cuesta más de lo que ahorra.
      if (fn.memo_hits * 16 < fn.memo_lookups) fn.memo_off = true;
      fn.memo_lookups = fn.memo_hits = 0;
    }
  }
  Value result;
  // Con plugin nativo, el plugin (si los argumentos caben en su ABI); si no, la referencia.
  if (fn.plugin.handle < 0 || !call_native(fn.plugin, game.types, args, result, fn.native)) {
    ScopedFrame scope(*this, fn.body.frame);
    for (uint32_t k = 0; k < fn.arity; ++k) scope.frame.slots[k] = args[k];
    result = run(fn.body.chunk, ctx, scope.frame);
  }
  if (memo != nullptr) memo->insert(fn_index, args, fn.arity, hash, result);
  return result;
}

Value eval_expr(const Expr& e, Ctx& ctx, int32_t actor, const Value* args, uint32_t argc) {
  Vm& machine = ctx.machine();
  ScopedFrame scope(machine, e.frame);
  scope.frame.actor = actor;
  for (uint32_t k = 0; k < argc; ++k) scope.frame.slots[k] = args[k];
  return machine.eval(e.chunk, ctx, scope.frame);
}

void run_code(const Code& c, Ctx& ctx, int32_t actor, const Value* args, uint32_t argc) {
  if (c.block.empty()) return;
  ScopedFrame scope(ctx.machine(), c.frame);
  scope.frame.actor = actor;
  for (uint32_t k = 0; k < argc; ++k) scope.frame.slots[k] = args[k];
  c.block.run(ctx, scope.frame);
}

// --- Operadores --------------------------------------------------------------------------------

namespace {

Value num_add(const Value& a, const Value& b) {
  if (a.tag == Tag::Int && b.tag == Tag::Int) return Value::integer(checked_add(a.i, b.i));
  return Value::number(a.as_rational() + b.as_rational());
}

Value num_mul(const Value& a, const Value& b) {
  if (a.tag == Tag::Int && b.tag == Tag::Int) return Value::integer(checked_mul(a.i, b.i));
  return Value::number(a.as_rational() * b.as_rational());
}

bool is_zero(const Value& v) { return v.tag == Tag::Int && v.i == 0; }

const Value& expect_tuple(const Value& v, const char* op, const Ctx& ctx) {
  if (!v.is_tuple_like()) {
    rule_error(std::string("'") + op + "' espera una lista, recibe " + repr(v, ctx));
  }
  return v;
}

const ArrayObj* expect_grid(const Value& v, const char* op, const Ctx& ctx) {
  if (v.tag != Tag::Grid) {
    rule_error(std::string("'") + op + "' espera una rejilla, recibe " + repr(v, ctx));
  }
  return v.arr();
}

const ArrayObj* expect_zone(const Value& v, const char* op, const Ctx& ctx) {
  if (v.tag != Tag::Zone) {
    rule_error(std::string("'") + op + "' espera una zona o bolsa, recibe " + repr(v, ctx));
  }
  return v.arr();
}

Value make_set_from(const Value& v, const char* op, const Ctx& ctx) {
  if (v.tag == Tag::Set) return v;
  Items it = iterate(v, op, ctx);
  ValueVec items;
  items.reserve(it.size);
  for (size_t k = 0; k < it.size; ++k) items.push_back(it[k]);
  return Value::set(std::move(items));
}

bool items_contain(const Items& it, const Value& x) {
  for (size_t k = 0; k < it.size; ++k) {
    if (equals(it[k], x)) return true;
  }
  return false;
}

// Cota de un `range`: enteros (un racional no es un índice válido en Python).
int64_t range_bound(const Value& v, const char* op, const Ctx& ctx) {
  expect_num(v, op, ctx);
  if (v.tag != Tag::Int) rule_error(std::string("'") + op + "' necesita enteros");
  return v.i;
}

bool in_bounds(const ArrayObj* g, const Value& cell) {
  int64_t r, c;
  if (cell.tag == Tag::Cell) {
    r = cell.cell_row();
    c = cell.cell_col();
  } else if (cell.tag == Tag::Tuple && cell.arr()->n == 2 &&
             cell.arr()->items()[0].tag == Tag::Int && cell.arr()->items()[1].tag == Tag::Int) {
    r = cell.arr()->items()[0].i;
    c = cell.arr()->items()[1].i;
  } else {
    rule_error("se esperaba una casilla");
  }
  return r >= 0 && r < g->b && c >= 0 && c < g->a;
}

void cell_parts(const Value& cell, int64_t& r, int64_t& c) {
  if (cell.tag == Tag::Cell) {
    r = cell.cell_row();
    c = cell.cell_col();
    return;
  }
  if (cell.tag == Tag::Tuple && cell.arr()->n == 2 && cell.arr()->items()[0].tag == Tag::Int &&
      cell.arr()->items()[1].tag == Tag::Int) {
    r = cell.arr()->items()[0].i;
    c = cell.arr()->items()[1].i;
    return;
  }
  rule_error("se esperaba una casilla");
}

Value subsets(const Value& coll, const Value& lo_v, const Value& hi_v, const Ctx& ctx) {
  Items it = iterate(coll, "subsets", ctx);
  int64_t lo = range_bound(lo_v, "subsets", ctx);
  int64_t hi = range_bound(hi_v, "subsets", ctx);
  ValueVec ordered;
  ordered.reserve(it.size);
  for (size_t k = 0; k < it.size; ++k) ordered.push_back(it[k]);
  std::stable_sort(ordered.begin(), ordered.end(), canonical_less);
  bool distinct = true;
  for (size_t k = 1; k < ordered.size(); ++k) {
    if (equals(ordered[k - 1], ordered[k])) {
      distinct = false;
      break;
    }
  }
  int64_t n = static_cast<int64_t>(ordered.size());
  ValueVec result;
  PoolVec<size_t> idx;
  for (int64_t size = std::max<int64_t>(lo, 0); size <= std::min(hi, n); ++size) {
    // Combinaciones lexicográficas de índices (itertools.combinations).
    idx.resize(static_cast<size_t>(size));
    for (int64_t k = 0; k < size; ++k) idx[static_cast<size_t>(k)] = static_cast<size_t>(k);
    ValueVec previous_of_size;
    while (true) {
      Value combo = Value::alloc_array(Tag::Tuple, static_cast<uint32_t>(size));
      for (int64_t k = 0; k < size; ++k) {
        combo.arr()->items()[k] = ordered[idx[static_cast<size_t>(k)]];
      }
      if (distinct) {
        result.push_back(std::move(combo));
      } else {
        // dict.fromkeys: la primera aparición de cada combinación.
        bool seen = false;
        for (const auto& prev : previous_of_size) {
          if (equals(prev, combo)) {
            seen = true;
            break;
          }
        }
        if (!seen) {
          previous_of_size.push_back(combo);
          result.push_back(std::move(combo));
        }
      }
      int64_t k = size - 1;
      while (k >= 0 && idx[static_cast<size_t>(k)] == static_cast<size_t>(n - size + k)) --k;
      if (k < 0) break;
      ++idx[static_cast<size_t>(k)];
      for (int64_t j = k + 1; j < size; ++j) {
        idx[static_cast<size_t>(j)] = idx[static_cast<size_t>(j - 1)] + 1;
      }
    }
  }
  return Value::tuple(std::move(result));
}

Value grid_lines(const ArrayObj* g, int64_t k) {
  static const int dirs[4][2] = {{0, 1}, {1, 0}, {1, 1}, {1, -1}};
  ValueVec lines;
  int64_t h = g->b, w = g->a;
  if (k >= 1) {
    for (const auto& d : dirs) {
      for (int64_t r = 0; r < h; ++r) {
        for (int64_t c = 0; c < w; ++c) {
          int64_t er = r + d[0] * (k - 1), ec = c + d[1] * (k - 1);
          if (er < 0 || er >= h || ec < 0 || ec >= w) continue;
          Value line = Value::alloc_array(Tag::Tuple, static_cast<uint32_t>(k));
          for (int64_t i = 0; i < k; ++i) {
            line.arr()->items()[i] = Value::cell(r + d[0] * i, c + d[1] * i);
          }
          lines.push_back(std::move(line));
        }
      }
    }
  }
  return Value::tuple(std::move(lines));
}

}  // namespace

// --- El bucle del intérprete -------------------------------------------------------------------

#if defined(__GNUC__) && !defined(__EMSCRIPTEN__) && !defined(GH_COUNT_OPS)
#define GH_THREADED 1
#else
#define GH_THREADED 0
// Las etiquetas del despacho directo quedan sin usar con el `switch`.
#pragma clang diagnostic ignored "-Wunused-label"
#endif

#ifdef GH_COUNT_OPS
uint64_t gh_op_counts[256];
#endif

Value Vm::run(const Chunk& chunk, Ctx& ctx, Frame& frame) {
  // Los punteros de pila e instrucción viven en registros; `sp_` se actualiza antes de llamar a
  // otra función de la IR y al salir (también por una excepción).
  Value* sp = sp_;
  if (sp + chunk.max_stack + 1 > stack_end_) rule_error("pila de evaluación agotada");
  const uint32_t* code = chunk.code.data();
  const uint32_t* ip = code;
  const Value* consts = chunk.consts.data();
  Value* slots = frame.slots;
  const int n = ctx.n;

#define POP() (std::move(*--sp))
// Las casillas por encima de la cima nunca guardan valores del montón: se construye en sitio.
#define PUSH(v) (new (sp++) Value(v))
#define TOP (sp[-1])

#if GH_THREADED
  // Despacho directo: cada instrucción salta a la siguiente (el `switch` queda de respaldo).
  static void* const dispatch[] = {
      &&L_OP_CONST,
      &&L_OP_VAR,
      &&L_OP_PARAM,
      &&L_OP_LOAD,
      &&L_OP_STORE,
      &&L_OP_ACTOR,
      &&L_OP_VIEWER,
      &&L_OP_OWNER,
      &&L_OP_FACE_UP,
      &&L_OP_SEATS,
      &&L_OP_AT,
      &&L_OP_LIST,
      &&L_OP_SET,
      &&L_OP_STRUCT,
      &&L_OP_CELL,
      &&L_OP_ADD,
      &&L_OP_SUB,
      &&L_OP_MUL,
      &&L_OP_DIV,
      &&L_OP_IDIV,
      &&L_OP_MOD,
      &&L_OP_NEG,
      &&L_OP_ABS,
      &&L_OP_MIN,
      &&L_OP_MAX,
      &&L_OP_EQ,
      &&L_OP_NE,
      &&L_OP_LT,
      &&L_OP_LE,
      &&L_OP_GT,
      &&L_OP_GE,
      &&L_OP_NOT,
      &&L_OP_AND_TEST,
      &&L_OP_OR_TEST,
      &&L_OP_JUMP,
      &&L_OP_JUMP_IF_FALSE,
      &&L_OP_POP,
      &&L_OP_IS_NONE,
      &&L_OP_UNWRAP,
      &&L_OP_LEN,
      &&L_OP_CONTAINS,
      &&L_OP_INDEX,
      &&L_OP_VAR_INDEX,
      &&L_OP_FIELD,
      &&L_OP_FIRST,
      &&L_OP_LAST,
      &&L_OP_ONLY,
      &&L_OP_APPEND,
      &&L_OP_CONCAT,
      &&L_OP_RANGE,
      &&L_OP_SLICE,
      &&L_OP_REVERSE,
      &&L_OP_DISTINCT,
      &&L_OP_UNION,
      &&L_OP_INTERSECTION,
      &&L_OP_DIFFERENCE,
      &&L_OP_SUBSETS,
      &&L_OP_ITER_INIT,
      &&L_OP_ITER_NEXT,
      &&L_OP_ITER_LOOP,
      &&L_OP_ITER_FIRST,
      &&L_OP_ALL_LOOP,
      &&L_OP_ANY_LOOP,
      &&L_OP_COUNT_LOOP,
      &&L_OP_SUM_LOOP,
      &&L_OP_PUSH_LOOP,
      &&L_OP_FILTER_LOOP,
      &&L_OP_ALL_STEP,
      &&L_OP_ANY_STEP,
      &&L_OP_COUNT_STEP,
      &&L_OP_SUM_STEP,
      &&L_OP_BUILD_BEGIN,
      &&L_OP_BUILD_PUSH,
      &&L_OP_BUILD_LIST,
      &&L_OP_FILTER_STEP,
      &&L_OP_FLAT_STEP,
      &&L_OP_ARGBEST_STEP,
      &&L_OP_BEST_OF,
      &&L_OP_SORT_PUSH,
      &&L_OP_SORT_BY,
      &&L_OP_NEXT_SEAT,
      &&L_OP_PREV_SEAT,
      &&L_OP_OTHER_SEAT,
      &&L_OP_SEATS_FROM,
      &&L_OP_CELLS,
      &&L_OP_LINES,
      &&L_OP_NEIGHBORS,
      &&L_OP_IN_BOUNDS,
      &&L_OP_SIZE,
      &&L_OP_ITEMS,
      &&L_OP_TOP,
      &&L_OP_ORD,
      &&L_OP_CALL,
      &&L_OP_WIN_LOSS,
      &&L_OP_FILL,
      &&L_OP_VAR_INDEX_LOCAL,
      &&L_OP_EQ_LOCAL,
      &&L_OP_NE_LOCAL,
      &&L_OP_EQ_CONST,
      &&L_OP_NE_CONST,
      &&L_OP_RETURN};
  static_assert(sizeof(dispatch) / sizeof(*dispatch) == OP_RETURN + 1);
#define GH_LABEL(op) L_##op
#define DISPATCH() goto* dispatch[*ip++]
#else
#define GH_LABEL(op) L_##op
#define DISPATCH() break
#endif

  try {
  while (true) {
#ifdef GH_COUNT_OPS
    ++gh_op_counts[*ip];
#endif
    switch (static_cast<Op>(*ip++)) {
      case OP_CONST:
      GH_LABEL(OP_CONST):
        PUSH(consts[*ip++]);
        DISPATCH();
      case OP_VAR:
      GH_LABEL(OP_VAR):
        PUSH((*ctx.store)[*ip++]);
        DISPATCH();
      case OP_PARAM:
      GH_LABEL(OP_PARAM):
        PUSH((*ctx.params)[*ip++]);
        DISPATCH();
      case OP_LOAD:
      GH_LABEL(OP_LOAD):
        PUSH(slots[*ip++]);
        DISPATCH();
      case OP_STORE:
      GH_LABEL(OP_STORE):
        slots[*ip++] = POP();
        DISPATCH();
      case OP_ACTOR:
      GH_LABEL(OP_ACTOR):
        if (frame.actor == NO_SEAT) rule_error("'actor' no está definido en este contexto");
        PUSH(Value::integer(frame.actor));
        DISPATCH();
      case OP_VIEWER:
      GH_LABEL(OP_VIEWER):
        if (frame.viewer == NO_SEAT) rule_error("'viewer' no está definido en este contexto");
        PUSH(Value::integer(frame.viewer));
        DISPATCH();
      case OP_OWNER:
      GH_LABEL(OP_OWNER):
        if (frame.owner == NO_SEAT) rule_error("'owner' no está definido en este contexto");
        PUSH(Value::integer(frame.owner));
        DISPATCH();
      case OP_FACE_UP:
      GH_LABEL(OP_FACE_UP):
        if (frame.face_up < 0) rule_error("'item_face_up' no está definido en este contexto");
        PUSH(Value::boolean(frame.face_up != 0));
        DISPATCH();
      case OP_SEATS:
      GH_LABEL(OP_SEATS):
        PUSH(ctx.seats);
        DISPATCH();
      case OP_AT:
      GH_LABEL(OP_AT): {
        int node = static_cast<int>(*ip++);
        bool found = false;
        if (ctx.path != nullptr) {
          for (int p : *ctx.path) {
            if (p == node) {
              found = true;
              break;
            }
          }
        }
        PUSH(Value::boolean(found));
      }
        DISPATCH();

      // --- Constructores ---
      case OP_LIST:
      GH_LABEL(OP_LIST): {
        uint32_t count = *ip++;
        Value v = Value::alloc_array(Tag::Tuple, count);
        Value* dst = v.arr()->items();
        for (uint32_t k = count; k > 0; --k) dst[k - 1] = POP();
        PUSH(std::move(v));
      }
        DISPATCH();
      case OP_SET:
      GH_LABEL(OP_SET): {
        uint32_t count = *ip++;
        ValueVec items(count);
        for (uint32_t k = count; k > 0; --k) items[k - 1] = POP();
        PUSH(Value::set(std::move(items)));
      }
        DISPATCH();
      case OP_STRUCT:
      GH_LABEL(OP_STRUCT): {
        uint32_t type = *ip++;
        uint32_t count = *ip++;
        Value v = Value::alloc_array(Tag::Struct, count);
        v.arr()->a = type;
        Value* dst = v.arr()->items();
        for (uint32_t k = count; k > 0; --k) dst[k - 1] = POP();
        PUSH(std::move(v));
      }
        DISPATCH();
      case OP_CELL:
      GH_LABEL(OP_CELL): {
        Value c = POP();
        Value r = POP();
        if (r.tag == Tag::Int && c.tag == Tag::Int) {
          PUSH(Value::cell(r.i, c.i));
        } else {
          expect_num(r, "cell", ctx);
          expect_num(c, "cell", ctx);
          PUSH(Value::tuple(ValueVec{r, c}));
        }
      }
        DISPATCH();

      // --- Aritmética ---
      case OP_ADD:
      GH_LABEL(OP_ADD): {
        uint32_t count = *ip++;
        if (count == 2 && sp[-1].tag == Tag::Int && sp[-2].tag == Tag::Int) {
          int64_t b = sp[-1].i;
          --sp;
          sp[-1].i = checked_add(sp[-1].i, b);
          break;
        }
        Value* first = sp - count;
        for (Value* v = first; v < sp; ++v) expect_num(*v, "add", ctx);
        Value acc = Value::integer(0);
        for (Value* v = first; v < sp; ++v) acc = num_add(acc, *v);
        while (sp > first) *--sp = Value();
        PUSH(std::move(acc));
      }
        DISPATCH();
      case OP_SUB:
      GH_LABEL(OP_SUB): {
        Value b = POP();
        Value& a = TOP;
        if (a.tag == Tag::Int && b.tag == Tag::Int) {
          a.i = checked_sub(a.i, b.i);
        } else {
          expect_num(a, "sub", ctx);
          expect_num(b, "sub", ctx);
          a = Value::number(a.as_rational() - b.as_rational());
        }
      }
        DISPATCH();
      case OP_MUL:
      GH_LABEL(OP_MUL): {
        uint32_t count = *ip++;
        if (count == 2 && sp[-1].tag == Tag::Int && sp[-2].tag == Tag::Int) {
          int64_t b = sp[-1].i;
          --sp;
          sp[-1].i = checked_mul(sp[-1].i, b);
          break;
        }
        Value* first = sp - count;
        for (Value* v = first; v < sp; ++v) expect_num(*v, "mul", ctx);
        Value acc = Value::integer(1);
        for (Value* v = first; v < sp; ++v) acc = num_mul(acc, *v);
        while (sp > first) *--sp = Value();
        PUSH(std::move(acc));
      }
        DISPATCH();
      case OP_DIV:
      GH_LABEL(OP_DIV): {
        Value b = POP();
        Value a = POP();
        expect_num(b, "div", ctx);
        if (is_zero(b)) rule_error("división por cero");
        expect_num(a, "div", ctx);
        PUSH(Value::number(a.as_rational() / b.as_rational()));
      }
        DISPATCH();
      case OP_IDIV:
      GH_LABEL(OP_IDIV): {
        Value b = POP();
        Value a = POP();
        expect_num(b, "idiv", ctx);
        if (is_zero(b)) rule_error("división por cero");
        expect_num(a, "idiv", ctx);
        if (a.tag == Tag::Int && b.tag == Tag::Int) {
          PUSH(Value::integer(floor_div(a.i, b.i)));
        } else {
          PUSH(Value::integer((a.as_rational() / b.as_rational()).floor()));
        }
      }
        DISPATCH();
      case OP_MOD:
      GH_LABEL(OP_MOD): {
        Value b = POP();
        Value a = POP();
        expect_num(b, "mod", ctx);
        if (is_zero(b)) rule_error("módulo por cero");
        expect_num(a, "mod", ctx);
        if (a.tag == Tag::Int && b.tag == Tag::Int) {
          PUSH(Value::integer(floor_mod(a.i, b.i)));
        } else {
          PUSH(Value::number(a.as_rational().floor_mod(b.as_rational())));
        }
      }
        DISPATCH();
      case OP_NEG:
      GH_LABEL(OP_NEG): {
        Value& a = TOP;
        expect_num(a, "neg", ctx);
        if (a.tag == Tag::Int) {
          a.i = checked_neg(a.i);
        } else {
          a = Value::number(-a.as_rational());
        }
      }
        DISPATCH();
      case OP_ABS:
      GH_LABEL(OP_ABS): {
        Value& a = TOP;
        expect_num(a, "abs", ctx);
        if (a.tag == Tag::Int) {
          if (a.i < 0) a.i = checked_neg(a.i);
        } else if (a.as_rational().num < 0) {
          a = Value::number(-a.as_rational());
        }
      }
        DISPATCH();
      case OP_MIN:
      GH_LABEL(OP_MIN):
      case OP_MAX:
      GH_LABEL(OP_MAX): {
        bool is_min = ip[-1] == OP_MIN;
        const char* name = is_min ? "min" : "max";
        uint32_t count = *ip++;
        Value* first = sp - count;
        if (count == 0) rule_error(std::string("'") + name + "' sin argumentos");
        for (Value* v = first; v < sp; ++v) expect_num(*v, name, ctx);
        Value* best = first;
        for (Value* v = first + 1; v < sp; ++v) {
          int c = (v->tag == Tag::Int && best->tag == Tag::Int)
                      ? (v->i > best->i) - (v->i < best->i)
                      : v->as_rational().compare(best->as_rational());
          if (is_min ? c < 0 : c > 0) best = v;
        }
        Value result = *best;
        while (sp > first) *--sp = Value();
        PUSH(std::move(result));
      }
        DISPATCH();

      // --- Comparación ---
      case OP_EQ:
      GH_LABEL(OP_EQ):
      case OP_NE:
      GH_LABEL(OP_NE): {
        bool eq = ip[-1] == OP_EQ;
        Value& b = sp[-1];
        Value& a = sp[-2];
        bool same;
        if (a.tag == b.tag && !is_heap_tag(a.tag)) {
          same = a.x == b.x && a.i == b.i;  // escalares en línea: comparar los bits
        } else {
          same = equals(a, b);
        }
        b = Value();
        --sp;
        a = Value::boolean(same == eq);
      }
        DISPATCH();
      case OP_LT:
      GH_LABEL(OP_LT):
      case OP_LE:
      GH_LABEL(OP_LE):
      case OP_GT:
      GH_LABEL(OP_GT):
      case OP_GE:
      GH_LABEL(OP_GE): {
        Op op = static_cast<Op>(ip[-1]);
        Value b = POP();
        Value& a = TOP;
        int c;
        if (a.tag == Tag::Int && b.tag == Tag::Int) {
          c = (a.i > b.i) - (a.i < b.i);
        } else {
          static const char* names[] = {"lt", "le", "gt", "ge"};
          c = compare_ir(a, b, names[op - OP_LT], ctx);
        }
        bool r = op == OP_LT ? c < 0 : op == OP_LE ? c <= 0 : op == OP_GT ? c > 0 : c >= 0;
        a = Value::boolean(r);
      }
        DISPATCH();

      // --- Lógica y control ---
      case OP_NOT:
      GH_LABEL(OP_NOT): {
        Value& a = TOP;
        a = Value::boolean(!expect_bool(a, "not", ctx));
      }
        DISPATCH();
      case OP_AND_TEST:
      GH_LABEL(OP_AND_TEST): {
        uint32_t target = *ip++;
        Value v = POP();
        if (v.tag == Tag::Bool && v.i == 0) {
          PUSH(Value::boolean(false));
          ip = code + target;
        } else if (v.tag != Tag::Bool) {
          expect_bool(v, "and", ctx);
        }
      }
        DISPATCH();
      case OP_OR_TEST:
      GH_LABEL(OP_OR_TEST): {
        uint32_t target = *ip++;
        Value v = POP();
        if (v.tag == Tag::Bool && v.i != 0) {
          PUSH(Value::boolean(true));
          ip = code + target;
        } else if (v.tag != Tag::Bool) {
          expect_bool(v, "or", ctx);
        }
      }
        DISPATCH();
      case OP_JUMP:
      GH_LABEL(OP_JUMP):
        ip = code + *ip;
        DISPATCH();
      case OP_JUMP_IF_FALSE:
      GH_LABEL(OP_JUMP_IF_FALSE): {
        uint32_t target = *ip++;
        uint32_t name = *ip++;
        Value& v = sp[-1];
        if (v.tag != Tag::Bool) expect_bool(v, name == 0 ? "if" : "case", ctx);
        bool b = v.i != 0;
        --sp;
        if (!b) ip = code + target;
      }
        DISPATCH();
      case OP_POP:
      GH_LABEL(OP_POP):
        *--sp = Value();
        DISPATCH();

      // --- Opcionales ---
      case OP_IS_NONE:
      GH_LABEL(OP_IS_NONE): {
        Value& a = TOP;
        a = Value::boolean(a.is_none());
      }
        DISPATCH();
      case OP_UNWRAP:
      GH_LABEL(OP_UNWRAP):
        if (TOP.is_none()) rule_error("'unwrap' sobre un opcional vacío");
        DISPATCH();

      // --- Colecciones ---
      case OP_LEN:
      GH_LABEL(OP_LEN): {
        Value& a = TOP;
        int64_t len;
        switch (a.tag) {
          case Tag::Cell:
            len = 2;
            break;
          case Tag::Tuple:
          case Tag::Set:
          case Tag::Zone:
            len = a.arr()->n;
            break;
          case Tag::Map:
            len = a.arr()->n / 2;
            break;
          case Tag::Text:
            len = static_cast<int64_t>(utf8_length(a.as_text()));
            break;
          default:
            rule_error("'len' no aplicable a " + repr(a, ctx));
        }
        a = Value::integer(len);
      }
        DISPATCH();
      case OP_CONTAINS:
      GH_LABEL(OP_CONTAINS): {
        Value x = POP();
        Value& coll = TOP;
        bool found;
        if (coll.tag == Tag::Text) {
          found = x.tag == Tag::Text && coll.as_text().find(x.as_text()) != std::string::npos;
        } else {
          found = items_contain(iterate(coll, "contains", ctx), x);
        }
        coll = Value::boolean(found);
      }
        DISPATCH();
      case OP_INDEX:
      GH_LABEL(OP_INDEX): {
        Value key = POP();
        Value& coll = TOP;
        if (coll.tag == Tag::Tuple && key.tag == Tag::Int && key.i >= 0 && key.i < coll.arr()->n) {
          coll = Value(coll.arr()->items()[key.i]);
        } else if (coll.tag == Tag::Grid && key.tag == Tag::Cell) {
          const ArrayObj* g = coll.arr();
          int64_t r = key.cell_row(), c = key.cell_col();
          if (r >= 0 && r < g->b && c >= 0 && c < g->a) {
            coll = Value(g->items()[r * g->a + c]);
          } else {
            coll = index_value(coll, key, ctx);
          }
        } else {
          coll = index_value(coll, key, ctx);
        }
      }
        DISPATCH();
      case OP_VAR_INDEX:
      GH_LABEL(OP_VAR_INDEX): {
        const Value& coll = (*ctx.store)[*ip++];
        Value& key = TOP;
        if (coll.tag == Tag::Tuple && key.tag == Tag::Int && key.i >= 0 && key.i < coll.arr()->n) {
          key = coll.arr()->items()[key.i];
        } else if (coll.tag == Tag::Grid && key.tag == Tag::Cell) {
          const ArrayObj* g = coll.arr();
          int64_t r = key.cell_row(), c = key.cell_col();
          if (r >= 0 && r < g->b && c >= 0 && c < g->a) {
            key = g->items()[r * g->a + c];
          } else {
            key = index_value(coll, key, ctx);
          }
        } else {
          key = index_value(coll, key, ctx);
        }
      }
        DISPATCH();
      case OP_FIELD:
      GH_LABEL(OP_FIELD): {
        uint32_t name = *ip++;
        Value& v = TOP;
        if (v.tag != Tag::Struct) rule_error("'field' espera un struct, recibe " + repr(v, ctx));
        int slot = ctx.game->field_slots[name][v.arr()->a];
        if (slot < 0) {
          rule_error(ctx.game->types.structs()[v.arr()->a].name + " no tiene el campo " +
                     ctx.game->field_names[name]);
        }
        v = Value(v.arr()->items()[slot]);
      }
        DISPATCH();
      case OP_FIRST:
      GH_LABEL(OP_FIRST):
      case OP_LAST:
      GH_LABEL(OP_LAST): {
        bool first = ip[-1] == OP_FIRST;
        const char* name = first ? "first" : "last";
        Value& v = TOP;
        expect_tuple(v, name, ctx);
        size_t len = v.tuple_size();
        if (len == 0) rule_error(std::string("'") + name + "' sobre una colección vacía");
        v = v.tuple_at(first ? 0 : len - 1);
      }
        DISPATCH();
      case OP_ONLY:
      GH_LABEL(OP_ONLY): {
        Value& v = TOP;
        Items it = iterate(v, "only", ctx);
        if (it.size != 1) {
          rule_error("'only' espera exactamente un elemento, hay " + std::to_string(it.size));
        }
        Value x = it[0];
        v = std::move(x);
      }
        DISPATCH();
      case OP_APPEND:
      GH_LABEL(OP_APPEND): {
        Value x = POP();
        Value& xs = TOP;
        expect_tuple(xs, "append", ctx);
        size_t len = xs.tuple_size();
        Value out = Value::alloc_array(Tag::Tuple, static_cast<uint32_t>(len + 1));
        for (size_t k = 0; k < len; ++k) out.arr()->items()[k] = xs.tuple_at(k);
        out.arr()->items()[len] = std::move(x);
        xs = std::move(out);
      }
        DISPATCH();
      case OP_CONCAT:
      GH_LABEL(OP_CONCAT): {
        Value b = POP();
        Value& a = TOP;
        expect_tuple(a, "concat", ctx);
        expect_tuple(b, "concat", ctx);
        size_t na = a.tuple_size(), nb = b.tuple_size();
        Value out = Value::alloc_array(Tag::Tuple, static_cast<uint32_t>(na + nb));
        for (size_t k = 0; k < na; ++k) out.arr()->items()[k] = a.tuple_at(k);
        for (size_t k = 0; k < nb; ++k) out.arr()->items()[na + k] = b.tuple_at(k);
        a = std::move(out);
      }
        DISPATCH();
      case OP_RANGE:
      GH_LABEL(OP_RANGE): {
        Value hi_v = POP();
        Value& lo_v = TOP;
        int64_t lo = range_bound(lo_v, "range", ctx);
        int64_t hi = range_bound(hi_v, "range", ctx);
        int64_t count = hi >= lo ? hi - lo + 1 : 0;
        if (count > 100'000'000) rule_error("'range' demasiado grande");
        Value out = Value::alloc_array(Tag::Tuple, static_cast<uint32_t>(count));
        for (int64_t k = 0; k < count; ++k) out.arr()->items()[k] = Value::integer(lo + k);
        lo_v = std::move(out);
      }
        DISPATCH();
      case OP_SLICE:
      GH_LABEL(OP_SLICE): {
        Value hi_v = POP();
        Value lo_v = POP();
        Value& xs = TOP;
        expect_tuple(xs, "slice", ctx);
        int64_t lo = std::max<int64_t>(range_bound(lo_v, "slice", ctx), 0);
        int64_t hi = std::max<int64_t>(range_bound(hi_v, "slice", ctx), 0);
        int64_t len = static_cast<int64_t>(xs.tuple_size());
        lo = std::min(lo, len);
        hi = std::min(hi, len);
        int64_t count = hi > lo ? hi - lo : 0;
        Value out = Value::alloc_array(Tag::Tuple, static_cast<uint32_t>(count));
        for (int64_t k = 0; k < count; ++k) {
          out.arr()->items()[k] = xs.tuple_at(static_cast<size_t>(lo + k));
        }
        xs = std::move(out);
      }
        DISPATCH();
      case OP_REVERSE:
      GH_LABEL(OP_REVERSE): {
        Value& xs = TOP;
        expect_tuple(xs, "reverse", ctx);
        size_t len = xs.tuple_size();
        Value out = Value::alloc_array(Tag::Tuple, static_cast<uint32_t>(len));
        for (size_t k = 0; k < len; ++k) out.arr()->items()[k] = xs.tuple_at(len - 1 - k);
        xs = std::move(out);
      }
        DISPATCH();
      case OP_DISTINCT:
      GH_LABEL(OP_DISTINCT): {
        Value& xs = TOP;
        expect_tuple(xs, "distinct", ctx);
        ValueVec out;
        size_t len = xs.tuple_size();
        for (size_t k = 0; k < len; ++k) {
          Value x = xs.tuple_at(k);
          bool seen = false;
          for (const auto& y : out) {
            if (equals(x, y)) {
              seen = true;
              break;
            }
          }
          if (!seen) out.push_back(std::move(x));
        }
        xs = Value::tuple(std::move(out));
      }
        DISPATCH();
      case OP_UNION:
      GH_LABEL(OP_UNION): {
        Value b = POP();
        Value& a = TOP;
        Value sa = make_set_from(a, "union", ctx);
        Value sb = make_set_from(b, "union", ctx);
        ValueVec items;
        for (uint32_t k = 0; k < sa.arr()->n; ++k) items.push_back(sa.arr()->items()[k]);
        for (uint32_t k = 0; k < sb.arr()->n; ++k) items.push_back(sb.arr()->items()[k]);
        a = Value::set(std::move(items));
      }
        DISPATCH();
      case OP_INTERSECTION:
      GH_LABEL(OP_INTERSECTION): {
        Value b = POP();
        Value& a = TOP;
        Value sa = make_set_from(a, "intersection", ctx);
        ValueVec items;
        if (sa.arr()->n > 0) {
          Items ib = iterate(b, "iteración", ctx);
          for (uint32_t k = 0; k < sa.arr()->n; ++k) {
            if (items_contain(ib, sa.arr()->items()[k])) items.push_back(sa.arr()->items()[k]);
          }
        }
        a = Value::set(std::move(items));
      }
        DISPATCH();
      case OP_DIFFERENCE:
      GH_LABEL(OP_DIFFERENCE): {
        Value b = POP();
        Value& a = TOP;
        Items ia = iterate(a, "difference", ctx);
        ValueVec items;
        if (ia.size > 0) {
          Items ib = iterate(b, "difference", ctx);
          for (size_t k = 0; k < ia.size; ++k) {
            if (!items_contain(ib, ia[k])) items.push_back(ia[k]);
          }
        }
        a = Value::tuple(std::move(items));
      }
        DISPATCH();
      case OP_SUBSETS:
      GH_LABEL(OP_SUBSETS): {
        Value hi = POP();
        Value lo = POP();
        Value& coll = TOP;
        coll = subsets(coll, lo, hi, ctx);
      }
        DISPATCH();

      // --- Comprensiones ---
      case OP_ITER_INIT:
      GH_LABEL(OP_ITER_INIT): {
        uint32_t name = *ip++;
        uint32_t coll_slot = *ip++;
        uint32_t idx_slot = *ip++;
        uint32_t nonempty = *ip++;
        Value coll = POP();
        if (coll.tag == Tag::Tuple || coll.tag == Tag::Set || coll.tag == Tag::Zone ||
            coll.tag == Tag::Map) {
          // Se recorren sus elementos en sitio (los mapas, de dos en dos: sus claves).
          if (nonempty && coll.arr()->n == 0) {
            rule_error(std::string("'") + ITER_OPS[name] + "' sobre una colección vacía");
          }
          slots[coll_slot] = std::move(coll);
        } else {
          const char* op_name = ITER_OPS[name];
          Items it = iterate(coll, op_name, ctx);
          if (nonempty && it.size == 0) {
            rule_error(std::string("'") + op_name + "' sobre una colección vacía");
          }
          slots[coll_slot] = std::move(it.holder);
        }
        slots[idx_slot] = Value::integer(0);
      }
        DISPATCH();
      case OP_ITER_NEXT:
      GH_LABEL(OP_ITER_NEXT): {
        const Value& coll = slots[ip[0]];
        Value& idx = slots[ip[1]];
        uint32_t binder = ip[2];
        uint32_t exit = ip[3];
        ip += 4;
        const ArrayObj* obj = coll.arr();
        bool map = coll.tag == Tag::Map;
        size_t size = map ? obj->n >> 1 : obj->n;
        if (static_cast<size_t>(idx.i) >= size) {
          ip = code + exit;
        } else {
          slots[binder] = obj->items()[map ? idx.i << 1 : idx.i];
          ++idx.i;
        }
      }
        DISPATCH();
      case OP_ITER_FIRST:
      GH_LABEL(OP_ITER_FIRST): {
        uint32_t name = ip[0], coll_slot = ip[1], idx_slot = ip[2], nonempty = ip[3];
        uint32_t binder = ip[4], exit = ip[5], source = ip[6];
        ip += 7;
        Value coll = source == UINT32_MAX ? POP() : slots[source];
        if (coll.tag != Tag::Tuple && coll.tag != Tag::Set && coll.tag != Tag::Zone &&
            coll.tag != Tag::Map) {
          coll = iterate(coll, ITER_OPS[name], ctx).holder;  // casillas (o el error)
        }
        const ArrayObj* obj = coll.arr();
        bool map = coll.tag == Tag::Map;
        size_t size = map ? obj->n >> 1 : obj->n;
        if (nonempty && size == 0) {
          rule_error(std::string("'") + ITER_OPS[name] + "' sobre una colección vacía");
        }
        if (size == 0) {
          ip = code + exit;
        } else {
          slots[binder] = obj->items()[0];
          slots[idx_slot] = Value::integer(1);
          slots[coll_slot] = std::move(coll);
        }
      }
        DISPATCH();

// Avanza el bucle de la comprensión: si hay otro elemento, a la variable y salta al cuerpo.
#define GH_ADVANCE(coll_slot, idx_slot, binder, body)                     \
  do {                                                                     \
    const Value& coll_ = slots[coll_slot];                                 \
    Value& idx_ = slots[idx_slot];                                         \
    const ArrayObj* obj_ = coll_.arr();                                    \
    bool map_ = coll_.tag == Tag::Map;                                     \
    size_t size_ = map_ ? obj_->n >> 1 : obj_->n;                          \
    if (static_cast<size_t>(idx_.i) < size_) {                             \
      slots[binder] = obj_->items()[map_ ? idx_.i << 1 : idx_.i];          \
      ++idx_.i;                                                            \
      ip = code + (body);                                                  \
    }                                                                      \
  } while (0)

      case OP_ALL_LOOP:
      GH_LABEL(OP_ALL_LOOP):
      case OP_ANY_LOOP:
      GH_LABEL(OP_ANY_LOOP): {
        bool all = ip[-1] == OP_ALL_LOOP;
        uint32_t out = ip[0], coll_slot = ip[1], idx_slot = ip[2], binder = ip[3], body = ip[4];
        ip += 5;
        Value& v = sp[-1];
        bool b = v.tag == Tag::Bool ? v.i != 0 : expect_bool(v, all ? "all" : "any", ctx);
        v = Value();
        --sp;
        if (b != all) {
          ip = code + out;  // cortocircuito
        } else {
          GH_ADVANCE(coll_slot, idx_slot, binder, body);
        }
      }
        DISPATCH();
      case OP_COUNT_LOOP:
      GH_LABEL(OP_COUNT_LOOP): {
        Value& acc = slots[ip[0]];
        uint32_t coll_slot = ip[1], idx_slot = ip[2], binder = ip[3], body = ip[4];
        ip += 5;
        Value& v = sp[-1];
        bool b = v.tag == Tag::Bool ? v.i != 0 : expect_bool(v, "count", ctx);
        v = Value();
        --sp;
        if (b) ++acc.i;
        GH_ADVANCE(coll_slot, idx_slot, binder, body);
      }
        DISPATCH();
      case OP_SUM_LOOP:
      GH_LABEL(OP_SUM_LOOP): {
        Value& acc = slots[ip[0]];
        uint32_t coll_slot = ip[1], idx_slot = ip[2], binder = ip[3], body = ip[4];
        ip += 5;
        Value v = POP();
        expect_num(v, "sum", ctx);
        acc = num_add(acc, v);
        GH_ADVANCE(coll_slot, idx_slot, binder, body);
      }
        DISPATCH();
      case OP_PUSH_LOOP:
      GH_LABEL(OP_PUSH_LOOP): {
        uint32_t coll_slot = ip[1], idx_slot = ip[2], binder = ip[3], body = ip[4];
        ip += 5;
        builders_[nbuilders_ - 1].push_back(POP());
        GH_ADVANCE(coll_slot, idx_slot, binder, body);
      }
        DISPATCH();
      case OP_FILTER_LOOP:
      GH_LABEL(OP_FILTER_LOOP): {
        uint32_t coll_slot = ip[1], idx_slot = ip[2], binder = ip[3], body = ip[4];
        ip += 5;
        Value& v = sp[-1];
        bool b = v.tag == Tag::Bool ? v.i != 0 : expect_bool(v, "filter", ctx);
        v = Value();
        --sp;
        if (b) builders_[nbuilders_ - 1].push_back(slots[binder]);
        GH_ADVANCE(coll_slot, idx_slot, binder, body);
      }
        DISPATCH();
#undef GH_ADVANCE
      case OP_ITER_LOOP:
      GH_LABEL(OP_ITER_LOOP): {
        const Value& coll = slots[ip[0]];
        Value& idx = slots[ip[1]];
        uint32_t binder = ip[2];
        uint32_t body = ip[3];
        ip += 4;
        const ArrayObj* obj = coll.arr();
        bool map = coll.tag == Tag::Map;
        size_t size = map ? obj->n >> 1 : obj->n;
        if (static_cast<size_t>(idx.i) < size) {
          slots[binder] = obj->items()[map ? idx.i << 1 : idx.i];
          ++idx.i;
          ip = code + body;
        }
      }
        DISPATCH();
      case OP_ALL_STEP:
      GH_LABEL(OP_ALL_STEP): {
        uint32_t exit = *ip++;
        Value& v = sp[-1];
        bool b = v.tag == Tag::Bool ? v.i != 0 : expect_bool(v, "all", ctx);
        v = Value();
        --sp;
        if (!b) ip = code + exit;
      }
        DISPATCH();
      case OP_ANY_STEP:
      GH_LABEL(OP_ANY_STEP): {
        uint32_t exit = *ip++;
        Value& v = sp[-1];
        bool b = v.tag == Tag::Bool ? v.i != 0 : expect_bool(v, "any", ctx);
        v = Value();
        --sp;
        if (b) ip = code + exit;
      }
        DISPATCH();
      case OP_COUNT_STEP:
      GH_LABEL(OP_COUNT_STEP): {
        Value& acc = slots[*ip++];
        Value v = POP();
        if (expect_bool(v, "count", ctx)) ++acc.i;
      }
        DISPATCH();
      case OP_SUM_STEP:
      GH_LABEL(OP_SUM_STEP): {
        Value& acc = slots[*ip++];
        Value v = POP();
        expect_num(v, "sum", ctx);
        acc = num_add(acc, v);
      }
        DISPATCH();
      case OP_BUILD_BEGIN:
      GH_LABEL(OP_BUILD_BEGIN):
        if (nbuilders_ == builders_.size()) builders_.emplace_back();
        builders_[nbuilders_++].clear();
        DISPATCH();
      case OP_BUILD_PUSH:
      GH_LABEL(OP_BUILD_PUSH):
        builders_[nbuilders_ - 1].push_back(POP());
        DISPATCH();
      case OP_BUILD_LIST:
      GH_LABEL(OP_BUILD_LIST): {
        auto& items = builders_[--nbuilders_];
        PUSH(Value::tuple(std::span<const Value>(items)));
        items.clear();
      }
        DISPATCH();
      case OP_FILTER_STEP:
      GH_LABEL(OP_FILTER_STEP): {
        uint32_t binder = *ip++;
        Value& v = sp[-1];
        bool b = v.tag == Tag::Bool ? v.i != 0 : expect_bool(v, "filter", ctx);
        v = Value();
        --sp;
        if (b) builders_[nbuilders_ - 1].push_back(slots[binder]);
      }
        DISPATCH();
      case OP_FLAT_STEP:
      GH_LABEL(OP_FLAT_STEP): {
        Value v = POP();
        Items it = iterate(v, "flat_map", ctx);
        auto& out = builders_[nbuilders_ - 1];
        for (size_t k = 0; k < it.size; ++k) out.push_back(it[k]);
      }
        DISPATCH();
      case OP_ARGBEST_STEP:
      GH_LABEL(OP_ARGBEST_STEP): {
        int sign = ip[0] ? 1 : -1;
        const char* name = sign > 0 ? "argmax" : "argmin";
        Value& best = slots[ip[1]];
        Value& best_key = slots[ip[2]];
        const Value& item = slots[ip[3]];
        ip += 4;
        Value key = POP();
        if (best_key.is_none() || compare_ir(key, best_key, name, ctx) * sign > 0) {
          best = item;
          best_key = std::move(key);
        }
      }
        DISPATCH();
      case OP_BEST_OF:
      GH_LABEL(OP_BEST_OF): {
        int sign = *ip++ ? 1 : -1;
        const char* name = sign > 0 ? "max_of" : "min_of";
        auto& values = builders_[--nbuilders_];
        Value best = values.at(0);
        for (size_t k = 1; k < values.size(); ++k) {
          if (compare_ir(values[k], best, name, ctx) * sign > 0) best = values[k];
        }
        values.clear();
        PUSH(std::move(best));
      }
        DISPATCH();
      case OP_SORT_PUSH:
      GH_LABEL(OP_SORT_PUSH): {
        auto& out = builders_[nbuilders_ - 1];
        out.push_back(POP());               // clave
        out.push_back(slots[*ip++]);        // elemento
      }
        DISPATCH();
      case OP_SORT_BY:
      GH_LABEL(OP_SORT_BY): {
        auto& pairs = builders_[--nbuilders_];
        size_t count = pairs.size() / 2;
        PoolVec<size_t> order(count);
        for (size_t k = 0; k < count; ++k) order[k] = k;
        std::stable_sort(order.begin(), order.end(), [&](size_t a, size_t b) {
          return compare_ir(pairs[2 * a], pairs[2 * b], "sort_by", ctx) < 0;
        });
        Value out = Value::alloc_array(Tag::Tuple, static_cast<uint32_t>(count));
        for (size_t k = 0; k < count; ++k) out.arr()->items()[k] = pairs[2 * order[k] + 1];
        pairs.clear();
        PUSH(std::move(out));
      }
        DISPATCH();

      // --- Asientos ---
      case OP_NEXT_SEAT:
      GH_LABEL(OP_NEXT_SEAT): {
        Value& s = TOP;
        s = Value::integer((expect_seat(s, n, "next_seat", ctx) + 1) % n);
      }
        DISPATCH();
      case OP_PREV_SEAT:
      GH_LABEL(OP_PREV_SEAT): {
        Value& s = TOP;
        s = Value::integer(floor_mod(expect_seat(s, n, "prev_seat", ctx) - 1, n));
      }
        DISPATCH();
      case OP_OTHER_SEAT:
      GH_LABEL(OP_OTHER_SEAT): {
        Value& s = TOP;
        if (n != 2) rule_error("'other_seat' solo existe en partidas de 2 jugadores");
        s = Value::integer(1 - expect_seat(s, n, "other_seat", ctx));
      }
        DISPATCH();
      case OP_SEATS_FROM:
      GH_LABEL(OP_SEATS_FROM): {
        Value& s = TOP;
        int64_t first = expect_seat(s, n, "seats_from", ctx);
        Value out = Value::alloc_array(Tag::Tuple, static_cast<uint32_t>(n));
        for (int k = 0; k < n; ++k) out.arr()->items()[k] = Value::integer((first + k) % n);
        s = std::move(out);
      }
        DISPATCH();

      // --- Tableros ---
      case OP_CELLS:
      GH_LABEL(OP_CELLS): {
        Value& g = TOP;
        const ArrayObj* grid = expect_grid(g, "cells", ctx);
        uint64_t key = (uint64_t(1) << 62) | (uint64_t(grid->a) << 31) | grid->b;
        auto& cache = ctx.game->grid_cache;
        auto found = cache.find(key);
        if (found == cache.end()) {
          Value out = Value::alloc_array(Tag::Tuple, grid->n);
          for (uint32_t r = 0, k = 0; r < grid->b; ++r) {
            for (uint32_t c = 0; c < grid->a; ++c, ++k) out.arr()->items()[k] = Value::cell(r, c);
          }
          found = cache.emplace(key, std::move(out)).first;
        }
        g = found->second;
      }
        DISPATCH();
      case OP_LINES:
      GH_LABEL(OP_LINES): {
        Value k = POP();
        Value& g = TOP;
        const ArrayObj* grid = expect_grid(g, "lines", ctx);
        int64_t len = range_bound(k, "lines", ctx);
        if (len < 0 || len > 1'000'000) {
          g = grid_lines(grid, len);
          break;
        }
        uint64_t key = (uint64_t(2) << 62) | (uint64_t(grid->a) << 42) | (uint64_t(grid->b) << 21) |
                       static_cast<uint64_t>(len);
        auto& cache = ctx.game->grid_cache;
        auto found = cache.find(key);
        if (found == cache.end()) found = cache.emplace(key, grid_lines(grid, len)).first;
        g = found->second;
      }
        DISPATCH();
      case OP_NEIGHBORS:
      GH_LABEL(OP_NEIGHBORS): {
        Value cell = POP();
        Value& g = TOP;
        const ArrayObj* grid = expect_grid(g, "neighbors", ctx);
        int64_t r, c;
        cell_parts(cell, r, c);
        ValueVec around;
        for (int dr = -1; dr <= 1; ++dr) {
          for (int dc = -1; dc <= 1; ++dc) {
            if (dr == 0 && dc == 0) continue;
            int64_t rr = r + dr, cc = c + dc;
            if (rr >= 0 && rr < grid->b && cc >= 0 && cc < grid->a) {
              around.push_back(Value::cell(rr, cc));
            }
          }
        }
        g = Value::tuple(std::move(around));
      }
        DISPATCH();
      case OP_IN_BOUNDS:
      GH_LABEL(OP_IN_BOUNDS): {
        Value cell = POP();
        Value& g = TOP;
        const ArrayObj* grid = expect_grid(g, "in_bounds", ctx);
        g = Value::boolean(in_bounds(grid, cell));
      }
        DISPATCH();

      // --- Zonas ---
      case OP_SIZE:
      GH_LABEL(OP_SIZE): {
        Value& z = TOP;
        z = Value::integer(expect_zone(z, "size", ctx)->n);
      }
        DISPATCH();
      case OP_ITEMS:
      GH_LABEL(OP_ITEMS): {
        Value& z = TOP;
        const ArrayObj* zone = expect_zone(z, "items", ctx);
        z = Value::tuple(std::span<const Value>(zone->items(), zone->n));
      }
        DISPATCH();
      case OP_TOP:
      GH_LABEL(OP_TOP): {
        Value& z = TOP;
        const ArrayObj* zone = expect_zone(z, "top", ctx);
        if (zone->a == 0) rule_error("'top' no tiene sentido en una bolsa (no tiene orden)");
        if (zone->n == 0) rule_error("'top' sobre una zona vacía");
        z = Value(zone->items()[0]);
      }
        DISPATCH();

      // --- Enumerados ---
      case OP_ORD:
      GH_LABEL(OP_ORD): {
        Value& x = TOP;
        if (x.tag != Tag::Enum) rule_error("'ord' espera un valor de enumerado, recibe " + repr(x, ctx));
        x = Value::integer(x.i);
      }
        DISPATCH();

      // --- Funciones ---
      case OP_CALL:
      GH_LABEL(OP_CALL): {
        uint32_t fn = *ip++;
        uint32_t argc = *ip++;
        Value* args = sp - argc;
        sp_ = sp;
        Value result = call(fn, args, ctx);
        sp = sp_;
        while (sp > args) *--sp = Value();
        PUSH(std::move(result));
      }
        DISPATCH();

      // --- Pagos ---
      case OP_WIN_LOSS:
      GH_LABEL(OP_WIN_LOSS): {
        Value loss = POP();
        Value win = POP();
        Value& w = TOP;
        Value out = Value::alloc_array(Tag::Tuple, static_cast<uint32_t>(n));
        for (int s = 0; s < n; ++s) {
          bool winner = s == expect_seat(w, n, "win_loss", ctx);
          out.arr()->items()[s] = expect_num(winner ? win : loss, "win_loss", ctx);
        }
        w = std::move(out);
      }
        DISPATCH();
      case OP_FILL:
      GH_LABEL(OP_FILL): {
        Value& v = TOP;
        expect_num(v, "fill", ctx);
        Value out = Value::alloc_array(Tag::Tuple, static_cast<uint32_t>(n));
        for (int s = 0; s < n; ++s) out.arr()->items()[s] = v;
        v = std::move(out);
      }
        DISPATCH();

      case OP_VAR_INDEX_LOCAL:
      GH_LABEL(OP_VAR_INDEX_LOCAL): {
        const Value& key = slots[ip[0]];
        const Value& coll = (*ctx.store)[ip[1]];
        ip += 2;
        if (coll.tag == Tag::Grid && key.tag == Tag::Cell) {
          const ArrayObj* g = coll.arr();
          int64_t r = key.cell_row(), c = key.cell_col();
          if (r >= 0 && r < g->b && c >= 0 && c < g->a) {
            PUSH(g->items()[r * g->a + c]);
            DISPATCH();
          }
        } else if (coll.tag == Tag::Tuple && key.tag == Tag::Int && key.i >= 0 &&
                   key.i < coll.arr()->n) {
          PUSH(coll.arr()->items()[key.i]);
          DISPATCH();
        }
        PUSH(index_value(coll, key, ctx));
      }
        DISPATCH();
      case OP_EQ_LOCAL:
      GH_LABEL(OP_EQ_LOCAL):
      case OP_NE_LOCAL:
      GH_LABEL(OP_NE_LOCAL):
      case OP_EQ_CONST:
      GH_LABEL(OP_EQ_CONST):
      case OP_NE_CONST:
      GH_LABEL(OP_NE_CONST): {
        uint32_t op = ip[-1];
        const Value& b = (op == OP_EQ_LOCAL || op == OP_NE_LOCAL) ? slots[*ip] : consts[*ip];
        ++ip;
        Value& a = sp[-1];
        bool same;
        if (a.tag == b.tag && !is_heap_tag(a.tag)) {
          same = a.x == b.x && a.i == b.i;
        } else {
          same = equals(a, b);
        }
        a = Value::boolean(same == (op == OP_EQ_LOCAL || op == OP_EQ_CONST));
      }
        DISPATCH();
      case OP_RETURN:
      GH_LABEL(OP_RETURN): {
        Value result = POP();
        sp_ = sp;
        return result;
      }
    }
  }
  } catch (...) {
    sp_ = sp;
    throw;
  }
#undef POP
#undef PUSH
#undef TOP
#undef GH_LABEL
#undef DISPATCH
}

}  // namespace gh
