# SPDX-License-Identifier: Apache-2.0
"""Ediciones del Studio: lo que se cambia en el diagrama o en un formulario llega al texto.

Cada edición es una lista de operaciones (`{"op": "addTransition", "node": "Move", …}`) sobre el
árbol sintáctico del archivo (la IR de autor). Se aplican sobre una copia del árbol y después se
reescribe **solo lo que cambió**: los elementos que siguen igual conservan su texto tal cual
(formato y comentarios incluidos) y los nuevos o cambiados se escriben con el formateador. Así,
mover una flecha en el diagrama cambia una línea del texto, no el archivo entero.

El resultado se comprueba siempre: el texto nuevo se vuelve a analizar y tiene que dar el árbol
esperado con los mismos comentarios. Si no (un caso que la reescritura parcial no sabe tratar),
se formatea el archivo entero, que también conserva los comentarios.

Renombrar (`{"op": "rename", "key": "state:board", "name": "tablero"}`) no pasa por el árbol:
cambia cada aparición del símbolo según el índice de símbolos del comprobador.

Las posiciones (`Change.start`/`end`) son índices de la cadena de Python; quien las mande a un
cliente en JavaScript tiene que convertirlas (ver `gamehub.studio.model.Utf16`).
"""

from __future__ import annotations

import copy
import dataclasses
import difflib
import re
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gamehub.lang import ast
from gamehub.lang import fragments as F
from gamehub.lang.compiler import compile_source
from gamehub.lang.diagnostics import Diagnostics
from gamehub.lang.layout import render
from gamehub.lang.lexer import KEYWORDS, Comment
from gamehub.lang.parser import NODE_KINDS, parse
from gamehub.lang.printer import WIDTH, Printer, format_file
from gamehub.lang.reference import NODE_MEMBERS
from gamehub.lang.source import Source
from gamehub.lang.symbols import RENAMABLE, SymbolIndex

IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

#: Nombre por defecto de un nodo nuevo de cada tipo.
DEFAULT_NODE_NAMES = {
    "decision": "Turn",
    "simultaneous": "Choose",
    "window": "React",
    "chance": "Deal",
    "auto": "Update",
    "phase": "Round",
    "terminal": "End",
}

#: Miembros con los que nace un nodo nuevo (para que compile cuanto antes).
PLACEHOLDERS = {
    "decision": {"actor": "0"},
    "simultaneous": {"actors": "seats"},
    "window": {"eligible": "seats", "mode": "priority"},
    "terminal": {"payoff": "fill(0)"},
}


class EditError(Exception):
    """La edición no se puede aplicar. `errors`: errores de sintaxis del trozo escrito (con su
    posición), si los hay; `field`: el campo del formulario al que se refieren."""

    def __init__(
        self, message: str, *, field: str | None = None, errors: list[F.FragmentError] | None = None
    ) -> None:
        super().__init__(message)
        self.message = message
        self.field = field
        self.errors = errors or []

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"message": self.message}
        if self.field:
            out["field"] = self.field
        if self.errors:
            out["errors"] = [e.to_json() for e in self.errors]
        return out


@dataclass(frozen=True)
class Change:
    """Sustituye el texto [start, end) por `insert`."""

    start: int
    end: int
    insert: str


@dataclass
class EditResult:
    text: str
    changes: list[Change]
    #: El elemento creado o cambiado (para seleccionarlo en el diagrama): {"node": …, …}.
    focus: dict[str, Any] | None = None


def apply_edits(
    text: str,
    ops: list[dict[str, Any]],
    *,
    name: str = "<texto>",
    path: Path | None = None,
    game: str | None = None,
) -> EditResult:
    """Aplica las operaciones en orden y devuelve el texto nuevo y los cambios mínimos."""
    current = text
    focus: dict[str, Any] | None = None
    for op in ops:
        current, new_focus = _apply_one(current, op, name, path, game)
        focus = new_focus or focus
    return EditResult(current, text_changes(text, current), focus)


def text_changes(old: str, new: str) -> list[Change]:
    """Los cambios mínimos (por líneas y, dentro de ellas, por caracteres) de `old` a `new`."""
    if old == new:
        return []
    a = old.splitlines(keepends=True)
    b = new.splitlines(keepends=True)
    starts = [0]
    for line in a:
        starts.append(starts[-1] + len(line))
    out: list[Change] = []
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        start, end = starts[i1], starts[i2]
        before, after = old[start:end], "".join(b[j1:j2])
        prefix = 0
        limit = min(len(before), len(after))
        while prefix < limit and before[prefix] == after[prefix]:
            prefix += 1
        suffix = 0
        while (
            suffix < limit - prefix
            and before[len(before) - 1 - suffix] == after[len(after) - 1 - suffix]
        ):
            suffix += 1
        out.append(Change(start + prefix, end - suffix, after[prefix : len(after) - suffix]))
    return out


# --- Una operación -------------------------------------------------------------------------------


def _parse_text(text: str, name: str, path: Path | None) -> tuple[Source, ast.File]:
    source = Source(name, text, path)
    diagnostics = Diagnostics()
    tree = parse(source, diagnostics)
    if diagnostics.has_errors:
        first = diagnostics.errors[0]
        raise EditError(
            "el texto tiene errores de sintaxis: corrígelos antes de editar desde el diagrama "
            f"({first.span}: {first.message})"
        )
    return source, tree


def _apply_one(
    text: str, op: dict[str, Any], name: str, path: Path | None, game: str | None
) -> tuple[str, dict[str, Any] | None]:
    kind = op.get("op")
    source, tree = _parse_text(text, name, path)
    if kind == "rename":
        return _rename(source, op), None
    new_tree = copy.deepcopy(tree)
    origin: dict[int, ast.Node] = {}
    _pair(tree, new_tree, origin)
    ops = _Ops(new_tree, _game(new_tree, game))
    handler = getattr(ops, f"op_{kind}", None)
    if not isinstance(kind, str) or handler is None:
        raise EditError(f"operación desconocida: {kind}")
    handler(op)
    return _Renderer(text, origin).file(tree, new_tree), ops.focus


def _pair(old: Any, new: Any, origin: dict[int, ast.Node]) -> None:
    """Relaciona cada nodo de la copia con el original del que viene."""
    if isinstance(old, ast.Node):
        origin[id(new)] = old
        for f in dataclasses.fields(old):
            if f.compare or f.name in ("members", "items"):
                _pair(getattr(old, f.name), getattr(new, f.name), origin)
    elif isinstance(old, list | tuple):
        for a, b in zip(old, new, strict=True):
            _pair(a, b, origin)


def _game(tree: ast.File, name: str | None) -> ast.GameDecl:
    games = [g for g in tree.items if isinstance(g, ast.GameDecl)]
    if name is not None:
        for g in games:
            if g.name == name:
                return g
        raise EditError(f"el archivo no tiene el juego {name}")
    if not games:
        raise EditError("el archivo no tiene ningún juego que editar")
    return games[0]


# --- Reescritura del texto ----------------------------------------------------------------------

