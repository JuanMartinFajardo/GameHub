// SPDX-License-Identifier: Apache-2.0
#include "gamehub/hashing.hpp"

#include "gamehub/sha256.hpp"

namespace gh {

namespace {

bool is_default(const std::string& key, const Json& value) {
  if (value.is_array() && value.size() == 0) return true;
  if ((key == "visibility" || key == "size_visibility") && value.is_string() &&
      value.as_string() == "all") {
    return true;
  }
  return false;
}

Json strip(const Json& node) {
  if (node.is_object()) {
    JsonObject out;
    for (const auto& [k, v] : node.as_object()) {
      if (k == "doc" || is_default(k, v)) continue;
      out.emplace_back(k, strip(v));
    }
    return Json(std::move(out));
  }
  if (node.is_array()) {
    const JsonArray& items = node.as_array();
    // Las S-expresiones (listas que empiezan por una cadena) no se tocan.
    if (!items.empty() && items[0].is_string()) return node;
    JsonArray out;
    for (const auto& item : items) out.push_back(strip(item));
    return Json(std::move(out));
  }
  return node;
}

}  // namespace

Json strip_cosmetic(const Json& doc) {
  JsonObject out;
  for (const auto& [k, v] : doc.as_object()) {
    if (k == "meta" || k == "ui" || k == "doc" || is_default(k, v)) continue;
    if (k == "constraints") {
      JsonArray cs;
      Json stripped = strip(v);  // (una temporal en el for se destruiría antes del cuerpo)
      for (const auto& c : stripped.as_array()) {
        JsonObject kept;
        for (const auto& [ck, cv] : c.as_object()) {
          if (ck != "message") kept.emplace_back(ck, cv);
        }
        cs.push_back(Json(std::move(kept)));
      }
      out.emplace_back(k, Json(std::move(cs)));
      continue;
    }
    out.emplace_back(k, strip(v));
  }
  return Json(std::move(out));
}

std::string rules_hash(const Json& doc) {
  return "sha256:" + Sha256::hex(strip_cosmetic(doc).dump());
}

}  // namespace gh
