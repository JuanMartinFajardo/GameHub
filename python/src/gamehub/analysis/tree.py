# SPDX-License-Identifier: Apache-2.0
"""Representaciones explícitas de un juego, construidas con el motor de referencia.

- `build_tree`: la **forma extensiva** (el árbol): nodos de azar con la probabilidad exacta de
  cada resultado, nodos de decisión agrupados en conjuntos de información y terminales con los
  pagos. Es la base de la forma normal, la forma de secuencias, CFR, la mejor respuesta y la
  exportación a Gambit.
- `state_graph`: el **grafo de estados**: los estados distintos del juego, identificados por su
  huella (`State.digest`), con las jugadas entre ellos. Si no tiene ciclos es un DAG y cuenta
  posiciones y partidas sin recorrer el árbol entero (tres en raya: 5.478 posiciones y 255.168
  partidas); también sirve para la inducción hacia atrás.

Los conjuntos de información son los del motor (`State.information_state`): dos nodos de un
asiento están en el mismo si lo que ese asiento ha observado desde el principio (vistas y eventos
de cada paso) es idéntico, lo que da recuerdo perfecto. Aquí la clave se calcula de forma
incremental (el resumen SHA-256 del padre, continuado con la observación del hijo): el mismo
resultado que el motor sin su coste cuadrático. En los nodos simultáneos los asientos eligen uno
tras otro, por orden de asiento: los envíos son ocultos, así que quien elige después no sabe qué
eligieron los demás y el juego es el mismo.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

from gamehub.console.render import is_hidden, value_text
from gamehub.engine.game import Game
from gamehub.engine.state import Action, State, Status
from gamehub.engine.values import to_json
from gamehub.ir.hashing import canonical_json

#: Nodos como máximo, por defecto, al construir un árbol o un grafo de estados.
MAX_NODES = 1_000_000


class TreeError(Exception):
    """No se puede construir la representación pedida."""


class TooLarge(TreeError):
    def __init__(self, what: str, limit: int) -> None:
        super().__init__(f"{what}: más de {limit:,} nodos (sube el límite o usa otro método)")
        self.limit = limit


def initial_state(
    game: Game | State, num_players: int | None = None, params: dict[str, Any] | None = None
) -> State:
    """El estado desde el que se analiza: el inicial del juego o uno dado."""
    return game if isinstance(game, State) else game.new_state(num_players, params)


def game_title(game: Game | State) -> str:
    return game.title if isinstance(game, Game) else game.game.ir["game"]["id"]


# --- Etiquetas -----------------------------------------------------------------------------------


def action_labels(actions: Sequence[Action]) -> list[str]:
    """Etiquetas cortas de las acciones de un nodo. Si todas se llaman igual y tienen un único
    argumento (`choose(Cooperate)`, `choose(Defect)`), basta con el argumento."""

    def args(a: Action) -> list[str]:
        return [value_text(to_json(v)) for _, v in a.args]

    if actions and len({a.name for a in actions}) == 1 and all(len(a.args) == 1 for a in actions):
        return [args(a)[0] for a in actions]
    return [f"{a.name}({', '.join(args(a))})" if a.args else a.name for a in actions]


def chance_label(child: State, outcome: Sequence[int]) -> str:
    """Etiqueta de un resultado de azar: lo que se ve en sus eventos (cartas repartidas, valores
    revelados) o, si no hay nada que mostrar, los sorteos."""
    parts: list[str] = []
    for e in child.events(None):
        kind = e.get("type")
        if kind == "move":
            to = e["to"]
            where = to["var"] + (f"[{to['seat']}]" if "seat" in to else "")
            parts.append(f"{where}={' '.join(value_text(x) for x in e['items'])}")
        elif kind == "reveal":
            parts.append(value_text(e["value"]))
        elif kind == "emit":
            parts.append(e["name"])
    return ", ".join(parts) if parts else "·".join(str(d) for d in outcome) or "∅"


def compact(v: Any) -> str:
    """Un valor de una vista en texto corto: `?` lo oculto, las zonas como sus objetos."""
    if is_hidden(v):
        return "?"
    if v is None:
        return "–"
    if isinstance(v, bool):
        return "sí" if v else "no"
    if isinstance(v, list):
        return "[" + ", ".join(compact(x) for x in v) + "]"
    if isinstance(v, dict):
        if "items" in v and set(v) <= {"size", "items"}:
            items = [compact(x) for x in v["items"]]
            items += ["?"] * (int(v.get("size", len(items))) - len(items))
            return " ".join(items) if items else "∅"
        if set(v) == {"size"}:
            return f"?×{v['size']}"
        return "/".join(compact(x) for x in v.values())
    return str(v)


def merged_outcomes(state: State, limit: int = 100_000) -> list[tuple[State, str, Fraction]]:
    """Los resultados del punto de azar, juntando (y sumando sus probabilidades) los que llevan
    al mismo estado con los mismos eventos: barajar J J Q Q K K da 720 sorteos pero solo 90
    órdenes distintos."""
    groups: dict[tuple[str, str], list[Any]] = {}
    for outcome, p in state.chance_outcomes(limit):
        child = state.apply_chance(outcome)
        key = (child.digest(), canonical_json(child.events(None)))
        group = groups.get(key)
        if group is None:
            groups[key] = [child, chance_label(child, outcome), p]
        else:
            group[2] += p
    return [(child, label, p) for child, label, p in groups.values()]


# --- Forma extensiva -----------------------------------------------------------------------------

_Frame = tuple[
    State, int, str, "Fraction | None", "list[Any] | None", tuple[Any, ...], Fraction, int
]


@dataclass(slots=True)
class Node:
    kind: str  # "chance" | "decision" | "terminal"
    parent: int
    depth: int
    player: int = -1
    infoset: int = -1
    children: list[int] = field(default_factory=list)
    #: Etiqueta de cada hijo (acción o resultado de azar).
    labels: list[str] = field(default_factory=list)
    #: Probabilidad de cada hijo (solo en los nodos de azar).
    probs: list[Fraction] = field(default_factory=list)
    payoffs: tuple[Fraction, ...] = ()
    #: Probabilidad de que el azar lleve hasta aquí.
    chance_reach: Fraction = Fraction(1)


@dataclass(slots=True)
class InfoSet:
    id: int
    player: int
    key: str
    actions: list[Action]
    labels: list[str]
    nodes: list[int]
    #: (conjunto, índice de la acción) de la decisión anterior del mismo asiento en cualquier
    #: camino hasta aquí (es la misma en todos: recuerdo perfecto); None si es la primera.
    parent: tuple[int, int] | None
    #: Lo que el asiento ve en este conjunto (solo las variables que cambian entre sus conjuntos).
    description: str = ""


@dataclass
class GameTree:
    title: str
    num_players: int
    nodes: list[Node]
    infosets: list[InfoSet]
    #: True si cada conjunto de información tiene un solo nodo.
    perfect_information: bool

    @property
    def root(self) -> Node:
        return self.nodes[0]

    def terminals(self) -> list[int]:
        return [i for i, n in enumerate(self.nodes) if n.kind == "terminal"]

    def infosets_of(self, player: int) -> list[InfoSet]:
        return [s for s in self.infosets if s.player == player]

    def sequences(self, index: int) -> list[tuple[int, int] | None]:
        """La última (conjunto, acción) de cada asiento en el camino hasta el nodo `index`."""
        last: list[tuple[int, int] | None] = [None] * self.num_players
        found = [False] * self.num_players
        child, i = index, self.nodes[index].parent
        while i >= 0 and not all(found):
            node = self.nodes[i]
            if node.kind == "decision" and not found[node.player]:
                last[node.player] = (node.infoset, node.children.index(child))
                found[node.player] = True
            child, i = i, node.parent
        return last

    def counts(self) -> dict[str, int]:
        kinds = [n.kind for n in self.nodes]
        return {
            "nodes": len(self.nodes),
            "terminals": kinds.count("terminal"),
            "chance": kinds.count("chance"),
            "decision": kinds.count("decision"),
            "infosets": len(self.infosets),
        }

    def to_json(self, max_nodes: int = 2000) -> dict[str, Any]:
        nodes = []
        for i, n in enumerate(self.nodes[:max_nodes]):
            item: dict[str, Any] = {"id": i, "kind": n.kind, "parent": n.parent}
            item["children"] = n.children
            item["labels"] = n.labels
            if n.kind == "chance":
                item["probs"] = [str(p) for p in n.probs]
            elif n.kind == "decision":
                item["player"] = n.player
                item["infoset"] = n.infoset
            else:
                item["payoffs"] = [str(p) for p in n.payoffs]
            nodes.append(item)
        return {
            "title": self.title,
            "players": self.num_players,
            "counts": self.counts(),
            "truncated": len(self.nodes) > max_nodes,
            "nodes": nodes,
            "infosets": [
                {
                    "id": s.id,
                    "player": s.player,
                    "actions": s.labels,
                    "nodes": len(s.nodes),
                    "description": s.description,
                }
                for s in self.infosets
            ],
        }

    def _repr_html_(self) -> str:
        from gamehub.analysis.widgets import tree_html

        return tree_html(self)


def build_tree(
    game: Game | State,
    *,
    num_players: int | None = None,
    params: dict[str, Any] | None = None,
    max_nodes: int = MAX_NODES,
    infosets: bool | None = None,
    chance_limit: int = 100_000,
    deadline: float | None = None,
) -> GameTree:
    """La forma extensiva del juego desde su estado inicial (o desde el estado dado).

    `infosets`: calcular los conjuntos de información con las observaciones de cada asiento
    (`None` = solo si la clasificación estática dice que hay información imperfecta; si no, cada
    nodo de decisión es su propio conjunto). `chance_limit`: resultados de azar como máximo en
    cada punto (si no, `NotEnumerable`); `deadline`: instante (`time.monotonic()`) a partir del
    cual se abandona con `TooLarge`."""
    root = initial_state(game, num_players, params)
    n = root.n
    if infosets is None:
        from gamehub.analysis.classify import classify

        infosets = not classify(root.game.ir).perfect_information
    nodes: list[Node] = []
    sets: list[InfoSet] = []
    by_key: dict[tuple[int, str], int] = {}
    witness: dict[int, State] = {}

    def observe(state: State, seat: int) -> bytes:
        observation = {"view": state.view(seat), "events": state.events(seat)}
        return canonical_json(observation).encode("utf-8")

    hashes: list[Any] | None = None
    if infosets:
        hashes = []
        for s in range(n):
            h = hashlib.sha256()
            h.update(observe(root, s))
            hashes.append(h)
    # Pila: (estado, padre, etiqueta, probabilidad, claves, última decisión de cada asiento,
    # probabilidad del azar hasta aquí, profundidad)
    stack: list[_Frame] = [(root, -1, "", None, hashes, (None,) * n, Fraction(1), 0)]
    while stack:
        state, parent, label, prob, keys, last, reach, depth = stack.pop()
        index = len(nodes)
        if index >= max_nodes:
            raise TooLarge("el árbol del juego", max_nodes)
        if deadline is not None and index % 256 == 0 and time.monotonic() > deadline:
            raise TooLarge("el árbol del juego (se acabó el tiempo)", index)
        node = Node(kind="terminal", parent=parent, depth=depth, chance_reach=reach)
        nodes.append(node)
        if parent >= 0:
            up = nodes[parent]
            up.children.append(index)
            up.labels.append(label)
            if prob is not None:
                up.probs.append(prob)
        status = state.status
        children: list[_Frame] = []
        if status is Status.TERMINAL:
            node.payoffs = tuple(Fraction(p) for p in state.payoffs or ())
            continue
        if status is Status.CHANCE:
            node.kind = "chance"
            for child, label, p in merged_outcomes(state, chance_limit):
                children.append(
                    (
                        child,
                        index,
                        label,
                        p,
                        _extend(keys, child, observe),
                        last,
                        reach * p,
                        depth + 1,
                    )
                )
        else:
            node.kind = "decision"
            seat = state.active_seats[0]
            node.player = seat
            actions = state.legal_actions(seat)
            key = keys[seat].hexdigest() if keys is not None else f"node:{index}"
            sid = by_key.get((seat, key))
            if sid is None:
                sid = len(sets)
                by_key[(seat, key)] = sid
                sets.append(
                    InfoSet(sid, seat, key, actions, action_labels(actions), [], last[seat])
                )
                witness[sid] = state
            info = sets[sid]
            if info.actions != actions:
                raise TreeError(
                    f"el asiento {seat} tiene acciones legales distintas en estados que no puede "
                    f"distinguir (nodo {state.node}): las acciones revelan información oculta"
                )
            if info.parent != last[seat]:
                raise TreeError(f"el asiento {seat} olvida lo que hizo (nodo {state.node})")
            info.nodes.append(index)
            node.infoset = sid
            for k, action in enumerate(actions):
                child = state.apply_action(seat, action)
                mine = (*last[:seat], (sid, k), *last[seat + 1 :])
                children.append(
                    (
                        child,
                        index,
                        info.labels[k],
                        None,
                        _extend(keys, child, observe),
                        mine,
                        reach,
                        depth + 1,
                    )
                )
        stack.extend(reversed(children))
    _describe(sets, witness)
    return GameTree(
        title=game_title(game),
        num_players=n,
        nodes=nodes,
        infosets=sets,
        perfect_information=all(len(s.nodes) == 1 for s in sets),
    )


def _extend(keys: list[Any] | None, child: State, observe: Any) -> list[Any] | None:
    if keys is None:
        return None
    out = []
    for seat, h in enumerate(keys):
        h = h.copy()
        h.update(observe(child, seat))
        out.append(h)
    return out


def _describe(sets: list[InfoSet], witness: dict[int, State]) -> None:
    """Describe cada conjunto con la vista de su asiento, quitando las variables que valen lo
    mismo en todos los conjuntos de ese asiento (no distinguen nada)."""
    views = {sid: witness[sid].view(sets[sid].player)["state"] for sid in witness}
    for player in {s.player for s in sets}:
        mine = [s for s in sets if s.player == player]
        names = list(views[mine[0].id]) if mine else []
        varying = [v for v in names if len({canonical_json(views[s.id][v]) for s in mine}) > 1]
        seen: dict[str, int] = {}
        for s in mine:
            text = " · ".join(f"{v}={compact(views[s.id][v])}" for v in varying)
            seen[text] = seen.get(text, 0) + 1
            s.description = text
        for s in mine:
            if seen[s.description] > 1:
                s.description = f"{s.description} (#{s.id})".strip()


# --- Grafo de estados ----------------------------------------------------------------------------


@dataclass
class StateGraph:
    """Los estados distintos de un juego y las jugadas entre ellos (por huella)."""

    title: str
    num_players: int
    kinds: list[str]
    players: list[int]
    children: list[list[int]]
    labels: list[list[str]]
    probs: list[list[Fraction]]
    payoffs: list[tuple[Fraction, ...]]
    #: Estados en orden de finalización (los hijos antes que los padres, si no hay ciclos).
    order: list[int]
    cyclic: bool
    states: list[State]

    @property
    def positions(self) -> int:
        return len(self.kinds)

    @property
    def terminals(self) -> int:
        return self.kinds.count("terminal")

    def games(self) -> int | None:
        """Cuántas partidas distintas hay (caminos de la raíz a un final; cada resultado del azar
        cuenta como un camino). None si hay ciclos."""
        if self.cyclic:
            return None
        paths = [0] * len(self.kinds)
        for i in self.order:
            paths[i] = 1 if self.kinds[i] == "terminal" else sum(paths[c] for c in self.children[i])
        return paths[0]


def state_graph(
    game: Game | State,
    *,
    num_players: int | None = None,
    params: dict[str, Any] | None = None,
    max_nodes: int = MAX_NODES,
    chance_limit: int = 100_000,
    deadline: float | None = None,
) -> StateGraph:
    """El grafo de estados alcanzables desde el estado inicial (o desde el dado). En los nodos
    simultáneos actúa primero el asiento más bajo, como en `build_tree` (y `chance_limit` y
    `deadline` significan lo mismo)."""
    root = initial_state(game, num_players, params)
    index: dict[str, int] = {}
    kinds: list[str] = []
    players: list[int] = []
    children: list[list[int]] = []
    labels: list[list[str]] = []
    probs: list[list[Fraction]] = []
    payoffs: list[tuple[Fraction, ...]] = []
    states: list[State] = []
    order: list[int] = []
    cyclic = False

    def add(state: State, digest: str) -> int:
        if len(kinds) >= max_nodes:
            raise TooLarge("el grafo de estados", max_nodes)
        if deadline is not None and len(kinds) % 256 == 0 and time.monotonic() > deadline:
            raise TooLarge("el grafo de estados (se acabó el tiempo)", len(kinds))
        i = len(kinds)
        index[digest] = i
        status = state.status
        kinds.append(status.value)
        players.append(state.active_seats[0] if status is Status.DECISION else -1)
        children.append([])
        labels.append([])
        probs.append([])
        payoffs.append(tuple(Fraction(p) for p in state.payoffs or ()))
        states.append(_detach(state))
        return i

    def expand(i: int) -> list[tuple[State, str, Fraction | None]]:
        state = states[i]
        if kinds[i] == "chance":
            return [
                (child := state.apply_chance(o), chance_label(child, o), p)
                for o, p in state.chance_outcomes(chance_limit)
            ]
        if kinds[i] == "decision":
            seat = players[i]
            actions = state.legal_actions(seat)
            names = action_labels(actions)
            return [(state.apply_action(seat, a), names[k], None) for k, a in enumerate(actions)]
        return []

    on_stack: set[int] = set()
    add(root, root.digest())
    stack: list[tuple[int, list[tuple[State, str, Fraction | None]], int]] = [(0, expand(0), 0)]
    on_stack.add(0)
    while stack:
        i, pending, k = stack[-1]
        if k == len(pending):
            stack.pop()
            on_stack.discard(i)
            order.append(i)
            continue
        stack[-1] = (i, pending, k + 1)
        child, label, p = pending[k]
        digest = child.digest()
        j = index.get(digest)
        if j is None:
            j = add(child, digest)
            stack.append((j, expand(j), 0))
            on_stack.add(j)
        elif j in on_stack:
            cyclic = True
        children[i].append(j)
        labels[i].append(label)
        if p is not None:
            probs[i].append(p)
    return StateGraph(
        title=game_title(game),
        num_players=root.n,
        kinds=kinds,
        players=players,
        children=children,
        labels=labels,
        probs=probs,
        payoffs=payoffs,
        order=order,
        cyclic=cyclic,
        states=states,
    )


def _detach(state: State) -> State:
    """El mismo estado sin el enlace a su padre (el grafo no necesita la historia y así no la
    retiene en memoria)."""
    return State(
        state.game,
        state.n,
        state.params,
        state.store,
        state.node,
        state.pending,
        state.payoffs,
        None,
        state.step,
        state.memo,
    )
