// SPDX-License-Identifier: Apache-2.0
#include "gamehub/pool.hpp"

#include <cstdlib>
#include <new>

namespace gh {

namespace {

constexpr size_t CLASSES = 64;  // bloques de hasta 1 KiB
constexpr size_t CHUNK = 64 * 1024;

struct FreeBlock {
  FreeBlock* next;
};

struct Pool {
  // Las listas libres crecen hasta el pico de memoria viva de cada tamaño.
  FreeBlock* free[CLASSES] = {};
  char* cursor = nullptr;
  char* end = nullptr;

  void* carve(size_t bytes) {
    if (cursor == nullptr || cursor + bytes > end) {
      // Los trozos no se devuelven nunca al sistema: se reutilizan por las listas libres.
      cursor = static_cast<char*>(std::malloc(CHUNK));
      if (cursor == nullptr) throw std::bad_alloc();
      end = cursor + CHUNK;
    }
    void* p = cursor;
    cursor += bytes;
    return p;
  }
};

thread_local Pool pool;

}  // namespace

void* pool_alloc(size_t bytes) {
  size_t cls = bytes / 16;
  if (cls >= CLASSES) {
    void* p = std::malloc(bytes);
    if (p == nullptr) throw std::bad_alloc();
    return p;
  }
  FreeBlock* block = pool.free[cls];
  if (block != nullptr) {
    pool.free[cls] = block->next;
    return block;
  }
  return pool.carve(bytes);
}

void pool_free(void* p, size_t bytes) {
  size_t cls = bytes / 16;
  if (cls >= CLASSES) {
    std::free(p);
    return;
  }
  auto* block = static_cast<FreeBlock*>(p);
  block->next = pool.free[cls];
  pool.free[cls] = block;
}

}  // namespace gh
