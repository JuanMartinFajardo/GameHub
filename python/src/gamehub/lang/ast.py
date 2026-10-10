# SPDX-License-Identifier: Apache-2.0
"""Árbol sintáctico de Nomos (la "IR de autor": estructura cercana al texto).

Los nodos son dataclasses mutables. Las posiciones (`span`) y los comentarios no participan en
la igualdad: dos árboles son iguales si describen el mismo texto salvo formato y comentarios.
La documentación (`doc`) sí participa, porque llega a la IR.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

from gamehub.lang.lexer import Comment
from gamehub.lang.source import NO_SPAN, Span

# --- Base ---------------------------------------------------------------------------------------


@dataclass(kw_only=True)
class Node:
    span: Span = field(default=NO_SPAN, compare=False, repr=False)


@dataclass(kw_only=True)
class Trivia:
    """Comentarios de un elemento: antes (en sus propias líneas), al final de su línea y los que
    había dentro y no pertenecían a ningún sub-elemento. `blank_before`: había una línea en
    blanco antes (el formateador la conserva)."""

    leading: list[Comment] = field(default_factory=list)
    trailing: Comment | None = None
    inner: list[Comment] = field(default_factory=list)
    blank_before: bool = False


@dataclass(kw_only=True)
class Item(Node):
    """Elemento que ocupa líneas propias: declaraciones, miembros de nodos, sentencias…"""

    doc: Text | None = None
    trivia: Trivia = field(default_factory=Trivia, compare=False, repr=False)


@dataclass
class Text(Node):
    """Texto para personas: cadena o mapa idioma → texto."""

    value: str | dict[str, str]

    def to_ir(self) -> Any:
        return self.value if isinstance(self.value, str) else dict(self.value)


# --- Tipos (sintaxis) ---------------------------------------------------------------------------


@dataclass
class TypeExpr(Node):
    pass


@dataclass
class TName(TypeExpr):
    """Primitivo (`Int`…) o nombre de enum/struct."""

    name: str


@dataclass
class TOption(TypeExpr):
    inner: TypeExpr


@dataclass
class TGeneric(TypeExpr):
    """`List<T>`, `Set<T>`, `Map<K, V>`, `Zone<T>`, `Bag<T>`."""

    name: str
    args: list[TypeExpr]


@dataclass
class TTuple(TypeExpr):
    items: list[TypeExpr]


@dataclass
class TPerPlayer(TypeExpr):
    inner: TypeExpr


@dataclass
class TGrid(TypeExpr):
    """`Grid[ancho, alto] of T`; las dimensiones son enteros o nombres de parámetros."""

    width: int | str
    height: int | str
    inner: TypeExpr


# --- Expresiones --------------------------------------------------------------------------------


@dataclass
class Expr(Node):
    pass


@dataclass
class Name(Expr):
    name: str


@dataclass
class IntLit(Expr):
    value: int


@dataclass
class DecimalLit(Expr):
    """Literal decimal exacto (`0.5` = 1/2). `text` conserva la escritura original."""

    value: Fraction
    text: str


@dataclass
class StrLit(Expr):
    value: str


@dataclass
class BoolLit(Expr):
    value: bool


@dataclass
class NoneLit(Expr):
    pass


@dataclass
class Paren(Expr):
    """Paréntesis explícitos: se conservan porque cambian la IR (`(a + b) + c` no se aplana)."""

    inner: Expr


@dataclass
class Unary(Expr):
    op: str  # "-" o "not"
    operand: Expr


@dataclass
class Binary(Expr):
    """op: + - * / div % == != < <= > >= in "not in" and or"""

    op: str
    left: Expr
    right: Expr


@dataclass
class RangeExpr(Expr):
    """`lo..hi` (inclusivo) o `lo..<hi` (exclusivo)."""

    lo: Expr
    hi: Expr
    inclusive: bool = True


@dataclass
class IfExpr(Expr):
    """`a if cond else b`"""

    then: Expr
    cond: Expr
    other: Expr


@dataclass
class Call(Expr):
    func: str
    args: list[Expr]


@dataclass
class Aggregate(Expr):
    """Forma con variable ligada: `all(x in xs : p)`, `sum(h in heaps : h)`…"""

    func: str
    var: str
    coll: Expr
    body: Expr


@dataclass
class Index(Expr):
    target: Expr
    index: Expr


@dataclass
class Slice(Expr):
    target: Expr
    lo: Expr | None
    hi: Expr | None


@dataclass
class Field(Expr):
    """`a.b`; también `Enum.Valor` y `Enum.values` (los distingue el comprobador)."""

    target: Expr
    name: str


@dataclass
class ListLit(Expr):
    items: list[Expr]


@dataclass
class TupleLit(Expr):
    items: list[Expr]


@dataclass
class CompFor(Node):
    var: str
    iter: Expr
    conds: list[Expr] = field(default_factory=list)


@dataclass
class Comprehension(Expr):
    """`[elem for x in xs if c for y in ys]`"""

    element: Expr
    clauses: list[CompFor]


@dataclass
class StructLit(Expr):
    type_name: str
    fields: list[tuple[str, Expr]]


@dataclass
class LetBlock(Expr):
    """`{ let x = e; …; resultado }`"""

    lets: list[tuple[str, Expr]]
    result: Expr


@dataclass
class CaseExpr(Expr):
    """`case { cond => valor … else => defecto }`"""

    arms: list[tuple[Expr, Expr]]
    default: Expr


@dataclass
class Pattern(Node):
    pass


@dataclass
class PWild(Pattern):
    pass


@dataclass
class PValue(Pattern):
    """Literal o valor de enumerado (expresión constante)."""

    value: Expr


@dataclass
class PTuple(Pattern):
    items: list[Pattern]


@dataclass
class MatchExpr(Expr):
    subject: Expr
    arms: list[tuple[Pattern, Expr]]


# --- Visibilidad --------------------------------------------------------------------------------


@dataclass
class Visibility(Node):
    """`all`, `none`, `owner` o un predicado (`when`) sobre viewer / owner / face_up."""

    kind: str
    expr: Expr | None = None


# --- Sentencias ---------------------------------------------------------------------------------


@dataclass(kw_only=True)
class Stmt(Item):
    pass


@dataclass
class LetStmt(Stmt):
    name: str
    value: Expr


@dataclass
class Assign(Stmt):
    """`lv = e`, `lv += e`, `lv -= e`, `lv *= e`. Con `roll(n)`, `random(xs)` o `sample(d)` a la
    derecha de `=` es una sentencia aleatoria."""

    target: Expr
    op: str
    value: Expr


@dataclass
class IfStmt(Stmt):
    cond: Expr
    then: list[Stmt]
    other: list[Stmt] | None = None


@dataclass
class ForStmt(Stmt):
    var: str
    iter: Expr
    body: list[Stmt]


@dataclass
class Selector(Node):
    """`all`, `top n`, `bottom n`, `at i` o `value` (un valor o una lista de valores)."""

    kind: str
    expr: Expr | None = None


@dataclass
class MoveStmt(Stmt):
    selector: Selector
    source: Expr
    dest: Expr
    position: str | None = None  # "top" | "bottom"


@dataclass
class FlipStmt(Stmt):
    selector: Selector
    zone: Expr
    face: Expr  # BoolLit para face_up / face_down


@dataclass
class ShuffleStmt(Stmt):
    zone: Expr


@dataclass
class DealStmt(Stmt):
    """`deal n from Z to each H` (n = None: `deal all`)."""

    count: Expr | None
    source: Expr
    dest: Expr


@dataclass
class RevealStmt(Stmt):
    value: Expr
    to: Expr | None  # None = all
    label: Text | None = None


@dataclass
class EmitStmt(Stmt):
    name: str
    fields: list[tuple[str, Expr]]
    visibility: Visibility | None = None


@dataclass
class RewardStmt(Stmt):
    amount: Expr
    seat: Expr


@dataclass
class FailStmt(Stmt):
    message: Text


# --- Flow ---------------------------------------------------------------------------------------


@dataclass(kw_only=True)
class Transition(Item):
    target: str  # id de nodo o "exit"
    when: Expr | None = None
    effects: list[Stmt] | None = None


@dataclass(kw_only=True)
class ActionParam(Node):
    name: str
    type: TypeExpr | None = None
    domain: Expr | None = None
    visibility: Visibility | None = None
    size_visibility: Visibility | None = None


@dataclass(kw_only=True)
class ActionDecl(Item):
    name: str
    params: list[ActionParam] = field(default_factory=list)
    requires: Expr | None = None
    effects: list[Stmt] | None = None
    transitions: list[Transition] = field(default_factory=list)
    visibility: Visibility | None = None
    end_comments: list[Comment] = field(default_factory=list, compare=False, repr=False)


@dataclass(kw_only=True)
class Member(Item):
    """`clave: expresión` dentro de un nodo (actor, actors, eligible, order, payoff, rank) o
    `mode: priority|collect|race` (la expresión es un `Name`)."""

    key: str
    value: Expr


@dataclass(kw_only=True)
class BlockMember(Item):
    """`resolve { … }`, `on_enter { … }`, `on_exit { … }`."""

    key: str
    body: list[Stmt]
    end_comments: list[Comment] = field(default_factory=list, compare=False, repr=False)


@dataclass(kw_only=True)
class LetMember(Item):
    """`let x = e` antes de `payoff` / `rank` en un terminal."""

    name: str
    value: Expr


@dataclass(kw_only=True)
class StartDecl(Item):
    """`start -> X` o `start { preparación } -> X` (en `flow` o en una `phase`)."""

    target: str
    setup: list[Stmt] | None = None


@dataclass(kw_only=True)
class NodeDecl(Item):
    """`kind`: decision, simultaneous, window, chance, auto, phase, terminal. `members` en el
    orden del texto: Member, BlockMember, LetMember, ActionDecl, Transition, Stmt (efectos de
    chance/auto), StartDecl y NodeDecl (hijos de una fase)."""

    kind: str
    name: str
    members: list[Item] = field(default_factory=list)
    end_comments: list[Comment] = field(default_factory=list, compare=False, repr=False)


# --- Declaraciones ------------------------------------------------------------------------------


@dataclass(kw_only=True)
class MetaEntry(Item):
    key: str
    value: Any  # Text, list[str] o str


@dataclass(kw_only=True)
class MetaBlock(Item):
    entries: list[MetaEntry]
    end_comments: list[Comment] = field(default_factory=list, compare=False, repr=False)


@dataclass
class UiName(Node):
    """Un nombre como argumento de una pista de `ui` (`column(board)`, `place(top)`)."""

    name: str


@dataclass
class UiArg(Node):
    """Argumento de una pista: `clave: valor` o solo `valor`. Valor: Text (texto o texto
    traducible), int, Fraction, bool, UiName o lista de valores."""

    key: str | None
    value: Any


@dataclass
class UiHint(Node):
    """`nombre` o `nombre(argumentos)` (`args` es None si no lleva paréntesis)."""

    name: str
    args: list[UiArg] | None = None


@dataclass(kw_only=True)
class UiEntry(Item):
    """`destino: pista, pista…`. `target`: "name" (variable de estado, opción o tipo),
    "action" (`action a` o `action a.p`), "node" (`node N`) o "seats"; `path`, sus nombres."""

    target: str
    path: list[str]
    hints: list[UiHint]


@dataclass(kw_only=True)
class UiBlock(Item):
    """`ui { … }`: pistas de presentación para las interfaces (no son reglas)."""

    entries: list[UiEntry]
    end_comments: list[Comment] = field(default_factory=list, compare=False, repr=False)


@dataclass(kw_only=True)
class PlayersDecl(Item):
    min: int
    max: int


@dataclass(kw_only=True)
class ParamDecl(Item):
    name: str
    type: TypeExpr
    default: Expr


@dataclass(kw_only=True)
class AssertDecl(Item):
    expr: Expr
    message: Text | None = None


@dataclass(kw_only=True)
class ParamsBlock(Item):
    items: list[Item]  # ParamDecl | AssertDecl
    end_comments: list[Comment] = field(default_factory=list, compare=False, repr=False)


@dataclass(kw_only=True)
class EnumDecl(Item):
    name: str
    values: list[str]


@dataclass(kw_only=True)
class StructField(Item):
    name: str
    type: TypeExpr


@dataclass(kw_only=True)
class StructDecl(Item):
    name: str
    fields: list[StructField]


@dataclass(kw_only=True)
class StateVar(Item):
    name: str
    type: TypeExpr
    init: Expr | None = None
    visibility: Visibility | None = None
    size_visibility: Visibility | None = None


@dataclass(kw_only=True)
class StateBlock(Item):
    vars: list[StateVar]
    end_comments: list[Comment] = field(default_factory=list, compare=False, repr=False)


@dataclass(kw_only=True)
class FnParam(Node):
    name: str
    type: TypeExpr


@dataclass(kw_only=True)
class FnDecl(Item):
    name: str
    params: list[FnParam]
    returns: TypeExpr
    body: Expr


@dataclass(kw_only=True)
class FlowBlock(Item):
    items: list[Item]  # StartDecl | NodeDecl
    end_comments: list[Comment] = field(default_factory=list, compare=False, repr=False)


# --- Tests --------------------------------------------------------------------------------------


@dataclass
class ActionLit(Node):
    """Acción en un test: `nombre(args)`, con asiento opcional (`1: nombre(args)`)."""

    name: str
    args: list[Expr]
    seat: Expr | None = None


@dataclass(kw_only=True)
class TestStep(Item):
    """`kind`: players, params, seed, play, chance, expect, legal, illegal, set.

    - players: `value` = IntLit
    - params: `entries` = [(nombre, expr)]
    - seed: `value` = IntLit
    - play: `actions` = [ActionLit]
    - chance: `value` = ListLit de sorteos, o `where` = predicado
    - expect: `value` = Bool
    - legal / illegal: `actions` = [ActionLit]
    - set: `target`, `value`
    """

    kind: str
    value: Expr | None = None
    actions: list[ActionLit] = field(default_factory=list)
    entries: list[tuple[str, Expr]] = field(default_factory=list)
    target: Expr | None = None
    where: Expr | None = None


@dataclass(kw_only=True)
class TestDecl(Item):
    name: str
    steps: list[TestStep]
    end_comments: list[Comment] = field(default_factory=list, compare=False, repr=False)


@dataclass(kw_only=True)
class InvariantDecl(Item):
    expr: Expr


# --- Mods ---------------------------------------------------------------------------------------


@dataclass(kw_only=True)
class OverrideDecl(Item):
    """`override <declaración>`: reemplaza la del juego base con el mismo nombre."""

    item: Item


@dataclass(kw_only=True)
class RemoveDecl(Item):
    """`remove node X`, `remove fn f`, `remove state x`, `remove param p`, `remove enum E`,
    `remove struct S`, `remove action Nodo.accion`."""

    kind: str
    path: list[str]


@dataclass(kw_only=True)
class ExtendNode(Item):
    """`extend node X { acciones y transiciones nuevas }`."""

    name: str
    members: list[Item]
    end_comments: list[Comment] = field(default_factory=list, compare=False, repr=False)


# --- Archivo ------------------------------------------------------------------------------------


@dataclass(kw_only=True)
class Import(Item):
    """`import a.b.{X, Y}` o `import a.b.*` (names = None)."""

    path: list[str]
    names: list[str] | None


@dataclass(kw_only=True)
class GameDecl(Item):
    name: str
    extends: str | None = None
    items: list[Item] = field(default_factory=list)
    end_comments: list[Comment] = field(default_factory=list, compare=False, repr=False)


@dataclass(kw_only=True)
class GameAlias(Item):
    """`game IteratedPD = repeat(PrisonersDilemma, rounds: 200, payoff: sum)`"""

    name: str
    combinator: str
    base: str
    args: list[tuple[str, Expr]]


@dataclass(kw_only=True)
class File(Node):
    items: list[Item]  # Import, EnumDecl, StructDecl, FnDecl, GameDecl, GameAlias
    end_comments: list[Comment] = field(default_factory=list, compare=False, repr=False)

    @property
    def imports(self) -> list[Import]:
        return [i for i in self.items if isinstance(i, Import)]

    @property
    def games(self) -> list[GameDecl | GameAlias]:
        return [i for i in self.items if isinstance(i, GameDecl | GameAlias)]

    @property
    def declarations(self) -> list[EnumDecl | StructDecl | FnDecl]:
        """Declaraciones de primer nivel (lo que el archivo ofrece como módulo)."""
        return [i for i in self.items if isinstance(i, EnumDecl | StructDecl | FnDecl)]
