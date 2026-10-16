# SPDX-License-Identifier: Apache-2.0
"""Análisis estáticos de una GameIR bien formada (los avisos de `gamehub check`).

Cada hallazgo señala el elemento de la IR al que se refiere (`where`):
`("node", id)`, `("transition", nodo, i)`, `("action", nodo, acción)`,
`("action_transition", nodo, acción, i)`, `("var", nombre)`, `("param", nombre)`,
`("function", nombre)`, `("type", nombre)` o `("game",)`. El compilador de Nomos lo traduce a
una posición en el texto.

- W401 nodo inalcanzable desde el inicio (sin mirar las condiciones).
- W402 transiciones que pueden no cubrir todos los casos: todas tienen condición y no hay una
  pareja complementaria (`c` / `not c`, `a < b` / `a >= b`…) ni una enumeración completa.
- W403 nodo desde el que no se puede llegar a ningún final.
- W404 bucle de nodos automáticos sin efectos: si se entra, no termina nunca.
- W405 posible fuga de información: un dato oculto llega a estado o eventos visibles para todos,
  decide quién juega o qué nodo sigue, o las jugadas legales dependen de datos que el actor no
  ve. Es un análisis de flujos explícitos e implícitos (`if`); lo que un bloque revela a todos
  (`reveal … to all`) deja de ser oculto en el resto del bloque.
- W406 declaración sin usar.
- W407 transición que nunca se toma: va detrás de una sin condición.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any

from gamehub.analysis import irwalk

Where = tuple[str, ...]


@dataclass(frozen=True)
class Finding:
    code: str
    message: str
    where: Where
    help: str | None = None


def lint(ir: dict[str, Any], uses: Iterable[Any] = ()) -> list[Finding]:
    """Avisos sobre la IR. `uses`: expresiones de fuera de la IR (tests, invariantes) que
    también cuentan como usos de parámetros, variables, funciones y tipos."""
    findings: list[Finding] = []
    graph = _Graph(ir)
    findings += graph.unreachable()
    findings += graph.dead_ends()
    findings += graph.loops_without_progress()
    findings += _transitions(ir, graph)
    findings += _Leaks(ir).run()
    findings += _unused(ir, uses)
    seen: set[tuple[str, Where, str]] = set()
    unique: list[Finding] = []
    for f in findings:
        key = (f.code, f.where, f.message)
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique


# --- grafo del flow -----------------------------------------------------------------------------

EXIT = "/exit"  # sufijo del vértice «salir de la fase P» (los ids de nodo no llevan '/')
WAITING = {"decision", "simultaneous", "window", "chance"}


class _Graph:
    """Grafo de saltos del flow, sin mirar las condiciones. Vértices: los nodos (entrar en una
    fase es un vértice que lleva a su `start`) y, por cada fase, `Fase/exit` (salir con
    `-> exit`, que lleva a las transiciones de la fase). Cada arista sabe si ejecuta efectos."""

    def __init__(self, ir: dict[str, Any]) -> None:
        self.nodes: dict[str, dict[str, Any]] = {}
        self.parent: dict[str, str | None] = {}
        for node, parent in irwalk.all_nodes(ir):
            self.nodes[node["id"]] = node
            self.parent[node["id"]] = parent
        self.start = ir["flow"]["start"]
        self.edges: dict[str, list[tuple[str, bool]]] = {}
        for node_id, node in self.nodes.items():
            out = self.edges.setdefault(node_id, [])
            if node["kind"] == "phase":
                out.append((node["start"], False))
                exits = self.edges.setdefault(node_id + EXIT, [])
                for t in node.get("transitions", []):
                    exits.append(self.jump(node_id, t))
                continue
            for t in _all_transitions(node):
                out.append(self.jump(node_id, t))

    def ancestors(self, node_id: str) -> list[str]:
        chain: list[str] = []
        parent = self.parent.get(node_id)
        while parent is not None:
            chain.append(parent)
            parent = self.parent.get(parent)
        return chain

    def jump(self, source: str, t: dict[str, Any]) -> tuple[str, bool]:
        """Arista de una transición: destino y si ejecuta efectos (los de la transición, o
        `on_exit`/`on_enter` de las fases de las que sale o en las que entra)."""
        effects = bool(t.get("effects"))
        if t["to"] == "$exit":
            phase = self.parent[source] or source
            return phase + EXIT, effects
        target = t["to"]
        left = set(self.ancestors(source))
        if self.nodes[source]["kind"] == "phase":
            left.add(source)
        entered = set(self.ancestors(target))
        crossed = left ^ entered
        if self.nodes[target]["kind"] == "phase":
            crossed.add(target)
        effects = effects or any(
            self.nodes[p].get("on_enter") or self.nodes[p].get("on_exit") for p in crossed
        )
        return target, effects

    def reachable(self) -> set[str]:
        seen = {self.start}
        stack = [self.start]
        while stack:
            for target, _ in self.edges.get(stack.pop(), []):
                if target not in seen:
                    seen.add(target)
                    stack.append(target)
        return seen

    def unreachable(self) -> list[Finding]:
        seen = self.reachable()
        findings: list[Finding] = []
        for node_id in self.nodes:
            if node_id in seen or any(p not in seen for p in self.ancestors(node_id)):
                continue  # dentro de una fase inalcanzable basta con avisar de la fase
            findings.append(
                Finding(
                    "W401",
                    f"el nodo {node_id} no es alcanzable desde el inicio",
                    ("node", node_id),
                    help="ninguna transición lleva a él: ¿falta un '-> " + node_id + "'?",
                )
            )
        return findings

    def dead_ends(self) -> list[Finding]:
        """Nodos alcanzables desde los que ningún camino llega a un terminal."""
        reverse: dict[str, set[str]] = {}
        for source, out in self.edges.items():
            for target, _ in out:
                reverse.setdefault(target, set()).add(source)
        finals = [n for n, node in self.nodes.items() if node["kind"] == "terminal"]
        alive = set(finals)
        stack = list(finals)
        while stack:
            for source in reverse.get(stack.pop(), ()):
                if source not in alive:
                    alive.add(source)
                    stack.append(source)
        seen = self.reachable()
        trapped = {v for v in seen if v not in alive}
        if not finals:
            return [
                Finding(
                    "W403",
                    "el juego no tiene ningún nodo terminal: la partida no puede acabar",
                    ("node", self.start),
                )
            ]
        findings: list[Finding] = []
        for v in sorted(trapped):
            if EXIT in v:
                continue
            entry = v == self.start or any(
                source in seen and source not in trapped for source in reverse.get(v, ())
            )
            if entry:
                findings.append(
                    Finding(
                        "W403",
                        f"desde {v} no se puede llegar a ningún final: la partida no acabaría",
                        ("node", v),
                    )
                )
        return findings

    def loops_without_progress(self) -> list[Finding]:
        """Ciclos de vértices automáticos (nodos `auto`, entradas y salidas de fases) cuyas
        aristas y vértices no ejecutan efectos: el estado no cambia, así que las condiciones dan
        siempre lo mismo y el ciclo se repite sin fin."""

        def quiet(v: str) -> bool:
            if EXIT in v:
                return not self.nodes[v.removesuffix(EXIT)].get("on_exit")
            node = self.nodes[v]
            if node["kind"] == "auto":
                return not node.get("effects")
            if node["kind"] == "phase":
                return not node.get("on_enter")
            return False

        graph = {
            v: [t for t, effects in out if not effects and quiet(t)]
            for v, out in self.edges.items()
            if quiet(v)
        }
        findings: list[Finding] = []
        for component in _cycles(graph):
            named = sorted(v for v in component if EXIT not in v) or [
                component[0].removesuffix(EXIT)
            ]
            loop = " → ".join(named)
            findings.append(
                Finding(
                    "W404",
                    f"bucle de nodos automáticos sin efectos ({loop}): si se entra, no termina",
                    ("node", named[0]),
                    help="algún nodo del bucle tiene que cambiar el estado o esperar a un jugador",
                )
            )
        return findings


def _all_transitions(node: dict[str, Any]) -> Iterator[dict[str, Any]]:
    for action in node.get("actions", []):
        yield from action.get("transitions", [])
    yield from node.get("transitions", [])


def _cycles(graph: dict[str, list[str]]) -> list[list[str]]:
    """Componentes fuertemente conexas con un ciclo (Tarjan, iterativo)."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    result: list[list[str]] = []
    counter = 0
    for root in graph:
        if root in index:
            continue
        work: list[tuple[str, int]] = [(root, 0)]
        while work:
            v, i = work.pop()
            if i == 0:
                index[v] = low[v] = counter
                counter += 1
                stack.append(v)
                on_stack.add(v)
            successors = graph.get(v, [])
            if i < len(successors):
                work.append((v, i + 1))
                w = successors[i]
                if w not in index:
                    work.append((w, 0))
                elif w in on_stack:
                    low[v] = min(low[v], index[w])
                continue
            if low[v] == index[v]:
                component: list[str] = []
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    component.append(w)
                    if w == v:
                        break
                if len(component) > 1 or v in graph.get(v, []):
                    result.append(component)
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[v])
    return result


