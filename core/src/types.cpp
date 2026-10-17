// SPDX-License-Identifier: Apache-2.0
#include "gamehub/types.hpp"

#include <algorithm>
#include <charconv>
#include <stdexcept>

#include "gamehub/errors.hpp"

namespace gh {

int StructDecl::field_index(const std::string& field) const {
  for (size_t k = 0; k < fields.size(); ++k) {
    if (fields[k] == field) return static_cast<int>(k);
  }
  return -1;
}

TypeTable::TypeTable(const Json& decls) {
  // Ids en orden alfabético de nombre: el orden canónico de Python compara los nombres.
  std::vector<const Json*> enums, structs;
  for (const auto& d : decls.as_array()) {
    if (d["kind"].as_string() == "enum") {
      enums.push_back(&d);
    } else {
      structs.push_back(&d);
    }
  }
  auto by_name = [](const Json* a, const Json* b) {
    return (*a)["name"].as_string() < (*b)["name"].as_string();
  };
  std::sort(enums.begin(), enums.end(), by_name);
  std::sort(structs.begin(), structs.end(), by_name);
  for (const Json* d : enums) {
    EnumDecl e{(*d)["name"].as_string(), {}};
    for (const auto& v : (*d)["values"].as_array()) e.values.push_back(v.as_string());
    enum_ids_[e.name] = static_cast<int>(enums_.size());
    enums_.push_back(std::move(e));
  }
  for (const Json* d : structs) {
    struct_ids_[(*d)["name"].as_string()] = static_cast<int>(structs_.size());
    structs_.push_back(StructDecl{(*d)["name"].as_string(), {}, {}});
  }
  // Los campos después: pueden referirse a cualquier struct.
  for (const Json* d : structs) {
    StructDecl& s = structs_[struct_ids_[(*d)["name"].as_string()]];
    for (const auto& f : (*d)["fields"].as_array()) {
      s.fields.push_back(f["name"].as_string());
      s.types.push_back(parse(f["type"]));
    }
  }
}

int TypeTable::enum_id(const std::string& name) const {
  auto it = enum_ids_.find(name);
  return it == enum_ids_.end() ? -1 : it->second;
}

int TypeTable::struct_id(const std::string& name) const {
  auto it = struct_ids_.find(name);
  return it == struct_ids_.end() ? -1 : it->second;
}

Value TypeTable::enum_value(const std::string& type, const std::string& name) const {
  int id = enum_id(type);
  if (id < 0) throw RuleError("enumerado desconocido: " + type);
  const auto& values = enums_[id].values;
  for (size_t k = 0; k < values.size(); ++k) {
    if (values[k] == name) return Value::enumeration(static_cast<uint32_t>(id), int64_t(k));
  }
  throw RuleError(type + " no tiene el valor " + name);
}

TypeRef TypeTable::parse(const Json& raw) const {
  auto t = std::make_shared<Type>();
  if (raw.is_string()) {
    const std::string& name = raw.as_string();
    static const std::pair<const char*, Type::Kind> prims[] = {
        {"Bool", Type::Kind::Bool}, {"Int", Type::Kind::Int},   {"Real", Type::Kind::Real},
        {"Text", Type::Kind::Text}, {"Seat", Type::Kind::Seat}, {"Cell", Type::Kind::Cell}};
    for (const auto& [prim, kind] : prims) {
      if (name == prim) {
        t->kind = kind;
        return t;
      }
    }
    int e = enum_id(name);
    if (e >= 0) {
      t->kind = Type::Kind::Enum;
      t->id = static_cast<uint32_t>(e);
      return t;
    }
    int s = struct_id(name);
    if (s < 0) throw IrError("tipo desconocido: " + name);
    t->kind = Type::Kind::Struct;
    t->id = static_cast<uint32_t>(s);
    return t;
  }
  const auto& parts = raw.as_array();
  const std::string& head = parts.at(0).as_string();
  if (head == "grid") {
    t->kind = Type::Kind::Grid;
    auto dim = [](const Json& d) -> std::variant<int64_t, std::string> {
      if (d.is_int()) return d.as_int();
      return d.at(1).as_string();
    };
    t->width = dim(parts.at(1));
    t->height = dim(parts.at(2));
    t->args.push_back(parse(parts.at(3)));
    return t;
  }
  static const std::pair<const char*, Type::Kind> ctors[] = {
      {"option", Type::Kind::Option},        {"list", Type::Kind::List},
      {"set", Type::Kind::Set},              {"map", Type::Kind::Map},
      {"tuple", Type::Kind::Tuple},          {"per_player", Type::Kind::PerPlayer},
      {"zone", Type::Kind::Zone},            {"bag", Type::Kind::Bag}};
  bool found = false;
  for (const auto& [ctor, kind] : ctors) {
    if (head == ctor) {
      t->kind = kind;
      found = true;
      break;
    }
  }
  if (!found) throw IrError("constructor de tipo desconocido: " + head);
  for (size_t k = 1; k < parts.size(); ++k) t->args.push_back(parse(parts[k]));
  return t;
}

// --- JSON → valor ------------------------------------------------------------------------------

namespace {

[[noreturn]] void bad(const std::string& why) { throw std::invalid_argument(why); }

const JsonArray& as_list(const Json& j) {
  if (!j.is_array()) bad("se esperaba una lista");
  return j.as_array();
}

int64_t parse_i64(std::string_view s) {
  int64_t v = 0;
  auto [ptr, ec] = std::from_chars(s.data(), s.data() + s.size(), v);
  if (ec != std::errc() || ptr != s.data() + s.size()) bad("número inválido");
  return v;
}

// "n/d", "n" o un decimal "a.b" (como `Fraction(texto)`).
Rational parse_rational(std::string s) {
  s.erase(0, s.find_first_not_of(" \t"));
  s.erase(s.find_last_not_of(" \t") + 1);
  auto slash = s.find('/');
  if (slash != std::string::npos) {
    int64_t d = parse_i64(std::string_view(s).substr(slash + 1));
    if (d == 0) bad("denominador cero");
    return Rational::of(parse_i64(std::string_view(s).substr(0, slash)), d);
  }
  auto dot = s.find('.');
  if (dot != std::string::npos) {
    std::string digits = s.substr(0, dot) + s.substr(dot + 1);
    __int128 den = 1;
    for (size_t k = dot + 1; k < s.size(); ++k) den *= 10;
    return Rational::of(parse_i64(digits), den);
  }
  return Rational::integer(parse_i64(s));
}

}  // namespace

Value TypeTable::decode(const Json& j, const Type& t) const {
  switch (t.kind) {
    case Type::Kind::Bool:
      if (!j.is_bool()) bad("se esperaba un booleano");
      return Value::boolean(j.as_bool());
    case Type::Kind::Int:
    case Type::Kind::Seat:
      if (!j.is_int()) bad("se esperaba un entero");
      return Value::integer(j.as_int());
    case Type::Kind::Real:
      if (j.is_int()) return Value::integer(j.as_int());
      if (!j.is_string()) bad("se esperaba un número");
      return Value::number(parse_rational(j.as_string()));
    case Type::Kind::Text:
      if (!j.is_string()) bad("se esperaba un texto");
      return Value::text(j.as_string());
    case Type::Kind::Cell: {
      const auto& rc = as_list(j);
      if (rc.size() != 2 || !rc[0].is_int() || !rc[1].is_int()) bad("se esperaba [fila, columna]");
      return Value::cell(rc[0].as_int(), rc[1].as_int());
    }
    case Type::Kind::Enum: {
      if (!j.is_string()) bad("se esperaba el nombre de un valor");
      const auto& values = enums_[t.id].values;
      for (size_t k = 0; k < values.size(); ++k) {
        if (values[k] == j.as_string()) return Value::enumeration(t.id, int64_t(k));
      }
      bad(enums_[t.id].name + " no tiene el valor " + j.as_string());
    }
    case Type::Kind::Struct: {
      const StructDecl& s = structs_[t.id];
      if (!j.is_object() || j.size() != s.fields.size()) bad("se esperaba un objeto");
      ValueVec fields;
      fields.reserve(s.fields.size());
      for (size_t k = 0; k < s.fields.size(); ++k) {
        const Json* f = j.find(s.fields[k]);
        if (f == nullptr) bad("falta el campo " + s.fields[k]);
        fields.push_back(decode(*f, *s.types[k]));
      }
      return Value::structure(t.id, std::move(fields));
    }
    case Type::Kind::Option:
      return j.is_null() ? Value::none() : decode(j, t.inner());
    case Type::Kind::List:
    case Type::Kind::PerPlayer: {
      ValueVec items;
      for (const auto& x : as_list(j)) items.push_back(decode(x, t.inner()));
      return Value::tuple(std::move(items));
    }
    case Type::Kind::Set: {
      ValueVec items;
      for (const auto& x : as_list(j)) items.push_back(decode(x, t.inner()));
      return Value::set(std::move(items));
    }
    case Type::Kind::Tuple: {
      const auto& items = as_list(j);
      if (items.size() != t.args.size()) bad("tupla de longitud distinta");
      ValueVec values;
      for (size_t k = 0; k < items.size(); ++k) values.push_back(decode(items[k], *t.args[k]));
      return Value::tuple(std::move(values));
    }
    case Type::Kind::Map: {
      ValueVec pairs;
      for (const auto& kv : as_list(j)) {
        const auto& p = as_list(kv);
        if (p.size() != 2) bad("se esperaba un par [clave, valor]");
        pairs.push_back(decode(p[0], *t.args[0]));
        pairs.push_back(decode(p[1], *t.args[1]));
      }
      return Value::map(std::move(pairs));
    }
    case Type::Kind::Zone:
    case Type::Kind::Bag: {
      const Json& raw = j.is_object() ? j.at("items") : j;
      ValueVec values;
      for (const auto& x : as_list(raw)) values.push_back(decode(x, t.inner()));
      ByteVec faces(values.size(), 0);
      return Value::zone(std::move(values), std::move(faces), t.kind == Type::Kind::Zone);
    }
    case Type::Kind::Grid:
      break;
  }
  bad("no se puede decodificar " + describe(t));
}

// --- Valor → JSON ------------------------------------------------------------------------------

Json TypeTable::to_json(const Value& v) const {
  switch (v.tag) {
    case Tag::None:
      return Json(nullptr);
    case Tag::Bool:
      return Json(v.i != 0);
    case Tag::Int:
      return Json(v.i);
    case Tag::Rat:
      return Json(static_cast<RatObj*>(v.p)->r.str());
    case Tag::Text:
      return Json(v.as_text());
    case Tag::Enum:
      return Json(enums_.at(v.x).values.at(static_cast<size_t>(v.i)));
    case Tag::Cell:
      return Json(JsonArray{Json(v.cell_row()), Json(v.cell_col())});
    case Tag::Tuple:
    case Tag::Set: {
      JsonArray items;
      const ArrayObj* a = v.arr();
      items.reserve(a->n);
      for (uint32_t k = 0; k < a->n; ++k) items.push_back(to_json(a->items()[k]));
      return Json(std::move(items));
    }
    case Tag::Struct: {
      const ArrayObj* a = v.arr();
      const StructDecl& s = structs_.at(a->a);
      JsonObject fields;
      for (uint32_t k = 0; k < a->n; ++k) fields.emplace_back(s.fields[k], to_json(a->items()[k]));
      return Json(std::move(fields));
    }
    case Tag::Map: {
      JsonArray pairs;
      const ArrayObj* a = v.arr();
      for (uint32_t k = 0; k + 1 < a->n; k += 2) {
        pairs.push_back(Json(JsonArray{to_json(a->items()[k]), to_json(a->items()[k + 1])}));
      }
      return Json(std::move(pairs));
    }
    case Tag::Zone: {
      JsonArray items;
      const ArrayObj* a = v.arr();
      for (uint32_t k = 0; k < a->n; ++k) items.push_back(to_json(a->items()[k]));
      JsonObject zone;
      zone.emplace_back("size", Json(int64_t(a->n)));
      zone.emplace_back("items", Json(std::move(items)));
      return Json(std::move(zone));
    }
    case Tag::Grid: {
      const ArrayObj* a = v.arr();
      JsonArray rows;
      for (uint32_t r = 0; r < a->b; ++r) {
        JsonArray row;
        for (uint32_t c = 0; c < a->a; ++c) row.push_back(to_json(a->items()[r * a->a + c]));
        rows.push_back(Json(std::move(row)));
      }
      return Json(std::move(rows));
    }
  }
  return Json(nullptr);
}

void TypeTable::to_json_into(const Value& v, std::string& out) const {
  switch (v.tag) {
    case Tag::None:
      out += "null";
      return;
    case Tag::Bool:
      out += v.i ? "true" : "false";
      return;
    case Tag::Int: {
      char buf[24];
      auto [end, ec] = std::to_chars(buf, buf + sizeof buf, v.i);
      out.append(buf, end);
      return;
    }
    case Tag::Rat:
      json_quote(out, static_cast<RatObj*>(v.p)->r.str());
      return;
    case Tag::Text:
      json_quote(out, v.as_text());
      return;
    case Tag::Enum:
      json_quote(out, enums_.at(v.x).values.at(static_cast<size_t>(v.i)));
      return;
    case Tag::Cell: {
      out += '[';
      to_json_into(Value::integer(v.cell_row()), out);
      out += ',';
      to_json_into(Value::integer(v.cell_col()), out);
      out += ']';
      return;
    }
    case Tag::Tuple:
    case Tag::Set: {
      const ArrayObj* a = v.arr();
      out += '[';
      for (uint32_t k = 0; k < a->n; ++k) {
        if (k) out += ',';
        to_json_into(a->items()[k], out);
      }
      out += ']';
      return;
    }
    case Tag::Struct: {
      const ArrayObj* a = v.arr();
      const StructDecl& s = structs_.at(a->a);
      // Claves ordenadas, como el JSON canónico.
      std::vector<uint32_t> order(a->n);
      for (uint32_t k = 0; k < a->n; ++k) order[k] = k;
      std::sort(order.begin(), order.end(),
                [&](uint32_t x, uint32_t y) { return s.fields[x] < s.fields[y]; });
      out += '{';
      bool first = true;
      for (uint32_t k : order) {
        if (!first) out += ',';
        first = false;
        json_quote(out, s.fields[k]);
        out += ':';
        to_json_into(a->items()[k], out);
      }
      out += '}';
      return;
    }
    case Tag::Map: {
      const ArrayObj* a = v.arr();
      out += '[';
      for (uint32_t k = 0; k + 1 < a->n; k += 2) {
        if (k) out += ',';
        out += '[';
        to_json_into(a->items()[k], out);
        out += ',';
        to_json_into(a->items()[k + 1], out);
        out += ']';
      }
      out += ']';
      return;
    }
    case Tag::Zone: {
      const ArrayObj* a = v.arr();
      out += "{\"items\":[";
      for (uint32_t k = 0; k < a->n; ++k) {
        if (k) out += ',';
        to_json_into(a->items()[k], out);
      }
      out += "],\"size\":";
      to_json_into(Value::integer(a->n), out);
      out += '}';
      return;
    }
    case Tag::Grid: {
      const ArrayObj* a = v.arr();
      out += '[';
      for (uint32_t r = 0; r < a->b; ++r) {
        if (r) out += ',';
        out += '[';
        for (uint32_t c = 0; c < a->a; ++c) {
          if (c) out += ',';
          to_json_into(a->items()[r * a->a + c], out);
        }
        out += ']';
      }
      out += ']';
      return;
    }
  }
}

std::string TypeTable::describe(const Type& t) const {
  switch (t.kind) {
    case Type::Kind::Bool:
      return "Bool";
    case Type::Kind::Int:
      return "Int";
    case Type::Kind::Real:
      return "Real";
    case Type::Kind::Text:
      return "Text";
    case Type::Kind::Seat:
      return "Seat";
    case Type::Kind::Cell:
      return "Cell";
    case Type::Kind::Enum:
      return enums_.at(t.id).name;
    case Type::Kind::Struct:
      return structs_.at(t.id).name;
    case Type::Kind::Grid:
      return "grid of " + describe(t.inner());
    default: {
      static const char* names[] = {"option", "list", "set", "map", "tuple", "per_player",
                                    "zone", "bag"};
      std::string out = names[static_cast<int>(t.kind) - static_cast<int>(Type::Kind::Option)];
      out += "<";
      for (size_t k = 0; k < t.args.size(); ++k) {
        if (k) out += ", ";
        out += describe(*t.args[k]);
      }
      return out + ">";
    }
  }
}

std::string TypeTable::repr(const Value& v) const {
  switch (v.tag) {
    case Tag::None:
      return "None";
    case Tag::Bool:
      return v.i ? "True" : "False";
    case Tag::Enum:
      return enums_.at(v.x).name + "." + enums_.at(v.x).values.at(static_cast<size_t>(v.i));
    case Tag::Text: {
      std::string out;
      json_quote(out, v.as_text());
      out.front() = '\'';
      out.back() = '\'';
      return out;
    }
    default:
      return to_json(v).dump();
  }
}

}  // namespace gh
