# SPDX-License-Identifier: Apache-2.0
"""Combinadores de juegos: `game Nuevo = repeat(Base, rounds: 10, payoff: sum)` y
`game Nuevo = best_of(Base, rounds: 3)`. Transforman la IR de la base:

    start -> Ronda
    [auto|chance Preparación { variables de la base a su valor inicial; preparación de la base }]
    …los nodos de la base, con cada terminal convertido en un nodo automático que apunta su
       resultado y salta a Siguiente…
    auto Siguiente { -> Fin when <se acabó>; -> Ronda { ronda += 1 } }
    terminal Fin { payoff: … }

- `repeat`: `rounds` rondas; pago final = suma (`payoff: sum`, por defecto) o media
  (`payoff: mean`) de los pagos de cada ronda.
- `best_of`: como mucho `rounds` rondas; gana una ronda quien tiene el pago más alto (sin
  empate) y la partida, quien antes gane más de la mitad, o quien más haya ganado al final. El
  ganador cobra `num_players - 1` y los demás pagan 1 (suma cero); si hay empate, todos 0.

El número de rondas es un parámetro nuevo del juego (`rounds`, con el valor dado por defecto).
Los nombres nuevos (parámetros, variables y nodos) se eligen para no chocar con los de la base.
"""

from __future__ import annotations

import copy
import itertools
from collections.abc import Iterator
from typing import Any

from gamehub.analysis import irwalk

COMBINATORS = ("repeat", "best_of")


def apply(
    combinator: str, base: dict[str, Any], game_id: str, rounds: int, payoff: str = "sum"
) -> dict[str, Any]:
    return _Builder(base, game_id).build(combinator, rounds, payoff)


