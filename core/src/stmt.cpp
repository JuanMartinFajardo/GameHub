// SPDX-License-Identifier: Apache-2.0
#include "gamehub/stmt.hpp"

#include <algorithm>

#include "gamehub/errors.hpp"

namespace gh {

namespace {

std::string repr(const Value& v, const Ctx& ctx) { return ctx.game->types.repr(v); }

const JsonPtr HIDDEN_JSON =
    std::make_shared<const Json>(Json(JsonObject{{"$hidden", Json(true)}}));

const Json& hidden() { return *HIDDEN_JSON; }

int64_t int_arg(const Value& v, const char* op, const Ctx& ctx) {
  expect_num(v, op, ctx);
  if (v.tag != Tag::Int) rule_error(std::string("'") + op + "' espera un entero");
  return v.i;
}

Draws& draws(Ctx& ctx) {
  if (ctx.draws == nullptr) rule_error("sentencia aleatoria fuera de un nodo de azar");
  return *ctx.draws;
}

const ArrayObj* expect_zone(const Value& v, const Ctx& ctx) {
  if (v.tag != Tag::Zone) rule_error("se esperaba una zona o bolsa, no " + repr(v, ctx));
  return v.arr();
}

void require_ordered(const ArrayObj* z, const char* what) {
  if (z->a == 0) {
    rule_error(std::string("'") + what + "' necesita una zona ordenada; las bolsas no tienen orden");
  }
}

// Una zona con otros elementos y el mismo orden (las bolsas se reordenan canónicamente).
Value zone_with(ValueVec&& values, ByteVec&& faces, bool ordered) {
  return Value::zone(std::move(values), std::move(faces), ordered);
}

}  // namespace

void Block::run(Ctx& ctx, Frame& frame) const {
  for (const auto& s : stmts) s->exec(ctx, frame);
}

bool Policy::allows(Ctx& ctx, Frame& frame) const {
  if (frame.viewer == NO_SEAT || kind == Kind::All) return true;
  if (kind == Kind::None) return false;
  if (kind == Kind::Owner) return frame.viewer == frame.owner;
  ScopedFrame scope(ctx.machine(), pred.frame);
  scope.frame.viewer = frame.viewer;
  scope.frame.owner = frame.owner;
  scope.frame.face_up = frame.face_up;
  if (frame.viewer == PUBLIC) {
    try {
      return expect_bool(ctx.machine().eval(pred.chunk, ctx, scope.frame), "visibilidad", ctx);
    } catch (const RuleError&) {
      return false;
    }
  }
  return expect_bool(ctx.machine().eval(pred.chunk, ctx, scope.frame), "visibilidad", ctx);
}

// --- Escritura y coerción ----------------------------------------------------------------------

void write_var(Ctx& ctx, uint32_t var, Value value) {
  (*ctx.store)[var] = std::move(value);
  if (ctx.memo != nullptr) ctx.memo->clear();
}

Value coerce(Value v, const Type& t, const Ctx& ctx) {
  switch (t.kind) {
    case Type::Kind::Zone:
    case Type::Kind::Bag: {
      bool ordered = t.kind == Type::Kind::Zone;
      if (v.tag == Tag::Zone) {
        if ((v.arr()->a != 0) == ordered) return v;
        const ArrayObj* z = v.arr();
        ValueVec values(z->items(), z->items() + z->n);
        ByteVec faces(z->faces(), z->faces() + z->n);
        return zone_with(std::move(values), std::move(faces), ordered);
      }
      Items it = iterate(v, "iteración", ctx);
      ValueVec values;
      for (size_t k = 0; k < it.size; ++k) values.push_back(it[k]);
      ByteVec faces(values.size(), 0);
      return zone_with(std::move(values), std::move(faces), ordered);
    }
    case Type::Kind::Set: {
      if (v.tag == Tag::Set) return v;
      Items it = iterate(v, "iteración", ctx);
      ValueVec values;
      for (size_t k = 0; k < it.size; ++k) values.push_back(it[k]);
      return Value::set(std::move(values));
    }
    case Type::Kind::Map: {
      if (v.tag == Tag::Map) return v;
      Items it = iterate(v, "iteración", ctx);
      ValueVec pairs;
      for (size_t k = 0; k < it.size; ++k) {
        const Value& p = it[k];
        if (!p.is_tuple_like() || p.tuple_size() != 2) rule_error("se esperaba un par (clave, valor)");
        pairs.push_back(p.tuple_at(0));
        pairs.push_back(p.tuple_at(1));
      }
      return Value::map(std::move(pairs));
    }
    case Type::Kind::PerPlayer:
    case Type::Kind::List: {
      Type::Kind inner = t.inner().kind;
      bool deep = inner == Type::Kind::Zone || inner == Type::Kind::Bag ||
                  inner == Type::Kind::Set || inner == Type::Kind::Map ||
                  inner == Type::Kind::PerPlayer || inner == Type::Kind::List ||
                  inner == Type::Kind::Option;
      if (!deep) return v;
      if (!v.is_tuple_like()) rule_error("se esperaba una lista, no " + repr(v, ctx));
      size_t n = v.tuple_size();
      Value out = Value::alloc_array(Tag::Tuple, static_cast<uint32_t>(n));
      for (size_t k = 0; k < n; ++k) out.arr()->items()[k] = coerce(v.tuple_at(k), t.inner(), ctx);
      return out;
    }
    case Type::Kind::Option:
      return v.is_none() ? v : coerce(std::move(v), t.inner(), ctx);
    default:
      return v;
  }
}

Value grid_from_rows(const Value& rows, int64_t width, int64_t height, const Type& t,
                     const Ctx& ctx) {
  bool ok = rows.is_tuple_like() && static_cast<int64_t>(rows.tuple_size()) == height;
  if (ok) {
    for (size_t r = 0; r < rows.tuple_size(); ++r) {
      Value row = rows.tuple_at(r);
      if (!row.is_tuple_like() || static_cast<int64_t>(row.tuple_size()) != width) {
        ok = false;
        break;
      }
    }
  }
  if (!ok) {
    rule_error("se esperaban " + std::to_string(height) + " filas de " + std::to_string(width) +
               " casillas para la rejilla");
  }
  ValueVec cells;
  cells.reserve(static_cast<size_t>(width * height));
  for (size_t r = 0; r < rows.tuple_size(); ++r) {
    Value row = rows.tuple_at(r);
    for (size_t c = 0; c < row.tuple_size(); ++c) cells.push_back(coerce(row.tuple_at(c), t.inner(), ctx));
  }
  return Value::grid(static_cast<uint32_t>(width), static_cast<uint32_t>(height), std::move(cells));
}

// --- Ubicaciones -------------------------------------------------------------------------------

namespace {

// Un paso de lectura (`index_value` o el campo de un struct), con sus errores.
Value step_get(const Ctx& ctx, const LStep& st, const Value& cur, const Value& key) {
  if (st.is_field) {
    if (cur.tag != Tag::Struct) rule_error("se esperaba un struct, no " + repr(cur, ctx));
    int slot = ctx.game->field_slots[st.field][cur.arr()->a];
    if (slot < 0) {
      rule_error(ctx.game->types.structs()[cur.arr()->a].name + " no tiene el campo " +
                 ctx.game->field_names[st.field]);
    }
    return cur.arr()->items()[slot];
  }
  return index_value(cur, key, ctx);
}

// Posición de `key` en un contenedor para escribirla (comprueba el rango como `_with_index`).
// Devuelve -1 en un mapa sin esa clave (hay que insertarla).
int64_t write_position(const Ctx& ctx, const LStep& st, const Value& cur, const Value& key) {
  if (st.is_field) {
    step_get(ctx, st, cur, key);
    return ctx.game->field_slots[st.field][cur.arr()->a];
  }
  switch (cur.tag) {
    case Tag::Tuple:
    case Tag::Cell:
      index_value(cur, key, ctx);
      return key.i;
    case Tag::Grid: {
      index_value(cur, key, ctx);
      const ArrayObj* g = cur.arr();
      int64_t r, c;
      if (key.tag == Tag::Cell) {
        r = key.cell_row();
        c = key.cell_col();
      } else {
        r = key.arr()->items()[0].i;
        c = key.arr()->items()[1].i;
      }
      return r * g->a + c;
    }
    case Tag::Map: {
      const ArrayObj* m = cur.arr();
      for (uint32_t k = 0; k < m->n / 2; ++k) {
        if (equals(m->items()[2 * k], key)) return 2 * k + 1;
      }
      return -1;
    }
    default:
      rule_error("no se puede asignar por índice en " + repr(cur, ctx));
  }
}

void update(const Ctx& ctx, Value& slot, const LValue& lv, const ValueVec& keys,
            size_t i, Value&& value);

void update_child(const Ctx& ctx, ArrayObj* obj, size_t pos, const LValue& lv,
                  const ValueVec& keys, size_t i, Value&& value) {
  Value& child = obj->items()[pos];
  if (obj->hash > 1) {
    uint64_t old = hash_value(child);
    update(ctx, child, lv, keys, i, std::move(value));
    obj->hash ^= positional_hash(pos, old) ^ positional_hash(pos, hash_value(child));
    if (obj->hash <= 1) obj->hash = 0;
  } else {
    obj->hash = 0;
    update(ctx, child, lv, keys, i, std::move(value));
  }
}

void update(const Ctx& ctx, Value& slot, const LValue& lv, const ValueVec& keys,
            size_t i, Value&& value) {
  if (i == lv.steps.size()) {
    slot = std::move(value);
    return;
  }
  const LStep& st = lv.steps[i];
  int64_t pos = write_position(ctx, st, slot, keys[i]);
  if (pos < 0) {
    // Una clave nueva en un mapa: solo puede ser el último paso (los anteriores se leyeron).
    const ArrayObj* m = slot.arr();
    ValueVec pairs(m->items(), m->items() + m->n);
    pairs.push_back(keys[i]);
    pairs.push_back(std::move(value));
    slot = Value::map(std::move(pairs));
    return;
  }
  if (slot.tag == Tag::Cell) {
    slot = Value::tuple(ValueVec{Value::integer(slot.cell_row()),
                                           Value::integer(slot.cell_col())});
  }
  update_child(ctx, slot.unique_arr(), static_cast<size_t>(pos), lv, keys, i + 1,
               std::move(value));
}

}  // namespace

ValueVec LValue::keys(Ctx& ctx, Frame& frame) const {
  // Claves y lecturas intercaladas, como `get` en Python: el error del primer nivel inválido.
  ValueVec out;
  out.reserve(steps.size());
  Value cur = (*ctx.store)[var];
  for (size_t k = 0; k < steps.size(); ++k) {
    const LStep& st = steps[k];
    Value key = st.is_field ? Value() : ctx.machine().eval(st.key, ctx, frame);
    if (k + 1 < steps.size()) cur = step_get(ctx, st, cur, key);
    out.push_back(std::move(key));
  }
  return out;
}

Value LValue::get_with(Ctx& ctx, const ValueVec& ks) const {
  Value cur = (*ctx.store)[var];
  for (size_t k = 0; k < steps.size(); ++k) cur = step_get(ctx, steps[k], cur, ks[k]);
  return cur;
}

Value LValue::get(Ctx& ctx, Frame& frame) const { return get_with(ctx, keys(ctx, frame)); }

void LValue::set_with(Ctx& ctx, const ValueVec& ks, Value value) const {
  update(ctx, (*ctx.store)[var], *this, ks, 0, std::move(value));
  if (ctx.memo != nullptr) ctx.memo->clear();
}

int32_t LValue::owner(const ValueVec& ks) const {
  int32_t owner = NO_SEAT;
  for (size_t k = 0; k < steps.size(); ++k) {
    if (steps[k].per_player) owner = static_cast<int32_t>(ks[k].i);
  }
  return owner;
}

Json location_json(const GameDef& game, uint32_t var, int32_t owner) {
  JsonObject loc;
  loc.emplace_back("var", Json(game.vars[var].name));
  if (owner != NO_SEAT) loc.emplace_back("seat", Json(int64_t(owner)));
  return Json(std::move(loc));
}

// --- Selectores --------------------------------------------------------------------------------

PoolVec<size_t> Selector::select(Ctx& ctx, Frame& frame, const Value& zone_v) const {
  const ArrayObj* z = zone_v.arr();
  size_t size = z->n;
  PoolVec<size_t> chosen;
  switch (kind) {
    case Kind::All:
      for (size_t k = 0; k < size; ++k) chosen.push_back(k);
      return chosen;
    case Kind::Top:
    case Kind::Bottom: {
      const char* name = kind == Kind::Top ? "top" : "bottom";
      int64_t k = int_arg(ctx.machine().eval(arg, ctx, frame), name, ctx);
      require_ordered(z, name);
      if (k < 0 || k > static_cast<int64_t>(size)) {
        rule_error(std::string("'") + name + " " + std::to_string(k) + "' en una zona de " +
                   std::to_string(size) + " elementos");
      }
      size_t first = kind == Kind::Top ? 0 : size - static_cast<size_t>(k);
      for (size_t j = 0; j < static_cast<size_t>(k); ++j) chosen.push_back(first + j);
      return chosen;
    }
    case Kind::At: {
      int64_t i = int_arg(ctx.machine().eval(arg, ctx, frame), "at", ctx);
      require_ordered(z, "at");
      if (i < 0 || i >= static_cast<int64_t>(size)) {
        rule_error("posición " + std::to_string(i) + " fuera de una zona de " +
                   std::to_string(size) + " elementos");
      }
      chosen.push_back(static_cast<size_t>(i));
      return chosen;
    }
    case Kind::Value:
    case Kind::Values: {
      Value a = ctx.machine().eval(arg, ctx, frame);
      ValueVec wanted;
      if (kind == Kind::Value) {
        wanted.push_back(a);
      } else {
        Items it = iterate(a, "values", ctx);
        for (size_t k = 0; k < it.size; ++k) wanted.push_back(it[k]);
      }
      for (const auto& v : wanted) {
        size_t found = size;
        for (size_t k = 0; k < size; ++k) {
          if (equals(z->items()[k], v) &&
              std::find(chosen.begin(), chosen.end(), k) == chosen.end()) {
            found = k;
            break;
          }
        }
        if (found == size) rule_error("no hay " + repr(v, ctx) + " en la zona");
        chosen.push_back(found);
      }
      return chosen;
    }
  }
  return chosen;
}

// --- Sentencias básicas ------------------------------------------------------------------------

void AssignStmt::exec(Ctx& ctx, Frame& frame) const {
  Value v = ctx.machine().eval(value, ctx, frame);
  if (target.type->kind == Type::Kind::Grid) {
    if (v.tag != Tag::Grid) {
      auto dim = [&](const std::variant<int64_t, std::string>& d) -> int64_t {
        if (std::holds_alternative<int64_t>(d)) return std::get<int64_t>(d);
        return (*ctx.params)[ctx.game->param_index.at(std::get<std::string>(d))].i;
      };
      v = grid_from_rows(v, dim(target.type->width), dim(target.type->height), *target.type, ctx);
    }
  } else {
    v = coerce(std::move(v), *target.type, ctx);
  }
  if (target.steps.empty()) {
    write_var(ctx, target.var, std::move(v));
    return;
  }
  target.set_with(ctx, target.keys(ctx, frame), std::move(v));
}

void LetStmt::exec(Ctx& ctx, Frame& frame) const { frame.slots[slot] = ctx.machine().eval(value, ctx, frame); }

void IfStmt::exec(Ctx& ctx, Frame& frame) const {
  if (expect_bool(ctx.machine().eval(cond, ctx, frame), "if", ctx)) {
    then.run(ctx, frame);
  } else {
    other.run(ctx, frame);
  }
}

void ForStmt::exec(Ctx& ctx, Frame& frame) const {
  Items it = iterate(ctx.machine().eval(coll, ctx, frame), "for", ctx);
  for (size_t k = 0; k < it.size; ++k) {
    frame.slots[slot] = it[k];
    body.run(ctx, frame);
  }
}

void FailStmt::exec(Ctx&, Frame&) const { rule_error(message); }

// --- Zonas -------------------------------------------------------------------------------------

namespace {

struct Sighting {
  bool size = false;
  PoolVec<bool> items;
};

// Para cada asiento y al final un espectador: ¿ve el tamaño de la zona? ¿y cada elemento?
std::vector<Sighting> sightings(Ctx& ctx, uint32_t var, int32_t owner,
                                const ByteVec& faces) {
  const VarDef& def = ctx.game->vars[var];
  std::vector<Sighting> out;
  for (int s = 0; s <= ctx.n; ++s) {
    Frame probe;
    probe.viewer = s == ctx.n ? PUBLIC : s;
    probe.owner = owner;
    Sighting sight;
    for (uint8_t face : faces) {
      probe.face_up = static_cast<int8_t>(face);
      sight.items.push_back(def.policy.allows(ctx, probe));
    }
    probe.face_up = -1;
    sight.size = def.size_policy.allows(ctx, probe);
    out.push_back(std::move(sight));
  }
  return out;
}

}  // namespace

void MoveStmt::exec(Ctx& ctx, Frame& frame) const {
  ValueVec src_keys = src.keys(ctx, frame);
  Value zone_v = src.get_with(ctx, src_keys);
  const ArrayObj* zone = expect_zone(zone_v, ctx);
  PoolVec<size_t> chosen = sel.select(ctx, frame, zone_v);
  ValueVec moved;
  ByteVec moved_faces;
  for (size_t k : chosen) {
    moved.push_back(zone->items()[k]);
    moved_faces.push_back(zone->faces()[k]);
  }
  int32_t src_owner = src.owner(src_keys);
  std::vector<Sighting> before;
  if (ctx.recording()) before = sightings(ctx, src.var, src_owner, moved_faces);
  PoolVec<bool> keep(zone->n, true);
  for (size_t k : chosen) keep[k] = false;
  ValueVec rest;
  ByteVec rest_faces;
  for (size_t k = 0; k < zone->n; ++k) {
    if (keep[k]) {
      rest.push_back(zone->items()[k]);
      rest_faces.push_back(zone->faces()[k]);
    }
  }
  bool src_ordered = zone->a != 0;
  zone_v = Value();
  src.set_with(ctx, src_keys, zone_with(std::move(rest), std::move(rest_faces), src_ordered));

  ValueVec dst_keys = dst.keys(ctx, frame);
  Value target_v = dst.get_with(ctx, dst_keys);
  const ArrayObj* target = expect_zone(target_v, ctx);
  ValueVec values;
  ByteVec faces;
  if (to_top) {
    values = moved;
    faces = moved_faces;
  }
  for (size_t k = 0; k < target->n; ++k) {
    values.push_back(target->items()[k]);
    faces.push_back(target->faces()[k]);
  }
  if (!to_top) {
    values.insert(values.end(), moved.begin(), moved.end());
    faces.insert(faces.end(), moved_faces.begin(), moved_faces.end());
  }
  bool dst_ordered = target->a != 0;
  target_v = Value();
  Value result = coerce(zone_with(std::move(values), std::move(faces), dst_ordered), *dst.type, ctx);
  dst.set_with(ctx, dst_keys, std::move(result));
  if (!ctx.recording()) return;

  int32_t dst_owner = dst.owner(dst_keys);
  std::vector<Sighting> after = sightings(ctx, dst.var, dst_owner, moved_faces);
  const TypeTable& types = ctx.game->types;
  JsonArray items;
  for (const auto& v : moved) items.push_back(types.to_json(v));
  JsonObject full;
  full.emplace_back("type", Json("move"));
  full.emplace_back("from", location_json(*ctx.game, src.var, src_owner));
  full.emplace_back("to", location_json(*ctx.game, dst.var, dst_owner));
  full.emplace_back("count", Json(int64_t(moved.size())));
  full.emplace_back("items", Json(items));
  auto full_ptr = std::make_shared<const Json>(Json(full));
  std::vector<JsonPtr> seen;
  for (size_t s = 0; s < before.size(); ++s) {
    const Sighting& a = before[s];
    const Sighting& b = after[s];
    if (!(a.size || b.size)) {
      seen.push_back(nullptr);
      continue;
    }
    JsonArray shown;
    bool all_shown = true;
    for (size_t k = 0; k < items.size(); ++k) {
      bool visible = a.items[k] || b.items[k];
      all_shown = all_shown && visible;
      shown.push_back(visible ? items[k] : hidden());
    }
    if (all_shown) {
      seen.push_back(full_ptr);
    } else {
      Json copy(full);
      copy.set("items", Json(std::move(shown)));
      seen.push_back(std::make_shared<const Json>(std::move(copy)));
    }
  }
  JsonPtr pub = seen.back();
  seen.pop_back();
  ctx.events->push_back(Event{full_ptr, std::move(seen), pub});
}

void FlipStmt::exec(Ctx& ctx, Frame& frame) const {
  ValueVec keys = target.keys(ctx, frame);
  Value zone_v = target.get_with(ctx, keys);
  const ArrayObj* zone = expect_zone(zone_v, ctx);
  PoolVec<size_t> chosen_list = sel.select(ctx, frame, zone_v);
  PoolVec<bool> chosen(zone->n, false);
  size_t count = 0;
  for (size_t k : chosen_list) {
    if (!chosen[k]) ++count;
    chosen[k] = true;
  }
  bool up = expect_bool(ctx.machine().eval(face, ctx, frame), "flip", ctx);
  ValueVec values(zone->items(), zone->items() + zone->n);
  ByteVec faces(zone->faces(), zone->faces() + zone->n);
  for (size_t k = 0; k < faces.size(); ++k) {
    if (chosen[k]) faces[k] = up ? 1 : 0;
  }
  bool ordered = zone->a != 0;
  zone_v = Value();
  target.set_with(ctx, keys, zone_with(std::move(values), std::move(faces), ordered));
  if (!ctx.recording()) return;
  JsonObject payload;
  payload.emplace_back("type", Json("flip"));
  payload.emplace_back("zone", location_json(*ctx.game, target.var, target.owner(keys)));
  payload.emplace_back("count", Json(int64_t(count)));
  payload.emplace_back("face_up", Json(up));
  ctx.events->push_back(Event::shared(Json(std::move(payload)), ctx.n));
}

// --- Azar --------------------------------------------------------------------------------------

void ShuffleStmt::exec(Ctx& ctx, Frame& frame) const {
  ValueVec keys = target.keys(ctx, frame);
  Value zone_v = target.get_with(ctx, keys);
  const ArrayObj* zone = expect_zone(zone_v, ctx);
  require_ordered(zone, "shuffle");
  ValueVec values(zone->items(), zone->items() + zone->n);
  ByteVec faces(zone->faces(), zone->faces() + zone->n);
  Draws& d = draws(ctx);
  for (size_t i = values.size(); i-- > 1;) {
    auto j = static_cast<size_t>(d.uniform(static_cast<int64_t>(i + 1)));
    std::swap(values[i], values[j]);
    std::swap(faces[i], faces[j]);
  }
  zone_v = Value();
  target.set_with(ctx, keys, zone_with(std::move(values), std::move(faces), true));
  if (!ctx.recording()) return;
  JsonObject payload;
  payload.emplace_back("type", Json("shuffle"));
  payload.emplace_back("zone", location_json(*ctx.game, target.var, target.owner(keys)));
  ctx.events->push_back(Event::shared(Json(std::move(payload)), ctx.n));
}

namespace {

void set_target(Ctx& ctx, Frame& frame, const LValue& target, Value v) {
  if (target.steps.empty()) {
    write_var(ctx, target.var, std::move(v));
  } else {
    target.set_with(ctx, target.keys(ctx, frame), std::move(v));
  }
}

}  // namespace

void RollStmt::exec(Ctx& ctx, Frame& frame) const {
  Draws& d = draws(ctx);
  int64_t n = int_arg(ctx.machine().eval(sides, ctx, frame), "roll", ctx);
  int64_t value = d.uniform(n) + 1;
  set_target(ctx, frame, target, Value::integer(value));
}

void RandomChoiceStmt::exec(Ctx& ctx, Frame& frame) const {
  Items it = iterate(ctx.machine().eval(coll, ctx, frame), "random_choice", ctx);
  auto k = static_cast<size_t>(draws(ctx).uniform(static_cast<int64_t>(it.size)));
  set_target(ctx, frame, target, coerce(it[k], *target.type, ctx));
}

void SampleStmt::exec(Ctx& ctx, Frame& frame) const {
  Items pairs = iterate(ctx.machine().eval(dist, ctx, frame), "sample", ctx);
  std::vector<Rational> probs;
  Rational total = Rational::integer(0);
  bool negative = false;
  for (size_t k = 0; k < pairs.size; ++k) {
    Value p = index_value(pairs[k], Value::integer(1), ctx);
    Rational r = expect_num(p, "sample", ctx).as_rational();
    if (r.num < 0) negative = true;
    total = total + r;
    probs.push_back(r);
  }
  if (negative || !(total == Rational::integer(1))) {
    std::string listing;
    for (size_t k = 0; k < probs.size(); ++k) listing += (k ? ", " : "") + probs[k].str();
    rule_error("distribución inválida en 'sample': [" + listing + "]");
  }
  auto i = static_cast<size_t>(draws(ctx).weighted(probs));
  Value choice = index_value(pairs[i], Value::integer(0), ctx);
  set_target(ctx, frame, target, coerce(std::move(choice), *target.type, ctx));
}

// --- Eventos -----------------------------------------------------------------------------------

void RevealStmt::exec(Ctx& ctx, Frame& frame) const {
  int n = ctx.n;
  PoolVec<bool> to(static_cast<size_t>(n), false);
  size_t count = 0;
  Items it = iterate(ctx.machine().eval(seats, ctx, frame), "reveal", ctx);
  for (size_t k = 0; k < it.size; ++k) {
    auto s = static_cast<size_t>(expect_seat(it[k], n, "reveal", ctx));
    if (!to[s]) ++count;
    to[s] = true;
  }
  Value v = ctx.machine().eval(value, ctx, frame);
  if (!ctx.recording()) return;
  JsonObject payload;
  payload.emplace_back("type", Json("reveal"));
  payload.emplace_back("value", ctx.game->types.to_json(v));
  if (has_label) payload.emplace_back("label", label);
  auto p = std::make_shared<const Json>(Json(std::move(payload)));
  std::vector<JsonPtr> seen;
  for (int s = 0; s < n; ++s) seen.push_back(to[static_cast<size_t>(s)] ? p : nullptr);
  ctx.events->push_back(Event{p, std::move(seen), count == static_cast<size_t>(n) ? p : nullptr});
}

void EmitStmt::exec(Ctx& ctx, Frame& frame) const {
  JsonObject values;
  for (const auto& [k, chunk] : fields) {
    values.emplace_back(k, ctx.game->types.to_json(ctx.machine().eval(chunk, ctx, frame)));
  }
  if (!ctx.recording()) return;
  JsonObject payload;
  payload.emplace_back("type", Json("emit"));
  payload.emplace_back("name", Json(name));
  payload.emplace_back("fields", Json(std::move(values)));
  auto p = std::make_shared<const Json>(Json(std::move(payload)));
  std::vector<JsonPtr> seen;
  for (int s = 0; s <= ctx.n; ++s) {
    Frame probe;
    probe.viewer = s == ctx.n ? PUBLIC : s;
    probe.owner = frame.actor;
    seen.push_back(policy.allows(ctx, probe) ? p : nullptr);
  }
  JsonPtr pub = seen.back();
  seen.pop_back();
  ctx.events->push_back(Event{p, std::move(seen), pub});
}

void RewardStmt::exec(Ctx& ctx, Frame& frame) const {
  int64_t s = expect_seat(ctx.machine().eval(seat, ctx, frame), ctx.n, "reward", ctx);
  Value a = ctx.machine().eval(amount, ctx, frame);
  expect_num(a, "reward", ctx);
  if (!ctx.recording()) return;
  JsonObject payload;
  payload.emplace_back("type", Json("reward"));
  payload.emplace_back("seat", Json(s));
  payload.emplace_back("amount", ctx.game->types.to_json(a));
  ctx.events->push_back(Event::shared(Json(std::move(payload)), ctx.n));
}

}  // namespace gh
