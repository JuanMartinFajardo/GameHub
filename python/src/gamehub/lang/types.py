# SPDX-License-Identifier: Apache-2.0
"""Tipos de Nomos para el comprobador: representación, compatibilidad y traducción a la IR.

Reglas de compatibilidad (de `assignable`):
- `Int` se usa donde se espera `Real`; `Seat` e `Int` son intercambiables (un asiento es un
  entero; el motor comprueba el rango).
- `T` se usa donde se espera `T?`; `none` donde se espera cualquier opcional.
- Una lista se usa donde se espera una zona, una bolsa, un conjunto o un `per_player` del mismo
  elemento (el motor la convierte al asignar).
- Una tupla `(Int, Int)` es una casilla (`Cell`) y viceversa.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

PRIMITIVES = ("Bool", "Int", "Real", "Text", "Seat", "Cell")
NUMERIC = frozenset({"Int", "Real", "Seat"})
COLLECTIONS = frozenset({"list", "set", "zone", "bag", "per_player"})


@dataclass(frozen=True)
class Ty:
    """`kind`: un primitivo (Bool, Int, Real, Text, Seat, Cell), enum, struct, option, list,
    set, map, tuple, per_player, zone, bag, grid o unknown (error ya informado: compatible con
    todo, evita errores en cascada)."""

    kind: str
    name: str = ""
    args: tuple[Ty, ...] = ()
    dims: tuple[int | str, ...] = ()

    @property
    def inner(self) -> Ty:
        return self.args[0]

    @property
    def is_unknown(self) -> bool:
        return self.kind == "unknown"

    @property
    def is_numeric(self) -> bool:
        return self.kind in NUMERIC

    def __str__(self) -> str:
        return show(self)


BOOL = Ty("Bool")
INT = Ty("Int")
REAL = Ty("Real")
TEXT = Ty("Text")
SEAT = Ty("Seat")
CELL = Ty("Cell")
UNKNOWN = Ty("unknown")
NONE = Ty("option", args=(UNKNOWN,))


def enum_(name: str) -> Ty:
    return Ty("enum", name)


def struct_(name: str) -> Ty:
    return Ty("struct", name)


def option(t: Ty) -> Ty:
    return Ty("option", args=(t,))


def list_(t: Ty) -> Ty:
    return Ty("list", args=(t,))


def set_(t: Ty) -> Ty:
    return Ty("set", args=(t,))


def map_(k: Ty, v: Ty) -> Ty:
    return Ty("map", args=(k, v))


def tuple_(*items: Ty) -> Ty:
    return Ty("tuple", args=tuple(items))


def per_player(t: Ty) -> Ty:
    return Ty("per_player", args=(t,))


def zone(t: Ty) -> Ty:
    return Ty("zone", args=(t,))


def bag(t: Ty) -> Ty:
    return Ty("bag", args=(t,))


def grid(width: int | str, height: int | str, t: Ty) -> Ty:
    return Ty("grid", args=(t,), dims=(width, height))


PAYOFF = list_(REAL)


def show(t: Ty) -> str:
    """El tipo escrito en Nomos."""
    match t.kind:
        case "unknown":
            return "?"
        case "enum" | "struct":
            return t.name
        case "option":
            if t.inner.is_unknown:
                return "none"
            return show(t.inner) + "?"
        case "list" | "set" | "zone" | "bag":
            return f"{t.kind.capitalize()}<{show(t.inner)}>"
        case "map":
            return f"Map<{show(t.args[0])}, {show(t.args[1])}>"
        case "tuple":
            return "(" + ", ".join(show(a) for a in t.args) + ")"
        case "per_player":
            return "per_player " + show(t.inner)
        case "grid":
            return f"Grid[{t.dims[0]}, {t.dims[1]}] of {show(t.inner)}"
    return t.kind


def to_ir(t: Ty) -> Any:
    """Tipo en la IR (`spec/ir/v0/type.schema.json`)."""
    match t.kind:
        case "enum" | "struct":
            return t.name
        case "option" | "list" | "set" | "per_player" | "zone" | "bag":
            return [t.kind, to_ir(t.inner)]
        case "map":
            return ["map", to_ir(t.args[0]), to_ir(t.args[1])]
        case "tuple":
            return ["tuple", *(to_ir(a) for a in t.args)]
        case "grid":
            dims = [d if isinstance(d, int) else ["param", d] for d in t.dims]
            return ["grid", *dims, to_ir(t.inner)]
        case "unknown":
            return "Int"
    return t.kind


def from_ir(raw: Any, enums: set[str]) -> Ty:
    """Tipo de la IR → `Ty` (los nombres que no son enums se toman como structs)."""
    if isinstance(raw, str):
        if raw in PRIMITIVES:
            return Ty(raw)
        return enum_(raw) if raw in enums else struct_(raw)
    head, *rest = raw
    if head == "grid":
        w, h, inner = rest
        dims = tuple(d if isinstance(d, int) else d[1] for d in (w, h))
        return Ty("grid", args=(from_ir(inner, enums),), dims=dims)
    return Ty(head, args=tuple(from_ir(r, enums) for r in rest))


def elem(t: Ty) -> Ty | None:
    """Tipo de los elementos al iterar (listas, conjuntos, zonas, bolsas, per_player, claves de
    un mapa); None si no es iterable."""
    if t.kind in COLLECTIONS:
        return t.inner
    if t.kind == "map":
        return t.args[0]
    if t.kind == "unknown":
        return UNKNOWN
    return None


def _cell_like(t: Ty) -> bool:
    return t.kind == "Cell" or (
        t.kind == "tuple" and len(t.args) == 2 and all(a.kind in ("Int", "Seat") for a in t.args)
    )


def assignable(src: Ty, dst: Ty) -> bool:
    """¿Se puede usar un valor de tipo `src` donde se espera `dst`?"""
    if src.is_unknown or dst.is_unknown or src == dst:
        return True
    if src.kind in ("Int", "Seat") and dst.kind in NUMERIC:
        return True
    if dst.kind == "option":
        if src.kind == "option":
            return assignable(src.inner, dst.inner)
        return assignable(src, dst.inner)
    if dst.kind == "Cell" or (dst.kind == "tuple" and _cell_like(dst)):
        return _cell_like(src)
    if dst.kind == "list":
        return src.kind == "list" and assignable(src.inner, dst.inner)
    if dst.kind in ("set", "zone", "bag", "per_player"):
        if src.kind == dst.kind or src.kind == "list":
            return assignable(src.inner, dst.inner)
        if dst.kind in ("zone", "bag") and src.kind in ("zone", "bag"):
            return assignable(src.inner, dst.inner)
        return False
    if dst.kind == "map":
        if src.kind == "map":
            return assignable(src.args[0], dst.args[0]) and assignable(src.args[1], dst.args[1])
        if src.kind == "list" and src.inner.kind == "tuple" and len(src.inner.args) == 2:
            return assignable(src.inner, tuple_(*dst.args))
        return src.kind == "list" and src.inner.is_unknown
    if dst.kind == "tuple":
        return (
            src.kind == "tuple"
            and len(src.args) == len(dst.args)
            and all(assignable(a, b) for a, b in zip(src.args, dst.args, strict=True))
        )
    if dst.kind == "grid":
        return src.kind == "grid" and src.dims == dst.dims and assignable(src.inner, dst.inner)
    return False


def join(a: Ty, b: Ty) -> Ty | None:
    """Menor tipo que admite valores de `a` y de `b` (listas literales, ramas de `if`…); None si
    son incompatibles."""
    if a.is_unknown:
        return b
    if b.is_unknown or a == b:
        return a
    if a.is_numeric and b.is_numeric:
        if "Real" in (a.kind, b.kind):
            return REAL
        return INT
    if a.kind == "option" or b.kind == "option":
        inner_a = a.inner if a.kind == "option" else a
        inner_b = b.inner if b.kind == "option" else b
        inner = join(inner_a, inner_b)
        return None if inner is None else option(inner)
    if _cell_like(a) and _cell_like(b):
        return CELL
    if a.kind == b.kind and a.kind in ("list", "set", "zone", "bag", "per_player"):
        inner = join(a.inner, b.inner)
        return None if inner is None else Ty(a.kind, args=(inner,))
    if a.kind == b.kind == "tuple" and len(a.args) == len(b.args):
        items = [join(x, y) for x, y in zip(a.args, b.args, strict=True)]
        if any(i is None for i in items):
            return None
        return tuple_(*(i for i in items if i is not None))
    if a.kind == b.kind == "map":
        k, v = join(a.args[0], b.args[0]), join(a.args[1], b.args[1])
        return None if k is None or v is None else map_(k, v)
    if assignable(a, b):
        return b
    if assignable(b, a):
        return a
    return None


def comparable(a: Ty, b: Ty) -> bool:
    """¿Tiene sentido `a == b`?"""
    return join(a, b) is not None


def ordered(a: Ty, b: Ty) -> bool:
    """¿Tiene sentido `a < b`? Números, enums del mismo tipo y textos."""
    if a.is_unknown or b.is_unknown:
        return True
    if a.is_numeric and b.is_numeric:
        return True
    if a.kind == b.kind == "enum":
        return a.name == b.name
    return a.kind == b.kind == "Text"


def contains_unknown(t: Ty) -> bool:
    return t.is_unknown or any(contains_unknown(a) for a in t.args)
