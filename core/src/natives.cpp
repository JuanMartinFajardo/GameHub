// SPDX-License-Identifier: Apache-2.0
// Valores ↔ palabras i32 (ABI gamehub-native/1), como `Codec` en gamehub.engine.natives.
#include "gamehub/natives.hpp"

#include <limits>

#include "gamehub/errors.hpp"

namespace gh {

namespace {

NativeHost* g_host = nullptr;

using Words = std::vector<int32_t>;

bool word(int64_t x, Words& out) {
  if (x < std::numeric_limits<int32_t>::min() || x > std::numeric_limits<int32_t>::max()) {
    return false;
  }
  out.push_back(static_cast<int32_t>(x));
  return true;
}

bool encode(const Value& v, const Type& t, const TypeTable& types, Words& out) {
  using K = Type::Kind;
  switch (t.kind) {
    case K::Bool:
      if (v.tag != Tag::Bool) return false;
      out.push_back(v.truthy() ? 1 : 0);
      return true;
    case K::Int:
    case K::Seat:
    case K::Real:
      // Como `_word` de Python: solo enteros (un booleano o un racional no caben).
      return v.tag == Tag::Int && word(v.i, out);
    case K::Text:
      return false;
    case K::Cell:
      if (!v.is_tuple_like() || v.tuple_size() != 2) return false;
      for (size_t k = 0; k < 2; ++k) {
        Value x = v.tuple_at(k);
        if (x.tag != Tag::Int || !word(x.i, out)) return false;
      }
      return true;
    case K::Enum:
      if (v.tag != Tag::Enum) return false;
      out.push_back(static_cast<int32_t>(v.i));
      return true;
    case K::Struct: {
      const StructDecl& decl = types.structs()[t.id];
      if (v.tag != Tag::Struct || v.arr()->n != decl.types.size()) return false;
      for (size_t k = 0; k < decl.types.size(); ++k) {
        if (!encode(v.arr()->items()[k], *decl.types[k], types, out)) return false;
      }
      return true;
    }
    case K::Tuple: {
      if (!v.is_tuple_like() || v.tuple_size() != t.args.size()) return false;
      for (size_t k = 0; k < t.args.size(); ++k) {
        if (!encode(v.tuple_at(k), *t.args[k], types, out)) return false;
      }
      return true;
    }
    case K::List: {
      if (!v.is_tuple_like()) return false;
      size_t n = v.tuple_size();
      if (!word(static_cast<int64_t>(n), out)) return false;
      for (size_t k = 0; k < n; ++k) {
        if (!encode(v.tuple_at(k), t.inner(), types, out)) return false;
      }
      return true;
    }
    case K::Option:
      if (v.is_none()) {
        out.push_back(0);
        return true;
      }
      out.push_back(1);
      return encode(v, t.inner(), types, out);
    default:
      throw RuleError("un plugin nativo no admite el tipo " + types.describe(t));
  }
}

struct Decoder {
  const int32_t* words;
  size_t n;
  size_t i = 0;
  const TypeTable& types;

  int32_t take() {
    if (i >= n) throw RuleError("el plugin nativo devolvió un resultado incompleto");
    return words[i++];
  }

  Value decode(const Type& t) {
    using K = Type::Kind;
    switch (t.kind) {
      case K::Bool:
        return Value::boolean(take() != 0);
      case K::Int:
      case K::Seat:
      case K::Real:
        return Value::integer(take());
      case K::Cell: {
        int64_t r = take();
        int64_t c = take();
        return Value::cell(r, c);
      }
      case K::Enum: {
        const EnumDecl& decl = types.enums()[t.id];
        int32_t w = take();
        if (w < 0 || static_cast<size_t>(w) >= decl.values.size()) {
          throw RuleError("el plugin nativo devolvió un " + decl.name + " inválido (" +
                          std::to_string(w) + ")");
        }
        return Value::enumeration(t.id, w);
      }
      case K::Struct: {
        const StructDecl& decl = types.structs()[t.id];
        ValueVec fields;
        for (const auto& ft : decl.types) fields.push_back(decode(*ft));
        return Value::structure(t.id, std::move(fields));
      }
      case K::Tuple: {
        ValueVec items;
        for (const auto& a : t.args) items.push_back(decode(*a));
        return Value::tuple(std::move(items));
      }
      case K::List: {
        int32_t count = take();
        ValueVec items;
        for (int32_t k = 0; k < count; ++k) items.push_back(decode(t.inner()));
        return Value::tuple(std::move(items));
      }
      case K::Option:
        if (take() == 0) return Value::none();
        return decode(t.inner());
      default:
        throw RuleError("un plugin nativo no admite el tipo " + types.describe(t));
    }
  }
};

}  // namespace

void set_native_host(NativeHost* host) { g_host = host; }
NativeHost* native_host() { return g_host; }

bool call_native(const NativeFn& fn, const TypeTable& types, const Value* args, Value& result,
                 const std::string& native_id) {
  NativeHost* host = fn.host;
  if (host == nullptr || fn.handle < 0) return false;
  Words in;
  for (size_t k = 0; k < fn.params.size(); ++k) {
    if (!encode(args[k], *fn.params[k], types, in)) return false;
  }
  const std::string module = native_id.substr(0, native_id.rfind('.'));
  if (in.size() > NATIVE_BUFFER_WORDS / 2) {
    throw RuleError("plugin nativo " + module + ".wasm: la entrada es demasiado grande");
  }
  Words out(NATIVE_BUFFER_WORDS / 2);
  int n = host->call(fn.handle, in.data(), static_cast<int>(in.size()), out.data(),
                     static_cast<int>(out.size()));
  if (n < 0 || n > NATIVE_BUFFER_WORDS / 2) {
    throw RuleError("el plugin nativo " + module + ".wasm devolvió un error (" +
                    std::to_string(n) + ")");
  }
  Decoder d{out.data(), static_cast<size_t>(n), 0, types};
  result = d.decode(*fn.returns);
  if (d.i != d.n) {
    throw RuleError("el plugin nativo " + module + ".wasm devolvió palabras de más");
  }
  return true;
}

}  // namespace gh
