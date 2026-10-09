# SPDX-License-Identifier: Apache-2.0
"""Análisis léxico y sintáctico de Nomos, diagnósticos y formateador."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import pytest

from gamehub.cli import main
from gamehub.lang import ast
from gamehub.lang.diagnostics import CompileError, Diagnostics, render
from gamehub.lang.layout import LINE, concat, fill, group, nest, text
from gamehub.lang.layout import render as render_doc
from gamehub.lang.lexer import tokenize
from gamehub.lang.parser import parse, parse_expression, parse_text
from gamehub.lang.printer import Printer, decimal_text, format_file, format_source
from gamehub.lang.source import Source

GAMES = sorted((Path(__file__).resolve().parents[2] / "games").glob("*/*.game"))
KITCHEN_SINK = Path(__file__).resolve().parent / "fixtures" / "kitchen-sink.game"
FORMATTED = [*GAMES, KITCHEN_SINK]


def kinds(text: str) -> list[str]:
    return [t.kind for t in tokenize(Source("t", text), Diagnostics())]


def expr(text: str) -> ast.Expr:
    e, diagnostics = parse_expression(text)
    assert not diagnostics.has_errors, [str(d) for d in diagnostics]
    return e


def show(e: ast.Expr) -> str:
    return render_doc(Printer().expr(e))


# --- léxico -------------------------------------------------------------------------------------


def test_newlines_only_count_outside_parentheses() -> None:
    assert kinds("f(a,\n b)\nx") == [
        "ident", "(", "ident", ",", "ident", ")", "newline", "ident", "newline", "eof",
    ]  # fmt: skip
    assert kinds("{\na\n}") == ["{", "newline", "ident", "newline", "}", "newline", "eof"]
    # Dentro de llaves vuelven a contar aunque estén entre paréntesis.
    assert "newline" in kinds("f(Card {\n x: 1 })")[3:6]


def test_numbers_ranges_and_decimals() -> None:
    tokens = tokenize(Source("t", "0..5 0..<n 2.5 1_000"), Diagnostics())
    assert [t.kind for t in tokens[:7]] == ["int", "..", "int", "int", "..<", "ident", "decimal"]
    assert tokens[6].value == Fraction(5, 2)
    assert tokens[7].value == 1000


def test_strings_and_escapes() -> None:
    tokens = tokenize(Source("t", r'"a\"b\n\u{e9}"'), Diagnostics())
    assert tokens[0].value == 'a"b\né'


def test_comments_are_trivia() -> None:
    tokens = tokenize(Source("t", "// uno\n/// doc\nx // fin\n/* b */ y"), Diagnostics())
    x, y = tokens[0], tokens[2]
    assert [c.kind for c in x.leading] == ["line", "doc"]
    assert x.leading[1].body == "doc"
    assert [c.text for c in y.leading] == ["// fin", "/* b */"]
    assert not y.leading[0].own_line and y.leading[1].own_line


def test_lexical_errors() -> None:
    diagnostics = Diagnostics()
    tokenize(Source("t", 'x ! "abierto\n /* sin cerrar'), diagnostics)
    codes = [d.code for d in diagnostics]
    assert codes == ["E101", "E103", "E102"]
    assert "not" in (diagnostics.items[0].help or "")


# --- expresiones --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "shape"),
    [
        ("a + b * c", "Binary(+, a, Binary(*, b, c))"),
        ("a - b - c", "Binary(-, Binary(-, a, b), c)"),
        ("not a == b", "Unary(not, Binary(==, a, b))"),
        ("x in 0..n - 1", "Binary(in, x, Range(0, Binary(-, n, 1)))"),
        ("a if c else b if d else e", "If(a, c, If(b, d, e))"),
        ("-x.y", "Unary(-, Field(x, y))"),
        ("a and b or c", "Binary(or, Binary(and, a, b), c)"),
        ("x not in xs", "Binary(not in, x, xs)"),
        ("n div 2 % 3", "Binary(%, Binary(div, n, 2), 3)"),
    ],
)
def test_precedence(source: str, shape: str) -> None:
    assert _shape(expr(source)) == shape


def _shape(e: ast.Expr) -> str:
    match e:
        case ast.Name(name=n):
            return n
        case ast.IntLit(value=v):
            return str(v)
        case ast.Binary(op=op, left=left, right=right):
            return f"Binary({op}, {_shape(left)}, {_shape(right)})"
        case ast.Unary(op=op, operand=x):
            return f"Unary({op}, {_shape(x)})"
        case ast.RangeExpr(lo=lo, hi=hi):
            return f"Range({_shape(lo)}, {_shape(hi)})"
        case ast.IfExpr(then=t, cond=c, other=o):
            return f"If({_shape(t)}, {_shape(c)}, {_shape(o)})"
        case ast.Field(target=t, name=n):
            return f"Field({_shape(t)}, {n})"
    return type(e).__name__


def test_collections_and_binders() -> None:
    comp = expr("[Card { suit: s, rank: r } for s in Suit.values for r in Rank.values]")
    assert isinstance(comp, ast.Comprehension)
    assert [c.var for c in comp.clauses] == ["s", "r"]
    assert isinstance(comp.element, ast.StructLit)
    agg = expr("all(c in line : board[c] == m)")
    assert isinstance(agg, ast.Aggregate) and agg.var == "c" and agg.func == "all"
    sliced = expr("items(pile)[0:last_count]")
    assert isinstance(sliced, ast.Slice)
    assert isinstance(expr("xs[:n]"), ast.Slice)
    assert isinstance(expr("(a, b)"), ast.TupleLit)
    assert isinstance(expr("(a)"), ast.Paren)
    block = expr("{ let a = 1; let b = 2; a + b }")
    assert isinstance(block, ast.LetBlock) and [n for n, _ in block.lets] == ["a", "b"]


def test_case_and_match() -> None:
    case = expr("case {\n a => 1\n b => 2\n else => 3\n}")
    assert isinstance(case, ast.CaseExpr) and len(case.arms) == 2
    match = expr("match (x, y) {\n (A, _) => 1\n (B, C) => 2\n _ => 0\n}")
    assert isinstance(match, ast.MatchExpr)
    assert isinstance(match.arms[0][0], ast.PTuple)
    assert isinstance(match.arms[2][0], ast.PWild)


def test_chained_comparisons_are_rejected() -> None:
    _, diagnostics = parse_expression("a < b < c")
    assert "no se encadenan" in diagnostics.items[0].message


def test_struct_literals_need_parentheses_before_a_block() -> None:
    file, diagnostics = parse_text(
        "game G {\n flow {\n auto A {\n if x { y = 1 }\n -> A\n }\n }\n}"
    )
    assert not diagnostics.has_errors
    node = file.games[0].items[0].items[0]  # type: ignore[union-attr]
    assert isinstance(node.members[0], ast.IfStmt)


# --- declaraciones y recuperación de errores ----------------------------------------------------


@pytest.mark.parametrize("path", GAMES, ids=lambda p: p.stem)
def test_games_parse_without_errors(path: Path) -> None:
    diagnostics = Diagnostics()
    file = parse(Source.from_path(path), diagnostics)
    assert not diagnostics.items, [str(d) for d in diagnostics]
    assert len(file.games) == 1


def test_documentation_comments_attach_to_declarations() -> None:
    file, _ = parse_text(
        "/// El juego\ngame G {\n  state {\n    /// Turno actual\n    turn: Seat = 0\n  }\n}"
    )
    game = file.items[0]
    assert isinstance(game, ast.GameDecl) and game.doc is not None
    assert game.doc.value == "El juego"
    state = game.items[0]
    assert isinstance(state, ast.StateBlock)
    assert state.vars[0].doc is not None and state.vars[0].doc.value == "Turno actual"


def test_annotations() -> None:
    file, diagnostics = parse_text(
        "game G {\n state {\n  @visible(owner) @size_visible(all)\n  hand: per_player Bag<Card>\n"
        "  @visible(viewer == owner or at(End)) x: Int = 0\n }\n}"
    )
    assert not diagnostics.has_errors
    hand, x = file.games[0].items[0].vars  # type: ignore[union-attr]
    assert hand.visibility.kind == "owner" and hand.size_visibility.kind == "all"
    assert x.visibility.kind == "when"


def test_several_errors_are_reported_and_parsing_continues() -> None:
    source = """game G {
  players 2
  state {
    a: Int = 1 +
    b: Int = )
    c: Int = 3
  }
  fn ok() -> Int = c
  flow {
    start -> A
    decision A {
      actor 0
      action go() { x = }
    }
  }
}
"""
    file, diagnostics = parse_text(source, "g.game")
    lines = sorted({d.span.line for d in diagnostics if d.span is not None})
    assert len(lines) >= 3
    game = file.items[0]
    assert isinstance(game, ast.GameDecl)
    names = [type(i).__name__ for i in game.items]
    assert names == ["PlayersDecl", "StateBlock", "FnDecl", "FlowBlock"]


def test_rustc_style_rendering() -> None:
    _, diagnostics = parse_text("game G {\n  players two\n}", "juego.game")
    text = render(diagnostics.items[0])
    assert text.splitlines()[0].startswith("error[E110]: se esperaba un número de jugadores")
    assert " --> juego.game:2:11" in text
    assert "2 |   players two" in text
    assert "  |           ^^^" in text


def test_reserved_words_are_explained() -> None:
    _, diagnostics = parse_text("game G {\n state {\n  state: Int = 0\n }\n}")
    assert "palabra reservada" in diagnostics.items[0].message


# --- formateador --------------------------------------------------------------------------------


@pytest.mark.parametrize("path", FORMATTED, ids=lambda p: p.stem)
def test_games_are_formatted_and_formatting_is_idempotent(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    formatted = format_source(Source(str(path), text))
    assert formatted == text, "ejecuta: gamehub fmt games"
    assert format_source(Source(str(path), formatted)) == formatted


@pytest.mark.parametrize("path", FORMATTED, ids=lambda p: p.stem)
def test_formatting_preserves_the_syntax_tree(path: Path) -> None:
    original, _ = parse_text(path.read_text(encoding="utf-8"))
    squeezed = path.read_text(encoding="utf-8").replace("\n\n", "\n")
    reformatted, _ = parse_text(format_source(Source("x", squeezed)))
    assert reformatted == original


@pytest.mark.parametrize("path", FORMATTED, ids=lambda p: p.stem)
@pytest.mark.parametrize("width", [24, 40, 60, 80])
def test_narrow_formatting_still_parses_to_the_same_tree(path: Path, width: int) -> None:
    """A cualquier ancho, el formateador solo parte líneas por donde el parser lo admite."""
    original, _ = parse_text(path.read_text(encoding="utf-8"))
    formatted = format_file(original, width)
    again, diagnostics = parse_text(formatted)
    assert not diagnostics.has_errors, [str(d) for d in diagnostics]
    assert again == original
    assert format_file(again, width) == formatted


def test_values_may_start_on_the_next_line() -> None:
    _, diagnostics = parse_text(
        "game G {\n  params {\n    n: Int =\n      3\n  }\n  state {\n    x: Int =\n      1\n  }\n"
        "  fn f() -> Int =\n    1\n  flow {\n    start -> A\n    decision A {\n      actor:\n"
        "        0\n      action go() requires\n          x > 0 {\n        x =\n          2\n"
        "        let y =\n          3\n      }\n      -> B when\n          x > 1\n    }\n"
        "    terminal B { payoff:\n      [0, 0] }\n  }\n}"
    )
    assert not diagnostics.items, [str(d) for d in diagnostics]


def test_comments_survive_formatting() -> None:
    source = """// cabecera