# --- transiciones -------------------------------------------------------------------------------

NEGATION = {"eq": "ne", "ne": "eq", "lt": "ge", "ge": "lt", "le": "gt", "gt": "le"}
SWAPPED = {"eq": "eq", "ne": "ne", "lt": "gt", "gt": "lt", "le": "ge", "ge": "le"}


def _transitions(ir: dict[str, Any], graph: _Graph) -> list[Finding]:
    enums = {t["name"]: t["values"] for t in ir.get("types", []) if t["kind"] == "enum"}
    findings: list[Finding] = []
    exiting = {
        graph.parent[n]
        for n, node in graph.nodes.items()
        for t in _all_transitions(node)
        if t["to"] == "$exit"
    }
    for node_id, node in graph.nodes.items():
        kind = node["kind"]
        own = node.get("transitions", [])
        findings += _shadowed(own, ("transition", node_id))
        for action in node.get("actions", []):
            findings += _shadowed(
                action.get("transitions", []), ("action_transition", node_id, action["name"])
            )
        if kind == "terminal" or (kind == "phase" and node_id not in exiting):
            continue
        # Listas que se prueban al salir: las de cada acción seguidas de las del nodo y, si no
        # hay acción (o todos pasan en una ventana), las del nodo.
        lists: list[tuple[list[dict[str, Any]], Where]] = []
        if kind in ("decision", "window"):
            for action in node.get("actions", []):
                mine = action.get("transitions", [])
                if mine and not own:
                    where: Where = (
                        "action_transition",
                        node_id,
                        action["name"],
                        str(len(mine) - 1),
                    )
                    lists.append((mine, where))
                elif not _covers(mine, enums) and own:
                    lists.append((mine + own, ("transition", node_id, str(len(own) - 1))))
        if own and kind != "decision":
            lists.append((own, ("transition", node_id, str(len(own) - 1))))
        for transitions, where in lists:
            if not _covers(transitions, enums):
                findings.append(
                    Finding(
                        "W402",
                        f"puede que ninguna transición se aplique al salir de {node_id}: todas "
                        "tienen condición",
                        where,
                        help="si no se cumple ninguna, la partida se detiene con un error; "
                        "añade al final una transición sin 'when'",
                    )
                )
    return findings


