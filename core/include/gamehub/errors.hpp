// SPDX-License-Identifier: Apache-2.0
// Errores del motor: los mismos que el de referencia (gamehub.engine.errors).
#pragma once

#include <stdexcept>
#include <string>

namespace gh {

struct EngineError : std::runtime_error {
  using std::runtime_error::runtime_error;
};

// Las reglas llevan a una situación imposible (un fallo de diseño del juego).
struct RuleError : EngineError {
  explicit RuleError(const std::string& message, const std::string& where = "")
      : EngineError(where.empty() ? message : where + ": " + message), where(where) {}
  std::string where;
};

// Se intentó aplicar una acción (o un resultado de azar) que no es legal.
struct IllegalAction : EngineError {
  using EngineError::EngineError;
};

// Parámetros de partida inválidos.
struct InvalidParams : EngineError {
  using EngineError::EngineError;
};

// Un punto de azar con demasiados resultados para enumerarlos.
struct NotEnumerable : EngineError {
  using EngineError::EngineError;
};

// La IR no se puede cargar (mal formada, o usa algo que este motor no admite).
struct IrError : EngineError {
  using EngineError::EngineError;
};

}  // namespace gh