game G { // tras la llave
  players 2 // jugadores


  // antes de state
  state {
    x: Int = 1 + /* dentro */ 2
    // al final de state
  }
  flow {
    start -> A
    terminal A { payoff: fill(0) } // final
  }
}
// fin
"""
    formatted = format_source(Source("g", source))
    for comment in ("// cabecera", "// tras la llave", "// jugadores", "// antes de state",
                    "/* dentro */", "// al final de state", "// final", "// fin"):  # fmt: skip
        assert comment in formatted
    assert "\n\n\n" not in formatted
    assert format_source(Source("g", formatted)) == formatted


def test_printer_adds_needed_parentheses() -> None:
    e = ast.Binary("*", ast.Binary("+", ast.Name("a"), ast.Name("b")), ast.Name("c"))
    assert show(e) == "(a + b) * c"
    e = ast.Binary("-", ast.Name("a"), ast.Binary("-", ast.Name("b"), ast.Name("c")))
    assert show(e) == "a - (b - c)"
    e = ast.IfExpr(ast.Name("a"), ast.IfExpr(ast.Name("b"), ast.Name("c"), ast.Name("d")),
                   ast.Name("e"))  # fmt: skip
    assert show(e) == "a if (b if c else d) else e"


def test_long_expressions_break_after_operators() -> None:
    names = " and ".join(f"condition_number_{i}" for i in range(8))
    file, _ = parse_text(f"game G {{\n  fn f() -> Bool = {names}\n}}")
    formatted = format_file(file)
    assert all(len(line) <= 100 for line in formatted.splitlines())
    assert parse_text(formatted)[0] == file
    # and/or: un operando por línea
    lines = formatted.splitlines()[2:-1]
    assert [line.strip() for line in lines] == [f"condition_number_{i} and" for i in range(7)] + [
        "condition_number_7"
    ]


def test_arithmetic_chains_fill_lines() -> None:
    terms = " + ".join(f"term_{i} * {i}" for i in range(40))
    file, _ = parse_text(f"game G {{\n  fn f() -> Int = {terms}\n}}")
    formatted = format_file(file)
    lines = formatted.splitlines()
    assert all(len(line) <= 100 for line in lines)
    terms_lines = lines[2:-1]
    assert all(len(line) > 85 for line in terms_lines[:-1])  # líneas llenas
    assert terms_lines[0].startswith("    term_0 * 0 + term_1 * 1 +")
    assert terms_lines[1].startswith("      term_")  # continuación con sangría
    assert parse_text(formatted)[0] == file


def test_bracketed_values_open_on_the_same_line_when_they_do_not_fit() -> None:
    short = "game G {\n  state {\n    x: List<Int> = [" + ", ".join(["1"] * 30) + "]\n  }\n}"
    formatted = format_source(Source("g", short))
    assert "    x: List<Int> =\n      [1, 1," in formatted  # cabe en la línea siguiente
    long = "game G {\n  state {\n    x: List<Int> = [" + ", ".join(["1"] * 60) + "]\n  }\n}"
    formatted = format_source(Source("g", long))
    assert "    x: List<Int> = [\n      1,\n" in formatted  # no cabe: se abre junto al '='
    assert format_source(Source("g", formatted)) == formatted


def test_blank_lines_around_comments_are_kept() -> None:
    source = """// cabecera

