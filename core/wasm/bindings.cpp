// SPDX-License-Identifier: Apache-2.0
// El núcleo C++ en el navegador (Emscripten + embind): juegos y sesiones de partida que hablan
// JSON. Una `Session` guarda el estado actual y su historia (para deshacer); las excepciones del
// motor no cruzan a JavaScript: los métodos que pueden fallar devuelven
// `{"ok": true, …}` o `{"ok": false, "error": "…", "kind": "rule"|"illegal"|…}`.
#include <emscripten/bind.h>
#include <emscripten/em_js.h>

#include <algorithm>
#include <cstdio>
#include <optional>
#include <string>
#include <vector>

#include "gamehub/errors.hpp"
#include "gamehub/natives.hpp"
#include "gamehub/playout.hpp"
#include "gamehub/search.hpp"
#include "gamehub/state.hpp"

using namespace gh;

namespace {

constexpr int OMNISCIENT = -2;  // en JavaScript: la vista sin ocultar nada

int seat_arg(int seat) { return seat == OMNISCIENT ? NO_SEAT : seat; }

std::string failure(const char* kind, const std::string& message) {
  return Json(JsonObject{{"ok", Json(false)}, {"kind", Json(kind)}, {"error", Json(message)}})
      .dump();
}

template <class F>
std::string guarded(F&& body) {
  try {
    return body();
  } catch (const RuleError& e) {
    return failure("rule", e.what());
  } catch (const IllegalAction& e) {
    return failure("illegal", e.what());
  } catch (const InvalidParams& e) {
    return failure("params", e.what());
  } catch (const NotEnumerable& e) {
    return failure("not_enumerable", e.what());
  } catch (const std::exception& e) {
    return failure("error", e.what());
  }
}

std::string ok(JsonObject fields = {}) {
  fields.insert(fields.begin(), {"ok", Json(true)});
  return Json(std::move(fields)).dump();
}

std::string hex64(uint64_t x) {
  char buf[17];
  std::snprintf(buf, sizeof buf, "%016llx", static_cast<unsigned long long>(x));
  return buf;
}

Json outcome_json(const Outcome& o) {
  JsonArray out;
  for (int64_t d : o) out.push_back(Json(d));
  return Json(std::move(out));
}

// Plugins nativos: los instancia JavaScript (`Module.ghNatives`, ver @gamehub/engine) y el núcleo
// los llama con las palabras del ABI gamehub-native/1 copiadas entre las dos memorias.
EM_JS(int, gh_js_native_find, (const char* id), {
  const natives = Module["ghNatives"];
  return natives ? natives.find(UTF8ToString(id)) : -1;
});

EM_JS(int, gh_js_native_call, (int handle, const int32_t* input, int len, int32_t* output,
                               int cap), {
  const words = HEAP32.subarray(input >> 2, (input >> 2) + len);
  const result = Module["ghNatives"].call(handle, words);
  if (typeof result === "number") return result;
  if (result.length > cap) return -1;
  HEAP32.set(result, output >> 2);
  return result.length;
});

class JsNativeHost : public NativeHost {
 public:
  int find(const std::string& native_id) override { return gh_js_native_find(native_id.c_str()); }
  int call(int handle, const int32_t* in, int len, int32_t* out, int cap) override {
    return gh_js_native_call(handle, in, len, out, cap);
  }
};

JsNativeHost js_host;

}  // namespace

class JsGame {
 public:
  // `natives`: usar los plugins nativos que haya registrado JavaScript (si no, la referencia).
  // Si la IR no es válida, `error()` lo dice y el juego no se puede usar.
  JsGame(const std::string& ir, bool natives) {
    set_native_host(natives ? &js_host : nullptr);
    std::string result = guarded([&] {
      game_.emplace(Game::from_text(ir));
      return ok();
    });
    set_native_host(nullptr);
    if (!game_) error_ = result;
  }
  std::string error() const { return error_; }
  std::string id() const { return def().id; }
  std::string title() const { return def().title; }
  std::string rulesHash() const { return def().rules_hash; }
  int minPlayers() const { return def().min_players; }
  int maxPlayers() const { return def().max_players; }
  // ¿Usa algún plugin nativo?
  bool usesNatives() const {
    for (const auto& f : def().functions) {
      if (f.plugin.handle >= 0) return true;
    }
    return false;
  }
  const Game& game() const { return *game_; }

  // Partidas aleatorias (las mismas que `gamehub fuzz`): {games, completed, steps, fingerprint…}.
  std::string playouts(int n, const std::string& params, double seed, int games, int max_steps) {
    return guarded([&] {
      PlayoutReport r = random_playouts(*game_, n, Json::parse(params),
                                        static_cast<uint64_t>(seed), static_cast<uint64_t>(games),
                                        max_steps);
      JsonArray errors;
      for (const auto& [s, m] : r.errors) {
        errors.push_back(Json(JsonArray{Json(int64_t(s)), Json(m)}));
      }
      return ok({{"games", Json(int64_t(r.games))},
                 {"completed", Json(int64_t(r.completed))},
                 {"truncated", Json(int64_t(r.truncated))},
                 {"steps", Json(int64_t(r.steps))},
                 {"errors", Json(std::move(errors))},
                 {"fingerprint", Json(hex64(r.fingerprint))}});
    });
  }