def _shadowed(transitions: list[dict[str, Any]], prefix: Where) -> list[Finding]:
    for i, t in enumerate(transitions):
        if "when" not in t and i + 1 < len(transitions):
            target = transitions[i + 1]["to"]
            return [
                Finding(
                    "W407",
                    f"la transición a {_target(target)} nunca se toma: la anterior no tiene "
                    "condición",
                    (*prefix, str(i + 1)),
                )
            ]
    return []


def _target(to: str) -> str:
    return "exit" if to == "$exit" else to


def _covers(transitions: list[dict[str, Any]], enums: dict[str, list[str]]) -> bool:
    guards = [t.get("when") for t in transitions]
    if any(g is None or g == ["const", True] for g in guards):
        return True
    present = [g for g in guards if g is not None]
    for i, g in enumerate(present):
        for h in present[i + 1 :]:
            if _complementary(g, h):
                return True
    return _enum_exhaustive(present, enums)


def _complementary(g: Any, h: Any) -> bool:
    if g == ["not", h] or h == ["not", g]:
        return True
    if isinstance(g, list) and isinstance(h, list) and len(g) == 3 and g[0] in NEGATION:
        op, a, b = g
        return h in ([NEGATION[op], a, b], [SWAPPED[NEGATION[op]], b, a])
    return False