#: Elementos con una lista de elementos que se escriben uno por línea.
_LISTS: dict[type, str] = {
    ast.GameDecl: "items",
    ast.FlowBlock: "items",
    ast.NodeDecl: "members",
    ast.StateBlock: "vars",
    ast.ParamsBlock: "items",
    ast.UiBlock: "entries",
}


def print_item(item: ast.Item, indent: str = "") -> str:
    """Un elemento con el formateador, con su documentación y sus comentarios, sangrado para ir
    a partir de una columna con `indent` delante (la primera línea no lleva la sangría)."""
    out = render(Printer().item(item), WIDTH - len(indent)).rstrip("\n")
    first, *rest = out.split("\n")
    return "\n".join([first, *((indent + line) if line else line for line in rest)])


def _comments_of(item: ast.Node) -> list[Comment]:
    out: list[Comment] = []
    if isinstance(item, ast.Item):
        t = item.trivia
        out.extend(t.leading)
        out.extend(t.inner)
        if t.trailing is not None:
            out.append(t.trailing)
    out.extend(getattr(item, "end_comments", []) or [])
    return out


def _all_comments(node: Any) -> Counter[tuple[str, str]]:
    found: Counter[tuple[str, str]] = Counter()

    def walk(x: Any) -> None:
        if isinstance(x, ast.Node):
            for c in _comments_of(x):
                found[(c.kind, c.text.rstrip())] += 1
            for f in dataclasses.fields(x):
                if f.compare or f.name in ("members", "items"):
                    walk(getattr(x, f.name))
        elif isinstance(x, list | tuple):
            for y in x:
                walk(y)

    walk(node)
    return found


def _key(c: Comment | None) -> tuple[Any, ...] | None:
    """Un comentario sin su posición (las copias del árbol tienen posiciones de otro texto)."""
    if c is None:
        return None
    return (c.kind, c.text, c.own_line, c.blank_before, c.blank_after)


def _keys(comments: list[Comment] | None) -> list[Any]:
    return [_key(c) for c in comments or []]


def _same_trivia(a: ast.Node, b: ast.Node) -> bool:
    if isinstance(a, ast.Item) and isinstance(b, ast.Item):
        ta, tb = a.trivia, b.trivia
        if (
            _keys(ta.leading) != _keys(tb.leading)
            or _keys(ta.inner) != _keys(tb.inner)
            or _key(ta.trailing) != _key(tb.trailing)
            or ta.blank_before != tb.blank_before
        ):
            return False
    return _keys(getattr(a, "end_comments", None)) == _keys(getattr(b, "end_comments", None))


def _same(a: ast.Node, b: ast.Node) -> bool:
    return a == b and _same_trivia(a, b)


def _same_shell(a: ast.Node, b: ast.Node, attr: str) -> bool:
    """Iguales salvo, quizá, su lista de elementos `attr`."""
    for f in dataclasses.fields(a):
        if f.compare and f.name != attr and getattr(a, f.name) != getattr(b, f.name):
            return False
    return _same_trivia(a, b)


def _compact(node: ast.NodeDecl) -> bool:
    """El formateador escribe el nodo en una línea si cabe (un solo miembro `clave: valor`)."""
    return len(node.members) == 1 and isinstance(node.members[0], ast.Member)


class _Renderer:
    def __init__(self, text: str, origin: dict[int, ast.Node]) -> None:
        self.text = text
        self.origin = origin

    # --- posiciones en el texto original ---

    def start(self, item: ast.Item) -> int:
        start = item.span.start
        if item.trivia.leading:
            start = min(start, item.trivia.leading[0].span.start)
        if item.doc is not None and item.doc.span.source is not None:
            start = min(start, item.doc.span.start)
        return start

    def end(self, item: ast.Item) -> int:
        end = item.span.end
        if item.trivia.trailing is not None:
            end = max(end, item.trivia.trailing.span.end)
        return end

    def line_start(self, offset: int) -> int:
        return self.text.rfind("\n", 0, offset) + 1

    def indent(self, item: ast.Item) -> str:
        start = self.start(item)
        return self.text[self.line_start(start) : start]

    def own_line(self, item: ast.Item) -> bool:
        if item.span.source is None:
            return False
        start, end = self.start(item), self.end(item)
        if self.text[self.line_start(start) : start].strip():
            return False
        stop = self.text.find("\n", end)
        return not self.text[end : len(self.text) if stop < 0 else stop].strip()

    def original(self, item: ast.Item) -> str:
        return self.text[self.start(item) : self.end(item)]

    # --- reescritura ---

    def file(self, old: ast.File, new: ast.File) -> str:
        out = self._file(old, new)
        if out is not None and _check(out, new):
            return out
        out = format_file(new)
        if not _check(out, new):
            raise EditError(
                "error interno del Studio: la edición no se puede escribir en el texto "
                "(esto es un fallo de GameHub: por favor, infórmalo)"
            )
        return out

    def _file(self, old: ast.File, new: ast.File) -> str | None:
        if not old.items or not new.items:
            return None
        if not all(self.own_line(i) and not self.indent(i) for i in old.items):
            return None
        r0, r1 = self.start(old.items[0]), self.end(old.items[-1])
        body = self.items(old.items, new.items, "", top=True)
        return self.text[:r0] + body + self.text[r1:]

    def item(self, old: ast.Item, new: ast.Item, indent: str) -> str:
        if _same(old, new):
            return self.original(old)
        inner = self.inside(old, new)
        return inner if inner is not None else print_item(new, indent)

    def inside(self, old: ast.Item, new: ast.Item) -> str | None:
        """Reescribe solo la lista de elementos de un contenedor (si es lo único que cambió)."""
        attr = _LISTS.get(type(old))
        if attr is None or type(new) is not type(old) or not _same_shell(old, new, attr):
            return None
        if isinstance(new, ast.NodeDecl) and _compact(new):
            return None
        old_items: list[ast.Item] = getattr(old, attr)
        new_items: list[ast.Item] = getattr(new, attr)
        if not old_items or not new_items or not all(self.own_line(i) for i in old_items):
            return None
        indent = self.indent(old_items[0])
        if not indent or any(self.indent(i) != indent for i in old_items):
            return None
        r0, r1 = self.start(old_items[0]), self.end(old_items[-1])
        body = self.items(old_items, new_items, indent, top=False)
        return self.text[self.start(old) : r0] + body + self.text[r1 : self.end(old)]

    def items(
        self, old_items: list[ast.Item], new_items: list[ast.Item], indent: str, *, top: bool
    ) -> str:
        olds = {id(o) for o in old_items}
        parts: list[str] = []
        prev: ast.Item | None = None
        for n in new_items:
            o = self.origin.get(id(n))
            if isinstance(o, ast.Item) and id(o) in olds:
                piece = self.item(o, n, indent)
            else:
                piece = print_item(n, indent)
            if prev is not None:
                blank = n.trivia.blank_before or (top and o is None and Printer._separate(prev, n))
                parts.append("\n" + ("\n" if blank else "") + indent)
            parts.append(piece)
            prev = n
        return "".join(parts)


