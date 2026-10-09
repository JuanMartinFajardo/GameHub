# SPDX-License-Identifier: Apache-2.0
"""Descompilador: GameIR → AST de Nomos (y, con el impresor, → texto).

Garantía (comprobada en los tests): para una IR bien tipada, compilar el texto descompilado da
la misma IR, y descompilar de nuevo da el mismo texto (`texto → IR → texto` es estable).
Para conseguirlo, el descompilador escribe la forma que el compilador traduce exactamente a cada
operador: paréntesis donde la IR no aplana, tipos explícitos en los parámetros de acción, etc.
"""

from __future__ import annotations

import re
from fractions import Fraction
from typing import Any

from gamehub.lang import ast
from gamehub.lang.checker import kebab
from gamehub.lang.printer import decimal_text, format_file

BINARY = {
    "sub": "-",
    "div": "/",
    "idiv": "div",
    "mod": "%",
    "eq": "==",
    "ne": "!=",
    "lt": "<",
    "le": "<=",
    "gt": ">",
    "ge": ">=",
}
VARIADIC = {"add": "+", "mul": "*", "and": "and", "or": "or"}
CALLS = {
    "next_seat": "next",
    "prev_seat": "prev",
    "other_seat": "other",
}
AGGREGATE_NAMES = {"max_of": "max", "min_of": "min"}
CONTEXT = {"actor": "actor", "viewer": "viewer", "owner": "owner", "item_face_up": "face_up"}
RANDOM = {"roll": "roll", "random_choice": "random", "sample": "sample"}


def camel(game_id: str) -> str:
    """`kuhn-poker` → `KuhnPoker`."""
    return "".join(
        part[:1].upper() + part[1:] for part in re.split(r"[^A-Za-z0-9]+", game_id) if part
    )


def decompile(ir: dict[str, Any], name: str | None = None) -> ast.File:
    return ast.File(items=[_Decompiler(ir).game(name)])


def decompile_text(ir: dict[str, Any], name: str | None = None) -> str:
    return format_file(decompile(ir, name))