// licencia
enum A { X }

game G {
  players 2
  // fin del juego

  // de verdad
}
"""
    assert format_source(Source("g", source)) == source


def test_layout_fill_and_trailing_text() -> None:
    words = [text(f"w{i}") for i in range(6)]
    parts: list = [words[0]]
    for w in words[1:]:
        parts.extend([concat(",", LINE), w])
    assert render_doc(fill(parts), 12) == "w0, w1, w2,\nw3, w4, w5"
    # El texto que sigue a un grupo cuenta para decidir si cabe.
    doc = concat(group("aaaa", nest(2, LINE, "bbbb")), " {")
    assert render_doc(doc, 11) == "aaaa bbbb {"
    assert render_doc(doc, 10) == "aaaa\n  bbbb {"


def test_decimal_text() -> None:
    assert decimal_text(Fraction(1, 2)) == "0.5"
    assert decimal_text(Fraction(-5, 4)) == "-1.25"
    assert decimal_text(Fraction(3)) == "3.0"
    assert decimal_text(Fraction(1, 3)) is None


def test_format_rejects_syntax_errors() -> None:
    with pytest.raises(CompileError):
        format_source(Source("x", "game {"))


def test_fmt_command(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "g.game"
    path.write_text(
        "game G {   players 2\n\n\n\n  flow { start -> A\n terminal A {payoff: fill(0)} } }"
    )
    assert main(["fmt", "--check", str(path)]) == 1
    assert main(["fmt", str(tmp_path)]) == 0
    assert main(["fmt", "--check", str(path)]) == 0
    assert path.read_text() == (
        "game G {\n  players 2\n\n  flow {\n    start -> A\n"
        "    terminal A { payoff: fill(0) }\n  }\n}\n"
    )
    path.write_text("game G {   players 2 }")
    assert main(["fmt", "--diff", str(path)]) == 1
    assert "+  players 2" in capsys.readouterr().out
    assert path.read_text() == "game G {   players 2 }"  # --diff no escribe
    capsys.readouterr()
    (tmp_path / "bad.game").write_text("game {")
    assert main(["fmt", str(tmp_path / "bad.game")]) == 1
    assert "error[E110]" in capsys.readouterr().err
