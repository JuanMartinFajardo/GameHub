# SPDX-License-Identifier: Apache-2.0
"""Parser de Nomos: descenso recursivo para declaraciones y sentencias, precedencia de
operadores para expresiones (ver la gramática en docs/wiki/lenguaje-game.md).

Recuperación de errores: un error dentro de un elemento (declaración, miembro de nodo,
sentencia) se informa y el parser salta hasta el final de ese elemento (salto de línea o `}`
del bloque), de modo que un solo archivo puede informar de varios errores independientes.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import TypeVar

from gamehub.lang import ast
from gamehub.lang.diagnostics import Diagnostics
from gamehub.lang.lexer import Comment, Token, tokenize
from gamehub.lang.source import Source, Span

NODE_KINDS = ("decision", "simultaneous", "window", "chance", "auto", "phase", "terminal")
COMPARISONS = ("==", "!=", "<", "<=", ">", ">=", "in")
STATEMENT_KEYWORDS = (
    "let",
    "if",
    "for",
    "move",
    "flip",
    "shuffle",
    "deal",
    "reveal",
    "emit",
    "reward",
    "fail",
)
ASSIGN_OPS = ("=", "+=", "-=", "*=")

ItemT = TypeVar("ItemT", bound=ast.Item)


class ParseError(Exception):
    """Error ya informado; sirve para abandonar el elemento actual."""


def parse(source: Source, diagnostics: Diagnostics) -> ast.File:
    tokens = tokenize(source, diagnostics)
    return Parser(tokens, diagnostics).file()


def parse_text(text: str, name: str = "<texto>") -> tuple[ast.File, Diagnostics]:
    diagnostics = Diagnostics()
    return parse(Source(name, text), diagnostics), diagnostics


def parse_expression(text: str, name: str = "<expresión>") -> tuple[ast.Expr, Diagnostics]:
    """Analiza una expresión suelta (tests, herramientas)."""
    diagnostics = Diagnostics()
    tokens = tokenize(Source(name, text), diagnostics)
    parser = Parser(tokens, diagnostics)
    try:
        expr = parser.expr()
        parser.skip_newlines()
        if not parser.at("eof"):
            parser.fail(f"sobra texto tras la expresión: {parser.peek().text!r}")
    except ParseError:
        expr = ast.NoneLit()
    return expr, diagnostics


class Parser:
    def __init__(self, tokens: list[Token], diagnostics: Diagnostics) -> None:
        self.tokens = tokens
        self.diagnostics = diagnostics
        self.pos = 0
        self.no_struct = False
        self.claimed: set[int] = set()

    # --- tokens ---------------------------------------------------------------------------------

    def peek(self, k: int = 0) -> Token:
        return self.tokens[min(self.pos + k, len(self.tokens) - 1)]

    def at(self, *kinds: str) -> bool:
        return self.peek().kind in kinds

    def at_word(self, *words: str) -> bool:
        tok = self.peek()
        return tok.kind == "ident" and tok.text in words

    def advance(self) -> Token:
        tok = self.peek()
        if tok.kind != "eof":
            self.pos += 1
        return tok

    def eat(self, kind: str) -> Token | None:
        return self.advance() if self.at(kind) else None

    def eat_word(self, word: str) -> Token | None:
        return self.advance() if self.at_word(word) else None

    def fail(self, message: str, span: Span | None = None, help: str | None = None) -> ParseError:
        tok = self.peek()
        self.diagnostics.error("E110", message, span or tok.span, _found(tok), help=help)
        return ParseError(message)

    def expect(self, kind: str, what: str | None = None) -> Token:
        if self.at(kind):
            return self.advance()
        raise self.fail(f"se esperaba {what or repr(kind)}")

    def expect_word(self, word: str) -> Token:
        if self.at_word(word):
            return self.advance()
        raise self.fail(f"se esperaba '{word}'")

    def ident(self, what: str = "un nombre") -> Token:
        if self.at("ident"):
            return self.advance()
        tok = self.peek()
        if tok.kind.isalpha() and tok.kind not in ("eof", "newline", "string", "int", "decimal"):
            raise self.fail(f"se esperaba {what}; '{tok.text}' es una palabra reservada")
        raise self.fail(f"se esperaba {what}")

    def skip_newlines(self) -> None:
        while self.at("newline", ";"):
            self.advance()

    def prev_span(self) -> Span:
        i = self.pos - 1
        while i > 0 and self.tokens[i].kind == "newline":
            i -= 1
        return self.tokens[max(i, 0)].span

    def span_from(self, start: int) -> Span:
        return self.tokens[start].span.to(self.prev_span())

    @contextmanager
    def struct_literals(self, allowed: bool) -> Iterator[None]:
        saved = self.no_struct
        self.no_struct = not allowed
        try:
            yield
        finally:
            self.no_struct = saved

    # --- comentarios y elementos ----------------------------------------------------------------

    def unclaimed(self, tok: Token) -> list[Comment]:
        return [c for c in tok.leading if id(c) not in self.claimed]

    def claim(self, comments: list[Comment]) -> list[Comment]:
        for c in comments:
            self.claimed.add(id(c))
        return comments

    def finish(self, node: ItemT, start: int) -> ItemT:
        """Completa un elemento que empieza en el token `start` y acaba en el anterior al
        actual: span, documentación (`///`), comentarios y línea en blanco previa."""
        node.span = self.span_from(start)
        first = self.tokens[start]
        leading = self.claim(self.unclaimed(first))
        docs = [c for c in leading if c.kind == "doc"]
        trivia = node.trivia
        trivia.leading = [c for c in leading if c.kind != "doc"]
        if docs and node.doc is None:
            node.doc = ast.Text("\n".join(c.body for c in docs), span=docs[0].span)
        elif docs:
            trivia.leading = leading
        for tok in self.tokens[start + 1 : self.pos]:
            trivia.inner.extend(self.claim(self.unclaimed(tok)))
        nxt = self.next_real()
        if nxt.leading and not nxt.leading[0].own_line and id(nxt.leading[0]) not in self.claimed:
            trivia.trailing = nxt.leading[0]
            self.claimed.add(id(nxt.leading[0]))
        trivia.blank_before = self.blank_before(start, leading)
        return node

    def next_real(self) -> Token:
        i = self.pos
        while self.tokens[i].kind == "newline":
            i += 1
        return self.tokens[i]

    def blank_before(self, start: int, leading: list[Comment]) -> bool:
        i = start - 1
        while i >= 0 and self.tokens[i].kind == "newline":
            i -= 1
        if i < 0:
            return False
        prev_line = self.tokens[i].span.end_line
        first_line = leading[0].span.line if leading else self.tokens[start].span.line
        if leading and not leading[0].own_line:
            return False
        source = self.tokens[start].span.source
        if source is None:
            return False
        return any(not source.line_text(n).strip() for n in range(prev_line + 1, first_line))

    def end_item(self, commas: bool = False) -> None:
        """Tras un elemento: salto de línea, ';' (o ',' si se admite), o el '}' del bloque."""
        if (commas and self.eat(",")) or self.at("newline", ";"):
            self.skip_newlines()
        elif not self.at("}", "eof"):
            raise self.fail("se esperaba un salto de línea antes del siguiente elemento")

    def synchronize(self) -> None:
        depth = 0
        while not self.at("eof"):
            tok = self.peek()
            if tok.kind == "{":
                depth += 1
            elif tok.kind == "}":
                if depth == 0:
                    return
                depth -= 1
            elif tok.kind in ("newline", ";") and depth == 0:
                self.skip_newlines()
                return
            self.advance()

    def block(
        self, parse_one: Callable[[], ast.Item | None], *, commas: bool = False
    ) -> tuple[list[ast.Item], list[Comment]]:
        """`{ elemento* }` con recuperación de errores. Devuelve los elementos y los
        comentarios que quedan antes del `}`."""
        self.expect("{", "'{'")
        items: list[ast.Item] = []
        while True:
            self.skip_newlines()
            if self.at("}"):
                break
            if self.at("eof"):
                self.fail("falta '}' para cerrar el bloque")
                return items, []
            start = self.pos
            try:
                item = parse_one()
                if item is not None:
                    items.append(item)
                self.end_item(commas)
            except ParseError:
                self.synchronize()
            if self.pos == start:
                self.advance()
        # Los comentarios antes de '}' solo se reclaman si quien llama los guarda; si no, pasan
        # a ser comentarios interiores del elemento que contiene el bloque (no se pierden).
        end = self.unclaimed(self.peek())
        self.advance()
        return items, end

    # --- archivo --------------------------------------------------------------------------------

    def file(self) -> ast.File:
        items: list[ast.Item] = []
        self.skip_newlines()
        while not self.at("eof"):
            start = self.pos
            try:
                item = self.top_item()
                items.append(item)
                self.end_item()
            except ParseError:
                self.synchronize()
                if self.at("}"):
                    self.advance()
            if self.pos == start:
                self.advance()
            self.skip_newlines()
        end = self.claim(self.unclaimed(self.peek()))
        return ast.File(items=items, end_comments=self.claim(end))

    def top_item(self) -> ast.Item:
        start = self.pos
        doc = self.annotations_doc_only()
        if self.at("import"):
            return self.finish(self.import_decl(), start)
        if self.at("game"):
            item = self.game_decl()
        elif self.at("enum"):
            item = self.enum_decl()
        elif self.at("struct"):
            item = self.struct_decl()
        elif self.at("fn"):
            item = self.fn_decl()
        else:
            raise self.fail("se esperaba 'import', 'game', 'enum', 'struct' o 'fn'")
        item.doc = doc or item.doc
        return self.finish(item, start)

    def annotations_doc_only(self) -> ast.Text | None:
        """`@doc(texto)` antes de una declaración que no admite otras anotaciones."""
        doc = None
        for name, arg, span in self.annotations():
            if name == "doc" and isinstance(arg, ast.Text):
                doc = arg
            else:
                self.diagnostics.error("E111", f"anotación no permitida aquí: @{name}", span)
        return doc

    def annotations(self) -> list[tuple[str, ast.Text | ast.Visibility, Span]]:
        result: list[tuple[str, ast.Text | ast.Visibility, Span]] = []
        while self.at("annotation"):
            tok = self.advance()
            name = tok.value
            self.expect("(", "'(' tras la anotación")
            arg: ast.Text | ast.Visibility
            if name == "doc":
                arg = self.text()
            elif name in ("visible", "size_visible"):
                arg = self.visibility()
            else:
                raise self.fail(
                    f"anotación desconocida: @{name}",
                    tok.span,
                    help="se admiten @visible, @size_visible y @doc",
                )
            self.expect(")", "')'")
            result.append((name, arg, tok.span.to(self.prev_span())))
            self.skip_newlines()
        return result

    def visibility(self) -> ast.Visibility:
        start = self.pos
        if self.at_word("all", "owner") and self.peek(1).kind == ")":
            word = self.advance().text
            return ast.Visibility(word, span=self.span_from(start))
        if self.at("none") and self.peek(1).kind == ")":
            self.advance()
            return ast.Visibility("none", span=self.span_from(start))
        expr = self.expr()
        return ast.Visibility("when", expr, span=self.span_from(start))

    def text(self) -> ast.Text:
        start = self.pos
        if self.at("string"):
            return ast.Text(self.advance().value, span=self.span_from(start))
        if self.at("{"):
            self.advance()
            entries: dict[str, str] = {}
            while True:
                self.skip_newlines()
                if self.eat("}"):
                    break
                if self.at("string"):
                    lang = self.advance().value
                else:
                    lang = self.ident("un código de idioma (es, en…)").text
                self.expect(":", "':'")
                value = self.expect("string", "un texto entre comillas")
                entries[lang] = value.value
                self.skip_newlines()
                if not self.eat(","):
                    self.skip_newlines()
                    self.expect("}", "',' o '}'")
                    break
            if not entries:
                raise self.fail("un texto traducible necesita al menos un idioma")
            return ast.Text(entries, span=self.span_from(start))
        raise self.fail('se esperaba un texto ("…" o { es: "…", en: "…" })')

    def import_decl(self) -> ast.Import:
        self.expect("import")
        path = [self.ident("el nombre de un módulo").text]
        names: list[str] | None = []
        while self.eat("."):
            if self.eat("*"):
                names = None
                break
            if self.at("{"):
                self.advance()
                while True:
                    self.skip_newlines()
                    if self.eat("}"):
                        break
                    assert names is not None
                    names.append(self.ident("un nombre a importar").text)
                    self.skip_newlines()
                    if not self.eat(","):
                        self.skip_newlines()
                        self.expect("}", "',' o '}'")
                        break
                break
            path.append(self.ident("el nombre de un módulo").text)
        if names == []:
            raise self.fail(
                "indica qué importar: import modulo.{A, B} o import modulo.*",
                help="por ejemplo: import std.cards.{Card, Suit, Rank, french52}",
            )
        return ast.Import(path=path, names=names)

    # --- juego ----------------------------------------------------------------------------------

    def game_decl(self) -> ast.GameDecl | ast.GameAlias:
        self.expect("game")
        name = self.ident("el nombre del juego").text
        if self.eat("="):
            combinator = self.ident("un combinador (repeat, best_of)").text
            self.expect("(", "'('")
            self.skip_newlines()
            base = self.ident("el juego base").text
            args: list[tuple[str, ast.Expr]] = []
            while True:
                self.skip_newlines()
                if self.eat(")"):
                    break
                self.expect(",", "',' o ')'")
                self.skip_newlines()
                if self.eat(")"):
                    break
                key = self.ident("el nombre de un argumento").text
                self.expect(":", "':'")
                args.append((key, self.expr()))
            return ast.GameAlias(name=name, combinator=combinator, base=base, args=args)
        extends = None
        if self.eat("extends"):
            extends = self.ident("el juego base").text
        items, end = self.block(self.game_item)
        return ast.GameDecl(name=name, extends=extends, items=items, end_comments=self.claim(end))

    def game_item(self) -> ast.Item:
        start = self.pos
        kind = self.peek().kind
        if kind == "annotation":
            doc = self.annotations_doc_only()
            item = self.game_item_body()
            item.doc = doc or item.doc
            return self.finish(item, start)
        return self.finish(self.game_item_body(), start)

    def game_item_body(self) -> ast.Item:
        kind = self.peek().kind
        match kind:
            case "meta":
                return self.meta_block()
            case "players":
                return self.players_decl()
            case "params":
                return self.params_block()
            case "enum":
                return self.enum_decl()
            case "struct":
                return self.struct_decl()
            case "state":
                return self.state_block()
            case "fn":
                return self.fn_decl()
            case "flow":
                return self.flow_block()
            case "test":
                return self.test_decl()
            case "invariant":
                self.advance()
                return ast.InvariantDecl(expr=self.expr())
            case "override":
                self.advance()
                start = self.pos
                if self.at(*NODE_KINDS):
                    inner: ast.Item = self.node_decl()
                else:
                    inner = self.game_item_body()
                if not isinstance(
                    inner,
                    ast.FnDecl
                    | ast.EnumDecl
                    | ast.StructDecl
                    | ast.NodeDecl
                    | ast.ParamsBlock
                    | ast.StateBlock,
                ):
                    raise self.fail(
                        "'override' se aplica a fn, enum, struct, un nodo, params o state",
                        self.span_from(start),
                    )
                return ast.OverrideDecl(item=self.finish(inner, start))
            case "remove":
                self.advance()
                what = self.ident("qué eliminar (node, fn, state, param, enum, struct, action)")
                if what.text not in ("node", "fn", "state", "param", "enum", "struct", "action"):
                    raise self.fail(
                        f"no se puede eliminar '{what.text}'",
                        what.span,
                        help="remove node X · remove fn f · remove state x · remove param p · "
                        "remove enum E · remove struct S · remove action Nodo.accion",
                    )
                path = [self.ident().text]
                while self.eat("."):
                    path.append(self.ident().text)
                return ast.RemoveDecl(kind=what.text, path=path)
            case "extend":
                self.advance()
                self.expect_word("node")
                name = self.ident("el nombre de un nodo").text
                items, end = self.block(lambda: self.node_member("decision"))
                return ast.ExtendNode(name=name, members=items, end_comments=self.claim(end))
            case "decision" | "simultaneous" | "window" | "chance" | "auto" | "phase" | "terminal":
                raise self.fail("los nodos van dentro de 'flow {{ … }}', no sueltos en el juego")
        raise self.fail(
            "se esperaba meta, players, params, enum, struct, state, fn, flow, test o invariant"
        )

    def meta_block(self) -> ast.MetaBlock:
        self.expect("meta")

        def entry() -> ast.MetaEntry:
            start = self.pos
            key = self.ident("un campo de meta (title, version, tags…)").text
            self.expect(":", "':'")
            value: object
            if self.at("["):
                self.advance()
                values: list[str] = []
                while True:
                    self.skip_newlines()
                    if self.eat("]"):
                        break
                    tok = self.peek()
                    if tok.kind in ("string", "ident"):
                        self.advance()
                        values.append(tok.value)
                    else:
                        raise self.fail("se esperaba un texto")
                    self.skip_newlines()
                    if not self.eat(","):
                        self.skip_newlines()
                        self.expect("]", "',' o ']'")
                        break
                value = values
            else:
                value = self.text()
            return self.finish(ast.MetaEntry(key=key, value=value), start)

        items, end = self.block(entry, commas=True)
        entries = [i for i in items if isinstance(i, ast.MetaEntry)]
        return ast.MetaBlock(entries=entries, end_comments=self.claim(end))

    def players_decl(self) -> ast.PlayersDecl:
        self.expect("players")
        lo = self.expect("int", "un número de jugadores").value
        hi = lo
        if self.eat(".."):
            hi = self.expect("int", "el máximo de jugadores").value
        return ast.PlayersDecl(min=lo, max=hi)

    def params_block(self) -> ast.ParamsBlock:
        self.expect("params")

        def item() -> ast.Item:
            start = self.pos
            doc = self.annotations_doc_only()
            node: ast.Item
            if self.eat("assert"):
                expr = self.expr()
                message = None
                if self.eat(","):
                    self.skip_newlines_inside()
                    message = self.text()
                node = ast.AssertDecl(expr=expr, message=message)
            else:
                name = self.ident("el nombre de un parámetro").text
                self.expect(":", "':' y el tipo del parámetro")
                type_ = self.type_expr()
                self.expect("=", "'=' y el valor por defecto")
                node = ast.ParamDecl(name=name, type=type_, default=self.value())
            node.doc = doc
            return self.finish(node, start)

        items, end = self.block(item)
        return ast.ParamsBlock(items=items, end_comments=self.claim(end))

    def enum_decl(self) -> ast.EnumDecl:
        self.expect("enum")
        name = self.ident("el nombre del enumerado").text
        self.expect("{", "'{'")
        values: list[str] = []
        while True:
            self.skip_newlines()
            if self.eat("}"):
                break
            values.append(self.ident("un valor del enumerado").text)
            self.skip_newlines()
            if not self.eat(","):
                self.skip_newlines()
                self.expect("}", "',' o '}'")
                break
        if not values:
            raise self.fail("un enumerado necesita al menos un valor", self.prev_span())
        return ast.EnumDecl(name=name, values=values)

    def struct_decl(self) -> ast.StructDecl:
        self.expect("struct")
        name = self.ident("el nombre del struct").text

        def field() -> ast.StructField:
            start = self.pos
            fname = self.ident("el nombre de un campo").text
            self.expect(":", "':' y el tipo del campo")
            node = ast.StructField(name=fname, type=self.type_expr())
            return self.finish(node, start)

        items, _ = self.block(field, commas=True)
        return ast.StructDecl(
            name=name, fields=[f for f in items if isinstance(f, ast.StructField)]
        )

    def state_block(self) -> ast.StateBlock:
        self.expect("state")

        def var() -> ast.StateVar:
            start = self.pos
            node = ast.StateVar(name="", type=ast.TName("Int"))
            for name, arg, span in self.annotations():
                if name == "doc" and isinstance(arg, ast.Text):
                    node.doc = arg
                elif name == "visible" and isinstance(arg, ast.Visibility):
                    node.visibility = arg
                elif name == "size_visible" and isinstance(arg, ast.Visibility):
                    node.size_visibility = arg
                else:
                    self.diagnostics.error("E111", f"anotación no permitida aquí: @{name}", span)
            node.name = self.ident("el nombre de una variable de estado").text
            self.expect(":", "':' y el tipo de la variable")
            node.type = self.type_expr()
            if self.eat("="):
                node.init = self.value()
            return self.finish(node, start)

        items, end = self.block(var)
        return ast.StateBlock(
            vars=[v for v in items if isinstance(v, ast.StateVar)], end_comments=self.claim(end)
        )

    def fn_decl(self) -> ast.FnDecl:
        self.expect("fn")
        name = self.ident("el nombre de la función").text
        self.expect("(", "'('")
        params: list[ast.FnParam] = []
        while not self.eat(")"):
            start = self.pos
            pname = self.ident("el nombre de un parámetro").text
            self.expect(":", "':' y el tipo del parámetro")
            params.append(
                ast.FnParam(name=pname, type=self.type_expr(), span=self.span_from(start))
            )
            if not self.eat(","):
                self.expect(")", "',' o ')'")
                break
        self.expect("->", "'->' y el tipo del resultado")
        returns = self.type_expr()
        if self.at("{"):
            body = self.let_block(allow_empty=True)
        else:
            self.expect("=", "'=' o '{' con el cuerpo de la función")
            body = self.value()
        return ast.FnDecl(name=name, params=params, returns=returns, body=body)

    # --- tipos ----------------------------------------------------------------------------------

    def type_expr(self) -> ast.TypeExpr:
        start = self.pos
        base = self.type_base()
        while self.at("?"):
            self.advance()
            base = ast.TOption(base, span=self.span_from(start))
        return base

    def type_base(self) -> ast.TypeExpr:
        start = self.pos
        if self.eat("("):
            items = [self.type_expr()]
            while self.eat(","):
                items.append(self.type_expr())
            self.expect(")", "')'")
            if len(items) < 2:
                raise self.fail(
                    "una tupla necesita al menos dos componentes", self.span_from(start)
                )
            return ast.TTuple(items, span=self.span_from(start))
        tok = self.ident("un tipo")
        name = tok.text
        if name == "per_player":
            return ast.TPerPlayer(self.type_expr(), span=self.span_from(start))
        if name == "Grid":
            self.expect("[", "'[' con las dimensiones (ancho, alto)")
            width = self.dimension()
            self.expect(",", "','")
            height = self.dimension()
            self.expect("]", "']'")
            self.expect_word("of")
            return ast.TGrid(width, height, self.type_expr(), span=self.span_from(start))
        if self.at("<"):
            self.advance()
            args = [self.type_expr()]
            while self.eat(","):
                args.append(self.type_expr())
            self.expect(">", "'>'")
            return ast.TGeneric(name, args, span=self.span_from(start))
        return ast.TName(name, span=self.span_from(start))

    def dimension(self) -> int | str:
        if self.at("int"):
            return self.advance().value
        return self.ident("una dimensión (entero o parámetro)").text

    # --- flow -----------------------------------------------------------------------------------

    def flow_block(self) -> ast.FlowBlock:
        self.expect("flow")
        items, end = self.block(self.flow_item)
        return ast.FlowBlock(items=items, end_comments=self.claim(end))

    def flow_item(self) -> ast.Item:
        start = self.pos
        doc = self.annotations_doc_only()
        if self.at("start"):
            item: ast.Item = self.start_decl()
        elif self.at(*NODE_KINDS):
            item = self.node_decl()
        else:
            raise self.fail(
                "se esperaba 'start' o un nodo (decision, simultaneous, window, chance, auto, "
                "phase, terminal)"
            )
        item.doc = doc or item.doc
        return self.finish(item, start)

    def start_decl(self) -> ast.StartDecl:
        self.expect("start")
        setup = None
        if self.at("{"):
            setup = self.stmt_block()
        self.expect("->", "'->' y el nodo inicial")
        target = self.ident("el nombre del nodo inicial").text
        return ast.StartDecl(target=target, setup=setup)

    def node_decl(self) -> ast.NodeDecl:
        kind = self.advance().kind
        name = self.ident("el nombre del nodo").text
        items, end = self.block(lambda: self.node_member(kind))
        return ast.NodeDecl(kind=kind, name=name, members=items, end_comments=self.claim(end))

    def node_member(self, kind: str) -> ast.Item:
        start = self.pos
        annotations = self.annotations()
        if self.at("action"):
            return self.finish(self.action_decl(annotations), start)
        if self.at("emit") and kind in ("chance", "auto"):
            return self.finish(self.emit_stmt(annotations), start)
        item = self.node_member_body(kind)
        self.apply_doc(item, annotations)
        return self.finish(item, start)

    def apply_doc(
        self, item: ast.Item, annotations: list[tuple[str, ast.Text | ast.Visibility, Span]]
    ) -> None:
        for name, arg, span in annotations:
            if name == "doc" and isinstance(arg, ast.Text):
                item.doc = arg
            else:
                self.diagnostics.error("E111", f"anotación no permitida aquí: @{name}", span)

    def node_member_body(self, kind: str) -> ast.Item:
        if self.at("action"):
            return self.action_decl([])
        if self.at("->"):
            return self.transition()
        if self.at("start"):
            return self.start_decl()
        if self.at(*NODE_KINDS):
            return self.node_decl()
        if self.at("let") and kind == "terminal":
            self.advance()
            name = self.ident("el nombre de la variable").text
            self.expect("=", "'='")
            return ast.LetMember(name=name, value=self.value())
        if self.at("ident") and self.peek(1).kind == ":":
            key = self.advance().text
            self.advance()
            return ast.Member(key=key, value=self.value())
        if (
            self.at("ident")
            and self.peek(1).kind == "{"
            and self.peek().text
            in (
                "resolve",
                "on_enter",
                "on_exit",
            )
        ):
            key = self.advance().text
            body, end = self.stmt_block_with_end()
            return ast.BlockMember(key=key, body=body, end_comments=self.claim(end))
        if kind in ("chance", "auto"):
            return self.stmt_body([])
        members = ("actor", "actors", "eligible", "mode", "order", "payoff", "rank")
        if self.at_word(*members):
            raise self.fail(
                f"falta ':' tras '{self.peek().text}'", help=f"escribe '{self.peek().text}: …'"
            )
        raise self.fail(
            "se esperaba un miembro del nodo (por ejemplo 'actor: …'), una acción o una "
            "transición ('-> Nodo')"
        )

    def action_decl(
        self, annotations: list[tuple[str, ast.Text | ast.Visibility, Span]]
    ) -> ast.ActionDecl:
        self.expect("action")
        node = ast.ActionDecl(name=self.ident("el nombre de la acción").text)
        for name, arg, span in annotations:
            if name == "doc" and isinstance(arg, ast.Text):
                node.doc = arg
            elif name == "visible" and isinstance(arg, ast.Visibility):
                node.visibility = arg
            else:
                self.diagnostics.error(
                    "E111", f"anotación no permitida en una acción: @{name}", span
                )
        self.expect("(", "'(' con los parámetros de la acción")
        while not self.eat(")"):
            node.params.append(self.action_param())
            if not self.eat(","):
                self.expect(")", "',' o ')'")
                break
        if self.eat("requires"):
            with self.struct_literals(False):
                node.requires = self.value()
        if self.at("{"):
            items, end = self.block(self.action_body_item)
            node.end_comments = self.claim(end)
            node.effects = []
            for item in items:
                if isinstance(item, ast.Transition):
                    node.transitions.append(item)
                elif isinstance(item, ast.Stmt):
                    if node.transitions:
                        self.diagnostics.error(
                            "E112",
                            "las sentencias de una acción van antes de sus transiciones",
                            item.span,
                            help="la IR ejecuta primero los efectos y después evalúa las "
                            "transiciones",
                        )
                    node.effects.append(item)
        return node

    def action_body_item(self) -> ast.Item:
        """Dentro de `action … { }`: sentencias y, al final, transiciones propias."""
        start = self.pos
        annotations = self.annotations()
        if self.at("emit"):
            return self.finish(self.emit_stmt(annotations), start)
        item: ast.Item = self.transition() if self.at("->") else self.stmt_body([])
        self.apply_doc(item, annotations)
        return self.finish(item, start)

    def action_param(self) -> ast.ActionParam:
        start = self.pos
        param = ast.ActionParam(name="")
        for name, arg, span in self.annotations():
            if name == "visible" and isinstance(arg, ast.Visibility):
                param.visibility = arg
            elif name == "size_visible" and isinstance(arg, ast.Visibility):
                param.size_visibility = arg
            else:
                self.diagnostics.error("E111", f"anotación no permitida aquí: @{name}", span)
        param.name = self.ident("el nombre del parámetro").text
        if self.eat(":"):
            param.type = self.type_expr()
        if self.eat("in"):
            param.domain = self.expr()
        if param.type is None and param.domain is None:
            raise self.fail(
                f"el parámetro '{param.name}' necesita un tipo o un dominio",
                self.span_from(start),
                help=f"por ejemplo: {param.name}: Choice  ·  {param.name} in 1..6",
            )
        param.span = self.span_from(start)
        return param

    def transition(self) -> ast.Transition:
        self.expect("->")
        target = "exit" if self.eat("exit") else self.ident("el nodo de destino (o 'exit')").text
        node = ast.Transition(target=target)
        if self.eat("when"):
            with self.struct_literals(False):
                node.when = self.value()
        if self.at("{"):
            node.effects = self.stmt_block()
        return node

    # --- sentencias -----------------------------------------------------------------------------

    def stmt_block(self) -> list[ast.Stmt]:
        body, _ = self.stmt_block_with_end()
        return body

    def stmt_block_with_end(self) -> tuple[list[ast.Stmt], list[Comment]]:
        items, end = self.block(self.stmt)
        return [s for s in items if isinstance(s, ast.Stmt)], end

    def stmt(self) -> ast.Stmt:
        start = self.pos
        annotations = self.annotations()
        if self.at("emit"):
            return self.finish(self.emit_stmt(annotations), start)
        doc = None
        for name, arg, span in annotations:
            if name == "doc" and isinstance(arg, ast.Text):
                doc = arg
            else:
                self.diagnostics.error("E111", f"anotación no permitida aquí: @{name}", span)
        node = self.stmt_body([])
        node.doc = doc or node.doc
        return self.finish(node, start)

    def stmt_body(self, annotations: list[tuple[str, ast.Text | ast.Visibility, Span]]) -> ast.Stmt:
        kind = self.peek().kind
        match kind:
            case "let":
                self.advance()
                name = self.ident("el nombre de la variable").text
                self.expect("=", "'='")
                return ast.LetStmt(name, self.value())
            case "if":
                return self.if_stmt()
            case "for":
                self.advance()
                var = self.ident("la variable del bucle").text
                self.expect("in", "'in'")
                with self.struct_literals(False):
                    iterable = self.expr()
                return ast.ForStmt(var, iterable, self.stmt_block())
            case "move":
                self.advance()
                selector = self.selector()
                self.expect_word("from")
                source = self.expr()
                self.expect_word("to")
                dest = self.expr()
                position = None
                if self.eat_word("at"):
                    if not self.at_word("top", "bottom"):
                        raise self.fail("se esperaba 'top' o 'bottom'")
                    position = self.advance().text
                return ast.MoveStmt(selector, source, dest, position)
            case "flip":
                self.advance()
                selector = self.selector()
                self.expect_word("of")
                zone = self.expr()
                if self.eat_word("face_up"):
                    face: ast.Expr = ast.BoolLit(True)
                elif self.eat_word("face_down"):
                    face = ast.BoolLit(False)
                elif self.eat_word("face"):
                    self.expect("(", "'('")
                    face = self.expr()
                    self.expect(")", "')'")
                    face = ast.Paren(face, span=face.span)
                else:
                    raise self.fail("se esperaba face_up, face_down o face(expresión)")
                return ast.FlipStmt(selector, zone, face)
            case "shuffle":
                self.advance()
                return ast.ShuffleStmt(self.expr())
            case "deal":
                self.advance()
                count = None
                if not self.eat_word("all"):
                    count = self.expr()
                self.expect_word("from")
                source = self.expr()
                self.expect_word("to")
                self.expect_word("each")
                return ast.DealStmt(count, source, self.expr())
            case "reveal":
                self.advance()
                value = self.expr()
                self.expect_word("to")
                to = None
                if not (self.at_word("all") and self.peek(1).kind != "("):
                    to = self.expr()
                else:
                    self.advance()
                label = self.text() if self.eat_word("as") else None
                return ast.RevealStmt(value, to, label)
            case "emit":
                return self.emit_stmt(annotations)
            case "reward":
                self.advance()
                amount = self.expr()
                self.expect_word("to")
                return ast.RewardStmt(amount, self.expr())
            case "fail":
                self.advance()
                return ast.FailStmt(self.text())
        if kind in ("->",):
            raise self.fail("las transiciones van al final del bloque del nodo o de la acción")
        target = self.expr()
        if not self.at(*ASSIGN_OPS):
            raise self.fail(
                "se esperaba una sentencia (asignación, let, if, for, move…)",
                help="una expresión suelta no tiene efecto",
            )
        op = self.advance().kind
        return ast.Assign(target, op, self.value())

    def emit_stmt(
        self, annotations: list[tuple[str, ast.Text | ast.Visibility, Span]]
    ) -> ast.EmitStmt:
        self.expect("emit")
        name = self.ident("el nombre del evento").text
        fields = self.field_list()
        node = ast.EmitStmt(name, fields)
        for aname, arg, span in annotations:
            if aname == "visible" and isinstance(arg, ast.Visibility):
                node.visibility = arg
            elif aname == "doc" and isinstance(arg, ast.Text):
                node.doc = arg
            else:
                self.diagnostics.error("E111", f"anotación no permitida aquí: @{aname}", span)
        return node

    def field_list(self) -> list[tuple[str, ast.Expr]]:
        self.expect("{", "'{'")
        fields: list[tuple[str, ast.Expr]] = []
        while True:
            self.skip_newlines()
            if self.eat("}"):
                break
            key = self.ident("el nombre de un campo").text
            self.expect(":", "':'")
            with self.struct_literals(True):
                fields.append((key, self.expr()))
            self.skip_newlines()
            if not self.eat(","):
                self.skip_newlines()
                self.expect("}", "',' o '}'")
                break
        return fields

    def if_stmt(self) -> ast.IfStmt:
        self.expect("if")
        with self.struct_literals(False):
            cond = self.expr()
        then = self.stmt_block()
        other: list[ast.Stmt] | None = None
        if self.at("newline") and self.peek(1).kind == "else":
            self.advance()
        if self.eat("else"):
            if self.at("if"):
                start = self.pos
                nested = self.finish(self.if_stmt(), start)
                other = [nested]
            else:
                other = self.stmt_block()
        return ast.IfStmt(cond, then, other)

    def selector(self) -> ast.Selector:
        """`all`, `top n`, `bottom n`, `at i` o una expresión (un valor o una lista de valores).
        Una variable llamada `top` se puede mover con `move (top) from …`."""
        start = self.pos
        nxt = self.peek(1)
        before_from = nxt.kind == "ident" and nxt.text in ("from", "of")
        if self.at_word("all") and before_from:
            self.advance()
            return ast.Selector("all", span=self.span_from(start))
        if self.at_word("top", "bottom", "at") and not before_from:
            kind = self.advance().text
            return ast.Selector(kind, self.expr(), span=self.span_from(start))
        return ast.Selector("value", self.expr(), span=self.span_from(start))

    # --- expresiones ----------------------------------------------------------------------------

    def expr(self) -> ast.Expr:
        start = self.pos
        value = self.or_expr()
        if self.at("if"):
            self.advance()
            cond = self.or_expr()
            self.expect("else", "'else' (expresión condicional: a if c else b)")
            other = self.expr()
            return ast.IfExpr(value, cond, other, span=self.span_from(start))
        return value

    def or_expr(self) -> ast.Expr:
        start = self.pos
        left = self.and_expr()
        while self.at("or"):
            self.advance()
            self.skip_newlines_inside()
            left = ast.Binary("or", left, self.and_expr(), span=self.span_from(start))
        return left

    def and_expr(self) -> ast.Expr:
        start = self.pos
        left = self.not_expr()
        while self.at("and"):
            self.advance()
            self.skip_newlines_inside()
            left = ast.Binary("and", left, self.not_expr(), span=self.span_from(start))
        return left

    def not_expr(self) -> ast.Expr:
        start = self.pos
        if self.eat("not"):
            return ast.Unary("not", self.not_expr(), span=self.span_from(start))
        return self.comparison()

    def comparison(self) -> ast.Expr:
        start = self.pos
        left = self.range_expr()
        op = self.comparison_op()
        if op is None:
            return left
        self.skip_newlines_inside()
        right = self.range_expr()
        node = ast.Binary(op, left, right, span=self.span_from(start))
        if self.comparison_op(peek_only=True) is not None:
            raise self.fail(
                "las comparaciones no se encadenan",
                help="escribe 'a < b and b < c' en lugar de 'a < b < c'",
            )
        return node

    def comparison_op(self, peek_only: bool = False) -> str | None:
        tok = self.peek()
        if tok.kind in COMPARISONS:
            if not peek_only:
                self.advance()
            return tok.kind
        if tok.kind == "not" and self.peek(1).kind == "in":
            if not peek_only:
                self.advance()
                self.advance()
            return "not in"
        return None

    def range_expr(self) -> ast.Expr:
        start = self.pos
        lo = self.additive()
        if self.at("..", "..<"):
            inclusive = self.advance().kind == ".."
            hi = self.additive()
            return ast.RangeExpr(lo, hi, inclusive, span=self.span_from(start))
        return lo

    def additive(self) -> ast.Expr:
        start = self.pos
        left = self.multiplicative()
        while self.at("+", "-"):
            op = self.advance().kind
            self.skip_newlines_inside()
            left = ast.Binary(op, left, self.multiplicative(), span=self.span_from(start))
        return left

    def multiplicative(self) -> ast.Expr:
        start = self.pos
        left = self.unary()
        while self.at("*", "/", "div", "%"):
            op = self.advance().kind
            self.skip_newlines_inside()
            left = ast.Binary(op, left, self.unary(), span=self.span_from(start))
        return left

    def unary(self) -> ast.Expr:
        start = self.pos
        if self.eat("-"):
            return ast.Unary("-", self.unary(), span=self.span_from(start))
        return self.postfix()

    def skip_newlines_inside(self) -> None:
        """Tras un operador binario la expresión continúa en la línea siguiente."""
        while self.at("newline"):
            self.advance()

    def value(self) -> ast.Expr:
        """Expresión tras `=`, `requires`, `when` o la clave de un miembro (`payoff:`): puede
        empezar en la línea siguiente, como la deja el formateador cuando no cabe."""
        self.skip_newlines_inside()
        return self.expr()

    def postfix(self) -> ast.Expr:
        start = self.pos
        expr = self.primary()
        while True:
            if self.at("("):
                if not isinstance(expr, ast.Name):
                    raise self.fail("solo se pueden llamar funciones por su nombre")
                expr = self.call(expr.name, start)
            elif self.at("["):
                self.advance()
                with self.struct_literals(True):
                    expr = self.index_or_slice(expr, start)
            elif self.at("."):
                self.advance()
                name = self.ident("el nombre de un campo").text
                expr = ast.Field(expr, name, span=self.span_from(start))
            else:
                return expr

    def call(self, func: str, start: int) -> ast.Expr:
        self.expect("(")
        with self.struct_literals(True):
            if self.eat(")"):
                return ast.Call(func, [], span=self.span_from(start))
            first = self.expr()
            if (
                self.at(":")
                and isinstance(first, ast.Binary)
                and first.op == "in"
                and isinstance(first.left, ast.Name)
            ):
                self.advance()
                body = self.expr()
                self.expect(")", "')'")
                return ast.Aggregate(
                    func, first.left.name, first.right, body, span=self.span_from(start)
                )
            args = [first]
            while self.eat(","):
                if self.at(")"):
                    break
                args.append(self.expr())
            self.expect(")", "',' o ')'")
        return ast.Call(func, args, span=self.span_from(start))

    def index_or_slice(self, target: ast.Expr, start: int) -> ast.Expr:
        lo = None if self.at(":") else self.expr()
        if self.eat(":"):
            hi = None if self.at("]") else self.expr()
            self.expect("]", "']'")
            return ast.Slice(target, lo, hi, span=self.span_from(start))
        self.expect("]", "']'")
        assert lo is not None
        return ast.Index(target, lo, span=self.span_from(start))

    def primary(self) -> ast.Expr:
        start = self.pos
        tok = self.peek()
        match tok.kind:
            case "int":
                self.advance()
                return ast.IntLit(tok.value, span=tok.span)
            case "decimal":
                self.advance()
                return ast.DecimalLit(tok.value, tok.text.replace("_", ""), span=tok.span)
            case "string":
                self.advance()
                return ast.StrLit(tok.value, span=tok.span)
            case "true" | "false":
                self.advance()
                return ast.BoolLit(tok.kind == "true", span=tok.span)
            case "none":
                self.advance()
                return ast.NoneLit(span=tok.span)
            case "ident":
                self.advance()
                if self.at("{") and not self.no_struct:
                    fields = self.field_list()
                    return ast.StructLit(tok.text, fields, span=self.span_from(start))
                return ast.Name(tok.text, span=tok.span)
            case "(":
                self.advance()
                with self.struct_literals(True):
                    first = self.expr()
                    if self.eat(","):
                        items = [first]
                        while not self.at(")"):
                            items.append(self.expr())
                            if not self.eat(","):
                                break
                        self.expect(")", "')'")
                        if len(items) < 2:
                            raise self.fail("una tupla necesita al menos dos componentes")
                        return ast.TupleLit(items, span=self.span_from(start))
                    self.expect(")", "')'")
                return ast.Paren(first, span=self.span_from(start))
            case "[":
                return self.list_or_comprehension()
            case "{":
                return self.let_block(allow_empty=False)
            case "case":
                return self.case_expr()
            case "match":
                return self.match_expr()
        if tok.kind == "newline":
            raise self.fail("la expresión está incompleta al final de la línea")
        raise self.fail("se esperaba una expresión")

    def list_or_comprehension(self) -> ast.Expr:
        start = self.pos
        self.expect("[")
        with self.struct_literals(True):
            if self.eat("]"):
                return ast.ListLit([], span=self.span_from(start))
            first = self.expr()
            if self.at("for"):
                clauses: list[ast.CompFor] = []
                while self.at("for"):
                    cstart = self.pos
                    self.advance()
                    var = self.ident("la variable de la comprensión").text
                    self.expect("in", "'in'")
                    iterable = self.or_expr()
                    conds: list[ast.Expr] = []
                    while self.eat("if"):
                        conds.append(self.or_expr())
                    clauses.append(ast.CompFor(var, iterable, conds, span=self.span_from(cstart)))
                self.expect("]", "']'")
                return ast.Comprehension(first, clauses, span=self.span_from(start))
            items = [first]
            while self.eat(","):
                if self.at("]"):
                    break
                items.append(self.expr())
            self.expect("]", "',' o ']'")
        return ast.ListLit(items, span=self.span_from(start))

    def let_block(self, *, allow_empty: bool) -> ast.Expr:
        start = self.pos
        self.expect("{")
        lets: list[tuple[str, ast.Expr]] = []
        with self.struct_literals(True):
            while True:
                self.skip_newlines()
                if not self.at("let"):
                    break
                self.advance()
                name = self.ident("el nombre de la variable").text
                self.expect("=", "'='")
                lets.append((name, self.value()))
            if not lets and not allow_empty:
                raise self.fail(
                    "un bloque { … } en una expresión empieza con 'let'",
                    help="para un conjunto usa set(a, b); para un struct, Nombre { campo: valor }",
                )
            result = self.expr()
            self.skip_newlines()
            self.expect("}", "'}'")
        if not lets:
            return result
        return ast.LetBlock(lets, result, span=self.span_from(start))

    def case_expr(self) -> ast.Expr:
        start = self.pos
        self.expect("case")
        self.expect("{", "'{'")
        arms: list[tuple[ast.Expr, ast.Expr]] = []
        default: ast.Expr | None = None
        with self.struct_literals(True):
            while True:
                self.skip_newlines()
                if self.eat("}"):
                    break
                if self.eat("else"):
                    self.expect("=>", "'=>'")
                    default = self.expr()
                    self.skip_newlines()
                    self.eat(",")
                    self.skip_newlines()
                    self.expect("}", "'}' (else es el último caso)")
                    break
                cond = self.expr()
                self.expect("=>", "'=>'")
                arms.append((cond, self.expr()))
                self.eat(",")
        if default is None:
            raise self.fail("'case' necesita un caso final 'else => …'", self.span_from(start))
        if not arms:
            raise self.fail(
                "'case' necesita al menos un caso además de else", self.span_from(start)
            )
        return ast.CaseExpr(arms, default, span=self.span_from(start))

    def match_expr(self) -> ast.Expr:
        start = self.pos
        self.expect("match")
        with self.struct_literals(False):
            subject = self.expr()
        self.expect("{", "'{'")
        arms: list[tuple[ast.Pattern, ast.Expr]] = []
        with self.struct_literals(True):
            while True:
                self.skip_newlines()
                if self.eat("}"):
                    break
                pattern = self.pattern()
                self.expect("=>", "'=>'")
                arms.append((pattern, self.expr()))
                self.eat(",")
        if not arms:
            raise self.fail("'match' necesita al menos un caso", self.span_from(start))
        return ast.MatchExpr(subject, arms, span=self.span_from(start))

    def pattern(self) -> ast.Pattern:
        start = self.pos
        if self.at_word("_"):
            self.advance()
            return ast.PWild(span=self.span_from(start))
        if self.eat("("):
            items = [self.pattern()]
            while self.eat(","):
                items.append(self.pattern())
            self.expect(")", "')'")
            if len(items) < 2:
                raise self.fail("un patrón de tupla necesita al menos dos componentes")
            return ast.PTuple(items, span=self.span_from(start))
        value = self.unary()
        return ast.PValue(value, span=self.span_from(start))

    # --- tests ----------------------------------------------------------------------------------

    def test_decl(self) -> ast.TestDecl:
        self.expect("test")
        name = self.expect("string", "el nombre del test entre comillas").value
        items, end = self.block(self.test_step)
        steps = [s for s in items if isinstance(s, ast.TestStep)]
        return ast.TestDecl(name=name, steps=steps, end_comments=self.claim(end))

    def test_step(self) -> ast.TestStep:
        start = self.pos
        doc = self.annotations_doc_only()
        step = self.test_step_body()
        step.doc = doc or step.doc
        return self.finish(step, start)

    def test_step_body(self) -> ast.TestStep:
        if self.eat("players"):
            tok = self.expect("int", "un número de jugadores")
            return ast.TestStep(kind="players", value=ast.IntLit(tok.value, span=tok.span))
        if self.eat("params"):
            entries = self.field_list()
            return ast.TestStep(kind="params", entries=entries)
        if self.eat_word("seed"):
            tok = self.expect("int", "una semilla (entero)")
            return ast.TestStep(kind="seed", value=ast.IntLit(tok.value, span=tok.span))
        if self.eat_word("play"):
            actions = [self.action_lit()]
            while self.eat(","):
                self.skip_newlines()
                actions.append(self.action_lit())
            return ast.TestStep(kind="play", actions=actions)
        if self.eat("chance"):
            if self.eat_word("where"):
                return ast.TestStep(kind="chance", where=self.expr())
            return ast.TestStep(kind="chance", value=self.expr())
        if self.eat_word("expect"):
            if self.at_word("legal", "illegal") and self.peek(1).kind in ("ident", "int"):
                kind = self.advance().text
                return ast.TestStep(kind=kind, actions=[self.action_lit()])
            return ast.TestStep(kind="expect", value=self.expr())
        if self.eat_word("set"):
            target = self.expr()
            self.expect("=", "'='")
            return ast.TestStep(kind="set", target=target, value=self.value())
        raise self.fail(
            "se esperaba un paso de test: play, chance, expect, set, seed, players o params"
        )

    def action_lit(self) -> ast.ActionLit:
        start = self.pos
        seat = None
        if self.at("int") and self.peek(1).kind == ":":
            tok = self.advance()
            seat = ast.IntLit(tok.value, span=tok.span)
            self.advance()
        name = self.ident("el nombre de una acción").text
        self.expect("(", "'(' (las acciones se escriben con paréntesis: check())")
        args: list[ast.Expr] = []
        with self.struct_literals(True):
            while not self.eat(")"):
                args.append(self.expr())
                if not self.eat(","):
                    self.expect(")", "',' o ')'")
                    break
        return ast.ActionLit(name, args, seat, span=self.span_from(start))


def _found(tok: Token) -> str:
    if tok.kind == "eof":
        return "fin del archivo"
    if tok.kind == "newline":
        return "fin de línea"
    return f"se encontró '{tok.text}'"
