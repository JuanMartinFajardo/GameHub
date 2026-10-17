// SPDX-License-Identifier: Apache-2.0
#include "gamehub/json.hpp"

#include <algorithm>
#include <charconv>

#include "gamehub/errors.hpp"

namespace gh {

namespace {

[[noreturn]] void type_error(const char* expected) {
  throw IrError(std::string("JSON: se esperaba ") + expected);
}

class Parser {
 public:
  explicit Parser(std::string_view text) : s_(text) {}

  Json parse_document() {
    Json v = parse_value(0);
    skip_ws();
    if (pos_ != s_.size()) fail("datos de más al final");
    return v;
  }

 private:
  std::string_view s_;
  size_t pos_ = 0;

  [[noreturn]] void fail(const std::string& what) {
    throw IrError("JSON inválido en la posición " + std::to_string(pos_) + ": " + what);
  }

  void skip_ws() {
    while (pos_ < s_.size()) {
      char c = s_[pos_];
      if (c == ' ' || c == '\n' || c == '\r' || c == '\t') {
        ++pos_;
      } else {
        break;
      }
    }
  }

  bool consume(std::string_view word) {
    if (s_.substr(pos_, word.size()) == word) {
      pos_ += word.size();
      return true;
    }
    return false;
  }

  Json parse_value(int depth) {
    if (depth > 512) fail("anidamiento excesivo");
    skip_ws();
    if (pos_ >= s_.size()) fail("fin inesperado");
    char c = s_[pos_];
    switch (c) {
      case '{':
        return parse_object(depth);
      case '[':
        return parse_array(depth);
      case '"':
        return Json(parse_string());
      case 't':
        if (consume("true")) return Json(true);
        break;
      case 'f':
        if (consume("false")) return Json(false);
        break;
      case 'n':
        if (consume("null")) return Json(nullptr);
        break;
      default:
        if (c == '-' || (c >= '0' && c <= '9')) return parse_number();
    }
    fail("valor inesperado");
  }

  Json parse_number() {
    size_t start = pos_;
    if (s_[pos_] == '-') ++pos_;
    while (pos_ < s_.size() && s_[pos_] >= '0' && s_[pos_] <= '9') ++pos_;
    if (pos_ < s_.size() && (s_[pos_] == '.' || s_[pos_] == 'e' || s_[pos_] == 'E')) {
      fail("los números en coma flotante no están permitidos");
    }
    int64_t value = 0;
    auto [ptr, ec] = std::from_chars(s_.data() + start, s_.data() + pos_, value);
    if (ec != std::errc() || ptr != s_.data() + pos_) fail("entero fuera de rango (64 bits)");
    return Json(value);
  }

  static void append_utf8(std::string& out, uint32_t cp) {
    if (cp < 0x80) {
      out += static_cast<char>(cp);
    } else if (cp < 0x800) {
      out += static_cast<char>(0xC0 | (cp >> 6));
      out += static_cast<char>(0x80 | (cp & 0x3F));
    } else if (cp < 0x10000) {
      out += static_cast<char>(0xE0 | (cp >> 12));
      out += static_cast<char>(0x80 | ((cp >> 6) & 0x3F));
      out += static_cast<char>(0x80 | (cp & 0x3F));
    } else {
      out += static_cast<char>(0xF0 | (cp >> 18));
      out += static_cast<char>(0x80 | ((cp >> 12) & 0x3F));
      out += static_cast<char>(0x80 | ((cp >> 6) & 0x3F));
      out += static_cast<char>(0x80 | (cp & 0x3F));
    }
  }

  uint32_t parse_hex4() {
    if (pos_ + 4 > s_.size()) fail("escape \\u incompleto");
    uint32_t cp = 0;
    for (int i = 0; i < 4; ++i) {
      char h = s_[pos_++];
      cp <<= 4;
      if (h >= '0' && h <= '9') {
        cp |= static_cast<uint32_t>(h - '0');
      } else if (h >= 'a' && h <= 'f') {
        cp |= static_cast<uint32_t>(h - 'a' + 10);
      } else if (h >= 'A' && h <= 'F') {
        cp |= static_cast<uint32_t>(h - 'A' + 10);
      } else {
        fail("escape \\u inválido");
      }
    }
    return cp;
  }

