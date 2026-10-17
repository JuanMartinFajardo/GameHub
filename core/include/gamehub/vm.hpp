// SPDX-License-Identifier: Apache-2.0
// La máquina virtual: contexto de evaluación, marcos, fuentes de azar, eventos y el intérprete
// del código de bytes.
#pragma once

#include <cstdint>
#include <memory>
#include <optional>
#include <string>
#include <vector>

#include "gamehub/bytecode.hpp"
#include "gamehub/game.hpp"
#include "gamehub/json.hpp"
#include "gamehub/rng.hpp"

namespace gh {

// Observador público (un espectador, sin asiento) y asiento de contexto sin definir.
constexpr int32_t PUBLIC = -1;
constexpr int32_t NO_SEAT = INT32_MIN;

// --- Azar --------------------------------------------------------------------------------------

using Outcome = PoolVec<int64_t>;

class Draws {
 public:
  virtual ~Draws() = default;
  virtual int64_t uniform(int64_t n) = 0;
  // Probabilidades exactas (ya validadas: no negativas, suman 1).
  virtual int64_t weighted(const std::vector<Rational>& probs) = 0;
};

// Sorteos desde un RNG, registrando la secuencia (el resultado del punto de azar).
class RngDraws : public Draws {
 public:
  explicit RngDraws(Pcg32& rng) : rng_(rng) {}
  int64_t uniform(int64_t n) override;
  int64_t weighted(const std::vector<Rational>& probs) override;
  Outcome taken;

 private:
  Pcg32& rng_;
};

// Reproduce una secuencia fija; si se acaba, lanza `NeedDraw` (para enumerar los resultados).
struct NeedDraw {
  int64_t n;
  std::vector<Rational> probs;  // vacío = uniforme
};

class ScriptedDraws : public Draws {
 public:
  explicit ScriptedDraws(const Outcome& draws) : draws_(draws) {}
  int64_t uniform(int64_t n) override;
  int64_t weighted(const std::vector<Rational>& probs) override;
  bool finished() const { return pos_ == draws_.size(); }
  Rational probability = Rational::integer(1);
  bool track_probability = false;

 private:
  int64_t next(int64_t n);
  const Outcome& draws_;
  size_t pos_ = 0;
};

// --- Eventos -----------------------------------------------------------------------------------

using JsonPtr = std::shared_ptr<const Json>;

// `full` es la versión omnisciente; `seen[s]` lo que ve el asiento s y `pub` un espectador
// (nullptr = no lo ve).
struct Event {
  JsonPtr full;
  std::vector<JsonPtr> seen;
  JsonPtr pub;

  const Json* for_seat(int seat) const;  // NO_SEAT = omnisciente, PUBLIC = espectador
  static Event shared(Json payload, int n);
};

// --- Memo --------------------------------------------------------------------------------------

// Resultados de funciones de la IR por (función, argumentos). Es una caché: no cambia ningún
// resultado.
class MemoTable {
 public:
  const Value* find(uint32_t fn, const Value* args, uint32_t argc, uint64_t hash) const;
  void insert(uint32_t fn, const Value* args, uint32_t argc, uint64_t hash, const Value& result);
  // Vaciarla es O(1): las entradas de generaciones anteriores cuentan como libres.
  void clear() {
    if (count_ == 0) return;
    ++generation_;
    count_ = 0;
  }
  size_t size() const { return count_; }
  static uint64_t key_hash(uint32_t fn, const Value* args, uint32_t argc);

 private:
  static constexpr uint32_t INLINE_ARGS = 3;
  struct Entry {
    uint64_t hash = 0;
    uint32_t generation = 0;  // 0 = nunca usada
    uint32_t fn = 0;
    uint32_t argc = 0;
    Value args[INLINE_ARGS];
    ValueVec more;  // los argumentos a partir del cuarto
    Value result;
    const Value& arg(uint32_t k) const { return k < INLINE_ARGS ? args[k] : more[k - INLINE_ARGS]; }
  };
  bool live(const Entry& e) const { return e.generation == generation_; }
  void grow();
  PoolVec<Entry> table_;
  size_t count_ = 0;
  uint32_t generation_ = 1;
};

// --- Contexto ----------------------------------------------------------------------------------

// Lo compartido durante una evaluación (como `Ctx` en Python).
class Vm;
Vm& vm();

struct Ctx {
  Vm* vm_ = nullptr;  // la VM del hilo (se busca una vez: el acceso a thread_local cuesta)
  const GameDef* game = nullptr;
  ValueVec* store = nullptr;  // las transacciones lo modifican en sitio
  const ValueVec* params = nullptr;
  int n = 0;
  const std::vector<int>* path = nullptr;  // nodo activo y sus fases
  Draws* draws = nullptr;                  // solo en los puntos de azar
  std::vector<Event>* events = nullptr;    // nullptr = no se registran
  MemoTable* memo = nullptr;               // memo "state" (nullptr = desactivado)
  MemoTable* match_memo = nullptr;         // memo "match": la partida (nullptr = desactivado)
  Value seats;                             // tuple(range(n)), calculada una vez

