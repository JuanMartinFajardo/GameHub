// SPDX-License-Identifier: Apache-2.0
#include "gamehub/action_space.hpp"

#include <algorithm>

#include "gamehub/errors.hpp"

namespace gh {

namespace {

int64_t binomial(int64_t n, int64_t k) {
  if (k < 0 || k > n) return 0;
  k = std::min(k, n - k);
  __int128 r = 1;
  for (int64_t i = 1; i <= k; ++i) {
    r = r * (n - k + i) / i;
    if (r > INT64_MAX) throw IrError("espacio de acciones demasiado grande (más de 2^63)");
  }
  return static_cast<int64_t>(r);
}

Universe parse_universe(const GameDef& g, const Json& j) {
  Universe u;
  const std::string& kind = j["kind"].as_string();
  if (kind == "bool") {
    u.kind = Universe::Kind::Bool;
    u.size = 2;
  } else if (kind == "enum") {
    u.kind = Universe::Kind::Enum;
    int id = g.types.enum_id(j["type"].as_string());
    if (id < 0) throw IrError("enumerado desconocido en el espacio de acciones");
    u.type = static_cast<uint32_t>(id);
    for (const auto& o : j["ordinals"].as_array()) u.ordinals.push_back(o.as_int());
    u.size = static_cast<int64_t>(u.ordinals.size());
  } else if (kind == "int") {
    u.kind = Universe::Kind::Int;
    u.lo = j["lo"].as_int();
    u.hi = j["hi"].as_int();
    u.size = u.hi - u.lo + 1;
  } else if (kind == "cell") {
    u.kind = Universe::Kind::Cell;
    u.rows = j["rows"].as_int();
    u.cols = j["cols"].as_int();
    u.size = u.rows * u.cols;
  } else if (kind == "struct" || kind == "tuple") {
    u.kind = kind == "struct" ? Universe::Kind::Struct : Universe::Kind::Tuple;
    if (kind == "struct") {
      int id = g.types.struct_id(j["type"].as_string());
      if (id < 0) throw IrError("struct desconocido en el espacio de acciones");
      u.type = static_cast<uint32_t>(id);
    }
    for (const auto& p : j["parts"].as_array()) u.parts.push_back(parse_universe(g, p));
    u.strides.assign(u.parts.size(), 1);
    for (size_t i = u.parts.size(); i-- > 1;) u.strides[i - 1] = u.strides[i] * u.parts[i].size;
    u.size = 1;
    for (const auto& p : u.parts) u.size *= p.size;
  } else if (kind == "option") {
    u.kind = Universe::Kind::Option;
    u.parts.push_back(parse_universe(g, j["inner"]));
    u.size = 1 + u.parts[0].size;
  } else if (kind == "subset") {
    u.kind = Universe::Kind::Subset;
    u.parts.push_back(parse_universe(g, j["elem"]));
    u.lo = j["lo"].as_int();
    u.hi = j["hi"].as_int();
    int64_t n = u.parts[0].size;
    u.size = 0;
    for (int64_t k = std::max<int64_t>(u.lo, 0); k <= std::min(u.hi, n); ++k) u.size += binomial(n, k);
  } else {
    throw IrError("universo desconocido: " + kind);
  }
  return u;
}

}  // namespace

int64_t Universe::rank(const Value& v) const {
  switch (kind) {
    case Kind::Bool:
      return v.tag == Tag::Bool ? v.i : -1;
    case Kind::Enum: {
      if (v.tag != Tag::Enum || v.x != type) return -1;
      for (size_t k = 0; k < ordinals.size(); ++k) {
        if (ordinals[k] == v.i) return static_cast<int64_t>(k);
      }
      return -1;
    }
    case Kind::Int:
      return v.tag == Tag::Int && v.i >= lo && v.i <= hi ? v.i - lo : -1;
    case Kind::Cell: {
      if (!v.is_tuple_like() || v.tuple_size() != 2) return -1;
      Value r = v.tuple_at(0), c = v.tuple_at(1);
      if (r.tag != Tag::Int || c.tag != Tag::Int) return -1;
      if (r.i < 0 || r.i >= rows || c.i < 0 || c.i >= cols) return -1;
      return r.i * cols + c.i;
    }
    case Kind::Struct:
    case Kind::Tuple: {
      if (kind == Kind::Struct && (v.tag != Tag::Struct || v.arr()->a != type)) return -1;
      if (kind == Kind::Tuple && (!v.is_tuple_like() || v.tuple_size() != parts.size())) return -1;
      if (kind == Kind::Struct && v.arr()->n != parts.size()) return -1;
      int64_t total = 0;
      for (size_t k = 0; k < parts.size(); ++k) {
        Value item = kind == Kind::Struct ? v.arr()->items()[k] : v.tuple_at(k);
        int64_t r = parts[k].rank(item);
        if (r < 0) return -1;
        total += r * strides[k];
      }
      return total;
    }
    case Kind::Option:
      if (v.is_none()) return 0;
      {
        int64_t r = parts[0].rank(v);
        return r < 0 ? -1 : 1 + r;
      }
    case Kind::Subset: {
      if (!v.is_tuple_like()) return -1;
      std::vector<int64_t> ranks;
      for (size_t k = 0; k < v.tuple_size(); ++k) {
        int64_t r = parts[0].rank(v.tuple_at(k));
        if (r < 0) return -1;
        ranks.push_back(r);
      }
      std::sort(ranks.begin(), ranks.end());
      if (std::adjacent_find(ranks.begin(), ranks.end()) != ranks.end()) return -1;  // repetidos
      auto k = static_cast<int64_t>(ranks.size());
      int64_t n = parts[0].size;
      int64_t first = std::max<int64_t>(lo, 0);
      if (k < first || k > std::min(hi, n)) return -1;
      int64_t offset = 0;
      for (int64_t j = first; j < k; ++j) offset += binomial(n, j);
      for (size_t i = 0; i < ranks.size(); ++i) offset += binomial(ranks[i], static_cast<int64_t>(i) + 1);
      return offset;
    }
  }
  return -1;
}

Value Universe::unrank(int64_t k) const {
  switch (kind) {
    case Kind::Bool:
      return Value::boolean(k == 1);
    case Kind::Enum:
      return Value::enumeration(type, ordinals.at(static_cast<size_t>(k)));
    case Kind::Int:
      return Value::integer(lo + k);
    case Kind::Cell:
      return Value::cell(k / cols, k % cols);
    case Kind::Struct:
    case Kind::Tuple: {
      ValueVec items;
      for (size_t i = 0; i < parts.size(); ++i) {
        items.push_back(parts[i].unrank(k / strides[i]));
        k %= strides[i];
      }
      if (kind == Kind::Struct) return Value::structure(type, std::move(items));
      return Value::tuple(std::move(items));
    }
    case Kind::Option:
      return k == 0 ? Value::none() : parts[0].unrank(k - 1);
    case Kind::Subset: {
      int64_t n = parts[0].size;
      for (int64_t size = std::max<int64_t>(lo, 0); size <= std::min(hi, n); ++size) {
        int64_t block = binomial(n, size);
        if (k < block) {
          ValueVec values;
          for (int64_t i = size; i > 0; --i) {
            int64_t r = i - 1;
            while (binomial(r + 1, i) <= k) ++r;
            values.push_back(parts[0].unrank(r));
            k -= binomial(r, i);
          }
          std::stable_sort(values.begin(), values.end(), canonical_less);
          return Value::tuple(std::move(values));
        }
        k -= block;
      }
      throw IrError("número fuera del universo");
    }
  }
  return Value();
}

ActionSpace::ActionSpace(std::shared_ptr<const GameDef> game, const Json& spec)
    : game_(std::move(game)) {
  const GameDef& g = *game_;
  for (const auto& b : spec["blocks"].as_array()) {
    Block block;
    block.name = b["name"].as_string();
    block.offset = b["offset"].as_int();
    for (const auto& p : b["params"].as_array()) block.params.push_back(parse_universe(g, p["universe"]));
    block.strides.assign(block.params.size(), 1);
    for (size_t i = block.params.size(); i-- > 1;) {
      block.strides[i - 1] = block.strides[i] * block.params[i].size;
    }
    block.size = 1;
    for (const auto& u : block.params) block.size *= u.size;
    if (block.size != b["size"].as_int()) throw IrError("tamaño de bloque incoherente");
    blocks_.push_back(std::move(block));
  }
  size_ = spec["size"].as_int();
  nodes_.resize(g.nodes.size());
  for (const auto& [node_id, entries] : spec["nodes"].as_object()) {
    auto it = g.node_index.find(node_id);
    if (it == g.node_index.end()) throw IrError("nodo desconocido en el espacio de acciones");
    const NodeDef& node = g.node(it->second);
    for (const auto& e : entries.as_array()) {
      const std::string& name = e["action"].as_string();
      const ActionDef* def = nullptr;  // `pass` de una ventana (reservado: no es una acción declarada)
      if (!(name == "pass" && node.kind == NodeKind::Window)) {
        uint32_t id = g.action_name_id(name);
        def = id == UINT32_MAX ? nullptr : node.action(id);
        if (def == nullptr) throw IrError("acción desconocida en el espacio de acciones: " + name);
      }
      nodes_[static_cast<size_t>(it->second)].push_back(
          Entry{def, static_cast<size_t>(e["block"].as_int())});
    }
  }
}

int64_t ActionSpace::encode(int node, const Action& action) const {
  if (node < 0) return -1;
  for (const auto& e : nodes_[static_cast<size_t>(node)]) {
    if (e.def != action.def) continue;
    const Block& b = blocks_[e.block];
    int64_t total = b.offset;
    for (size_t k = 0; k < b.params.size(); ++k) {
      int64_t r = b.params[k].rank(action.args[k]);
      if (r < 0) return -1;
      total += r * b.strides[k];
    }
    return total;
  }
  return -1;
}

std::optional<Action> ActionSpace::decode(int node, int64_t id) const {
  if (node < 0) return std::nullopt;
  for (const auto& e : nodes_[static_cast<size_t>(node)]) {
    const Block& b = blocks_[e.block];
    if (id < b.offset || id >= b.offset + b.size) continue;
    int64_t k = id - b.offset;
    ValueVec args;
    for (size_t i = 0; i < b.params.size(); ++i) {
      args.push_back(b.params[i].unrank(k / b.strides[i]));
      k %= b.strides[i];
    }
    return Action{e.def, Args(args)};
  }
  return std::nullopt;
}

std::vector<int64_t> ActionSpace::legal_ids(const State& state, int seat) const {
  std::vector<int64_t> ids;
  int node = state.node();
  state.for_each_legal(seat, [&](const Action& a) {
    int64_t id = encode(node, a);
    if (id < 0) {
      throw RuleError("una acción legal queda fuera del espacio de acciones: " +
                      a.to_json(state.game()).dump());
    }
    ids.push_back(id);
    return true;
  });
  return ids;
}

}  // namespace gh
