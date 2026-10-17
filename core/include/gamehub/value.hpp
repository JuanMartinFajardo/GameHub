// SPDX-License-Identifier: Apache-2.0
// Valores del motor C++ (ADR-076).
//
// Un `Value` ocupa 16 bytes. Los valores pequeños van en línea (opcional vacío, booleanos,
// enteros, enumerados y casillas); el resto son objetos inmutables en el montón con conteo de
// referencias (no atómico: un estado pertenece a un hilo). Correspondencia con la IR y con los
// valores de Python (`gamehub.engine.values`):
//
// | IR                          | Tag            | Python                      |
// |-----------------------------|----------------|-----------------------------|
// | option vacío                | None           | None                        |
// | Bool                        | Bool           | bool                        |
// | Int, Seat, Real entero      | Int (int64)    | int                         |
// | Real no entero              | Rat            | Fraction                    |
// | Text                        | Text (UTF-8)   | str                         |
// | enum                        | Enum           | EnumValue                   |
// | Cell                        | Cell (en línea) o Tuple de 2 enteros | tuple     |
// | list, tuple, per_player     | Tuple          | tuple                       |
// | struct                      | Struct         | StructValue                 |
// | set / map                   | Set / Map      | SetValue / MapValue         |
// | zone / bag                  | Zone           | Zone                        |
// | grid                        | Grid           | Grid                        |
//
// Una casilla en línea se comporta en todo como la tupla de sus dos enteros (igualdad, orden,
// hash, iteración). El **orden canónico** es el de `sort_key` en Python.
//
// Cada contenedor guarda en caché su hash estructural, que se actualiza en O(1) al escribir una
// posición (XOR de hashes posicionales): es el hash de Zobrist automático de los estados.
#pragma once

#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <new>
#include <span>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include "gamehub/rational.hpp"

namespace gh {

enum class Tag : uint8_t {
  // En línea.
  None = 0,
  Bool,
  Int,
  Enum,
  Cell,
  // En el montón.
  Rat,
  Text,
  Tuple,
  Struct,
  Set,
  Map,
  Zone,
  Grid,
};

inline bool is_heap_tag(Tag t) { return t >= Tag::Rat; }

struct Value;

// Cabecera común de los objetos del montón.
struct Obj {
  uint32_t rc;
};

struct RatObj : Obj {
  Rational r;
};

struct TextObj : Obj {
  std::string s;
};

// Tupla, struct, conjunto, mapa (pares clave, valor seguidos), zona o rejilla: `n` valores
// seguidos de la cabecera (y, en las zonas, `n` bytes con la cara de cada elemento).
struct alignas(16) ArrayObj : Obj {
  uint32_t n;   // número de valores en `items`
  uint32_t a;   // struct: id del tipo; zona: 1 = ordenada; rejilla: ancho
  uint32_t b;   // rejilla: alto
  uint64_t hash;  // caché del hash estructural (0 = sin calcular)
  uint64_t pad_;

  Value* items() { return reinterpret_cast<Value*>(this + 1); }
  const Value* items() const { return reinterpret_cast<const Value*>(this + 1); }
  inline uint8_t* faces();
  inline const uint8_t* faces() const;
};
static_assert(sizeof(ArrayObj) == 32);

void free_obj(Tag tag, Obj* obj);

struct Value {
  Tag tag = Tag::None;
  uint32_t x = 0;  // enum: id del tipo; casilla: fila
  union {
    int64_t i;
    Obj* p;
  };

  Value() : i(0) {}
  ~Value() {
    if (is_heap_tag(tag)) release();
  }
  Value(const Value& o) : tag(o.tag), x(o.x), i(o.i) {
    if (is_heap_tag(tag)) ++p->rc;
  }
  Value(Value&& o) noexcept : tag(o.tag), x(o.x), i(o.i) {
    o.tag = Tag::None;
    o.i = 0;
  }
  Value& operator=(const Value& o) {
    if (this != &o) {
      if (is_heap_tag(o.tag)) ++o.p->rc;
      if (is_heap_tag(tag)) release();
      tag = o.tag;
      x = o.x;
      i = o.i;
    }
    return *this;
  }
  Value& operator=(Value&& o) noexcept {
    if (this != &o) {
      if (is_heap_tag(tag)) release();
      tag = o.tag;
      x = o.x;
      i = o.i;
      o.tag = Tag::None;
      o.i = 0;
    }
    return *this;
  }