  std::string parse_string() {
    ++pos_;  // comilla de apertura
    std::string out;
    while (true) {
      if (pos_ >= s_.size()) fail("cadena sin cerrar");
      char c = s_[pos_++];
      if (c == '"') break;
      if (c != '\\') {
        if (static_cast<unsigned char>(c) < 0x20) fail("carácter de control en una cadena");
        out += c;
        continue;
      }
      if (pos_ >= s_.size()) fail("escape incompleto");
      char e = s_[pos_++];
      switch (e) {
        case '"':
          out += '"';
          break;
        case '\\':
          out += '\\';
          break;
        case '/':
          out += '/';
          break;
        case 'b':
          out += '\b';
          break;
        case 'f':
          out += '\f';
          break;
        case 'n':
          out += '\n';
          break;
        case 'r':
          out += '\r';
          break;
        case 't':
          out += '\t';
          break;
        case 'u': {
          uint32_t cp = parse_hex4();
          if (cp >= 0xD800 && cp < 0xDC00 && s_.substr(pos_, 2) == "\\u") {
            size_t save = pos_;
            pos_ += 2;
            uint32_t low = parse_hex4();
            if (low >= 0xDC00 && low < 0xE000) {
              cp = 0x10000 + ((cp - 0xD800) << 10) + (low - 0xDC00);
            } else {
              pos_ = save;
            }
          }
          append_utf8(out, cp);
          break;
        }
        default:
          fail("escape desconocido");
      }
    }
    return out;
  }

  Json parse_array(int depth) {
    ++pos_;
    JsonArray items;
    skip_ws();
    if (pos_ < s_.size() && s_[pos_] == ']') {
      ++pos_;
      return Json(std::move(items));
    }
    while (true) {
      items.push_back(parse_value(depth + 1));
      skip_ws();
      if (pos_ >= s_.size()) fail("array sin cerrar");
      char c = s_[pos_++];
      if (c == ']') break;
      if (c != ',') fail("se esperaba ',' o ']'");
    }
    return Json(std::move(items));
  }

