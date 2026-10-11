# SPDX-License-Identifier: Apache-2.0
"""Impresor del AST de Nomos: el formateador canónico (`gamehub fmt`) y la salida del
descompilador.

Reglas de formato: sangría de 2 espacios, ancho de 100 columnas, una declaración o sentencia por
línea, como mucho una línea en blanco entre elementos (se conservan las del original), espacios
alrededor de los operadores binarios. Un nodo con un único miembro, una acción con una sola
sentencia simple y una transición con una sola sentencia simple se escriben en una línea si
caben. Si una expresión no cabe: tras `=` o `clave:` el valor pasa a la línea siguiente (o, si
empieza por un corchete y tampoco cabe allí, se abre en la misma línea y se parte por dentro);
una cadena aritmética reparte sus operandos rellenando líneas; una de `and`/`or`, uno por línea.
Los comentarios se conservan, con las líneas en blanco que los separaban; los que estaban en
medio de una expresión pasan a la línea anterior al elemento que los contenía.
"""

from __future__ import annotations

from fractions import Fraction

from gamehub.lang import ast
from gamehub.lang.diagnostics import CompileError, Diagnostics
from gamehub.lang.layout import (
    HARDLINE,
    LINE,
    NIL,
    SOFTLINE,
    Doc,
    Hang,
    IfBreak,
    concat,
    fill,
    group,
    join,
    nest,
    render,
    text,
)
from gamehub.lang.lexer import KEYWORDS, Comment
from gamehub.lang.parser import parse
from gamehub.lang.source import Source

INDENT = 2
WIDTH = 100

#: Precedencias (mayor = liga más fuerte).
P_IF, P_OR, P_AND, P_NOT, P_CMP, P_RANGE, P_ADD, P_MUL, P_UNARY, P_POSTFIX, P_ATOM = range(1, 12)
BINARY_PREC = {
    "or": P_OR,
    "and": P_AND,
    "==": P_CMP,
    "!=": P_CMP,
    "<": P_CMP,
    "<=": P_CMP,
    ">": P_CMP,
    ">=": P_CMP,
    "in": P_CMP,
    "not in": P_CMP,
    "+": P_ADD,
    "-": P_ADD,
    "*": P_MUL,
    "/": P_MUL,
    "div": P_MUL,
    "%": P_MUL,
}
SIMPLE_STMTS = (
    ast.LetStmt,
    ast.Assign,
    ast.MoveStmt,
    ast.FlipStmt,
    ast.ShuffleStmt,
    ast.DealStmt,
    ast.RevealStmt,
    ast.EmitStmt,
    ast.RewardStmt,
    ast.FailStmt,
)


def format_file(file: ast.File, width: int = WIDTH) -> str:
    return render(Printer().file(file), width).rstrip("\n") + "\n"


def format_source(source: Source) -> str:
    """Formatea un texto Nomos. Lanza `CompileError` si tiene errores de sintaxis."""
    diagnostics = Diagnostics()
    tree = parse(source, diagnostics)
    if diagnostics.has_errors:
        raise CompileError(diagnostics)
    return format_file(tree)


