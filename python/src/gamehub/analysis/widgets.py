# SPDX-License-Identifier: Apache-2.0
"""Vistas HTML para notebooks (Jupyter las muestra solas con `_repr_html_`): la matriz de pagos
con las mejores respuestas subrayadas y los equilibrios resaltados, el árbol plegable, la
convergencia de CFR, la tabla de Grundy y el resultado de un torneo. Sin dependencias: HTML y SVG
con estilos en línea que heredan el color del texto (se ven bien con fondo claro u oscuro)."""

from __future__ import annotations

import html
import math
from collections.abc import Sequence
from fractions import Fraction
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gamehub.analysis.feasibility import Feasibility
    from gamehub.analysis.normal_form import NormalForm
    from gamehub.analysis.repeated import TournamentResult
    from gamehub.analysis.tree import GameTree

_TABLE = "border-collapse:collapse;font:13px/1.4 system-ui,sans-serif"
_CELL = "border:1px solid rgba(128,128,128,.35);padding:4px 8px;text-align:center"
_HEAD = _CELL + ";font-weight:600;background:rgba(128,128,128,.08)"
_EQ = "background:rgba(46,160,67,.18);outline:2px solid rgba(46,160,67,.7);outline-offset:-2px"


def _e(x: Any) -> str:
    return html.escape(str(x))


def number(x: Any) -> str:
    if isinstance(x, Fraction):
        return str(x.numerator) if x.denominator == 1 else f"{x.numerator}/{x.denominator}"
    if isinstance(x, float):
        return f"{x:.4g}"
    return str(x)


def normal_form_html(nf: NormalForm) -> str:
    from gamehub.analysis.nash import best_responses, pure_equilibria

    equilibria = set(pure_equilibria(nf))
    title = f"<div style='font-weight:600;margin:4px 0'>{_e(nf.title)}</div>" if nf.title else ""
    if nf.num_players != 2:
        rows = []
        for p in nf.profiles():
            style = _CELL + (";" + _EQ if p in equilibria else "")
            names = " · ".join(_e(nf.strategies[k][s]) for k, s in enumerate(p))
            pay = ", ".join(number(u) for u in nf.payoffs[p])
            rows.append(f"<tr><td style='{_CELL}'>{names}</td><td style='{style}'>{pay}</td></tr>")
        head = f"<tr><th style='{_HEAD}'>perfil</th><th style='{_HEAD}'>pagos</th></tr>"
        return f"{title}<table style='{_TABLE}'>{head}{''.join(rows)}</table>"
    m, n = nf.shape
    head = "".join(f"<th style='{_HEAD}'>{_e(s)}</th>" for s in nf.strategies[1])
    body = []
    for i in range(m):
        cells = []
        for j in range(n):
            u = nf.payoffs[(i, j)]
            br0 = i in best_responses(nf, 0, (i, j))
            br1 = j in best_responses(nf, 1, (i, j))
            a = f"<u>{number(u[0])}</u>" if br0 else number(u[0])
            b = f"<u>{number(u[1])}</u>" if br1 else number(u[1])
            style = _CELL + (";" + _EQ if (i, j) in equilibria else "")
            cells.append(f"<td style='{style}'>{a}, {b}</td>")
        body.append(f"<tr><th style='{_HEAD}'>{_e(nf.strategies[0][i])}</th>{''.join(cells)}</tr>")
    legend = (
        "<div style='font:12px system-ui;opacity:.7;margin-top:4px'>subrayado: mejor respuesta · "
        "recuadro verde: equilibrio de Nash en estrategias puras</div>"
    )
    return (
        f"{title}<table style='{_TABLE}'><tr><th style='{_HEAD}'></th>{head}</tr>"
        f"{''.join(body)}</table>{legend}"
    )