class _Builder:
    def __init__(self, base: dict[str, Any], game_id: str) -> None:
        self.ir = copy.deepcopy(base)
        self.ir["game"] = {"id": game_id, "version": "0.1.0"}
        self.globals = {p["name"] for p in self.ir.get("params", [])}
        self.globals |= {v["name"] for v in self.ir.get("state", [])}
        self.globals |= {f["name"] for f in self.ir.get("functions", [])}
        self.globals |= {t["name"] for t in self.ir.get("types", [])}
        self.globals |= {"num_players"}
        self.node_ids = {node["id"] for node, _ in irwalk.all_nodes(self.ir)}

    def fresh(self, base: str, taken: set[str]) -> str:
        for i in itertools.chain([""], itertools.count(2)):
            name = f"{base}{i}"
            if name not in taken:
                taken.add(name)
                return name
        raise AssertionError

    def retitle(self, combinator: str, rounds: int, payoff: str) -> None:
        """Título «(N rondas)» / «(al mejor de N)» y una descripción propia."""
        meta = self.ir.setdefault("meta", {})
        title = meta.get("title", self.ir["game"]["id"])
        titles = title if isinstance(title, dict) else {"es": title}
        how = {
            "repeat": {
                "es": (f" ({rounds} rondas)", "se suman los pagos de cada ronda")
                if payoff == "sum"
                else (f" ({rounds} rondas)", "se paga la media de los pagos de cada ronda"),
                "en": (f" ({rounds} rounds)", "round payoffs are added up")
                if payoff == "sum"
                else (f" ({rounds} rounds)", "the mean round payoff is paid"),
            },
            "best_of": {
                "es": (f" (al mejor de {rounds})", "gana quien gana más rondas"),
                "en": (f" (best of {rounds})", "whoever wins most rounds wins"),
            },
        }[combinator]
        meta["title"] = {lang: text + how.get(lang, how["es"])[0] for lang, text in titles.items()}
        meta["description"] = {
            lang: f"{text}{how.get(lang, how['es'])[0]}: {how.get(lang, how['es'])[1]}."
            for lang, text in titles.items()
        }
        # La etiqueta deja que las herramientas lo reconozcan (p. ej. el asesor de viabilidad
        # propone un torneo de Axelrod para los juegos repetidos).
        tag = "repeated" if combinator == "repeat" else "best-of"
        tags = list(meta.get("tags", []))
        if tag not in tags:
            meta["tags"] = [*tags, tag]

    def build(self, combinator: str, rounds: int, payoff: str) -> dict[str, Any]:
        ir = self.ir
        self.retitle(combinator, rounds, payoff)
        flow = ir["flow"]
        base_vars = list(ir.get("state", []))
        g = self.globals
        rounds_param = self.fresh("rounds", g)
        round_var = self.fresh("round", g)
        score_var = self.fresh("totals" if combinator == "repeat" else "wins", g)
        # Locales: tampoco pueden llamarse como un global (el texto descompilado no compilaría).
        self.result, self.seat, self.x = (self.fresh(n, g) for n in ("result", "s", "x"))
        self.cell, self.owner = self.fresh("cell", g), self.fresh("o", g)
        phase = self.fresh("Round", self.node_ids)
        setup_node = self.fresh("Setup", self.node_ids)
        next_node = self.fresh("Next", self.node_ids)
        end_node = self.fresh("End", self.node_ids)

        ir.setdefault("params", []).append(
            {"name": rounds_param, "type": "Int", "default": ["const", rounds]}
        )
        ir.setdefault("constraints", []).append(
            {
                "expr": ["ge", ["param", rounds_param], ["const", 1]],
                "message": {"es": "hace falta al menos una ronda", "en": "at least one round"},
            }
        )
        score_type = ["per_player", "Real" if combinator == "repeat" else "Int"]
        ir["state"] = [
            *base_vars,
            {"name": round_var, "type": "Int", "init": ["const", 1]},
            {"name": score_var, "type": score_type, "init": ["const", 0]},
        ]
        for node, _ in irwalk.all_nodes(ir):
            if node["kind"] == "terminal":
                node["kind"] = "auto"
                node["effects"] = self.tally(combinator, node.pop("payoff"), score_var)
                node.pop("rank", None)
                node["transitions"] = [{"to": next_node}]

        reset = list(self.reset(base_vars))
        setup = flow.pop("setup", [])
        inner = list(flow["nodes"])
        first = flow["start"]
        if reset or setup:
            random = any(irwalk.is_random(s) for s in irwalk.walk_block(setup))
            inner.insert(
                0,
                {
                    "id": setup_node,
                    "kind": "chance" if random else "auto",
                    "effects": [*reset, *setup],
                    "transitions": [{"to": first}],
                },
            )
            first = setup_node
        score_at = ["index", ["var", score_var], ["local", self.seat]]
        finished: Any = ["ge", ["var", round_var], ["param", rounds_param]]
        if combinator == "best_of":
            majority = ["gt", ["mul", ["const", 2], score_at], ["param", rounds_param]]
            finished = ["or", finished, ["any", self.seat, ["seats"], majority]]
        next_round = ["assign", ["var", round_var], ["add", ["var", round_var], ["const", 1]]]
        flow["start"] = phase
        flow["nodes"] = [
            {"id": phase, "kind": "phase", "start": first, "nodes": inner},
            {
                "id": next_node,
                "kind": "auto",
                "transitions": [
                    {"to": end_node, "when": finished},
                    {"to": phase, "effects": [next_round]},
                ],
            },
            {
                "id": end_node,
                "kind": "terminal",
                "payoff": self.final(combinator, payoff, score_var, rounds_param),
            },
        ]
        return ir

    def tally(self, combinator: str, payoff: Any, score: str) -> list[Any]:
        """Efectos que sustituyen a un terminal: apuntar el resultado de la ronda."""
        result, seat, x = ["local", self.result], ["local", self.seat], ["local", self.x]
        effects: list[Any] = [["let", self.result, payoff]]
        if combinator == "repeat":
            at = ["index", ["var", score], seat]
            gained = ["add", at, ["index", result, seat]]
            effects.append(["for", self.seat, ["seats"], [["assign", at, gained]]])
            return effects
        best = ["max_of", self.x, result, x]
        unique = ["eq", ["count", self.x, result, ["eq", x, best]], ["const", 1]]
        winner = ["argmax", self.seat, ["seats"], ["index", result, seat]]
        won = ["index", ["var", score], winner]
        effects.append(["if", unique, [["assign", won, ["add", won, ["const", 1]]]]])
        return effects

    def final(self, combinator: str, payoff: str, score: str, rounds: str) -> Any:
        seat, x = ["local", self.seat], ["local", self.x]
        score_at = ["index", ["var", score], seat]
        if combinator == "repeat":
            value = score_at if payoff == "sum" else ["div", score_at, ["param", rounds]]
            return ["map", self.seat, ["seats"], value]
        best = ["max_of", self.x, ["var", score], x]
        unique = ["eq", ["count", self.x, ["var", score], ["eq", x, best]], ["const", 1]]
        leader = ["argmax", self.seat, ["seats"], score_at]
        share = ["sub", ["param", "num_players"], ["const", 1]]
        wins = ["map", self.seat, ["seats"], ["if", ["eq", seat, leader], share, ["const", -1]]]
        return ["if", unique, wins, ["fill", ["const", 0]]]

    def reset(self, variables: list[dict[str, Any]]) -> Iterator[Any]:
        """Sentencias que devuelven cada variable a su valor inicial."""
        for var in variables:
            name, t, init = var["name"], var["type"], var["init"]
            target = ["var", name]
            if _kind(t) == "grid":
                cell = ["local", self.cell]
                rows = (
                    _kind(t[3]) not in ("list", "tuple")
                    and isinstance(init, list)
                    and init[0] == "list"
                    and len(init) > 1
                    and all(isinstance(r, list) and r[0] == "list" for r in init[1:])
                )
                row = ["index", cell, ["const", 0]]
                column = ["index", cell, ["const", 1]]
                value = ["index", ["index", init, row], column] if rows else init
                assign = ["assign", ["index", target, cell], value]
                yield ["for", self.cell, ["cells", target], [assign]]
            elif _kind(t) == "per_player":
                owned = _replace_owner(init, self.owner)
                yield ["assign", target, ["map", self.owner, ["seats"], owned]]
            else:
                yield ["assign", target, init]


def _kind(t: Any) -> str:
    return t[0] if isinstance(t, list) else t


def _replace_owner(e: Any, local: str) -> Any:
    if isinstance(e, list):
        if e == ["owner"]:
            return ["local", local]
        return [_replace_owner(x, local) for x in e]
    if isinstance(e, dict):
        return {k: _replace_owner(v, local) for k, v in e.items()}
    return e