def _check(text: str, expected: ast.File) -> bool:
    """El texto da el árbol esperado, con los mismos comentarios."""
    diagnostics = Diagnostics()
    tree = parse(Source("<comprobación>", text), diagnostics)
    if diagnostics.has_errors or tree != expected:
        return False
    return _all_comments(tree) == _all_comments(expected)


# --- Renombrar ----------------------------------------------------------------------------------


def _rename(source: Source, op: dict[str, Any]) -> str:
    key = op.get("key")
    new_name = op.get("name")
    if not isinstance(key, str) or not isinstance(new_name, str):
        raise EditError("rename necesita key y name")
    kind = key.split(":", 1)[0]
    if kind not in RENAMABLE:
        raise EditError("eso no se puede renombrar (es predefinido)")
    _identifier(new_name, "el nombre nuevo", field="name")
    index = SymbolIndex()
    before = compile_source(source, index=index, schema=False)
    symbol = index.symbols.get(key)
    occurrences = index.of(key, source.name)
    if symbol is None or not occurrences:
        raise EditError("no se encuentra ese símbolo en el archivo (¿compila el juego?)")
    if not any(d.source is not None and d.source.name == source.name for d in symbol.decls):
        raise EditError(
            f"`{symbol.name}` se declara en otro archivo: renómbralo allí (o en su módulo)"
        )
    if new_name == symbol.name:
        return source.text
    clash = _clash(index, kind, new_name, key)
    if clash is not None:
        raise EditError(f"ya hay {clash} que se llama `{new_name}`", field="name")
    text = source.text
    spans = sorted({(o.span.start, o.span.end) for o in occurrences}, reverse=True)
    for start, end in spans:
        if text[start:end] == symbol.name:
            text = text[:start] + new_name + text[end:]
    _parse_text(text, source.name, source.path)
    if before.ok:
        # Un renombrado nunca debe romper un juego que compilaba (p. ej. un `override` tiene que
        # llamarse como lo que sustituye en el juego base).
        after = compile_source(Source(source.name, text, source.path), schema=False)
        if not after.ok:
            first = after.diagnostics.errors[0]
            raise EditError(f"no se puede renombrar así: {first.message}", field="name")
    return text


#: Clases de símbolo cuyos nombres comparten espacio (no pueden repetirse entre sí).
_GLOBAL = {"state", "param", "fn", "type", "value"}
_KIND_NAMES = {
    "state": "una variable de estado",
    "param": "una opción",
    "fn": "una función",
    "type": "un tipo",
    "value": "un valor de enumerado",
    "node": "un nodo",
    "action": "una acción",
    "game": "un juego",
}


def _clash(index: SymbolIndex, kind: str, name: str, key: str) -> str | None:
    """Qué hay ya con ese nombre que choque con el símbolo renombrado (o None)."""
    owner = key.rsplit(".", 1)[0]
    for other in index.symbols.values():
        if other.key == key or other.name != name:
            continue
        if kind in _GLOBAL and other.kind in _GLOBAL:
            return _KIND_NAMES[other.kind]
        if other.kind == kind and kind in ("node", "action", "game"):
            return _KIND_NAMES[kind]
        if (
            kind in ("field", "aparam")
            and other.kind == kind
            and other.key.rsplit(".", 1)[0] == owner
        ):
            return "un campo" if kind == "field" else "un parámetro"
    return None


def _identifier(name: Any, what: str, *, field: str | None = None) -> str:
    if not isinstance(name, str) or not IDENTIFIER.match(name):
        raise EditError(
            f"{what} tiene que ser un identificador: letras, dígitos y _, sin empezar por "
            "un dígito",
            field=field,
        )
    if name in KEYWORDS:
        raise EditError(f"`{name}` es una palabra reservada de Nomos", field=field)
    return name


# --- Operaciones ----------------------------------------------------------------------------------


#: Orden en que suelen ir los miembros de un nodo (para colocar los nuevos).
def _member_rank(item: ast.Item) -> int:
    match item:
        case ast.LetMember():
            return 0
        case ast.Member():
            return 1
        case ast.BlockMember(key=key) if key in ("on_enter", "on_exit"):
            return 2
        case ast.StartDecl():
            return 3
        case ast.NodeDecl():
            return 4
        case ast.ActionDecl():
            return 5
        case ast.BlockMember():
            return 7
        case ast.Transition():
            return 8
        case ast.Stmt():
            return 6
    return 6


#: Orden de las secciones de un juego (para colocar las nuevas).
def _game_rank(item: ast.Item) -> int:
    match item:
        case ast.MetaBlock():
            return 0
        case ast.PlayersDecl():
            return 1
        case ast.ParamsBlock():
            return 2
        case ast.EnumDecl() | ast.StructDecl():
            return 3
        case ast.StateBlock():
            return 4
        case ast.FnDecl():
            return 5
        case ast.FlowBlock():
            return 6
        case ast.UiBlock():
            return 7
        case ast.TestDecl():
            return 8
        case ast.InvariantDecl():
            return 9
    return 6


def _insert_ranked(items: list[ast.Item], item: ast.Item, rank: Callable[[ast.Item], int]) -> None:
    """Inserta tras el último elemento de rango menor o igual (o al principio)."""
    r = rank(item)
    position = 0
    for i, other in enumerate(items):
        if rank(other) <= r:
            position = i + 1
    items.insert(position, item)


def _text_value(value: Any, what: str) -> ast.Text:
    if isinstance(value, str):
        return ast.Text(value)
    if (
        isinstance(value, dict)
        and value
        and all(isinstance(k, str) and isinstance(v, str) for k, v in value.items())
    ):
        return ast.Text(dict(value))
    raise EditError(f"{what} tiene que ser un texto o un texto traducible {{es: …, en: …}}")


def _fragment[T](parse_fn: Callable[[str], T], text: Any, field: str) -> T:
    if not isinstance(text, str):
        raise EditError(f"falta el valor de {field}", field=field)
    try:
        return parse_fn(text)
    except F.FragmentSyntaxError as exc:
        raise EditError(str(exc), field=field, errors=exc.errors) from None


def _optional_expr(op: dict[str, Any], key: str) -> ast.Expr | None:
    value = op.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return _fragment(F.expression, value, key)


def _statements(value: Any, field: str) -> tuple[list[ast.Stmt], list[Comment]]:
    if value is None:
        return [], []
    return _fragment(F.statements, value, field)


