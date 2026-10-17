// SPDX-License-Identifier: Apache-2.0
// Racionales exactos de 64 bits (numerador y denominador). El motor de referencia usa enteros
// de precisión arbitraria; aquí un resultado que no cabe en 64 bits es un `RuleError`
// ("desbordamiento"), nunca un valor distinto (ADR-076).
#pragma once

#include <cstdint>
#include <string>

#include "gamehub/errors.hpp"

namespace gh {

[[noreturn]] void overflow_error();

inline int64_t checked_add(int64_t a, int64_t b) {
  int64_t r;
  if (__builtin_add_overflow(a, b, &r)) overflow_error();
  return r;
}
inline int64_t checked_sub(int64_t a, int64_t b) {
  int64_t r;
  if (__builtin_sub_overflow(a, b, &r)) overflow_error();
  return r;
}
inline int64_t checked_mul(int64_t a, int64_t b) {
  int64_t r;
  if (__builtin_mul_overflow(a, b, &r)) overflow_error();
  return r;
}
inline int64_t checked_neg(int64_t a) {
  if (a == INT64_MIN) overflow_error();
  return -a;
}
// División entera hacia abajo y módulo con el signo del divisor (como `//` y `%` de Python).
inline int64_t floor_div(int64_t a, int64_t b) {
  if (a == INT64_MIN && b == -1) overflow_error();
  int64_t q = a / b;
  if ((a % b != 0) && ((a < 0) != (b < 0))) --q;
  return q;
}
inline int64_t floor_mod(int64_t a, int64_t b) {
  if (b == -1) return 0;
  int64_t m = a % b;
  if (m != 0 && ((m < 0) != (b < 0))) m += b;
  return m;
}

struct Rational {
  int64_t num = 0;
  int64_t den = 1;  // > 0, mcd(|num|, den) = 1

  static Rational of(__int128 num, __int128 den);  // normaliza; den != 0
  static Rational integer(int64_t n) { return {n, 1}; }
  bool is_integer() const { return den == 1; }

  Rational operator+(const Rational& o) const;
  Rational operator-(const Rational& o) const;
  Rational operator*(const Rational& o) const;
  Rational operator/(const Rational& o) const;  // o != 0
  Rational operator-() const { return {checked_neg(num), den}; }
  int64_t floor() const;                         // ⌊x⌋
  Rational floor_mod(const Rational& o) const;  // x - o·⌊x/o⌋
  int compare(const Rational& o) const;
  bool operator==(const Rational& o) const { return num == o.num && den == o.den; }

  // "n/d", o "n" si es entero (como los racionales en JSON).
  std::string str() const;
};

}  // namespace gh
