# SPDX-License-Identifier: Apache-2.0
"""Diagrama del flow (`gamehub viz`) en Mermaid o Graphviz (DOT).

Cada nodo es una caja con su tipo, su nombre y lo esencial (quién juega, qué acciones hay, el
pago); cada transición es una flecha con su acción y su condición escritas en Nomos. Las fases son
subgrafos con una marca de entrada (su `start`) y otra de salida (`-> exit`, de la que salen las
transiciones de la fase).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from gamehub.analysis import irwalk
from gamehub.lang.decompile import expression_text

KINDS = {
    "decision": "decisión",
    "simultaneous": "simultáneo",
    "window": "ventana",
    "chance": "azar",
    "auto": "automático",
    "phase": "fase",
    "terminal": "final",
}
START = "__start"
LABEL_WIDTH = 48


@dataclass
class Box:
    id: str
    kind: str
    lines: list[str]
    parent: str | None


@dataclass
class Edge:
    source: str
    target: str
    label: str = ""


@dataclass
class Flow:
    title: str
    boxes: list[Box] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    phases: dict[str, list[str]] = field(default_factory=dict)  # fase → hijos directos


def flow_graph(ir: dict[str, Any]) -> Flow:
    def text(e: Any) -> str:
        return _short(expression_text(ir, e))

    title = ir.get("meta", {}).get("title", ir["game"]["id"])
    if isinstance(title, dict):
        title = title.get("es") or next(iter(title.values()))
    flow = Flow(str(title))
    flow.edges.append(Edge(START, ir["flow"]["start"]))
    for node, parent in irwalk.all_nodes(ir):
        node_id, kind = node["id"], node["kind"]
        lines: list[str] = []
        if kind in ("decision",) and "actor" in node:
            lines.append(f"juega {text(node['actor'])}")
        if kind == "simultaneous" and "actors" in node:
            lines.append(f"juegan {text(node['actors'])}")
        if kind == "window":
            lines.append(f"{node.get('mode', 'priority')}: {text(node['eligible'])}")
        actions = [a["name"] + "()" for a in node.get("actions", [])]
        if actions:
            lines.append(_short(" · ".join(actions)))
        if kind == "terminal" and "payoff" in node:
            lines.append(f"pago {text(node['payoff'])}")
        flow.boxes.append(Box(node_id, kind, lines, parent))
        if parent is not None:
            flow.phases.setdefault(parent, []).append(node_id)
        if kind == "phase":
            flow.phases.setdefault(node_id, [])
            flow.edges.append(Edge(f"{node_id}__start", node["start"]))
            for t in node.get("transitions", []):
                flow.edges.append(Edge(f"{node_id}__exit", t["to"], _guard(t, text)))
            continue
        for action in node.get("actions", []):
            for t in action.get("transitions", []):
                label = " · ".join(x for x in (action["name"] + "()", _guard(t, text)) if x)
                flow.edges.append(Edge(node_id, _target(t, parent), label))
        for t in node.get("transitions", []):
            flow.edges.append(Edge(node_id, _target(t, parent), _guard(t, text)))
    return flow


def _guard(t: dict[str, Any], text: Any) -> str:
    parts = []
    if "when" in t:
        parts.append(f"si {text(t['when'])}")
    if t.get("effects"):
        parts.append("{…}")
    return " ".join(parts)


def _target(t: dict[str, Any], parent: str | None) -> str:
    return f"{parent}__exit" if t["to"] == "$exit" and parent is not None else t["to"]


def _short(text: str) -> str:
    return text if len(text) <= LABEL_WIDTH else text[: LABEL_WIDTH - 1] + "…"


# --- Mermaid ------------------------------------------------------------------------------------

SHAPES = {
    "decision": ('["', '"]'),
    "simultaneous": ('[["', '"]]'),
    "window": ('[/"', '"\\]'),
    "chance": ('{{"', '"}}'),
    "auto": ('("', '")'),
    "terminal": ('(["', '"])'),
}


def mermaid(ir: dict[str, Any]) -> str:
    flow = flow_graph(ir)
    out = [f"---\ntitle: {_mermaid_text(flow.title)}\n---", "flowchart TD"]
    out.append(f'  {START}(("inicio"))')
    boxes = {b.id: b for b in flow.boxes}

    def box(b: Box, indent: str) -> None:
        if b.kind == "phase":
            out.append(f'{indent}subgraph {b.id}["fase {b.id}"]')
            out.append(f'{indent}  {b.id}__start((" "))')
            for child in flow.phases[b.id]:
                box(boxes[child], indent + "  ")
            out.append(f'{indent}  {b.id}__exit((("exit")))')
            out.append(f"{indent}end")
            return
        left, right = SHAPES[b.kind]
        lines = [_mermaid_text(line) for line in b.lines]
        label = "<br/>".join([f"<b>{b.id}</b>", f"<i>{KINDS[b.kind]}</i>", *lines])
        out.append(f"{indent}{b.id}{left}{label}{right}")

    for b in flow.boxes:
        if b.parent is None:
            box(b, "  ")
    for e in flow.edges:
        arrow = f' -- "{_mermaid_text(e.label)}" --> ' if e.label else " --> "
        out.append(f"  {e.source}{arrow}{e.target}")
    return "\n".join(out) + "\n"


def _mermaid_text(text: str) -> str:
    """Texto dentro de una etiqueta de Mermaid (comillas y signos que parecerían HTML)."""
    return text.replace('"', "#quot;").replace("<", "#lt;").replace(">", "#gt;")


# --- Graphviz -----------------------------------------------------------------------------------

DOT_SHAPES = {
    "decision": "box",
    "simultaneous": "box3d",
    "window": "trapezium",
    "chance": "hexagon",
    "auto": "ellipse",
    "terminal": "doubleoctagon",
}


def dot(ir: dict[str, Any]) -> str:
    flow = flow_graph(ir)
    out = [
        "digraph flow {",
        f"  label={_dot_text(flow.title)}; labelloc=t; fontname=Helvetica; compound=true;",
        "  node [fontname=Helvetica, fontsize=11]; edge [fontname=Helvetica, fontsize=10];",
        f'  {START} [label="inicio", shape=circle];',
    ]
    boxes = {b.id: b for b in flow.boxes}

    def box(b: Box, indent: str) -> None:
        if b.kind == "phase":
            out.append(f"{indent}subgraph cluster_{b.id} {{")
            out.append(f"{indent}  label={_dot_text('fase ' + b.id)}; style=rounded;")
            out.append(f'{indent}  {b.id}__start [label="", shape=circle, width=0.15];')
            for child in flow.phases[b.id]:
                box(boxes[child], indent + "  ")
            out.append(f'{indent}  {b.id}__exit [label="exit", shape=doublecircle];')
            out.append(f"{indent}}}")
            return
        label = "\n".join([b.id, f"({KINDS[b.kind]})", *b.lines])
        out.append(f"{indent}{b.id} [label={_dot_text(label)}, shape={DOT_SHAPES[b.kind]}];")

    for b in flow.boxes:
        if b.parent is None:
            box(b, "  ")
    for e in flow.edges:
        attrs = [f"label={_dot_text(e.label)}"] if e.label else []
        target = e.target
        if target in flow.phases:  # a una fase se entra por su marca de inicio
            attrs.append(f"lhead=cluster_{target}")
            target = f"{target}__start"
        suffix = f" [{', '.join(attrs)}]" if attrs else ""
        out.append(f"  {e.source} -> {target}{suffix};")
    out.append("}")
    return "\n".join(out) + "\n"


def _dot_text(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'
