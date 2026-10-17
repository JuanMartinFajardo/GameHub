// SPDX-License-Identifier: Apache-2.0
// JSON mínimo: lectura de la IR, vistas, eventos y la forma canónica (RFC 8785 en el subconjunto
// que usa GameHub: sin números en coma flotante) que coincide byte a byte con
// `json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False)` de Python.
#pragma once

#include <cstdint>
#include <initializer_list>
#include <string>
#include <string_view>
#include <utility>
#include <variant>
#include <vector>

namespace gh {

class Json;
using JsonArray = std::vector<Json>;
using JsonObject = std::vector<std::pair<std::string, Json>>;

class Json {
 public:
  enum class Kind : uint8_t { Null, Bool, Int, String, Array, Object };

  Json() : v_(nullptr) {}
  Json(std::nullptr_t) : v_(nullptr) {}
  Json(bool b) : v_(b) {}
  Json(int i) : v_(static_cast<int64_t>(i)) {}
  Json(int64_t i) : v_(i) {}
  Json(const char* s) : v_(std::string(s)) {}
  Json(std::string s) : v_(std::move(s)) {}
  Json(std::string_view s) : v_(std::string(s)) {}
  Json(JsonArray a) : v_(std::move(a)) {}
  Json(JsonObject o) : v_(std::move(o)) {}

  static Json array() { return Json(JsonArray{}); }
  static Json object() { return Json(JsonObject{}); }
  static Json parse(std::string_view text);

  Kind kind() const { return static_cast<Kind>(v_.index()); }
  bool is_null() const { return kind() == Kind::Null; }
  bool is_bool() const { return kind() == Kind::Bool; }
  bool is_int() const { return kind() == Kind::Int; }
  bool is_string() const { return kind() == Kind::String; }
  bool is_array() const { return kind() == Kind::Array; }
  bool is_object() const { return kind() == Kind::Object; }

  bool as_bool() const;
  int64_t as_int() const;
  const std::string& as_string() const;
  const JsonArray& as_array() const;
  JsonArray& as_array();
  const JsonObject& as_object() const;
  JsonObject& as_object();

  // Objetos: búsqueda lineal (los objetos de la IR son pequeños).
  const Json* find(std::string_view key) const;
  bool contains(std::string_view key) const { return find(key) != nullptr; }
  const Json& at(std::string_view key) const;
  const Json& operator[](std::string_view key) const { return at(key); }
  // Añade o reemplaza una clave (conserva el orden de inserción).
  void set(std::string_view key, Json value);
  // Arrays.
  const Json& at(size_t i) const;
  const Json& operator[](size_t i) const { return at(i); }
  size_t size() const;
  void push_back(Json value);

  // Forma canónica (claves ordenadas, sin espacios, UTF-8 sin escapar).
  std::string dump() const;
  void dump_to(std::string& out) const;

  bool operator==(const Json& other) const;
  bool operator!=(const Json& other) const { return !(*this == other); }

 private:
  std::variant<std::nullptr_t, bool, int64_t, std::string, JsonArray, JsonObject> v_;
};

// Escribe `s` como cadena JSON (con comillas) al estilo de Python con ensure_ascii=False.
void json_quote(std::string& out, std::string_view s);

}  // namespace gh
