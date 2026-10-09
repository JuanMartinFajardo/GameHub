# SPDX-License-Identifier: Apache-2.0
"""API Python para construir juegos en GameIR: un tercer frente junto al texto Nomos y Studio.

Útil para familias de juegos generadas por programa (matrices aleatorias, tableros
paramétricos) y para escribir juegos antes de que exista el compilador de Nomos (Fase 2).

    from gamehub.build import GameBuilder, T, arg, assign, const, if_, op, p

    g = GameBuilder("tictactoe", "1.0.0", players=2)
    Mark = g.enum("Mark", ["X", "O"])
    board = g.state("board", T.grid(3, 3, T.option("Mark")), const(None))
    ...
    ir = g.build()

Las expresiones son objetos `Expr` con operadores de Python (`+`, `==`, `&`, `|`, `~`, `[]`):
generan S-expresiones de la IR, no ejecutan nada. Usa `&`, `|` y `~` en lugar de `and`, `or` y
`not`, que Python no permite sobrecargar.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from fractions import Fraction
from typing import Any

from gamehub.engine.errors import RuleError

# --- Expresiones --------------------------------------------------------------------------------


class Expr:
    __slots__ = ("sexpr",)
    __hash__ = None  # type: ignore[assignment]

    def __init__(self, sexpr: list[Any]) -> None:
        self.sexpr = sexpr

    def __repr__(self) -> str:
        return f"Expr({self.sexpr!r})"

    def __bool__(self) -> bool:
        raise TypeError(
            "una Expr no es un booleano de Python: usa &, | y ~ (y if_ para condicionales)"
        )

    # aritmética
    def __add__(self, o: Any) -> Expr:
        return op("add", self, o)

    def __radd__(self, o: Any) -> Expr:
        return op("add", o, self)

    def __sub__(self, o: Any) -> Expr:
        return op("sub", self, o)

    def __rsub__(self, o: Any) -> Expr:
        return op("sub", o, self)

    def __mul__(self, o: Any) -> Expr:
        return op("mul", self, o)

    def __rmul__(self, o: Any) -> Expr:
        return op("mul", o, self)

    def __truediv__(self, o: Any) -> Expr:
        return op("div", self, o)

    def __floordiv__(self, o: Any) -> Expr:
        return op("idiv", self, o)

    def __mod__(self, o: Any) -> Expr:
        return op("mod", self, o)

    def __neg__(self) -> Expr:
        return op("neg", self)

    # comparación (devuelven Expr, no bool)
    def __eq__(self, o: object) -> Expr:  # type: ignore[override]
        return op("eq", self, o)

    def __ne__(self, o: object) -> Expr:  # type: ignore[override]
        return op("ne", self, o)

    def __lt__(self, o: Any) -> Expr:
        return op("lt", self, o)

    def __le__(self, o: Any) -> Expr:
        return op("le", self, o)

    def __gt__(self, o: Any) -> Expr:
        return op("gt", self, o)

    def __ge__(self, o: Any) -> Expr:
        return op("ge", self, o)

    # lógica
    def __and__(self, o: Any) -> Expr:
        return op("and", self, o)

    def __or__(self, o: Any) -> Expr:
        return op("or", self, o)

    def __invert__(self) -> Expr:
        return op("not", self)

    # acceso
    def __getitem__(self, key: Any) -> Expr:
        return op("index", self, key)

    def field(self, name: str) -> Expr:
        return Expr(["field", self.sexpr, name])

    def len(self) -> Expr:
        return op("len", self)

    def size(self) -> Expr:
        return op("size", self)

    def items(self) -> Expr:
        return op("items", self)

    def top(self) -> Expr:
        return op("top", self)

    def only(self) -> Expr:
        return op("only", self)

    def first(self) -> Expr:
        return op("first", self)

    def last(self) -> Expr:
        return op("last", self)

    def is_none(self) -> Expr:
        return op("is_none", self)

    def unwrap(self) -> Expr:
        return op("unwrap", self)

    def contains(self, x: Any) -> Expr:
        return op("contains", self, x)

    def append(self, x: Any) -> Expr:
        return op("append", self, x)

    def ord(self) -> Expr:
        return op("ord", self)


def lift(x: Any) -> list[Any]:
    """Valor Python → S-expresión."""
    if isinstance(x, Expr):
        return x.sexpr
    if x is None or isinstance(x, bool | int | str):
        return ["const", x]
    if isinstance(x, Fraction):
        return ["rat", x.numerator, x.denominator]
    if isinstance(x, list | tuple):
        return ["list", *(lift(i) for i in x)]
    raise TypeError(f"no se puede convertir a expresión: {x!r}")


def op(name: str, *args: Any) -> Expr:
    """Cualquier operador del catálogo cuyos argumentos sean expresiones."""
    return Expr([name, *(lift(a) for a in args)])


def const(v: Any) -> Expr:
    return Expr(["const", v])


def var(name: str) -> Expr:
    return Expr(["var", name])


def param(name: str) -> Expr:
    return Expr(["param", name])


def arg(name: str) -> Expr:
    return Expr(["arg", name])


def local(name: str) -> Expr:
    return Expr(["local", name])


def actor() -> Expr:
    return Expr(["actor"])


def seats() -> Expr:
    return Expr(["seats"])


def at(node: str) -> Expr:
    return Expr(["at", node])


def call(function: str, *args: Any) -> Expr:
    return Expr(["call", function, *(lift(a) for a in args)])


def if_(cond: Any, then: Any, other: Any) -> Expr:
    return op("if", cond, then, other)


def case(*pairs: tuple[Any, Any], default: Any) -> Expr:
    return Expr(["case", [[lift(c), lift(v)] for c, v in pairs], lift(default)])


def let(name: str, value: Any, body: Callable[[Expr], Any]) -> Expr:
    return Expr(["let", name, lift(value), lift(body(local(name)))])


def _comprehension(kind: str) -> Callable[[str, Any, Callable[[Expr], Any]], Expr]:
    def build(name: str, coll: Any, body: Callable[[Expr], Any]) -> Expr:
        return Expr([kind, name, lift(coll), lift(body(local(name)))])

    build.__name__ = kind
    return build


all_ = _comprehension("all")
any_ = _comprehension("any")
count = _comprehension("count")
sum_ = _comprehension("sum")
map_ = _comprehension("map")
flat_map = _comprehension("flat_map")
filter_ = _comprehension("filter")
argmax = _comprehension("argmax")
argmin = _comprehension("argmin")
max_of = _comprehension("max_of")
min_of = _comprehension("min_of")
sort_by = _comprehension("sort_by")

# --- Sentencias ---------------------------------------------------------------------------------

Stmt = list[Any]


def _block(stmts: Iterable[Stmt]) -> list[Stmt]:
    return list(stmts)


def assign(target: Expr, value: Any) -> Stmt:
    return ["assign", target.sexpr, lift(value)]


def let_(name: str, value: Any) -> Stmt:
    return ["let", name, lift(value)]


def if_then(cond: Any, then: Iterable[Stmt], other: Iterable[Stmt] | None = None) -> Stmt:
    stmt = ["if", lift(cond), _block(then)]
    return stmt if other is None else [*stmt, _block(other)]


def for_(name: str, coll: Any, body: Callable[[Expr], Iterable[Stmt]]) -> Stmt:
    return ["for", name, lift(coll), _block(body(local(name)))]


class Sel:
    """Selectores de elementos de zona para `move` y `flip`."""

    @staticmethod
    def all() -> list[Any]:
        return ["all"]

    @staticmethod
    def top(n: Any = 1) -> list[Any]:
        return ["top", lift(n)]

    @staticmethod
    def bottom(n: Any = 1) -> list[Any]:
        return ["bottom", lift(n)]

    @staticmethod
    def at(i: Any) -> list[Any]:
        return ["at", lift(i)]

    @staticmethod
    def value(v: Any) -> list[Any]:
        return ["value", lift(v)]

    @staticmethod
    def values(vs: Any) -> list[Any]:
        return ["values", lift(vs)]


def move(src: Expr, dst: Expr, sel: list[Any], pos: str | None = None) -> Stmt:
    stmt = ["move", src.sexpr, dst.sexpr, sel]
    return stmt if pos is None else [*stmt, pos]


def flip(zone: Expr, sel: list[Any], face_up: Any) -> Stmt:
    return ["flip", zone.sexpr, sel, lift(face_up)]


def shuffle(zone: Expr) -> Stmt:
    return ["shuffle", zone.sexpr]


def roll(target: Expr, sides: Any) -> Stmt:
    return ["roll", target.sexpr, lift(sides)]


def random_choice(target: Expr, coll: Any) -> Stmt:
    return ["random_choice", target.sexpr, lift(coll)]


def sample(target: Expr, dist: Any) -> Stmt:
    return ["sample", target.sexpr, lift(dist)]


def reveal(value: Any, to: Any, label: Any = None) -> Stmt:
    stmt = ["reveal", lift(value), lift(to)]
    return stmt if label is None else [*stmt, label]


def emit(name: str, visibility: Any = None, **fields: Any) -> Stmt:
    stmt = ["emit", name, {k: lift(v) for k, v in fields.items()}]
    return stmt if visibility is None else [*stmt, _visibility(visibility)]


def reward(seat: Any, amount: Any) -> Stmt:
    return ["reward", lift(seat), lift(amount)]


def fail(message: str) -> Stmt:
    return ["fail", message]


# --- Tipos y visibilidad -----------------------------------------------------------------------


class T:
    """Constructores de tipos de la IR (los primitivos son cadenas: "Int", "Seat"…)."""

    @staticmethod
    def option(t: Any) -> list[Any]:
        return ["option", t]

    @staticmethod
    def list(t: Any) -> list[Any]:
        return ["list", t]

    @staticmethod
    def set(t: Any) -> list[Any]:
        return ["set", t]

    @staticmethod
    def map(k: Any, v: Any) -> list[Any]:
        return ["map", k, v]

    @staticmethod
    def tuple(*ts: Any) -> list[Any]:
        return ["tuple", *ts]

    @staticmethod
    def per_player(t: Any) -> list[Any]:
        return ["per_player", t]

    @staticmethod
    def zone(t: Any) -> list[Any]:
        return ["zone", t]

    @staticmethod
    def bag(t: Any) -> list[Any]:
        return ["bag", t]

    @staticmethod
    def grid(width: int | str, height: int | str, t: Any) -> list[Any]:
        dims = [d if isinstance(d, int) else ["param", d] for d in (width, height)]
        return ["grid", *dims, t]


def _visibility(v: Any) -> Any:
    if v is None or isinstance(v, str):
        return v
    return {"when": lift(v)}


def p(
    name: str, type_: Any, domain: Any, visibility: Any = None, size_visibility: Any = None
) -> dict[str, Any]:
    """Parámetro de acción."""
    raw: dict[str, Any] = {"name": name, "type": type_, "domain": lift(domain)}
    if visibility is not None:
        raw["visibility"] = _visibility(visibility)
    if size_visibility is not None:
        raw["size_visibility"] = _visibility(size_visibility)
    return raw


# --- Juego y nodos -----------------------------------------------------------------------------


class EnumRef:
    """Enumerado declarado: `Mark.X` es la expresión del valor X; `Mark.values()` la lista."""

    def __init__(self, name: str, values: list[str]) -> None:
        self._name = name
        self._values = list(values)

    def __getattr__(self, value: str) -> Expr:
        if value.startswith("_") or value not in self._values:
            raise AttributeError(f"{self._name} no tiene el valor {value}")
        return Expr(["enum", self._name, value])

    def values(self) -> Expr:
        return Expr(["enum_values", self._name])


def _transitions(raw: dict[str, Any]) -> list[dict[str, Any]]:
    return raw.setdefault("transitions", [])


class NodeBuilder:
    def __init__(self, raw: dict[str, Any]) -> None:
        self.raw = raw

    def action(
        self,
        name: str,
        *params: dict[str, Any],
        requires: Any = None,
        effects: Iterable[Stmt] = (),
        visibility: Any = None,
        doc: Any = None,
    ) -> NodeBuilder:
        action: dict[str, Any] = {"name": name}
        if doc is not None:
            action["doc"] = doc
        if params:
            action["params"] = list(params)
        if requires is not None:
            action["requires"] = lift(requires)
        effects = _block(effects)
        if effects:
            action["effects"] = effects
        if visibility is not None:
            action["visibility"] = _visibility(visibility)
        self.raw.setdefault("actions", []).append(action)
        return self

    def to(self, target: str, when: Any = None, effects: Iterable[Stmt] = ()) -> NodeBuilder:
        transition: dict[str, Any] = {"to": target}
        if when is not None:
            transition["when"] = lift(when)
        effects = _block(effects)
        if effects:
            transition["effects"] = effects
        _transitions(self.raw).append(transition)
        return self


class _Container:
    """Algo que contiene nodos: el flow principal o una fase."""

    _nodes: list[dict[str, Any]]

    def _add(self, raw: dict[str, Any]) -> NodeBuilder:
        self._nodes.append(raw)
        return NodeBuilder(raw)

    def decision(self, id: str, actor: Any, doc: Any = None) -> NodeBuilder:
        return self._add(_with_doc({"id": id, "kind": "decision", "actor": lift(actor)}, doc))

    def simultaneous(
        self, id: str, actors: Any, resolve: Iterable[Stmt] = (), doc: Any = None
    ) -> NodeBuilder:
        raw = {"id": id, "kind": "simultaneous", "actors": lift(actors)}
        resolve = _block(resolve)
        if resolve:
            raw["resolve"] = resolve
        return self._add(_with_doc(raw, doc))

    def window(
        self, id: str, eligible: Any, mode: str, order: Any = None, doc: Any = None
    ) -> NodeBuilder:
        raw = {"id": id, "kind": "window", "eligible": lift(eligible), "mode": mode}
        if order is not None:
            raw["order"] = lift(order)
        return self._add(_with_doc(raw, doc))

    def chance(self, id: str, *effects: Stmt, doc: Any = None) -> NodeBuilder:
        raw = {"id": id, "kind": "chance", "effects": list(effects), "transitions": []}
        return self._add(_with_doc(raw, doc))

    def auto(self, id: str, *effects: Stmt, doc: Any = None) -> NodeBuilder:
        raw: dict[str, Any] = {"id": id, "kind": "auto", "transitions": []}
        if effects:
            raw["effects"] = list(effects)
        return self._add(_with_doc(raw, doc))

    def terminal(self, id: str, payoff: Any, rank: Any = None, doc: Any = None) -> NodeBuilder:
        raw = {"id": id, "kind": "terminal", "payoff": lift(payoff)}
        if rank is not None:
            raw["rank"] = lift(rank)
        return self._add(_with_doc(raw, doc))

    def phase(
        self,
        id: str,
        start: str,
        on_enter: Iterable[Stmt] = (),
        on_exit: Iterable[Stmt] = (),
        doc: Any = None,
    ) -> PhaseBuilder:
        raw: dict[str, Any] = {"id": id, "kind": "phase", "start": start, "nodes": []}
        if on_enter:
            raw["on_enter"] = _block(on_enter)
        if on_exit:
            raw["on_exit"] = _block(on_exit)
        self._nodes.append(_with_doc(raw, doc))
        return PhaseBuilder(raw)


class PhaseBuilder(_Container, NodeBuilder):
    def __init__(self, raw: dict[str, Any]) -> None:
        NodeBuilder.__init__(self, raw)
        self._nodes = raw["nodes"]


def _with_doc(raw: dict[str, Any], doc: Any) -> dict[str, Any]:
    if doc is not None:
        raw["doc"] = doc
    return raw


class GameBuilder(_Container):
    def __init__(
        self,
        id: str,
        version: str = "0.1.0",
        *,
        players: int | tuple[int, int],
        title: Any = None,
        description: Any = None,
        tags: list[str] | None = None,
        license: str | None = None,
    ) -> None:
        lo, hi = (players, players) if isinstance(players, int) else players
        self.ir: dict[str, Any] = {
            "ir_version": "0.1.0",
            "game": {"id": id, "version": version},
            "players": {"min": lo, "max": hi},
            "state": [],
            "flow": {"start": "", "nodes": []},
        }
        meta = {"title": title, "description": description, "tags": tags, "license": license}
        meta = {k: v for k, v in meta.items() if v is not None}
        if meta:
            self.ir["meta"] = meta
        self._nodes = self.ir["flow"]["nodes"]

    def enum(self, name: str, values: list[str], doc: Any = None) -> EnumRef:
        decl = _with_doc({"kind": "enum", "name": name, "values": list(values)}, doc)
        self.ir.setdefault("types", []).append(decl)
        return EnumRef(name, values)

    def struct(self, name: str, doc: Any = None, **fields: Any) -> str:
        decl = {
            "kind": "struct",
            "name": name,
            "fields": [{"name": k, "type": t} for k, t in fields.items()],
        }
        self.ir.setdefault("types", []).append(_with_doc(decl, doc))
        return name

    def param(self, name: str, type_: Any, default: Any, doc: Any = None) -> Expr:
        raw = {"name": name, "type": type_, "default": lift(default)}
        self.ir.setdefault("params", []).append(_with_doc(raw, doc))
        return param(name)

    def constraint(self, expr: Any, message: Any = None) -> None:
        raw: dict[str, Any] = {"expr": lift(expr)}
        if message is not None:
            raw["message"] = message
        self.ir.setdefault("constraints", []).append(raw)

    def state(
        self,
        name: str,
        type_: Any,
        init: Any,
        visibility: Any = None,
        size_visibility: Any = None,
        doc: Any = None,
    ) -> Expr:
        raw: dict[str, Any] = {"name": name, "type": type_, "init": lift(init)}
        if visibility is not None:
            raw["visibility"] = _visibility(visibility)
        if size_visibility is not None:
            raw["size_visibility"] = _visibility(size_visibility)
        self.ir["state"].append(_with_doc(raw, doc))
        return var(name)

    def function(
        self,
        name: str,
        params: list[tuple[str, Any]],
        returns: Any,
        body: Callable[..., Any],
        doc: Any = None,
    ) -> Callable[..., Expr]:
        raw = {
            "name": name,
            "params": [[n, t] for n, t in params],
            "returns": returns,
            "body": lift(body(*(arg(n) for n, _ in params))),
        }
        self.ir.setdefault("functions", []).append(_with_doc(raw, doc))
        return lambda *args: call(name, *args)

    def setup(self, *stmts: Stmt) -> None:
        self.ir["flow"].setdefault("setup", []).extend(stmts)

    def start(self, node: str) -> None:
        self.ir["flow"]["start"] = node

    def build(self, *, check: bool = True) -> dict[str, Any]:
        """El documento IR. Con `check`, lo valida y lanza `RuleError` si tiene problemas."""
        if check:
            from gamehub.ir import check as check_ir

            problems = check_ir(self.ir)
            if problems:
                listing = "\n  ".join(str(p) for p in problems)
                raise RuleError(f"el juego construido no es válido:\n  {listing}")
        return self.ir
