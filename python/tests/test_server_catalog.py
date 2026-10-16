# SPDX-License-Identifier: Apache-2.0
"""El catálogo de un servidor: qué juegos se cargan de archivos y directorios."""

from __future__ import annotations

from pathlib import Path

import pytest

from gamehub.server.catalog import Catalog, CatalogError

ROOT = Path(__file__).resolve().parents[2]


def test_a_directory_of_packages_gives_their_main_games() -> None:
    catalog = Catalog.load([ROOT / "games"])
    ids = sorted(catalog.games)
    # Uno por paquete: los juegos de los tests de un paquete (iterated-pd/tests.game) no.
    packages = sorted(p.parent.name for p in (ROOT / "games").glob("*/game.toml"))
    assert len(ids) == len(packages) >= 16
    assert "iterated-pd" in ids and "iterated-pd-tests" not in ids


def test_a_package_a_file_and_loose_files(tmp_path: Path) -> None:
    assert sorted(Catalog.load([ROOT / "games" / "iterated-pd"]).games) == ["iterated-pd"]
    both = Catalog.load([ROOT / "games" / "iterated-pd" / "tests.game"])
    assert "iterated-pd-tests" in both.games
    loose = tmp_path / "juegos"
    loose.mkdir()
    (loose / "nim.ir.json").write_text(
        (ROOT / "spec" / "ir" / "examples" / "nim.ir.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (loose / "node_modules").mkdir()
    (loose / "node_modules" / "roto.game").write_text("no es nomos", encoding="utf-8")
    assert sorted(Catalog.load([loose]).games) == ["nim"]


def test_a_broken_game_is_reported(tmp_path: Path) -> None:
    broken = tmp_path / "roto.game"
    broken.write_text("game Roto {", encoding="utf-8")
    with pytest.raises(CatalogError, match=r"roto\.game"):
        Catalog.load([broken])
