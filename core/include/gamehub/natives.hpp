// SPDX-License-Identifier: Apache-2.0
// Plugins nativos (ADR-062) en el núcleo C++: una función de la IR con `"native"` puede
// calcularse con un plugin WebAssembly (ABI gamehub-native/1) en vez de con su cuerpo de
// referencia, como en `gamehub.engine.natives`. El núcleo no ejecuta WebAssembly: quien lo aloja
// (en el navegador, JavaScript) registra un `NativeHost` que llama al plugin; sin él se usa
// siempre la referencia.
#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "gamehub/types.hpp"
#include "gamehub/value.hpp"

namespace gh {

//: Palabras del búfer de intercambio (64 KiB): la mitad para la entrada y la otra para la salida.
constexpr int NATIVE_BUFFER_WORDS = 16384;

class NativeHost {
 public:
  virtual ~NativeHost() = default;
  // Un identificador de la implementación de `native_id` ("std.poker.hand_value"), o -1 si no
  // hay plugin.
  virtual int find(const std::string& native_id) = 0;
  // Llama al plugin con las palabras `in` y escribe el resultado en `out` (como mucho `cap`
  // palabras). Devuelve cuántas escribió (negativo = error).
  virtual int call(int handle, const int32_t* in, int len, int32_t* out, int cap) = 0;
};

// El anfitrión de los plugins para los juegos que se carguen a continuación (nullptr = sin
// plugins). Cada función guarda el suyo: debe vivir tanto como el juego.
void set_native_host(NativeHost* host);
NativeHost* native_host();

struct NativeFn {
  NativeHost* host = nullptr;
  int handle = -1;
  std::vector<TypeRef> params;
  TypeRef returns;
};

// Codifica los argumentos (false si alguno no cabe en el ABI: un número fuera de 32 bits, un
// racional, un texto…; entonces calcula la referencia) y llama al plugin. Lanza RuleError si el
// plugin falla o devuelve algo que no es un valor del tipo.
bool call_native(const NativeFn& fn, const TypeTable& types, const Value* args, Value& result,
                 const std::string& native_id);

}  // namespace gh
