# SPDX-License-Identifier: Apache-2.0
"""Valores y tipos en tiempo de ejecución del motor de referencia.

Todos los valores son inmutables y hashables. Correspondencia con los tipos de la IR:

| Tipo IR                    | Valor Python                                   |
|----------------------------|------------------------------------------------|
| Bool, Int, Text, Seat      | bool, int, str, int                            |
| Real                       | int o Fraction (exacto; entero si es integral) |
| Cell, tuple, list          | tuple                                          |
| enum                       | EnumValue                                      |
| struct                     | StructValue                                    |
| option                     | None o el valor                                |
| set                        | SetValue (orden canónico, sin repetidos)       |
| map                        | MapValue (pares ordenados por clave)           |
| per_player                 | tuple indexada por asiento                     |
| zone / bag                 | Zone(ordered=True) / Zone(ordered=False)       |
| grid                       | Grid                                           |

Toda iteración sobre conjuntos, bolsas y mapas sigue el **orden canónico** de `sort_key`, de
modo que la ejecución es determinista e independiente del hash de Python.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

from gamehub.engine.errors import RuleError

# --- Valores ------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EnumValue:
    type: str
    name: str
    ordinal: int

    def __repr__(self) -> str:
        return f"{self.type}.{self.name}"


@dataclass(frozen=True, slots=True)
class StructValue:
    type: str
    fields: tuple[tuple[str, Any], ...]

    def get(self, name: str) -> Any:
        for key, value in self.fields:
            if key == name:
                return value
        raise RuleError(f"{self.type} no tiene el campo {name}")

    def replace(self, name: str, value: Any) -> StructValue:
        self.get(name)
        return StructValue(self.type, tuple((k, value if k == name else v) for k, v in self.fields))

    def __repr__(self) -> str:
        inner = ", ".join(f"{k}: {v!r}" for k, v in self.fields)
        return f"{self.type} {{{inner}}}"


@dataclass(frozen=True, slots=True)
class SetValue:
    items: tuple[Any, ...]

    @staticmethod
    def of(values: Iterable[Any]) -> SetValue:
        unique = list(dict.fromkeys(values))
        return SetValue(tuple(sorted(unique, key=sort_key)))


@dataclass(frozen=True, slots=True)
class MapValue:
    items: tuple[tuple[Any, Any], ...]

    @staticmethod
    def of(pairs: Iterable[tuple[Any, Any]]) -> MapValue:
        merged = dict(pairs)
        return MapValue(tuple(sorted(merged.items(), key=lambda kv: sort_key(kv[0]))))

    def get(self, key: Any) -> Any:
        for k, v in self.items:
            if k == key:
                return v
        raise RuleError(f"clave inexistente en el mapa: {key!r}")

    def set(self, key: Any, value: Any) -> MapValue:
        return MapValue.of([*self.items, (key, value)])


@dataclass(frozen=True, slots=True)
class ZoneItem:
    value: Any
    face_up: bool = False


@dataclass(frozen=True, slots=True)
class Zone:
    """Zona ordenada (índice 0 = arriba) o bolsa (`ordered=False`, siempre en orden canónico)."""

    items: tuple[ZoneItem, ...] = ()
    ordered: bool = True

    @staticmethod
    def of(values: Iterable[Any], *, ordered: bool = True) -> Zone:
        return Zone(tuple(ZoneItem(v) for v in values), ordered).normalized()

    def normalized(self) -> Zone:
        if self.ordered:
            return self
        key = lambda item: (sort_key(item.value), item.face_up)  # noqa: E731
        return Zone(tuple(sorted(self.items, key=key)), ordered=False)

    def values(self) -> tuple[Any, ...]:
        return tuple(item.value for item in self.items)

    def with_items(self, items: Iterable[ZoneItem]) -> Zone:
        return Zone(tuple(items), self.ordered).normalized()

    def __len__(self) -> int:
        return len(self.items)


@dataclass(frozen=True, slots=True)
class Grid:
    width: int
    height: int
    cells: tuple[Any, ...] = field(repr=False)

    @staticmethod
    def filled(width: int, height: int, value: Any) -> Grid:
        return Grid(width, height, (value,) * (width * height))

    def in_bounds(self, cell: Any) -> bool:
        r, c = cell
        return 0 <= r < self.height and 0 <= c < self.width

    def _offset(self, cell: Any) -> int:
        if not (isinstance(cell, tuple) and len(cell) == 2 and self.in_bounds(cell)):
            raise RuleError(f"casilla fuera de la rejilla {self.height}×{self.width}: {cell!r}")
        return cell[0] * self.width + cell[1]

    def get(self, cell: Any) -> Any:
        return self.cells[self._offset(cell)]

    def set(self, cell: Any, value: Any) -> Grid:
        i = self._offset(cell)
        return Grid(self.width, self.height, (*self.cells[:i], value, *self.cells[i + 1 :]))

    def rows(self) -> list[tuple[Any, ...]]:
        w = self.width
        return [self.cells[r * w : (r + 1) * w] for r in range(self.height)]


def norm_num(x: Any) -> Any:
    """Racionales integrales como int (forma canónica)."""
    if isinstance(x, Fraction) and x.denominator == 1:
        return int(x)
    return x


def sort_key(v: Any) -> tuple[Any, ...]:
    """Orden total canónico entre valores (para conjuntos, bolsas, mapas y desempates)."""
    if v is None:
        return (0,)
    if isinstance(v, bool):
        return (1, int(v))
    if isinstance(v, int | Fraction):
        return (2, v)
    if isinstance(v, str):
        return (3, v)
    if isinstance(v, EnumValue):
        return (4, v.type, v.ordinal)
    if isinstance(v, tuple):
        return (5, tuple(sort_key(x) for x in v))
    if isinstance(v, StructValue):
        return (6, v.type, tuple(sort_key(x) for _, x in v.fields))
    if isinstance(v, SetValue):
        return (7, tuple(sort_key(x) for x in v.items))
    if isinstance(v, MapValue):
        return (8, tuple((sort_key(k), sort_key(x)) for k, x in v.items))
    if isinstance(v, Zone):
        return (9, v.ordered, tuple((sort_key(i.value), i.face_up) for i in v.items))
    if isinstance(v, Grid):
        return (10, v.width, v.height, tuple(sort_key(x) for x in v.cells))
    raise TypeError(f"valor desconocido: {v!r}")


# --- Tipos -------------------------------------------------------------------------------------

PRIMITIVES = frozenset({"Bool", "Int", "Real", "Text", "Seat", "Cell"})


@dataclass(frozen=True, slots=True)
class Type:
    """Tipo de la IR ya analizado. `kind`: prim, enum, struct, option, list, set, map, tuple,
    per_player, zone, bag o grid."""

    kind: str
    name: str = ""
    args: tuple[Type, ...] = ()
    dims: tuple[int | str, ...] = ()

    @property
    def inner(self) -> Type:
        return self.args[0]


class TypeTable:
    """Enumerados y structs declarados; analiza tipos y convierte valores a/desde JSON."""

    def __init__(self, decls: list[dict[str, Any]]) -> None:
        self.enums: dict[str, tuple[EnumValue, ...]] = {}
        self.structs: dict[str, tuple[tuple[str, Type], ...]] = {}
        for d in decls:
            if d["kind"] == "enum":
                values = tuple(EnumValue(d["name"], v, i) for i, v in enumerate(d["values"]))
                self.enums[d["name"]] = values
        for d in decls:
            if d["kind"] == "struct":
                fields = tuple((f["name"], self.parse(f["type"])) for f in d["fields"])
                self.structs[d["name"]] = fields

    def enum_value(self, type_name: str, name: str) -> EnumValue:
        for v in self.enums[type_name]:
            if v.name == name:
                return v
        raise RuleError(f"{type_name} no tiene el valor {name}")

    def parse(self, raw: Any) -> Type:
        if isinstance(raw, str):
            if raw in PRIMITIVES:
                return Type("prim", raw)
            if raw in self.enums:
                return Type("enum", raw)
            return Type("struct", raw)
        head, *rest = raw
        if head == "grid":
            w, h, inner = rest
            dims = tuple(d if isinstance(d, int) else d[1] for d in (w, h))
            return Type("grid", args=(self.parse(inner),), dims=dims)
        return Type(head, args=tuple(self.parse(r) for r in rest))

    # --- JSON (entrada) -------------------------------------------------------------------------

    def decode(self, j: Any, t: Type) -> Any:
        """JSON → valor (acciones recibidas, parámetros, replays). Valida la forma."""
        try:
            return self._decode(j, t)
        except (KeyError, TypeError, ValueError, IndexError, RuleError) as exc:
            raise ValueError(f"valor JSON inválido para {describe(t)}: {j!r}") from exc

    def _decode(self, j: Any, t: Type) -> Any:
        match t.kind:
            case "prim":
                return self._decode_prim(j, t.name)
            case "enum":
                if not isinstance(j, str):
                    raise TypeError(j)
                return self.enum_value(t.name, j)
            case "struct":
                fields = self.structs[t.name]
                if not isinstance(j, dict) or set(j) != {k for k, _ in fields}:
                    raise TypeError(j)
                return StructValue(t.name, tuple((k, self._decode(j[k], ft)) for k, ft in fields))
            case "option":
                return None if j is None else self._decode(j, t.inner)
            case "list" | "per_player":
                return tuple(self._decode(x, t.inner) for x in _as_list(j))
            case "set":
                return SetValue.of(self._decode(x, t.inner) for x in _as_list(j))
            case "tuple":
                items = _as_list(j)
                if len(items) != len(t.args):
                    raise ValueError(j)
                return tuple(self._decode(x, tt) for x, tt in zip(items, t.args, strict=True))
            case "map":
                return MapValue.of(
                    (self._decode(k, t.args[0]), self._decode(x, t.args[1])) for k, x in _as_list(j)
                )
            case "zone" | "bag":
                raw = j["items"] if isinstance(j, dict) else j
                values = [self._decode(x, t.inner) for x in _as_list(raw)]
                return Zone.of(values, ordered=t.kind == "zone")
        raise TypeError(f"no se puede decodificar {describe(t)}")

    @staticmethod
    def _decode_prim(j: Any, name: str) -> Any:
        match name:
            case "Bool":
                if not isinstance(j, bool):
                    raise TypeError(j)
                return j
            case "Int" | "Seat":
                if isinstance(j, bool) or not isinstance(j, int):
                    raise TypeError(j)
                return j
            case "Real":
                if isinstance(j, bool):
                    raise TypeError(j)
                if isinstance(j, int):
                    return j
                return norm_num(Fraction(j))
            case "Text":
                if not isinstance(j, str):
                    raise TypeError(j)
                return j
            case "Cell":
                r, c = _as_list(j)
                if isinstance(r, bool) or isinstance(c, bool):
                    raise TypeError(j)
                return (int(r), int(c))
        raise TypeError(name)


#: Marcador de valor oculto en vistas y eventos.
HIDDEN: dict[str, bool] = {"$hidden": True}


def to_json(v: Any) -> Any:
    """Valor → JSON. Los valores en tiempo de ejecución se autodescriben, así que no hace falta
    el tipo: enums como su nombre, structs como objetos, listas/tuplas/casillas/per_player como
    arrays, conjuntos en orden canónico, mapas como pares, zonas como {size, items}, racionales no
    enteros como "n/d".

    Despacha por el tipo exacto (es el camino caliente al enumerar miles de acciones): comprobar
    `isinstance(v, Fraction)` pasa por la maquinaria de las clases abstractas y es lento."""
    kind = type(v)
    if kind is int or kind is str or kind is bool or v is None:
        return v
    convert = _TO_JSON.get(kind)
    if convert is None:
        raise TypeError(f"valor desconocido: {v!r}")
    return convert(v)


def to_json_shared(v: Any, memo: dict[int, Any]) -> Any:
    """Como `to_json`, pero reutiliza la conversión de cada objeto ya visto (por identidad) en
    `memo`. Para listas grandes que comparten elementos (las acciones legales de Mentiroso son
    miles de subconjuntos de las mismas cartas). El resultado comparte objetos JSON entre sí: solo
    para serializarlo, no para modificarlo. `memo` debe vivir menos que los valores."""
    kind = type(v)
    if kind is int or kind is str or kind is bool or v is None:
        return v
    if kind is tuple:
        return [to_json_shared(x, memo) for x in v]
    key = id(v)
    found = memo.get(key)
    if found is None:
        found = memo[key] = to_json(v)
    return found


def _fraction_json(v: Fraction) -> Any:
    n = norm_num(v)
    return n if isinstance(n, int) else f"{n.numerator}/{n.denominator}"


_TO_JSON: dict[type, Any] = {
    Fraction: _fraction_json,
    EnumValue: lambda v: v.name,
    StructValue: lambda v: {k: to_json(x) for k, x in v.fields},
    tuple: lambda v: [to_json(x) for x in v],
    SetValue: lambda v: [to_json(x) for x in v.items],
    MapValue: lambda v: [[to_json(k), to_json(x)] for k, x in v.items],
    Zone: lambda v: {"size": len(v), "items": [to_json(i.value) for i in v.items]},
    Grid: lambda v: [[to_json(x) for x in row] for row in v.rows()],
}


def _as_list(j: Any) -> list[Any]:
    if not isinstance(j, list):
        raise TypeError(j)
    return j


def describe(t: Type) -> str:
    if t.kind in ("prim", "enum", "struct"):
        return t.name
    if t.kind == "grid":
        return f"grid[{t.dims[0]}, {t.dims[1]}] of {describe(t.inner)}"
    return f"{t.kind}<{', '.join(describe(a) for a in t.args)}>"
