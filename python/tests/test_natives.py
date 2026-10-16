# SPDX-License-Identifier: Apache-2.0
"""Plugins nativos (ADR-062): la anotación @native, el plugin WebAssembly de std.poker y su
equivalencia con la implementación de referencia."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from gamehub.engine import natives
from gamehub.engine.errors import RuleError
from gamehub.engine.values import StructValue, Type, TypeTable
from gamehub.lang.compiler import compile_text
from gamehub.lang.decompile import decompile_text
from gamehub.lang.modules import stdlib_dir
from gamehub.lang.printer import format_source
from gamehub.lang.source import Source

POKER = stdlib_dir() / "std" / "poker.game"

pytestmark = pytest.mark.skipif(not natives.wasm_available(), reason="sin wasmtime")


@pytest.fixture(scope="module")
def poker() -> Any:
    return natives.module_game(POKER)


def hand(defn: Any, text: str) -> int:
    """El valor de una mano escrita como «As Kh 10d …» (palos c, d, h, s)."""
    suits = {"c": "Clubs", "d": "Diamonds", "h": "Hearts", "s": "Spades"}
    ranks = {"J": "Jack", "Q": "Queen", "K": "King", "A": "Ace"}
    numbers = ["Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten"]
    cards = []
    for word in text.split():
        rank, suit = word[:-1], word[-1]
        name = ranks.get(rank) or numbers[int(rank) - 2]
        cards.append(
            StructValue(
                "Card",
                (
                    ("suit", defn.types.enum_value("Suit", suits[suit])),
                    ("rank", defn.types.enum_value("Rank", name)),
                ),
            )
        )
    value = natives.call_function(defn, "hand_value", {"cards": tuple(cards)})
    assert value == natives.call_function(
        defn, "hand_value", {"cards": tuple(cards)}, reference=True
    )
    return value


def test_the_plugin_replaces_the_reference(poker: Any) -> None:
    fn = poker.functions["hand_value"]
    assert fn.native == "std.poker.hand_value" and fn.body is not fn.reference


def test_hands_are_ordered_as_in_poker(poker: Any) -> None:
    ladder = [
        "2c 5d 9h Jc Ks 3d 7h",  # carta alta
        "2c 2d 9h Jc Ks 3d 7h",  # pareja
        "2c 2d 9h 9c Ks 3d 7h",  # dobles parejas
        "2c 2d 2h 9c Ks 3d 7h",  # trío
        "Ac 2d 3h 4c 5s Jd 9h",  # escalera (la rueda)
        "6c 2d 3h 4c 5s Jd 9h",  # escalera al seis
        "2h 5h 9h Jh Kh 3d 7c",  # color
        "2c 2d 2h 9c 9s 3d 7h",  # full
        "2c 2d 2h 2s 9s 3d 7h",  # póquer
        "Ah 2h 3h 4h 5h Jd 9c",  # escalera de color
        "Ah Kh Qh Jh 10h Jd 9c",  # escalera real
    ]
    values = [hand(poker, h) for h in ladder]
    assert values == sorted(values) and len(set(values)) == len(values)
    categories = [v >> 20 for v in values]
    assert categories == [0, 1, 2, 3, 4, 4, 5, 6, 7, 8, 8]


def test_kickers_and_ties(poker: Any) -> None:
    # La mejor combinación de cinco: la sexta y la séptima carta no cuentan.
    assert hand(poker, "Ac Ad Kh Qc Js 3d 2h") == hand(poker, "As Ah Kd Qs Jc 4d 2c")
    assert hand(poker, "Ac Ad Kh Qc Js 3d 2h") > hand(poker, "As Ah Kd Qs 10c 9d 8c")
    # Dobles parejas: decide la carta que queda, aunque haya una tercera pareja.
    assert hand(poker, "Kc Kd 7h 7c 5s 5d Ah") > hand(poker, "Ks Kh 7d 7s Qc 2d 3h")
    # Full: el trío manda; con dos tríos, el más bajo hace de pareja.
    assert hand(poker, "3c 3d 3h 2c 2s Ad Ah") == hand(poker, "3c 3d 3h As Ad 9c 8c")
    assert hand(poker, "Kc Kd Kh 2c 2s 2d 9h") > hand(poker, "Qc Qd Qh Ac As 9c 8c")
    # Color: las cinco más altas del palo.
    assert hand(poker, "Ah 9h 7h 5h 3h 2h Kd") == hand(poker, "Ah 9h 7h 5h 3h Kd Qc")


def test_the_plugin_matches_the_reference_on_random_inputs() -> None:
    assert natives.compare_with_reference("std.poker.hand_value", 1500, seed=7) == []


def test_the_wasm_binary_is_built_from_its_source() -> None:
    assert natives.build(write=False) == []


def test_without_natives_the_reference_is_used(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GAMEHUB_NATIVES", "0")
    defn = natives.module_game(POKER)
    fn = defn.functions["hand_value"]
    assert fn.body is fn.reference


def test_a_python_implementation_has_priority() -> None:
    natives.register("std.poker.hand_value", lambda cards: len(cards))
    try:
        defn = natives.module_game(POKER)
        assert natives.call_function(defn, "hand_value", {"cards": ()}) == 0
    finally:
        natives.unregister("std.poker.hand_value")


def test_codec_roundtrip() -> None:
    types = TypeTable(
        [
            {"kind": "enum", "name": "Color", "values": ["Red", "Green"]},
            {"kind": "struct", "name": "P", "fields": [
                {"name": "c", "type": "Color"}, {"name": "xs", "type": ["list", "Int"]},
            ]},
        ]
    )  # fmt: skip
    codec = natives.Codec(types)
    t = types.parse(["tuple", ["list", "P"], ["option", "Cell"], "Bool", ["option", "Int"]])
    value = (
        (
            StructValue("P", (("c", types.enum_value("Color", "Green")), ("xs", (3, -4)))),
            StructValue("P", (("c", types.enum_value("Color", "Red")), ("xs", ()))),
        ),
        (2, 7),
        True,
        None,
    )
    words: list[int] = []
    codec.encode(value, t, words)
    assert words == [2, 1, 2, 3, -4, 0, 0, 1, 2, 7, 1, 0]
    assert codec.decode(words, 0, t) == (value, len(words))
    with pytest.raises(OverflowError):
        codec.encode(2**40, Type("prim", "Int"), [])


def test_a_module_with_imports_is_rejected(tmp_path: Path) -> None:
    wat = tmp_path / "evil.wat"
    wat.write_text('(module (import "env" "f" (func)) (memory (export "memory") 1))')
    with pytest.raises(RuleError, match="importa"):
        natives.WasmModule(wat)


def test_a_runaway_plugin_runs_out_of_fuel(tmp_path: Path) -> None:
    wat = tmp_path / "loop.wat"
    wat.write_text(
        '(module (memory (export "memory") 1) (func (export "gh_buffer") (result i32) i32.const 0)'
        ' (func (export "spin") (param i32 i32 i32) (result i32) (loop $l (br $l)) i32.const 0))'
    )
    module = natives.WasmModule(wat)
    with pytest.raises(RuleError, match="ha fallado"):
        module.call("spin", [])


# --- La anotación en Nomos ---------------------------------------------------------------------

NATIVE_GAME = """@native("demo.double")
fn double(x: Int) -> Int = 2 * x

game G {
  players 1
  flow {
    start -> End
    terminal End { payoff: [double(1)] }
  }
}
"""


def test_native_reaches_the_ir_and_round_trips() -> None:
    result = compile_text(NATIVE_GAME)
    assert result.ok
    (fn,) = result.game().ir["functions"]
    assert fn["native"] == "demo.double"
    assert format_source(Source("g.game", NATIVE_GAME)) == NATIVE_GAME
    assert '@native("demo.double")' in decompile_text(result.game().ir, "G")


def errors(text: str) -> list[str]:
    return [f"{d.code} {d.message}" for d in compile_text(text).diagnostics.errors]


def test_native_signatures_are_checked() -> None:
    bad = NATIVE_GAME.replace("fn double(x: Int) -> Int = 2 * x", "fn double(x: Text) -> Int = 2")
    assert any(e.startswith("E211") and "Text" in e for e in errors(bad))
    bad_id = NATIVE_GAME.replace('"demo.double"', '"Double"')
    assert any(e.startswith("E211") for e in errors(bad_id))
    on_enum = '@native("demo.x")\nenum E { A }\n' + NATIVE_GAME.split("\n\n", 1)[1]
    assert any(e.startswith("E111") for e in errors(on_enum))
