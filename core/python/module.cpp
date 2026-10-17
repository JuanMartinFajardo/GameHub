// SPDX-License-Identifier: Apache-2.0
// Módulo de Python `gamehub_core` (nanobind): el motor C++ y sus algoritmos. La API que imita la
// del motor de referencia (`Game`, `State` con objetos de Python) está en
// `gamehub.engine.core`; este módulo habla en JSON (dict, list, int, str, bool, None).
#include <nanobind/nanobind.h>
#include <nanobind/stl/optional.h>
#include <nanobind/stl/pair.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/tuple.h>
#include <nanobind/stl/vector.h>

#include "gamehub/action_space.hpp"
#include "gamehub/cfr.hpp"
#include "gamehub/errors.hpp"
#include "gamehub/hashing.hpp"
#include "gamehub/playout.hpp"
#include "gamehub/search.hpp"
#include "gamehub/sha256.hpp"
#include "gamehub/state.hpp"

namespace nb = nanobind;
using namespace gh;

namespace {

// --- JSON ↔ Python -----------------------------------------------------------------------------

nb::object to_py(const Json& j) {
  switch (j.kind()) {
    case Json::Kind::Null:
      return nb::none();
    case Json::Kind::Bool:
      return nb::bool_(j.as_bool());
    case Json::Kind::Int:
      return nb::int_(j.as_int());
    case Json::Kind::String:
      return nb::str(j.as_string().c_str(), j.as_string().size());
    case Json::Kind::Array: {
      nb::list out;
      for (const auto& x : j.as_array()) out.append(to_py(x));
      return out;
    }
    case Json::Kind::Object: {
      nb::dict out;
      for (const auto& [k, v] : j.as_object()) out[nb::str(k.c_str(), k.size())] = to_py(v);
      return out;
    }
  }
  return nb::none();
}

Json from_py(nb::handle h) {
  if (h.is_none()) return Json(nullptr);
  if (nb::isinstance<nb::bool_>(h)) return Json(nb::cast<bool>(h));
  if (nb::isinstance<nb::int_>(h)) return Json(nb::cast<int64_t>(h));
  if (nb::isinstance<nb::str>(h)) return Json(nb::cast<std::string>(h));
  if (nb::isinstance<nb::dict>(h)) {
    JsonObject out;
    for (auto [k, v] : nb::borrow<nb::dict>(h)) out.emplace_back(nb::cast<std::string>(k), from_py(v));
    return Json(std::move(out));
  }
  if (nb::isinstance<nb::list>(h) || nb::isinstance<nb::tuple>(h)) {
    JsonArray out;
    for (auto x : h) out.push_back(from_py(x));
    return Json(std::move(out));
  }
  throw nb::type_error("valor no convertible a JSON");
}

int seat_arg(const nb::object& seat) {
  if (seat.is_none()) return NO_SEAT;
  return nb::cast<int>(seat);
}

nb::object outcome_py(const Outcome& o) {
  nb::list items;
  for (int64_t d : o) items.append(nb::int_(d));
  return nb::tuple(items);
}

Outcome outcome_from(const nb::handle& h) {
  Outcome o;
  for (auto x : h) o.push_back(nb::cast<int64_t>(x));
  return o;
}

nb::tuple rational_py(const Rational& r) { return nb::make_tuple(r.num, r.den); }

// Los errores del motor como los de `gamehub.engine.errors` (si el paquete está disponible).
void translate(const std::exception_ptr& p, void*) {
  auto raise = [](const char* name, const char* message) {
    try {
      nb::object errors = nb::module_::import_("gamehub.engine.errors");
      nb::object cls = errors.attr(name);
      PyErr_SetObject(cls.ptr(), nb::str(message).ptr());
    } catch (...) {
      PyErr_SetString(PyExc_RuntimeError, message);
    }
  };
  try {
    std::rethrow_exception(p);
  } catch (const RuleError& e) {
    raise("RuleError", e.what());
  } catch (const IllegalAction& e) {
    raise("IllegalAction", e.what());
  } catch (const InvalidParams& e) {
    raise("InvalidParams", e.what());
  } catch (const NotEnumerable& e) {
    raise("NotEnumerable", e.what());
  } catch (const EngineError& e) {
    raise("EngineError", e.what());
  }
}

ApplyOptions options(bool validate, bool events, bool history) {
  ApplyOptions opt;
  opt.validate = validate;
  opt.events = events;
  opt.history = history;
  return opt;
}

}  // namespace

