// SPDX-License-Identifier: Apache-2.0
// Arena de memoria para los contenedores: listas libres por tamaño (múltiplos de 16 bytes),
// una por hilo. Los estados se crean y destruyen a millones en los playouts; reutilizar los
// bloques evita casi todas las llamadas a malloc.
#pragma once

#include <cstddef>
#include <vector>

namespace gh {

void* pool_alloc(size_t bytes);  // `bytes` múltiplo de 16
void pool_free(void* p, size_t bytes);

inline size_t pool_round(size_t bytes) { return (bytes + 15) & ~size_t(15); }

// Asignador de la arena para los contenedores de la biblioteca estándar.
template <class T>
struct PoolAllocator {
  using value_type = T;
  PoolAllocator() noexcept = default;
  template <class U>
  PoolAllocator(const PoolAllocator<U>&) noexcept {}
  T* allocate(size_t n) { return static_cast<T*>(pool_alloc(pool_round(n * sizeof(T)))); }
  void deallocate(T* p, size_t n) noexcept { pool_free(p, pool_round(n * sizeof(T))); }
  template <class U>
  bool operator==(const PoolAllocator<U>&) const noexcept {
    return true;
  }
};

template <class T>
using PoolVec = std::vector<T, PoolAllocator<T>>;

}  // namespace gh
