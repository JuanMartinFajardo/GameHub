// SPDX-License-Identifier: Apache-2.0
// SHA-256 (FIPS 180-4): las huellas de estado (`digest`), el hash de reglas y las claves de
// información con recuerdo perfecto, idénticas a las de `hashlib` en el motor de referencia.
#pragma once

#include <array>
#include <cstdint>
#include <string>
#include <string_view>

namespace gh {

class Sha256 {
 public:
  Sha256();
  void update(std::string_view data);
  void update(const uint8_t* data, size_t size);
  std::array<uint8_t, 32> finish();
  std::string hexdigest();

  static std::string hex(std::string_view data);

 private:
  void block(const uint8_t* p);
  uint32_t h_[8];
  uint8_t buf_[64];
  size_t len_ = 0;
  uint64_t total_ = 0;
};

}  // namespace gh
