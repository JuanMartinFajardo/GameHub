# SPDX-License-Identifier: Apache-2.0
"""Forma normal (estratégica): cada jugador elige una estrategia pura y cobra el pago esperado.

- A mano: `NormalForm.from_matrices(A, B)` (dos jugadores) o `NormalForm.from_function(...)`.
- Desde un juego: `normal_form(game)` construye la forma extensiva y enumera las estrategias puras
  **reducidas** (planes de acción): cada estrategia elige una acción solo en los conjuntos de
  información que ella misma deja alcanzar, así que dos estrategias que se diferencian únicamente
  en lo que harían en situaciones imposibles cuentan como una. En un juego simultáneo de una sola
  jugada, las estrategias son las acciones. Los pagos son exactos (racionales), con el azar
  promediado.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from gamehub.analysis.tree import GameTree, TooLarge, build_tree, initial_state
from gamehub.engine.game import Game
from gamehub.engine.state import State

Profile = tuple[int, ...]
#: Estrategia mixta: una probabilidad por estrategia pura.
Mixed = tuple[Any, ...]
#: Perfil mixto: una estrategia mixta por jugador.
MixedProfile = tuple[Mixed, ...]

#: Estrategias reducidas como máximo por jugador, y perfiles en total, por defecto.
MAX_STRATEGIES = 10_000
MAX_PROFILES = 1_000_000


@dataclass
class NormalForm:
    title: str
    players: tuple[str, ...]
    strategies: tuple[tuple[str, ...], ...]
    #: Pagos de cada perfil de estrategias puras (todos los perfiles).
    payoffs: dict[Profile, tuple[Fraction, ...]]
    #: Si viene de un árbol: el plan de cada estrategia ({conjunto de información: acción}).
    plans: tuple[tuple[dict[int, int], ...], ...] | None = None
    #: Si viene de un árbol: descripción de cada conjunto de información citado en los planes.
    infosets: dict[int, str] | None = None

    # --- construcción ---------------------------------------------------------------------------

    @staticmethod
    def from_matrices(
        a: Sequence[Sequence[Any]],
        b: Sequence[Sequence[Any]] | None = None,
        *,
        rows: Sequence[str] | None = None,
        columns: Sequence[str] | None = None,
        title: str = "",
    ) -> NormalForm:
        """Bimatriz: `a[i][j]` es el pago del jugador de filas y `b[i][j]` el del de columnas
        (si falta `b`, el juego es de suma cero: `b = -a`)."""
        m, n = len(a), len(a[0])
        rows = list(rows or [f"r{i}" for i in range(m)])
        columns = list(columns or [f"c{j}" for j in range(n)])
        payoffs = {
            (i, j): (Fraction(a[i][j]), Fraction(-a[i][j] if b is None else b[i][j]))
            for i in range(m)
            for j in range(n)
        }
        return NormalForm(title, _seat_names(2), (tuple(rows), tuple(columns)), payoffs)

    @staticmethod
    def from_function(
        strategies: Sequence[Sequence[str]],
        payoff: Callable[[Profile], Sequence[Any]],
        *,
        title: str = "",
    ) -> NormalForm:
        shape = [len(s) for s in strategies]
        payoffs = {
            p: tuple(Fraction(x) for x in payoff(p))
            for p in itertools.product(*(range(k) for k in shape))
        }
        return NormalForm(
            title, _seat_names(len(shape)), tuple(tuple(s) for s in strategies), payoffs
        )

    # --- consulta -------------------------------------------------------------------------------

    @property
    def num_players(self) -> int:
        return len(self.strategies)

    @property
    def shape(self) -> tuple[int, ...]:
        return tuple(len(s) for s in self.strategies)

    def profiles(self) -> Iterator[Profile]:
        return itertools.product(*(range(k) for k in self.shape))

    def payoff(self, profile: Sequence[int]) -> tuple[Fraction, ...]:
        return self.payoffs[tuple(profile)]

    def matrix(self, player: int) -> list[list[Fraction]]:
        """Matriz de pagos de `player` (solo con dos jugadores: filas = jugador 0)."""
        if self.num_players != 2:
            raise ValueError("matrix() es para juegos de dos jugadores")
        m, n = self.shape
        return [[self.payoffs[(i, j)][player] for j in range(n)] for i in range(m)]

    def deviate(self, profile: Sequence[int], player: int, strategy: int) -> Profile:
        out = list(profile)
        out[player] = strategy
        return tuple(out)

    def expected(self, profile: MixedProfile) -> tuple[Any, ...]:
        """Pagos esperados de un perfil mixto."""
        total = [Fraction(0)] * self.num_players
        for p, weight in self._weighted(profile):
            for k, u in enumerate(self.payoffs[p]):
                total[k] += weight * u
        return tuple(total)

    def strategy_values(self, player: int, profile: MixedProfile) -> list[Any]:
        """Pago esperado de cada estrategia pura de `player` contra las mixtas de los demás."""
        others = [profile[k] if k != player else None for k in range(self.num_players)]
        values = []
        for s in range(self.shape[player]):
            pure = tuple(1 if t == s else 0 for t in range(self.shape[player]))
            mixed = tuple(pure if o is None else o for o in others)
            values.append(self.expected(mixed)[player])
        return values

    def _weighted(self, profile: MixedProfile) -> Iterator[tuple[Profile, Any]]:
        supports = [[(s, q) for s, q in enumerate(mix) if q] for mix in profile]
        for combo in itertools.product(*supports):
            weight: Any = 1
            for _, q in combo:
                weight *= q
            yield tuple(s for s, _ in combo), weight

    def is_constant_sum(self) -> bool:
        return len({sum(u) for u in self.payoffs.values()}) <= 1

    def restrict(self, keep: Sequence[Sequence[int]]) -> NormalForm:
        """El juego con solo las estrategias de `keep` (en ese orden) de cada jugador."""
        payoffs = {
            p: self.payoffs[tuple(keep[k][s] for k, s in enumerate(p))]
            for p in itertools.product(*(range(len(k)) for k in keep))
        }
        plans = (
            tuple(tuple(self.plans[k][s] for s in ks) for k, ks in enumerate(keep))
            if self.plans is not None
            else None
        )
        return NormalForm(
            self.title,
            self.players,
            tuple(tuple(self.strategies[k][s] for s in ks) for k, ks in enumerate(keep)),
            payoffs,
            plans,
            self.infosets,
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "players": list(self.players),
            "strategies": [list(s) for s in self.strategies],
            "payoffs": [
                {"profile": list(p), "payoffs": [str(u) for u in self.payoffs[p]]}
                for p in self.profiles()
            ],
            "infosets": {str(k): v for k, v in (self.infosets or {}).items()},
        }

    def _repr_html_(self) -> str:
        from gamehub.analysis.widgets import normal_form_html

        return normal_form_html(self)


def _seat_names(n: int) -> tuple[str, ...]:
    return tuple(f"Asiento {i}" for i in range(n))


# --- Desde un juego ------------------------------------------------------------------------------


def normal_form(
    game: Game | State | GameTree,
    *,
    num_players: int | None = None,
    params: dict[str, Any] | None = None,
    max_strategies: int = MAX_STRATEGIES,
    max_profiles: int = MAX_PROFILES,
) -> NormalForm:
    """La forma normal reducida del juego (ver el docstring del módulo)."""
    if isinstance(game, GameTree):
        tree = game
    else:
        tree = build_tree(initial_state(game, num_players, params), infosets=True)
        if isinstance(game, Game):
            tree.title = game.title
    return from_tree(tree, max_strategies=max_strategies, max_profiles=max_profiles)


def from_tree(
    tree: GameTree, *, max_strategies: int = MAX_STRATEGIES, max_profiles: int = MAX_PROFILES
) -> NormalForm:
    n = tree.num_players
    plans = [_plans(tree, player, max_strategies) for player in range(n)]
    total = 1
    for p in plans:
        total *= len(p)
    if total > max_profiles:
        raise TooLarge(f"la forma normal ({total:,} perfiles)", max_profiles)
    # Cada final, con la probabilidad del azar, sus pagos y la última decisión de cada asiento.
    terminals = tree.terminals()
    masks: list[list[int]] = []
    for player in range(n):
        by_last: dict[tuple[int, int] | None, int] = {}
        for bit, z in enumerate(terminals):
            key = tree.sequences(z)[player]
            by_last[key] = by_last.get(key, 0) | (1 << bit)
        free = by_last.get(None, 0)
        masks.append(
            [
                free | _or(by_last.get((info, a), 0) for info, a in plan.items())
                for plan in plans[player]
            ]
        )
    weights = [tree.nodes[z].chance_reach for z in terminals]
    values = [tree.nodes[z].payoffs for z in terminals]
    payoffs: dict[Profile, tuple[Fraction, ...]] = {}
    for profile in itertools.product(*(range(len(p)) for p in plans)):
        mask = -1
        for player, s in enumerate(profile):
            mask &= masks[player][s]
        total_payoff = [Fraction(0)] * n
        while mask:
            low = mask & -mask
            z = low.bit_length() - 1
            mask ^= low
            w = weights[z]
            for k, u in enumerate(values[z]):
                total_payoff[k] += w * u
        payoffs[profile] = tuple(total_payoff)
    labels = tuple(
        tuple(_plan_label(tree, player, plan) for plan in plans[player]) for player in range(n)
    )
    cited = {i for player_plans in plans for plan in player_plans for i in plan}
    return NormalForm(
        title=tree.title,
        players=_seat_names(n),
        strategies=labels,
        payoffs=payoffs,
        plans=tuple(tuple(p) for p in plans),
        infosets={i: tree.infosets[i].description for i in sorted(cited)},
    )


def _or(masks: Iterator[int]) -> int:
    out = 0
    for m in masks:
        out |= m
    return out


def _plans(tree: GameTree, player: int, limit: int) -> list[dict[int, int]]:
    """Las estrategias puras reducidas de `player`: los planes que eligen una acción en cada
    conjunto alcanzable con las elecciones anteriores del propio plan."""
    children: dict[tuple[int, int] | None, list[int]] = {}
    for info in tree.infosets_of(player):
        children.setdefault(info.parent, []).append(info.id)

    def plans(seq: tuple[int, int] | None) -> list[dict[int, int]]:
        result: list[dict[int, int]] = [{}]
        for info in children.get(seq, []):
            options = [
                {info: a, **sub}
                for a in range(len(tree.infosets[info].actions))
                for sub in plans((info, a))
            ]
            if len(result) * len(options) > limit:
                raise TooLarge(f"las estrategias reducidas del asiento {player}", limit)
            result = [{**r, **o} for r in result for o in options]
        return result

    return plans(None)


def _plan_label(tree: GameTree, player: int, plan: dict[int, int]) -> str:
    if not plan:
        return "–"
    if len(tree.infosets_of(player)) == 1:
        (info, a), *_ = plan.items()
        return tree.infosets[info].labels[a]
    return " ".join(f"I{info}:{tree.infosets[info].labels[a]}" for info, a in sorted(plan.items()))