  bool recording() const { return events != nullptr; }
  Vm& machine() {
    if (vm_ == nullptr) vm_ = &vm();
    return *vm_;
  }
};

// Ámbito de una evaluación: las ranuras y los asientos de contexto.
struct Frame {
  Value* slots = nullptr;
  int32_t actor = NO_SEAT;
  int32_t viewer = NO_SEAT;
  int32_t owner = NO_SEAT;
  int8_t face_up = -1;  // -1 = sin definir
};

// --- VM ----------------------------------------------------------------------------------------

class Vm {
 public:
  Vm();
  ~Vm();

  // Evalúa una expresión en el marco dado.
  Value eval(const Chunk& chunk, Ctx& ctx, Frame& frame);
  // Llama a una función de la IR (con su memo).
  Value call(uint32_t fn, const Value* args, Ctx& ctx);

  // Ranuras para un marco nuevo (todas a None) y su liberación (orden LIFO).
  Value* push_slots(uint32_t n);
  void pop_slots(uint32_t n);

 private:
  Value run(const Chunk& chunk, Ctx& ctx, Frame& frame);

  std::unique_ptr<Value[]> stack_;
  Value* stack_end_;
  Value* sp_;
  std::unique_ptr<Value[]> slots_;
  Value* slots_end_;
  Value* slot_top_;
  std::vector<ValueVec> builders_;
  size_t nbuilders_ = 0;
};

// Un marco con sus ranuras reservadas mientras vive el objeto.
class ScopedFrame {
 public:
  ScopedFrame(Vm& machine, uint32_t slots) : vm_(machine), n_(slots) {
    frame.slots = vm_.push_slots(slots);
  }
  explicit ScopedFrame(uint32_t slots) : ScopedFrame(vm(), slots) {}
  ~ScopedFrame() { vm_.pop_slots(n_); }
  ScopedFrame(const ScopedFrame&) = delete;
  ScopedFrame& operator=(const ScopedFrame&) = delete;
  Frame frame;

 private:
  Vm& vm_;
  uint32_t n_;
};

// Evalúa una expresión independiente (con su propio marco).
Value eval_expr(const Expr& e, Ctx& ctx, int32_t actor = NO_SEAT, const Value* args = nullptr,
                uint32_t argc = 0);
// Ejecuta un bloque independiente (con su propio marco).
void run_code(const Code& c, Ctx& ctx, int32_t actor = NO_SEAT, const Value* args = nullptr,
              uint32_t argc = 0);

// --- Utilidades de los operadores (también las usan las sentencias y el estado) -----------------

[[noreturn]] void rule_error(const std::string& message);
bool expect_bool(const Value& v, const char* op, const Ctx& ctx);
const Value& expect_num(const Value& v, const char* op, const Ctx& ctx);
int64_t expect_seat(const Value& v, int n, const char* op, const Ctx& ctx);
// Elementos de una colección en orden (listas tal cual, conjuntos/bolsas/mapas en orden
// canónico, zonas de arriba abajo): vista sin copiar.
struct Items {
  const Value* data = nullptr;
  size_t size = 0;
  size_t stride = 1;
  Value holder;  // mantiene vivo el objeto de `data` (una casilla se materializa como tupla)
  const Value& operator[](size_t k) const { return data[k * stride]; }
};
Items iterate(const Value& coll, const char* op, const Ctx& ctx);
Value index_value(const Value& coll, const Value& key, const Ctx& ctx);
int compare_ir(const Value& a, const Value& b, const char* op, const Ctx& ctx);

}  // namespace gh