def _enum_exhaustive(guards: list[Any], enums: dict[str, list[str]]) -> bool:
    """Condiciones `x == E.v` (o `E.v == x`) sobre la misma `x` que recorren todo el enum."""
    by_subject: dict[str, tuple[str, set[str]]] = {}
    for g in guards:
        if not (isinstance(g, list) and len(g) == 3 and g[0] == "eq"):
            continue
        for subject, value in ((g[1], g[2]), (g[2], g[1])):
            if isinstance(value, list) and value[0] == "enum":
                key = repr(subject)
                enum_name, entries = by_subject.get(key, (value[1], set()))
                if enum_name == value[1]:
                    entries.add(value[2])
                    by_subject[key] = (enum_name, entries)
    return any(set(enums.get(name, [])) <= seen for name, seen in by_subject.values())


# --- fugas de información -----------------------------------------------------------------------


def _hidden(visibility: Any) -> bool:
    """¿Oculta algo esta visibilidad? `@visible(face_up)` no cuenta: lo que está boca arriba es
    público y lo que no, no se puede leer sin darle la vuelta (que es una jugada visible)."""
    return visibility not in (None, "all", {"when": ["item_face_up"]})


def _owner_sees(visibility: Any) -> bool:
    """¿Ve el dueño de cada parte su parte? `@visible(owner)` o un predicado que lo incluye como
    alternativa: `@visible(viewer == owner or …)`."""
    if visibility == "owner":
        return True
    if not isinstance(visibility, dict):
        return False
    owner_eq = (["eq", ["viewer"], ["owner"]], ["eq", ["owner"], ["viewer"]])
    when = visibility.get("when")
    if when in owner_eq:
        return True
    return isinstance(when, list) and when[:1] == ["or"] and any(x in owner_eq for x in when[1:])


