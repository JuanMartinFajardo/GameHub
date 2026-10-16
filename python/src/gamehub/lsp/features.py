# SPDX-License-Identifier: Apache-2.0
"""Las funciones del servidor de lenguaje, sin depender del transporte: reciben el análisis de un
documento y una posición, y devuelven objetos del LSP. Así se prueban sin un cliente.

Cuando el texto tiene errores de sintaxis no se compila; lo que necesita los símbolos (hover,
autocompletado de nombres…) usa entonces el último análisis que compiló (`last_good`).
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from lsprotocol import types

from gamehub.lang import ast
from gamehub.lang.diagnostics import Severity
from gamehub.lang.lexer import KEYWORDS
from gamehub.lang.parser import NODE_KINDS
from gamehub.lang.printer import format_file
from gamehub.lang.reference import (
    CONTEXT,
    EXPRESSION_KEYWORDS,
    FUNCTIONS,
    GAME_SECTIONS,
    NODE_MEMBERS,
    STATEMENTS,
    TYPES,
)
from gamehub.lang.reference import (
    NODE_KINDS as NODE_KIND_DOCS,
)
from gamehub.lang.source import Span
from gamehub.lang.symbols import RENAMABLE, Occurrence, Symbol, SymbolIndex
from gamehub.lang.ui import ALLOWED as UI_ALLOWED
from gamehub.lsp.analysis import Analysis, Positions, path_to_uri
from gamehub.lsp.context import Context, context_at
from gamehub.studio.edits import EditError, plan_rename, text_changes

KIND_NAMES = {
    "state": "variable de estado",
    "param": "opción de la partida",
    "fn": "función",
    "type": "tipo",
    "value": "valor de enumerado",
    "field": "campo",
    "node": "nodo",
    "action": "acción",
    "aparam": "parámetro de la acción",
    "local": "variable local",
    "game": "juego",
}

COMPLETION_KINDS = {
    "state": types.CompletionItemKind.Variable,
    "param": types.CompletionItemKind.Constant,
    "fn": types.CompletionItemKind.Function,
    "type": types.CompletionItemKind.Class,
    "value": types.CompletionItemKind.EnumMember,
    "field": types.CompletionItemKind.Field,
    "node": types.CompletionItemKind.Module,
    "action": types.CompletionItemKind.Method,
    "aparam": types.CompletionItemKind.Variable,
    "local": types.CompletionItemKind.Variable,
    "game": types.CompletionItemKind.Module,
}

META_KEYS = ("id", "version", "title", "description", "authors", "license", "tags")
TEST_STEPS = ("players", "params", "seed", "play", "chance", "expect", "set")
UI_TARGET_WORDS = ("action", "node", "seats")
ANNOTATIONS = {
    "visible": "Quién ve el valor: @visible(all | none | owner | condición)",
    "size_visible": "Quién ve el tamaño de una zona o bolsa: @size_visible(…)",
    "doc": 'Documentación traducible: @doc({ es: "…", en: "…" })',
}
WINDOW_MODES = ("priority", "collect", "race")
SUGGESTION = re.compile(r"¿quisiste decir `([^`]+)`\?")
WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _md(value: str) -> types.MarkupContent:
    return types.MarkupContent(kind=types.MarkupKind.Markdown, value=value)


def _code(text: str) -> str:
    return f"```nomos\n{text}\n```"


class _Locations:
    """Posiciones LSP de spans de cualquier archivo (los de otros archivos, p. ej. la biblioteca
    estándar, se convierten con su propio texto)."""

    def __init__(self, analysis: Analysis) -> None:
        self.analysis = analysis
        self.cache: dict[str, Positions] = {analysis.name: analysis.positions}

    def location(self, span: Span) -> types.Location | None:
        source = span.source
        if source is None:
            return None
        if source.name == self.analysis.name:
            return types.Location(self.analysis.uri, self.analysis.positions.span(span))
        if source.path is None:
            return None
        positions = self.cache.get(source.name)
        if positions is None:
            positions = self.cache[source.name] = Positions(source.text)
        return types.Location(path_to_uri(source.path), positions.span(span))


# --- Diagnósticos ---------------------------------------------------------------------------------


def diagnostics(analysis: Analysis) -> list[types.Diagnostic]:
    out: list[types.Diagnostic] = []
    locations = _Locations(analysis)
    for d in analysis.diagnostics.items:
        span = d.span
        mine = span is not None and span.source is not None and span.source.name == analysis.name
        if mine:
            assert span is not None
            rng = analysis.positions.span(span)
            message = d.message
        else:
            # Un error en otro archivo (un módulo importado): se enseña al principio.
            rng = analysis.positions.range(0, 0)
            message = f"{d.message} (en {span})" if span is not None else d.message
        details = [f"nota: {n}" for n in d.notes]
        if d.help:
            details.append(f"ayuda: {d.help}")
        related = []
        for label in d.labels:
            if label.primary or label.span.source is None:
                continue
            location = locations.location(label.span)
            if location is not None:
                info = types.DiagnosticRelatedInformation(location, label.message or "aquí")
                related.append(info)
        out.append(
            types.Diagnostic(
                range=rng,
                message="\n".join([message, *details]),
                severity=(
                    types.DiagnosticSeverity.Error
                    if d.severity is Severity.ERROR
                    else types.DiagnosticSeverity.Warning
                ),
                code=d.code,
                source="nomos",
                related_information=related or None,
            )
        )
    return out


# --- Símbolos -------------------------------------------------------------------------------------


def _best(analysis: Analysis, last_good: Analysis | None) -> Analysis:
    """El análisis con símbolos: el actual si compiló; si no, el último que compiló."""
    if analysis.result is not None or last_good is None:
        return analysis
    return last_good


def symbol_at(analysis: Analysis, offset: int) -> tuple[Occurrence, Symbol | None] | None:
    occ = analysis.index.at(analysis.name, offset)
    if occ is None:
        return None
    return occ, analysis.index.symbols.get(occ.key)


def _describe(key: str, symbol: Symbol | None) -> str:
    kind, _, name = key.partition(":")
    if kind == "builtin":
        entry = FUNCTIONS.get(name)
        if entry is None:
            return _code(name)
        return "\n\n".join([_code("\n".join(entry.signatures)), entry.doc])
    if kind == "context":
        ty, doc = CONTEXT.get(name, ("", ""))
        return "\n\n".join([_code(f"{name}: {ty}"), doc])
    if symbol is None:
        return _code(name)
    parts = [_code(symbol.detail or symbol.name), f"*{KIND_NAMES.get(symbol.kind, symbol.kind)}*"]
    if symbol.doc:
        parts.append(symbol.doc)
    return "\n\n".join(parts)


def hover(analysis: Analysis, offset: int) -> types.Hover | None:
    found = symbol_at(analysis, offset)
    if found is not None:
        occ, symbol = found
        return types.Hover(_md(_describe(occ.key, symbol)), analysis.positions.span(occ.span))
    word = _word_at(analysis.text, offset)
    if word is not None:
        start, end, text = word
        doc = _keyword_doc(text)
        if doc is not None:
            return types.Hover(_md(doc), analysis.positions.range(start, end))
    typed = analysis.index.type_at(analysis.name, offset)
    if typed is not None:
        span, ty = typed
        shown = analysis.text[span.start : span.end]
        if len(shown) > 60:
            shown = shown[:57] + "…"
        return types.Hover(_md(f"`{shown}`: `{ty}`"), analysis.positions.span(span))
    return None


def _keyword_doc(word: str) -> str | None:
    if word in NODE_KIND_DOCS:
        return f"**{word}**: {NODE_KIND_DOCS[word]}"
    if word in STATEMENTS:
        return _code(STATEMENTS[word])
    if word in GAME_SECTIONS:
        return _code(GAME_SECTIONS[word])
    if word in TYPES:
        return f"**{word}**: {TYPES[word]}"
    return None


def _word_at(text: str, offset: int) -> tuple[int, int, str] | None:
    start = offset
    while start > 0 and (text[start - 1].isalnum() or text[start - 1] == "_"):
        start -= 1
    end = offset
    while end < len(text) and (text[end].isalnum() or text[end] == "_"):
        end += 1
    if start == end:
        return None
    return start, end, text[start:end]


def definition(analysis: Analysis, offset: int) -> list[types.Location]:
    found = symbol_at(analysis, offset)
    if found is None or found[1] is None:
        return []
    locations = _Locations(analysis)
    return [loc for span in found[1].decls if (loc := locations.location(span)) is not None]


def references(analysis: Analysis, offset: int, include_declaration: bool) -> list[types.Location]:
    found = symbol_at(analysis, offset)
    if found is None:
        return []
    locations = _Locations(analysis)
    out = []
    for occ in analysis.index.of(found[0].key):
        if occ.decl and not include_declaration:
            continue
        location = locations.location(occ.span)
        if location is not None:
            out.append(location)
    return out


def highlights(analysis: Analysis, offset: int) -> list[types.DocumentHighlight]:
    found = symbol_at(analysis, offset)
    if found is None:
        return []
    return [
        types.DocumentHighlight(
            analysis.positions.span(o.span),
            types.DocumentHighlightKind.Write if o.decl else types.DocumentHighlightKind.Read,
        )
        for o in analysis.index.of(found[0].key, analysis.name)
    ]


def prepare_rename(analysis: Analysis, offset: int) -> types.PrepareRenamePlaceholder | None:
    found = symbol_at(analysis, offset)
    if found is None or found[1] is None:
        return None
    occ, symbol = found
    if symbol is None or symbol.kind not in RENAMABLE:
        return None
    if not any(d.source is not None and d.source.name == analysis.name for d in symbol.decls):
        return None
    return types.PrepareRenamePlaceholder(analysis.positions.span(occ.span), symbol.name)


def rename(analysis: Analysis, offset: int, new_name: str) -> types.WorkspaceEdit:
    """Lanza `EditError` si no se puede (nombre no válido, choque…)."""
    found = symbol_at(analysis, offset)
    if found is None or found[1] is None:
        raise EditError("aquí no hay nada que renombrar")
    plan = plan_rename(
        analysis.source,
        found[0].key,
        new_name,
        index=analysis.index,
        compiled_ok=analysis.result is not None and analysis.result.ok,
    )
    edits = [
        types.TextEdit(analysis.positions.range(start, end), new_name) for start, end in plan.spans
    ]
    return types.WorkspaceEdit(changes={analysis.uri: edits})


# --- Formato --------------------------------------------------------------------------------------


def formatting(analysis: Analysis) -> list[types.TextEdit] | None:
    if not analysis.syntax_ok:
        return None
    formatted = format_file(analysis.tree)
    return [
        types.TextEdit(analysis.positions.range(c.start, c.end), c.insert)
        for c in text_changes(analysis.text, formatted)
    ]


# --- Esquema del documento y plegado --------------------------------------------------------------


def document_symbols(analysis: Analysis) -> list[types.DocumentSymbol]:
    positions = analysis.positions

    def sym(
        name: str,
        kind: types.SymbolKind,
        item: ast.Node,
        detail: str | None = None,
        children: list[types.DocumentSymbol] | None = None,
    ) -> types.DocumentSymbol:
        rng = positions.span(item.span)
        selection = positions.span(item.name_span()) if item.name_spans else rng
        return types.DocumentSymbol(
            name=name,
            kind=kind,
            range=rng,
            selection_range=selection,
            detail=detail,
            children=children or None,
        )

    def node(n: ast.NodeDecl) -> types.DocumentSymbol:
        children = []
        for m in n.members:
            if isinstance(m, ast.ActionDecl):
                children.append(sym(m.name, types.SymbolKind.Method, m, "acción"))
            elif isinstance(m, ast.NodeDecl):
                children.append(node(m))
        return sym(n.name, types.SymbolKind.Module, n, n.kind, children)

    def game_items(items: list[ast.Item]) -> list[types.DocumentSymbol]:
        out = []
        for item in items:
            match item:
                case ast.StateBlock(vars=variables):
                    out.extend(
                        sym(v.name, types.SymbolKind.Variable, v, "estado") for v in variables
                    )
                case ast.ParamsBlock(items=params):
                    out.extend(
                        sym(p.name, types.SymbolKind.Constant, p, "opción")
                        for p in params
                        if isinstance(p, ast.ParamDecl)
                    )
                case ast.EnumDecl():
                    out.append(sym(item.name, types.SymbolKind.Enum, item, "enum"))
                case ast.StructDecl():
                    out.append(sym(item.name, types.SymbolKind.Struct, item, "struct"))
                case ast.FnDecl():
                    out.append(sym(item.name, types.SymbolKind.Function, item, "fn"))
                case ast.FlowBlock(items=flow_items):
                    nodes = [node(n) for n in flow_items if isinstance(n, ast.NodeDecl)]
                    out.append(
                        types.DocumentSymbol(
                            name="flow",
                            kind=types.SymbolKind.Namespace,
                            range=positions.span(item.span),
                            selection_range=positions.span(item.span),
                            children=nodes or None,
                        )
                    )
                case ast.TestDecl():
                    out.append(sym(item.name, types.SymbolKind.Event, item, "test"))
        return out

    out: list[types.DocumentSymbol] = []
    for item in analysis.tree.items:
        if isinstance(item, ast.GameDecl):
            out.append(sym(item.name, types.SymbolKind.Class, item, "game", game_items(item.items)))
        elif isinstance(item, ast.GameAlias):
            out.append(sym(item.name, types.SymbolKind.Class, item, item.combinator))
        else:
            out.extend(game_items([item]))
    return out


def folding_ranges(analysis: Analysis) -> list[types.FoldingRange]:
    out: list[types.FoldingRange] = []
    source = analysis.source

    def visit(node: object) -> None:
        if isinstance(node, ast.Item) and node.span.source is source:
            first, last = node.span.line, node.span.end_line
            if last > first:
                out.append(types.FoldingRange(start_line=first - 1, end_line=last - 1))
        if isinstance(node, ast.Node):
            for value in vars(node).values():
                if isinstance(value, list):
                    for x in value:
                        if isinstance(x, ast.Item):
                            visit(x)

    for item in analysis.tree.items:
        visit(item)
    return out


# --- Arreglos rápidos -----------------------------------------------------------------------------


def code_actions(
    analysis: Analysis, diagnostics_in_range: Iterable[types.Diagnostic]
) -> list[types.CodeAction]:
    """Arreglos para los errores que traen una sugerencia («¿quisiste decir `x`?»)."""
    out = []
    for d in diagnostics_in_range:
        match = SUGGESTION.search(d.message)
        if match is None:
            continue
        start = analysis.positions.offset(d.range.start)
        end = analysis.positions.offset(d.range.end)
        if not WORD.fullmatch(analysis.text[start:end]):
            continue
        suggestion = match.group(1)
        out.append(
            types.CodeAction(
                title=f"Cambiar por `{match.group(1)}`",
                kind=types.CodeActionKind.QuickFix,
                diagnostics=[d],
                is_preferred=True,
                edit=types.WorkspaceEdit(
                    changes={analysis.uri: [types.TextEdit(d.range, suggestion)]}
                ),
            )
        )
    return out


# --- Ayuda de firmas ------------------------------------------------------------------------------


def signature_help(
    analysis: Analysis, offset: int, last_good: Analysis | None = None
) -> types.SignatureHelp | None:
    ctx = context_at(analysis.text, offset)
    if not ctx.parens:
        return None
    opener, before = ctx.parens[-1]
    if opener.kind != "(" or not before or before[-1].kind != "ident":
        return None
    name = before[-1].text
    tail = ctx.before[ctx.before.index(opener) + 1 :] if opener in ctx.before else []
    depth = 0
    active = 0
    for tok in tail:
        if tok.kind in ("(", "["):
            depth += 1
        elif tok.kind in (")", "]"):
            depth -= 1
        elif tok.kind == "," and depth == 0:
            active += 1
    signatures: list[str] = []
    doc = ""
    entry = FUNCTIONS.get(name)
    if entry is not None:
        signatures = list(entry.signatures)
        doc = entry.doc
    else:
        best = _best(analysis, last_good)
        symbol = best.index.symbols.get(f"fn:{name}")
        if symbol is None:
            return None
        signatures = [symbol.detail.removeprefix("fn ")]
        doc = symbol.doc or ""
    infos = []
    for signature in signatures:
        inside = signature[signature.find("(") + 1 : signature.rfind(")")]
        params = [p.strip() for p in _split_params(inside)] if inside.strip() else []
        infos.append(
            types.SignatureInformation(
                label=signature,
                documentation=_md(doc) if doc else None,
                parameters=[types.ParameterInformation(label=p) for p in params],
            )
        )
    return types.SignatureHelp(signatures=infos, active_signature=0, active_parameter=active)


def _split_params(text: str) -> list[str]:
    out, depth, current = [], 0, ""
    for ch in text:
        if ch in "([<":
            depth += 1
        elif ch in ")]>":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(current)
            current = ""
        else:
            current += ch
    if current.strip():
        out.append(current)
    return out


# --- Autocompletado -------------------------------------------------------------------------------


class _Items:
    def __init__(self, analysis: Analysis, ctx: Context, offset: int) -> None:
        self.analysis = analysis
        self.ctx = ctx
        self.range = analysis.positions.range(ctx.prefix_start, offset)
        self.items: dict[str, types.CompletionItem] = {}

    def add(
        self,
        label: str,
        kind: types.CompletionItemKind,
        *,
        detail: str | None = None,
        doc: str | None = None,
        insert: str | None = None,
        rank: int = 5,
    ) -> None:
        if label in self.items:
            return
        self.items[label] = types.CompletionItem(
            label=label,
            kind=kind,
            detail=detail,
            documentation=_md(doc) if doc else None,
            sort_text=f"{rank}{label.lower()}",
            filter_text=label,
            text_edit=types.TextEdit(self.range, insert if insert is not None else label),
        )

    def keywords(
        self, words: Iterable[str], docs: dict[str, str] | None = None, rank: int = 6
    ) -> None:
        for w in words:
            doc = (docs or {}).get(w)
            shown = _code(doc) if doc else None
            self.add(w, types.CompletionItemKind.Keyword, doc=shown, rank=rank)

    def symbols(self, index: SymbolIndex, kinds: Iterable[str], rank: int = 3) -> None:
        wanted = set(kinds)
        for symbol in index.symbols.values():
            if symbol.kind in wanted:
                self.add(
                    symbol.name,
                    COMPLETION_KINDS.get(symbol.kind, types.CompletionItemKind.Text),
                    detail=symbol.detail,
                    doc=symbol.doc,
                    rank=rank,
                )

    def result(self) -> types.CompletionList:
        return types.CompletionList(is_incomplete=False, items=list(self.items.values()))


def completion(
    analysis: Analysis, offset: int, last_good: Analysis | None = None
) -> types.CompletionList:
    ctx = context_at(analysis.text, offset)
    items = _Items(analysis, ctx, offset)
    best = _best(analysis, last_good)
    index = best.index
    block = ctx.block
    last = ctx.last_text()
    if ctx.annotation:
        for name, doc in ANNOTATIONS.items():
            items.add(name, types.CompletionItemKind.Keyword, doc=doc, insert=f"{name}(")
        return items.result()
    if last == "->":
        for name in _node_names(analysis):
            items.add(name, types.CompletionItemKind.Module, detail="nodo", rank=1)
        if ctx.in_phase():
            items.add("exit", types.CompletionItemKind.Keyword, doc="Sale de la fase", rank=2)
        return items.result()
    if _type_position(ctx):
        for name, doc in TYPES.items():
            items.add(name, types.CompletionItemKind.Class, doc=doc, rank=2)
        items.symbols(index, ["type"], rank=1)
        return items.result()
    if last == "." and len(ctx.before) >= 2:
        _members(items, best, ctx)
        return items.result()
    if ctx.line_start:
        if _line_start(items, ctx, best, analysis):
            return items.result()
    elif block == "ui" and last in (":", ","):
        target = ctx.before[0].text if ctx.before else ""
        kind = _ui_kind(index, ctx)
        for hint in UI_ALLOWED.get(kind, sorted({h for v in UI_ALLOWED.values() for h in v})):
            items.add(hint, types.CompletionItemKind.Property, detail=f"pista para {target}")
        return items.result()
    elif block == "ui" and ctx.before and ctx.before[0].kind == "action":
        items.symbols(index, ["action"], rank=1)
        return items.result()
    elif block == "ui" and ctx.before and ctx.before[0].text == "node":
        for name in _node_names(analysis):
            items.add(name, types.CompletionItemKind.Module, rank=1)
        return items.result()
    elif last == ":" and len(ctx.before) >= 2 and ctx.before[-2].text == "mode":
        for mode in WINDOW_MODES:
            items.add(mode, types.CompletionItemKind.EnumMember, rank=1)
        return items.result()
    elif block == "test" and ctx.before and ctx.before[0].text in ("play", "legal", "illegal"):
        items.symbols(index, ["action"], rank=1)
    _expression(items, best, ctx, offset)
    return items.result()


def _line_start(items: _Items, ctx: Context, best: Analysis, analysis: Analysis) -> bool:
    """Completa el principio de una línea; devuelve False si ahí también vale una expresión."""
    block = ctx.block
    index = best.index
    match block:
        case "file":
            items.keywords(["import", "game", "enum", "struct", "fn"])
            return True
        case "game":
            items.keywords([*GAME_SECTIONS, "override", "remove", "extend"], GAME_SECTIONS, rank=1)
            return True
        case "flow":
            items.keywords(["start"], rank=1)
            items.keywords(NODE_KINDS, rank=2)
            return True
        case "meta":
            for key in META_KEYS:
                items.add(key, types.CompletionItemKind.Property, insert=f"{key}: ", rank=1)
            return True
        case "ui":
            items.symbols(index, ["state", "param", "type"], rank=1)
            items.keywords(UI_TARGET_WORDS, rank=2)
            return True
        case "test":
            items.keywords(TEST_STEPS, rank=1)
            return True
        case "state" | "params" | "struct" | "enum":
            return True
    if block.startswith("node:"):
        kind = block.split(":", 1)[1]
        for key in NODE_MEMBERS[kind]:
            items.add(key, types.CompletionItemKind.Property, insert=f"{key}: ", rank=1)
        if kind in ("decision", "simultaneous", "window"):
            items.keywords(["action"], rank=1)
        if kind == "terminal":
            items.keywords(["let"], rank=2)
        if kind == "phase":
            items.keywords(["start", "on_enter", "on_exit"], rank=1)
            items.keywords(NODE_KINDS, rank=2)
        if kind == "simultaneous":
            items.keywords(["resolve"], rank=2)
        if kind != "terminal":
            items.add("->", types.CompletionItemKind.Keyword, doc="Una transición: -> Nodo when …")
        if kind in ("chance", "auto"):
            items.keywords(STATEMENTS, STATEMENTS)
            items.symbols(index, ["state"], rank=3)
        return True
    if block in ("action", "stmts"):
        items.keywords(STATEMENTS, STATEMENTS, rank=2)
        items.symbols(index, ["state"], rank=1)
        if block == "action":
            items.add("->", types.CompletionItemKind.Keyword, doc="Una transición de la acción")
        return True
    return False


def _type_position(ctx: Context) -> bool:
    before = ctx.before
    if not before:
        return False
    last = before[-1].kind
    if last in ("of", "<") or (last == "ident" and before[-1].text == "per_player"):
        return True
    if last == "," and ctx.parens and ctx.parens[-1][0].kind == "<":
        return True
    if last == "->" and before[0].kind == "fn":
        return True
    if last != ":":
        return False
    if ctx.block in ("state", "params", "struct") and len(before) >= 2:
        return before[-2].kind == "ident"
    if ctx.parens:
        opener, prior = ctx.parens[-1]
        return opener.kind == "(" and bool(prior) and prior[0].kind in ("fn", "action")
    return False


def _ui_kind(index: SymbolIndex, ctx: Context) -> str:
    first = ctx.before[0] if ctx.before else None
    if first is None:
        return ""
    if first.kind == "action":
        return "action_param" if any(t.kind == "." for t in ctx.before) else "action"
    if first.text == "node":
        return "node"
    if first.text == "seats":
        return "seats"
    for prefix, kind in (("state", "state"), ("param", "param")):
        if f"{prefix}:{first.text}" in index.symbols:
            return kind
    symbol = index.symbols.get(f"type:{first.text}")
    if symbol is not None:
        return "enum" if symbol.detail.startswith("enum") else "struct"
    return ""


def _members(items: _Items, best: Analysis, ctx: Context) -> None:
    """Tras `x.`: los valores de un enumerado o los campos de un struct."""
    target = ctx.before[-2]
    index = best.index
    symbol = index.symbols.get(f"type:{target.text}")
    if symbol is not None and symbol.detail.startswith("enum"):
        prefix = f"value:{target.text}."
        for key, value in index.symbols.items():
            if key.startswith(prefix):
                kind = types.CompletionItemKind.EnumMember
                items.add(value.name, kind, detail=value.detail, rank=1)
        items.add("values", types.CompletionItemKind.Property, detail=f"List<{target.text}>")
        return
    struct = _type_of_word(best, target.text)
    if struct is not None:
        prefix = f"field:{struct}."
        for key, value in index.symbols.items():
            if key.startswith(prefix):
                items.add(value.name, types.CompletionItemKind.Field, detail=value.detail, rank=1)
        return
    # Sin saber el tipo: todos los campos de todos los structs.
    items.symbols(index, ["field"], rank=2)


def _type_of_word(best: Analysis, word: str) -> str | None:
    """El tipo de un nombre (si es un struct), según el último análisis."""
    for symbol in best.index.symbols.values():
        if symbol.name == word and symbol.kind in ("state", "local", "aparam", "param"):
            ty = symbol.detail.split(": ", 1)[-1]
            ty = re.sub(r"^per_player ", "", ty)
            if f"type:{ty}" in best.index.symbols:
                return ty
    return None


def _expression(items: _Items, best: Analysis, ctx: Context, offset: int) -> None:
    index = best.index
    # Locales visibles: los declarados antes del cursor en la misma declaración; los parámetros
    # de una acción, solo dentro de esa acción.
    actions = {n for b, n in zip(ctx.blocks, ctx.names, strict=True) if b == "action"}
    if len(ctx.before) >= 2 and ctx.before[0].kind == "action":
        actions.add(ctx.before[1].text)
    for symbol in index.symbols.values():
        if symbol.kind not in ("local", "aparam"):
            continue
        if symbol.kind == "aparam" and symbol.key.split(":", 1)[1].split(".")[0] not in actions:
            continue
        for span in symbol.decls:
            if (
                span.source is not None
                and span.source.name == best.name
                and ctx.scope_start <= span.start < offset
            ):
                items.add(
                    symbol.name,
                    types.CompletionItemKind.Variable,
                    detail=symbol.detail,
                    rank=0,
                )
    items.symbols(index, ["state", "param"], rank=1)
    items.symbols(index, ["fn"], rank=2)
    items.symbols(index, ["value", "type"], rank=3)
    for name, entry in FUNCTIONS.items():
        items.add(
            name,
            types.CompletionItemKind.Function,
            detail=entry.signatures[0],
            doc=entry.doc,
            rank=4,
        )
    for name, (ty, doc) in CONTEXT.items():
        if name in ("payoff", "active") and ctx.block != "test":
            continue
        items.add(name, types.CompletionItemKind.Variable, detail=ty, doc=doc, rank=4)
    items.keywords(EXPRESSION_KEYWORDS, rank=7)
    if ctx.block.startswith("node:") or ctx.block in ("action", "stmts"):
        items.keywords([k for k in ("when", "requires") if k in KEYWORDS], rank=7)


def _node_names(analysis: Analysis) -> list[str]:
    names: list[str] = []

    def visit(items: list[ast.Item]) -> None:
        for item in items:
            if isinstance(item, ast.NodeDecl):
                names.append(item.name)
                visit(item.members)

    for game in analysis.tree.items:
        if isinstance(game, ast.GameDecl):
            for item in game.items:
                if isinstance(item, ast.FlowBlock):
                    visit(item.items)
    return names