class _Ops:
    def __init__(self, tree: ast.File, game: ast.GameDecl) -> None:
        self.tree = tree
        self.game = game
        self.focus: dict[str, Any] | None = None

    # --- búsqueda ---------------------------------------------------------------------------

    def flow(self, *, create: bool = False) -> ast.FlowBlock:
        for item in self.game.items:
            if isinstance(item, ast.FlowBlock):
                return item
        if not create:
            raise EditError("el juego no tiene flow")
        flow = ast.FlowBlock(items=[])
        flow.trivia.blank_before = True
        _insert_ranked(self.game.items, flow, _game_rank)
        return flow

    def walk(self) -> Iterator[tuple[ast.NodeDecl, list[ast.Item], ast.NodeDecl | None]]:
        """Todos los nodos (también los de dentro de las fases): (nodo, lista que lo contiene,
        fase que lo contiene o None)."""

        def visit(
            items: list[ast.Item], parent: ast.NodeDecl | None
        ) -> Iterator[tuple[ast.NodeDecl, list[ast.Item], ast.NodeDecl | None]]:
            for item in items:
                if isinstance(item, ast.NodeDecl):
                    yield item, items, parent
                    if item.kind == "phase":
                        yield from visit(item.members, item)

        for item in self.game.items:
            if isinstance(item, ast.FlowBlock):
                yield from visit(item.items, None)

    def node(self, name: Any) -> tuple[ast.NodeDecl, list[ast.Item], ast.NodeDecl | None]:
        for found in self.walk():
            if found[0].name == name:
                return found
        raise EditError(f"no hay ningún nodo `{name}`")

    def phase(self, name: Any) -> ast.NodeDecl:
        node, _, _ = self.node(name)
        if node.kind != "phase":
            raise EditError(f"`{name}` no es una fase")
        return node

    def container(self, parent: Any) -> list[ast.Item]:
        """La lista donde van los nodos del flow (None) o de una fase."""
        if parent is None:
            return self.flow(create=True).items
        return self.phase(parent).members

    def names(self) -> set[str]:
        """Los nombres ya usados en el juego (para no repetir al crear)."""
        taken: set[str] = set()
        for item in self.game.items:
            match item:
                case ast.StateBlock(vars=variables):
                    taken.update(v.name for v in variables)
                case ast.ParamsBlock(items=params):
                    taken.update(p.name for p in params if isinstance(p, ast.ParamDecl))
                case ast.EnumDecl():
                    taken.add(item.name)
                    taken.update(item.values)
                case ast.StructDecl() | ast.FnDecl():
                    taken.add(item.name)
        for item in self.tree.items:
            if isinstance(item, ast.EnumDecl | ast.StructDecl | ast.FnDecl):
                taken.add(item.name)
                if isinstance(item, ast.EnumDecl):
                    taken.update(item.values)
        for node, _, _ in self.walk():
            taken.add(node.name)
            for m in node.members:
                if isinstance(m, ast.ActionDecl):
                    taken.add(m.name)
        return taken

    def fresh(self, base: str) -> str:
        taken = self.names() | set(KEYWORDS)
        if base not in taken:
            return base
        i = 2
        while f"{base}{i}" in taken:
            i += 1
        return f"{base}{i}"

    def new_name(self, op: dict[str, Any], key: str, base: str, what: str) -> str:
        name = op.get(key)
        if name is None:
            return self.fresh(base)
        _identifier(name, what, field=key)
        if name in self.names():
            raise EditError(f"ya hay algo que se llama `{name}`", field=key)
        return name

    def action(self, node: ast.NodeDecl, name: Any) -> ast.ActionDecl:
        for m in node.members:
            if isinstance(m, ast.ActionDecl) and m.name == name:
                return m
        raise EditError(f"el nodo {node.name} no tiene la acción `{name}`")

    def transitions_of(self, op: dict[str, Any]) -> tuple[ast.NodeDecl, ast.ActionDecl | None]:
        node, _, _ = self.node(op.get("node"))
        action = self.action(node, op["action"]) if op.get("action") is not None else None
        return node, action

    def transition_list(
        self, node: ast.NodeDecl, action: ast.ActionDecl | None
    ) -> list[ast.Transition]:
        if action is not None:
            return action.transitions
        return [m for m in node.members if isinstance(m, ast.Transition)]

    def transition(self, op: dict[str, Any]) -> tuple[ast.NodeDecl, ast.ActionDecl | None, int]:
        node, action = self.transitions_of(op)
        index = op.get("index")
        items = self.transition_list(node, action)
        if not isinstance(index, int) or not 0 <= index < len(items):
            raise EditError(f"no hay transición número {index}")
        return node, action, index

    def element(self, target: Any) -> ast.Item:
        """El elemento al que se refiere `target` ({"node": …}, {"state": …}…)."""
        if not isinstance(target, dict):
            raise EditError("destino no válido")
        if "node" in target:
            node, action = self.transitions_of(target)
            if "index" in target:
                _, _, i = self.transition(target)
                return self.transition_list(node, action)[i]
            return action if action is not None else node
        for key, cls, attr in (
            ("state", ast.StateBlock, "vars"),
            ("param", ast.ParamsBlock, "items"),
        ):
            if key in target:
                for block in self.game.items:
                    if isinstance(block, cls):
                        for x in getattr(block, attr):
                            if getattr(x, "name", None) == target[key]:
                                return x
                raise EditError(f"no existe `{target[key]}`")
        for key in ("fn", "type"):
            if key in target:
                return self.declaration(target[key])
        raise EditError("destino no válido")

    def declaration(self, name: Any) -> ast.EnumDecl | ast.StructDecl | ast.FnDecl:
        for item in self.game.items:
            if isinstance(item, ast.EnumDecl | ast.StructDecl | ast.FnDecl) and item.name == name:
                return item
        raise EditError(f"el juego no declara `{name}`")

    def block(self, cls: type, *, create: bool) -> Any:
        for item in self.game.items:
            if isinstance(item, cls):
                return item
        if not create:
            return None
        lists = {ast.MetaBlock: "entries", ast.StateBlock: "vars", ast.ParamsBlock: "items"}
        block = cls(**{lists.get(cls) or _LISTS[cls]: []})
        self.add_game_item(block)
        return block

    def add_game_item(self, item: ast.Item) -> None:
        """Añade una declaración al juego en su sitio. Tras otra de la misma clase sigue el
        estilo de esa (con o sin línea en blanco: `fn` seguidas, por ejemplo)."""
        _insert_ranked(self.game.items, item, _game_rank)
        i = self.game.items.index(item)
        prev = self.game.items[i - 1] if i else None
        item.trivia.blank_before = (
            not (type(prev) is type(item) and prev is not None and not prev.trivia.blank_before)
            if i
            else False
        )

    # --- nodos ------------------------------------------------------------------------------

    def op_addNode(self, op: dict[str, Any]) -> None:
        kind = op.get("kind")
        if kind not in NODE_KINDS:
            raise EditError(f"tipo de nodo desconocido: {kind}")
        name = self.new_name(op, "name", DEFAULT_NODE_NAMES[kind], "el nombre del nodo")
        members: list[ast.Item] = []
        given = op.get("members") or {}
        for key, src in {**PLACEHOLDERS.get(kind, {}), **given}.items():
            if key not in NODE_MEMBERS[kind]:
                raise EditError(f"un nodo {kind} no tiene `{key}`")
            members.append(ast.Member(key=key, value=_fragment(F.expression, src, key)))
        node = ast.NodeDecl(kind=kind, name=name, members=members)
        node.trivia.blank_before = True
        parent = op.get("parent")
        container = self.container(parent)
        after = op.get("after")
        nodes = [i for i, m in enumerate(container) if isinstance(m, ast.NodeDecl)]
        if after is not None:
            position = next(
                (i + 1 for i, m in enumerate(container) if getattr(m, "name", None) == after),
                None,
            )
            if position is None:
                raise EditError(f"no hay ningún nodo `{after}` ahí")
        elif nodes:
            position = nodes[-1] + 1
        else:
            position = len(container)
            if parent is not None:
                position = next(
                    (i for i, m in enumerate(container) if _member_rank(m) > 4), len(container)
                )
        container.insert(position, node)
        if not any(isinstance(m, ast.StartDecl) for m in container):
            container.insert(0, ast.StartDecl(target=name))
        self.focus = {"node": name}

    def op_deleteNode(self, op: dict[str, Any]) -> None:
        node, container, _ = self.node(op.get("node"))
        container.remove(node)
        removed = {node.name} | {n.name for n, _, _ in _subnodes(node)}
        for other, _, _ in self.walk():
            other.members = [
                m
                for m in other.members
                if not (isinstance(m, ast.Transition) and m.target in removed)
            ]
            for m in other.members:
                if isinstance(m, ast.ActionDecl):
                    m.transitions = [t for t in m.transitions if t.target not in removed]
                    _tidy_action(m)
        ui = self.block(ast.UiBlock, create=False)
        if ui is not None:
            ui.entries = [
                e for e in ui.entries if not (e.target == "node" and e.path[0] in removed)
            ]
            if not ui.entries:
                self.game.items.remove(ui)

    def op_moveNode(self, op: dict[str, Any]) -> None:
        node, container, _ = self.node(op.get("node"))
        parent = op.get("parent")
        if parent is not None and (
            parent == node.name or parent in {n.name for n, _, _ in _subnodes(node)}
        ):
            raise EditError("una fase no puede ir dentro de sí misma")
        target = self.container(parent)
        before = op.get("before")
        container.remove(node)
        if before is not None:
            position = next(
                (i for i, m in enumerate(target) if getattr(m, "name", None) == before), None
            )
            if position is None:
                raise EditError(f"no hay ningún nodo `{before}` ahí")
        else:
            nodes = [i for i, m in enumerate(target) if isinstance(m, ast.NodeDecl)]
            position = nodes[-1] + 1 if nodes else len(target)
        node.trivia.blank_before = True
        target.insert(position, node)
        if not any(isinstance(m, ast.StartDecl) for m in target):
            target.insert(0, ast.StartDecl(target=node.name))
        # Si el nodo era el inicio de donde estaba y se mete en una fase de ese mismo sitio, el
        # inicio pasa a ser la fase.
        start = next((m for m in container if isinstance(m, ast.StartDecl)), None)
        if (
            start is not None
            and start.target == node.name
            and parent is not None
            and any(getattr(m, "name", None) == parent for m in container)
        ):
            start.target = parent
        self.focus = {"node": node.name}

    def op_setNodeKind(self, op: dict[str, Any]) -> None:
        node, _, _ = self.node(op.get("node"))
        kind = op.get("kind")
        if kind not in NODE_KINDS:
            raise EditError(f"tipo de nodo desconocido: {kind}")
        if (
            node.kind == "phase"
            and kind != "phase"
            and any(isinstance(m, ast.NodeDecl) for m in node.members)
        ):
            raise EditError("la fase tiene nodos dentro: sácalos antes de cambiarle el tipo")
        node.kind = kind
        node.members = [
            m
            for m in node.members
            if not (isinstance(m, ast.Member) and m.key not in NODE_MEMBERS[kind])
        ]
        present = {m.key for m in node.members if isinstance(m, ast.Member)}
        for key, src in PLACEHOLDERS.get(kind, {}).items():
            if key not in present:
                _insert_ranked(
                    node.members, ast.Member(key=key, value=F.expression(src)), _member_rank
                )
        self.focus = {"node": node.name}

    def op_setMember(self, op: dict[str, Any]) -> None:
        node, _, _ = self.node(op.get("node"))
        key = op.get("key")
        if key not in NODE_MEMBERS[node.kind]:
            raise EditError(f"un nodo {node.kind} no tiene `{key}`", field="key")
        existing = next(
            (m for m in node.members if isinstance(m, ast.Member) and m.key == key), None
        )
        value = _optional_expr(op, "value")
        if value is None:
            if existing is not None:
                node.members.remove(existing)
        elif existing is not None:
            existing.value = value
        else:
            _insert_ranked(node.members, ast.Member(key=key, value=value), _member_rank)
        self.focus = {"node": node.name}

    def op_setBlock(self, op: dict[str, Any]) -> None:
        node, _, _ = self.node(op.get("node"))
        key = op.get("key")
        body, end = _statements(op.get("value"), "value")
        if key == "effects":
            if node.kind not in ("chance", "auto"):
                raise EditError("solo los nodos chance y auto tienen efectos sueltos")
            positions = [i for i, m in enumerate(node.members) if isinstance(m, ast.Stmt)]
            members = [m for m in node.members if not isinstance(m, ast.Stmt)]
            at = positions[0] if positions else None
            if at is None:
                at = next(
                    (i for i, m in enumerate(members) if isinstance(m, ast.Transition)),
                    len(members),
                )
            if end and body:
                body[-1].trivia.inner.extend(end)
            node.members = [*members[:at], *body, *members[at:]]
        else:
            allowed = {"simultaneous": ("resolve",), "phase": ("on_enter", "on_exit")}
            if key not in allowed.get(node.kind, ()):
                raise EditError(f"un nodo {node.kind} no tiene `{key}`")
            existing = next(
                (m for m in node.members if isinstance(m, ast.BlockMember) and m.key == key), None
            )
            if not body and not end:
                if existing is not None:
                    node.members.remove(existing)
            elif existing is not None:
                existing.body = body
                existing.end_comments = end
            else:
                block = ast.BlockMember(key=str(key), body=body, end_comments=end)
                _insert_ranked(node.members, block, _member_rank)
        self.focus = {"node": node.name}

    def op_setLets(self, op: dict[str, Any]) -> None:
        node, _, _ = self.node(op.get("node"))
        if node.kind != "terminal":
            raise EditError("solo los terminales tienen let")
        lets = []
        for i, entry in enumerate(op.get("lets") or []):
            name = _identifier(entry.get("name"), "el nombre", field=f"lets.{i}.name")
            lets.append(
                ast.LetMember(
                    name=name, value=_fragment(F.expression, entry.get("value"), f"lets.{i}.value")
                )
            )
        rest = [m for m in node.members if not isinstance(m, ast.LetMember)]
        node.members = [*lets, *rest]
        self.focus = {"node": node.name}

    def op_setStart(self, op: dict[str, Any]) -> None:
        parent = op.get("phase")
        container = self.container(parent)
        target = op.get("target")
        if not isinstance(target, str) or not any(
            getattr(m, "name", None) == target for m in container
        ):
            raise EditError(
                f"`{target}` no es un nodo de {'la fase ' + parent if parent else 'flow'}"
            )
        start = next((m for m in container if isinstance(m, ast.StartDecl)), None)
        if start is None:
            container.insert(0, ast.StartDecl(target=target))
        else:
            start.target = target

    def op_setSetup(self, op: dict[str, Any]) -> None:
        flow = self.flow()
        start = next((m for m in flow.items if isinstance(m, ast.StartDecl)), None)
        if start is None:
            raise EditError("el flow no tiene start")
        body, end = _statements(op.get("value"), "value")
        if end and body:
            body[-1].trivia.inner.extend(end)
        start.setup = body or None

    def op_setDoc(self, op: dict[str, Any]) -> None:
        item = self.element(op.get("target"))
        doc = op.get("doc")
        item.doc = None if doc in (None, "") else _text_value(doc, "la documentación")

    # --- acciones ---------------------------------------------------------------------------

    def params(self, values: Any) -> list[ast.ActionParam]:
        out: list[ast.ActionParam] = []
        for i, p in enumerate(values or []):
            name = _identifier(p.get("name"), "el nombre del parámetro", field=f"params.{i}.name")
            param = ast.ActionParam(name=name)
            if p.get("type"):
                param.type = _fragment(F.type_expr, p["type"], f"params.{i}.type")
            if p.get("domain"):
                param.domain = _fragment(F.expression, p["domain"], f"params.{i}.domain")
            if param.type is None and param.domain is None:
                raise EditError(
                    f"el parámetro {name} necesita un tipo o un dominio", field=f"params.{i}"
                )
            if p.get("visibility"):
                param.visibility = _fragment(
                    F.visibility, p["visibility"], f"params.{i}.visibility"
                )
            if p.get("sizeVisibility"):
                param.size_visibility = _fragment(
                    F.visibility, p["sizeVisibility"], f"params.{i}.sizeVisibility"
                )
            out.append(param)
        if len({p.name for p in out}) != len(out):
            raise EditError("hay dos parámetros con el mismo nombre", field="params")
        return out

    def op_addAction(self, op: dict[str, Any]) -> None:
        node, _, _ = self.node(op.get("node"))
        if node.kind not in ("decision", "simultaneous", "window"):
            raise EditError(f"un nodo {node.kind} no tiene acciones")
        name = op.get("name")
        if name is None:
            name = self.fresh("act")
        else:
            _identifier(name, "el nombre de la acción", field="name")
            if any(isinstance(m, ast.ActionDecl) and m.name == name for m in node.members):
                raise EditError(f"el nodo ya tiene la acción `{name}`", field="name")
        action = ast.ActionDecl(name=name, params=self.params(op.get("params")))
        action.requires = _optional_expr(op, "requires")
        effects, end = _statements(op.get("effects"), "effects")
        if effects or end:
            action.effects = effects
            action.end_comments = end
        _insert_ranked(node.members, action, _member_rank)
        self.focus = {"node": node.name, "action": name}

    def op_updateAction(self, op: dict[str, Any]) -> None:
        node, _, _ = self.node(op.get("node"))
        action = self.action(node, op.get("action"))
        if "params" in op:
            action.params = self.params(op["params"])
        if "requires" in op:
            action.requires = _optional_expr(op, "requires")
        if "effects" in op:
            effects, end = _statements(op.get("effects"), "effects")
            action.effects = effects
            action.end_comments = end
            _tidy_action(action)
        if "visibility" in op:
            vis = op.get("visibility")
            action.visibility = _fragment(F.visibility, vis, "visibility") if vis else None
        self.focus = {"node": node.name, "action": action.name}

    def op_deleteAction(self, op: dict[str, Any]) -> None:
        node, _, _ = self.node(op.get("node"))
        node.members.remove(self.action(node, op.get("action")))
        self.focus = {"node": node.name}

    def op_moveAction(self, op: dict[str, Any]) -> None:
        node, _, _ = self.node(op.get("node"))
        action = self.action(node, op.get("action"))
        actions = [m for m in node.members if isinstance(m, ast.ActionDecl)]
        index = op.get("index")
        if not isinstance(index, int) or not 0 <= index < len(actions):
            raise EditError(f"posición no válida: {index}")
        _reorder(node.members, actions, action, index)
        self.focus = {"node": node.name, "action": action.name}

    # --- transiciones -----------------------------------------------------------------------

    def target(self, value: Any) -> str:
        if value == "exit":
            return "exit"
        if not any(n.name == value for n, _, _ in self.walk()):
            raise EditError(f"no hay ningún nodo `{value}`", field="target")
        return str(value)

    def op_addTransition(self, op: dict[str, Any]) -> None:
        node, action = self.transitions_of(op)
        if action is not None and node.kind == "simultaneous":
            raise EditError(
                "en un nodo simultáneo las transiciones van en el nodo, no en las acciones"
            )
        transition = ast.Transition(target=self.target(op.get("target")))
        transition.when = _optional_expr(op, "when")
        effects, end = _statements(op.get("effects"), "effects")
        if end and effects:
            effects[-1].trivia.inner.extend(end)
        transition.effects = effects or None
        current = self.transition_list(node, action)
        index = op.get("index")
        if not isinstance(index, int):
            # Delante de una última transición sin condición (si no, quedaría inalcanzable).
            index = len(current)
            if current and current[-1].when is None and transition.when is not None:
                index -= 1
        index = max(0, min(index, len(current)))
        if action is not None:
            if action.effects is None:
                action.effects = []
            action.transitions.insert(index, transition)
        elif index < len(current):
            node.members.insert(node.members.index(current[index]), transition)
        else:
            _insert_ranked(node.members, transition, _member_rank)
        self.focus = {**_where(node, action), "transition": index}

    def op_updateTransition(self, op: dict[str, Any]) -> None:
        node, action, index = self.transition(op)
        transition = self.transition_list(node, action)[index]
        if "target" in op:
            transition.target = self.target(op["target"])
        if "when" in op:
            transition.when = _optional_expr(op, "when")
        if "effects" in op:
            effects, end = _statements(op.get("effects"), "effects")
            if end and effects:
                effects[-1].trivia.inner.extend(end)
            transition.effects = effects or None
        self.focus = {**_where(node, action), "transition": index}

    def op_deleteTransition(self, op: dict[str, Any]) -> None:
        node, action, index = self.transition(op)
        transition = self.transition_list(node, action)[index]
        if action is not None:
            action.transitions.remove(transition)
            _tidy_action(action)
        else:
            node.members.remove(transition)
        self.focus = _where(node, action)

    def op_moveTransition(self, op: dict[str, Any]) -> None:
        node, action, index = self.transition(op)
        items = self.transition_list(node, action)
        to = op.get("to")
        if not isinstance(to, int) or not 0 <= to < len(items):
            raise EditError(f"posición no válida: {to}")
        transition = items[index]
        if action is not None:
            action.transitions.remove(transition)
            action.transitions.insert(to, transition)
        else:
            _reorder(node.members, items, transition, to)
        self.focus = {**_where(node, action), "transition": to}

    # --- declaraciones ----------------------------------------------------------------------

    def op_setMeta(self, op: dict[str, Any]) -> None:
        key = _identifier(op.get("key"), "el campo de meta", field="key")
        meta = self.block(ast.MetaBlock, create=True)
        value = op.get("value")
        existing = next((e for e in meta.entries if e.key == key), None)
        if value is None:
            if existing is not None:
                meta.entries.remove(existing)
            return
        if isinstance(value, list):
            if not all(isinstance(v, str) for v in value):
                raise EditError(f"{key} es una lista de textos", field="value")
            new_value: Any = list(value)
        else:
            new_value = _text_value(value, key)
        if existing is not None:
            existing.value = new_value
        else:
            meta.entries.append(ast.MetaEntry(key=key, value=new_value))

    def op_setPlayers(self, op: dict[str, Any]) -> None:
        lo, hi = op.get("min"), op.get("max", op.get("min"))
        if not isinstance(lo, int) or not isinstance(hi, int) or lo < 1 or hi < lo:
            raise EditError("jugadores: un mínimo de al menos 1 y un máximo no menor", field="min")
        players = self.block(ast.PlayersDecl, create=False)
        if players is None:
            players = ast.PlayersDecl(min=lo, max=hi)
            self.add_game_item(players)
            players.trivia.blank_before = False
        players.min, players.max = lo, hi

    def state_var(self, name: Any) -> tuple[ast.StateBlock, ast.StateVar]:
        block = self.block(ast.StateBlock, create=False)
        if block is not None:
            for var in block.vars:
                if var.name == name:
                    return block, var
        raise EditError(f"no hay ninguna variable de estado `{name}`")

    def fill_var(self, var: ast.StateVar, op: dict[str, Any]) -> None:
        if "type" in op:
            var.type = _fragment(F.type_expr, op["type"], "type")
        if "init" in op:
            var.init = _optional_expr(op, "init")
        if "visibility" in op:
            vis = op.get("visibility")
            var.visibility = _fragment(F.visibility, vis, "visibility") if vis else None
        if "sizeVisibility" in op:
            vis = op.get("sizeVisibility")
            var.size_visibility = _fragment(F.visibility, vis, "sizeVisibility") if vis else None
        if "doc" in op:
            doc = op.get("doc")
            var.doc = _text_value(doc, "la documentación") if doc else None

    def op_addState(self, op: dict[str, Any]) -> None:
        name = self.new_name(op, "name", "value", "el nombre de la variable")
        if "type" not in op:
            raise EditError("falta el tipo", field="type")
        var = ast.StateVar(name=name, type=ast.TName("Int"))
        self.fill_var(var, op)
        block = self.block(ast.StateBlock, create=True)
        block.vars.append(var)
        self.focus = {"state": name}

    def op_updateState(self, op: dict[str, Any]) -> None:
        _, var = self.state_var(op.get("name"))
        self.fill_var(var, op)
        self.focus = {"state": var.name}

    def op_deleteState(self, op: dict[str, Any]) -> None:
        block, var = self.state_var(op.get("name"))
        block.vars.remove(var)
        if not block.vars:
            self.game.items.remove(block)

    def op_moveState(self, op: dict[str, Any]) -> None:
        block, var = self.state_var(op.get("name"))
        index = op.get("index")
        if not isinstance(index, int) or not 0 <= index < len(block.vars):
            raise EditError(f"posición no válida: {index}")
        block.vars.remove(var)
        block.vars.insert(index, var)

    def param(self, name: Any) -> tuple[ast.ParamsBlock, ast.ParamDecl]:
        block = self.block(ast.ParamsBlock, create=False)
        if block is not None:
            for p in block.items:
                if isinstance(p, ast.ParamDecl) and p.name == name:
                    return block, p
        raise EditError(f"no hay ninguna opción `{name}`")

    def op_addParam(self, op: dict[str, Any]) -> None:
        name = self.new_name(op, "name", "option", "el nombre de la opción")
        param = ast.ParamDecl(
            name=name,
            type=_fragment(F.type_expr, op.get("type"), "type"),
            default=_fragment(F.expression, op.get("default"), "default"),
        )
        if op.get("doc"):
            param.doc = _text_value(op["doc"], "la documentación")
        block = self.block(ast.ParamsBlock, create=True)
        asserts = [i for i, p in enumerate(block.items) if isinstance(p, ast.AssertDecl)]
        block.items.insert(asserts[0] if asserts else len(block.items), param)
        self.focus = {"param": name}

    def op_updateParam(self, op: dict[str, Any]) -> None:
        _, param = self.param(op.get("name"))
        if "type" in op:
            param.type = _fragment(F.type_expr, op["type"], "type")
        if "default" in op:
            param.default = _fragment(F.expression, op["default"], "default")
        if "doc" in op:
            param.doc = _text_value(op["doc"], "la documentación") if op["doc"] else None
        self.focus = {"param": param.name}

    def op_deleteParam(self, op: dict[str, Any]) -> None:
        block, param = self.param(op.get("name"))
        block.items.remove(param)
        if not block.items:
            self.game.items.remove(block)

    def enum_values(self, values: Any) -> list[str]:
        if not isinstance(values, list) or not values:
            raise EditError("un enumerado necesita al menos un valor", field="values")
        out = [_identifier(v, "cada valor", field="values") for v in values]
        if len(set(out)) != len(out):
            raise EditError("hay valores repetidos", field="values")
        return out

    def op_addEnum(self, op: dict[str, Any]) -> None:
        name = self.new_name(op, "name", "Kind", "el nombre del enumerado")
        values = self.enum_values(op.get("values"))
        taken = self.names()
        for v in values:
            if v in taken:
                raise EditError(f"ya hay algo que se llama `{v}`", field="values")
        self.add_game_item(ast.EnumDecl(name=name, values=values))
        self.focus = {"type": name}

    def op_updateEnum(self, op: dict[str, Any]) -> None:
        decl = self.declaration(op.get("name"))
        if not isinstance(decl, ast.EnumDecl):
            raise EditError(f"`{decl.name}` no es un enumerado")
        decl.values = self.enum_values(op.get("values"))
        self.focus = {"type": decl.name}

    def struct_fields(self, fields: Any) -> list[ast.StructField]:
        if not isinstance(fields, list) or not fields:
            raise EditError("un struct necesita al menos un campo", field="fields")
        out = []
        for i, f in enumerate(fields):
            name = _identifier(f.get("name"), "el nombre del campo", field=f"fields.{i}.name")
            out.append(
                ast.StructField(
                    name=name, type=_fragment(F.type_expr, f.get("type"), f"fields.{i}.type")
                )
            )
        if len({f.name for f in out}) != len(out):
            raise EditError("hay campos repetidos", field="fields")
        return out

    def op_addStruct(self, op: dict[str, Any]) -> None:
        name = self.new_name(op, "name", "Item", "el nombre del struct")
        self.add_game_item(ast.StructDecl(name=name, fields=self.struct_fields(op.get("fields"))))
        self.focus = {"type": name}

    def op_updateStruct(self, op: dict[str, Any]) -> None:
        decl = self.declaration(op.get("name"))
        if not isinstance(decl, ast.StructDecl):
            raise EditError(f"`{decl.name}` no es un struct")
        decl.fields = self.struct_fields(op.get("fields"))
        self.focus = {"type": decl.name}

    def op_deleteType(self, op: dict[str, Any]) -> None:
        decl = self.declaration(op.get("name"))
        if isinstance(decl, ast.FnDecl):
            raise EditError(f"`{decl.name}` es una función")
        self.game.items.remove(decl)

    def fn_params(self, params: Any) -> list[ast.FnParam]:
        out = []
        for i, p in enumerate(params or []):
            name = _identifier(p.get("name"), "el nombre del parámetro", field=f"params.{i}.name")
            out.append(
                ast.FnParam(
                    name=name, type=_fragment(F.type_expr, p.get("type"), f"params.{i}.type")
                )
            )
        if len({p.name for p in out}) != len(out):
            raise EditError("hay dos parámetros con el mismo nombre", field="params")
        return out

    def op_addFn(self, op: dict[str, Any]) -> None:
        name = self.new_name(op, "name", "helper", "el nombre de la función")
        fn = ast.FnDecl(
            name=name,
            params=self.fn_params(op.get("params")),
            returns=_fragment(F.type_expr, op.get("returns"), "returns"),
            body=_fragment(F.expression, op.get("body"), "body"),
        )
        if op.get("doc"):
            fn.doc = _text_value(op["doc"], "la documentación")
        self.add_game_item(fn)
        self.focus = {"fn": name}

    def op_updateFn(self, op: dict[str, Any]) -> None:
        fn = self.declaration(op.get("name"))
        if not isinstance(fn, ast.FnDecl):
            raise EditError(f"`{fn.name}` no es una función")
        if "params" in op:
            fn.params = self.fn_params(op["params"])
        if "returns" in op:
            fn.returns = _fragment(F.type_expr, op["returns"], "returns")
        if "body" in op:
            fn.body = _fragment(F.expression, op["body"], "body")
        if "doc" in op:
            fn.doc = _text_value(op["doc"], "la documentación") if op["doc"] else None
        self.focus = {"fn": fn.name}

    def op_deleteFn(self, op: dict[str, Any]) -> None:
        fn = self.declaration(op.get("name"))
        if not isinstance(fn, ast.FnDecl):
            raise EditError(f"`{fn.name}` no es una función")
        self.game.items.remove(fn)

    def op_setUiEntry(self, op: dict[str, Any]) -> None:
        """Pone (o quita, con `hints: null`) las pistas de un destino de `ui { … }`:
        `{"target": "board", "hints": "grid, label(\"Tablero\")"}`."""
        target = op.get("target")
        if not isinstance(target, str) or not target.strip():
            raise EditError("falta el destino de la pista", field="target")
        hints = op.get("hints")
        text = hints if isinstance(hints, str) else "hidden"
        items, _ = _fragment(lambda t: F.ui_entries(f"{target}: {t}"), text, "hints")
        if len(items) != 1:
            raise EditError("se esperaba un solo destino", field="target")
        entry = items[0]
        ui = self.block(ast.UiBlock, create=hints is not None)
        if ui is None:
            return
        same = [e for e in ui.entries if _ui_target(e) == _ui_target(entry)]
        position = ui.entries.index(same[0]) if same else len(ui.entries)
        for e in same:
            ui.entries.remove(e)
        if hints is not None:
            ui.entries.insert(position, entry)
        if not ui.entries:
            self.game.items.remove(ui)

    def op_insertSource(self, op: dict[str, Any]) -> None:
        """Añade declaraciones escritas en Nomos (lo que generan las plantillas y el diseñador de
        componentes): se mezclan con los bloques que ya existan."""
        items, _ = _fragment(F.game_items, op.get("source"), "source")
        taken = self.names()
        for item in items:
            match item:
                case ast.StateBlock(vars=variables):
                    for v in variables:
                        if v.name in taken:
                            raise EditError(f"ya hay algo que se llama `{v.name}`")
                    self.block(ast.StateBlock, create=True).vars.extend(variables)
                case ast.ParamsBlock(items=params):
                    self.block(ast.ParamsBlock, create=True).items.extend(params)
                case ast.UiBlock(entries=entries):
                    self.block(ast.UiBlock, create=True).entries.extend(entries)
                case ast.MetaBlock(entries=entries):
                    meta = self.block(ast.MetaBlock, create=True)
                    keys = {e.key for e in entries}
                    meta.entries = [e for e in meta.entries if e.key not in keys] + entries
                case ast.FlowBlock(items=flow_items):
                    flow = self.flow(create=True)
                    has_start = any(isinstance(m, ast.StartDecl) for m in flow.items)
                    for f in flow_items:
                        if isinstance(f, ast.StartDecl) and has_start:
                            continue
                        f.trivia.blank_before = isinstance(f, ast.NodeDecl)
                        flow.items.append(f)
                case ast.EnumDecl() | ast.StructDecl() | ast.FnDecl():
                    names = [item.name, *(item.values if isinstance(item, ast.EnumDecl) else [])]
                    for n in names:
                        if n in taken:
                            raise EditError(f"ya hay algo que se llama `{n}`")
                    self.add_game_item(item)
                case _:
                    self.add_game_item(item)
            taken = self.names()