class _Leaks:
    """Datos ocultos: variables con visibilidad distinta de `all` y argumentos de acción
    ocultos. Una lectura no cuenta como oculta si es el tamaño de algo de tamaño visible, o (al
    decidir qué puede jugar el actor) la parte del actor de una variable `@visible(owner)`."""

    def __init__(self, ir: dict[str, Any]) -> None:
        self.ir = ir
        self.vars = {v["name"]: v for v in ir.get("state", [])}
        self.functions = {f["name"]: f for f in ir.get("functions", [])}
        self._fn_cache: dict[str, set[str]] = {}
        self.findings: list[Finding] = []

    def run(self) -> list[Finding]:
        self.block(
            self.ir["flow"].get("setup", []), {}, set(), {}, ("node", self.ir["flow"]["start"])
        )
        for node, _ in irwalk.all_nodes(self.ir):
            self.node(node)
        return self.findings

    # --- lecturas ocultas -----------------------------------------------------------------------

    def private(self, name: str) -> bool:
        var = self.vars.get(name)
        return var is not None and _hidden(var.get("visibility"))

    def size_public(self, e: Any, hidden_args: dict[str, Any]) -> bool:
        """¿Es pública la cantidad de elementos de `e`?"""
        if isinstance(e, list) and e and e[0] == "items":
            return self.size_public(e[1], hidden_args)
        if isinstance(e, list) and e and e[0] == "index":
            e = e[1]
        if isinstance(e, list) and e and e[0] == "var":
            var = self.vars.get(e[1], {})
            return not _hidden(var.get("visibility")) or not _hidden(var.get("size_visibility"))
        if isinstance(e, list) and e and e[0] == "arg" and e[1] in hidden_args:
            return not _hidden(hidden_args[e[1]].get("size_visibility"))
        return False

    def reads(
        self,
        e: Any,
        locals_: dict[str, set[str]],
        hidden_args: dict[str, Any],
        actor_view: bool = False,
    ) -> set[str]:
        """Datos ocultos que lee la expresión (nombres para el mensaje)."""
        op = e[0]
        match op:
            case "var":
                return {f"`{e[1]}`"} if self.private(e[1]) else set()
            case "arg":
                return {f"el argumento oculto `{e[1]}`"} if e[1] in hidden_args else set()
            case "local":
                return set(locals_.get(e[1], set()))
            case "index" if actor_view and e[2] == ["actor"]:
                base = e[1]
                if isinstance(base, list) and base[0] == "var":
                    var = self.vars.get(base[1], {})
                    if _owner_sees(var.get("visibility")):
                        return set()
            case "len" | "size" if self.size_public(e[1], hidden_args):
                inner = e[1][1] if e[1][0] == "items" else e[1]
                keys = inner[2:] if inner[0] == "index" else []
                return set().union(*(self.reads(k, locals_, hidden_args, actor_view) for k in keys))
            case "call":
                found = set(self.function(e[1]))
                for arg in e[2:]:
                    found |= self.reads(arg, locals_, hidden_args, actor_view)
                return found
        found: set[str] = set()
        for child in irwalk.children(e):
            found |= self.reads(child, locals_, hidden_args, actor_view)
        return found

    def function(self, name: str) -> set[str]:
        if name not in self._fn_cache:
            self._fn_cache[name] = set()  # las funciones no son recursivas, pero por si acaso
            body = self.functions.get(name, {}).get("body")
            self._fn_cache[name] = self.reads(body, {}, {}) if body is not None else set()
        return self._fn_cache[name]

    # --- sentencias -----------------------------------------------------------------------------

    def block(
        self,
        stmts: list[Any],
        locals_: dict[str, set[str]],
        pc: set[str],
        hidden_args: dict[str, Any],
        where: Where,
        revealed: frozenset[str] = frozenset(),
    ) -> None:
        """Recorre sentencias buscando datos ocultos que acaben a la vista. Lo que el bloque
        revela a todos (`reveal … to all`) deja de contar como oculto en lo que sigue."""
        scope = dict(locals_)
        shown = set(revealed)

        def hidden(e: Any, extra: set[str] = set()) -> set[str]:  # noqa: B006 (no se modifica)
            return (self.reads(e, scope, hidden_args) | extra | pc) - shown

        for stmt in stmts:
            op = stmt[0]
            match op:
                case "let":
                    scope[stmt[1]] = hidden(stmt[2])
                case "assign":
                    target, value = stmt[1], stmt[2]
                    root = _root(target)
                    if root is not None and not self.private(root):
                        keys = set().union(
                            *(self.reads(k, scope, hidden_args) for k in _lvalue_keys(target))
                        )
                        found = hidden(value, keys)
                        if found:
                            self.leak(
                                f"`{root}` es visible para todos y recibe datos ocultos "
                                f"({_names(found)})",
                                where,
                            )
                case "if":
                    cond = hidden(stmt[1])
                    inner = frozenset(shown)
                    self.block(stmt[2], scope, cond, hidden_args, where, inner)
                    if len(stmt) > 3 and stmt[3] is not None:
                        self.block(stmt[3], scope, cond, hidden_args, where, inner)
                case "for":
                    loop = dict(scope)
                    loop[stmt[1]] = hidden(stmt[2])
                    self.block(stmt[3], loop, pc - shown, hidden_args, where, frozenset(shown))
                case "emit":
                    visibility = stmt[3] if len(stmt) > 3 else None
                    if not _hidden(visibility):
                        found = set(pc) - shown
                        for field in stmt[2].values():
                            found |= hidden(field)
                        if found:
                            self.leak(
                                f"el evento `{stmt[1]}` lo ven todos y lleva datos ocultos "
                                f"({_names(found)})",
                                where,
                            )
                case "reveal" if stmt[2] == ["seats"]:
                    shown |= self.reads(stmt[1], scope, hidden_args)

    def leak(self, message: str, where: Where) -> None:
        self.findings.append(
            Finding(
                "W405",
                f"posible fuga de información: {message}",
                where,
                help="si es intencionado (se revela a propósito), usa `reveal` antes o restringe "
                "la visibilidad con @visible",
            )
        )

    # --- nodos ----------------------------------------------------------------------------------

    def node(self, node: dict[str, Any]) -> None:
        node_id = node["id"]
        here: Where = ("node", node_id)
        for key in ("actor", "actors", "eligible", "order"):
            if key in node:
                found = self.reads(node[key], {}, {})
                if found:
                    self.leak(
                        f"quién juega en {node_id} depende de datos ocultos ({_names(found)})",
                        here,
                    )
        for key in ("effects", "resolve", "on_enter", "on_exit"):
            if node.get(key):
                self.block(node[key], {}, set(), {}, here)
        for action in node.get("actions", []):
            self.action(node_id, action)
        for i, t in enumerate(node.get("transitions", [])):
            self.transition(t, {}, ("transition", node_id, str(i)))

    def action(self, node_id: str, action: dict[str, Any]) -> None:
        name = action["name"]
        where: Where = ("action", node_id, name)
        hidden = {p["name"]: p for p in action.get("params", []) if _hidden(p.get("visibility"))}
        legality = [p["domain"] for p in action.get("params", []) if "domain" in p]
        if "requires" in action:
            legality.append(action["requires"])
        found: set[str] = set()
        for e in legality:
            found |= self.reads(e, {}, {}, actor_view=True)
        if found:
            self.leak(
                f"las jugadas legales de {name} dependen de datos que el actor no ve "
                f"({_names(found)})",
                where,
            )
        if action.get("effects"):
            self.block(action["effects"], {}, set(), hidden, where)
        for i, t in enumerate(action.get("transitions", [])):
            self.transition(t, hidden, ("action_transition", node_id, name, str(i)))

    def transition(self, t: dict[str, Any], hidden: dict[str, Any], where: Where) -> None:
        if "when" in t:
            found = self.reads(t["when"], {}, hidden)
            if found:
                self.leak(
                    f"el camino a {_target(t['to'])} depende de datos ocultos ({_names(found)}) "
                    "y todos ven por qué nodo sigue la partida",
                    where,
                )
        if t.get("effects"):
            self.block(t["effects"], {}, set(), hidden, where)


