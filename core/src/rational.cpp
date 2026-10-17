// SPDX-License-Identifier: Apache-2.0
#include "gamehub/rational.hpp"

namespace gh {

void overflow_error() {
  throw RuleError("desbordamiento: un número no cabe en 64 bits (el motor C++ no tiene enteros "
                  "de precisión arbitraria)");
}

namespace {

__int128 gcd128(__int128 a, __int128 b) {
  if (a < 0) a = -a;
  if (b < 0) b = -b;
  while (b != 0) {
    __int128 t = a % b;
    a = b;
    b = t;
  }
  return a;
}

int64_t narrow(__int128 x) {
  if (x > INT64_MAX || x < INT64_MIN) overflow_error();
  return static_cast<int64_t>(x);
}

}  // namespace

Rational Rational::of(__int128 num, __int128 den) {
  if (den < 0) {
    num = -num;
    den = -den;
  }
  __int128 g = gcd128(num, den);
  if (g > 1) {
    num /= g;
    den /= g;
  }
  return {narrow(num), narrow(den)};
}

Rational Rational::operator+(const Rational& o) const {
  if (den == 1 && o.den == 1) return {checked_add(num, o.num), 1};
  return of(__int128(num) * o.den + __int128(o.num) * den, __int128(den) * o.den);
}

Rational Rational::operator-(const Rational& o) const {
  if (den == 1 && o.den == 1) return {checked_sub(num, o.num), 1};
  return of(__int128(num) * o.den - __int128(o.num) * den, __int128(den) * o.den);
}

Rational Rational::operator*(const Rational& o) const {
  if (den == 1 && o.den == 1) return {checked_mul(num, o.num), 1};
  return of(__int128(num) * o.num, __int128(den) * o.den);
}

Rational Rational::operator/(const Rational& o) const {
  return of(__int128(num) * o.den, __int128(den) * o.num);
}

int64_t Rational::floor() const { return floor_div(num, den); }

Rational Rational::floor_mod(const Rational& o) const {
  // x - o·⌊x/o⌋, exacto.
  Rational q = *this / o;
  return *this - o * Rational::integer(q.floor());
}

int Rational::compare(const Rational& o) const {
  __int128 a = __int128(num) * o.den;
  __int128 b = __int128(o.num) * den;
  return (a > b) - (a < b);
}

std::string Rational::str() const {
  if (den == 1) return std::to_string(num);
  return std::to_string(num) + "/" + std::to_string(den);
}

}  // namespace gh
