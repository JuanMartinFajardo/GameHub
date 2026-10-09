# SPDX-License-Identifier: Apache-2.0
"""Funciones predefinidas de Nomos: tipo del resultado y traducción a la IR.

Casi todas corresponden 1:1 con un operador del catálogo (`spec/ir/v0/ops.json`); algunas tienen
nombre de Nomos (`next` → `next_seat`, `other` → `other_seat`, `max(x in xs : e)` → `max_of`).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from gamehub.lang import ast
from gamehub.lang import types as T
from gamehub.lang.source import Span
from gamehub.lang.types import Ty

if TYPE_CHECKING:
    from gamehub.lang.checker import Checker, Ctx, Scope, Typed

Builtin = Callable[["Checker", ast.Call, "Scope", "Ctx", "Ty | None"], "Typed"]
BUILTINS: dict[str, Builtin] = {}

#: Forma con variable ligada → operador de la IR.
AGGREGATES = {
    "all": "all",
    "any": "any",
    "count": "count",
    "sum": "sum",
    "max": "max_of",
    "min": "min_of",
    "argmax": "argmax",
    "argmin": "argmin",
    "sort_by": "sort_by",
    "map": "map",
    "filter": "filter",
    "flat_map": "flat_map",
}

#: Variable ligada de las formas abreviadas `sum(xs)`, `max(xs)`, `min(xs)`.
SHORT_BINDER = "x"


def builtin(*names: str) -> Callable[[Builtin], Builtin]:
    def register(fn: Builtin) -> Builtin:
        for name in names:
            BUILTINS[name] = fn
        return fn

    return register


def _args(
    c: Checker,
    call: ast.Call,
    scope: Scope,
    ctx: Ctx,
    count: int,
    hints: list[Ty | None] | None = None,
) -> list[Typed] | None:
    if len(call.args) != count:
        c.error(
            "E207",
            f"{call.func} recibe {count} argumento(s) y se le pasan {len(call.args)}",
            call.span,
        )
        return None
    wanted: list[Ty | None] = hints if hints is not None else [None] * count
    return [c.expr(a, scope, ctx, h) for a, h in zip(call.args, wanted, strict=True)]


def _err(c: Checker, message: str, span: Span, help: str | None = None) -> Typed:
    return c.error("E301", message, span, help=help)


def _kind(c: Checker, typed: Typed, kinds: tuple[str, ...], what: str, span: Span) -> Ty | None:
    _, ty = typed
    if ty.is_unknown:
        return ty
    if ty.kind not in kinds:
        c.error("E301", f"{what}, no `{ty}`", span)
        return None
    return ty


# --- Colecciones --------------------------------------------------------------------------------


@builtin("len")
def _len(c: Checker, call: ast.Call, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
    a = _args(c, call, scope, ctx, 1)
    if a is None:
        return ["const", None], T.UNKNOWN
    kinds = ("list", "set", "map", "Text", "per_player", "zone", "bag")
    _kind(c, a[0], kinds, "len espera una colección o un texto", call.args[0].span)
    return ["len", a[0][0]], T.INT


@builtin("size", "items", "top")
def _zone_ops(c: Checker, call: ast.Call, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
    a = _args(c, call, scope, ctx, 1)
    if a is None:
        return ["const", None], T.UNKNOWN
    ir, ty = a[0]
    kinds = ("zone",) if call.func == "top" else ("zone", "bag")
    what = (
        "top espera una Zone (las bolsas no tienen orden)"
        if call.func == "top"
        else (f"{call.func} espera una Zone o una Bag")
    )
    checked = _kind(c, a[0], kinds, what, call.args[0].span)
    item = ty.inner if checked is not None and not checked.is_unknown else T.UNKNOWN
    if call.func == "size":
        return ["size", ir], T.INT
    if call.func == "items":
        return ["items", ir], T.list_(item)
    return ["top", ir], item


@builtin("first", "last", "reverse", "distinct")
def _list_ops(c: Checker, call: ast.Call, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
    a = _args(c, call, scope, ctx, 1)
    if a is None:
        return ["const", None], T.UNKNOWN
    ir, ty = a[0]
    checked = _kind(c, a[0], ("list",), f"{call.func} espera una lista", call.args[0].span)
    item = ty.inner if checked is not None and not checked.is_unknown else T.UNKNOWN
    if call.func in ("first", "last"):
        return [call.func, ir], item
    return [call.func, ir], T.list_(item)


@builtin("only")
def _only(c: Checker, call: ast.Call, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
    a = _args(c, call, scope, ctx, 1)
    if a is None:
        return ["const", None], T.UNKNOWN
    ir, ty = a[0]
    return ["only", ir], c.iterable(ty, call.args[0].span)


@builtin("append")
def _append(c: Checker, call: ast.Call, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
    if len(call.args) != 2:
        return c.error("E207", "append(lista, elemento)", call.span)
    xs_ir, xs = c.expr(call.args[0], scope, ctx, expected)
    if xs.kind != "list" and not xs.is_unknown:
        return _err(c, f"append espera una lista, no `{xs}`", call.args[0].span)
    item = xs.inner if xs.kind == "list" else T.UNKNOWN
    x = c.expect(c.expr(call.args[1], scope, ctx, item), item, call.args[1].span)
    return ["append", xs_ir, x], xs


@builtin("concat")
def _concat(c: Checker, call: ast.Call, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
    a = _args(c, call, scope, ctx, 2, [expected, expected])
    if a is None:
        return ["const", None], T.UNKNOWN
    (l_ir, left), (r_ir, right) = a
    result = T.join(left, right)
    if result is None or result.kind not in ("list", "unknown"):
        return _err(c, f"concat une dos listas del mismo tipo, no `{left}` y `{right}`", call.span)
    return ["concat", l_ir, r_ir], result


@builtin("union", "intersection", "difference")
def _set_ops(c: Checker, call: ast.Call, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
    a = _args(c, call, scope, ctx, 2)
    if a is None:
        return ["const", None], T.UNKNOWN
    (l_ir, left), (r_ir, right) = a
    li = c.iterable(left, call.args[0].span)
    ri = c.iterable(right, call.args[1].span)
    item = T.join(li, ri)
    if item is None:
        return _err(c, f"{call.func} de colecciones de `{li}` y `{ri}`", call.span)
    if call.func == "difference":
        return ["difference", l_ir, r_ir], T.list_(li)
    return [call.func, l_ir, r_ir], T.set_(item)


@builtin("subsets")
def _subsets(c: Checker, call: ast.Call, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
    a = _args(c, call, scope, ctx, 3, [None, T.INT, T.INT])
    if a is None:
        return ["const", None], T.UNKNOWN
    (coll_ir, coll), lo, hi = a
    item = c.iterable(coll, call.args[0].span)
    lo_ir = c.expect(lo, T.INT, call.args[1].span)
    hi_ir = c.expect(hi, T.INT, call.args[2].span)
    return ["subsets", coll_ir, lo_ir, hi_ir], T.list_(T.list_(item))


@builtin("range")
def _range(c: Checker, call: ast.Call, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
    a = _args(c, call, scope, ctx, 2, [T.INT, T.INT])
    if a is None:
        return ["const", None], T.UNKNOWN
    lo = c.expect(a[0], T.INT, call.args[0].span)
    hi = c.expect(a[1], T.INT, call.args[1].span)
    return ["range", lo, hi], T.list_(T.INT)


@builtin("slice")
def _slice(c: Checker, call: ast.Call, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
    a = _args(c, call, scope, ctx, 3, [None, T.INT, T.INT])
    if a is None:
        return ["const", None], T.UNKNOWN
    (xs_ir, xs), lo, hi = a
    if xs.kind != "list" and not xs.is_unknown:
        return _err(c, f"slice espera una lista, no `{xs}`", call.args[0].span)
    return [
        "slice",
        xs_ir,
        c.expect(lo, T.INT, call.args[1].span),
        c.expect(hi, T.INT, call.args[2].span),
    ], xs


@builtin("contains")
def _contains(c: Checker, call: ast.Call, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
    if len(call.args) != 2:
        return c.error("E207", "contains(colección, x)", call.span)
    coll_ir, coll = c.expr(call.args[0], scope, ctx)
    item = c.iterable(coll, call.args[0].span) if coll.kind != "Text" else T.TEXT
    x_ir, x = c.expr(call.args[1], scope, ctx, item)
    if not T.comparable(x, item):
        c.error("E301", f"`{x}` nunca está en una colección de `{item}`", call.span)
    return ["contains", coll_ir, x_ir], T.BOOL


@builtin("set")
def _set(c: Checker, call: ast.Call, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
    hint = expected.inner if expected is not None and expected.kind == "set" else None
    item: Ty = hint or T.UNKNOWN
    irs = []
    for a in call.args:
        ir, ty = c.expr(a, scope, ctx, hint)
        joined = T.join(item, ty)
        if joined is None:
            c.error("E301", f"elementos incompatibles en el conjunto: `{item}` y `{ty}`", a.span)
        else:
            item = joined
        irs.append(ir)
    return ["set", *irs], T.set_(item)


# --- Números ------------------------------------------------------------------------------------


@builtin("abs")
def _abs(c: Checker, call: ast.Call, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
    a = _args(c, call, scope, ctx, 1)
    if a is None:
        return ["const", None], T.UNKNOWN
    ir, ty = a[0]
    if not (ty.is_numeric or ty.is_unknown):
        return _err(c, f"abs espera un número, no `{ty}`", call.args[0].span)
    return ["abs", ir], T.INT if ty.kind == "Seat" else ty


@builtin("min", "max")
def _min_max(c: Checker, call: ast.Call, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
    if len(call.args) == 1:
        return _short_aggregate(c, call, scope, ctx)
    if len(call.args) < 2:
        return c.error("E207", f"{call.func} recibe dos o más números, o una colección", call.span)
    typed = [c.expr(a, scope, ctx) for a in call.args]
    result: Ty = T.UNKNOWN
    for (_, ty), a in zip(typed, call.args, strict=True):
        if not (ty.is_numeric or ty.is_unknown):
            return _err(c, f"{call.func} compara números, no `{ty}`", a.span)
        result = T.join(result, ty) or T.UNKNOWN
    return [call.func, *(ir for ir, _ in typed)], T.INT if result.kind == "Seat" else result


@builtin("sum")
def _sum(c: Checker, call: ast.Call, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
    if len(call.args) != 1:
        return c.error(
            "E207",
            "sum recibe una colección de números o la forma sum(x in xs : expresión)",
            call.span,
        )
    return _short_aggregate(c, call, scope, ctx)


def _short_aggregate(c: Checker, call: ast.Call, scope: Scope, ctx: Ctx) -> Typed:
    """`sum(xs)`, `max(xs)`, `min(xs)` = la forma ligada con la variable `x`."""
    x = ast.Name(SHORT_BINDER, span=call.span)
    inner_scope = scope.child()
    return aggregate(
        c, call.func, SHORT_BINDER, call.args[0], x, inner_scope, ctx, call.span, short=True
    )


@builtin("rat")
def _rat(c: Checker, call: ast.Call, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
    if len(call.args) != 2 or not all(isinstance(a, ast.IntLit | ast.Unary) for a in call.args):
        return c.error("E207", "rat(n, d) recibe dos enteros constantes", call.span)
    values = []
    for a in call.args:
        ir, _ = c.expr(a, scope, ctx)
        if not (isinstance(ir, list) and ir[0] == "const" and isinstance(ir[1], int)):
            return c.error("E207", "rat(n, d) recibe dos enteros constantes", a.span)
        values.append(ir[1])
    n, d = values
    if d <= 0:
        return c.error("E301", "el denominador de rat debe ser positivo", call.span)
    return ["rat", n, d], T.REAL


# --- Opcionales y enumerados --------------------------------------------------------------------


@builtin("is_none", "unwrap")
def _optional(c: Checker, call: ast.Call, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
    a = _args(c, call, scope, ctx, 1)
    if a is None:
        return ["const", None], T.UNKNOWN
    ir, ty = a[0]
    if ty.kind != "option" and not ty.is_unknown:
        return _err(c, f"{call.func} espera un opcional (T?), no `{ty}`", call.args[0].span)
    if call.func == "is_none":
        return ["is_none", ir], T.BOOL
    return ["unwrap", ir], ty.inner if ty.kind == "option" else T.UNKNOWN


@builtin("ord")
def _ord(c: Checker, call: ast.Call, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
    a = _args(c, call, scope, ctx, 1)
    if a is None:
        return ["const", None], T.UNKNOWN
    ir, ty = a[0]
    if ty.kind != "enum" and not ty.is_unknown:
        return _err(c, f"ord espera un valor de enumerado, no `{ty}`", call.args[0].span)
    return ["ord", ir], T.INT


# --- Asientos -----------------------------------------------------------------------------------

SEAT_OPS = {"next": "next_seat", "prev": "prev_seat", "other": "other_seat"}


@builtin("next", "prev", "other", "seats_from")
def _seat_ops(c: Checker, call: ast.Call, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
    a = _args(c, call, scope, ctx, 1, [T.SEAT])
    if a is None:
        return ["const", None], T.UNKNOWN
    s = c.expect(a[0], T.SEAT, call.args[0].span)
    if call.func == "seats_from":
        return ["seats_from", s], T.list_(T.SEAT)
    return [SEAT_OPS[call.func], s], T.SEAT


# --- Tableros -----------------------------------------------------------------------------------


def _grid_arg(c: Checker, typed: Typed, span: Span) -> Ty:
    _, ty = typed
    if ty.kind != "grid" and not ty.is_unknown:
        c.error("E301", f"se esperaba una rejilla (Grid), no `{ty}`", span)
        return T.UNKNOWN
    return ty


@builtin("cells")
def _cells(c: Checker, call: ast.Call, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
    a = _args(c, call, scope, ctx, 1)
    if a is None:
        return ["const", None], T.UNKNOWN
    _grid_arg(c, a[0], call.args[0].span)
    return ["cells", a[0][0]], T.list_(T.CELL)


@builtin("lines")
def _lines(c: Checker, call: ast.Call, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
    a = _args(c, call, scope, ctx, 2, [None, T.INT])
    if a is None:
        return ["const", None], T.UNKNOWN
    _grid_arg(c, a[0], call.args[0].span)
    k = c.expect(a[1], T.INT, call.args[1].span)
    return ["lines", a[0][0], k], T.list_(T.list_(T.CELL))


@builtin("neighbors", "in_bounds")
def _grid_cell(c: Checker, call: ast.Call, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
    a = _args(c, call, scope, ctx, 2, [None, T.CELL])
    if a is None:
        return ["const", None], T.UNKNOWN
    _grid_arg(c, a[0], call.args[0].span)
    cell = c.expect(a[1], T.CELL, call.args[1].span)
    if call.func == "neighbors":
        return ["neighbors", a[0][0], cell], T.list_(T.CELL)
    return ["in_bounds", a[0][0], cell], T.BOOL


@builtin("cell")
def _cell(c: Checker, call: ast.Call, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
    a = _args(c, call, scope, ctx, 2, [T.INT, T.INT])
    if a is None:
        return ["const", None], T.UNKNOWN
    return [
        "cell",
        c.expect(a[0], T.INT, call.args[0].span),
        c.expect(a[1], T.INT, call.args[1].span),
    ], T.CELL


# --- Pagos --------------------------------------------------------------------------------------


@builtin("win_loss")
def _win_loss(c: Checker, call: ast.Call, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
    a = _args(c, call, scope, ctx, 3, [T.SEAT, T.REAL, T.REAL])
    if a is None:
        return ["const", None], T.UNKNOWN
    w = c.expect(a[0], T.SEAT, call.args[0].span)
    win = c.expect(a[1], T.REAL, call.args[1].span)
    loss = c.expect(a[2], T.REAL, call.args[2].span)
    return ["win_loss", w, win, loss], T.PAYOFF


@builtin("fill")
def _fill(c: Checker, call: ast.Call, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
    a = _args(c, call, scope, ctx, 1, [T.REAL])
    if a is None:
        return ["const", None], T.UNKNOWN
    return ["fill", c.expect(a[0], T.REAL, call.args[0].span)], T.PAYOFF


# --- Formas con variable ligada -----------------------------------------------------------------


@builtin("all", "any", "count", "argmax", "argmin", "sort_by", "map", "filter", "flat_map")
def _needs_binder(c: Checker, call: ast.Call, scope: Scope, ctx: Ctx, expected: Ty | None) -> Typed:
    return c.error(
        "E207",
        f"{call.func} se escribe con una variable: {call.func}(x in colección : expresión)",
        call.span,
    )


def aggregate(
    c: Checker,
    func: str,
    var: str,
    coll_e: ast.Expr,
    body_e: ast.Expr,
    scope: Scope,
    ctx: Ctx,
    span: Span,
    *,
    short: bool = False,
) -> Typed:
    op = AGGREGATES.get(func)
    if op is None:
        return c.error(
            "E207",
            f"{func} no admite la forma con variable (x in xs : …)",
            span,
            help="formas con variable: " + ", ".join(AGGREGATES),
        )
    coll_ir, coll = c.expr(coll_e, scope, ctx)
    item = c.iterable(coll, coll_e.span)
    inner = scope.child()
    if short:
        inner.names[var] = _binding(item)
    else:
        c.bind(inner, var, "local", item, span)
    want = T.BOOL if op in ("all", "any", "count", "filter") else None
    body_ir, body = c.expr(body_e, inner, ctx, want)
    result: Ty
    match op:
        case "all" | "any" | "count" | "filter":
            c.expect((body_ir, body), T.BOOL, body_e.span)
            result = {"filter": T.list_(item), "count": T.INT}.get(op, T.BOOL)
        case "sum":
            if not (body.is_numeric or body.is_unknown):
                c.error("E301", f"sum suma números, no `{body}`", body_e.span)
            result = (
                T.INT
                if body.kind in ("Int", "Seat")
                else (T.REAL if body.kind == "Real" else T.UNKNOWN)
            )
        case "max_of" | "min_of" | "argmax" | "argmin" | "sort_by":
            if not (body.is_numeric or body.is_unknown or body.kind in ("enum", "Text")):
                c.error(
                    "E301",
                    f"{func} necesita algo ordenable (números, enumerados o textos), no `{body}`",
                    body_e.span,
                )
            result = {
                "max_of": body,
                "min_of": body,
                "argmax": item,
                "argmin": item,
                "sort_by": T.list_(item),
            }[op]
        case "map":
            result = T.list_(body)
        case _:  # flat_map
            inner_item = c.iterable(body, body_e.span)
            result = T.list_(inner_item)
    return [op, var, coll_ir, body_ir], result


def _binding(ty: Ty) -> Any:
    from gamehub.lang.checker import Binding

    return Binding("local", ty)