  // Las partidas al azar del Studio con su cobertura (como `gamehub.studio.sim.playouts`): las
  // sumas de pagos como racionales exactos ("p/q") y las longitudes como mínimo, máximo, suma y
  // número, para que JavaScript calcule las medias igual que Python.
  std::string studioPlayouts(int n, const std::string& params, double seed, int games,
                             int max_steps, double time_limit) {
    return guarded([&] {
      CoverageReport r = coverage_playouts(*game_, n, Json::parse(params),
                                           static_cast<uint64_t>(seed),
                                           static_cast<uint64_t>(games), max_steps, time_limit);
      JsonArray errors;
      for (const auto& [g, m] : r.errors) {
        errors.push_back(Json(JsonObject{
            {"game", Json(int64_t(g))}, {"message", Json(m)}, {"node", Json()}}));
      }
      JsonArray totals, wins;
      for (const auto& t : r.totals) totals.push_back(Json(t.str()));
      for (uint64_t w : r.wins) wins.push_back(Json(int64_t(w)));
      JsonObject lengths{{"count", Json(int64_t(r.lengths.size()))}};
      if (!r.lengths.empty()) {
        auto [lo, hi] = std::minmax_element(r.lengths.begin(), r.lengths.end());
        uint64_t sum = 0;
        for (uint64_t x : r.lengths) sum += x;
        lengths.push_back({"min", Json(int64_t(*lo))});
        lengths.push_back({"max", Json(int64_t(*hi))});
        lengths.push_back({"sum", Json(int64_t(sum))});
      }
      auto counts = [](const std::map<std::string, uint64_t>& m) {
        JsonObject out;
        for (const auto& [k, v] : m) out.push_back({k, Json(int64_t(v))});
        return Json(std::move(out));
      };
      return ok({{"games", Json(int64_t(r.games))},
                 {"finished", Json(int64_t(r.finished))},
                 {"truncated", Json(int64_t(r.truncated))},
                 {"errors", Json(std::move(errors))},
                 {"lengths", Json(std::move(lengths))},
                 {"totals", Json(std::move(totals))},
                 {"wins", Json(std::move(wins))},
                 {"draws", Json(int64_t(r.draws))},
                 {"coverage", Json(JsonObject{{"nodes", counts(r.nodes)},
                                              {"actions", counts(r.actions)},
                                              {"transitions", counts(r.transitions)}})}});
    });
  }

 private:
  const GameDef& def() const { return game_->def(); }
  std::optional<Game> game_;
  std::string error_;
};

class JsSession {
 public:
  JsSession(const JsGame& game, int players, const std::string& params, double seed)
      : game_(game.game()), chance_(static_cast<uint64_t>(seed), STREAM_CHANCE) {
    std::string result = guarded([&] {
      states_.push_back(game_.new_state(players, Json::parse(params)));
      return ok();
    });
    error_ = Json::parse(result).find("error") ? result : "";
    for (int s = 0; s < players; ++s) {
      uint64_t stream = STREAM_AGENT_BASE + static_cast<uint64_t>(s);
      agents_.emplace_back(static_cast<uint64_t>(seed), stream);
    }
  }

  // "" si se creó bien; si no, el error en JSON.
  std::string error() const { return error_; }
  const State& current() const { return states_.back(); }

  std::string status() const { return status_name(current().status()); }
  std::string node() const {
    return current().node() < 0 ? "" : current().game().node(current().node()).id;
  }
  int depth() const { return static_cast<int>(states_.size()) - 1; }
  std::string activeSeats() const {
    JsonArray out;
    for (int s : current().active_seats()) out.push_back(Json(int64_t(s)));
    return Json(std::move(out)).dump();
  }
  std::string view(int seat) const { return current().view(seat_arg(seat)).dump(); }
  // Los eventos de los pasos `first`… (0 = la preparación) hasta el actual, como los ve `seat`.
  std::string eventsFrom(int first, int seat) const {
    JsonArray out;
    for (size_t i = static_cast<size_t>(std::max(first, 0)); i < states_.size(); ++i) {
      Json events = states_[i].events(seat_arg(seat));
      for (auto& e : events.as_array()) out.push_back(e);
    }
    return Json(std::move(out)).dump();
  }
  std::string snapshot() const { return current().snapshot_text(); }
  std::string digest() const { return current().digest(); }
  std::string payoffs() const {
    if (!current().is_terminal()) return "null";
    return payoffs_json(current().game(), current().payoffs()).dump();
  }
  std::string ranking() const {
    return guarded([&] {
      auto r = current().ranking();
      if (!r) return std::string("null");
      JsonArray out;
      for (int x : *r) out.push_back(Json(int64_t(x)));
      return Json(std::move(out)).dump();
    });
  }