def tree_html(tree: GameTree, max_nodes: int = 300) -> str:
    shown = 0

    def render(h: int, label: str) -> str:
        nonlocal shown
        shown += 1
        node = tree.nodes[h]
        if node.kind == "terminal":
            pay = ", ".join(number(u) for u in node.payoffs)
            return f"<div style='margin-left:1em'>{_e(label)} → <b>({pay})</b></div>"
        what = "azar" if node.kind == "chance" else f"asiento {node.player} · I{node.infoset}"
        if shown > max_nodes:
            return f"<div style='margin-left:1em;opacity:.6'>{_e(label)} … ({what})</div>"
        kids = []
        for k, c in enumerate(node.children):
            edge = node.labels[k]
            if node.kind == "chance":
                edge += f" [{number(node.probs[k])}]"
            kids.append(render(c, edge))
        summary = f"{_e(label)} <span style='opacity:.7'>({what})</span>" if label else what
        return (
            f"<details style='margin-left:1em' {'open' if node.depth < 2 else ''}>"
            f"<summary>{summary}</summary>{''.join(kids)}</details>"
        )

    counts = tree.counts()
    head = (
        f"<div style='font:12px system-ui;opacity:.7'>{counts['nodes']:,} nodos · "
        f"{counts['terminals']:,} finales · {counts['infosets']:,} conjuntos de información</div>"
    )
    return f"<div style='font:13px/1.5 system-ui,sans-serif'>{head}{render(0, '')}</div>"


def convergence_svg(
    points: Sequence[tuple[int, float]], width: int = 480, height: int = 240
) -> str:
    """Explotabilidad frente a iteraciones, en escala logarítmica en los dos ejes."""
    data = [(i, e) for i, e in points if i > 0 and e > 0]
    if len(data) < 2:
        return "<svg width='0' height='0'></svg>"
    pad = 40
    xs = [math.log10(i) for i, _ in data]
    ys = [math.log10(e) for _, e in data]
    x0, x1 = min(xs), max(xs) or 1
    y0, y1 = math.floor(min(ys)), math.ceil(max(ys))
    if y0 == y1:
        y1 = y0 + 1

    def px(x: float) -> float:
        return pad + (x - x0) / ((x1 - x0) or 1) * (width - 2 * pad)

    def py(y: float) -> float:
        return height - pad - (y - y0) / (y1 - y0) * (height - 2 * pad)

    path = " ".join(
        f"{'M' if k == 0 else 'L'}{px(x):.1f},{py(y):.1f}"
        for k, (x, y) in enumerate(zip(xs, ys, strict=True))
    )
    label = "font-size='11' fill='currentColor' opacity='.7'"
    ticks = "".join(
        f"<line x1='{pad}' x2='{width - pad}' y1='{py(t):.1f}' y2='{py(t):.1f}' "
        f"stroke='currentColor' opacity='.12'/>"
        f"<text x='{pad - 6}' y='{py(t) + 4:.1f}' {label} text-anchor='end'>1e{t}</text>"
        for t in range(y0, y1 + 1)
    )
    return (
        f"<svg viewBox='0 0 {width} {height}' width='{width}' height='{height}' "
        f"style='font-family:system-ui;color:inherit'>{ticks}"
        f"<path d='{path}' fill='none' stroke='#2f81f7' stroke-width='2'/>"
        f"<text x='{width / 2}' y='{height - 8}' {label} text-anchor='middle'>"
        f"iteraciones ({data[0][0]:,} – {data[-1][0]:,})</text>"
        f"<text x='12' y='{height / 2}' {label} transform='rotate(-90 12 {height / 2})' "
        f"text-anchor='middle'>explotabilidad</text></svg>"
    )


def grundy_table_html(rows: Sequence[tuple[Any, int]], header: str = "posición") -> str:
    cells = "".join(
        f"<tr><td style='{_CELL}'>{_e(k)}</td>"
        f"<td style='{_CELL}{';font-weight:700' if g == 0 else ''}'>{g}</td></tr>"
        for k, g in rows
    )
    return (
        f"<table style='{_TABLE}'><tr><th style='{_HEAD}'>{_e(header)}</th>"
        f"<th style='{_HEAD}'>Grundy</th></tr>{cells}</table>"
    )


def tournament_html(result: TournamentResult) -> str:
    names = result.names
    head = "".join(f"<th style='{_HEAD}'>{_e(n)}</th>" for n in names)
    rows = "".join(
        f"<tr><th style='{_HEAD}'>{_e(names[i])}</th>"
        + "".join(f"<td style='{_CELL}'>{float(x):.3f}</td>" for x in result.scores[i])
        + f"<td style='{_CELL};font-weight:600'>{float(result.averages[i]):.3f}</td></tr>"
        for i in range(len(names))
    )
    return (
        f"<table style='{_TABLE}'><tr><th style='{_HEAD}'></th>{head}"
        f"<th style='{_HEAD}'>media</th></tr>{rows}</table>"
    )


def feasibility_html(f: Feasibility) -> str:
    items = "".join(f"<li>{_e(line)}</li>" for line in f.lines())
    return f"<ul style='font:13px/1.5 system-ui,sans-serif'>{items}</ul>"
