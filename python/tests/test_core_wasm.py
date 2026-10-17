# SPDX-License-Identifier: Apache-2.0
"""El núcleo C++ en WebAssembly (`web/packages/engine/wasm`): los binarios guardados son los de
las fuentes actuales (si no, `gamehub wasm --write`, que necesita Emscripten). Que se comporta
como el motor de referencia lo comprueban los tests del paquete web (`pnpm test`)."""

from __future__ import annotations

import json

from gamehub.engine import core_wasm


def test_wasm_build_is_up_to_date() -> None:
    assert core_wasm.check() == []


def test_fingerprint_covers_core_sources_and_plugins() -> None:
    root = core_wasm.repo_root()
    names = {p.relative_to(root).as_posix() for p in core_wasm.sources()}
    assert "core/CMakeLists.txt" in names
    assert "core/wasm/bindings.cpp" in names
    assert "core/src/vm.cpp" in names
    assert "stdlib/std/native/std.poker.wasm" in names
    stamp = json.loads((core_wasm.output_dir() / "BUILD.json").read_text(encoding="utf-8"))
    assert stamp["natives"] == ["std.poker"]
    assert stamp["emscripten"].startswith("emcc")


def test_natives_index_lists_every_plugin() -> None:
    text = core_wasm.render_natives_index()
    for plugin in core_wasm.natives():
        assert f'"{plugin.stem}": () => new URL("../wasm/natives/{plugin.name}"' in text
