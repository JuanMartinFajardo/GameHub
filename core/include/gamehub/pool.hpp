// SPDX-License-Identifier: Apache-2.0
// Arena de memoria para los contenedores: listas libres por tamaño (múltiplos de 16 bytes),
// una por hilo. Los estados se crean y destruyen a millones en los playouts; reutilizar los
// bloques evita casi todas las llamadas a malloc.
#pragma once

#include <cstddef>

namespace gh {

void* pool_alloc(size_t bytes);  // `bytes` múltiplo de 16
void pool_free(void* p, size_t bytes);

}  // namespace gh
