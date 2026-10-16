# SPDX-License-Identifier: Apache-2.0
"""La sección `ui { … }` de Nomos: pistas de presentación para las interfaces.

    ui {
      board: grid
      cup: dice, label({ es: "Cubilete", en: "Cup" })
      die: hidden
      Mark: symbols(X: "✕", O: "◯")
      Disc: colors(Red: "#e53935", Yellow: "#fdd835")
      Card: card(rank: rank, suit: suit)
      action drop.c: column(board)
      action bid: label({ es: "Apostar", en: "Bid" })
      node Bid: label({ es: "Apuestas", en: "Bidding" })
      seats: colors("#e53935", "#fdd835")
    }

No son reglas: llegan a la IR en la clave `ui`, que no cuenta para el hash de reglas, y solo las
leen las interfaces (la UI genérica de la web, `@gamehub/auto-ui`). Aquí está el catálogo de
pistas, su comprobación (E701–E704), la traducción a la IR y la vuelta (para el descompilador).
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Any

from gamehub.lang import ast
from gamehub.lang import types as T
from gamehub.lang.diagnostics import Diagnostics
from gamehub.lang.source import Span
from gamehub.lang.symbols import SymbolIndex
from gamehub.lang.types import Ty

#: Cómo dibujar una variable de estado (como mucho una por variable).
WIDGETS = ("grid", "hand", "pile", "deck", "row", "dice", "counter", "chips", "seat", "hidden")
#: Dónde dibujarla: en la mesa, en el panel de cada asiento (per_player) o en la barra de arriba.
PLACES = ("table", "seats", "top")
#: Cómo elegir el valor de un parámetro de acción tocando el tablero o una zona.
INPUTS = ("cell", "column", "row", "pick")

COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

#: Pistas por clase de destino (para los mensajes de error).
ALLOWED = {
    "state": (*WIDGETS, "label", "place"),
    "param": ("label",),
    "enum": ("label", "symbols", "colors", "labels", "card"),
    "struct": ("label", "card"),
    "action": ("label",),
    "action_param": ("label", *INPUTS),
    "node": ("label",),
    "seats": ("colors", "names"),
}


def slot(target: str, hint: str) -> str:
    """El hueco que ocupa una pista: las formas de dibujar una variable comparten uno (`widget`)
    y las formas de elegir un parámetro, otro (`input`); las demás, el suyo."""
    if target == "action_param" and hint in INPUTS:
        return "input"
    if target == "state" and hint in WIDGETS:
        return "widget"
    return hint


def merge(base: list[ast.UiEntry], extra: list[ast.UiEntry]) -> list[ast.UiEntry]:
    """Las pistas de una variante (`extends`) sobre las de la base: cada una sustituye a la del
    mismo hueco y destino."""

    def key(entry: ast.UiEntry, hint: ast.UiHint) -> tuple[str, tuple[str, ...], str]:
        kind = {"action": "action_param" if len(entry.path) == 2 else "action"}.get(
            entry.target, "state" if entry.target == "name" else entry.target
        )
        return entry.target, tuple(entry.path), slot(kind, hint.name)

    replaced = {key(e, h) for e in extra for h in e.hints}
    kept: list[ast.UiEntry] = []
    for entry in base:
        hints = [h for h in entry.hints if key(entry, h) not in replaced]
        if hints:
            kept.append(ast.UiEntry(target=entry.target, path=entry.path, hints=hints))
    return [*kept, *extra]


# --- Comprobación y traducción a la IR -----------------------------------------------------------


@dataclass
class UiContext:
    """Lo que la comprobación necesita saber del juego (lo rellena el comprobador)."""

    state: dict[str, Ty]
    params: set[str]
    enums: dict[str, list[str]]
    structs: dict[str, dict[str, Ty]]
    #: acción → parámetro → tipos (una acción puede estar en varios nodos)
    actions: dict[str, dict[str, list[Ty]]]
    nodes: set[str]
    #: tipos que llegan a la IR (los importados que no se usan, no)
    emitted_types: set[str] = field(default_factory=set)


class _Fail(Exception):
    pass


class UiChecker:
    def __init__(
        self, ctx: UiContext, diagnostics: Diagnostics, index: SymbolIndex | None = None
    ) -> None:
        self.ctx = ctx
        self.diagnostics = diagnostics
        self.index = index
        self.ir: dict[str, Any] = {}
        self.seen: dict[tuple[str, tuple[str, ...], str], Span] = {}

    def note(self, span: Span | None, key: str) -> None:
        if self.index is not None:
            self.index.ref(span, key)

    def note_path(self, entry: ast.UiEntry, i: int, key: str) -> None:
        if i < len(entry.name_spans):
            self.note(entry.name_spans[i], key)

    def error(self, code: str, message: str, span: Span, help: str | None = None) -> _Fail:
        self.diagnostics.error(code, message, span, help=help)
        return _Fail()

    def run(self, entries: list[ast.UiEntry]) -> dict[str, Any]:
        for entry in entries:
            try:
                kind = self.target_kind(entry)
            except _Fail:
                continue
            for hint in entry.hints:
                key = (entry.target, tuple(entry.path), slot(kind, hint.name))
                if key in self.seen:
                    self.error(
                        "E704",
                        f"`{_target_text(entry)}` ya tiene una pista "
                        + ("de dibujo" if key[2] in ("widget", "input") else f"`{hint.name}`"),
                        hint.span,
                    )
                    continue
                self.seen[key] = hint.span
                try:
                    self.hint(entry, kind, hint)
                except _Fail:
                    continue
        order = ("state", "params", "types", "actions", "nodes", "seats")
        return {k: self.ir[k] for k in order if self.ir.get(k)}

    # --- destinos -------------------------------------------------------------------------------

    def target_kind(self, entry: ast.UiEntry) -> str:
        ctx = self.ctx
        span = entry.span
        match entry.target:
            case "seats":
                return "seats"
            case "node":
                [name] = entry.path
                if name not in ctx.nodes:
                    raise self.error(
                        "E701", f"no hay ningún nodo `{name}`", span, _close(name, ctx.nodes)
                    )
                self.note_path(entry, 0, f"node:{name}")
                return "node"
            case "action":
                name = entry.path[0]
                if name not in ctx.actions:
                    raise self.error(
                        "E701", f"no hay ninguna acción `{name}`", span, _close(name, ctx.actions)
                    )
                self.note_path(entry, 0, f"action:{name}")
                if len(entry.path) == 1:
                    return "action"
                param = entry.path[1]
                if param not in ctx.actions[name]:
                    raise self.error(
                        "E701",
                        f"la acción `{name}` no tiene el parámetro `{param}`",
                        span,
                        _close(param, ctx.actions[name]),
                    )
                self.note_path(entry, 1, f"aparam:{name}.{param}")
                return "action_param"
        [name] = entry.path
        if name in ctx.state:
            self.note_path(entry, 0, f"state:{name}")
            return "state"
        if name in ctx.params:
            self.note_path(entry, 0, f"param:{name}")
            return "param"
        if name in ctx.enums:
            self.note_path(entry, 0, f"type:{name}")
            return "enum"
        if name in ctx.structs:
            self.note_path(entry, 0, f"type:{name}")
            return "struct"
        known = [*ctx.state, *ctx.params, *ctx.enums, *ctx.structs]
        raise self.error(
            "E701",
            f"`{name}` no es una variable de estado, una opción ni un tipo del juego",
            span,
            _close(name, known)
            or "para acciones y nodos escribe `action nombre: …` o `node Nombre: …`",
        )

    # --- pistas ---------------------------------------------------------------------------------

    def hint(self, entry: ast.UiEntry, kind: str, hint: ast.UiHint) -> None:
        if hint.name not in ALLOWED[kind]:
            what = {
                "state": "una variable de estado",
                "param": "una opción",
                "enum": "un enumerado",
                "struct": "un struct",
                "action": "una acción",
                "action_param": "un parámetro de acción",
                "node": "un nodo",
                "seats": "seats",
            }[kind]
            raise self.error(
                "E702",
                f"`{hint.name}` no es una pista para {what}",
                hint.span,
                "se admiten: " + ", ".join(ALLOWED[kind]),
            )
        name = entry.path[-1] if entry.path else ""
        match kind:
            case "state":
                self.state_hint(name, hint)
            case "param":
                self.put("params", name, "label", self.text_arg(hint))
            case "enum" | "struct":
                self.type_hint(name, kind, hint)
            case "action":
                self.put("actions", name, "label", self.text_arg(hint))
            case "action_param":
                self.param_hint(entry.path[0], name, hint)
            case "node":
                self.put("nodes", name, "label", self.text_arg(hint))
            case "seats":
                self.seats_hint(hint)

    def put(self, section: str, name: str, key: str, value: Any) -> None:
        self.ir.setdefault(section, {}).setdefault(name, {})[key] = value

    def state_hint(self, name: str, hint: ast.UiHint) -> None:
        ty = self.ctx.state[name]
        base = ty.inner if ty.kind == "per_player" else ty
        if hint.name == "label":
            self.put("state", name, "label", self.text_arg(hint))
            return
        if hint.name == "place":
            where = self.name_arg(hint, PLACES)
            if where == "seats" and ty.kind != "per_player":
                raise self.error(
                    "E703",
                    "place(seats) es para variables per_player (una por asiento)",
                    hint.span,
                )
            self.put("state", name, "place", where)
            return
        self.no_args(hint)
        if not _fits_widget(hint.name, base):
            raise self.error(
                "E702",
                f"`{hint.name}` no sirve para dibujar `{name}`, que es `{ty}`",
                hint.span,
                _widget_help(hint.name),
            )
        self.put("state", name, "widget", hint.name)

    def type_hint(self, name: str, kind: str, hint: ast.UiHint) -> None:
        if hint.name == "label":
            self.put("types", name, "label", self.text_arg(hint))
            return
        if hint.name == "card":
            self.put("types", name, "card", self.card_args(name, kind, hint))
            return
        values = self.ctx.enums[name]
        named = self.named_args(hint)
        out: dict[str, Any] = {}
        for key, value, span in named:
            if key not in values:
                raise self.error(
                    "E703", f"`{name}` no tiene el valor `{key}`", span, _close(key, values)
                )
            self.note(Span(span.source, span.start, span.start + len(key)), f"value:{name}.{key}")
            if hint.name == "labels":
                out[key] = self.text_value(value, span)
            else:
                text = self.plain_text(value, span)
                if hint.name == "colors" and not COLOR.match(text):
                    raise self.error(
                        "E703", f"color no válido: {text!r}", span, 'usa "#rgb" o "#rrggbb"'
                    )
                out[key] = text
        self.put("types", name, hint.name, out)

    def card_args(self, name: str, kind: str, hint: ast.UiHint) -> dict[str, str]:
        if kind == "enum":
            self.no_args(hint)
            return {}
        fields = self.ctx.structs[name]
        out: dict[str, str] = {}
        for key, value, span in self.named_args(hint):
            if key not in ("rank", "suit"):
                raise self.error("E703", f"card(…) admite rank y suit, no `{key}`", span)
            if not isinstance(value, ast.UiName) or value.name not in fields:
                shown = value.name if isinstance(value, ast.UiName) else value
                raise self.error(
                    "E703",
                    f"`{name}` no tiene el campo `{shown}`",
                    span,
                    _close(str(shown), fields),
                )
            if fields[value.name].kind not in ("enum", "Int"):
                raise self.error(
                    "E703", f"el campo `{value.name}` debe ser un enumerado o un Int", span
                )
            self.note(value.span, f"field:{name}.{value.name}")
            out[key] = value.name
        if "rank" not in out:
            raise self.error(
                "E703",
                "card(…) de un struct necesita al menos rank: el campo con el valor de la carta",
                hint.span,
                "por ejemplo: Card: card(rank: rank, suit: suit)",
            )
        return out

    def param_hint(self, action: str, param: str, hint: ast.UiHint) -> None:
        params = self.ir.setdefault("actions", {}).setdefault(action, {})
        target = params.setdefault("params", {}).setdefault(param, {})
        if hint.name == "label":
            target["label"] = self.text_arg(hint)
            return
        types = self.ctx.actions[action][param]
        var = self.name_arg(hint)
        if var not in self.ctx.state:
            raise self.error(
                "E703",
                f"`{var}` no es una variable de estado",
                hint.span,
                _close(var, self.ctx.state),
            )
        arg = (hint.args or [None])[0]
        if arg is not None and isinstance(arg.value, ast.UiName):
            self.note(arg.value.span, f"state:{var}")
        vt = self.ctx.state[var]
        if hint.name in ("cell", "column", "row"):
            if vt.kind != "grid":
                raise self.error("E703", f"`{var}` no es una rejilla (Grid)", hint.span)
            want = T.CELL if hint.name == "cell" else T.INT
            if not all(T.assignable(t, want) for t in types):
                raise self.error(
                    "E703",
                    f"{hint.name}({var}) da {'una casilla' if hint.name == 'cell' else 'un Int'}"
                    f" y el parámetro `{param}` es `{types[0]}`",
                    hint.span,
                )
        else:  # pick
            base = vt.inner if vt.kind == "per_player" else vt
            item = T.elem(base)
            if item is None or base.kind == "map":
                raise self.error("E703", f"`{var}` no es una colección de la que elegir", hint.span)
            ok = (T.list_(item), T.set_(item), item)
            if not all(any(T.assignable(t, w) for w in ok) for t in types):
                raise self.error(
                    "E703",
                    f"pick({var}) elige `{item}` (o una lista de ellos) y el parámetro `{param}`"
                    f" es `{types[0]}`",
                    hint.span,
                )
        target["input"] = hint.name
        target["of"] = var

    def seats_hint(self, hint: ast.UiHint) -> None:
        values = self.positional(hint)
        if not values:
            raise self.error("E703", f"{hint.name}(…) necesita al menos un valor", hint.span)
        out = []
        for value, span in values:
            if hint.name == "colors":
                text = self.plain_text(value, span)
                if not COLOR.match(text):
                    raise self.error("E703", f"color no válido: {text!r}", span)
                out.append(text)
            else:
                out.append(self.text_value(value, span))
        self.ir.setdefault("seats", {})[hint.name] = out

    # --- argumentos -----------------------------------------------------------------------------

    def no_args(self, hint: ast.UiHint) -> None:
        if hint.args:
            raise self.error("E703", f"`{hint.name}` no lleva argumentos", hint.span)

    def positional(self, hint: ast.UiHint) -> list[tuple[Any, Span]]:
        args = hint.args or []
        if any(a.key is not None for a in args):
            raise self.error("E703", f"`{hint.name}(…)` no lleva argumentos con nombre", hint.span)
        return [(a.value, a.span) for a in args]

    def named_args(self, hint: ast.UiHint) -> list[tuple[str, Any, Span]]:
        args = hint.args or []
        if not args:
            raise self.error("E703", f"`{hint.name}(…)` necesita argumentos", hint.span)
        out: list[tuple[str, Any, Span]] = []
        seen: set[str] = set()
        for a in args:
            if a.key is None:
                raise self.error(
                    "E703",
                    f"los argumentos de `{hint.name}` llevan nombre (Valor: …)",
                    a.span,
                )
            if a.key in seen:
                raise self.error("E703", f"`{a.key}` repetido", a.span)
            seen.add(a.key)
            out.append((a.key, a.value, a.span))
        return out

    def single(self, hint: ast.UiHint) -> tuple[Any, Span]:
        values = self.positional(hint)
        if len(values) != 1:
            raise self.error("E703", f"`{hint.name}(…)` lleva un argumento", hint.span)
        return values[0]

    def text_arg(self, hint: ast.UiHint) -> Any:
        return self.text_value(*self.single(hint))

    def name_arg(self, hint: ast.UiHint, allowed: tuple[str, ...] | None = None) -> str:
        value, span = self.single(hint)
        if not isinstance(value, ast.UiName):
            raise self.error("E703", f"`{hint.name}(…)` lleva un nombre", span)
        if allowed is not None and value.name not in allowed:
            raise self.error(
                "E703",
                f"`{value.name}` no vale aquí",
                span,
                "se admiten: " + ", ".join(allowed),
            )
        return value.name

    def text_value(self, value: Any, span: Span) -> Any:
        if not isinstance(value, ast.Text):
            raise self.error("E703", 'se esperaba un texto ("…" o { es: "…", en: "…" })', span)
        return value.to_ir()

    def plain_text(self, value: Any, span: Span) -> str:
        if not isinstance(value, ast.Text) or not isinstance(value.value, str):
            raise self.error("E703", 'se esperaba un texto simple ("…")', span)
        return value.value


def _fits_widget(widget: str, t: Ty) -> bool:
    if t.is_unknown or widget == "hidden":
        return True
    item = T.elem(t) if t.kind in ("list", "set", "zone", "bag") else None
    match widget:
        case "grid":
            return t.kind == "grid"
        case "hand" | "pile" | "deck" | "row":
            return item is not None
        case "dice":
            return t.kind == "Int" or (item is not None and item.kind == "Int")
        case "counter" | "chips":
            return t.kind in ("Int", "Real")
        case "seat":
            return t.kind == "Seat" or (t.kind == "option" and t.inner.kind == "Seat")
    return False


def _widget_help(widget: str) -> str:
    return {
        "grid": "grid es para rejillas (Grid[…] of …)",
        "hand": "hand, pile, deck y row son para listas, conjuntos, zonas y bolsas",
        "pile": "hand, pile, deck y row son para listas, conjuntos, zonas y bolsas",
        "deck": "hand, pile, deck y row son para listas, conjuntos, zonas y bolsas",
        "row": "hand, pile, deck y row son para listas, conjuntos, zonas y bolsas",
        "dice": "dice es para un Int o una colección de Int",
        "counter": "counter y chips son para números",
        "chips": "counter y chips son para números",
        "seat": "seat es para un Seat",
    }.get(widget, "")


def _close(name: str, candidates: Any) -> str | None:
    found = difflib.get_close_matches(name, list(candidates), n=1, cutoff=0.7)
    return f"¿quisiste decir `{found[0]}`?" if found else None


def _target_text(entry: ast.UiEntry) -> str:
    match entry.target:
        case "action":
            return "action " + ".".join(entry.path)
        case "node":
            return "node " + entry.path[0]
        case "seats":
            return "seats"
    return entry.path[0]


def check_ui(
    entries: list[ast.UiEntry],
    ctx: UiContext,
    diagnostics: Diagnostics,
    index: SymbolIndex | None = None,
) -> dict[str, Any]:
    """Comprueba las pistas y devuelve la clave `ui` de la IR (vacía si no hay ninguna). Las
    pistas de tipos importados que no llegan a la IR se descartan."""
    ui = UiChecker(ctx, diagnostics, index).run(entries)
    types = ui.get("types")
    if types is not None:
        kept = {k: v for k, v in types.items() if k in ctx.emitted_types}
        if kept:
            ui["types"] = kept
        else:
            del ui["types"]
    return ui


# --- IR → texto (descompilador) ------------------------------------------------------------------


def _text(value: Any) -> ast.Text:
    return ast.Text(value if isinstance(value, str) else dict(value))


def _label(value: Any) -> ast.UiHint:
    return ast.UiHint("label", [ast.UiArg(None, _text(value))])


def entries_from_ir(ui: dict[str, Any]) -> list[ast.UiEntry]:
    """Las entradas de `ui { … }` que se traducen exactamente a la clave `ui` de la IR."""
    out: list[ast.UiEntry] = []

    def add(target: str, path: list[str], hints: list[ast.UiHint]) -> None:
        if hints:
            out.append(ast.UiEntry(target=target, path=path, hints=hints))

    for name, spec in ui.get("state", {}).items():
        hints = []
        if "widget" in spec:
            hints.append(ast.UiHint(spec["widget"]))
        if "place" in spec:
            hints.append(ast.UiHint("place", [ast.UiArg(None, ast.UiName(spec["place"]))]))
        if "label" in spec:
            hints.append(_label(spec["label"]))
        add("name", [name], hints)
    for name, spec in ui.get("params", {}).items():
        add("name", [name], [_label(spec["label"])] if "label" in spec else [])
    for name, spec in ui.get("types", {}).items():
        hints = []
        for key in ("symbols", "colors"):
            if key in spec:
                args = [ast.UiArg(k, ast.Text(v)) for k, v in spec[key].items()]
                hints.append(ast.UiHint(key, args))
        if "labels" in spec:
            args = [ast.UiArg(k, _text(v)) for k, v in spec["labels"].items()]
            hints.append(ast.UiHint("labels", args))
        if "card" in spec:
            card = spec["card"]
            args = [ast.UiArg(k, ast.UiName(card[k])) for k in ("rank", "suit") if k in card]
            hints.append(ast.UiHint("card", args or None))
        if "label" in spec:
            hints.append(_label(spec["label"]))
        add("name", [name], hints)
    for name, spec in ui.get("actions", {}).items():
        add("action", [name], [_label(spec["label"])] if "label" in spec else [])
        for param, pspec in spec.get("params", {}).items():
            hints = []
            if "input" in pspec:
                arg = ast.UiArg(None, ast.UiName(pspec["of"]))
                hints.append(ast.UiHint(pspec["input"], [arg]))
            if "label" in pspec:
                hints.append(_label(pspec["label"]))
            add("action", [name, param], hints)
    for name, spec in ui.get("nodes", {}).items():
        add("node", [name], [_label(spec["label"])] if "label" in spec else [])
    seats = ui.get("seats", {})
    hints = []
    if "colors" in seats:
        hints.append(ast.UiHint("colors", [ast.UiArg(None, ast.Text(c)) for c in seats["colors"]]))
    if "names" in seats:
        hints.append(ast.UiHint("names", [ast.UiArg(None, _text(n)) for n in seats["names"]]))
    add("seats", [], hints)
    return out
