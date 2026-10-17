# SPDX-License-Identifier: Apache-2.0
"""Un informe de análisis: ejecuta los análisis pedidos sobre un juego y devuelve un documento
JSON (los racionales como texto, `"-1/18"`). Lo usan `gamehub analyze` y la pestaña «Análisis»
del Studio. Un análisis que no se aplica al juego (alfa-beta con información imperfecta, Grundy
en un juego misère…) no rompe el informe: queda en `errors` con su motivo.

Análisis (`ANALYSES`): feasibility, count, solve, tree, normal_form, nash, dominance, correlated,
pareto, sequence_form, cfr, grundy, coop, tournament. `auto` = la viabilidad y lo que recomienda
si es barato.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from gamehub.analysis import nash as nash_mod
from gamehub.analysis.classify import classify
from gamehub.analysis.feasibility import Feasibility, feasibility, knuth_estimate
from gamehub.analysis.lp import Backend
from gamehub.analysis.nash import GameShapeError
from gamehub.analysis.normal_form import NormalForm, normal_form
from gamehub.analysis.tree import (
    MAX_NODES,
    GameTree,
    TooLarge,
    TreeError,
    build_tree,
    state_graph,
)
from gamehub.engine.errors import EngineError
from gamehub.engine.game import Game

#: Tamaño del árbol (log10) por encima del cual no se intenta la forma normal.
NORMAL_FORM_LOG10 = 4

ANALYSES = (
    "feasibility",
    "count",
    "solve",
    "retrograde",
    "tree",
    "normal_form",
    "nash",
    "dominance",
    "correlated",
    "pareto",
    "sequence_form",
    "cfr",
    "grundy",
    "coop",
    "tournament",
)


def num(x: Any) -> Any:
    """Un número para JSON: racionales como texto exacto, `float` redondeados."""
    if isinstance(x, bool):
        return x
    if isinstance(x, Fraction):
        return str(x.numerator) if x.denominator == 1 else f"{x.numerator}/{x.denominator}"
    if isinstance(x, int):
        return str(x)
    if isinstance(x, float):
        return float(f"{x:.6g}")
    return x


def nums(xs: Iterable[Any]) -> list[Any]:
    return [num(x) for x in xs]


@dataclass
class Options:
    cfr_iterations: int = 1000
    cfr_plus: bool = True
    tournament_rounds: int = 200
    tournament_noise: float = 0.0
    max_nodes: int = MAX_NODES
    lp: Backend = "auto"
    seed: int = 0
    #: "auto" (el núcleo C++ si está instalado), "cpp" o "python".
    engine: str = "auto"


class _Context:
    """Las representaciones del juego, construidas una vez y compartidas entre análisis."""

    def __init__(
        self, game: Game, num_players: int | None, params: dict[str, Any], options: Options
    ):
        self.game = game
        self.num_players = num_players
        self.params = params
        self.options = options
        self._tree: GameTree | None = None
        self._nf: NormalForm | None = None
        self._equilibria: list[Any] | None = None
        self._size: float | None = None
        self.feasibility: Feasibility | None = None

    def state(self) -> Any:
        return self.game.new_state(self.num_players, self.params)

    def size_log10(self) -> float:
        """log10 del tamaño del árbol: el del asesor si ya se calculó o una estimación rápida."""
        if self._size is None:
            if self.feasibility is not None:
                self._size = self.feasibility.tree_log10
            else:
                self._size = knuth_estimate(self.state(), samples=60, budget=2.0).tree_log10
        return self._size

    def tree(self) -> GameTree:
        if self._tree is None:
            # Antes de construirlo, la estimación: si el árbol no va a caber, mejor decirlo en un
            # par de segundos que tras minutos de trabajo.
            size = self.size_log10()
            if size > math.log10(self.options.max_nodes) + 0.5:
                raise TooLarge(
                    f"el árbol del juego (≈ 10^{size:.1f} nodos)", self.options.max_nodes
                )
            self._tree = build_tree(self.state(), max_nodes=self.options.max_nodes)
            self._tree.title = self.game.title
        return self._tree

    def normal_form(self) -> NormalForm:
        if self._nf is None:
            size = self.size_log10()
            if size > NORMAL_FORM_LOG10:
                raise GameShapeError(
                    f"la forma normal no es viable: el árbol tiene ≈ 10^{size:.1f} nodos y las "
                    "estrategias reducidas serían incontables (usa la forma de secuencias o CFR)"
                )
            self._nf = normal_form(self.tree())
        return self._nf

    def equilibria(self) -> list[Any]:
        if self._equilibria is None:
            self._equilibria = nash_mod.equilibria(self.normal_form())
        return self._equilibria


def analyze(
    game: Game,
    analyses: Iterable[str] = ("auto",),
    *,
    num_players: int | None = None,
    params: dict[str, Any] | None = None,
    options: Options | None = None,
) -> dict[str, Any]:
    options = options or Options()
    ctx = _Context(game, num_players, dict(params or {}), options)
    wanted = list(dict.fromkeys(analyses))
    report: dict[str, Any] = {
        "game": {
            "id": game.id,
            "title": game.title,
            "players": ctx.state().n,
            "params": ctx.params,
        },
        "errors": {},
    }
    if "auto" in wanted:
        wanted.remove("auto")
        f = _run(report, "feasibility", lambda: _feasibility(ctx))
        if f is not None:
            wanted = _auto(ctx.feasibility) + wanted
    for name in wanted:
        if name in report or name in report["errors"]:
            continue
        if name not in _RUNNERS:
            report["errors"][name] = f"análisis desconocido: {name}"
            continue
        _run(report, name, lambda name=name: _RUNNERS[name](ctx))
    return report


def _run(report: dict[str, Any], name: str, fn: Callable[[], Any]) -> Any:
    try:
        result = fn()
    except (GameShapeError, TreeError, EngineError, ValueError, KeyError) as exc:
        report["errors"][name] = str(exc)
        return None
    report[name] = result
    return result


def _auto(f: Feasibility | None) -> list[str]:
    """Lo recomendado que se calcula en segundos con el motor de Python."""
    if f is None:
        return []
    size = f.size_log10
    out: list[str] = []
    for r in f.recommendations:
        if r.code == "solve" and size <= 4.5:
            out.append("solve")
        elif r.code == "grundy" and size <= 4.5:
            out.append("grundy")
        elif r.code in ("normal_form", "nash") and size <= 3.5:
            out.extend(["normal_form", "nash"])
            if f.classification.zero_sum is not True:
                out.append("pareto")
        elif r.code == "sequence_form" and size <= 3.5:
            out.append("sequence_form")
        elif r.code == "cfr" and size <= 3.5:
            out.append("cfr")
    return list(dict.fromkeys(out))


# --- Cada análisis -------------------------------------------------------------------------------


def _feasibility(ctx: _Context) -> dict[str, Any]:
    ctx.feasibility = feasibility(ctx.state(), seed=ctx.options.seed)
    ctx.feasibility.title = ctx.game.title
    return ctx.feasibility.to_json()


def _count(ctx: _Context) -> dict[str, Any]:
    graph = state_graph(ctx.state(), max_nodes=ctx.options.max_nodes)
    return {
        "positions": graph.positions,
        "terminals": graph.terminals,
        "games": graph.games(),
        "cyclic": graph.cyclic,
    }


def _use_cpp(ctx: _Context) -> bool:
    from gamehub.engine.core import available

    if ctx.options.engine == "python":
        return False
    if ctx.options.engine == "cpp" and not available():
        raise ValueError("el núcleo C++ no está instalado (pip install 'gamehub[core]')")
    return available()


def _solve(ctx: _Context) -> dict[str, Any]:
    from gamehub.analysis.search import solve

    state = ctx.state()
    if _use_cpp(ctx) and state.n == 2 and classify(ctx.game.ir).zero_sum is not False:
        from gamehub.analysis import cpp

        try:
            solution = cpp.alphabeta(ctx.game, num_players=ctx.num_players, params=ctx.params)
        except EngineError as exc:
            if "no suman siempre lo mismo" not in str(exc):
                raise
            solution = solve(state, max_nodes=ctx.options.max_nodes)
    else:
        solution = solve(state, max_nodes=ctx.options.max_nodes)
    out = solution.to_json()
    out["value"] = nums(solution.value)
    return out


def _tree(ctx: _Context) -> dict[str, Any]:
    return ctx.tree().to_json(max_nodes=400)


def _normal_form(ctx: _Context) -> dict[str, Any]:
    nf = ctx.normal_form()
    return {
        "players": list(nf.players),
        "strategies": [list(s) for s in nf.strategies],
        "payoffs": [{"profile": list(p), "payoffs": nums(nf.payoffs[p])} for p in nf.profiles()],
        "infosets": {str(k): v for k, v in (nf.infosets or {}).items()},
        "constant_sum": nf.is_constant_sum(),
    }


def _mixed(nf: NormalForm, profile: Any) -> dict[str, Any]:
    return {
        "strategies": [nums(mix) for mix in profile],
        "payoffs": nums(nf.expected(profile)),
    }


def _nash(ctx: _Context) -> dict[str, Any]:
    nf = ctx.normal_form()
    out: dict[str, Any] = {
        "strategies": [list(x) for x in nf.strategies],
        "pure": [list(p) for p in nash_mod.pure_equilibria(nf)],
    }
    if nf.num_players == 2:
        found = ctx.equilibria()
        small = nash_mod.support_pairs(*nf.shape) <= nash_mod.SUPPORT_PAIRS_LIMIT
        out["method"] = "support_enumeration+lemke_howson" if small else "lemke_howson"
        out["complete"] = small
        out["mixed"] = [_mixed(nf, eq) for eq in found]
        if nf.is_constant_sum():
            zs = nash_mod.zero_sum(nf, backend=ctx.options.lp)
            out["zero_sum"] = {
                "value": num(zs.value),
                "strategies": [nums(s) for s in zs.strategies],
            }
    return out


def _dominance(ctx: _Context) -> dict[str, Any]:
    nf = ctx.normal_form()
    strict = nash_mod.iterated_dominance(nf, mixed=True, backend=ctx.options.lp)
    weak = nash_mod.iterated_dominance(nf, weak=True)
    return {
        "strategies": [list(x) for x in nf.strategies],
        "strict": {"remaining": strict.remaining, "steps": [list(s) for s in strict.steps]},
        "weak": {"remaining": weak.remaining, "steps": [list(s) for s in weak.steps]},
    }


def _correlated(ctx: _Context) -> dict[str, Any]:
    nf = ctx.normal_form()
    dist = nash_mod.correlated_equilibrium(nf, backend=ctx.options.lp)
    welfare = sum((q * sum(nf.payoffs[p]) for p, q in dist.items()), Fraction(0))
    return {
        "strategies": [list(x) for x in nf.strategies],
        "distribution": [{"profile": list(p), "probability": num(q)} for p, q in dist.items()],
        "welfare": num(welfare),
    }


def _pareto(ctx: _Context) -> dict[str, Any]:
    nf = ctx.normal_form()
    value, best = nash_mod.social_optimum(nf)
    egal, egal_best = nash_mod.social_optimum(nf, "egalitarian")
    found = ctx.equilibria()
    pure_eq = nash_mod.pure_equilibria(nf)
    return {
        "strategies": [list(x) for x in nf.strategies],
        "optimal": [list(p) for p in nash_mod.pareto_optimal(nf)],
        "equilibria_dominated": [
            {"profile": list(p), "by": [list(q) for q in nash_mod.pareto_dominators(nf, p)]}
            for p in pure_eq
            if nash_mod.pareto_dominators(nf, p)
        ],
        "utilitarian": {"value": num(value), "profiles": [list(p) for p in best]},
        "egalitarian": {"value": num(egal), "profiles": [list(p) for p in egal_best]},
        "price_of_anarchy": num(nash_mod.price_of_anarchy(nf, found)),
        "price_of_stability": num(nash_mod.price_of_stability(nf, found)),
    }


def _sequence_form(ctx: _Context) -> dict[str, Any]:
    from gamehub.analysis.policy import exploitability, policy_json
    from gamehub.analysis.sequence_form import sequence_form

    tree = ctx.tree()
    sol = sequence_form(tree, backend=ctx.options.lp)
    return {
        "value": num(sol.value),
        "exploitability": num(exploitability(tree, sol.policy)),
        "policy": policy_json(tree, sol.policy),
    }


def _cfr(ctx: _Context) -> dict[str, Any]:
    from gamehub.analysis.cfr import solve_cfr
    from gamehub.analysis.policy import expected_values, exploitability, policy_json

    tree = ctx.tree()
    iterations = ctx.options.cfr_iterations
    every = max(1, iterations // 50)
    policy, convergence = solve_cfr(
        tree, iterations, plus=ctx.options.cfr_plus, measure_every=every
    )
    return {
        "iterations": iterations,
        "plus": ctx.options.cfr_plus,
        "values": nums(expected_values(tree, policy)),
        "exploitability": num(float(exploitability(tree, policy))),
        "convergence": [[i, num(e)] for i, e in convergence.points],
        "policy": policy_json(tree, policy),
    }


def _retrograde(ctx: _Context) -> dict[str, Any]:
    """Análisis retrógrado en C++: juegos deterministas de dos jugadores, también con ciclos."""
    from gamehub.analysis import cpp

    if not _use_cpp(ctx):
        raise ValueError("el análisis retrógrado necesita el núcleo C++")
    return cpp.retrograde(ctx.game, num_players=ctx.num_players, params=ctx.params)


def _grundy(ctx: _Context) -> dict[str, Any]:
    from gamehub.analysis.cgt import grundy

    return grundy(ctx.state(), max_nodes=ctx.options.max_nodes).to_json()


def _coop(ctx: _Context) -> dict[str, Any]:
    from gamehub.analysis import coop

    nf = ctx.normal_form()
    cf = coop.characteristic_function(nf, backend=ctx.options.lp)
    out: dict[str, Any] = cf.to_json()
    out["shapley"] = nums(coop.shapley(cf))
    out["banzhaf"] = nums(coop.banzhaf(cf))
    point = coop.core(cf, backend=ctx.options.lp)
    out["core"] = None if point is None else nums(point)
    try:
        out["nucleolus"] = nums(coop.nucleolus(cf))
    except GameShapeError as exc:
        out["nucleolus"] = None
        out["nucleolus_error"] = str(exc)
    if nf.num_players == 2:
        bargaining = coop.nash_bargaining(nf)
        out["nash_bargaining"] = (
            None
            if bargaining is None
            else {
                "payoffs": nums(bargaining.payoffs),
                "disagreement": nums(bargaining.disagreement),
            }
        )
    return out


def _tournament(ctx: _Context) -> dict[str, Any]:
    from gamehub.analysis.repeated import ecological, tournament

    stage_game = ctx.game
    params = dict(ctx.params)
    # Un juego repetido se analiza con su juego de etapa: una sola ronda.
    if "repeated" in stage_game.ir.get("meta", {}).get("tags", []):
        rounds_param = next(
            (p["name"] for p in stage_game.ir.get("params", []) if p["name"].startswith("rounds")),
            None,
        )
        if rounds_param:
            params[rounds_param] = 1
    stage = normal_form(stage_game.new_state(ctx.num_players, params))
    result = tournament(
        stage,
        rounds=ctx.options.tournament_rounds,
        noise=ctx.options.tournament_noise,
        seed=ctx.options.seed,
    )
    out = result.to_json()
    history = ecological(result, generations=200)
    out["ecological"] = {
        "generations": len(history) - 1,
        "final": [round(x, 4) for x in history[-1]],
        "series": [[round(x, 4) for x in row] for row in history[:: max(1, len(history) // 50)]],
    }
    return out


_RUNNERS: dict[str, Callable[[_Context], Any]] = {
    "feasibility": _feasibility,
    "count": _count,
    "solve": _solve,
    "retrograde": _retrograde,
    "tree": _tree,
    "normal_form": _normal_form,
    "nash": _nash,
    "dominance": _dominance,
    "correlated": _correlated,
    "pareto": _pareto,
    "sequence_form": _sequence_form,
    "cfr": _cfr,
    "grundy": _grundy,
    "coop": _coop,
    "tournament": _tournament,
}


# --- En texto ------------------------------------------------------------------------------------


def report_lines(report: dict[str, Any]) -> list[str]:
    """El informe en texto, para la terminal."""
    g = report["game"]
    out = [f"{g['title']} ({g['players']} jugadores)"]
    if "feasibility" in report:
        f = report["feasibility"]
        out.append("\n▸ Viabilidad")
        out.append("  " + " · ".join(f["labels"]))
        out.append(
            f"  ramificación ≈ {f['branching']:.1f} · duración ≈ {f['depth']['mean']:.1f} pasos "
            f"(máx. {f['depth']['max']}) · árbol ≈ 10^{f['tree_log10']:.1f} nodos (Knuth)"
        )
        if f["exact"]:
            out.append("  exacto: " + " · ".join(f"{k}={v:,}" for k, v in f["exact"].items()))
        for r in f["recommendations"]:
            out.append(f"  → {r['text']}" + (f" ({r['phase']})" if r["phase"] else ""))
    if "count" in report:
        c = report["count"]
        games = f"{c['games']:,}" if c["games"] is not None else "∞ (hay ciclos)"
        out.append("\n▸ Recuento")
        out.append(
            f"  {c['positions']:,} posiciones · {c['terminals']:,} finales · {games} partidas"
        )
    if "solve" in report:
        s = report["solve"]
        out.append(
            "\n▸ Solución ("
            + ("alfa-beta" if s["method"] == "alphabeta" else "inducción hacia atrás")
            + ")"
        )
        out.append(f"  valor: ({', '.join(s['value'])}) · {s['states']:,} estados")
        if s["best"]:
            out.append(f"  jugadas óptimas: {', '.join(s['best'])}")
        out.append(f"  partida óptima: {' '.join(s['pv'])}")
    if "tree" in report:
        c = report["tree"]["counts"]
        out.append("\n▸ Forma extensiva")
        out.append(
            f"  {c['nodes']:,} nodos · {c['terminals']:,} finales · {c['chance']:,} de azar · "
            f"{c['infosets']:,} conjuntos de información"
        )
    if "normal_form" in report:
        out.append("\n▸ Forma normal")
        out.extend("  " + line for line in _matrix_lines(report["normal_form"]))
    if "nash" in report:
        n = report["nash"]
        nf = n
        out.append("\n▸ Equilibrios de Nash")
        if nf:
            pure = [_profile_name(nf, p) for p in n["pure"]]
            out.append(f"  puros: {', '.join(pure) if pure else 'ninguno'}")
        for eq in n.get("mixed", []):
            mix = (
                " | ".join(
                    ", ".join(
                        f"{name}={q}"
                        for name, q in zip(nf["strategies"][k], s, strict=True)
                        if q != "0"
                    )
                    for k, s in enumerate(eq["strategies"])
                )
                if nf
                else str(eq["strategies"])
            )
            out.append(f"  ({mix}) → pagos ({', '.join(eq['payoffs'])})")
        if "zero_sum" in n:
            out.append(f"  valor (suma cero): {n['zero_sum']['value']}")
    if "dominance" in report:
        d = report["dominance"]
        nf = d
        out.append("\n▸ Dominancia iterada")
        for kind, title in (("strict", "estricta (también por mixtas)"), ("weak", "débil")):
            steps = d[kind]["steps"]
            text = ", ".join(
                f"{nf['strategies'][p][s] if nf else s} (asiento {p})" for p, s, _ in steps
            )
            out.append(f"  {title}: {text if steps else 'nada que eliminar'}")
    if "correlated" in report:
        c = report["correlated"]
        nf = c
        dist = ", ".join(
            f"{_profile_name(nf, d['profile']) if nf else d['profile']}: {d['probability']}"
            for d in c["distribution"]
        )
        out.append("\n▸ Equilibrio correlado (máximo bienestar)")
        out.append(f"  {dist} · bienestar {c['welfare']}")
    if "pareto" in report:
        p = report["pareto"]
        nf = p
        out.append("\n▸ Eficiencia")
        if nf:
            out.append(
                "  óptimos de Pareto: " + ", ".join(_profile_name(nf, q) for q in p["optimal"])
            )
            for item in p["equilibria_dominated"]:
                by = ", ".join(_profile_name(nf, q) for q in item["by"])
                eq = _profile_name(nf, item["profile"])
                out.append(f"  el equilibrio {eq} está dominado en Pareto por {by}")
        out.append(f"  óptimo social (utilitarista): {p['utilitarian']['value']}")
        if p["price_of_anarchy"] is not None:
            out.append(
                f"  precio de la anarquía: {p['price_of_anarchy']} · "
                f"de la estabilidad: {p['price_of_stability']}"
            )
    if "sequence_form" in report:
        s = report["sequence_form"]
        out.append("\n▸ Forma de secuencias (equilibrio exacto)")
        out.append(
            f"  valor para el asiento 0: {s['value']} · explotabilidad: {s['exploitability']}"
        )
        out.extend("  " + line for line in _policy_lines(s["policy"]))
    if "cfr" in report:
        c = report["cfr"]
        out.append(f"\n▸ {'CFR+' if c['plus'] else 'CFR'} ({c['iterations']:,} iteraciones)")
        values = ", ".join(str(v) for v in c["values"])
        out.append(f"  valores: ({values}) · explotabilidad: {c['exploitability']}")
        out.extend("  " + line for line in _policy_lines(c["policy"]))
    if "grundy" in report:
        gr = report["grundy"]
        out.append("\n▸ Sprague–Grundy")
        who = "gana quien mueve" if gr["outcome"] == "N" else "pierde quien mueve"
        out.append(f"  valor de Grundy: {gr['value']} → posición {gr['outcome']} ({who})")
        if gr["winning"]:
            out.append(f"  jugadas ganadoras: {', '.join(gr['winning'])}")
    if "coop" in report:
        c = report["coop"]
        out.append("\n▸ Juego cooperativo (función característica maximin)")
        for item in c["values"]:
            if item["coalition"]:
                out.append(
                    f"  v({{{', '.join(str(i) for i in item['coalition'])}}}) = {item['value']}"
                )
        out.append(f"  Shapley: ({', '.join(c['shapley'])}) · Banzhaf: ({', '.join(c['banzhaf'])})")
        out.append(
            "  núcleo: " + ("vacío" if c["core"] is None else f"contiene ({', '.join(c['core'])})")
        )
        if c.get("nucleolus") is not None:
            out.append(f"  nucléolo: ({', '.join(c['nucleolus'])})")
        if c.get("nash_bargaining"):
            nb = c["nash_bargaining"]
            agreed, threat = ", ".join(nb["payoffs"]), ", ".join(nb["disagreement"])
            out.append(f"  negociación de Nash: ({agreed}) desde ({threat})")
    if "tournament" in report:
        t = report["tournament"]
        out.append(f"\n▸ Torneo de Axelrod ({t['rounds']} rondas por partida)")
        for k, item in enumerate(t["ranking"], start=1):
            out.append(f"  {k:2}. {item['name']:<7} {item['score']:.3f}")
        final = sorted(zip(t["names"], t["ecological"]["final"], strict=True), key=lambda x: -x[1])
        out.append(
            "  simulación ecológica: " + ", ".join(f"{n} {s:.0%}" for n, s in final if s >= 0.005)
        )
    for name, message in report["errors"].items():
        out.append(f"\n✗ {name}: {message}")
    return out


def _profile_name(nf: dict[str, Any], profile: list[int]) -> str:
    return "(" + ", ".join(nf["strategies"][k][s] for k, s in enumerate(profile)) + ")"


def _matrix_lines(nf: dict[str, Any]) -> list[str]:
    strategies = nf["strategies"]
    if len(strategies) != 2:
        return [
            f"{_profile_name(nf, p['profile'])}: ({', '.join(p['payoffs'])})" for p in nf["payoffs"]
        ]
    payoffs = {tuple(p["profile"]): p["payoffs"] for p in nf["payoffs"]}
    if len(strategies[0]) * len(strategies[1]) > 64:
        return [
            f"{len(strategies[0])} × {len(strategies[1])} estrategias (reducidas)",
            *(f"I{k}: {v}" for k, v in nf["infosets"].items()),
        ]
    cells = [
        [", ".join(payoffs[(i, j)]) for j in range(len(strategies[1]))]
        for i in range(len(strategies[0]))
    ]
    width = max(len(x) for row in cells for x in row)
    width = max(width, *(len(s) for s in strategies[1]))
    left = max(len(s) for s in strategies[0])
    lines = [" " * left + " │ " + " │ ".join(s.center(width) for s in strategies[1])]
    lines.append("─" * left + "─┼─" + "─┼─".join("─" * width for _ in strategies[1]))
    for s, row in zip(strategies[0], cells, strict=True):
        lines.append(s.ljust(left) + " │ " + " │ ".join(x.center(width) for x in row))
    return lines


def _policy_lines(policy: list[dict[str, Any]], limit: int = 24) -> list[str]:
    lines = []
    for item in policy[:limit]:
        probs = ", ".join(f"{a}={q}" for a, q in zip(item["actions"], item["probs"], strict=True))
        lines.append(
            f"[{item['player']}] {item['description'] or 'I' + str(item['infoset'])}: {probs}"
        )
    if len(policy) > limit:
        lines.append(f"… y {len(policy) - limit} conjuntos de información más")
    return lines
