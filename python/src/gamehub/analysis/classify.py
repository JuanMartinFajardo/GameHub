# SPDX-License-Identifier: Apache-2.0
"""Clasificación estática de un juego a partir de su IR: jugadores, azar, información,
simultaneidad y suma cero (cuando se puede asegurar sin jugar)."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from gamehub.analysis import irwalk


@dataclass(frozen=True)
class Classification:
    min_players: int
    max_players: int
    chance: bool
    perfect_information: bool
    simultaneous: bool
    #: True si todos los finales suman cero; False si alguno seguro que no; None si no se sabe.
    zero_sum: bool | None

    def labels(self) -> list[str]:
        lo, hi = self.min_players, self.max_players
        out = [f"{lo} jugador{'es' if lo != 1 else ''}" if lo == hi else f"{lo}–{hi} jugadores"]
        out.append("azar" if self.chance else "determinista")
        out.append("información perfecta" if self.perfect_information else "información imperfecta")
        out.append("jugadas simultáneas" if self.simultaneous else "por turnos")
        if self.zero_sum is not None:
            out.append("suma cero" if self.zero_sum else "suma no nula")
        return out

    def to_json(self) -> dict[str, Any]:
        return {
            "players": {"min": self.min_players, "max": self.max_players},
            "chance": self.chance,
            "perfect_information": self.perfect_information,
            "simultaneous": self.simultaneous,
            "zero_sum": self.zero_sum,
        }


def classify(ir: dict[str, Any]) -> Classification:
    nodes = [node for node, _ in irwalk.all_nodes(ir)]
    setup = ir["flow"].get("setup", [])
    chance = any(n["kind"] == "chance" for n in nodes) or any(
        irwalk.is_random(s) for s in irwalk.walk_block(setup)
    )
    simultaneous = any(
        n["kind"] == "simultaneous" or (n["kind"] == "window" and n.get("mode") == "collect")
        for n in nodes
    )
    hidden_state = any(v.get("visibility") not in (None, "all") for v in ir.get("state", []))
    hidden_args = any(
        p.get("visibility") not in (None, "all")
        for n in nodes
        for a in n.get("actions", [])
        for p in a.get("params", [])
    )
    private_events = any(
        stmt[0] == "emit" and len(stmt) > 3 and stmt[3] not in (None, "all")
        for n in nodes
        for block in irwalk.node_blocks(n)
        for stmt in irwalk.walk_block(block)
    )
    players = ir["players"]
    sums = [
        _payoff_sum(n["payoff"], players["min"], players["max"])
        for n in nodes
        if n["kind"] == "terminal" and "payoff" in n
    ]
    if sums and all(s == 0 for s in sums):
        zero_sum: bool | None = True
    elif any(s is not None and s != 0 for s in sums):
        zero_sum = False
    else:
        zero_sum = None
    return Classification(
        min_players=players["min"],
        max_players=players["max"],
        chance=chance,
        perfect_information=not (hidden_state or hidden_args or private_events or simultaneous),
        simultaneous=simultaneous,
        zero_sum=zero_sum,
    )


def _payoff_sum(e: Any, lo: int, hi: int) -> Fraction | None:
    """Suma de un vector de pagos si se puede saber sin jugar (si no, None)."""
    op = e[0]
    match op:
        case "let":
            return _payoff_sum(e[3], lo, hi)
        case "if":
            a, b = _payoff_sum(e[2], lo, hi), _payoff_sum(e[3], lo, hi)
            return a if a is not None and a == b else None
        case "case":
            sums = [_payoff_sum(result, lo, hi) for _, result in e[1]]
            sums.append(_payoff_sum(e[2], lo, hi))
            first = sums[0]
            return first if first is not None and all(s == first for s in sums) else None
        case "list":
            values = [_number(x) for x in e[1:]]
            return None if any(v is None for v in values) else sum(values, Fraction(0))  # type: ignore[arg-type]
        case "fill":
            value = _number(e[1])
            return Fraction(0) if value == 0 else None
        case "win_loss":
            win, lose = e[2], e[3]
            if lo == hi == 2 and (win == ["neg", lose] or lose == ["neg", win]):
                return Fraction(0)
            a, b = _number(win), _number(lose)
            if a is not None and b is not None and lo == hi:
                return a + (lo - 1) * b
    return None


def _number(e: Any) -> Fraction | None:
    if isinstance(e, list) and e:
        if e[0] == "const" and isinstance(e[1], int) and not isinstance(e[1], bool):
            return Fraction(e[1])
        if e[0] == "rat":
            return Fraction(e[1], e[2])
        if e[0] == "neg":
            inner = _number(e[1])
            return -inner if inner is not None else None
    return None
