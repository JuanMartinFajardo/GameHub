# SPDX-License-Identifier: Apache-2.0
"""Generador de código: expresiones y funciones de la IR → funciones de Python (ADR-063).

El compilador de referencia (`gamehub.engine.expr`) convierte cada expresión en un árbol de
cierres: es fácil de leer y de comprobar, pero cada nodo es una llamada y cada local, un
diccionario. Este módulo escribe el mismo cálculo como código fuente de Python (un `def` por
expresión o por función de la IR, con los locales y los argumentos como variables de Python) y lo
compila con `exec`. Llama a **las mismas funciones** de cada operador que los cierres
(`expr.PURE`, `expr.FAST`, `expr.REDUCERS`…), así que da los mismos resultados y los mismos
errores; lo comprueban las trazas de conformidad y partidas al azar de todos los juegos con los
dos compiladores.

Si una expresión usa algo que el generador no sabe escribir, se compila con los cierres (no
cambia nada más que la velocidad). `GAMEHUB_CODEGEN=0` lo desactiva del todo.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from fractions import Fraction
from typing import Any

from gamehub.engine import expr as E
from gamehub.engine.errors import RuleError
from gamehub.engine.values import StructValue, TypeTable, norm_num


class Unsupported(Exception):
    """La expresión usa algo que el generador no escribe: se compila con los cierres."""


def enabled() -> bool:
    return os.environ.get("GAMEHUB_CODEGEN", "1") not in ("0", "false", "no")


def _ctxval(value: Any, label: str) -> Any:
    if value is None:
        raise RuleError(f"'{label}' no está definido en este contexto")
    return value


def _field(value: Any, name: str) -> Any:
    if not isinstance(value, StructValue):
        raise RuleError(f"'field' espera un struct, recibe {value!r}")
    return value.get(name)


def _fast_helper(fast: Callable[[int, int], Any], slow: Callable[..., Any]) -> Callable[..., Any]:
    def helper(x: Any, y: Any) -> Any:
        if type(x) is int and type(y) is int:
            return fast(x, y)
        return slow(x, y)

    return helper


def _base_namespace() -> dict[str, Any]:
    ns: dict[str, Any] = {
        "_iterate": E.iterate,
        "_boolean": E.boolean,
        "_ctxval": _ctxval,
        "_field": _field,
        "_StructValue": StructValue,
    }
    for name, fn in E.PURE.items():
        ns[f"_p_{name}"] = fn
    for name, fn in E.SEATED.items():
        ns[f"_s_{name}"] = fn
    for name, (fast, slow) in E.FAST.items():
        ns[f"_fi_{name}"] = _fast_helper(fast, slow)
        ns[f"_fs_{name}"] = slow
    for name, reduce in E.REDUCERS.items():
        ns[f"_r_{name}"] = reduce
    return ns


_BASE: dict[str, Any] | None = None


def base_namespace() -> dict[str, Any]:
    global _BASE
    if _BASE is None:
        _BASE = _base_namespace()
    return _BASE


class Codegen:
    """Genera las funciones de un juego. `callers` es la tabla de funciones de la IR (nombre →
    función `(ctx, *args)` con su memo): el código generado la consulta al llamar, así que se
    puede rellenar después."""

    def __init__(
        self,
        types: TypeTable,
        var_index: dict[str, int],
        callers: dict[str, Callable[..., Any]],
    ) -> None:
        self.types = types
        self.var_index = var_index
        self.callers = callers

    # --- unidades ---------------------------------------------------------------------------------

    def expression(self, e: Any) -> E.Compiled:
        """Una expresión con el contrato de los cierres: una función del entorno."""
        unit = _Unit(self, mode="env")
        body = unit.expr(e, {})
        return unit.build("env", body, ["ctx = env.ctx"])  # type: ignore[return-value]

    def function(self, params: list[str], body: Any) -> Callable[..., Any]:
        """El cuerpo de una función de la IR como función de Python `(ctx, *args)`."""
        unit = _Unit(self, mode="fn")
        unit.args = {p: f"a{i}" for i, p in enumerate(params)}
        source = unit.expr(body, {})
        signature = ", ".join(["ctx", *unit.args.values()])
        return unit.build(signature, source, [])


class _Unit:
    """Una función generada: su código y sus constantes."""

    def __init__(self, gen: Codegen, mode: str) -> None:
        self.gen = gen
        self.mode = mode  # "env": expresión con entorno; "fn": cuerpo de función
        self.args: dict[str, str] = {}
        self.consts: list[Any] = []
        self.counter = 0

    def build(self, signature: str, body: str, prelude: list[str]) -> Callable[..., Any]:
        lines = [f"def _generated({signature}):"]
        lines += [f"    {line}" for line in prelude]
        lines.append(f"    return {body}")
        namespace = dict(base_namespace())
        namespace["_F"] = self.gen.callers
        for i, value in enumerate(self.consts):
            namespace[f"_k{i}"] = value
        try:
            code = compile("\n".join(lines), "<gamehub-codegen>", "exec")
        except (SyntaxError, RecursionError, MemoryError) as exc:
            raise Unsupported(f"no se puede compilar: {exc}") from None
        exec(code, namespace)
        return namespace["_generated"]

    def const(self, value: Any) -> str:
        self.consts.append(value)
        return f"_k{len(self.consts) - 1}"

    def fresh(self) -> str:
        self.counter += 1
        return f"l{self.counter}"

    # --- expresiones ------------------------------------------------------------------------------

    def expr(self, e: Any, scope: dict[str, str]) -> str:
        if not isinstance(e, list) or not e or not isinstance(e[0], str):
            raise Unsupported(f"expresión mal formada: {e!r}")
        op, args = e[0], e[1:]
        method = getattr(self, f"op_{op}", None)
        if method is not None:
            return method(args, scope)
        if op in E.FAST:
            parts = [self.expr(a, scope) for a in args]
            if len(parts) == 2:
                return f"_fi_{op}({parts[0]}, {parts[1]})"
            return f"_fs_{op}({', '.join(parts)})"
        if op in E.PURE:
            return f"_p_{op}({', '.join(self.expr(a, scope) for a in args)})"
        if op in E.SEATED:
            parts = ["ctx.n", *(self.expr(a, scope) for a in args)]
            return f"_s_{op}({', '.join(parts)})"
        if op in E.REDUCERS:
            binder, coll, body = args
            local = self.fresh()
            inner = {**scope, binder: local}
            return (
                f"_r_{op}({op!r}, _iterate({self.expr(coll, scope)}, {op!r}), "
                f"lambda {local}: {self.expr(body, inner)})"
            )
        raise Unsupported(f"operador sin generador: {op}")

    # Referencias y literales

    def op_const(self, args: list[Any], scope: dict[str, str]) -> str:
        value = args[0]
        if value is None or isinstance(value, bool | int | str):
            return repr(value)
        return self.const(value)

    def op_rat(self, args: list[Any], scope: dict[str, str]) -> str:
        n, d = args
        if d <= 0:
            raise RuleError(f"racional con denominador no positivo: {n}/{d}")
        return self.const(norm_num(Fraction(n, d)))

    def op_enum(self, args: list[Any], scope: dict[str, str]) -> str:
        return self.const(self.gen.types.enum_value(args[0], args[1]))

    def op_enum_values(self, args: list[Any], scope: dict[str, str]) -> str:
        return self.const(self.gen.types.enums[args[0]])

    def op_var(self, args: list[Any], scope: dict[str, str]) -> str:
        return f"ctx.store[{self.gen.var_index[args[0]]}]"

    def op_param(self, args: list[Any], scope: dict[str, str]) -> str:
        return f"ctx.params[{args[0]!r}]"

    def op_arg(self, args: list[Any], scope: dict[str, str]) -> str:
        name = args[0]
        if self.mode == "fn":
            if name not in self.args:
                raise Unsupported(f"argumento desconocido: {name}")
            return self.args[name]
        return f"env.args[{name!r}]"

    def op_local(self, args: list[Any], scope: dict[str, str]) -> str:
        name = args[0]
        if name in scope:
            return scope[name]
        if self.mode == "fn":
            raise Unsupported(f"local libre en una función: {name}")
        return f"env.locals[{name!r}]"

    def _context(self, attr: str, label: str) -> str:
        if self.mode == "fn":
            return f"_ctxval(None, {label!r})"
        return f"_ctxval(env.{attr}, {label!r})"

    def op_actor(self, args: list[Any], scope: dict[str, str]) -> str:
        return self._context("actor", "actor")

    def op_viewer(self, args: list[Any], scope: dict[str, str]) -> str:
        return self._context("viewer", "viewer")

    def op_owner(self, args: list[Any], scope: dict[str, str]) -> str:
        return self._context("owner", "owner")

    def op_item_face_up(self, args: list[Any], scope: dict[str, str]) -> str:
        return self._context("face_up", "item_face_up")

    def op_seats(self, args: list[Any], scope: dict[str, str]) -> str:
        return "tuple(range(ctx.n))"

    def op_at(self, args: list[Any], scope: dict[str, str]) -> str:
        return f"({args[0]!r} in ctx.path)"

    def op_struct(self, args: list[Any], scope: dict[str, str]) -> str:
        type_name, fields = args
        order = [name for name, _ in self.gen.types.structs[type_name]]
        parts = [f"({name!r}, {self.expr(fields[name], scope)})" for name in order]
        inner = ", ".join(parts) + ("," if len(parts) == 1 else "")
        return f"_StructValue({type_name!r}, ({inner}))"

    # Lógica y control

    def op_and(self, args: list[Any], scope: dict[str, str]) -> str:
        if not args:
            return "True"
        return "(" + " and ".join(f"_boolean({self.expr(a, scope)}, 'and')" for a in args) + ")"

    def op_or(self, args: list[Any], scope: dict[str, str]) -> str:
        if not args:
            return "False"
        return "(" + " or ".join(f"_boolean({self.expr(a, scope)}, 'or')" for a in args) + ")"

    def op_if(self, args: list[Any], scope: dict[str, str]) -> str:
        cond, then, other = (self.expr(a, scope) for a in args)
        return f"({then} if _boolean({cond}, 'if') else {other})"

    def op_case(self, args: list[Any], scope: dict[str, str]) -> str:
        result = self.expr(args[1], scope)
        for cond, value in reversed(args[0]):
            c, v = self.expr(cond, scope), self.expr(value, scope)
            result = f"({v} if _boolean({c}, 'case') else {result})"
        return result

    def op_let(self, args: list[Any], scope: dict[str, str]) -> str:
        name, value, body = args
        local = self.fresh()
        inner = self.expr(body, {**scope, name: local})
        return f"(lambda {local}: {inner})({self.expr(value, scope)})"

    def op_field(self, args: list[Any], scope: dict[str, str]) -> str:
        return f"_field({self.expr(args[0], scope)}, {args[1]!r})"

    # Funciones

    def op_call(self, args: list[Any], scope: dict[str, str]) -> str:
        name = args[0]
        parts = ["ctx", *(self.expr(a, scope) for a in args[1:])]
        return f"_F[{name!r}]({', '.join(parts)})"


# --- Llamadas a funciones de la IR con su memo ---------------------------------------------

_MISSING = object()


def caller(
    name: str,
    impl: Callable[..., Any],
    kind: str | None,
    static_memo: dict[Any, Any],
    limit: int,
) -> Callable[..., Any]:
    """La función que usa el código generado para llamar a `name`: `impl(ctx, *args)` con el
    mismo memo que la llamada de los cierres (ver `Ctx.memo` y `game._memo_kinds`)."""
    if kind is None:
        return impl
    if kind == "static":

        def static_call(ctx: Any, *args: Any) -> Any:
            key = (name, *args)
            found = static_memo.get(key, _MISSING)
            if found is _MISSING:
                if len(static_memo) > limit:
                    static_memo.clear()
                found = static_memo[key] = impl(ctx, *args)
            return found

        return static_call

    def state_call(ctx: Any, *args: Any) -> Any:
        memo = ctx.memo
        if memo is None:
            return impl(ctx, *args)
        key = (name, *args)
        found = memo.get(key, _MISSING)
        if found is _MISSING:
            found = memo[key] = impl(ctx, *args)
        return found

    return state_call
