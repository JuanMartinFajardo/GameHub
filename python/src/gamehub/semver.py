# SPDX-License-Identifier: Apache-2.0
"""Versiones semánticas (semver 2.0) y requisitos de versión al estilo de Cargo.

    ^1.2.3   >=1.2.3, <2.0.0      (lo que se escribe sin operador: "1.2.3" es "^1.2.3")
    ^0.2.3   >=0.2.3, <0.3.0      (en 0.y.z, la y hace de versión mayor)
    ~1.2.3   >=1.2.3, <1.3.0
    1.2.*    >=1.2.0, <1.3.0      (y `*`: cualquiera)
    >=0.3, <0.4                   (varias comparaciones separadas por comas: todas a la vez)

Una versión previa (`1.0.0-beta.2`) solo cumple un requisito que nombra una previa de la misma
versión (`>=1.0.0-beta`), como en Cargo y npm.

`bump` y `allowed` aplican la regla del versionado automático del hub: un cambio incompatible
de la interfaz sube la mayor (o la y en 0.y.z), un cambio de reglas o una ampliación de la
interfaz, la menor (o la z en 0.y.z), y un cambio cosmético, el parche.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

#: Qué cambió entre dos versiones de un juego (ver `gamehub.ir.interface.change_level`).
Level = Literal["major", "minor", "patch"]

_VERSION = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+[0-9A-Za-z.-]+)?$"
)
_PARTIAL = re.compile(
    r"^(\d+|\*|x)(?:\.(\d+|\*|x))?(?:\.(\d+|\*|x))?(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)


class VersionError(ValueError):
    """Una versión o un requisito mal escritos."""


@dataclass(frozen=True)
class Version:
    major: int
    minor: int
    patch: int
    pre: tuple[int | str, ...] = ()

    @classmethod
    def parse(cls, text: str) -> Version:
        m = _VERSION.match(text.strip().removeprefix("v"))
        if m is None:
            raise VersionError(f"versión no válida: {text!r} (semver: 1.2.3 o 1.2.3-beta.1)")
        pre = tuple(int(p) if p.isdigit() else p for p in m[4].split(".")) if m[4] else ()
        return cls(int(m[1]), int(m[2]), int(m[3]), pre)

    def __str__(self) -> str:
        core = f"{self.major}.{self.minor}.{self.patch}"
        return f"{core}-{'.'.join(map(str, self.pre))}" if self.pre else core

    @property
    def core(self) -> tuple[int, int, int]:
        return (self.major, self.minor, self.patch)

    def key(self) -> tuple[object, ...]:
        """Clave de orden de semver: una previa va antes que su versión; entre identificadores,
        los numéricos antes que los alfanuméricos."""
        pre = tuple((0, p, "") if isinstance(p, int) else (1, 0, p) for p in self.pre)
        return (*self.core, 0 if self.pre else 1, pre)

    def __lt__(self, other: Version) -> bool:
        return self.key() < other.key()

    def __le__(self, other: Version) -> bool:
        return self.key() <= other.key()

    def __gt__(self, other: Version) -> bool:
        return self.key() > other.key()

    def __ge__(self, other: Version) -> bool:
        return self.key() >= other.key()

    def bump(self, level: Level) -> Version:
        """La siguiente versión para un cambio de ese nivel (en 0.y.z, un nivel menos)."""
        if self.major == 0:
            level = "minor" if level == "major" else "patch"
        if level == "major":
            return Version(self.major + 1, 0, 0)
        if level == "minor":
            return Version(self.major, self.minor + 1, 0)
        return Version(self.major, self.minor, self.patch + 1)


def allowed(previous: Version, new: Version, level: Level) -> bool:
    """¿Puede `new` publicarse tras `previous` con un cambio de ese nivel? Tiene que ser mayor
    y, si el cambio rompe algo, cambiar la parte que lo anuncia."""
    if new <= previous:
        return False
    if previous.pre and new.core == previous.core:
        return True  # de una previa a la siguiente previa o a la versión final
    if level == "major":
        if previous.major > 0:
            return new.major > previous.major
        return new.core[:2] > previous.core[:2]
    if level == "minor" and previous.major > 0:
        return new.core[:2] > previous.core[:2]
    return True


# --- requisitos ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class Comparator:
    op: str  # ">=", ">", "<", "<=", "="
    version: Version

    def matches(self, v: Version) -> bool:
        if self.op == ">=":
            return v >= self.version
        if self.op == ">":
            return v > self.version
        if self.op == "<":
            return v < self.version
        if self.op == "<=":
            return v <= self.version
        return v.key() == self.version.key()

    def __str__(self) -> str:
        return f"{self.op}{self.version}"


@dataclass(frozen=True)
class Requirement:
    text: str
    comparators: tuple[Comparator, ...]

    @classmethod
    def parse(cls, text: str) -> Requirement:
        parts = [p.strip() for p in text.split(",")]
        if not text.strip() or any(not p for p in parts):
            raise VersionError(f"requisito de versión vacío: {text!r}")
        comparators: list[Comparator] = []
        for part in parts:
            comparators += _comparators(part)
        return cls(text.strip(), tuple(comparators))

    def matches(self, v: Version) -> bool:
        if not all(c.matches(v) for c in self.comparators):
            return False
        # Una previa solo vale si el requisito nombra una previa de la misma versión.
        return not v.pre or any(
            c.version.pre and c.version.core == v.core for c in self.comparators
        )

    def best(self, versions: list[Version]) -> Version | None:
        """La versión más alta que cumple el requisito."""
        found = [v for v in versions if self.matches(v)]
        return max(found, key=Version.key) if found else None

    def __str__(self) -> str:
        return self.text


def _comparators(part: str) -> list[Comparator]:
    m = re.match(r"^(\^|~|>=|<=|>|<|=)?\s*(.+)$", part)
    if m is None:
        raise VersionError(f"requisito no válido: {part!r}")
    op, rest = m[1] or "^", m[2].removeprefix("v")
    if rest in ("*", "x"):
        if m[1]:
            raise VersionError(f"requisito no válido: {part!r}")
        return []
    p = _PARTIAL.match(rest)
    if p is None:
        raise VersionError(f"requisito no válido: {part!r}")
    nums = [p[1], p[2], p[3]]
    wild = [n in ("*", "x") for n in nums]
    if any(wild):
        if m[1] or p[4]:
            raise VersionError(f"requisito no válido: {part!r} (comodín con operador o previa)")
        given = [int(n) for n in nums[: wild.index(True)]]
        if any(n is not None and n not in ("*", "x") for n in nums[wild.index(True) :]):
            raise VersionError(f"requisito no válido: {part!r}")
        if not given:
            return []
        return _range(given, "~" if len(given) == 2 else "^")
    given = [int(n) for n in nums if n is not None]
    pre = tuple(int(x) if x.isdigit() else x for x in p[4].split(".")) if p[4] else ()
    if pre and len(given) < 3:
        raise VersionError(f"requisito no válido: {part!r} (una previa necesita x.y.z)")
    full = Version(*(given + [0] * (3 - len(given))), pre=pre)  # type: ignore[arg-type]
    if op in ("^", "~"):
        return _range(given, op, pre)
    if op == "=":
        if len(given) == 3:
            return [Comparator("=", full)]
        return _range(given, "~" if len(given) == 2 else "^")
    if op == ">" and len(given) < 3:
        # >1.2 significa "después de toda la 1.2".
        return [Comparator(">=", _upper(given, "~" if len(given) == 2 else "^"))]
    if op == "<=" and len(given) < 3:
        return [Comparator("<", _upper(given, "~" if len(given) == 2 else "^"))]
    return [Comparator(op, full)]


def _range(given: list[int], op: str, pre: tuple[int | str, ...] = ()) -> list[Comparator]:
    low = Version(*(given + [0] * (3 - len(given))), pre=pre)  # type: ignore[arg-type]
    return [Comparator(">=", low), Comparator("<", _upper(given, op))]


def _upper(given: list[int], op: str) -> Version:
    """El primer valor que ya no entra en `^given` o `~given`."""
    major, minor, patch = [*given, 0, 0][:3]
    if op == "~":
        if len(given) == 1:
            return Version(major + 1, 0, 0)
        return Version(major, minor + 1, 0)
    if major > 0 or len(given) == 1:
        return Version(major + 1, 0, 0)
    if minor > 0 or len(given) == 2:
        return Version(0, minor + 1, 0)
    return Version(0, 0, patch + 1)
