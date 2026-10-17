# SPDX-License-Identifier: Apache-2.0
"""Números globales de acción calculados desde la IR, sin explorar el juego (ADR-079).

Para una partida concreta (número de jugadores y parámetros), cada acción posible recibe un entero
fijo en `[0, size)`:

- Las acciones se agrupan en **bloques**: uno por cada firma distinta (nombre y universos de sus
  parámetros), en el orden en que aparecen en el flujo; `pass` (ventanas) es otro bloque. Dos nodos
  con la misma acción (la misma firma) comparten números.
- Dentro de un bloque, el número es la **base mixta** de los rangos de sus argumentos: cada
  parámetro tiene un **universo** finito con un rango (valor → entero) y su inverso:
  `Bool` (2), enumerados (sus valores), `Seat` (los asientos), `Cell` (las casillas de la rejilla
  más grande del estado), structs y tuplas (producto de sus campos), opcionales (1 + el interno),
  enteros acotados y **subconjuntos** (`subsets`: el número combinatorio de los elementos elegidos,
  por tamaños).
- Los enteros se acotan con una **interpretación abstracta por intervalos** de su dominio:
  constantes, parámetros de la partida, número de jugadores, funciones de la IR y las variables
  de estado, cuyas cotas salen de un punto fijo sobre todas sus asignaciones (con ensanchamiento),
  o de su rango declarado (`@range` en Nomos, `"range"` en la IR).

Ajedrez: `play` 64 × 64, `promote` 64 × 64 × 4 y `claim_draw`: 20.481 números. Si un dominio no se
puede acotar, `action_space` lanza `Unbounded` con el parámetro culpable (se puede declarar el
rango de la variable que lo limita).

`ActionSpace.encode(node, action)` y `decode(node, id)` convierten en los dos sentidos; `to_json()`
es la especificación que usa también el núcleo C++.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from functools import reduce
from typing import Any

from gamehub.engine.state import PASS, Action
from gamehub.engine.values import EnumValue, StructValue, Type, TypeTable, sort_key


class Unbounded(Exception):
    """Un parámetro de acción sin cota finita: no se le pueden dar números globales."""


class OutsideSpace(Exception):
    """Una acción fuera del espacio calculado (p. ej. un subconjunto con elementos repetidos)."""


# --- Universos ---------------------------------------------------------------------------------


class Universe:
    size: int

    def rank(self, v: Any) -> int:
        raise NotImplementedError

    def unrank(self, k: int) -> Any:
        raise NotImplementedError

    def to_json(self) -> dict[str, Any]:
        raise NotImplementedError

    def key(self) -> str:
        import json

        return json.dumps(self.to_json(), sort_keys=True)


@dataclass(frozen=True)
class BoolU(Universe):
    size: int = 2

    def rank(self, v: Any) -> int:
        if v is True:
            return 1
        if v is False:
            return 0
        raise OutsideSpace(v)

    def unrank(self, k: int) -> Any:
        return k == 1

    def to_json(self) -> dict[str, Any]:
        return {"kind": "bool"}


@dataclass(frozen=True)
class EnumU(Universe):
    """Los valores de un enumerado que admite el dominio (todos, o los que lista)."""

    values: tuple[EnumValue, ...]

    @property
    def size(self) -> int:  # type: ignore[override]
        return len(self.values)

    def rank(self, v: Any) -> int:
        for k, x in enumerate(self.values):
            if x == v:
                return k
        raise OutsideSpace(v)

    def unrank(self, k: int) -> Any:
        return self.values[k]

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": "enum",
            "type": self.values[0].type,
            "ordinals": [v.ordinal for v in self.values],
        }


@dataclass(frozen=True)
class IntU(Universe):
    lo: int
    hi: int

    @property
    def size(self) -> int:  # type: ignore[override]
        return self.hi - self.lo + 1

    def rank(self, v: Any) -> int:
        if isinstance(v, bool) or not isinstance(v, int) or not self.lo <= v <= self.hi:
            raise OutsideSpace(v)
        return v - self.lo

    def unrank(self, k: int) -> Any:
        return self.lo + k

    def to_json(self) -> dict[str, Any]:
        return {"kind": "int", "lo": self.lo, "hi": self.hi}


@dataclass(frozen=True)
class CellU(Universe):
    rows: int
    cols: int

    @property
    def size(self) -> int:  # type: ignore[override]
        return self.rows * self.cols

    def rank(self, v: Any) -> int:
        if not (isinstance(v, tuple) and len(v) == 2):
            raise OutsideSpace(v)
        r, c = v
        if not (0 <= r < self.rows and 0 <= c < self.cols):
            raise OutsideSpace(v)
        return r * self.cols + c

    def unrank(self, k: int) -> Any:
        return divmod(k, self.cols)

    def to_json(self) -> dict[str, Any]:
        return {"kind": "cell", "rows": self.rows, "cols": self.cols}


def _radix(parts: tuple[Universe, ...]) -> list[int]:
    """Pesos de la base mixta (el primer componente es el más significativo)."""
    strides = [1] * len(parts)
    for i in range(len(parts) - 2, -1, -1):
        strides[i] = strides[i + 1] * parts[i + 1].size
    return strides


@dataclass(frozen=True)
class ProductU(Universe):
    """Struct (con `type`) o tupla: el producto de sus componentes."""

    parts: tuple[Universe, ...]
    type: str | None = None
    names: tuple[str, ...] = ()

    @property
    def size(self) -> int:  # type: ignore[override]
        return math.prod(p.size for p in self.parts)

    def _values(self, v: Any) -> tuple[Any, ...]:
        if self.type is not None:
            if not isinstance(v, StructValue) or v.type != self.type:
                raise OutsideSpace(v)
            return tuple(x for _, x in v.fields)
        if not isinstance(v, tuple) or len(v) != len(self.parts):
            raise OutsideSpace(v)
        return v

    def rank(self, v: Any) -> int:
        values = self._values(v)
        strides = _radix(self.parts)
        return sum(p.rank(x) * s for p, x, s in zip(self.parts, values, strides, strict=True))

    def unrank(self, k: int) -> Any:
        values = []
        for p, s in zip(self.parts, _radix(self.parts), strict=True):
            q, k = divmod(k, s)
            values.append(p.unrank(q))
        if self.type is not None:
            return StructValue(self.type, tuple(zip(self.names, values, strict=True)))
        return tuple(values)

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"kind": "struct" if self.type else "tuple"}
        if self.type:
            out["type"] = self.type
        out["parts"] = [p.to_json() for p in self.parts]
        return out


@dataclass(frozen=True)
class OptionU(Universe):
    inner: Universe

    @property
    def size(self) -> int:  # type: ignore[override]
        return 1 + self.inner.size

    def rank(self, v: Any) -> int:
        return 0 if v is None else 1 + self.inner.rank(v)

    def unrank(self, k: int) -> Any:
        return None if k == 0 else self.inner.unrank(k - 1)

    def to_json(self) -> dict[str, Any]:
        return {"kind": "option", "inner": self.inner.to_json()}


@dataclass(frozen=True)
class SubsetU(Universe):
    """Subconjuntos de `lo` a `hi` elementos distintos de un universo, por tamaños y, dentro de
    cada tamaño, por el número combinatorio de los rangos elegidos (de mayor a menor)."""

    elem: Universe
    lo: int
    hi: int

    def _sizes(self) -> range:
        return range(max(self.lo, 0), min(self.hi, self.elem.size) + 1)

    @property
    def size(self) -> int:  # type: ignore[override]
        return sum(math.comb(self.elem.size, k) for k in self._sizes())

    def rank(self, v: Any) -> int:
        if not isinstance(v, tuple):
            raise OutsideSpace(v)
        ranks = sorted(self.elem.rank(x) for x in v)
        if len(set(ranks)) != len(ranks):
            raise OutsideSpace(f"subconjunto con elementos repetidos: {v!r}")
        k = len(ranks)
        if k not in self._sizes():
            raise OutsideSpace(v)
        offset = sum(math.comb(self.elem.size, j) for j in self._sizes() if j < k)
        return offset + sum(math.comb(r, i + 1) for i, r in enumerate(ranks))

    def unrank(self, k: int) -> Any:
        for size in self._sizes():
            block = math.comb(self.elem.size, size)
            if k < block:
                ranks = []
                for i in range(size, 0, -1):
                    r = i - 1
                    while math.comb(r + 1, i) <= k:
                        r += 1
                    ranks.append(r)
                    k -= math.comb(r, i)
                values = [self.elem.unrank(r) for r in ranks]
                return tuple(sorted(values, key=sort_key))
            k -= block
        raise OutsideSpace(k)

    def to_json(self) -> dict[str, Any]:
        return {"kind": "subset", "elem": self.elem.to_json(), "lo": self.lo, "hi": self.hi}


# --- Intervalos --------------------------------------------------------------------------------


_BOTTOM: Any = object()  # el elemento de una colección vacía (neutro de `join`)


@dataclass(frozen=True)
class Iv:
    """Enteros en [lo, hi] (None = sin cota)."""

    lo: int | None
    hi: int | None


@dataclass(frozen=True)
class Col:
    """Colección de elementos `elem` y como mucho `maxlen` elementos."""

    elem: Any
    maxlen: int | None


@dataclass(frozen=True)
class Enums:
    """Algunos valores de un enumerado (sus ordinales)."""

    type: str
    ordinals: frozenset[int]


TOP: Any = None  # sin información


def join(a: Any, b: Any) -> Any:
    if a is _BOTTOM:
        return b
    if b is _BOTTOM:
        return a
    if a is TOP or b is TOP:
        return TOP
    if isinstance(a, Enums) and isinstance(b, Enums) and a.type == b.type:
        return Enums(a.type, a.ordinals | b.ordinals)
    if isinstance(a, Iv) and isinstance(b, Iv):
        lo = None if a.lo is None or b.lo is None else min(a.lo, b.lo)
        hi = None if a.hi is None or b.hi is None else max(a.hi, b.hi)
        return Iv(lo, hi)
    if isinstance(a, Col) and isinstance(b, Col):
        ml = None if a.maxlen is None or b.maxlen is None else max(a.maxlen, b.maxlen)
        return Col(join(a.elem, b.elem), ml)
    return TOP


def join_all(values: list[Any]) -> Any:
    real = [v for v in values if v is not _BOTTOM]
    return reduce(join, real) if real else _BOTTOM


def _iv(v: Any) -> Iv:
    return v if isinstance(v, Iv) else Iv(None, None)


def _bound(op: Callable[[int, int], int], *xs: int | None) -> int | None:
    return None if any(x is None for x in xs) else reduce(op, xs)  # type: ignore[arg-type]


def iv_add(a: Iv, b: Iv) -> Iv:
    return Iv(_bound(int.__add__, a.lo, b.lo), _bound(int.__add__, a.hi, b.hi))


def iv_neg(a: Iv) -> Iv:
    return Iv(None if a.hi is None else -a.hi, None if a.lo is None else -a.lo)


def iv_mul(a: Iv, b: Iv) -> Iv:
    if None in (a.lo, a.hi, b.lo, b.hi):
        # Con signo conocido aún se puede acotar algo (p. ej. dos no negativos).
        if a.lo is not None and b.lo is not None and a.lo >= 0 and b.lo >= 0:
            return Iv(a.lo * b.lo, _bound(int.__mul__, a.hi, b.hi))
        return Iv(None, None)
    products = [a.lo * b.lo, a.lo * b.hi, a.hi * b.lo, a.hi * b.hi]  # type: ignore[operator]
    return Iv(min(products), max(products))


def _abstract(value: Any) -> Any:
    """Un valor concreto (un parámetro) como valor abstracto."""
    if isinstance(value, bool):
        return TOP
    if isinstance(value, int):
        return Iv(value, value)
    if isinstance(value, EnumValue):
        return Enums(value.type, frozenset({value.ordinal}))
    if isinstance(value, tuple):
        return Col(join_all([_abstract(x) for x in value]) if value else _BOTTOM, len(value))
    return TOP


# --- Análisis de expresiones -------------------------------------------------------------------


@dataclass
class _Analysis:
    ir: dict[str, Any]
    n: int
    params: dict[str, Any]
    types: TypeTable
    var_abs: dict[str, Any] = field(default_factory=dict)
    functions: dict[str, dict[str, Any]] = field(default_factory=dict)
    max_enum: int = 1
    zone_total: int | None = None
    _calls: dict[Any, Any] = field(default_factory=dict)

    def seat(self) -> Iv:
        return Iv(0, self.n - 1)

    def expr(self, e: Any, env: dict[str, Any]) -> Any:
        op, a = e[0], e[1:]
        ev = self.expr
        match op:
            case "const":
                return _abstract(_const_value(a[0]))
            case "enum":
                values = self.types.enums[a[0]]
                ordinal = next(v.ordinal for v in values if v.name == a[1])
                return Enums(a[0], frozenset({ordinal}))
            case "var":
                return self.var_abs.get(a[0], TOP)
            case "param":
                return _abstract(self.params.get(a[0]))
            case "arg" | "local":
                return env.get(a[0], TOP)
            case "actor" | "owner" | "viewer" | "next_seat" | "prev_seat" | "other_seat":
                return self.seat()
            case "seats" | "seats_from":
                return Col(self.seat(), self.n)
            case "list" | "tuple" | "set":
                return Col(join_all([ev(x, env) for x in a]) if a else _BOTTOM, len(a))
            case "add":
                return reduce(iv_add, (_iv(ev(x, env)) for x in a), Iv(0, 0))
            case "sub":
                return iv_add(_iv(ev(a[0], env)), iv_neg(_iv(ev(a[1], env))))
            case "mul":
                return reduce(iv_mul, (_iv(ev(x, env)) for x in a), Iv(1, 1))
            case "neg":
                return iv_neg(_iv(ev(a[0], env)))
            case "abs":
                x = _iv(ev(a[0], env))
                if x.lo is not None and x.lo >= 0:
                    return x
                hi = None if x.lo is None or x.hi is None else max(-x.lo, x.hi)
                return Iv(0, hi)
            case "min" | "max":
                xs = [_iv(ev(x, env)) for x in a]
                pick = min if op == "min" else max
                los = [x.lo for x in xs]
                his = [x.hi for x in xs]
                if op == "min":
                    lo = None if None in los else pick(los)  # type: ignore[type-var]
                    known = [h for h in his if h is not None]
                    return Iv(lo, min(known) if known else None)
                known_lo = [lo for lo in los if lo is not None]
                hi = None if None in his else max(his)  # type: ignore[type-var]
                return Iv(max(known_lo) if known_lo else None, hi)
            case "idiv":
                x, d = _iv(ev(a[0], env)), _iv(ev(a[1], env))
                if d.lo is not None and d.lo > 0 and x.lo is not None and x.lo >= 0:
                    return Iv(0, None if x.hi is None else x.hi // d.lo)
                return Iv(None, None)
            case "mod":
                d = _iv(ev(a[1], env))
                if d.lo is not None and d.lo > 0:
                    return Iv(0, None if d.hi is None else d.hi - 1)
                return Iv(None, None)
            case "if":
                return join_all([ev(a[1], env), ev(a[2], env)])
            case "case":
                return join_all([ev(v, env) for _, v in a[0]] + [ev(a[1], env)])
            case "let":
                return ev(a[2], {**env, a[0]: ev(a[1], env)})
            case "len" | "size":
                c = ev(a[0], env)
                if op == "size":
                    return Iv(0, self.zone_total)
                return Iv(0, c.maxlen if isinstance(c, Col) else None)
            case "count":
                c = ev(a[1], env)
                return Iv(0, c.maxlen if isinstance(c, Col) else None)
            case "index" | "first" | "last" | "only" | "top":
                c = ev(a[0], env)
                return c.elem if isinstance(c, Col) else TOP
            case "items":
                c = ev(a[0], env)
                return c if isinstance(c, Col) else Col(TOP, self.zone_total)
            case "argmax" | "argmin":
                c = ev(a[1], env)
                return c.elem if isinstance(c, Col) else TOP
            case "max_of" | "min_of":
                c = ev(a[1], env)
                return ev(a[2], {**env, a[0]: c.elem if isinstance(c, Col) else TOP})
            case "sum":
                c = ev(a[1], env)
                body = _iv(ev(a[2], {**env, a[0]: c.elem if isinstance(c, Col) else TOP}))
                k = c.maxlen if isinstance(c, Col) else None
                lo = 0 if body.lo is not None and body.lo >= 0 else _bound(int.__mul__, k, body.lo)
                hi = _bound(int.__mul__, k, body.hi)
                return Iv(None if lo is None else min(lo, 0), None if hi is None else max(hi, 0))
            case "map" | "filter" | "sort_by":
                c = ev(a[1], env)
                elem = c.elem if isinstance(c, Col) else TOP
                ml = c.maxlen if isinstance(c, Col) else None
                if op == "map":
                    return Col(ev(a[2], {**env, a[0]: elem}), ml)
                return Col(elem, ml)
            case "flat_map":
                c = ev(a[1], env)
                body = ev(a[2], {**env, a[0]: c.elem if isinstance(c, Col) else TOP})
                if isinstance(c, Col) and isinstance(body, Col):
                    return Col(body.elem, _bound(int.__mul__, c.maxlen, body.maxlen))
                return Col(TOP, None)
            case "reverse" | "distinct" | "slice":
                return ev(a[0], env)
            case "append":
                c, x = ev(a[0], env), ev(a[1], env)
                if isinstance(c, Col):
                    return Col(join_all([c.elem, x]), _bound(int.__add__, c.maxlen, 1))
                return TOP
            case "concat" | "union":
                c, d = ev(a[0], env), ev(a[1], env)
                if isinstance(c, Col) and isinstance(d, Col):
                    return Col(join_all([c.elem, d.elem]), _bound(int.__add__, c.maxlen, d.maxlen))
                return TOP
            case "intersection" | "difference":
                return ev(a[0], env)
            case "range":
                lo, hi = _iv(ev(a[0], env)), _iv(ev(a[1], env))
                ml = None if lo.lo is None or hi.hi is None else max(hi.hi - lo.lo + 1, 0)
                return Col(Iv(lo.lo, hi.hi), ml)
            case "subsets":
                c = ev(a[0], env)
                hi = _iv(ev(a[2], env)).hi
                return Col(Col(c.elem if isinstance(c, Col) else TOP, hi), None)
            case "ord":
                return Iv(0, self.max_enum - 1)
            case "enum_values":
                count = len(self.types.enums[a[0]])
                return Col(Enums(a[0], frozenset(range(count))), count)
            case "win_loss" | "fill":
                return Col(
                    join_all([ev(x, env) for x in a[1:]] if op == "win_loss" else [ev(a[0], env)]),
                    self.n,
                )
            case "call":
                return self.call(a[0], [ev(x, env) for x in a[1:]])
        return TOP

    def call(self, name: str, args: list[Any]) -> Any:
        key = (name, tuple(map(repr, args)))
        if key in self._calls:
            return self._calls[key]
        self._calls[key] = TOP  # (la IR no tiene recursión; por si acaso)
        f = self.functions[name]
        env = {p[0]: v for p, v in zip(f["params"], args, strict=True)}
        result = self.expr(f["body"], env)
        self._calls[key] = result
        return result


def _const_value(raw: Any) -> Any:
    if isinstance(raw, list):
        return tuple(_const_value(x) for x in raw)
    return raw


# --- Punto fijo sobre las variables de estado ---------------------------------------------------


def _blocks(ir: dict[str, Any]) -> Iterator[tuple[list[Any], dict[str, Any] | None]]:
    """Cada bloque de sentencias de la IR con la acción a la que pertenece (sus argumentos)."""
    flow = ir["flow"]
    yield flow.get("setup", []), None

    def nodes(ns: list[dict[str, Any]]) -> Iterator[tuple[list[Any], dict[str, Any] | None]]:
        for node in ns:
            for key in ("effects", "resolve", "on_enter", "on_exit"):
                if key in node:
                    yield node[key], None
            for t in node.get("transitions", []):
                yield t.get("effects", []), None
            for a in node.get("actions", []):
                yield a.get("effects", []), a
                for t in a.get("transitions", []):
                    yield t.get("effects", []), a
            if node["kind"] == "phase":
                yield from nodes(node["nodes"])

    yield from nodes(flow["nodes"])


def _set_path(abs_value: Any, depth: int, value: Any) -> Any:
    """El valor abstracto de una variable tras escribir `value` a `depth` índices de profundidad."""
    if depth == 0:
        return join_all([abs_value, value])
    if isinstance(abs_value, Col):
        return Col(_set_path(abs_value.elem, depth - 1, value), abs_value.maxlen)
    return TOP


def _widen(old: Any, new: Any) -> Any:
    if isinstance(old, Iv) and isinstance(new, Iv):
        lo = new.lo if old.lo is not None and new.lo is not None and new.lo >= old.lo else None
        hi = new.hi if old.hi is not None and new.hi is not None and new.hi <= old.hi else None
        return Iv(lo, hi)
    if isinstance(old, Col) and isinstance(new, Col):
        ml = new.maxlen if old.maxlen is not None and new.maxlen == old.maxlen else None
        return Col(_widen(old.elem, new.elem), ml)
    return new


def _declared(var: dict[str, Any], analysis: _Analysis) -> Iv | None:
    raw = var.get("range")
    if raw is None:
        return None
    lo, hi = (_iv(analysis.expr(x, {})) for x in raw)
    return Iv(lo.lo, hi.hi)


def _with_leaf(t: Type, leaf: Any, dims: Callable[[Type], int | None], n: int) -> Any:
    """El valor abstracto de una variable del tipo `t` cuyas hojas enteras están en `leaf`."""
    match t.kind:
        case "per_player":
            return Col(_with_leaf(t.inner, leaf, dims, n), n)
        case "list" | "set":
            return Col(_with_leaf(t.inner, leaf, dims, n), None)
        case "grid":
            return Col(_with_leaf(t.inner, leaf, dims, n), dims(t))
        case "option":
            return _with_leaf(t.inner, leaf, dims, n)
        case "prim" if t.name in ("Int", "Seat"):
            return leaf
    return TOP


def _var_fixpoint(analysis: _Analysis, ir: dict[str, Any]) -> None:
    def dims(t: Type) -> int | None:
        w, h = (d if isinstance(d, int) else analysis.params.get(d) for d in t.dims)
        return w * h if isinstance(w, int) and isinstance(h, int) else None

    state = ir.get("state", [])
    declared: dict[str, Any] = {}
    for v in state:
        t = analysis.types.parse(v["type"])
        rng = _declared(v, analysis)
        if rng is not None:
            declared[v["name"]] = _with_leaf(t, rng, dims, analysis.n)
        init = analysis.expr(v["init"], {"$owner": analysis.seat()})
        if t.kind == "per_player":
            init = Col(init, analysis.n)
        elif t.kind == "grid":
            init = Col(init, dims(t))
        analysis.var_abs[v["name"]] = declared.get(v["name"], init)

    def stmts(block: list[Any], env: dict[str, Any], out: dict[str, list[Any]]) -> None:
        for s in block:
            op, a = s[0], s[1:]
            match op:
                case "let":
                    env = {**env, a[0]: analysis.expr(a[1], env)}
                case "assign" | "roll" | "random_choice" | "sample":
                    target, depth = a[0], 0
                    while target[0] != "var":
                        depth += target[0] == "index"
                        target = target[1]
                    name = target[1]
                    if op == "assign":
                        value = analysis.expr(a[1], env)
                    elif op == "roll":
                        value = Iv(1, _iv(analysis.expr(a[1], env)).hi)
                    elif op == "random_choice":
                        c = analysis.expr(a[1], env)
                        value = c.elem if isinstance(c, Col) else TOP
                    else:
                        value = TOP
                    out.setdefault(name, []).append((depth, value))
                case "if":
                    stmts(a[1], env, out)
                    if len(a) > 2 and a[2]:
                        stmts(a[2], env, out)
                case "for":
                    c = analysis.expr(a[1], env)
                    stmts(a[2], {**env, a[0]: c.elem if isinstance(c, Col) else TOP}, out)

    for iteration in range(12):
        writes: dict[str, list[tuple[int, Any]]] = {}
        for block, action in _blocks(ir):
            env: dict[str, Any] = {}
            if action is not None:
                for p in action.get("params", []):
                    d = analysis.expr(p["domain"], env)
                    env[p["name"]] = d.elem if isinstance(d, Col) else TOP
            stmts(block, env, writes)
        changed = False
        for v in state:
            name = v["name"]
            if name in declared or name not in writes:
                continue
            old = analysis.var_abs[name]
            new = old
            for depth, value in writes[name]:
                new = _set_path(new, depth, value)
            if iteration >= 3:
                new = _widen(old, new)
            if new != old:
                analysis.var_abs[name] = new
                changed = True
        analysis._calls.clear()
        if not changed:
            return


# --- Espacio de acciones -----------------------------------------------------------------------


@dataclass
class Block:
    name: str
    params: tuple[str, ...]
    universes: tuple[Universe, ...]
    offset: int

    @property
    def size(self) -> int:
        return math.prod(u.size for u in self.universes)

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "offset": self.offset,
            "size": self.size,
            "params": [
                {"name": p, "universe": u.to_json()}
                for p, u in zip(self.params, self.universes, strict=True)
            ],
        }


@dataclass
class ActionSpace:
    """Los números globales de acción de una partida (ver el módulo)."""

    blocks: list[Block]
    by_node: dict[tuple[str, str], int]  # (nodo, acción) → bloque
    nodes: dict[str, list[int]]  # nodo → sus bloques (el de `pass` incluido en ventanas)

    @property
    def size(self) -> int:
        return sum(b.size for b in self.blocks)

    def encode(self, node: str, action: Action) -> int:
        b = self.blocks[self.by_node[(node, action.name)]]
        args = dict(action.args)
        ranks = [u.rank(args[p]) for p, u in zip(b.params, b.universes, strict=True)]
        strides = _radix(b.universes)
        return b.offset + sum(r * s for r, s in zip(ranks, strides, strict=True))

    def decode(self, node: str, number: int) -> Action:
        for i in self.nodes.get(node, []):
            b = self.blocks[i]
            if b.offset <= number < b.offset + b.size:
                k = number - b.offset
                values = []
                for u, s in zip(b.universes, _radix(b.universes), strict=True):
                    q, k = divmod(k, s)
                    values.append(u.unrank(q))
                if b.name == "pass" and not b.params:
                    return PASS
                return Action(b.name, tuple(zip(b.params, values, strict=True)))
        raise OutsideSpace(f"el número {number} no es una acción del nodo {node}")

    def to_json(self) -> dict[str, Any]:
        return {
            "size": self.size,
            "blocks": [b.to_json() for b in self.blocks],
            "nodes": {
                node: [
                    {"action": action, "block": self.by_node[(node, action)]}
                    for (nd, action) in self.by_node
                    if nd == node
                ]
                for node in self.nodes
            },
        }


def action_space(ir: dict[str, Any], num_players: int, params: dict[str, Any]) -> ActionSpace:
    """El espacio de acciones de una partida. `params` son los valores de todos los parámetros
    (como `State.params`, sin `num_players`)."""
    analysis = _analysis(ir, num_players, params)
    types = analysis.types
    grid = _largest_grid(ir, types, analysis.params)

    blocks: list[Block] = []
    index: dict[str, int] = {}
    by_node: dict[tuple[str, str], int] = {}
    nodes: dict[str, list[int]] = {}

    def block_for(name: str, names: tuple[str, ...], universes: tuple[Universe, ...]) -> int:
        key = name + "|" + "|".join(u.key() for u in universes)
        if key not in index:
            offset = sum(b.size for b in blocks)
            index[key] = len(blocks)
            blocks.append(Block(name, names, universes, offset))
        return index[key]

    def visit(ns: list[dict[str, Any]]) -> None:
        for node in ns:
            for a in node.get("actions", []):
                env: dict[str, Any] = {}
                universes = []
                for p in a.get("params", []):
                    t = types.parse(p["type"])
                    domain = analysis.expr(p["domain"], env)
                    elem = domain.elem if isinstance(domain, Col) else TOP
                    env[p["name"]] = elem
                    where = f"{node['id']}.{a['name']}.{p['name']}"
                    universes.append(_universe(t, p["domain"], elem, types, analysis, grid, where))
                names = tuple(p["name"] for p in a.get("params", []))
                b = block_for(a["name"], names, tuple(universes))
                by_node[(node["id"], a["name"])] = b
                nodes.setdefault(node["id"], []).append(b)
            if node["kind"] == "window":
                b = block_for("pass", (), ())
                by_node[(node["id"], "pass")] = b
                nodes.setdefault(node["id"], []).append(b)
            if node["kind"] == "phase":
                visit(node["nodes"])

    visit(ir["flow"]["nodes"])
    return ActionSpace(blocks, by_node, nodes)


def _universe(
    t: Type,
    domain: Any,
    elem: Any,
    types: TypeTable,
    analysis: _Analysis,
    grid: tuple[int, int] | None,
    where: str,
) -> Universe:
    match t.kind:
        case "prim":
            match t.name:
                case "Bool":
                    return BoolU()
                case "Seat":
                    return IntU(0, analysis.n - 1)
                case "Int":
                    if isinstance(elem, Iv) and elem.lo is not None and elem.hi is not None:
                        return IntU(elem.lo, max(elem.hi, elem.lo))
                    raise Unbounded(f"{where}: no se puede acotar el entero (dominio {elem})")
                case "Cell":
                    if grid is None:
                        raise Unbounded(f"{where}: casillas sin una rejilla en el estado")
                    return CellU(*grid)
            raise Unbounded(f"{where}: el tipo {t.name} no tiene un universo finito")
        case "enum":
            values = types.enums[t.name]
            if isinstance(elem, Enums) and elem.type == t.name:
                values = tuple(v for v in values if v.ordinal in elem.ordinals)
            return EnumU(values)
        case "struct":
            fields = types.structs[t.name]
            return ProductU(
                tuple(_universe(ft, None, TOP, types, analysis, grid, where) for _, ft in fields),
                t.name,
                tuple(f for f, _ in fields),
            )
        case "tuple":
            return ProductU(
                tuple(_universe(x, None, TOP, types, analysis, grid, where) for x in t.args)
            )
        case "option":
            return OptionU(_universe(t.inner, None, TOP, types, analysis, grid, where))
        case "list" if domain is not None and domain[0] == "subsets":
            inner = _universe(t.inner, None, TOP, types, analysis, grid, where)
            lo = _iv(analysis.expr(domain[2], {})).lo
            hi = _iv(analysis.expr(domain[3], {})).hi
            if lo is None or hi is None:
                raise Unbounded(f"{where}: tamaños de subconjunto sin cota")
            return SubsetU(inner, lo, hi)
    raise Unbounded(f"{where}: el tipo {t.kind} no tiene un universo finito")


def _largest_grid(
    ir: dict[str, Any], types: TypeTable, params: dict[str, Any]
) -> tuple[int, int] | None:
    """(filas, columnas) que abarcan todas las rejillas del estado."""
    rows = cols = 0
    for v in ir.get("state", []):
        t = types.parse(v["type"])
        while t.kind in ("per_player", "list", "option"):
            t = t.inner
        if t.kind != "grid":
            continue
        w, h = (d if isinstance(d, int) else params[d] for d in t.dims)
        rows, cols = max(rows, h), max(cols, w)
    return (rows, cols) if rows and cols else None


def _zone_total(ir: dict[str, Any], analysis: _Analysis) -> int | None:
    """Cota del tamaño de cualquier zona: los movimientos conservan los elementos, así que no
    puede haber más que la suma de los tamaños iniciales (si ninguna asignación crea zonas)."""
    from gamehub.analysis.irwalk import walk_block

    for block, _ in _blocks(ir):
        for stmt in walk_block(block):
            if stmt[0] == "assign":
                target = stmt[1]
                while target[0] != "var":
                    target = target[1]
                var = next(v for v in ir.get("state", []) if v["name"] == target[1])
                t = analysis.types.parse(var["type"])
                while t.kind in ("per_player", "list"):
                    t = t.inner
                if t.kind in ("zone", "bag"):
                    return None
    total = 0
    for v in ir.get("state", []):
        t = analysis.types.parse(v["type"])
        count = 1
        while t.kind in ("per_player", "list"):
            if t.kind == "per_player":
                count *= analysis.n
            t = t.inner
        if t.kind in ("zone", "bag"):
            init = analysis.expr(v["init"], {"$owner": analysis.seat()})
            if not isinstance(init, Col) or init.maxlen is None:
                return None
            total += count * init.maxlen
    return total


# --- Cotas del azar y de los pagos -------------------------------------------------------------


def _analysis(ir: dict[str, Any], num_players: int, params: dict[str, Any]) -> _Analysis:
    types = TypeTable(ir.get("types", []))
    analysis = _Analysis(ir, num_players, dict(params), types)
    analysis.params["num_players"] = num_players
    analysis.functions = {f["name"]: f for f in ir.get("functions", [])}
    analysis.max_enum = max((len(v) for v in types.enums.values()), default=1)
    analysis.zone_total = _zone_total(ir, analysis)
    _var_fixpoint(analysis, ir)
    return analysis


def chance_bound(ir: dict[str, Any], num_players: int, params: dict[str, Any]) -> int | None:
    """Cota del número de opciones de un solo sorteo (barajar una zona, tirar un dado, elegir de
    una colección), o None si no se puede acotar. Sirve para presentar el azar sorteo a sorteo."""
    from gamehub.analysis.irwalk import all_nodes, walk_block

    analysis = _analysis(ir, num_players, params)
    blocks = [ir["flow"].get("setup", [])]
    blocks += [n.get("effects", []) for n, _ in all_nodes(ir) if n["kind"] == "chance"]
    best = 0
    for block in blocks:
        for stmt in walk_block(block):
            match stmt[0]:
                case "shuffle":
                    bound = analysis.zone_total
                case "roll":
                    bound = _iv(analysis.expr(stmt[2], {})).hi
                case "random_choice" | "sample":
                    c = analysis.expr(stmt[2], {})
                    bound = c.maxlen if isinstance(c, Col) else None
                case _:
                    continue
            if bound is None:
                return None
            best = max(best, bound)
    return best


def payoff_bounds(
    ir: dict[str, Any], num_players: int, params: dict[str, Any]
) -> tuple[int | None, int | None]:
    """Cotas (mínimo, máximo) de los pagos de cualquier asiento, o None donde no se sabe."""
    from gamehub.analysis.irwalk import all_nodes

    analysis = _analysis(ir, num_players, params)
    los: list[int | None] = []
    his: list[int | None] = []
    for node, _ in all_nodes(ir):
        if node["kind"] != "terminal":
            continue
        payoff = analysis.expr(node["payoff"], {})
        elem = _iv(payoff.elem if isinstance(payoff, Col) else TOP)
        los.append(elem.lo)
        his.append(elem.hi)
    lo = None if not los or None in los else min(x for x in los if x is not None)
    hi = None if not his or None in his else max(x for x in his if x is not None)
    return lo, hi


__all__ = [
    "ActionSpace",
    "Block",
    "OutsideSpace",
    "Unbounded",
    "Universe",
    "action_space",
    "chance_bound",
    "payoff_bounds",
]
