// SPDX-License-Identifier: Apache-2.0
// Juegos y estados del motor C++: la misma API y la misma semántica operacional que el motor de
// referencia (`gamehub.engine.state`, docs/wiki/engine.md). Los estados son inmutables y
// comparten estructura con su padre: deshacer una jugada es volver al estado anterior.
#pragma once

#include <functional>
#include <memory>
#include <optional>
#include <string>
#include <utility>
#include <vector>

#include "gamehub/game.hpp"
#include "gamehub/json.hpp"
#include "gamehub/rng.hpp"
#include "gamehub/vm.hpp"

namespace gh {

enum class Status : uint8_t { Chance, Decision, Terminal };
const char* status_name(Status s);

// Los argumentos de una acción: una tupla compartida (copiar una acción no reserva memoria).
// Con un solo argumento (lo más frecuente) se guarda el valor tal cual.
class Args {
 public:
  Args() = default;
  explicit Args(std::span<const Value> items) : n_(static_cast<uint32_t>(items.size())) {
    if (n_ == 1) {
      v_ = items[0];
    } else if (n_ > 1) {
      v_ = Value::tuple(items);
    }
  }
  size_t size() const { return n_; }
  bool empty() const { return n_ == 0; }
  const Value* data() const {
    if (n_ == 0) return nullptr;
    return n_ == 1 ? &v_ : v_.arr()->items();
  }
  const Value& operator[](size_t k) const { return data()[k]; }
  const Value& at(size_t k) const {
    if (k >= size()) throw std::out_of_range("argumento inexistente");
    return (*this)[k];
  }

 private:
  Value v_;
  uint32_t n_ = 0;
};

struct Action {
  const ActionDef* def = nullptr;  // nullptr = `pass` (ventanas)
  Args args;                       // en el orden de los parámetros

  bool is_pass() const { return def == nullptr; }
  const std::string& name(const GameDef& g) const {
    return def == nullptr ? g.action_names[g.pass_id] : def->name;
  }
  Json to_json(const GameDef& g) const;  // {"name": …, "args": {…}}
  bool operator==(const Action& o) const;
  uint64_t hash() const;
};

struct Pending {
  PoolVec<int> order;  // asientos convocados
  PoolVec<std::pair<int, Action>> submitted;
  bool responded(int seat) const {
    for (const auto& [s, a] : submitted) {
      if (s == seat) return true;
    }
    return false;
  }
};

struct Step {
  enum class Kind : uint8_t { Start, Action, Chance, Edit } kind = Kind::Start;
  int seat = -1;
  Action action;
  Outcome outcome;
  std::vector<Event> events;
};

// Opciones de una transición: las búsquedas no necesitan eventos ni historial.
struct ApplyOptions {
  bool events = true;    // registrar los eventos (vistas por asiento) del paso
  bool history = true;   // enlazar con el estado padre (historial, replays, estados de información)
  bool validate = true;  // comprobar la legalidad (desactivar solo con acciones de legal_actions)
};

class Game;

// Lo que comparten todos los estados de una partida.
struct Match {
  int n = 0;
  ValueVec params;  // `num_players` y los declarados, en orden
  Value seats;                // tuple(range(n))
  // Funciones que solo dependen de las opciones y del número de jugadores (una caché; los
  // estados de una partida se usan desde un solo hilo).
  mutable MemoTable memo;
};

struct StateNode {
  std::shared_ptr<const GameDef> game;
  int n = 0;
  std::shared_ptr<const Match> match;
  ValueVec store;
  int node = -1;  // -1 = antes de la preparación (punto de azar)
  std::shared_ptr<const Pending> pending;
  bool terminal = false;
  ValueVec payoffs;
  std::shared_ptr<const StateNode> parent;
  Step step;
  int depth = 0;
  const std::vector<int>* path = nullptr;  // fases activas y el nodo (en el GameDef)
  mutable MemoTable memo;  // funciones "state" con este estado (una caché)
};

class State {
 public:
  State() = default;
  explicit State(std::shared_ptr<const StateNode> node) : s_(std::move(node)) {}

  const GameDef& game() const { return *s_->game; }
  const StateNode& data() const { return *s_; }
  const std::shared_ptr<const StateNode>& ptr() const { return s_; }
  int num_players() const { return s_->n; }
  int node() const { return s_->node; }
  int depth() const { return s_->depth; }