def quote(value: str) -> str:
    out = ['"']
    for ch in value:
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif ch == "\r":
            out.append("\\r")
        elif ord(ch) < 32:
            out.append(f"\\u{{{ord(ch):x}}}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def is_identifier(name: str) -> bool:
    return (
        bool(name)
        and (name[0].isalpha() or name[0] == "_")
        and all(c.isalnum() or c == "_" for c in name)
        and name not in KEYWORDS
    )


def plain(item: ast.Item) -> bool:
    """Sin documentación ni comentarios (condición para escribirlo en una línea)."""
    t = item.trivia
    return item.doc is None and not t.leading and t.trailing is None and not t.inner


class Printer:
    # --- elementos y bloques --------------------------------------------------------------------

    def file(self, f: ast.File) -> Doc:
        parts: list[Doc | str] = []
        for i, item in enumerate(f.items):
            if i:
                parts.append(HARDLINE)
                if item.trivia.blank_before or self._separate(f.items[i - 1], item):
                    parts.append(HARDLINE)
            parts.append(self.item(item))
        for i, c in enumerate(f.end_comments):
            if f.items or i:
                parts.append(HARDLINE)
                if c.blank_before:
                    parts.append(HARDLINE)
            parts.append(text(c.text))
        return concat(*parts)

    @staticmethod
    def _separate(prev: ast.Item, item: ast.Item) -> bool:
        """Entre declaraciones de primer nivel de distinto tipo, o entre juegos, una línea en
        blanco aunque el original no la tuviera."""
        if isinstance(prev, ast.Import) and isinstance(item, ast.Import):
            return False
        return isinstance(item, ast.GameDecl | ast.GameAlias) or type(prev) is not type(item)

    def item(self, item: ast.Item) -> Doc:
        parts: list[Doc | str] = []
        for c in item.trivia.leading:
            parts.extend([text(c.text), HARDLINE])
            if c.blank_after:
                parts.append(HARDLINE)
        for c in item.trivia.inner:
            parts.extend([text(c.text), HARDLINE])
        if item.doc is not None:
            parts.extend([self.doc_comment(item.doc), HARDLINE])
        parts.append(self.item_body(item))
        if item.trivia.trailing is not None:
            parts.append(text(" " + item.trivia.trailing.text))
        return concat(*parts)

    def doc_comment(self, doc: ast.Text) -> Doc:
        if isinstance(doc.value, str):
            return join(
                HARDLINE, [text(("/// " + line).rstrip()) for line in doc.value.split("\n")]
            )
        return concat("@doc(", self.text(doc), ")")

    def block(
        self,
        header: Doc | str,
        items: list[ast.Item],
        end_comments: list[Comment] | None = None,
    ) -> Doc:
        end_comments = end_comments or []
        if not items and not end_comments:
            return concat(header, " {}")
        body: list[Doc | str] = []
        for i, item in enumerate(items):
            if i:
                body.append(HARDLINE)
                if item.trivia.blank_before:
                    body.append(HARDLINE)
            body.append(self.item(item))
        for i, c in enumerate(end_comments):
            if items or i:
                body.append(HARDLINE)
                if c.blank_before:
                    body.append(HARDLINE)
            body.append(text(c.text))
        return concat(header, " {", nest(INDENT, HARDLINE, *body), HARDLINE, "}")

    def compact_block(
        self, header: Doc | str, items: list[ast.Item], end_comments: list[Comment] | None = None
    ) -> Doc:
        """Bloque que se escribe en una línea si tiene un solo elemento simple y cabe."""
        if len(items) == 1 and plain(items[0]) and not end_comments:
            inner = self.item_body(items[0])
            return group(header, " {", nest(INDENT, LINE, inner), LINE, "}")
        return self.block(header, items, end_comments)

    def item_body(self, item: ast.Item) -> Doc:
        method = getattr(self, "i_" + type(item).__name__, None)
        if method is None:
            raise TypeError(f"no sé imprimir {type(item).__name__}")
        return method(item)

    # --- archivo y juego ------------------------------------------------------------------------

    def i_Import(self, item: ast.Import) -> Doc:
        path = ".".join(item.path)
        if item.names is None:
            return text(f"import {path}.*")
        return text(f"import {path}.{{{', '.join(item.names)}}}")

    def i_GameDecl(self, item: ast.GameDecl) -> Doc:
        header = f"game {item.name}" + (f" extends {item.extends}" if item.extends else "")
        return self.block(header, item.items, item.end_comments)

    def i_GameAlias(self, item: ast.GameAlias) -> Doc:
        args = [text(item.base)] + [concat(k, ": ", self.expr(v)) for k, v in item.args]
        return group(
            f"game {item.name} = {item.combinator}(",
            nest(INDENT, SOFTLINE, join(concat(",", LINE), args)),
            SOFTLINE,
            ")",
        )

    def i_MetaBlock(self, item: ast.MetaBlock) -> Doc:
        return self.block("meta", list(item.entries), item.end_comments)

    def i_MetaEntry(self, item: ast.MetaEntry) -> Doc:
        value = item.value
        if isinstance(value, ast.Text):
            shown: Doc = self.text(value)
        elif isinstance(value, list):
            shown = group(
                "[",
                nest(INDENT, SOFTLINE, join(concat(",", LINE), [text(quote(v)) for v in value])),
                SOFTLINE,
                "]",
            )
        else:
            shown = text(quote(str(value)))
        return concat(item.key, ": ", shown)

    def i_UiBlock(self, item: ast.UiBlock) -> Doc:
        return self.block("ui", list(item.entries), item.end_comments)

    def i_UiEntry(self, item: ast.UiEntry) -> Doc:
        match item.target:
            case "action":
                target = "action " + ".".join(item.path)
            case "node":
                target = "node " + item.path[0]
            case "seats":
                target = "seats"
            case _:
                target = item.path[0]
        return concat(target, ": ", join(", ", [self.ui_hint(h) for h in item.hints]))

    def ui_hint(self, hint: ast.UiHint) -> Doc:
        if hint.args is None:
            return text(hint.name)
        args = [
            concat(f"{a.key}: ", self.ui_value(a.value))
            if a.key is not None
            else self.ui_value(a.value)
            for a in hint.args
        ]
        return group(
            f"{hint.name}(",
            nest(INDENT, SOFTLINE, join(concat(",", LINE), args)),
            SOFTLINE,
            ")",
        )

    def ui_value(self, value: object) -> Doc:
        match value:
            case ast.Text():
                return self.text(value)
            case ast.UiName(name=name):
                return text(name)
            case bool():
                return text("true" if value else "false")
            case int():
                return text(str(value))
            case Fraction():
                return text(decimal_text(value) or str(value))
            case list():
                items = [self.ui_value(v) for v in value]
                return group(
                    "[", nest(INDENT, SOFTLINE, join(concat(",", LINE), items)), SOFTLINE, "]"
                )
        raise TypeError(value)

    def i_PlayersDecl(self, item: ast.PlayersDecl) -> Doc:
        if item.min == item.max:
            return text(f"players {item.min}")
        return text(f"players {item.min}..{item.max}")

    def i_ParamsBlock(self, item: ast.ParamsBlock) -> Doc:
        return self.block("params", item.items, item.end_comments)

    def i_ParamDecl(self, item: ast.ParamDecl) -> Doc:
        return self.rhs(concat(item.name, ": ", self.type(item.type), " ="), item.default)

    def i_AssertDecl(self, item: ast.AssertDecl) -> Doc:
        doc = concat("assert ", self.expr(item.expr))
        if item.message is not None:
            doc = concat(doc, ",", group(nest(INDENT, LINE, self.text(item.message))))
        return group(doc)

    def i_EnumDecl(self, item: ast.EnumDecl) -> Doc:
        return group(
            f"enum {item.name} {{",
            nest(INDENT, LINE, join(concat(",", LINE), [text(v) for v in item.values])),
            LINE,
            "}",
        )

    def i_StructDecl(self, item: ast.StructDecl) -> Doc:
        if all(plain(f) for f in item.fields):
            fields = [self.i_StructField(f) for f in item.fields]
            return group(
                f"struct {item.name} {{",
                nest(INDENT, LINE, join(concat(",", LINE), fields)),
                LINE,
                "}",
            )
        return self.block(f"struct {item.name}", list(item.fields))

    def i_StructField(self, item: ast.StructField) -> Doc:
        return concat(item.name, ": ", self.type(item.type))

    def i_StateBlock(self, item: ast.StateBlock) -> Doc:
        return self.block("state", list(item.vars), item.end_comments)

    def i_StateVar(self, item: ast.StateVar) -> Doc:
        annotations = self.annotations(item.visibility, item.size_visibility)
        decl = concat(item.name, ": ", self.type(item.type))
        if item.init is not None:
            decl = self.rhs(concat(decl, " ="), item.init)
        if annotations is not NIL:
            return concat(annotations, HARDLINE, decl)
        return decl

    def annotations(
        self, visibility: ast.Visibility | None, size_visibility: ast.Visibility | None
    ) -> Doc:
        parts: list[Doc] = []
        if visibility is not None:
            parts.append(concat("@visible(", self.visibility(visibility), ")"))
        if size_visibility is not None:
            parts.append(concat("@size_visible(", self.visibility(size_visibility), ")"))
        return join(" ", parts) if parts else NIL

    def visibility(self, vis: ast.Visibility) -> Doc:
        if vis.kind == "when":
            assert vis.expr is not None
            return self.expr(vis.expr)
        return text(vis.kind)

    def i_FnDecl(self, item: ast.FnDecl) -> Doc:
        params = [concat(p.name, ": ", self.type(p.type)) for p in item.params]
        header = group(
            f"fn {item.name}(",
            nest(INDENT, SOFTLINE, join(concat(",", LINE), params)),
            SOFTLINE,
            ") -> ",
            self.type(item.returns),
        )
        body = item.body
        if isinstance(body, ast.LetBlock):
            lines = [concat("let ", n, " = ", self.expr(v)) for n, v in body.lets]
            lines.append(self.expr(body.result))
            return concat(
                header, " {", nest(INDENT, HARDLINE, join(HARDLINE, lines)), HARDLINE, "}"
            )
        return self.rhs(concat(header, " ="), body)

    def i_InvariantDecl(self, item: ast.InvariantDecl) -> Doc:
        return group("invariant ", self.expr(item.expr))

    def i_OverrideDecl(self, item: ast.OverrideDecl) -> Doc:
        return concat("override ", self.item_body(item.item))

    def i_RemoveDecl(self, item: ast.RemoveDecl) -> Doc:
        return text(f"remove {item.kind} {'.'.join(item.path)}")

    def i_ExtendNode(self, item: ast.ExtendNode) -> Doc:
        return self.block(f"extend node {item.name}", item.members, item.end_comments)

    # --- flow -----------------------------------------------------------------------------------

    def i_FlowBlock(self, item: ast.FlowBlock) -> Doc:
        return self.block("flow", item.items, item.end_comments)

    def i_StartDecl(self, item: ast.StartDecl) -> Doc:
        if item.setup is None:
            return text(f"start -> {item.target}")
        return concat(self.block("start", list(item.setup)), f" -> {item.target}")

    def i_NodeDecl(self, item: ast.NodeDecl) -> Doc:
        header = f"{item.kind} {item.name}"
        members = item.members
        if len(members) == 1 and isinstance(members[0], ast.Member):
            return self.compact_block(header, members, item.end_comments)
        return self.block(header, members, item.end_comments)

    def i_Member(self, item: ast.Member) -> Doc:
        return self.rhs(f"{item.key}:", item.value)

    def i_LetMember(self, item: ast.LetMember) -> Doc:
        return self.rhs(f"let {item.name} =", item.value)

    def i_BlockMember(self, item: ast.BlockMember) -> Doc:
        return self.block(item.key, list(item.body), item.end_comments)

    def i_ActionDecl(self, item: ast.ActionDecl) -> Doc:
        params = [self.action_param(p) for p in item.params]
        header: Doc = group(
            f"action {item.name}(",
            nest(INDENT, SOFTLINE, join(concat(",", LINE), params)),
            SOFTLINE,
            ")",
        )
        if item.requires is not None:
            requires = nest(2 * INDENT, LINE, self.bare_cond(item.requires))
            header = group(header, " requires", requires)
        if item.visibility is not None:
            header = concat("@visible(", self.visibility(item.visibility), ")", HARDLINE, header)
        if item.effects is None:
            return header
        body: list[ast.Item] = [*item.effects, *item.transitions]
        if (
            not item.transitions
            and len(item.effects) == 1
            and isinstance(item.effects[0], SIMPLE_STMTS)
        ):
            return self.compact_block(header, body, item.end_comments)
        return self.block(header, body, item.end_comments)

    def action_param(self, p: ast.ActionParam) -> Doc:
        parts: list[Doc | str] = []
        annotations = self.annotations(p.visibility, p.size_visibility)
        if annotations is not NIL:
            parts.extend([annotations, " "])
        parts.append(p.name)
        if p.type is not None:
            parts.extend([": ", self.type(p.type)])
        if p.domain is not None:
            parts.extend([" in ", self.expr(p.domain)])
        return concat(*parts)

    def i_Transition(self, item: ast.Transition) -> Doc:
        header: Doc = text(f"-> {item.target}")
        if item.when is not None:
            header = group(header, " when", nest(2 * INDENT, LINE, self.bare_cond(item.when)))
        if item.effects is None:
            return header
        effects: list[ast.Item] = list(item.effects)
        if len(effects) == 1 and isinstance(effects[0], SIMPLE_STMTS):
            return self.compact_block(header, effects)
        return self.block(header, effects)

    # --- sentencias -----------------------------------------------------------------------------

    def i_LetStmt(self, item: ast.LetStmt) -> Doc:
        return self.rhs(f"let {item.name} =", item.value)

    def i_Assign(self, item: ast.Assign) -> Doc:
        return self.rhs(concat(self.expr(item.target, P_POSTFIX), f" {item.op}"), item.value)

    def i_IfStmt(self, item: ast.IfStmt) -> Doc:
        doc = self.block(concat("if ", self.cond(item.cond)), list(item.then))
        other = item.other
        if other is None:
            return doc
        if len(other) == 1 and isinstance(other[0], ast.IfStmt) and plain(other[0]):
            return concat(doc, " else ", self.i_IfStmt(other[0]))
        return concat(doc, " ", self.block("else", list(other)))

    def i_ForStmt(self, item: ast.ForStmt) -> Doc:
        header = concat(f"for {item.var} in ", self.cond(item.iter))
        return self.block(header, list(item.body))

    def selector(self, sel: ast.Selector) -> Doc:
        if sel.kind == "all":
            return text("all")
        assert sel.expr is not None
        if sel.kind == "value":
            value = sel.expr
            if isinstance(value, ast.Name) and value.name in ("all", "top", "bottom", "at"):
                return concat("(", value.name, ")")
            return self.expr(value)
        return concat(sel.kind, " ", self.expr(sel.expr, P_RANGE))

    def i_MoveStmt(self, item: ast.MoveStmt) -> Doc:
        parts: list[Doc | str] = [
            "move ",
            self.selector(item.selector),
            " from ",
            self.expr(item.source),
            " to ",
            self.expr(item.dest),
        ]
        if item.position is not None:
            parts.append(f" at {item.position}")
        return group(*parts)

    def i_FlipStmt(self, item: ast.FlipStmt) -> Doc:
        face = item.face
        if isinstance(face, ast.BoolLit):
            shown: Doc = text("face_up" if face.value else "face_down")
        else:
            inner = face.inner if isinstance(face, ast.Paren) else face
            shown = concat("face(", self.expr(inner), ")")
        return concat(
            "flip ", self.selector(item.selector), " of ", self.expr(item.zone), " ", shown
        )

    def i_ShuffleStmt(self, item: ast.ShuffleStmt) -> Doc:
        return concat("shuffle ", self.expr(item.zone))

    def i_DealStmt(self, item: ast.DealStmt) -> Doc:
        count = text("all") if item.count is None else self.expr(item.count)
        return concat(
            "deal ", count, " from ", self.expr(item.source), " to each ", self.expr(item.dest)
        )

    def i_RevealStmt(self, item: ast.RevealStmt) -> Doc:
        to = text("all") if item.to is None else self.expr(item.to)
        doc = concat("reveal ", self.expr(item.value), " to ", to)
        if item.label is not None:
            doc = concat(doc, " as ", self.text(item.label))
        return group(doc)

    def i_EmitStmt(self, item: ast.EmitStmt) -> Doc:
        fields = [concat(k, ": ", self.expr(v)) for k, v in item.fields]
        doc = group(
            f"emit {item.name} {{",
            nest(INDENT, LINE, join(concat(",", LINE), fields)),
            LINE,
            "}",
        )
        if item.visibility is not None:
            return concat("@visible(", self.visibility(item.visibility), ") ", doc)
        return doc

    def i_RewardStmt(self, item: ast.RewardStmt) -> Doc:
        return concat("reward ", self.expr(item.amount), " to ", self.expr(item.seat))

    def i_FailStmt(self, item: ast.FailStmt) -> Doc:
        return concat("fail ", self.text(item.message))

    # --- tests ----------------------------------------------------------------------------------

    def i_TestDecl(self, item: ast.TestDecl) -> Doc:
        return self.block(f"test {quote(item.name)}", list(item.steps), item.end_comments)

    def i_TestStep(self, item: ast.TestStep) -> Doc:
        match item.kind:
            case "players" | "seed":
                assert item.value is not None
                return concat(item.kind, " ", self.expr(item.value))
            case "params":
                entries = [concat(k, ": ", self.expr(v)) for k, v in item.entries]
                return group(
                    "params {", nest(INDENT, LINE, join(concat(",", LINE), entries)), LINE, "}"
                )
            case "play":
                actions = [self.action_lit(a) for a in item.actions]
                return group("play ", nest(INDENT * 2, join(concat(",", LINE), actions)))
            case "chance":
                if item.where is not None:
                    return group("chance where ", self.expr(item.where))
                assert item.value is not None
                return concat("chance ", self.expr(item.value))
            case "expect":
                assert item.value is not None
                return group("expect ", self.expr(item.value))
            case "legal" | "illegal":
                return concat(f"expect {item.kind} ", self.action_lit(item.actions[0]))
            case "set":
                assert item.target is not None and item.value is not None
                return group(
                    "set ", self.expr(item.target), " =", nest(INDENT, LINE, self.expr(item.value))
                )
        raise TypeError(item.kind)

    def action_lit(self, a: ast.ActionLit) -> Doc:
        seat: Doc | str = concat(self.expr(a.seat), ": ") if a.seat is not None else ""
        args = [self.expr(x) for x in a.args]
        return group(
            seat, a.name, "(", nest(INDENT, SOFTLINE, join(concat(",", LINE), args)), SOFTLINE, ")"
        )

    # --- textos y tipos -------------------------------------------------------------------------

    def text(self, t: ast.Text) -> Doc:
        if isinstance(t.value, str):
            return text(quote(t.value))
        entries = [
            concat(k if is_identifier(k) else quote(k), ": ", quote(v)) for k, v in t.value.items()
        ]
        if len(entries) == 1:
            return concat("{ ", entries[0], " }")
        return group("{", nest(INDENT, LINE, join(concat(",", LINE), entries)), LINE, "}")

    def type(self, t: ast.TypeExpr) -> str:
        if isinstance(t, ast.TName):
            return t.name
        if isinstance(t, ast.TOption):
            return self.type(t.inner) + "?"
        if isinstance(t, ast.TGeneric):
            return f"{t.name}<{', '.join(self.type(a) for a in t.args)}>"
        if isinstance(t, ast.TTuple):
            return f"({', '.join(self.type(a) for a in t.items)})"
        if isinstance(t, ast.TPerPlayer):
            return "per_player " + self.type(t.inner)
        if isinstance(t, ast.TGrid):
            return f"Grid[{t.width}, {t.height}] of {self.type(t.inner)}"
        raise TypeError(t)

    # --- expresiones ----------------------------------------------------------------------------

    def rhs(self, prefix: Doc | str, value: ast.Expr) -> Doc:
        """`prefijo valor`: el valor pasa a la línea siguiente si no cabe; uno que empieza por un
        corchete se queda en la misma línea si tampoco cabe en la siguiente, y `case` y `match`
        siempre empiezan en la misma línea."""
        if isinstance(value, ast.CaseExpr | ast.MatchExpr):
            return concat(prefix, " ", self.expr(value))
        prefix_doc = text(prefix) if isinstance(prefix, str) else prefix
        return Hang(prefix_doc, self.expr(value), INDENT, hug=_bracketed(value))

    def cond(self, e: ast.Expr) -> Doc:
        """Expresión seguida de un bloque `{ … }` en la misma línea (`if`, `for`, `match`): si se
        parte, sus líneas de continuación llevan sangría doble para no confundirse con el
        cuerpo."""
        return nest(INDENT, self.bare_cond(e))

    def bare_cond(self, e: ast.Expr) -> Doc:
        """Expresión seguida de `{`: un literal de struct suelto necesitaría paréntesis."""
        if _struct_outside_brackets(e):
            return concat("(", self.expr(e), ")")
        return self.expr(e)

    def expr(self, e: ast.Expr, min_prec: int = 0) -> Doc:
        doc, prec = self._expr(e)
        if prec < min_prec:
            return group("(", nest(INDENT, SOFTLINE, doc), SOFTLINE, ")")
        return doc

    def _expr(self, e: ast.Expr) -> tuple[Doc, int]:
        match e:
            case ast.Name(name=name):
                return text(name), P_ATOM
            case ast.IntLit(value=value):
                if value < 0:
                    return text(f"-{-value}"), P_UNARY
                return text(str(value)), P_ATOM
            case ast.DecimalLit(text=literal):
                return text(literal), P_ATOM
            case ast.StrLit(value=value):
                return text(quote(value)), P_ATOM
            case ast.BoolLit(value=value):
                return text("true" if value else "false"), P_ATOM
            case ast.NoneLit():
                return text("none"), P_ATOM
            case ast.Paren(inner=inner):
                return group("(", nest(INDENT, SOFTLINE, self.expr(inner)), SOFTLINE, ")"), P_ATOM
            case ast.Unary(op="-", operand=operand):
                return concat("-", self.expr(operand, P_UNARY)), P_UNARY
            case ast.Unary(op=_, operand=operand):
                return concat("not ", self.expr(operand, P_NOT)), P_NOT
            case ast.Binary(op=op, left=left, right=right) if BINARY_PREC[op] == P_CMP:
                doc = group(
                    self.expr(left, P_CMP + 1),
                    f" {op}",
                    nest(INDENT, LINE, self.expr(right, P_CMP + 1)),
                )
                return doc, P_CMP
            case ast.Binary(op=op):
                return self.chain(e, BINARY_PREC[op]), BINARY_PREC[op]
            case ast.RangeExpr(lo=lo, hi=hi, inclusive=inclusive):
                op = ".." if inclusive else "..<"
                return concat(self.expr(lo, P_ADD), op, self.expr(hi, P_ADD)), P_RANGE
            case ast.IfExpr(then=then, cond=cond, other=other):
                doc = concat(
                    self.expr(then, P_OR),
                    " if ",
                    self.expr(cond, P_OR),
                    " else ",
                    self.expr(other, P_IF),
                )
                return doc, P_IF
            case ast.Call(func=func, args=args):
                docs = [self.expr(a) for a in args]
                return self.call_doc(func, docs), P_POSTFIX
            case ast.Aggregate(func=func, var=var, coll=coll, body=body):
                inner = concat(var, " in ", self.expr(coll, P_RANGE), " :", LINE, self.expr(body))
                return group(func, "(", nest(INDENT, SOFTLINE, inner), SOFTLINE, ")"), P_POSTFIX
            case ast.Index(target=target, index=index):
                return concat(self.expr(target, P_POSTFIX), "[", self.expr(index), "]"), P_POSTFIX
            case ast.Slice(target=target, lo=lo, hi=hi):
                lo_doc = self.expr(lo) if lo is not None else NIL
                hi_doc = self.expr(hi) if hi is not None else NIL
                return concat(
                    self.expr(target, P_POSTFIX), "[", lo_doc, ":", hi_doc, "]"
                ), P_POSTFIX
            case ast.Field(target=target, name=name):
                return concat(self.expr(target, P_POSTFIX), ".", name), P_POSTFIX
            case ast.ListLit(items=items):
                return self.seq("[", [self.expr(x) for x in items], "]"), P_ATOM
            case ast.TupleLit(items=items):
                return self.seq("(", [self.expr(x) for x in items], ")"), P_ATOM
            case ast.Comprehension(element=element, clauses=clauses):
                parts: list[Doc | str] = [self.expr(element)]
                for clause in clauses:
                    parts.extend([LINE, f"for {clause.var} in ", self.expr(clause.iter, P_OR)])
                    for c in clause.conds:
                        parts.extend([LINE, "if ", self.expr(c, P_OR)])
                return group("[", nest(INDENT, SOFTLINE, *parts), SOFTLINE, "]"), P_ATOM
            case ast.StructLit(type_name=name, fields=fields):
                docs = [concat(k, ": ", self.expr(v)) for k, v in fields]
                return (
                    group(
                        f"{name} {{", nest(INDENT, LINE, join(concat(",", LINE), docs)), LINE, "}"
                    ),
                    P_ATOM,
                )
            case ast.LetBlock(lets=lets, result=result):
                lines = [concat("let ", n, " = ", self.expr(v)) for n, v in lets]
                lines.append(self.expr(result))
                sep = concat(IfBreak(NIL, text(";")), LINE)
                return group("{", nest(INDENT, LINE, join(sep, lines)), LINE, "}"), P_ATOM
            case ast.CaseExpr(arms=arms, default=default):
                lines = [concat(self.expr(c), " => ", self.expr(v)) for c, v in arms]
                lines.append(concat("else => ", self.expr(default)))
                return concat(
                    "case {", nest(INDENT, HARDLINE, join(HARDLINE, lines)), HARDLINE, "}"
                ), P_ATOM
            case ast.MatchExpr(subject=subject, arms=arms):
                lines = [concat(self.pattern(p), " => ", self.expr(v)) for p, v in arms]
                return (
                    concat(
                        "match ",
                        self.cond(subject),
                        " {",
                        nest(INDENT, HARDLINE, join(HARDLINE, lines)),
                        HARDLINE,
                        "}",
                    ),
                    P_ATOM,
                )
        raise TypeError(f"no sé imprimir la expresión {type(e).__name__}")

    def chain(self, e: ast.Binary, prec: int) -> Doc:
        """Cadena de operadores de la misma precedencia, que asocian por la izquierda
        (`a + b - c`, `p and q and r`). Si no cabe, con `and`/`or` va un operando por línea; con
        operadores aritméticos, tantos por línea como quepan. Las líneas de continuación llevan
        sangría y el operador queda al final de la línea anterior."""
        rights: list[tuple[str, ast.Expr]] = []
        node: ast.Expr = e
        while isinstance(node, ast.Binary) and BINARY_PREC[node.op] == prec:
            rights.append((node.op, node.right))
            node = node.left
        rights.reverse()
        first = self.expr(node, prec)
        if prec in (P_AND, P_OR):
            rest = [concat(f" {op}", LINE, self.expr(r, prec + 1)) for op, r in rights]
            return group(first, nest(INDENT, *rest))
        # El primer operando no lleva la sangría de continuación (si se parte por dentro, sus
        # líneas se alinean con él).
        parts: list[Doc] = [nest(-INDENT, first)]
        for op, r in rights:
            parts.extend([concat(f" {op}", LINE), self.expr(r, prec + 1)])
        return nest(INDENT, fill(parts))

    def call_doc(self, func: str, args: list[Doc]) -> Doc:
        if not args:
            return text(f"{func}()")
        return group(
            func, "(", nest(INDENT, SOFTLINE, join(concat(",", LINE), args)), SOFTLINE, ")"
        )

    def seq(self, open_: str, items: list[Doc], close: str) -> Doc:
        if not items:
            return text(open_ + close)
        return group(open_, nest(INDENT, SOFTLINE, join(concat(",", LINE), items)), SOFTLINE, close)

    def pattern(self, p: ast.Pattern) -> Doc:
        if isinstance(p, ast.PWild):
            return text("_")
        if isinstance(p, ast.PTuple):
            return concat("(", join(", ", [self.pattern(x) for x in p.items]), ")")
        assert isinstance(p, ast.PValue)
        return self.expr(p.value, P_UNARY)


def _bracketed(e: ast.Expr) -> bool:
    """Expresión que empieza abriendo un corchete y se puede partir por dentro."""
    match e:
        case ast.Call(args=args):
            return bool(args)
        case ast.ListLit(items=items) | ast.TupleLit(items=items):
            return bool(items)
        case ast.Comprehension() | ast.StructLit() | ast.Aggregate() | ast.Paren() | ast.LetBlock():
            return True
    return False


def _struct_outside_brackets(e: ast.Expr) -> bool:
    match e:
        case ast.StructLit():
            return True
        case ast.Binary(left=left, right=right):
            return _struct_outside_brackets(left) or _struct_outside_brackets(right)
        case ast.Unary(operand=operand):
            return _struct_outside_brackets(operand)
        case ast.IfExpr(then=then, cond=cond, other=other):
            return any(_struct_outside_brackets(x) for x in (then, cond, other))
        case ast.RangeExpr(lo=lo, hi=hi):
            return _struct_outside_brackets(lo) or _struct_outside_brackets(hi)
        case ast.Field(target=target) | ast.Index(target=target) | ast.Slice(target=target):
            return _struct_outside_brackets(target)
    return False


def decimal_text(value: Fraction) -> str | None:
    """Escritura decimal exacta de un racional (None si no es un decimal finito)."""
    den = value.denominator
    twos = fives = 0
    while den % 2 == 0:
        den //= 2
        twos += 1
    while den % 5 == 0:
        den //= 5
        fives += 1
    if den != 1:
        return None
    digits = max(twos, fives, 1)
    scaled = abs(value) * 10**digits
    assert scaled.denominator == 1
    raw = str(scaled.numerator).rjust(digits + 1, "0")
    whole, frac = raw[:-digits], raw[-digits:]
    sign = "-" if value < 0 else ""
    return f"{sign}{whole}.{frac}"
