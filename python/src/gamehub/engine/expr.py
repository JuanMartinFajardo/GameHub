# SPDX-License-Identifier: Apache-2.0
"""Compilador de expresiones de la IR a funciones Python (`Env → valor`).

Cada operador del catálogo (`spec/ir/v0/ops.json`) tiene aquí su implementación de referencia;
`OPERATORS` debe cubrir el catálogo completo (lo comprueba un test). La semántica exacta de cada
operador está documentada en `docs/wiki/motor.md`.
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Iterable, Sequence
from fractions import Fraction
from itertools import combinations
from typing import Any

from gamehub.engine.env import Env
from gamehub.engine.errors import RuleError
from gamehub.engine.values import (
    EnumValue,
    Grid,
    MapValue,
    SetValue,
    StructValue,
    TypeTable,
    Zone,
    norm_num,
    sort_key,
)

Compiled = Callable[[Env], Any]

#: Resultados guardados como mucho de las funciones que solo dependen de sus argumentos.
STATIC_MEMO_LIMIT = 200_000

# --- Comprobaciones y utilidades ----------------------------------------------------------------


def num(x: Any, op: str) -> Any:
    if isinstance(x, bool) or not isinstance(x, int | Fraction):
        raise RuleError(f"'{op}' espera números, recibe {x!r}")
    return x


def boolean(x: Any, op: str) -> bool:
    if not isinstance(x, bool):
        raise RuleError(f"'{op}' espera un booleano, recibe {x!r}")
    return x


def seat(x: Any, n: int, op: str) -> int:
    if isinstance(x, bool) or not isinstance(x, int) or not 0 <= x < n:
        raise RuleError(f"'{op}': asiento inválido {x!r} (hay {n})")
    return x


def iterate(coll: Any, op: str = "iteración") -> Sequence[Any]:
    """Elementos de una colección en orden: listas tal cual, conjuntos/bolsas/mapas (claves)
    en orden canónico, zonas de arriba abajo."""
    if isinstance(coll, tuple):
        return coll
    if isinstance(coll, SetValue):
        return coll.items
    if isinstance(coll, Zone):
        return coll.values()
    if isinstance(coll, MapValue):
        return tuple(k for k, _ in coll.items)
    raise RuleError(f"'{op}' espera una colección, recibe {coll!r}")


def compare(a: Any, b: Any, op: str) -> int:
    """Orden de la IR: números, enums del mismo tipo (orden de declaración) y textos."""
    if isinstance(a, EnumValue) and isinstance(b, EnumValue) and a.type == b.type:
        return (a.ordinal > b.ordinal) - (a.ordinal < b.ordinal)
    if isinstance(a, str) and isinstance(b, str):
        return (a > b) - (a < b)
    x, y = num(a, op), num(b, op)
    return (x > y) - (x < y)


def sub_multisets(values: Sequence[Any], lo: int, hi: int) -> tuple[tuple[Any, ...], ...]:
    """Sub-multiconjuntos distintos de tamaño lo..hi, en orden canónico: por tamaño y, dentro de
    cada tamaño, combinaciones lexicográficas sobre los elementos ordenados canónicamente."""
    ordered = sorted(values, key=sort_key)
    # Sin elementos repetidos, las combinaciones ya son distintas: no hace falta deduplicar.
    distinct = len(set(ordered)) == len(ordered)
    result: list[tuple[Any, ...]] = []
    for size in range(max(lo, 0), min(hi, len(ordered)) + 1):
        combos = combinations(ordered, size)
        result.extend(combos if distinct else dict.fromkeys(combos))
    return tuple(result)


def is_sub_multiset(candidate: Sequence[Any], values: Sequence[Any]) -> bool:
    remaining = list(values)
    for x in candidate:
        if x not in remaining:
            return False
        remaining.remove(x)
    return True


def grid_lines(g: Grid, k: int) -> tuple[tuple[tuple[int, int], ...], ...]:
    """Líneas rectas de longitud k: horizontales, verticales, diagonales ↘ y diagonales ↙;
    dentro de cada dirección, por casilla inicial en orden de filas."""
    lines: list[tuple[tuple[int, int], ...]] = []
    for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
        for r in range(g.height):
            for c in range(g.width):
                end = (r + dr * (k - 1), c + dc * (k - 1))
                if k >= 1 and g.in_bounds(end):
                    lines.append(tuple((r + dr * i, c + dc * i) for i in range(k)))
    return tuple(lines)


def grid_cells(g: Grid) -> tuple[tuple[int, int], ...]:
    return tuple((r, c) for r in range(g.height) for c in range(g.width))


def index_value(coll: Any, key: Any) -> Any:
    kind = type(coll)
    if kind is tuple and type(key) is int and 0 <= key < len(coll):
        return coll[key]
    if kind is Grid and type(key) is tuple and len(key) == 2:
        r, c = key
        if type(r) is int and type(c) is int and 0 <= r < coll.height and 0 <= c < coll.width:
            return coll.cells[r * coll.width + c]
    if isinstance(coll, tuple):
        if isinstance(key, bool) or not isinstance(key, int) or not 0 <= key < len(coll):
            raise RuleError(f"índice fuera de rango: {key!r} (longitud {len(coll)})")
        return coll[key]
    if isinstance(coll, Grid):
        return coll.get(key)
    if isinstance(coll, MapValue):
        return coll.get(key)
    raise RuleError(f"no se puede indexar {coll!r}")


def _expect(cond: bool, message: str) -> None:
    if not cond:
        raise RuleError(message)


# --- Compilador --------------------------------------------------------------------------------


class ExprCompiler:
    def __init__(self, types: TypeTable, var_index: dict[str, int] | None = None) -> None:
        self.types = types
        self.var_index = var_index or {}

    def compile(self, e: Any) -> Compiled:
        op, args = e[0], e[1:]
        builder = OPERATORS.get(op)
        if builder is None:
            raise NotImplementedError(f"operador sin implementar: {op}")
        return builder(self, args)

    def many(self, args: Iterable[Any]) -> list[Compiled]:
        return [self.compile(a) for a in args]


Builder = Callable[[ExprCompiler, list[Any]], Compiled]
OPERATORS: dict[str, Builder] = {}


def op(*names: str) -> Callable[[Builder], Builder]:
    def register(fn: Builder) -> Builder:
        for name in names:
            OPERATORS[name] = fn
        return fn

    return register


def pure(name: str, fn: Callable[..., Any]) -> None:
    """Registra un operador cuyos argumentos son todos expresiones y que solo depende de ellos."""

    def build(c: ExprCompiler, args: list[Any]) -> Compiled:
        compiled = c.many(args)
        if len(compiled) == 1:
            (a,) = compiled
            return lambda env: fn(a(env))
        if len(compiled) == 2:
            a, b = compiled
            return lambda env: fn(a(env), b(env))
        return lambda env: fn(*(x(env) for x in compiled))

    OPERATORS[name] = build


def seated(name: str, fn: Callable[..., Any]) -> None:
    """Como `pure`, pero la función recibe además el nº de asientos."""

    def build(c: ExprCompiler, args: list[Any]) -> Compiled:
        compiled = c.many(args)
        return lambda env: fn(env.ctx.n, *(x(env) for x in compiled))

    OPERATORS[name] = build


def fast_int(name: str, fast: Callable[[int, int], Any], slow: Callable[..., Any]) -> None:
    """Como `pure`, con un atajo cuando hay dos argumentos y los dos son enteros (no booleanos):
    es el caso de casi toda la aritmética de casillas y contadores. `slow` da el resultado (y
    los errores) en los demás casos."""

    def build(c: ExprCompiler, args: list[Any]) -> Compiled:
        compiled = c.many(args)
        if len(compiled) != 2:
            return lambda env: slow(*(x(env) for x in compiled))
        a, b = compiled

        def f(env: Env) -> Any:
            x, y = a(env), b(env)
            if type(x) is int and type(y) is int:
                return fast(x, y)
            return slow(x, y)

        return f

    OPERATORS[name] = build


# Referencias y literales


@op("const")
def _const(c: ExprCompiler, args: list[Any]) -> Compiled:
    value = args[0]
    return lambda env: value


@op("rat")
def _rat(c: ExprCompiler, args: list[Any]) -> Compiled:
    n, d = args
    if d <= 0:
        raise RuleError(f"racional con denominador no positivo: {n}/{d}")
    value = norm_num(Fraction(n, d))
    return lambda env: value


@op("enum")
def _enum(c: ExprCompiler, args: list[Any]) -> Compiled:
    value = c.types.enum_value(args[0], args[1])
    return lambda env: value


@op("var")
def _var(c: ExprCompiler, args: list[Any]) -> Compiled:
    i = c.var_index[args[0]]
    return lambda env: env.ctx.store[i]


@op("param")
def _param(c: ExprCompiler, args: list[Any]) -> Compiled:
    name = args[0]
    return lambda env: env.ctx.params[name]


@op("arg")
def _arg(c: ExprCompiler, args: list[Any]) -> Compiled:
    name = args[0]
    return lambda env: env.args[name]


@op("local")
def _local(c: ExprCompiler, args: list[Any]) -> Compiled:
    name = args[0]
    return lambda env: env.locals[name]


def _context(attr: str, label: str) -> Builder:
    def build(c: ExprCompiler, args: list[Any]) -> Compiled:
        def get(env: Env) -> Any:
            value = getattr(env, attr)
            if value is None:
                raise RuleError(f"'{label}' no está definido en este contexto")
            return value

        return get

    return build


OPERATORS["actor"] = _context("actor", "actor")
OPERATORS["viewer"] = _context("viewer", "viewer")
OPERATORS["owner"] = _context("owner", "owner")
OPERATORS["item_face_up"] = _context("face_up", "item_face_up")


@op("seats")
def _seats(c: ExprCompiler, args: list[Any]) -> Compiled:
    return lambda env: tuple(range(env.ctx.n))


@op("at")
def _at(c: ExprCompiler, args: list[Any]) -> Compiled:
    node = args[0]
    return lambda env: node in env.ctx.path


# Constructores

pure("list", lambda *xs: tuple(xs))
pure("set", lambda *xs: SetValue.of(xs))
pure("tuple", lambda *xs: tuple(xs))
fast_int("cell", lambda r, col: (r, col), lambda r, col: (num(r, "cell"), num(col, "cell")))


@op("struct")
def _struct(c: ExprCompiler, args: list[Any]) -> Compiled:
    type_name, fields = args
    order = [name for name, _ in c.types.structs[type_name]]
    compiled = [(name, c.compile(fields[name])) for name in order]
    return lambda env: StructValue(type_name, tuple((k, f(env)) for k, f in compiled))


# Aritmética (exacta)


def _add(*xs: Any) -> Any:
    return norm_num(sum((num(x, "add") for x in xs), start=0))


def _mul(*xs: Any) -> Any:
    return norm_num(functools.reduce(lambda a, b: a * b, (num(x, "mul") for x in xs), 1))


def _div(a: Any, b: Any) -> Any:
    if num(b, "div") == 0:
        raise RuleError("división por cero")
    return norm_num(Fraction(num(a, "div")) / b)


def _idiv(a: Any, b: Any) -> Any:
    if num(b, "idiv") == 0:
        raise RuleError("división por cero")
    return norm_num(Fraction(num(a, "idiv")) // b)


def _mod(a: Any, b: Any) -> Any:
    if num(b, "mod") == 0:
        raise RuleError("módulo por cero")
    return norm_num(num(a, "mod") % b)


fast_int("add", int.__add__, _add)
fast_int("sub", int.__sub__, lambda a, b: norm_num(num(a, "sub") - num(b, "sub")))
fast_int("mul", int.__mul__, _mul)
pure("div", _div)
pure("idiv", _idiv)
pure("mod", _mod)
pure("neg", lambda a: norm_num(-num(a, "neg")))
pure("abs", lambda a: norm_num(abs(num(a, "abs"))))
pure("min", lambda *xs: min(num(x, "min") for x in xs))
pure("max", lambda *xs: max(num(x, "max") for x in xs))

# Comparación

pure("eq", lambda a, b: a == b)
pure("ne", lambda a, b: a != b)
fast_int("lt", int.__lt__, lambda a, b: compare(a, b, "lt") < 0)
fast_int("le", int.__le__, lambda a, b: compare(a, b, "le") <= 0)
fast_int("gt", int.__gt__, lambda a, b: compare(a, b, "gt") > 0)
fast_int("ge", int.__ge__, lambda a, b: compare(a, b, "ge") >= 0)

# Lógica y control


@op("and")
def _and(c: ExprCompiler, args: list[Any]) -> Compiled:
    compiled = c.many(args)

    def f(env: Env) -> bool:
        for x in compiled:
            v = x(env)
            if v is False:
                return False
            if v is not True:
                boolean(v, "and")
        return True

    return f


@op("or")
def _or(c: ExprCompiler, args: list[Any]) -> Compiled:
    compiled = c.many(args)

    def f(env: Env) -> bool:
        for x in compiled:
            v = x(env)
            if v is True:
                return True
            if v is not False:
                boolean(v, "or")
        return False

    return f


pure("not", lambda a: not boolean(a, "not"))


@op("if")
def _if(c: ExprCompiler, args: list[Any]) -> Compiled:
    cond, then, other = c.many(args)

    def f(env: Env) -> Any:
        v = cond(env)
        if v is True:
            return then(env)
        if v is False:
            return other(env)
        boolean(v, "if")
        raise AssertionError

    return f


@op("case")
def _case(c: ExprCompiler, args: list[Any]) -> Compiled:
    cases = [(c.compile(cond), c.compile(value)) for cond, value in args[0]]
    default = c.compile(args[1])

    def f(env: Env) -> Any:
        for cond, value in cases:
            if boolean(cond(env), "case"):
                return value(env)
        return default(env)

    return f


@op("let")
def _let(c: ExprCompiler, args: list[Any]) -> Compiled:
    name, value_e, body_e = args
    value, body = c.compile(value_e), c.compile(body_e)
    return lambda env: body(env.bind(name, value(env)))


# Opcionales


def _unwrap(x: Any) -> Any:
    if x is None:
        raise RuleError("'unwrap' sobre un opcional vacío")
    return x


pure("is_none", lambda x: x is None)
pure("unwrap", _unwrap)

# Colecciones


def _len(x: Any) -> int:
    if isinstance(x, tuple | str | Zone):
        return len(x)
    if isinstance(x, SetValue | MapValue):
        return len(x.items)
    raise RuleError(f"'len' no aplicable a {x!r}")


def _contains(coll: Any, x: Any) -> bool:
    if isinstance(coll, str):
        return isinstance(x, str) and x in coll
    return x in iterate(coll, "contains")


def _non_empty(xs: Sequence[Any], op_name: str) -> Sequence[Any]:
    _expect(len(xs) > 0, f"'{op_name}' sobre una colección vacía")
    return xs


def _only(coll: Any) -> Any:
    items = iterate(coll, "only")
    _expect(len(items) == 1, f"'only' espera exactamente un elemento, hay {len(items)}")
    return items[0]


def _list(x: Any, op_name: str) -> tuple[Any, ...]:
    if not isinstance(x, tuple):
        raise RuleError(f"'{op_name}' espera una lista, recibe {x!r}")
    return x


def _slice(xs: Any, lo: Any, hi: Any) -> tuple[Any, ...]:
    xs = _list(xs, "slice")
    return xs[max(num(lo, "slice"), 0) : max(num(hi, "slice"), 0)]


def _as_set(x: Any, op_name: str) -> SetValue:
    return x if isinstance(x, SetValue) else SetValue.of(iterate(x, op_name))


def _subsets(coll: Any, lo: Any, hi: Any) -> tuple[tuple[Any, ...], ...]:
    return sub_multisets(iterate(coll, "subsets"), num(lo, "subsets"), num(hi, "subsets"))


pure("len", _len)
pure("contains", _contains)
pure("index", index_value)
pure("first", lambda xs: _non_empty(_list(xs, "first"), "first")[0])
pure("last", lambda xs: _non_empty(_list(xs, "last"), "last")[-1])
pure("only", _only)
pure("append", lambda xs, x: (*_list(xs, "append"), x))
pure("concat", lambda a, b: _list(a, "concat") + _list(b, "concat"))
pure("range", lambda lo, hi: tuple(range(num(lo, "range"), num(hi, "range") + 1)))
pure("slice", _slice)
pure("reverse", lambda xs: tuple(reversed(_list(xs, "reverse"))))
pure("distinct", lambda xs: tuple(dict.fromkeys(_list(xs, "distinct"))))
pure("union", lambda a, b: SetValue.of((*_as_set(a, "union").items, *_as_set(b, "union").items)))
pure(
    "intersection",
    lambda a, b: SetValue.of(x for x in _as_set(a, "intersection").items if x in iterate(b)),
)
pure(
    "difference",
    lambda a, b: tuple(x for x in iterate(a, "difference") if x not in iterate(b, "difference")),
)
pure("subsets", _subsets)


@op("field")
def _field(c: ExprCompiler, args: list[Any]) -> Compiled:
    value, name = c.compile(args[0]), args[1]

    def f(env: Env) -> Any:
        v = value(env)
        if not isinstance(v, StructValue):
            raise RuleError(f"'field' espera un struct, recibe {v!r}")
        return v.get(name)

    return f


# Comprensiones (el último argumento es el cuerpo, con la variable ligada)


def comprehension(name: str, reduce: Callable[[str, Sequence[Any], Callable[[Any], Any]], Any]):
    def build(c: ExprCompiler, args: list[Any]) -> Compiled:
        binder, coll_e, body_e = args
        coll, body = c.compile(coll_e), c.compile(body_e)

        def f(env: Env) -> Any:
            items = iterate(coll(env), name)
            # Un solo ámbito para todos los elementos: el cuerpo se evalúa entero antes de pasar
            # al siguiente (las reducciones no guardan nada que lo use después).
            scope = env.bind(binder, None)
            local = scope.locals

            def apply(x: Any) -> Any:
                local[binder] = x
                return body(scope)

            return reduce(name, items, apply)

        return f

    OPERATORS[name] = build


def _arg_best(sign: int) -> Callable[[str, Sequence[Any], Callable[[Any], Any]], Any]:
    def reduce(name: str, items: Sequence[Any], body: Callable[[Any], Any]) -> Any:
        best, best_key = None, None
        for x in _non_empty(items, name):
            key = body(x)
            if best_key is None or compare(key, best_key, name) * sign > 0:
                best, best_key = x, key
        return best

    return reduce


def _best_of(sign: int) -> Callable[[str, Sequence[Any], Callable[[Any], Any]], Any]:
    def reduce(name: str, items: Sequence[Any], body: Callable[[Any], Any]) -> Any:
        values = [body(x) for x in _non_empty(items, name)]
        best = values[0]
        for v in values[1:]:
            if compare(v, best, name) * sign > 0:
                best = v
        return best

    return reduce


def _sort_by(name: str, items: Sequence[Any], body: Callable[[Any], Any]) -> tuple[Any, ...]:
    keyed = [(body(x), x) for x in items]
    keyed.sort(key=functools.cmp_to_key(lambda a, b: compare(a[0], b[0], name)))
    return tuple(x for _, x in keyed)


def _flat_map(name: str, items: Sequence[Any], body: Callable[[Any], Any]) -> tuple[Any, ...]:
    return tuple(y for x in items for y in iterate(body(x), name))


comprehension("all", lambda n, xs, f: all(boolean(f(x), n) for x in xs))
comprehension("any", lambda n, xs, f: any(boolean(f(x), n) for x in xs))
comprehension("count", lambda n, xs, f: sum(1 for x in xs if boolean(f(x), n)))
comprehension("sum", lambda n, xs, f: norm_num(sum((num(f(x), n) for x in xs), start=0)))
comprehension("map", lambda n, xs, f: tuple(f(x) for x in xs))
comprehension("flat_map", _flat_map)
comprehension("filter", lambda n, xs, f: tuple(x for x in xs if boolean(f(x), n)))
comprehension("argmax", _arg_best(+1))
comprehension("argmin", _arg_best(-1))
comprehension("max_of", _best_of(+1))
comprehension("min_of", _best_of(-1))
comprehension("sort_by", _sort_by)

# Asientos


def _other_seat(n: int, s: Any) -> int:
    _expect(n == 2, "'other_seat' solo existe en partidas de 2 jugadores")
    return 1 - seat(s, n, "other_seat")


seated("next_seat", lambda n, s: (seat(s, n, "next_seat") + 1) % n)
seated("prev_seat", lambda n, s: (seat(s, n, "prev_seat") - 1) % n)
seated("other_seat", _other_seat)
seated("seats_from", lambda n, s: tuple((seat(s, n, "seats_from") + i) % n for i in range(n)))

# Tableros


def _grid(g: Any, op_name: str) -> Grid:
    if not isinstance(g, Grid):
        raise RuleError(f"'{op_name}' espera una rejilla, recibe {g!r}")
    return g


def _neighbors(g: Any, cell: Any) -> tuple[tuple[int, int], ...]:
    g = _grid(g, "neighbors")
    r, col = cell
    around = [(r + dr, col + dc) for dr in (-1, 0, 1) for dc in (-1, 0, 1) if dr or dc]
    return tuple(x for x in around if g.in_bounds(x))


pure("cells", lambda g: grid_cells(_grid(g, "cells")))
pure("lines", lambda g, k: grid_lines(_grid(g, "lines"), num(k, "lines")))
pure("neighbors", _neighbors)
pure("in_bounds", lambda g, cell: _grid(g, "in_bounds").in_bounds(cell))

# Zonas


def _zone(z: Any, op_name: str) -> Zone:
    if not isinstance(z, Zone):
        raise RuleError(f"'{op_name}' espera una zona o bolsa, recibe {z!r}")
    return z


def _top(z: Any) -> Any:
    z = _zone(z, "top")
    _expect(z.ordered, "'top' no tiene sentido en una bolsa (no tiene orden)")
    _expect(len(z) > 0, "'top' sobre una zona vacía")
    return z.items[0].value


pure("size", lambda z: len(_zone(z, "size")))
pure("items", lambda z: _zone(z, "items").values())
pure("top", _top)

# Enumerados


@op("enum_values")
def _enum_values(c: ExprCompiler, args: list[Any]) -> Compiled:
    values = c.types.enums[args[0]]
    return lambda env: values


def _ord(x: Any) -> int:
    if not isinstance(x, EnumValue):
        raise RuleError(f"'ord' espera un valor de enumerado, recibe {x!r}")
    return x.ordinal


pure("ord", _ord)

# Funciones


@op("call")
def _call(c: ExprCompiler, args: list[Any]) -> Compiled:
    name, arg_exprs = args[0], c.many(args[1:])

    def f(env: Env) -> Any:
        ctx = env.ctx
        game = ctx.game
        fn = game.functions[name]
        values = [a(env) for a in arg_exprs]
        kind = fn.memo
        if kind is None:
            return fn.body(Env(ctx, args=dict(zip(fn.params, values, strict=True))))
        if kind == "static":
            memo = game.static_memo
            if len(memo) > STATIC_MEMO_LIMIT:
                memo.clear()
        else:
            memo = ctx.memo
            if memo is None:
                return fn.body(Env(ctx, args=dict(zip(fn.params, values, strict=True))))
        key = (name, *values)
        try:
            return memo[key]
        except KeyError:
            pass
        result = fn.body(Env(ctx, args=dict(zip(fn.params, values, strict=True))))
        memo[key] = result
        return result

    return f


# Pagos

seated(
    "win_loss",
    lambda n, w, win, loss: tuple(
        norm_num(num(win, "win_loss") if s == seat(w, n, "win_loss") else num(loss, "win_loss"))
        for s in range(n)
    ),
)
seated("fill", lambda n, v: (norm_num(num(v, "fill")),) * n)
