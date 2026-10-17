// SPDX-License-Identifier: Apache-2.0
// Hash de reglas (como `gamehub.ir.hashing`): SHA-256 del JSON canónico de la IR sin `meta`,
// `ui`, campos `doc`, mensajes de las restricciones ni valores por defecto explícitos.
#pragma once

#include <string>

#include "gamehub/json.hpp"

namespace gh {

Json strip_cosmetic(const Json& doc);
std::string rules_hash(const Json& doc);  // "sha256:…"

}  // namespace gh