  Json parse_object(int depth) {
    ++pos_;
    JsonObject members;
    skip_ws();
    if (pos_ < s_.size() && s_[pos_] == '}') {
      ++pos_;
      return Json(std::move(members));
    }
    while (true) {
      skip_ws();
      if (pos_ >= s_.size() || s_[pos_] != '"') fail("se esperaba una clave");
      std::string key = parse_string();
      skip_ws();
      if (pos_ >= s_.size() || s_[pos_] != ':') fail("se esperaba ':'");
      ++pos_;
      Json value = parse_value(depth + 1);
      // Como `json.loads`: una clave repetida se queda con el último valor.
      bool replaced = false;
      for (auto& [k, v] : members) {
        if (k == key) {
          v = std::move(value);
          replaced = true;
          break;
        }
      }
      if (!replaced) members.emplace_back(std::move(key), std::move(value));
      skip_ws();
      if (pos_ >= s_.size()) fail("objeto sin cerrar");
      char c = s_[pos_++];
      if (c == '}') break;
      if (c != ',') fail("se esperaba ',' o '}'");
    }
    return Json(std::move(members));
  }
};

}  // namespace

Json Json::parse(std::string_view text) { return Parser(text).parse_document(); }

bool Json::as_bool() const {
  if (auto* b = std::get_if<bool>(&v_)) return *b;
  type_error("un booleano");
}

int64_t Json::as_int() const {
  if (auto* i = std::get_if<int64_t>(&v_)) return *i;
  type_error("un entero");
}

const std::string& Json::as_string() const {
  if (auto* s = std::get_if<std::string>(&v_)) return *s;
  type_error("una cadena");
}

const JsonArray& Json::as_array() const {
  if (auto* a = std::get_if<JsonArray>(&v_)) return *a;
  type_error("un array");
}

JsonArray& Json::as_array() {
  if (auto* a = std::get_if<JsonArray>(&v_)) return *a;
  type_error("un array");
}

const JsonObject& Json::as_object() const {
  if (auto* o = std::get_if<JsonObject>(&v_)) return *o;
  type_error("un objeto");
}

JsonObject& Json::as_object() {
  if (auto* o = std::get_if<JsonObject>(&v_)) return *o;
  type_error("un objeto");
}

const Json* Json::find(std::string_view key) const {
  if (auto* o = std::get_if<JsonObject>(&v_)) {
    for (const auto& [k, v] : *o) {
      if (k == key) return &v;
    }
  }
  return nullptr;
}

const Json& Json::at(std::string_view key) const {
  const Json* found = find(key);
  if (found == nullptr) throw IrError("JSON: falta la clave '" + std::string(key) + "'");
  return *found;
}

void Json::set(std::string_view key, Json value) {
  auto& o = as_object();
  for (auto& [k, v] : o) {
    if (k == key) {
      v = std::move(value);
      return;
    }
  }
  o.emplace_back(std::string(key), std::move(value));
}

const Json& Json::at(size_t i) const {
  const auto& a = as_array();
  if (i >= a.size()) throw IrError("JSON: índice fuera de rango");
  return a[i];
}

size_t Json::size() const {
  if (auto* a = std::get_if<JsonArray>(&v_)) return a->size();
  if (auto* o = std::get_if<JsonObject>(&v_)) return o->size();
  if (auto* s = std::get_if<std::string>(&v_)) return s->size();
  return 0;
}

void Json::push_back(Json value) { as_array().push_back(std::move(value)); }

void json_quote(std::string& out, std::string_view s) {
  static const char* hex = "0123456789abcdef";
  out += '"';
  for (char ch : s) {
    auto c = static_cast<unsigned char>(ch);
    switch (c) {
      case '"':
        out += "\\\"";
        break;
      case '\\':
        out += "\\\\";
        break;
      case '\n':
        out += "\\n";
        break;
      case '\r':
        out += "\\r";
        break;
      case '\t':
        out += "\\t";
        break;
      case '\b':
        out += "\\b";
        break;
      case '\f':
        out += "\\f";
        break;
      default:
        if (c < 0x20) {
          out += "\\u00";
          out += hex[c >> 4];
          out += hex[c & 0xF];
        } else {
          out += ch;
        }
    }
  }
  out += '"';
}

void Json::dump_to(std::string& out) const {
  switch (kind()) {
    case Kind::Null:
      out += "null";
      return;
    case Kind::Bool:
      out += std::get<bool>(v_) ? "true" : "false";
      return;
    case Kind::Int: {
      char buf[24];
      auto [end, ec] = std::to_chars(buf, buf + sizeof buf, std::get<int64_t>(v_));
      out.append(buf, end);
      return;
    }
    case Kind::String:
      json_quote(out, std::get<std::string>(v_));
      return;
    case Kind::Array: {
      out += '[';
      bool first = true;
      for (const auto& item : std::get<JsonArray>(v_)) {
        if (!first) out += ',';
        first = false;
        item.dump_to(out);
      }
      out += ']';
      return;
    }
    case Kind::Object: {
      const auto& members = std::get<JsonObject>(v_);
      std::vector<const std::pair<std::string, Json>*> sorted;
      sorted.reserve(members.size());
      for (const auto& m : members) sorted.push_back(&m);
      std::sort(sorted.begin(), sorted.end(),
                [](const auto* a, const auto* b) { return a->first < b->first; });
      out += '{';
      bool first = true;
      for (const auto* m : sorted) {
        if (!first) out += ',';
        first = false;
        json_quote(out, m->first);
        out += ':';
        m->second.dump_to(out);
      }
      out += '}';
      return;
    }
  }
}

std::string Json::dump() const {
  std::string out;
  dump_to(out);
  return out;
}

bool Json::operator==(const Json& other) const {
  if (kind() != other.kind()) return false;
  switch (kind()) {
    case Kind::Null:
      return true;
    case Kind::Bool:
      return std::get<bool>(v_) == std::get<bool>(other.v_);
    case Kind::Int:
      return std::get<int64_t>(v_) == std::get<int64_t>(other.v_);
    case Kind::String:
      return std::get<std::string>(v_) == std::get<std::string>(other.v_);
    case Kind::Array:
      return std::get<JsonArray>(v_) == std::get<JsonArray>(other.v_);
    case Kind::Object: {
      // Igualdad de objetos sin depender del orden de las claves.
      const auto& a = std::get<JsonObject>(v_);
      const auto& b = std::get<JsonObject>(other.v_);
      if (a.size() != b.size()) return false;
      for (const auto& [k, v] : a) {
        const Json* w = other.find(k);
        if (w == nullptr || !(v == *w)) return false;
      }
      return true;
    }
  }
  return false;
}

}  // namespace gh