def _ui_target(entry: ast.UiEntry) -> str:
    match entry.target:
        case "action":
            return "action " + ".".join(entry.path)
        case "node":
            return "node " + entry.path[0]
        case "seats":
            return "seats"
    return entry.path[0]


def _where(node: ast.NodeDecl, action: ast.ActionDecl | None) -> dict[str, Any]:
    return {"node": node.name, "action": action.name} if action is not None else {"node": node.name}


def _subnodes(node: ast.NodeDecl) -> Iterator[tuple[ast.NodeDecl, list[ast.Item], ast.NodeDecl]]:
    for m in node.members:
        if isinstance(m, ast.NodeDecl):
            yield m, node.members, node
            yield from _subnodes(m)


def _tidy_action(action: ast.ActionDecl) -> None:
    """Una acción sin efectos ni transiciones se escribe sin llaves."""
    if not action.effects and not action.transitions and not action.end_comments:
        action.effects = None


def _reorder(members: list[ast.Item], group: list[Any], item: Any, index: int) -> None:
    """Mueve `item` a la posición `index` dentro de su grupo (acciones o transiciones de un
    nodo), sin mover los demás miembros."""
    slots = [members.index(g) for g in group]
    order = [g for g in group if g is not item]
    order.insert(index, item)
    for slot, g in zip(slots, order, strict=True):
        members[slot] = g