NB_MODULE(gamehub_core, m) {
  m.doc() = "GameHub: el núcleo C++ (VM de la GameIR y algoritmos).";
  // Los juegos envueltos para OpenSpiel quedan registrados hasta el final del proceso.
  nb::set_leak_warnings(false);
  nb::register_exception_translator(translate);
  m.attr("PUBLIC") = PUBLIC;

  m.def("sha256", [](const std::string& data) { return Sha256::hex(data); });
  m.def("canonical_json", [](nb::handle value) { return from_py(value).dump(); });
  m.def("rules_hash", [](const std::string& ir) { return rules_hash(Json::parse(ir)); });
  m.def("strip_cosmetic", [](const std::string& ir) { return strip_cosmetic(Json::parse(ir)).dump(); });
  m.def("pcg32", [](uint64_t seed, uint64_t stream, int count) {
    Pcg32 rng(seed, stream);
    std::vector<uint32_t> out;
    for (int k = 0; k < count; ++k) out.push_back(rng.next_u32());
    return out;
  });

  nb::class_<Action>(m, "Action")
      .def("to_json", [](const Action& a, const Game& g) { return to_py(a.to_json(g.def())); })
      .def("name", [](const Action& a, const Game& g) { return a.name(g.def()); })
      .def_prop_ro("is_pass", &Action::is_pass)
      .def("__eq__", [](const Action& a, const Action& b) { return a == b; })
      .def("__hash__", [](const Action& a) { return static_cast<int64_t>(a.hash() >> 1); });

  // --- Algoritmos ---
  m.def(
      "perft",
      [](const State& s, int depth, std::vector<std::string> skip) {
        nb::gil_scoped_release release;
        return perft(s, depth, skip);
      },
      nb::arg("state"), nb::arg("depth"), nb::arg("skip") = std::vector<std::string>{});
  m.def(
      "perft_divide",
      [](const State& s, int depth, std::vector<std::string> skip) {
        std::vector<std::pair<Action, uint64_t>> out;
        {
          nb::gil_scoped_release release;
          out = perft_divide(s, depth, skip);
        }
        nb::list result;
        for (auto& [a, n] : out) result.append(nb::make_tuple(a, n));
        return result;
      },
      nb::arg("state"), nb::arg("depth"), nb::arg("skip") = std::vector<std::string>{});
  m.def(
      "alphabeta",
      [](const State& s, uint64_t max_nodes) {
        AlphaBetaResult r;
        {
          nb::gil_scoped_release release;
          r = alphabeta(s, max_nodes);
        }
        nb::dict out;
        out["value"] = rational_py(r.value);
        out["total"] = rational_py(r.total);
        out["best"] = r.best;
        out["pv"] = r.pv;
        out["states"] = r.states;
        out["nodes"] = r.nodes;
        return out;
      },
      nb::arg("state"), nb::arg("max_nodes") = 100'000'000);
  m.def(
      "mcts",
      [](const State& s, uint64_t simulations, double c, uint64_t seed, int max_rollout) {
        MctsResult r;
        {
          nb::gil_scoped_release release;
          r = mcts(s, simulations, c, seed, max_rollout);
        }
        nb::dict out;
        out["actions"] = r.actions;
        out["visits"] = r.visits;
        out["values"] = r.values;
        out["best"] = r.best;
        out["simulations"] = r.simulations;
        return out;
      },
      nb::arg("state"), nb::arg("simulations"), nb::arg("c") = 1.4, nb::arg("seed") = 0,
      nb::arg("max_rollout") = 10'000);
  m.def(
      "retrograde",
      [](const State& s, uint64_t max_positions) {
        RetroResult r;
        {
          nb::gil_scoped_release release;
          r = retrograde(s, max_positions);
        }
        nb::dict out;
        out["outcome"] = r.outcome;
        out["positions"] = r.positions;
        out["wins"] = r.wins;
        out["draws"] = r.draws;
        out["losses"] = r.losses;
        out["depth"] = r.depth;
        return out;
      },
      nb::arg("state"), nb::arg("max_positions") = 50'000'000);
  m.def(
      "cfr",
      [](const State& s, int iterations, bool plus, int measure_every, size_t max_nodes) {
        GameTreeEF tree;
        PolicyEF policy;
        std::vector<std::pair<int, double>> convergence;
        double expl;
        {
          nb::gil_scoped_release release;
          tree = build_tree(s, max_nodes);
          CfrSolver solver(tree, plus);
          solver.run(iterations, measure_every);
          policy = solver.average();
          convergence = solver.convergence();
          expl = exploitability(tree, policy);
        }
        nb::list infosets;
        for (const auto& info : tree.infosets) {
          infosets.append(nb::make_tuple(info.player, info.key, info.actions));
        }
        nb::dict out;
        out["infosets"] = infosets;
        out["policy"] = policy;
        out["convergence"] = convergence;
        out["nodes"] = tree.nodes.size();
        out["exploitability"] = expl;
        return out;
      },
      nb::arg("state"), nb::arg("iterations"), nb::arg("plus") = true,
      nb::arg("measure_every") = 0, nb::arg("max_nodes") = 10'000'000);
  m.def(
      "mccfr",
      [](const State& s, int iterations, const std::string& sampling, uint64_t seed,
         double epsilon, bool exploitability_on_tree) {
        auto kind = sampling == "outcome" ? Mccfr::Sampling::Outcome : Mccfr::Sampling::External;
        std::vector<Mccfr::Entry> policy;
        double expl = -1.0;
        size_t infosets = 0;
        {
          nb::gil_scoped_release release;
          Mccfr solver(s, kind, seed, epsilon);
          solver.run(iterations);
          policy = solver.policy();
          infosets = solver.infosets();
          if (exploitability_on_tree) {
            GameTreeEF tree = build_tree(s);
            expl = exploitability(tree, solver.on_tree(tree));
          }
        }
        nb::list entries;
        for (const auto& e : policy) entries.append(nb::make_tuple(e.player, e.key, e.average));
        nb::dict out;
        out["policy"] = entries;
        out["infosets"] = infosets;
        if (expl >= 0) out["exploitability"] = expl;
        return out;
      },
      nb::arg("state"), nb::arg("iterations"), nb::arg("sampling") = "external",
      nb::arg("seed") = 0, nb::arg("epsilon") = 0.6, nb::arg("exploitability") = false);
  m.def(
      "solve_wdl",
      [](const Game& g, int n, nb::object params, int table_bits, int threads, uint64_t max_nodes,
         double max_seconds) {
        Json p = params.is_none() ? Json::object() : from_py(params);
        WdlResult r;
        {
          nb::gil_scoped_release release;
          r = solve_wdl(g, n, p, table_bits, threads, max_nodes, max_seconds);
        }
        nb::dict out;
        out["outcome"] = r.outcome;
        out["nodes"] = r.nodes;
        out["table_hits"] = r.table_hits;
        out["seconds"] = r.seconds;
        return out;
      },
      nb::arg("game"), nb::arg("num_players"), nb::arg("params").none() = nb::none(),
      nb::arg("table_bits") = 24, nb::arg("threads") = 1, nb::arg("max_nodes") = UINT64_MAX,
      nb::arg("max_seconds") = 0.0);
  m.def("state_key", [](const State& s) {
    StateKey k = state_key(s);
    return nb::make_tuple(k.a, k.b);
  });

  nb::class_<ActionSpace>(m, "ActionSpace")
      .def("__init__",
           [](ActionSpace* self, const Game& g, nb::handle spec) {
             new (self) ActionSpace(g.def_ptr(), from_py(spec));
           })
      .def_prop_ro("size", &ActionSpace::size)
      .def("legal_ids", &ActionSpace::legal_ids)
      .def("encode", [](const ActionSpace& sp, const State& s,
                        const Action& a) { return sp.encode(s.node(), a); })
      .def("decode", [](const ActionSpace& sp, const State& s, int64_t id) {
        return sp.decode(s.node(), id);
      });

  nb::class_<Game>(m, "Game")
      .def("__init__",
           [](Game* self, const std::string& ir) { new (self) Game(Game::from_text(ir)); })
      .def_prop_ro("id", [](const Game& g) { return g.def().id; })
      .def_prop_ro("version", [](const Game& g) { return g.def().version; })
      .def_prop_ro("title", [](const Game& g) { return g.def().title; })
      .def_prop_ro("rules_hash", [](const Game& g) { return g.def().rules_hash; })
      .def_prop_ro("players",
                   [](const Game& g) { return nb::make_tuple(g.def().min_players, g.def().max_players); })
      .def(
          "new_state",
          [](const Game& g, int n, nb::object params, bool events, bool history) {
            Json p = params.is_none() ? Json::object() : from_py(params);
            return g.new_state(n, p, options(true, events, history));
          },
          nb::arg("num_players"), nb::arg("params").none() = nb::none(), nb::arg("events") = true,
          nb::arg("history") = true)
      .def(
          "decode_action",
          [](const Game& g, nb::object node, nb::handle data) {
            int index = -1;
            if (!node.is_none()) {
              auto it = g.def().node_index.find(nb::cast<std::string>(node));
              if (it != g.def().node_index.end()) index = it->second;
            }
            return g.decode_action(index, from_py(data));
          },
          nb::arg("node").none(), nb::arg("data"))
      .def("action_to_json",
           [](const Game& g, const Action& a) { return to_py(a.to_json(g.def())); })
      .def(
          "playouts",
          [](const Game& g, int n, nb::object params, uint64_t seed, uint64_t games,
             int max_steps) {
            Json p = params.is_none() ? Json::object() : from_py(params);
            PlayoutReport r;
            {
              nb::gil_scoped_release release;
              r = random_playouts(g, n, p, seed, games, max_steps);
            }
            nb::dict out;
            out["games"] = r.games;
            out["completed"] = r.completed;
            out["truncated"] = r.truncated;
            out["steps"] = r.steps;
            out["seconds"] = r.seconds;
            out["fingerprint"] = r.fingerprint;
            nb::list errors, sums;
            for (const auto& [s, m] : r.errors) errors.append(nb::make_tuple(s, m));
            for (const auto& x : r.payoff_sums) sums.append(rational_py(x));
            out["errors"] = errors;
            out["payoff_sums"] = sums;
            return out;
          },
          nb::arg("num_players"), nb::arg("params").none() = nb::none(), nb::arg("seed") = 0,
          nb::arg("games") = 1000, nb::arg("max_steps") = 10'000);

  nb::class_<State>(m, "State")
      .def_prop_ro("status", [](const State& s) { return status_name(s.status()); })
      .def_prop_ro("is_terminal", &State::is_terminal)
      .def_prop_ro("node",
                   [](const State& s) -> nb::object {
                     if (s.node() < 0) return nb::none();
                     return nb::str(s.game().node(s.node()).id.c_str());
                   })
      .def_prop_ro("num_players", &State::num_players)
      .def_prop_ro("depth", &State::depth)
      .def_prop_ro("active_seats",
                   [](const State& s) {
                     nb::list out;
                     for (int x : s.active_seats()) out.append(x);
                     return nb::tuple(out);
                   })
      .def_prop_ro("payoffs",
                   [](const State& s) -> nb::object {
                     if (!s.is_terminal()) return nb::none();
                     return to_py(payoffs_json(s.game(), s.payoffs()));
                   })
      .def("legal_actions", &State::legal_actions)
      .def("count_legal", &State::count_legal)
      .def("legal_actions_json",
           [](const State& s, int seat) {
             nb::list out;
             s.for_each_legal(seat, [&](const Action& a) {
               out.append(to_py(a.to_json(s.game())));
               return true;
             });
             return out;
           })
      .def(
          "apply_action",
          [](const State& s, int seat, const Action& a, bool validate, bool events, bool history) {
            return s.apply_action(seat, a, options(validate, events, history));
          },
          nb::arg("seat"), nb::arg("action"), nb::arg("validate") = true, nb::arg("events") = true,
          nb::arg("history") = true)
      .def(
          "chance_outcomes",
          [](const State& s, size_t limit) {
            nb::list out;
            for (const auto& [o, p] : s.chance_outcomes(limit)) {
              out.append(nb::make_tuple(outcome_py(o), rational_py(p)));
            }
            return out;
          },
          nb::arg("limit") = 100'000)
      .def("sample_chance",
           [](const State& s, uint64_t state, uint64_t inc) {
             Pcg32 rng;
             rng.state = state;
             rng.inc = inc;
             Outcome o = s.sample_chance(rng);
             return nb::make_tuple(outcome_py(o), rng.state);
           })
      .def(
          "apply_chance",
          [](const State& s, nb::handle outcome, bool events, bool history) {
            return s.apply_chance(outcome_from(outcome), options(true, events, history));
          },
          nb::arg("outcome"), nb::arg("events") = true, nb::arg("history") = true)
      .def("outcome_probability",
           [](const State& s, nb::handle outcome) {
             return rational_py(s.outcome_probability(outcome_from(outcome)));
           })
      .def(
          "view", [](const State& s, nb::object seat) { return to_py(s.view(seat_arg(seat))); },
          nb::arg("seat").none())
      .def(
          "events", [](const State& s, nb::object seat) { return to_py(s.events(seat_arg(seat))); },
          nb::arg("seat").none())
      .def("snapshot", [](const State& s) { return to_py(s.snapshot()); })
      .def("snapshot_text", &State::snapshot_text)
      .def("digest", &State::digest)
      .def("information_state", &State::information_state)
      .def("observation_digest", &State::observation_digest)
      .def("view_text", [](const State& s, int seat) { return s.view(seat).dump(); })
      .def("snapshot_hash", [](const State& s) { return s.hash(); })
      .def("next_draw",
           [](const State& s, nb::handle prefix) -> nb::object {
             auto next = s.next_draw(outcome_from(prefix));
             if (!next) return nb::none();
             nb::list probs;
             for (const auto& p : next->second) probs.append(rational_py(p));
             return nb::make_tuple(next->first, probs);
           })
      .def("hash", [](const State& s) { return s.hash(); })
      .def("ranking", &State::ranking)
      .def(
          "options",
          [](const State& s, int seat, nb::object name, nb::object args) {
            std::string n;
            const std::string* name_ptr = nullptr;
            if (!name.is_none()) {
              n = nb::cast<std::string>(name);
              name_ptr = &n;
            }
            Json a = args.is_none() ? Json::object() : from_py(args);
            return to_py(s.options(seat, name_ptr, &a));
          },
          nb::arg("seat"), nb::arg("name").none() = nb::none(), nb::arg("args").none() = nb::none())
      .def("illegal_reason", &State::illegal_reason)
      .def("evaluate",
           [](const State& s, nb::handle expr) {
             return to_py(s.game().types.to_json(s.evaluate(from_py(expr))));
           })
      .def("decode_action", [](const State& s, nb::handle data) { return s.decode_action(from_py(data)); })
      .def("step",
           [](const State& s) {
             const Step& st = s.step();
             nb::dict out;
             static const char* kinds[] = {"start", "action", "chance", "edit"};
             out["kind"] = kinds[static_cast<int>(st.kind)];
             if (st.kind == Step::Kind::Action) {
               out["seat"] = st.seat;
               out["action"] = to_py(st.action.to_json(s.game()));
             }
             if (st.kind == Step::Kind::Chance) out["outcome"] = outcome_py(st.outcome);
             return out;
           })
      .def("params",
           [](const State& s) {
             nb::dict out;
             const GameDef& g = s.game();
             for (size_t k = 0; k < g.params.size(); ++k) {
               out[g.params[k].name.c_str()] = to_py(g.types.to_json(s.data().match->params[k]));
             }
             return out;
           })
      .def("step_events",
           [](const State& s) {
             nb::list out;
             for (const auto& e : s.step().events) {
               nb::list seen;
               for (const auto& p : e.seen) seen.append(p ? to_py(*p) : nb::none());
               out.append(nb::make_tuple(to_py(*e.full), nb::tuple(seen),
                                         e.pub ? to_py(*e.pub) : nb::none()));
             }
             return out;
           })
      .def("parent", [](const State& s) -> std::optional<State> {
        if (!s.data().parent) return std::nullopt;
        return State(s.data().parent);
      });
}
