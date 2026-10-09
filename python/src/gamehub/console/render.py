# SPDX-License-Identifier: Apache-2.0
"""Representación en texto de vistas, acciones y eventos (para la terminal)."""

from __future__ import annotations

from typing import Any

from gamehub.engine.game import Game
from gamehub.engine.state import Action
from gamehub.engine.values import Type, to_json

HIDDEN_MARK = "▒"
NONE_MARK = "·"


def is_hidden(v: Any) -> bool:
    return isinstance(v, dict) and v.get("$hidden") is True


def value_text(v: Any) -> str:
    """Valor JSON de una vista → texto compacto."""
    if is_hidden(v):
        return HIDDEN_MARK
    if v is None:
        return NONE_MARK
    if isinstance(v, bool):
        return "sí" if v else "no"
    if isinstance(v, int | str):
        return str(v)
    if isinstance(v, list):
        return "[" + ", ".join(value_text(x) for x in v) + "]"
    if isinstance(v, dict):
        if "items" in v and set(v) <= {"size", "items"}:
            return zone_text(v)
        if set(v) == {"size"}:
            return f"{v['size']} ocultas"
        return "/".join(value_text(x) for x in v.values())
    return str(v)


def zone_text(z: dict[str, Any]) -> str:
    items = z.get("items", [])
    shown = " ".join(value_text(x) for x in items) if items else ""
    size = z.get("size")
    if size is None:
        return f"{{{shown}}} (tamaño oculto)"
    hidden = size - len(items)
    extra = f" +{hidden} {HIDDEN_MARK}" if hidden > 0 else ""
    body = shown or ("vacía" if size == 0 else "")
    return f"({size}) {body}{extra}".rstrip()


def board_text(rows: list[list[Any]]) -> list[str]:
    cells = [[value_text(x) for x in row] for row in rows]
    width = max((len(c) for row in cells for c in row), default=1)
    header = "    " + " ".join(f"{c:>{width}}" for c in range(len(cells[0]) if cells else 0))
    lines = [header]
    lines += [f"{r:>3} " + " ".join(f"{c:>{width}}" for c in row) for r, row in enumerate(cells)]
    return lines


def var_lines(name: str, value: Any, t: Type) -> list[str]:
    if is_hidden(value):
        return [f"  {name}: {HIDDEN_MARK}"]
    if t.kind == "per_player":
        lines = [f"  {name}:"]
        for seat, item in enumerate(value):
            if t.inner.kind == "grid" and not is_hidden(item):
                lines += [f"    asiento {seat}:"] + ["      " + ln for ln in board_text(item)]
            else:
                lines.append(f"    asiento {seat}: {value_text(item)}")
        return lines
    if t.kind == "grid":
        return [f"  {name}:"] + ["    " + ln for ln in board_text(value)]
    return [f"  {name}: {value_text(value)}"]


def view_text(game: Game, view: dict[str, Any], *, seat: int | None) -> str:
    who = "vista omnisciente" if seat is None else f"vista del asiento {seat}"
    lines = [f"── {game.title} · {who} · nodo {view['node']} ──"]
    for var in game.defn.vars:
        lines += var_lines(var.name, view["state"][var.name], var.type)
    if view.get("active"):
        lines.append(f"  turno: {', '.join(str(s) for s in view['active'])}")
    if view.get("responded"):
        lines.append(f"  ya han respondido: {', '.join(str(s) for s in view['responded'])}")
    if "payoffs" in view:
        lines.append(f"  pagos: {', '.join(value_text(p) for p in view['payoffs'])}")
    return "\n".join(lines)


def action_text(action: Action) -> str:
    if not action.args:
        return action.name
    args = ", ".join(f"{k}: {value_text(to_json(v))}" for k, v in action.args)
    return f"{action.name}({args})"


def event_text(e: dict[str, Any]) -> str | None:
    """Evento → línea de texto (None para los que no merece la pena mostrar)."""
    kind = e.get("type")
    if kind == "action":
        if "name" not in e:
            return f"asiento {e['seat']} actúa (oculto)"
        args = e.get("args") or {}
        inner = ", ".join(f"{k}: {value_text(v)}" for k, v in args.items())
        return f"asiento {e['seat']}: {e['name']}" + (f"({inner})" if inner else "")
    if kind == "move":
        where = lambda loc: loc["var"] + (f"[{loc['seat']}]" if "seat" in loc else "")  # noqa: E731
        items = " ".join(value_text(x) for x in e["items"])
        return f"{e['count']} de {where(e['from'])} → {where(e['to'])}: {items}"
    if kind == "reveal":
        return f"se revela: {value_text(e['value'])}"
    if kind == "emit":
        fields = ", ".join(f"{k}={value_text(v)}" for k, v in e["fields"].items())
        return f"{e['name']}: {fields}"
    if kind == "shuffle":
        return f"se baraja {e['zone']['var']}"
    if kind in ("submitted", "responded"):
        return f"asiento {e['seat']} ya ha elegido"
    if kind == "responses":
        return "respuestas: " + ", ".join(f"{r['seat']}={r['name']}" for r in e["responses"])
    if kind == "reward":
        return f"recompensa para {e['seat']}: {value_text(e['amount'])}"
    if kind == "end":
        return f"fin · pagos: {', '.join(value_text(p) for p in e['payoffs'])}"
    return None
