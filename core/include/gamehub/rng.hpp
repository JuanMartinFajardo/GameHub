// SPDX-License-Identifier: Apache-2.0
// PCG32 (XSH-RR 64/32), idéntico a `pcg32_srandom_r` / `pcg32_random_r` / `pcg32_boundedrand_r`
// de la implementación de referencia en C y a `gamehub.engine.rng.Pcg32` (ADR-022).
#pragma once

#include <cstdint>
#include <stdexcept>

namespace gh {

// Flujos de PCG32 por propósito (los mismos que en Python).
constexpr uint64_t STREAM_CHANCE = 1;
constexpr uint64_t STREAM_SERVER = 2;
constexpr uint64_t STREAM_AGENT_BASE = 1000;  // + asiento

struct Pcg32 {
  uint64_t state = 0;
  uint64_t inc = 0;

  Pcg32() = default;
  explicit Pcg32(uint64_t seed, uint64_t stream = STREAM_CHANCE) {
    state = 0;
    inc = (stream << 1) | 1;
    next_u32();
    state += seed;
    next_u32();
  }

  uint32_t next_u32() {
    uint64_t old = state;
    state = old * 6364136223846793005ULL + inc;
    auto xorshifted = static_cast<uint32_t>(((old >> 18) ^ old) >> 27);
    auto rot = static_cast<uint32_t>(old >> 59);
    return (xorshifted >> rot) | (xorshifted << ((-rot) & 31));
  }

  // Entero uniforme en [0, n), sin sesgo (por rechazo).
  uint32_t below(uint64_t n) {
    if (n == 0 || n > (uint64_t(1) << 32)) throw std::out_of_range("cota fuera de rango");
    uint64_t threshold = ((uint64_t(1) << 32) - n) % n;
    while (true) {
      uint32_t r = next_u32();
      if (r >= threshold) return static_cast<uint32_t>(r % n);
    }
  }
};

}  // namespace gh