  // --- Construcción -----------------------------------------------------------------------------
  static Value none() { return Value(); }
  static Value boolean(bool b) {
    Value v;
    v.tag = Tag::Bool;
    v.i = b ? 1 : 0;
    return v;
  }
  static Value integer(int64_t n) {
    Value v;
    v.tag = Tag::Int;
    v.i = n;
    return v;
  }
  static Value enumeration(uint32_t type, int64_t ordinal) {
    Value v;
    v.tag = Tag::Enum;
    v.x = type;
    v.i = ordinal;
    return v;
  }
  static Value cell(int64_t r, int64_t c);  // en línea si cabe en 32 bits; si no, una tupla
  static Value number(const Rational& r);   // Int si es entero
  static Value text(std::string_view s);
  static Value tuple(std::span<const Value> items);
  static Value tuple(std::vector<Value>&& items);
  static Value structure(uint32_t type, std::vector<Value>&& fields);
  static Value set(std::vector<Value>&& items);    // ordena y quita repetidos
  static Value map(std::vector<Value>&& pairs);    // k0, v0, k1, v1…; ordena (gana el último)
  static Value zone(std::vector<Value>&& values, std::vector<uint8_t>&& faces, bool ordered);
  static Value grid(uint32_t width, uint32_t height, std::vector<Value>&& cells);

  // Un objeto ArrayObj vacío de `n` valores (todos None) con la etiqueta dada.
  static Value alloc_array(Tag tag, uint32_t n, bool with_faces = false);

  // --- Consulta ---------------------------------------------------------------------------------
  bool is_none() const { return tag == Tag::None; }
  bool is_bool() const { return tag == Tag::Bool; }
  bool is_int() const { return tag == Tag::Int; }
  bool is_number() const { return tag == Tag::Int || tag == Tag::Rat; }
  bool truthy() const { return i != 0; }  // solo para Bool
  int64_t as_int() const { return i; }
  Rational as_rational() const {
    return tag == Tag::Int ? Rational::integer(i) : static_cast<RatObj*>(p)->r;
  }
  const std::string& as_text() const { return static_cast<TextObj*>(p)->s; }
  ArrayObj* arr() const { return static_cast<ArrayObj*>(p); }
  int64_t cell_row() const { return static_cast<int32_t>(x); }
  int64_t cell_col() const { return static_cast<int32_t>(i); }

  // Tuplas (incluidas las casillas en línea).
  bool is_tuple_like() const { return tag == Tag::Tuple || tag == Tag::Cell; }
  size_t tuple_size() const { return tag == Tag::Cell ? 2 : arr()->n; }
  Value tuple_at(size_t k) const {
    if (tag == Tag::Cell) return integer(k == 0 ? cell_row() : cell_col());
    return arr()->items()[k];
  }

  // Copia-al-escribir: el objeto pasa a ser exclusivo de este valor (lo copia si se comparte).
  ArrayObj* unique_arr();

 private:
  void release() {
    if (--p->rc == 0) free_obj(tag, p);
  }
};
static_assert(sizeof(Value) == 16);

inline uint8_t* ArrayObj::faces() { return reinterpret_cast<uint8_t*>(items() + n); }
inline const uint8_t* ArrayObj::faces() const {
  return reinterpret_cast<const uint8_t*>(items() + n);
}

// --- Operaciones -------------------------------------------------------------------------------

// Igualdad de Python (`==`): las casillas son tuplas y un booleano es igual a 0/1.
bool equals(const Value& a, const Value& b);
inline bool operator==(const Value& a, const Value& b) { return equals(a, b); }
// Orden canónico total (`sort_key`): -1, 0, 1.
int compare_canonical(const Value& a, const Value& b);
inline bool canonical_less(const Value& a, const Value& b) {
  return compare_canonical(a, b) < 0;
}
// Hash estructural (coherente con `equals`).
uint64_t hash_value(const Value& v);
// Mezcla de 64 bits (splitmix64).
inline uint64_t mix64(uint64_t z) {
  z += 0x9e3779b97f4a7c15ULL;
  z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ULL;
  z = (z ^ (z >> 27)) * 0x94d049bb133111ebULL;
  return z ^ (z >> 31);
}
// Contribución al hash de un elemento en una posición.
inline uint64_t positional_hash(size_t index, uint64_t element_hash) {
  return mix64(element_hash ^ (0x5851f42d4c957f2dULL * (index + 1)));
}
// Escribe `value` en la posición `k` de un contenedor exclusivo, manteniendo el hash en caché.
void set_item(ArrayObj* obj, size_t k, Value value);

// Número de puntos de código de un texto UTF-8 (`len` de Python).
size_t utf8_length(std::string_view s);

}  // namespace gh