def _root(lvalue: Any) -> str | None:
    node = lvalue
    while isinstance(node, list) and node and node[0] in ("index", "field"):
        node = node[1]
    return node[1] if isinstance(node, list) and node and node[0] == "var" else None


def _lvalue_keys(lvalue: Any) -> Iterator[Any]:
    node = lvalue
    while isinstance(node, list) and node and node[0] in ("index", "field"):
        if node[0] == "index":
            yield node[2]
        node = node[1]


def _names(found: set[str]) -> str:
    return ", ".join(sorted(found))


# --- declaraciones sin usar ---------------------------------------------------------------------


def _unused(ir: dict[str, Any], uses: Iterable[Any]) -> list[Finding]:
    declared_types = {t["name"] for t in ir.get("types", [])}
    used_vars: set[str] = set()
    used_params: set[str] = set()
    used_calls: set[str] = set()
    used_types: set[str] = set()

    def expr(e: Any) -> None:
        for node in irwalk.walk(e):
            match node[0]:
                case "var":
                    used_vars.add(node[1])
                case "param":
                    used_params.add(node[1])
                case "call":
                    used_calls.add(node[1])
                case "enum" | "enum_values" | "struct":
                    used_types.add(node[1])

    def type_spec(t: Any) -> None:
        if isinstance(t, str):
            if t in declared_types:
                used_types.add(t)
        elif isinstance(t, list) and t:
            if t[0] == "param":  # dimensión de un Grid dada por un parámetro
                used_params.add(t[1])
                return
            for part in t[1:]:
                type_spec(part)

    for e in irwalk.game_exprs(ir):
        expr(e)
    for e in uses:
        expr(e)
    for p in ir.get("params", []):
        type_spec(p["type"])
    for v in ir.get("state", []):
        type_spec(v["type"])
    for f in ir.get("functions", []):
        for p in f["params"]:
            type_spec(p[1])
        type_spec(f["returns"])
    for t in ir.get("types", []):
        for field in t.get("fields", []):
            if field["type"] != t["name"]:
                type_spec(field["type"])
    for node, _ in irwalk.all_nodes(ir):
        for action in node.get("actions", []):
            for p in action.get("params", []):
                type_spec(p["type"])
    findings: list[Finding] = []
    for p in ir.get("params", []):
        if p["name"] not in used_params:
            findings.append(
                Finding("W406", f"el parámetro `{p['name']}` no se usa", ("param", p["name"]))
            )
    for v in ir.get("state", []):
        if v["name"] not in used_vars:
            findings.append(
                Finding(
                    "W406", f"la variable de estado `{v['name']}` no se usa", ("var", v["name"])
                )
            )
    for f in ir.get("functions", []):
        if f["name"] not in used_calls:
            findings.append(
                Finding("W406", f"la función `{f['name']}` no se usa", ("function", f["name"]))
            )
    for t in ir.get("types", []):
        if t["name"] not in used_types:
            findings.append(
                Finding("W406", f"el tipo `{t['name']}` no se usa", ("type", t["name"]))
            )
    return findings
