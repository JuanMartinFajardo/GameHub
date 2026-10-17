// SPDX-License-Identifier: Apache-2.0
#include "gamehub/value.hpp"

#include <algorithm>

#include "gamehub/pool.hpp"

namespace gh {

// --- Memoria -----------------------------------------------------------------------------------

namespace {

size_t array_bytes(uint32_t n, bool with_faces) {
  size_t bytes = sizeof(ArrayObj) + size_t(n) * sizeof(Value) + (with_faces ? n : 0);
  return (bytes + 15) & ~size_t(15);
}

}  // namespace

Value Value::alloc_array(Tag tag, uint32_t n, bool with_faces) {
  void* mem = pool_alloc(array_bytes(n, with_faces));
  auto* obj = new (mem) ArrayObj;
  obj->rc = 1;
  obj->n = n;
  obj->a = 0;
  obj->b = 0;
  obj->hash = 0;
  obj->hash2 = 0;
  Value* items = obj->items();
  for (uint32_t k = 0; k < n; ++k) new (items + k) Value();
  if (with_faces) std::memset(obj->faces(), 0, n);
  Value v;
  v.tag = tag;
  v.p = obj;
  return v;
}

void free_obj(Tag tag, Obj* obj) {
  switch (tag) {
    case Tag::Rat:
      delete static_cast<RatObj*>(obj);
      return;
    case Tag::Text:
      delete static_cast<TextObj*>(obj);
      return;
    default: {
      auto* a = static_cast<ArrayObj*>(obj);
      Value* items = a->items();
      for (uint32_t k = 0; k < a->n; ++k) items[k].~Value();
      pool_free(a, array_bytes(a->n, tag == Tag::Zone));
    }
  }
}

ArrayObj* Value::unique_arr() {
  ArrayObj* obj = arr();
  if (obj->rc == 1) return obj;
  Value copy = alloc_array(tag, obj->n, tag == Tag::Zone);
  ArrayObj* c = copy.arr();
  c->a = obj->a;
  c->b = obj->b;
  c->hash = obj->hash;
  c->hash2 = obj->hash2;
  const Value* src = obj->items();
  Value* dst = c->items();
  for (uint32_t k = 0; k < obj->n; ++k) dst[k] = src[k];
  if (tag == Tag::Zone) std::memcpy(c->faces(), obj->faces(), obj->n);
  *this = std::move(copy);
  return c;
}

// --- Construcción ------------------------------------------------------------------------------

Value Value::cell(int64_t r, int64_t c) {
  if (r >= INT32_MIN && r <= INT32_MAX && c >= INT32_MIN && c <= INT32_MAX) {
    Value v;
    v.tag = Tag::Cell;
    v.x = static_cast<uint32_t>(static_cast<int32_t>(r));
    v.i = c;
    return v;
  }
  return tuple(ValueVec{integer(r), integer(c)});
}

Value Value::number(const Rational& r) {
  if (r.den == 1) return integer(r.num);
  auto* obj = new RatObj;
  obj->rc = 1;
  obj->r = r;
  Value v;
  v.tag = Tag::Rat;
  v.p = obj;
  return v;
}

Value Value::text(std::string_view s) {
  auto* obj = new TextObj;
  obj->rc = 1;
  obj->s = std::string(s);
  Value v;
  v.tag = Tag::Text;
  v.p = obj;
  return v;
}

Value Value::tuple(std::span<const Value> items) {
  Value v = alloc_array(Tag::Tuple, static_cast<uint32_t>(items.size()));
  Value* dst = v.arr()->items();
  for (size_t k = 0; k < items.size(); ++k) dst[k] = items[k];
  return v;
}

Value Value::tuple(ValueVec&& items) {
  Value v = alloc_array(Tag::Tuple, static_cast<uint32_t>(items.size()));
  Value* dst = v.arr()->items();
  for (size_t k = 0; k < items.size(); ++k) dst[k] = std::move(items[k]);
  return v;
}

Value Value::structure(uint32_t type, ValueVec&& fields) {
  Value v = alloc_array(Tag::Struct, static_cast<uint32_t>(fields.size()));
  v.arr()->a = type;
  Value* dst = v.arr()->items();
  for (size_t k = 0; k < fields.size(); ++k) dst[k] = std::move(fields[k]);
  return v;
}

Value Value::set(ValueVec&& items) {
  std::stable_sort(items.begin(), items.end(), canonical_less);
  ValueVec unique;
  unique.reserve(items.size());
  for (auto& x : items) {
    if (unique.empty() || !equals(unique.back(), x)) unique.push_back(std::move(x));
  }
  Value v = alloc_array(Tag::Set, static_cast<uint32_t>(unique.size()));
  Value* dst = v.arr()->items();
  for (size_t k = 0; k < unique.size(); ++k) dst[k] = std::move(unique[k]);
  return v;
}

Value Value::map(ValueVec&& pairs) {
  // dict(pares): una clave repetida se queda con el último valor; después, orden por clave.
  size_t count = pairs.size() / 2;
  PoolVec<size_t> order(count);
  for (size_t k = 0; k < count; ++k) order[k] = k;
  std::stable_sort(order.begin(), order.end(), [&](size_t a, size_t b) {
    return compare_canonical(pairs[2 * a], pairs[2 * b]) < 0;
  });
  PoolVec<size_t> kept;
  for (size_t k : order) {
    if (!kept.empty() && equals(pairs[2 * kept.back()], pairs[2 * k])) {
      kept.back() = k;  // el último par con esa clave gana
    } else {
      kept.push_back(k);
    }
  }
  Value v = alloc_array(Tag::Map, static_cast<uint32_t>(2 * kept.size()));
  Value* dst = v.arr()->items();
  for (size_t j = 0; j < kept.size(); ++j) {
    dst[2 * j] = std::move(pairs[2 * kept[j]]);
    dst[2 * j + 1] = std::move(pairs[2 * kept[j] + 1]);
  }
  return v;
}

Value Value::zone(ValueVec&& values, ByteVec&& faces, bool ordered) {
  size_t n = values.size();
  PoolVec<size_t> order(n);
  for (size_t k = 0; k < n; ++k) order[k] = k;
  if (!ordered) {
    // Las bolsas, siempre en orden canónico de (valor, cara).
    std::stable_sort(order.begin(), order.end(), [&](size_t a, size_t b) {
      int c = compare_canonical(values[a], values[b]);
      if (c != 0) return c < 0;
      return faces[a] < faces[b];
    });
  }
  Value v = alloc_array(Tag::Zone, static_cast<uint32_t>(n), true);
  ArrayObj* obj = v.arr();
  obj->a = ordered ? 1 : 0;
  for (size_t k = 0; k < n; ++k) {
    obj->items()[k] = std::move(values[order[k]]);
    obj->faces()[k] = faces[order[k]] ? 1 : 0;
  }
  return v;
}

Value Value::grid(uint32_t width, uint32_t height, ValueVec&& cells) {
  Value v = alloc_array(Tag::Grid, static_cast<uint32_t>(cells.size()));
  v.arr()->a = width;
  v.arr()->b = height;
  Value* dst = v.arr()->items();
  for (size_t k = 0; k < cells.size(); ++k) dst[k] = std::move(cells[k]);
  return v;
}

// --- Igualdad ----------------------------------------------------------------------------------

namespace {

bool tuple_equals(const Value& a, const Value& b) {
  size_t n = a.tuple_size();
  if (n != b.tuple_size()) return false;
  if (a.tag == Tag::Cell && b.tag == Tag::Cell) return a.x == b.x && a.i == b.i;
  for (size_t k = 0; k < n; ++k) {
    if (!equals(a.tuple_at(k), b.tuple_at(k))) return false;
  }
  return true;
}

bool items_equal(const ArrayObj* a, const ArrayObj* b) {
  if (a == b) return true;
  if (a->n != b->n || a->a != b->a || a->b != b->b) return false;
  if (a->hash != 0 && b->hash != 0 && a->hash != b->hash) return false;
  const Value* x = a->items();
  const Value* y = b->items();
  for (uint32_t k = 0; k < a->n; ++k) {
    if (!equals(x[k], y[k])) return false;
  }
  return true;
}

}  // namespace

bool equals(const Value& a, const Value& b) {
  if (a.tag != b.tag) {
    if (a.is_tuple_like() && b.is_tuple_like()) return tuple_equals(a, b);
    // En Python, True == 1 y False == 0.
    if ((a.tag == Tag::Bool && b.tag == Tag::Int) || (a.tag == Tag::Int && b.tag == Tag::Bool)) {
      return a.i == b.i;
    }
    return false;
  }
  switch (a.tag) {
    case Tag::None:
      return true;
    case Tag::Bool:
    case Tag::Int:
      return a.i == b.i;
    case Tag::Enum:
    case Tag::Cell:
      return a.x == b.x && a.i == b.i;
    case Tag::Rat:
      return a.p == b.p || static_cast<RatObj*>(a.p)->r == static_cast<RatObj*>(b.p)->r;
    case Tag::Text:
      return a.p == b.p || a.as_text() == b.as_text();
    case Tag::Tuple:
    case Tag::Struct:
    case Tag::Set:
    case Tag::Map:
    case Tag::Grid:
      return items_equal(a.arr(), b.arr());
    case Tag::Zone: {
      if (!items_equal(a.arr(), b.arr())) return false;
      return std::memcmp(a.arr()->faces(), b.arr()->faces(), a.arr()->n) == 0;
    }
  }
  return false;
}

// --- Orden canónico ----------------------------------------------------------------------------

namespace {

// Primer elemento de `sort_key`.
int category(Tag t) {
  switch (t) {
    case Tag::None:
      return 0;
    case Tag::Bool:
      return 1;
    case Tag::Int:
    case Tag::Rat:
      return 2;
    case Tag::Text:
      return 3;
    case Tag::Enum:
      return 4;
    case Tag::Cell:
    case Tag::Tuple:
      return 5;
    case Tag::Struct:
      return 6;
    case Tag::Set:
      return 7;
    case Tag::Map:
      return 8;
    case Tag::Zone:
      return 9;
    case Tag::Grid:
      return 10;
  }
  return 11;
}

int cmp_int(int64_t a, int64_t b) { return (a > b) - (a < b); }

int compare_items(const Value* x, size_t nx, const Value* y, size_t ny) {
  size_t n = std::min(nx, ny);
  for (size_t k = 0; k < n; ++k) {
    int c = compare_canonical(x[k], y[k]);
    if (c != 0) return c;
  }
  return cmp_int(static_cast<int64_t>(nx), static_cast<int64_t>(ny));
}

}  // namespace

// Los nombres de los tipos (enum, struct) se comparan por su id, que el motor asigna en orden
// alfabético de nombre: así el orden coincide con el de Python, que compara los nombres.
int compare_canonical(const Value& a, const Value& b) {
  int ca = category(a.tag), cb = category(b.tag);
  if (ca != cb) return ca < cb ? -1 : 1;
  switch (a.tag) {
    case Tag::None:
      return 0;
    case Tag::Bool:
      return cmp_int(a.i, b.i);
    case Tag::Int:
    case Tag::Rat:
      if (a.tag == Tag::Int && b.tag == Tag::Int) return cmp_int(a.i, b.i);
      return a.as_rational().compare(b.as_rational());
    case Tag::Text: {
      int c = a.as_text().compare(b.as_text());
      return (c > 0) - (c < 0);
    }
    case Tag::Enum:
      if (a.x != b.x) return a.x < b.x ? -1 : 1;
      return cmp_int(a.i, b.i);
    case Tag::Cell:
    case Tag::Tuple: {
      if (a.tag == Tag::Cell && b.tag == Tag::Cell) {
        int c = cmp_int(a.cell_row(), b.cell_row());
        return c != 0 ? c : cmp_int(a.cell_col(), b.cell_col());
      }
      size_t na = a.tuple_size(), nb = b.tuple_size();
      size_t n = std::min(na, nb);
      for (size_t k = 0; k < n; ++k) {
        int c = compare_canonical(a.tuple_at(k), b.tuple_at(k));
        if (c != 0) return c;
      }
      return cmp_int(static_cast<int64_t>(na), static_cast<int64_t>(nb));
    }
    case Tag::Struct:
      if (a.arr()->a != b.arr()->a) return a.arr()->a < b.arr()->a ? -1 : 1;
      return compare_items(a.arr()->items(), a.arr()->n, b.arr()->items(), b.arr()->n);
    case Tag::Set:
      return compare_items(a.arr()->items(), a.arr()->n, b.arr()->items(), b.arr()->n);
    case Tag::Map: {
      // Tuplas de pares (clave, valor): lexicográfico por pares.
      const ArrayObj* x = a.arr();
      const ArrayObj* y = b.arr();
      size_t n = std::min(x->n, y->n);
      for (size_t k = 0; k < n; ++k) {
        int c = compare_canonical(x->items()[k], y->items()[k]);
        if (c != 0) return c;
      }
      return cmp_int(x->n, y->n);
    }
    case Tag::Zone: {
      const ArrayObj* x = a.arr();
      const ArrayObj* y = b.arr();
      if (x->a != y->a) return x->a < y->a ? -1 : 1;  // las bolsas (False) antes
      size_t n = std::min(x->n, y->n);
      for (size_t k = 0; k < n; ++k) {
        int c = compare_canonical(x->items()[k], y->items()[k]);
        if (c != 0) return c;
        if (x->faces()[k] != y->faces()[k]) return x->faces()[k] < y->faces()[k] ? -1 : 1;
      }
      return cmp_int(x->n, y->n);
    }
    case Tag::Grid: {
      const ArrayObj* x = a.arr();
      const ArrayObj* y = b.arr();
      if (x->a != y->a) return x->a < y->a ? -1 : 1;
      if (x->b != y->b) return x->b < y->b ? -1 : 1;
      return compare_items(x->items(), x->n, y->items(), y->n);
    }
  }
  return 0;
}

// --- Hash --------------------------------------------------------------------------------------

namespace {

uint64_t hash_bytes(std::string_view s) {
  uint64_t h = 0xcbf29ce484222325ULL;
  for (char c : s) {
    h ^= static_cast<uint8_t>(c);
    h *= 0x100000001b3ULL;
  }
  return mix64(h);
}

constexpr uint64_t SEED_TUPLE = 0x7475706c65ULL;
constexpr uint64_t SEED_STRUCT = 0x737472756374ULL;
constexpr uint64_t SEED_SET = 0x736574ULL;
constexpr uint64_t SEED_MAP = 0x6d6170ULL;
constexpr uint64_t SEED_ZONE = 0x7a6f6e65ULL;
constexpr uint64_t SEED_GRID = 0x67726964ULL;

uint64_t nonzero(uint64_t h) { return h == 0 ? 1 : h; }

uint64_t zone_item_hash(const ArrayObj* obj, size_t k) {
  return hash_value(obj->items()[k]) ^ (obj->faces()[k] ? 0x9e3779b97f4a7c15ULL : 0);
}

uint64_t compute_array_hash(Tag tag, const ArrayObj* obj) {
  uint64_t h = 0;
  switch (tag) {
    case Tag::Tuple:
      h = mix64(SEED_TUPLE ^ obj->n);
      break;
    case Tag::Struct:
      h = mix64(SEED_STRUCT ^ (uint64_t(obj->a) << 32) ^ obj->n);
      break;
    case Tag::Set:
      h = mix64(SEED_SET ^ obj->n);
      break;
    case Tag::Map:
      h = mix64(SEED_MAP ^ obj->n);
      break;
    case Tag::Zone:
      h = mix64(SEED_ZONE ^ (uint64_t(obj->a) << 32) ^ obj->n);
      for (uint32_t k = 0; k < obj->n; ++k) h ^= positional_hash(k, zone_item_hash(obj, k));
      return nonzero(h);
    case Tag::Grid:
      h = mix64(SEED_GRID ^ (uint64_t(obj->a) << 40) ^ (uint64_t(obj->b) << 20) ^ obj->n);
      break;
    default:
      break;
  }
  const Value* items = obj->items();
  for (uint32_t k = 0; k < obj->n; ++k) h ^= positional_hash(k, hash_value(items[k]));
  return nonzero(h);
}

}  // namespace

uint64_t hash_value(const Value& v) {
  switch (v.tag) {
    case Tag::None:
      return 0x6e6f6e65ULL;
    case Tag::Bool:
    case Tag::Int:
      return mix64(static_cast<uint64_t>(v.i));
    case Tag::Enum:
      return mix64((uint64_t(v.x) << 40) ^ static_cast<uint64_t>(v.i) ^ 0x656e756dULL);
    case Tag::Cell:
      // El mismo hash que la tupla de sus dos enteros.
      return nonzero(mix64(SEED_TUPLE ^ 2) ^ positional_hash(0, mix64(v.cell_row())) ^
                     positional_hash(1, mix64(v.cell_col())));
    case Tag::Rat: {
      const Rational& r = static_cast<RatObj*>(v.p)->r;
      return mix64(mix64(static_cast<uint64_t>(r.num)) ^ static_cast<uint64_t>(r.den));
    }
    case Tag::Text:
      return hash_bytes(v.as_text());
    default: {
      ArrayObj* obj = v.arr();
      if (obj->hash == 0) obj->hash = compute_array_hash(v.tag, obj);
      return obj->hash;
    }
  }
}

void set_item(ArrayObj* obj, size_t k, Value value) {
  Value& slot = obj->items()[k];
  obj->hash2 = 0;
  // Un hash en caché de 1 puede venir de `nonzero(0)`: no se actualiza, se recalculará.
  if (obj->hash > 1) {
    obj->hash ^= positional_hash(k, hash_value(slot)) ^ positional_hash(k, hash_value(value));
  } else {
    obj->hash = 0;
  }
  slot = std::move(value);
}

// --- Segundo hash ------------------------------------------------------------------------------

namespace {

inline uint64_t mix64b(uint64_t z) {
  // El finalizador de MurmurHash3 (constantes distintas de splitmix64).
  z ^= z >> 33;
  z *= 0xff51afd7ed558ccdULL;
  z ^= z >> 33;
  z *= 0xc4ceb9fe1a85ec53ULL;
  z ^= z >> 33;
  return z;
}

inline uint64_t positional2(size_t index, uint64_t h) {
  return mix64b(h + 0x2545f4914f6cdd1dULL * (index + 7));
}

uint64_t compute_hash2(Tag tag, const ArrayObj* obj) {
  uint64_t h = mix64b(0x68617368322dULL ^ (uint64_t(static_cast<uint8_t>(tag)) << 56) ^
                      (uint64_t(obj->a) << 32) ^ (uint64_t(obj->b) << 16) ^ obj->n);
  if (tag == Tag::Tuple) h = mix64b(0x7475706c652dULL ^ obj->n);  // igual que una casilla
  const Value* items = obj->items();
  for (uint32_t k = 0; k < obj->n; ++k) {
    uint64_t e = hash_value2(items[k]);
    if (tag == Tag::Zone && obj->faces()[k]) e ^= 0x632d6661636521ULL;
    h ^= positional2(k, e);
  }
  return h == 0 ? 1 : h;
}

}  // namespace

uint64_t hash_value2(const Value& v) {
  switch (v.tag) {
    case Tag::None:
      return 0x4e6f6e6532ULL;
    case Tag::Bool:
    case Tag::Int:
      return mix64b(static_cast<uint64_t>(v.i) ^ 0x696e7432ULL);
    case Tag::Enum:
      return mix64b((uint64_t(v.x) << 44) ^ static_cast<uint64_t>(v.i) ^ 0x656e756d32ULL);
    case Tag::Cell: {
      uint64_t h = mix64b(0x7475706c652dULL ^ 2);
      h ^= positional2(0, mix64b(static_cast<uint64_t>(v.cell_row()) ^ 0x696e7432ULL));
      h ^= positional2(1, mix64b(static_cast<uint64_t>(v.cell_col()) ^ 0x696e7432ULL));
      return h == 0 ? 1 : h;
    }
    case Tag::Rat: {
      const Rational& r = static_cast<RatObj*>(v.p)->r;
      return mix64b(mix64b(static_cast<uint64_t>(r.num)) + static_cast<uint64_t>(r.den));
    }
    case Tag::Text: {
      uint64_t h = 0x84222325cbf29ce4ULL;
      for (char c : v.as_text()) h = (h ^ static_cast<uint8_t>(c)) * 0x100000001b3ULL;
      return mix64b(h);
    }
    default: {
      ArrayObj* obj = v.arr();
      if (obj->hash2 == 0) obj->hash2 = compute_hash2(v.tag, obj);
      return obj->hash2;
    }
  }
}

size_t utf8_length(std::string_view s) {
  size_t n = 0;
  for (char c : s) {
    if ((static_cast<uint8_t>(c) & 0xC0) != 0x80) ++n;
  }
  return n;
}

}  // namespace gh
