# SPDX-License-Identifier: Apache-2.0
"""Comprobaciones de buena formación que el JSON Schema no puede expresar.

Suponen un documento que ya pasa el esquema. Comprueban:

- declaraciones únicas (estado, parámetros, funciones, tipos, nodos, acciones)
- referencias: variables, parámetros, argumentos, locales, funciones (y su aridad),
  tipos y valores de enumerados, campos de structs, nodos de `at` y de transiciones
- contextos: `actor` en acciones y transiciones de decisión; `viewer` / `item_face_up` en
  visibilidad; `owner` en visibilidad e inicialización; sin leer estado en parámetros
- sentencias aleatorias solo en `flow.setup` y en nodos `chance`; lvalues válidos
- sin recursión entre funciones (las expresiones deben ser totales)
- salidas: transiciones incondicionales al final, `$exit` solo dentro de fases, nodos con salida
- nodos simultáneos sin transiciones por acción; `pass` reservado en ventanas
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from gamehub.ir.catalog import Catalog, OpSpec, load_catalog
from gamehub.ir.problems import Problem

PRIMITIVE_TYPES = frozenset({"Bool", "Int", "Real", "Text", "Seat", "Cell"})


@dataclass(frozen=True)
class _Ctx:
    """Qué está permitido en el punto actual del recorrido."""

    path: str
    args: frozenset[str] = frozenset()
    locals: frozenset[str] = frozenset()
    actor: bool = False
    visibility: bool = False
    owned: bool = False
    chance: bool = False
    reads_state: bool = True

    def at(self, *parts: object) -> _Ctx:
        return replace(self, path="/".join([self.path, *map(str, parts)]))

    def bind(self, name: str) -> _Ctx:
        return replace(self, locals=self.locals | {name})


class _Checker:
    def __init__(self, doc: dict[str, Any], catalog: Catalog) -> None:
        self.doc = doc
        self.catalog = catalog
        self.problems: list[Problem] = []
        self.state = self._names(doc.get("state", []), "state")
        self.params = self._names(doc.get("params", []), "params") | {"num_players"}
        functions = doc.get("functions", [])
        self._names(functions, "functions")
        self.arity = {f["name"]: len(f["params"]) for f in functions}
        types = doc.get("types", [])
        self._names(types, "types")
        self.enums = {t["name"]: set(t["values"]) for t in types if t["kind"] == "enum"}
        self.structs = {
            t["name"]: [f["name"] for f in t["fields"]] for t in types if t["kind"] == "struct"
        }
        self.node_ids: set[str] = set()
        self.calls: dict[str, set[str]] = {name: set() for name in self.arity}
        self.current_function: str | None = None

    # --- utilidades -----------------------------------------------------------------------------

    def error(self, path: str, message: str) -> None:
        self.problems.append(Problem(path, message))

    def _names(self, items: list[dict[str, Any]], section: str) -> set[str]:
        seen: set[str] = set()
        for i, item in enumerate(items):
            if item["name"] in seen:
                self.error(f"{section}/{i}/name", f"nombre duplicado: {item['name']}")
            seen.add(item["name"])
        return seen

    # --- documento ------------------------------------------------------------------------------

    def run(self) -> list[Problem]:
        doc = self.doc
        players = doc["players"]
        if players["min"] > players["max"]:
            self.error("players", "min no puede ser mayor que max")
        for i, t in enumerate(doc.get("types", [])):
            for j, f in enumerate(t.get("fields", [])):
                self.type_ref(f["type"], f"types/{i}/fields/{j}/type")
            if t["kind"] == "struct":
                fields = self.structs[t["name"]]
                if len(set(fields)) != len(fields):
                    self.error(f"types/{i}/fields", "campos duplicados")
        constant = _Ctx("", reads_state=False)
        for i, p in enumerate(doc.get("params", [])):
            self.type_ref(p["type"], f"params/{i}/type")
            self.expr(p["default"], replace(constant, path=f"params/{i}/default"))
        for i, c in enumerate(doc.get("constraints", [])):
            self.expr(c["expr"], replace(constant, path=f"constraints/{i}/expr"))
        for i, var in enumerate(doc.get("state", [])):
            self.state_var(var, f"state/{i}")
        for i, fn in enumerate(doc.get("functions", [])):
            self.function(fn, f"functions/{i}")
        self.flow(doc["flow"])
        self.check_recursion()
        return sorted(set(self.problems))

    def type_ref(self, t: Any, path: str) -> None:
        if isinstance(t, str):
            if t not in PRIMITIVE_TYPES and t not in self.enums and t not in self.structs:
                self.error(path, f"tipo desconocido: {t}")
            return
        head, *rest = t
        if head == "grid":
            for k, dim in enumerate(rest[:2], start=1):
                if isinstance(dim, list) and dim[1] not in self.params:
                    self.error(f"{path}/{k}", f"parámetro desconocido: {dim[1]}")
            self.type_ref(rest[2], f"{path}/3")
            return
        for k, sub in enumerate(rest, start=1):
            self.type_ref(sub, f"{path}/{k}")

    def state_var(self, var: dict[str, Any], path: str) -> None:
        self.type_ref(var["type"], f"{path}/type")
        per_player = isinstance(var["type"], list) and var["type"][0] == "per_player"
        self.expr(var["init"], _Ctx(f"{path}/init", owned=per_player, reads_state=False))
        for key in ("visibility", "size_visibility"):
            if key not in var:
                continue
            if var[key] == "owner" and not per_player:
                self.error(f"{path}/{key}", "'owner' solo tiene sentido en variables per_player")
            self.visibility(var[key], f"{path}/{key}")

    def function(self, fn: dict[str, Any], path: str) -> None:
        names = [p[0] for p in fn["params"]]
        if len(set(names)) != len(names):
            self.error(f"{path}/params", "parámetros duplicados")
        for k, (_, t) in enumerate(fn["params"]):
            self.type_ref(t, f"{path}/params/{k}/1")
        self.type_ref(fn["returns"], f"{path}/returns")
        self.current_function = fn["name"]
        self.expr(fn["body"], _Ctx(f"{path}/body", args=frozenset(names)))
        self.current_function = None

    def visibility(self, vis: Any, path: str) -> None:
        if isinstance(vis, dict):
            self.expr(vis["when"], _Ctx(f"{path}/when", visibility=True, owned=True))

    def check_recursion(self) -> None:
        visiting: set[str] = set()
        done: set[str] = set()

        def visit(name: str, trail: list[str]) -> None:
            if name in done:
                return
            if name in visiting:
                cycle = " → ".join([*trail[trail.index(name) :], name])
                self.error("functions", f"recursión no permitida: {cycle}")
                return
            visiting.add(name)
            for callee in sorted(self.calls.get(name, ())):
                visit(callee, [*trail, name])
            visiting.discard(name)
            done.add(name)

        for name in sorted(self.calls):
            visit(name, [])

    # --- flow -----------------------------------------------------------------------------------

    def flow(self, flow: dict[str, Any]) -> None:
        self.collect_nodes(flow["nodes"], "flow/nodes")
        if flow["start"] not in {n["id"] for n in flow["nodes"]}:
            self.error(
                "flow/start", f"el nodo inicial no existe en el nivel superior: {flow['start']}"
            )
        self.block(flow.get("setup", []), _Ctx("flow/setup", chance=True))
        for i, node in enumerate(flow["nodes"]):
            self.node(node, f"flow/nodes/{i}", in_phase=False)

    def collect_nodes(self, nodes: list[dict[str, Any]], path: str) -> None:
        for i, node in enumerate(nodes):
            if node["id"] in self.node_ids:
                self.error(f"{path}/{i}/id", f"id de nodo duplicado: {node['id']}")
            self.node_ids.add(node["id"])
            if node["kind"] == "phase":
                self.collect_nodes(node["nodes"], f"{path}/{i}/nodes")

    def node(self, node: dict[str, Any], path: str, in_phase: bool) -> None:
        kind = node["kind"]
        base = _Ctx(path)
        transitions = node.get("transitions", [])
        match kind:
            case "decision":
                self.expr(node["actor"], base.at("actor"))
                self.actions(node["actions"], path, in_phase)
                self.transitions(transitions, replace(base, actor=True).at("transitions"), in_phase)
                self.require_exit(node, path)
            case "simultaneous":
                self.expr(node["actors"], base.at("actors"))
                self.actions(node["actions"], path, in_phase)
                self.block(node.get("resolve", []), base.at("resolve"))
                self.transitions(transitions, base.at("transitions"), in_phase)
                for j, action in enumerate(node["actions"]):
                    if action.get("transitions"):
                        self.error(
                            f"{path}/actions/{j}/transitions",
                            "en un nodo simultáneo las acciones se resuelven juntas: "
                            "las transiciones van en el nodo",
                        )
                if not transitions:
                    self.error(path, "un nodo simultáneo necesita transiciones de nodo")
            case "window":
                self.expr(node["eligible"], base.at("eligible"))
                if "order" in node:
                    self.expr(node["order"], base.at("order"))
                self.actions(node["actions"], path, in_phase)
                self.transitions(transitions, base.at("transitions"), in_phase)
                if not transitions:
                    self.error(
                        path, "una ventana necesita transiciones de nodo (todos pueden pasar)"
                    )
                for j, action in enumerate(node["actions"]):
                    if action["name"] == "pass":
                        self.error(
                            f"{path}/actions/{j}/name",
                            "'pass' está reservado: en una ventana pasar es implícito",
                        )
            case "chance" | "auto":
                self.block(
                    node.get("effects", []), replace(base, chance=kind == "chance").at("effects")
                )
                self.transitions(transitions, base.at("transitions"), in_phase)
                if not transitions:
                    self.error(path, f"un nodo {kind} necesita al menos una transición")
            case "phase":
                if node["start"] not in {n["id"] for n in node["nodes"]}:
                    self.error(f"{path}/start", f"el inicio no es hijo de la fase: {node['start']}")
                self.block(node.get("on_enter", []), base.at("on_enter"))
                self.block(node.get("on_exit", []), base.at("on_exit"))
                for i, child in enumerate(node["nodes"]):
                    self.node(child, f"{path}/nodes/{i}", in_phase=True)
                self.transitions(transitions, base.at("transitions"), in_phase)
            case "terminal":
                self.expr(node["payoff"], base.at("payoff"))
                if "rank" in node:
                    self.expr(node["rank"], base.at("rank"))

    def require_exit(self, node: dict[str, Any], path: str) -> None:
        if node.get("transitions"):
            return
        if not all(a.get("transitions") for a in node["actions"]):
            self.error(path, "sin transiciones de nodo, todas las acciones deben tener las suyas")

    def actions(self, actions: list[dict[str, Any]], path: str, in_phase: bool) -> None:
        self._names(actions, f"{path}/actions")
        for j, action in enumerate(actions):
            apath = f"{path}/actions/{j}"
            ctx = _Ctx(apath, actor=True)
            args: set[str] = set()
            for k, param in enumerate(action.get("params", [])):
                ppath = f"{apath}/params/{k}"
                self.type_ref(param["type"], f"{ppath}/type")
                self.expr(
                    param["domain"], replace(ctx, path=f"{ppath}/domain", args=frozenset(args))
                )
                for key in ("visibility", "size_visibility"):
                    if key in param:
                        self.visibility(param[key], f"{ppath}/{key}")
                if param["name"] in args:
                    self.error(f"{ppath}/name", f"parámetro duplicado: {param['name']}")
                args.add(param["name"])
            full = replace(ctx, args=frozenset(args))
            if "requires" in action:
                self.expr(action["requires"], full.at("requires"))
            self.block(action.get("effects", []), full.at("effects"))
            if "visibility" in action:
                self.visibility(action["visibility"], f"{apath}/visibility")
            self.transitions(action.get("transitions", []), full.at("transitions"), in_phase)

    def transitions(self, transitions: list[dict[str, Any]], ctx: _Ctx, in_phase: bool) -> None:
        for k, t in enumerate(transitions):
            tctx = ctx.at(k)
            target = t["to"]
            if target == "$exit":
                if not in_phase:
                    self.error(f"{tctx.path}/to", "'$exit' solo se permite dentro de una fase")
            elif target not in self.node_ids:
                self.error(f"{tctx.path}/to", f"nodo desconocido: {target}")
            if "when" in t:
                self.expr(t["when"], tctx.at("when"))
            elif k != len(transitions) - 1:
                self.error(
                    tctx.path, "transición incondicional antes de otras: serían inalcanzables"
                )
            self.block(t.get("effects", []), tctx.at("effects"))

    # --- sentencias -----------------------------------------------------------------------------

    def block(self, stmts: list[Any], ctx: _Ctx) -> None:
        local_names = ctx.locals
        for i, stmt in enumerate(stmts):
            bound = self.stmt(stmt, replace(ctx, locals=local_names).at(i))
            if bound is not None:
                local_names = local_names | {bound}

    def stmt(self, stmt: list[Any], ctx: _Ctx) -> str | None:
        op, args = stmt[0], stmt[1:]
        spec = self.catalog.statements[op]
        if spec.chance and not ctx.chance:
            self.error(
                ctx.path, f"'{op}' es aleatoria: solo se permite en flow.setup o en nodos chance"
            )
        match op:
            case "let":
                self.expr(args[1], ctx.at(2))
                return args[0]
            case "for":
                self.expr(args[1], ctx.at(2))
                self.block(args[2], ctx.bind(args[0]).at(3))
                return None
        self.walk_args(spec, args, ctx, statement=True)
        return None

    def selector(self, sel: list[Any], ctx: _Ctx) -> None:
        self.walk_args(self.catalog.selectors[sel[0]], sel[1:], ctx, statement=False)

    def lvalue(self, e: Any, ctx: _Ctx) -> None:
        node = e
        while isinstance(node, list) and node and node[0] in ("index", "field"):
            node = node[1]
        if not (isinstance(node, list) and node and node[0] == "var"):
            self.error(ctx.path, "solo se puede modificar el estado: var, index o field sobre var")

    # --- expresiones ----------------------------------------------------------------------------

    def expr(self, e: Any, ctx: _Ctx) -> None:
        op, args = e[0], e[1:]
        spec = self.catalog.expressions[op]
        match op:
            case "var":
                if not ctx.reads_state:
                    self.error(
                        ctx.path, "aquí no se puede leer el estado (solo parámetros y constantes)"
                    )
                elif args[0] not in self.state:
                    self.error(ctx.path, f"variable de estado desconocida: {args[0]}")
            case "param":
                if args[0] not in self.params:
                    self.error(ctx.path, f"parámetro desconocido: {args[0]}")
            case "arg":
                if args[0] not in ctx.args:
                    self.error(ctx.path, f"argumento desconocido en este contexto: {args[0]}")
            case "local":
                if args[0] not in ctx.locals:
                    self.error(ctx.path, f"variable local no ligada: {args[0]}")
            case "actor":
                if not ctx.actor:
                    self.error(
                        ctx.path, "'actor' solo existe en acciones y transiciones de decisión"
                    )
            case "viewer" | "item_face_up":
                if not ctx.visibility:
                    self.error(ctx.path, f"'{op}' solo existe en políticas de visibilidad")
            case "owner":
                if not ctx.owned:
                    self.error(
                        ctx.path, "'owner' solo existe en visibilidad e inicialización per_player"
                    )
            case "at":
                if args[0] not in self.node_ids:
                    self.error(ctx.path, f"nodo desconocido: {args[0]}")
            case "enum":
                self.enum_value(args[0], args[1], ctx.path)
            case "enum_values":
                if args[0] not in self.enums:
                    self.error(ctx.path, f"enumerado desconocido: {args[0]}")
            case "struct":
                self.struct_literal(args[0], args[1], ctx.path)
            case "call":
                self.call(args[0], len(args) - 1, ctx.path)
        self.walk_args(spec, args, ctx, statement=False)

    def enum_value(self, type_name: str, value: str, path: str) -> None:
        if type_name not in self.enums:
            self.error(path, f"enumerado desconocido: {type_name}")
        elif value not in self.enums[type_name]:
            self.error(path, f"{type_name} no tiene el valor {value}")

    def struct_literal(self, type_name: str, fields: dict[str, Any], path: str) -> None:
        if type_name not in self.structs:
            self.error(path, f"struct desconocido: {type_name}")
            return
        expected = set(self.structs[type_name])
        if set(fields) != expected:
            self.error(path, f"{type_name} requiere exactamente los campos {sorted(expected)}")

    def call(self, name: str, count: int, path: str) -> None:
        if name not in self.arity:
            self.error(path, f"función desconocida: {name}")
            return
        if count != self.arity[name]:
            self.error(path, f"{name} espera {self.arity[name]} argumentos, recibe {count}")
        if self.current_function is not None:
            self.calls[self.current_function].add(name)

    def walk_args(self, spec: OpSpec, args: list[Any], ctx: _Ctx, *, statement: bool) -> None:
        """Recorre los argumentos según su tipo. En operadores con ligadura (`bind`), solo el
        último argumento (el cuerpo) ve la variable ligada."""
        kinds = spec.kinds_for(len(args))
        bound = args[kinds.index("bind")] if "bind" in kinds else None
        for i, (kind, value) in enumerate(zip(kinds, args, strict=True)):
            sub = ctx.at(i + 1)
            match kind:
                case "e":
                    body = bound is not None and i == len(args) - 1 and not statement
                    self.expr(value, sub.bind(bound) if body and bound else sub)
                case "l":
                    self.lvalue(value, sub)
                    self.expr(value, sub)
                case "cases":
                    for k, (cond, result) in enumerate(value):
                        self.expr(cond, sub.at(k, 0))
                        self.expr(result, sub.at(k, 1))
                case "fields":
                    for name, field_expr in value.items():
                        self.expr(field_expr, sub.at(name))
                case "block":
                    self.block(value, sub)
                case "sel":
                    self.selector(value, sub)
                case "vis":
                    self.visibility(value, sub.path)


def wellformed_problems(doc: dict[str, Any]) -> list[Problem]:
    """Problemas de buena formación de un documento que ya cumple el JSON Schema."""
    return _Checker(doc, load_catalog()).run()