  // Las acciones legales de un asiento, hasta `limit` (más allá: {"truncated": true}).
  std::string legal(int seat, int limit) const {
    return guarded([&] {
      JsonArray actions;
      bool truncated = false;
      current().for_each_legal(seat, [&](const Action& a) {
        if (limit > 0 && static_cast<int>(actions.size()) >= limit) {
          truncated = true;
          return false;
        }
        actions.push_back(a.to_json(current().game()));
        return true;
      });
      return ok({{"actions", Json(std::move(actions))}, {"truncated", Json(truncated)}});
    });
  }

  std::string options(int seat, const std::string& name, const std::string& args) const {
    return guarded([&] {
      Json given = Json::parse(args);
      const std::string* n = name.empty() ? nullptr : &name;
      return ok({{"options", current().options(seat, n, &given)}});
    });
  }

  std::string act(int seat, const std::string& action) {
    return guarded([&] {
      Action a = current().decode_action(Json::parse(action));
      State next = current().apply_action(seat, a);
      states_.push_back(next);
      return ok();
    });
  }

  // Sortea el punto de azar con el generador de la sesión y lo aplica.
  std::string chance() {
    return guarded([&] {
      Outcome o = current().sample_chance(chance_);
      states_.push_back(current().apply_chance(o));
      return ok({{"outcome", outcome_json(o)}});
    });
  }

  std::string applyChance(const std::string& outcome) {
    return guarded([&] {
      Outcome o;
      Json digits = Json::parse(outcome);
      for (const auto& d : digits.as_array()) o.push_back(d.as_int());
      states_.push_back(current().apply_chance(o));
      return ok();
    });
  }

  std::string chanceOutcomes(int limit) const {
    return guarded([&] {
      JsonArray out;
      for (const auto& [o, p] : current().chance_outcomes(static_cast<size_t>(limit))) {
        out.push_back(Json(JsonArray{outcome_json(o), Json(p.str())}));
      }
      return ok({{"outcomes", Json(std::move(out))}});
    });
  }

  bool undo() {
    if (states_.size() <= 1) return false;
    states_.pop_back();
    return true;
  }

  // La jugada de un bot: "random" (uniforme con el generador del asiento), "first" (la primera
  // legal) o "mcts" (UCT con `simulations` partidas aleatorias y, si `max_seconds` > 0, como
  // mucho ese tiempo).
  std::string botAction(int seat, const std::string& kind, int simulations, double max_seconds) {
    return guarded([&] {
      std::vector<Action> legal = current().legal_actions(seat);
      if (legal.empty()) throw IllegalAction("el asiento no tiene acciones legales");
      if (kind == "mcts" && current().first_active() == seat && legal.size() > 1) {
        MctsResult r = mcts(current(), static_cast<uint64_t>(simulations), 1.4,
                            agents_[static_cast<size_t>(seat)].next_u32(), 10'000, max_seconds);
        return ok({{"action", r.actions[r.best].to_json(current().game())}});
      }
      if (kind == "first") return ok({{"action", legal.front().to_json(current().game())}});
      const Action& a = legal[agents_[static_cast<size_t>(seat)].below(legal.size())];
      return ok({{"action", a.to_json(current().game())}});
    });
  }

 private:
  const Game& game_;
  std::vector<State> states_;
  Pcg32 chance_;
  std::vector<Pcg32> agents_;
  std::string error_;
};

EMSCRIPTEN_BINDINGS(gamehub_core) {
  emscripten::class_<JsGame>("Game")
      .constructor<std::string, bool>()
      .function("error", &JsGame::error)
      .function("usesNatives", &JsGame::usesNatives)
      .function("id", &JsGame::id)
      .function("title", &JsGame::title)
      .function("rulesHash", &JsGame::rulesHash)
      .function("minPlayers", &JsGame::minPlayers)
      .function("maxPlayers", &JsGame::maxPlayers)
      .function("playouts", &JsGame::playouts)
      .function("studioPlayouts", &JsGame::studioPlayouts);
  emscripten::class_<JsSession>("Session")
      .constructor<const JsGame&, int, std::string, double>()
      .function("error", &JsSession::error)
      .function("status", &JsSession::status)
      .function("node", &JsSession::node)
      .function("depth", &JsSession::depth)
      .function("activeSeats", &JsSession::activeSeats)
      .function("view", &JsSession::view)
      .function("eventsFrom", &JsSession::eventsFrom)
      .function("snapshot", &JsSession::snapshot)
      .function("digest", &JsSession::digest)
      .function("payoffs", &JsSession::payoffs)
      .function("ranking", &JsSession::ranking)
      .function("legal", &JsSession::legal)
      .function("options", &JsSession::options)
      .function("act", &JsSession::act)
      .function("chance", &JsSession::chance)
      .function("applyChance", &JsSession::applyChance)
      .function("chanceOutcomes", &JsSession::chanceOutcomes)
      .function("undo", &JsSession::undo)
      .function("botAction", &JsSession::botAction);
  emscripten::constant("OMNISCIENT", OMNISCIENT);
  emscripten::constant("PUBLIC", PUBLIC);
}
