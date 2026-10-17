// SPDX-License-Identifier: Apache-2.0
// Tipos de la IR ya analizados y tabla de enumerados y structs (como `TypeTable` en Python):
// conversión JSON → valor (acciones, parámetros, replays) y valor → JSON (vistas, eventos).
#pragma once

#include <memory>
#include <string>
#include <unordered_map>
#include <variant>
#include <vector>

#include "gamehub/json.hpp"
#include "gamehub/value.hpp"

namespace gh {

struct Type;
using TypeRef = std::shared_ptr<const Type>;

struct Type {
  enum class Kind : uint8_t {
    Bool,
    Int,
    Real,
    Text,
    Seat,
    Cell,
    Enum,
    Struct,
    Option,
    List,
    Set,
    Map,
    Tuple,
    PerPlayer,
    Zone,
    Bag,
    Grid,
  };
  Kind kind;
  uint32_t id = 0;            // enum / struct
  std::vector<TypeRef> args;  // constructores
  // Rejilla: dimensiones constantes, o el nombre del parámetro que las da.
  std::variant<int64_t, std::string> width, height;

  const Type& inner() const { return *args.at(0); }
  bool is_prim() const { return kind <= Kind::Cell; }
};

struct EnumDecl {
  std::string name;
  std::vector<std::string> values;
};

struct StructDecl {
  std::string name;
  std::vector<std::string> fields;
  std::vector<TypeRef> types;
  int field_index(const std::string& field) const;
};

class TypeTable {
 public:
  TypeTable() = default;
  explicit TypeTable(const Json& decls);

  TypeRef parse(const Json& raw) const;

  const std::vector<EnumDecl>& enums() const { return enums_; }
  const std::vector<StructDecl>& structs() const { return structs_; }
  int enum_id(const std::string& name) const;    // -1 si no existe
  int struct_id(const std::string& name) const;  // -1 si no existe
  Value enum_value(const std::string& type, const std::string& name) const;

  // JSON → valor, validando la forma (lanza std::invalid_argument con el motivo).
  Value decode(const Json& j, const Type& t) const;
  // Valor → JSON (los valores no se autodescriben: hacen falta los nombres de la tabla).
  Json to_json(const Value& v) const;
  void to_json_into(const Value& v, std::string& out) const;  // directamente como texto

  std::string describe(const Type& t) const;
  std::string repr(const Value& v) const;  // para los mensajes de error

 private:
  std::vector<EnumDecl> enums_;      // ordenados por nombre (ids)
  std::vector<StructDecl> structs_;  // ordenados por nombre (ids)
  std::unordered_map<std::string, int> enum_ids_, struct_ids_;
};

}  // namespace gh
