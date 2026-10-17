# SPDX-License-Identifier: Apache-2.0
"""El asesor de viabilidad: antes de lanzar un cálculo, cuánto ocupa el juego y qué se puede
calcular (docs/wiki/game-theory.md §1).

1. La **clasificación** estática de la IR (jugadores, azar, información, simultaneidad, suma).
2. El **tamaño**, con el estimador de Knuth (1975): en cada partida al azar, el producto de los
   factores de ramificación hasta cada profundidad estima cuántos nodos hay a esa profundidad
   (en el azar, el inverso de la probabilidad del resultado sorteado: muestreo por importancia);
   la media sobre muchas partidas es un estimador insesgado del tamaño del árbol. También la
   ramificación media y la duración de las partidas.
3. Si el árbol es pequeño, el **recuento exacto** (posiciones y partidas con el grafo de estados,
   o nodos y conjuntos de información con la forma extensiva).
4. Una **recomendación** con los métodos que tienen sentido para esa clase y ese tamaño.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

from gamehub.analysis.classify import Classification, classify
from gamehub.analysis.tree import (
    TreeError,
    build_tree,
    game_title,
    initial_state,
    merged_outcomes,
    state_graph,
)
from gamehub.engine.errors import EngineError, NotEnumerable, RuleError
from gamehub.engine.game import Game
from gamehub.engine.rng import Pcg32
from gamehub.engine.state import State, Status

#: Hasta este tamaño estimado se intenta el recuento exacto; si no, una sonda con este máximo de
#: nodos (en los juegos de información perfecta, el grafo de estados puede ser mucho menor que el
#: árbol: el Nim 3-5-7 tiene 10⁷ nodos y 384 posiciones).
EXACT_COUNT_LIMIT = 50_000
PROBE_LIMIT = 10_000
PROBE_SECONDS = 5.0
MIN_SAMPLES = 20
#: Resultados de azar como máximo para juntar los equivalentes al muestrear.
MERGE_LIMIT = 5_000
#: Umbrales de la recomendación, en log10 del tamaño (orientativos; docs/wiki/game-theory.md §1).
PYTHON_EXACT = 6.0
CPP_EXACT = 9.0
CPP_CFR_INFOSETS = 10**7


@dataclass(frozen=True)
class Recommendation:
    #: Código estable (lo usan la CLI y el Studio): solve, grundy, normal_form, nash,
    #: sequence_form, cfr, tournament, cpp_exact, cpp_cfr, approximate.
    code: str
    text: str
    #: Fase del roadmap que lo trae, si todavía no está (F8: C++, F9: heurísticas y bots).
    phase: str | None = None


@dataclass
class Feasibility:
    title: str
    classification: Classification
    num_players: int
    samples: int
    #: log10 del tamaño estimado del árbol (nodos) y de sus hojas (partidas distintas).
    tree_log10: float
    leaves_log10: float
    branching: float
    depth_mean: float
    depth_max: int
    truncated: int
    #: Recuentos exactos si el juego es pequeño: positions, games (grafo de estados) o nodes,
    #: infosets (forma extensiva).
    exact: dict[str, int] = field(default_factory=dict)
    recommendations: list[Recommendation] = field(default_factory=list)
    tags: tuple[str, ...] = ()

    @property
    def size_log10(self) -> float:
        """log10 del tamaño que cuenta para recomendar: las posiciones exactas (información
        perfecta), los nodos exactos o, si no se conocen, la estimación del árbol."""
        exact = self.exact.get("positions") or self.exact.get("nodes")
        return math.log10(exact) if exact else self.tree_log10

    def to_json(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "classification": self.classification.to_json(),
            "labels": self.classification.labels(),
            "players": self.num_players,
            "samples": self.samples,
            "tree_log10": round(self.tree_log10, 3),
            "leaves_log10": round(self.leaves_log10, 3),
            "branching": round(self.branching, 3),
            "depth": {"mean": round(self.depth_mean, 2), "max": self.depth_max},
            "truncated": self.truncated,
            "exact": self.exact,
            "recommendations": [
                {"code": r.code, "text": r.text, "phase": r.phase} for r in self.recommendations
            ],
        }

    def _repr_html_(self) -> str:
        from gamehub.analysis.widgets import feasibility_html

        return feasibility_html(self)

    def lines(self) -> list[str]:
        """El informe en texto, para la terminal."""
        c = self.classification
        out = [" · ".join(c.labels())]
        out.append(
            f"ramificación ≈ {self.branching:.1f} · duración ≈ {self.depth_mean:.1f} pasos "
            f"(máx. {self.depth_max})"
        )
        out.append(
            f"árbol ≈ 10^{self.tree_log10:.1f} nodos · ≈ 10^{self.leaves_log10:.1f} partidas "
            f"(Knuth, {self.samples} muestras)"
        )
        if self.truncated:
            out.append(f"⚠ {self.truncated} muestras llegaron al límite de pasos")
        if self.exact:
            names = {
                "positions": "posiciones",
                "games": "partidas",
                "nodes": "nodos",
                "infosets": "conjuntos de información",
                "terminals": "finales",
            }
            out.append(
                "exacto: " + " · ".join(f"{v:,} {names.get(k, k)}" for k, v in self.exact.items())
            )
        out.append("recomendado:")
        for r in self.recommendations:
            out.append(f"  - {r.text}" + (f" ({r.phase})" if r.phase else ""))
        return out


def _sample_chance(
    state: State, rng: Pcg32, cache: dict[str, list[tuple[State, str, Fraction]]]
) -> tuple[State, Fraction]:
    """Un resultado de azar y su probabilidad. Si los resultados son pocos (el sorteo tiene
    probabilidad >= 1/MERGE_LIMIT), se enumeran y se juntan los que llevan al mismo estado, como
    en la forma extensiva (`merged_outcomes`), para que el estimador mida el árbol que se
    construiría; si no, el sorteo tal cual (barajar 52 cartas no se puede enumerar)."""
    outcome = state.sample_chance(rng)
    p = state.outcome_probability(outcome)
    if p * MERGE_LIMIT < 1:
        return state.apply_chance(outcome), p
    key = state.digest()
    merged = cache.get(key)
    if merged is None:
        try:
            merged = merged_outcomes(state, limit=MERGE_LIMIT)
        except NotEnumerable:
            return state.apply_chance(outcome), p
        if len(cache) < 1000:
            cache[key] = merged
    r = Fraction(rng.next_u32(), 2**32)
    acc = Fraction(0)
    for child, _, q in merged:
        acc += q
        if r < acc:
            return child, q
    child, _, q = merged[-1]
    return child, q


def _logsumexp(values: list[float]) -> float:
    top = max(values)
    if top == -math.inf:
        return top
    return top + math.log(sum(math.exp(v - top) for v in values))


@dataclass(frozen=True)
class KnuthEstimate:
    samples: int
    #: log10 del tamaño estimado del árbol (nodos) y de sus hojas.
    tree_log10: float
    leaves_log10: float
    branching: float
    depth_mean: float
    depth_max: int
    #: Muestras que llegaron al límite de pasos (y las que fallaron por un error de reglas).
    truncated: int
    errors: int
    seconds: float


def knuth_estimate(
    root: State,
    *,
    samples: int = 200,
    seed: int = 0,
    max_steps: int = 10_000,
    budget: float | None = 20.0,
    min_samples: int = MIN_SAMPLES,
    skip_errors: bool = False,
) -> KnuthEstimate:
    """El estimador de Knuth desde `root`: `samples` partidas al azar como mucho, o menos si se
    acaba el tiempo (`budget` segundos, con al menos `min_samples`). Con `skip_errors`, una partida
    que tropieza con un error de reglas se descarta (el Studio estima juegos a medio escribir)."""
    started = time.monotonic()
    rng = Pcg32(seed, 7)
    tree_logs: list[float] = []
    leaf_logs: list[float] = []
    depths: list[int] = []
    branchings: list[int] = []
    truncated = errors = 0
    cache: dict[str, list[tuple[State, str, Fraction]]] = {}
    for done in range(samples):
        if budget is not None and done >= min_samples and time.monotonic() - started > budget:
            break
        state = root
        log_w = 0.0
        levels = [0.0]
        steps = 0
        try:
            while not state.is_terminal and steps < max_steps:
                if state.status is Status.CHANCE:
                    state, p = _sample_chance(state, rng, cache)
                    log_w += math.log(p.denominator) - math.log(p.numerator)
                else:
                    seat = state.active_seats[0]
                    actions = state.legal_actions(seat)
                    branchings.append(len(actions))
                    log_w += math.log(len(actions))
                    state = state.apply_action(seat, actions[rng.below(len(actions))])
                levels.append(log_w)
                steps += 1
        except RuleError:
            if not skip_errors:
                raise
            errors += 1
            continue
        if not state.is_terminal:
            truncated += 1
        depths.append(steps)
        tree_logs.append(_logsumexp(levels))
        leaf_logs.append(log_w)
    ln10 = math.log(10)
    log_n = math.log(len(tree_logs)) if tree_logs else 0.0
    return KnuthEstimate(
        samples=len(tree_logs),
        tree_log10=(_logsumexp(tree_logs) - log_n) / ln10 if tree_logs else 0.0,
        leaves_log10=(_logsumexp(leaf_logs) - log_n) / ln10 if leaf_logs else 0.0,
        branching=sum(branchings) / len(branchings) if branchings else 0.0,
        depth_mean=sum(depths) / len(depths) if depths else 0.0,
        depth_max=max(depths, default=0),
        truncated=truncated,
        errors=errors,
        seconds=time.monotonic() - started,
    )


def feasibility(
    game: Game | State,
    *,
    num_players: int | None = None,
    params: dict[str, Any] | None = None,
    samples: int = 200,
    seed: int = 0,
    max_steps: int = 10_000,
    exact: bool = True,
    budget: float | None = 20.0,
) -> Feasibility:
    """La clasificación, el tamaño (`knuth_estimate`, con `samples`, `seed`, `max_steps` y
    `budget`), el recuento exacto si cabe (con su propio límite de tiempo, `PROBE_SECONDS`) y la
    recomendación."""
    root = initial_state(game, num_players, params)
    ir = root.game.ir
    c = classify(ir)
    k = knuth_estimate(root, samples=samples, seed=seed, max_steps=max_steps, budget=budget)
    truncated = k.truncated
    result = Feasibility(
        title=game_title(game),
        classification=c,
        num_players=root.n,
        samples=k.samples,
        tree_log10=k.tree_log10,
        leaves_log10=k.leaves_log10,
        branching=k.branching,
        depth_mean=k.depth_mean,
        depth_max=k.depth_max,
        truncated=truncated,
        tags=tuple(ir.get("meta", {}).get("tags", [])),
    )
    if exact and not truncated:
        small = result.tree_log10 <= math.log10(EXACT_COUNT_LIMIT)
        result.exact = _exact_counts(root, c, EXACT_COUNT_LIMIT * 2 if small else PROBE_LIMIT)
    result.recommendations = recommend(result)
    return result


def _exact_counts(root: State, c: Classification, limit: int) -> dict[str, int]:
    deadline = time.monotonic() + PROBE_SECONDS
    try:
        if c.perfect_information:
            graph = state_graph(root, max_nodes=limit, chance_limit=MERGE_LIMIT, deadline=deadline)
            out = {"positions": graph.positions, "terminals": graph.terminals}
            games = graph.games()
            if games is not None:
                out["games"] = games
            return out
        tree = build_tree(
            root, max_nodes=limit, infosets=True, chance_limit=MERGE_LIMIT, deadline=deadline
        )
        counts = tree.counts()
        return {
            "nodes": counts["nodes"],
            "terminals": counts["terminals"],
            "infosets": counts["infosets"],
        }
    except (TreeError, EngineError):
        return {}


def _core_phase() -> str | None:
    """Lo que hace falta para lo que corre en el núcleo C++: nada si está instalado."""
    from gamehub.engine.core import available

    return None if available() else "gamehub[core]"


def recommend(f: Feasibility) -> list[Recommendation]:
    c = f.classification
    size = f.size_log10
    out: list[Recommendation] = []
    two_zero = f.num_players == 2 and c.zero_sum is True
    if c.perfect_information:
        combinatorial = "combinatorial" in f.tags or "impartial" in f.tags
        if combinatorial and not c.chance and f.num_players == 2:
            out.append(Recommendation("grundy", "valores de Grundy y clases de resultado (N/P)"))
        if size <= PYTHON_EXACT:
            what = (
                "minimax con poda alfa-beta"
                if two_zero
                else "inducción hacia atrás (equilibrio perfecto en subjuegos)"
            )
            if c.chance:
                what += " con expectimax en el azar"
            out.append(Recommendation("solve", f"solución exacta en Python: {what}"))
        elif size <= CPP_EXACT:
            out.append(
                Recommendation(
                    "cpp_exact",
                    "solución exacta en C++ (alfa-beta con tablas de transposición, "
                    "análisis retrógrado)",
                    _core_phase(),
                )
            )
        else:
            out.append(
                Recommendation(
                    "approximate",
                    "solución exacta inviable: alfa-beta con heurística, MCTS, arena de bots",
                    "F9",
                )
            )
        return out
    one_shot = c.simultaneous and f.depth_max <= f.num_players and not c.chance
    if one_shot or size <= 4:
        out.append(Recommendation("normal_form", "forma normal (estrategias puras reducidas)"))
        out.append(
            Recommendation(
                "nash",
                "equilibrios de Nash, dominancia, Pareto, bienestar y precio de la anarquía"
                if f.num_players == 2
                else "equilibrios puros, dominancia, equilibrio correlado y Pareto",
            )
        )
    if "repeated" in f.tags or "iterated" in f.tags:
        out.append(Recommendation("tournament", "torneo de estrategias al estilo de Axelrod"))
    if size <= PYTHON_EXACT:
        if two_zero:
            out.append(
                Recommendation(
                    "sequence_form",
                    "equilibrio exacto por la forma de secuencias (programa lineal)",
                )
            )
        out.append(
            Recommendation(
                "cfr", "CFR+ con explotabilidad (equilibrio aproximado con cota de error)"
            )
        )
        return out
    infosets = f.exact.get("infosets")
    if (infosets is not None and infosets <= CPP_CFR_INFOSETS) or size <= CPP_EXACT:
        out.append(Recommendation("cpp_cfr", "CFR tabular en C++", _core_phase()))
    else:
        out.append(
            Recommendation(
                "approximate",
                "exacto inviable: MCCFR, ISMCTS, heurísticas, aprendizaje por refuerzo; "
                "métricas empíricas",
                "F9",
            )
        )
    return out