  Status status() const;
  bool is_terminal() const { return s_->terminal; }
  std::vector<int> active_seats() const;
  bool is_active(int seat) const;
  int first_active() const;  // -1 si no hay
  const ValueVec& payoffs() const { return s_->payoffs; }
  const Value& value(const std::string& var) const;

  // Acciones legales en orden (declaración, parámetros, dominio; `pass` al final en ventanas).
  std::vector<Action> legal_actions(int seat) const;
  // Recorre las acciones legales; `visit` devuelve false para parar.
  void for_each_legal(int seat, const std::function<bool(const Action&)>& visit) const;
  size_t count_legal(int seat) const;
  std::optional<std::vector<int>> ranking() const;
  // Construcción progresiva: nombres (name vacío) o valores del siguiente parámetro.
  Json options(int seat, const std::string* name, const Json* args) const;
  std::optional<std::string> illegal_reason(int seat, const Action& action) const;
  Action decode_action(const Json& data) const;

  State apply_action(int seat, const Action& action, const ApplyOptions& opt = {}) const;
  std::vector<std::pair<Outcome, Rational>> chance_outcomes(size_t limit = 100'000) const;
  Outcome sample_chance(Pcg32& rng) const;
  State apply_chance(const Outcome& outcome, const ApplyOptions& opt = {}) const;
  // apply_chance(sample_chance(rng)) en una sola ejecución del punto de azar.
  State sample_and_apply(Pcg32& rng, const ApplyOptions& opt = {}) const;
  Rational outcome_probability(const Outcome& outcome) const;
  // El siguiente sorteo de un punto de azar tras `prefix`: (n, probabilidades; vacío = uniforme),
  // o nullopt si `prefix` ya es un resultado completo. Para presentar el azar sorteo a sorteo.
  std::optional<std::pair<int64_t, std::vector<Rational>>> next_draw(const Outcome& prefix) const;
  // Una copia tras ejecutar sentencias de la IR fuera del flujo (los `set` de los tests).
  State edited(const Json& stmts) const;
  // El valor de una expresión de la IR con vista omnisciente.
  Value evaluate(const Json& expr) const;

  Json view(int seat) const;    // NO_SEAT = omnisciente, PUBLIC = espectador
  Json events(int seat) const;  // eventos del último paso que ve el asiento
  Json snapshot() const;
  std::string snapshot_text() const;  // JSON canónico de la instantánea
  std::string digest() const;
  std::string information_state(int seat) const;  // SHA-256 con recuerdo perfecto
  // SHA-256 de lo que observa el asiento en este estado: {"view": …, "events": …} canónico.
  std::string observation_digest(int seat) const;
  // Hash estructural del estado (Zobrist automático): nodo, envíos, pagos y almacén.
  uint64_t hash() const;
  const Step& step() const { return s_->step; }
  std::vector<State> path() const;  // del estado inicial a este

 private:
  std::shared_ptr<const StateNode> s_;
};

class Game {
 public:
  explicit Game(const Json& ir) : def_(std::make_shared<const GameDef>(ir)) {}
  static Game from_text(std::string_view ir_json) { return Game(Json::parse(ir_json)); }

  const GameDef& def() const { return *def_; }
  const std::shared_ptr<const GameDef>& def_ptr() const { return def_; }
  State new_state(int num_players, const Json& params = Json::object(),
                  const ApplyOptions& opt = {}) const;
  // Acción del nodo dado desde JSON, sin estado (los clientes solo conocen su vista).
  Action decode_action(int node, const Json& data) const;

 private:
  std::shared_ptr<const GameDef> def_;
};

// Acción del nodo dado desde JSON (sin comprobar la legalidad).
Action decode_action(const GameDef& g, int node, const Json& data);

// Cobertura: las transiciones que se tomen en este hilo se añaden a `trace` (nullptr = ninguna).
void set_transition_trace(std::vector<const TransitionDef*>* trace);

// El contexto de una consulta sobre el estado (sin escribir en él): heurísticas, herramientas.
Ctx state_query_ctx(const State& s);

// Utilidades compartidas con los algoritmos.
std::vector<int> competition_ranking(const ValueVec& scores);
Json payoffs_json(const GameDef& g, const ValueVec& payoffs);

}  // namespace gh