class _Decompiler:
    def __init__(self, ir: dict[str, Any]) -> None:
        self.ir = ir
        types = ir.get("types", [])
        self.enums = {t["name"]: t["values"] for t in types if t["kind"] == "enum"}
        self.structs = {
            t["name"]: [(f["name"], f["type"]) for f in t["fields"]]
            for t in types
            if t["kind"] == "struct"
        }
        owners: dict[str, list[str]] = {}
        for enum, values in self.enums.items():
            for v in values:
                owners.setdefault(v, []).append(enum)
        globals_ = {v["name"] for v in ir.get("state", [])}
        globals_ |= {p["name"] for p in ir.get("params", [])}
        globals_ |= {f["name"] for f in ir.get("functions", [])}
        self.bare = {v for v, o in owners.items() if len(o) == 1 and v not in globals_}

    # --- declaraciones --------------------------------------------------------------------------

    def game(self, name: str | None) -> ast.GameDecl:
        ir = self.ir
        game_id = ir["game"]["id"]
        name = name or camel(game_id) or "Game"
        items: list[ast.Item] = [self.meta(name)]
        players = ir["players"]
        items.append(ast.PlayersDecl(min=players["min"], max=players["max"]))
        params = self.params()
        if params is not None:
            items.append(self.blank(params))
        first_type = True
        for t in ir.get("types", []):
            decl = self.type_decl(t)
            items.append(self.blank(decl) if first_type else decl)
            first_type = False
        items.append(self.blank(self.state()))
        first_fn = True
        for f in ir.get("functions", []):
            decl = self.function(f)
            items.append(self.blank(decl) if first_fn else decl)
            first_fn = False
        items.append(self.blank(self.flow()))
        return ast.GameDecl(name=name, items=items)

    @staticmethod
    def blank(item: ast.Item) -> ast.Item:
        item.trivia.blank_before = True
        return item

    def meta(self, name: str) -> ast.MetaBlock:
        ir = self.ir
        entries: list[ast.MetaEntry] = []
        if kebab(name) != ir["game"]["id"]:
            entries.append(ast.MetaEntry(key="id", value=ast.Text(ir["game"]["id"])))
        entries.append(ast.MetaEntry(key="version", value=ast.Text(ir["game"]["version"])))
        meta = ir.get("meta", {})
        for key in ("title", "description", "authors", "license", "tags"):
            if key not in meta:
                continue
            value = meta[key]
            entries.append(
                ast.MetaEntry(
                    key=key, value=list(value) if isinstance(value, list) else ast.Text(value)
                )
            )
        return ast.MetaBlock(entries=entries)

    def params(self) -> ast.ParamsBlock | None:
        params = self.ir.get("params", [])
        constraints = self.ir.get("constraints", [])
        if not params and not constraints:
            return None
        items: list[ast.Item] = []
        for p in params:
            items.append(
                ast.ParamDecl(
                    name=p["name"],
                    type=self.type(p["type"]),
                    default=self.expr(p["default"]),
                    doc=self.text(p.get("doc")),
                )
            )
        for c in constraints:
            items.append(
                ast.AssertDecl(expr=self.expr(c["expr"]), message=self.text(c.get("message")))
            )
        return ast.ParamsBlock(items=items)

    def type_decl(self, t: dict[str, Any]) -> ast.EnumDecl | ast.StructDecl:
        doc = self.text(t.get("doc"))
        if t["kind"] == "enum":
            return ast.EnumDecl(name=t["name"], values=list(t["values"]), doc=doc)
        fields = [ast.StructField(name=f["name"], type=self.type(f["type"])) for f in t["fields"]]
        return ast.StructDecl(name=t["name"], fields=fields, doc=doc)

    def state(self) -> ast.StateBlock:
        variables = []
        for v in self.ir.get("state", []):
            type_ir = v["type"]
            inner = (
                type_ir[1] if isinstance(type_ir, list) and type_ir[0] == "per_player" else type_ir
            )
            init = None if v["init"] == self.zero(inner) else self.expr(v["init"])
            variables.append(
                ast.StateVar(
                    name=v["name"],
                    type=self.type(type_ir),
                    init=init,
                    visibility=self.visibility(v.get("visibility")),
                    size_visibility=self.visibility(v.get("size_visibility")),
                    doc=self.text(v.get("doc")),
                )
            )
        return ast.StateBlock(vars=variables)

    def zero(self, t: Any) -> Any:
        """El valor por defecto que pone el compilador si se omite la inicialización."""
        if isinstance(t, str):
            match t:
                case "Bool":
                    return ["const", False]
                case "Int" | "Real" | "Seat":
                    return ["const", 0]
                case "Text":
                    return ["const", ""]
                case "Cell":
                    return ["cell", ["const", 0], ["const", 0]]
            if t in self.enums:
                return ["enum", t, self.enums[t][0]]
            if t in self.structs:
                return ["struct", t, {k: self.zero(ft) for k, ft in self.structs[t]}]
            return None
        head = t[0]
        if head == "option":
            return ["const", None]
        if head in ("list", "set", "map", "zone", "bag"):
            return ["list"]
        if head in ("per_player",):
            return self.zero(t[1])
        if head == "grid":
            return self.zero(t[3])
        if head == "tuple":
            return ["tuple", *(self.zero(x) for x in t[1:])]
        return None

    def function(self, f: dict[str, Any]) -> ast.FnDecl:
        params = [ast.FnParam(name=p, type=self.type(t)) for p, t in f["params"]]
        body = self.expr(f["body"])
        return ast.FnDecl(
            name=f["name"],
            params=params,
            returns=self.type(f["returns"]),
            body=body,
            doc=self.text(f.get("doc")),
        )

    # --- flow -----------------------------------------------------------------------------------

    def flow(self) -> ast.FlowBlock:
        flow = self.ir["flow"]
        setup = flow.get("setup")
        items: list[ast.Item] = [
            ast.StartDecl(target=flow["start"], setup=self.stmts(setup) if setup else None)
        ]
        items.extend(self.blank(self.node(n)) for n in flow["nodes"])
        return ast.FlowBlock(items=items)

    def node(self, n: dict[str, Any]) -> ast.NodeDecl:
        kind = n["kind"]
        members: list[ast.Item] = []

        def member(key: str) -> None:
            if key in n:
                value = ast.Name(n[key]) if key == "mode" else self.expr(n[key])
                members.append(ast.Member(key=key, value=value))

        match kind:
            case "decision":
                member("actor")
            case "simultaneous":
                member("actors")
            case "window":
                member("eligible")
                member("mode")
                member("order")
            case "chance" | "auto":
                members.extend(self.stmts(n.get("effects", [])))
            case "phase":
                members.append(ast.StartDecl(target=n["start"]))
                for key in ("on_enter", "on_exit"):
                    if n.get(key):
                        members.append(ast.BlockMember(key=key, body=self.stmts(n[key])))
                members.extend(self.node(child) for child in n["nodes"])
            case "terminal":
                payoff = n["payoff"]
                if "rank" not in n:
                    while isinstance(payoff, list) and payoff[0] == "let":
                        members.append(ast.LetMember(name=payoff[1], value=self.expr(payoff[2])))
                        payoff = payoff[3]
                members.append(ast.Member(key="payoff", value=self.expr(payoff)))
                if "rank" in n:
                    members.append(ast.Member(key="rank", value=self.expr(n["rank"])))
        members.extend(self.action(a) for a in n.get("actions", []))
        if kind == "simultaneous" and n.get("resolve"):
            members.append(ast.BlockMember(key="resolve", body=self.stmts(n["resolve"])))
        members.extend(self.transition(t) for t in n.get("transitions", []))
        return ast.NodeDecl(kind=kind, name=n["id"], members=members, doc=self.text(n.get("doc")))

    def action(self, a: dict[str, Any]) -> ast.ActionDecl:
        params = []
        for p in a.get("params", []):
            type_ir, domain = p["type"], p["domain"]
            short = (domain == ["enum_values", type_ir]) or (
                type_ir == "Bool" and domain == ["list", ["const", False], ["const", True]]
            )
            params.append(
                ast.ActionParam(
                    name=p["name"],
                    type=self.type(type_ir),
                    domain=None if short else self.expr(domain),
                    visibility=self.visibility(p.get("visibility")),
                    size_visibility=self.visibility(p.get("size_visibility")),
                )
            )
        effects = self.stmts(a.get("effects", []))
        transitions = [self.transition(t) for t in a.get("transitions", [])]
        has_body = bool(effects or transitions)
        return ast.ActionDecl(
            name=a["name"],
            params=params,
            requires=self.expr(a["requires"]) if "requires" in a else None,
            effects=effects if has_body else None,
            transitions=transitions,
            visibility=self.visibility(a.get("visibility")),
            doc=self.text(a.get("doc")),
        )

    def transition(self, t: dict[str, Any]) -> ast.Transition:
        effects = t.get("effects")
        return ast.Transition(
            target="exit" if t["to"] == "$exit" else t["to"],
            when=self.expr(t["when"]) if "when" in t else None,
            effects=self.stmts(effects) if effects else None,
            doc=self.text(t.get("doc")),
        )

    # --- sentencias -----------------------------------------------------------------------------

    def stmts(self, block: list[Any]) -> list[ast.Stmt]:
        return [self.stmt(s) for s in block]

    def stmt(self, s: list[Any]) -> ast.Stmt:
        op, args = s[0], s[1:]
        match op:
            case "assign":
                target, value = args
                if (
                    isinstance(value, list)
                    and len(value) == 3
                    and value[1] == target
                    and value[0] in ("add", "sub", "mul", "concat", "difference")
                ):
                    compound = {
                        "add": "+=",
                        "sub": "-=",
                        "mul": "*=",
                        "concat": "+=",
                        "difference": "-=",
                    }
                    return ast.Assign(self.expr(target), compound[value[0]], self.expr(value[2]))
                return ast.Assign(self.expr(target), "=", self.expr(value))
            case "let":
                return ast.LetStmt(args[0], self.expr(args[1]))
            case "if":
                other = self.stmts(args[2]) if len(args) > 2 else None
                return ast.IfStmt(self.expr(args[0]), self.stmts(args[1]), other)
            case "for":
                return ast.ForStmt(args[0], self.expr(args[1]), self.stmts(args[2]))
            case "move":
                position = args[3] if len(args) > 3 else None
                return ast.MoveStmt(
                    self.selector(args[2]), self.expr(args[0]), self.expr(args[1]), position
                )
            case "flip":
                face = args[2]
                face_e: ast.Expr = (
                    ast.BoolLit(face[1])
                    if face[0] == "const" and isinstance(face[1], bool)
                    else ast.Paren(self.expr(face))
                )
                return ast.FlipStmt(self.selector(args[1]), self.expr(args[0]), face_e)
            case "shuffle":
                return ast.ShuffleStmt(self.expr(args[0]))
            case "roll" | "random_choice" | "sample":
                call = ast.Call(RANDOM[op], [self.expr(args[1])])
                return ast.Assign(self.expr(args[0]), "=", call)
            case "reveal":
                to = None if args[1] == ["seats"] else self.expr(args[1])
                label = ast.Text(args[2]) if len(args) > 2 else None
                return ast.RevealStmt(self.expr(args[0]), to, label)
            case "emit":
                fields = [(k, self.expr(v)) for k, v in args[1].items()]
                vis = self.visibility(args[2]) if len(args) > 2 else None
                return ast.EmitStmt(args[0], fields, vis)
            case "reward":
                return ast.RewardStmt(self.expr(args[1]), self.expr(args[0]))
            case "fail":
                return ast.FailStmt(ast.Text(args[0]))
        raise ValueError(f"sentencia desconocida en la IR: {op}")

    def selector(self, sel: list[Any]) -> ast.Selector:
        kind = sel[0]
        if kind == "all":
            return ast.Selector("all")
        if kind in ("value", "values"):
            value = self.expr(sel[1])
            if isinstance(value, ast.Name) and value.name in ("all", "top", "bottom", "at"):
                value = ast.Paren(value)
            return ast.Selector("value", value)
        return ast.Selector(kind, self.expr(sel[1]))

    # --- expresiones ----------------------------------------------------------------------------

    def expr(self, e: Any) -> ast.Expr:
        op: str = e[0]
        args = e[1:]
        match op:
            case "const":
                return self.const(args[0])
            case "rat":
                return self.rational(Fraction(args[0], args[1]))
            case "enum":
                if args[1] in self.bare:
                    return ast.Name(args[1])
                return ast.Field(ast.Name(args[0]), args[1])
            case "var" | "arg" | "local":
                return ast.Name(args[0])
            case "param":
                return ast.Name(args[0])
            case "actor" | "viewer" | "owner" | "item_face_up":
                return ast.Name(CONTEXT[op])
            case "seats":
                return ast.Name("seats")
            case "at":
                return ast.Call("at", [ast.Name(args[0])])
            case "list":
                return ast.ListLit([self.expr(x) for x in args])
            case "tuple":
                return ast.TupleLit([self.expr(x) for x in args])
            case "struct":
                return ast.StructLit(args[0], [(k, self.expr(v)) for k, v in args[1].items()])
            case "add" | "mul" | "and" | "or":
                return self.chain(op, args)
            case "neg":
                inner = self.expr(args[0])
                if isinstance(inner, ast.IntLit | ast.DecimalLit):
                    inner = ast.Paren(inner)
                return ast.Unary("-", inner)
            case "not":
                inner_ir = args[0]
                if isinstance(inner_ir, list) and inner_ir[0] == "contains":
                    return ast.Binary("not in", self.expr(inner_ir[2]), self.expr(inner_ir[1]))
                return ast.Unary("not", self.expr(inner_ir))
            case "if":
                return ast.IfExpr(self.expr(args[1]), self.expr(args[0]), self.expr(args[2]))
            case "case":
                arms = [(self.expr(c), self.expr(v)) for c, v in args[0]]
                if not arms:
                    return self.expr(args[1])
                return ast.CaseExpr(arms, self.expr(args[1]))
            case "let":
                lets: list[tuple[str, ast.Expr]] = []
                node: Any = e
                while isinstance(node, list) and node[0] == "let":
                    lets.append((node[1], self.expr(node[2])))
                    node = node[3]
                return ast.LetBlock(lets, self.expr(node))
            case "contains":
                return ast.Binary("in", self.expr(args[1]), self.expr(args[0]))
            case "index":
                return ast.Index(self.expr(args[0]), self.expr(args[1]))
            case "field":
                return ast.Field(self.expr(args[0]), args[1])
            case "range":
                return ast.RangeExpr(self.expr(args[0]), self.expr(args[1]))
            case "slice":
                return ast.Slice(self.expr(args[0]), self.expr(args[1]), self.expr(args[2]))
            case "enum_values":
                return ast.Field(ast.Name(args[0]), "values")
            case "call":
                return ast.Call(args[0], [self.expr(x) for x in args[1:]])
            case "map" | "filter" | "flat_map":
                return self.comprehension(e)
            case (
                "all"
                | "any"
                | "count"
                | "sum"
                | "max_of"
                | "min_of"
                | "argmax"
                | "argmin"
                | "sort_by"
            ):
                var, coll, body = args
                func = AGGREGATE_NAMES.get(op, op)
                if op in ("sum", "max_of", "min_of") and var == "x" and body == ["local", "x"]:
                    return ast.Call(func, [self.expr(coll)])
                return ast.Aggregate(func, var, self.expr(coll), self.expr(body))
        if op in BINARY:
            return ast.Binary(BINARY[op], self.expr(args[0]), self.expr(args[1]))
        return ast.Call(CALLS.get(op, op), [self.expr(x) for x in args])

    def chain(self, op: str, args: list[Any]) -> ast.Expr:
        """`["add", a, b, c]` → `a + b + c`; un primer operando que sea a su vez `add` va entre
        paréntesis para que el compilador no lo aplane."""
        symbol = VARIADIC[op]
        first = self.expr(args[0])
        if isinstance(args[0], list) and args[0][0] == op:
            first = ast.Paren(first)
        result = first
        for x in args[1:]:
            result = ast.Binary(symbol, result, self.expr(x))
        return result

    def const(self, value: Any) -> ast.Expr:
        if value is None:
            return ast.NoneLit()
        if isinstance(value, bool):
            return ast.BoolLit(value)
        if isinstance(value, int):
            return ast.Unary("-", ast.IntLit(-value)) if value < 0 else ast.IntLit(value)
        return ast.StrLit(value)

    def rational(self, value: Fraction) -> ast.Expr:
        text = decimal_text(abs(value))
        if text is not None:
            lit = ast.DecimalLit(abs(value), text)
            return ast.Unary("-", lit) if value < 0 else lit
        numerator = (
            ast.Unary("-", ast.IntLit(-value.numerator))
            if value < 0
            else ast.IntLit(value.numerator)
        )
        return ast.Call("rat", [numerator, ast.IntLit(value.denominator)])

    def comprehension(self, e: list[Any]) -> ast.Expr:
        """`map` / `filter` / `flat_map` → `[… for x in xs if c …]` cuando la cadena de
        `flat_map` acaba en `map` o `filter` (lo que produce el compilador); si no, la forma
        con variable (`flat_map(x in xs : …)`)."""
        node = e
        while node[0] == "flat_map":
            body = node[3]
            if not (isinstance(body, list) and body[0] in ("map", "filter", "flat_map")):
                op, var, coll, body = e
                return ast.Aggregate(op, var, self.expr(coll), self.expr(body))
            node = body
        clauses: list[ast.CompFor] = []
        node = e
        while True:
            op, var, coll, body = node
            if op == "filter":
                clauses.append(ast.CompFor(var, self.expr(coll), [self.expr(body)]))
                return ast.Comprehension(ast.Name(var), clauses)
            conds: list[ast.Expr] = []
            if isinstance(coll, list) and coll[0] == "filter" and coll[1] == var:
                conds = [self.expr(coll[3])]
                coll = coll[2]
            clauses.append(ast.CompFor(var, self.expr(coll), conds))
            if op == "map":
                element = self.expr(body)
                if conds and body == ["local", var]:
                    element = ast.Paren(element)  # si no, el compilador lo traduce a filter
                return ast.Comprehension(element, clauses)
            node = body

    # --- tipos, textos, visibilidad -------------------------------------------------------------

    def type(self, t: Any) -> ast.TypeExpr:
        if isinstance(t, str):
            return ast.TName(t)
        head, *rest = t
        match head:
            case "option":
                return ast.TOption(self.type(rest[0]))
            case "list" | "set" | "zone" | "bag" | "map":
                return ast.TGeneric(head.capitalize(), [self.type(x) for x in rest])
            case "tuple":
                return ast.TTuple([self.type(x) for x in rest])
            case "per_player":
                return ast.TPerPlayer(self.type(rest[0]))
            case "grid":
                w, h, inner = rest
                dims = [d if isinstance(d, int) else d[1] for d in (w, h)]
                return ast.TGrid(dims[0], dims[1], self.type(inner))
        raise ValueError(f"tipo desconocido en la IR: {t}")

    @staticmethod
    def text(value: Any) -> ast.Text | None:
        return None if value is None else ast.Text(value)

    def visibility(self, vis: Any) -> ast.Visibility | None:
        if vis is None or vis == "all":  # "all" es el valor por defecto
            return None
        if isinstance(vis, str):
            return ast.Visibility(vis)
        return ast.Visibility("when", self.expr(vis["when"]))
