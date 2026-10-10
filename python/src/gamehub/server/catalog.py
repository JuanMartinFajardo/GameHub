# SPDX-License-Identifier: Apache-2.0
"""Catálogo de juegos de un servidor: los que se pueden hospedar por su id.

Se carga desde archivos `.game` (compilados), `.ir.json` o directorios. De un paquete de juego
(un directorio con `game.toml`) se carga su archivo principal; de otros directorios, los paquetes
que contienen y los `.game` e `.ir.json` sueltos. Un `.game` con varios juegos aporta todos.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from gamehub.engine import Game, load_game


class CatalogError(Exception):
    """Un juego que no se puede cargar."""


class Catalog:
    def __init__(self, games: Iterable[Game] = ()) -> None:
        self.games: dict[str, Game] = {}
        for game in games:
            self.add(game)

    def add(self, game: Game) -> None:
        self.games[game.id] = game

    def get(self, game_id: str) -> Game | None:
        return self.games.get(game_id)

    def __len__(self) -> int:
        return len(self.games)

    def info(self) -> list[dict[str, Any]]:
        return [game_info(g) for g in sorted(self.games.values(), key=lambda g: g.id)]

    @classmethod
    def load(cls, paths: Iterable[Path]) -> Catalog:
        catalog = cls()
        for path in paths:
            for game in load_games(path):
                catalog.add(game)
        return catalog


def game_info(game: Game) -> dict[str, Any]:
    return {
        "id": game.id,
        "version": game.version,
        "title": game.title,
        "rules_hash": game.rules_hash,
        "players": {"min": game.players[0], "max": game.players[1]},
    }


def load_games(path: Path) -> list[Game]:
    """Los juegos de un archivo o directorio. `CatalogError` si alguno no compila."""
    if path.is_dir():
        from gamehub.packages import MANIFEST, SKIPPED_DIRS, PackageError, load_manifest

        if (path / MANIFEST).is_file():
            # De un paquete, su juego principal (no los de sus tests o sus módulos).
            try:
                return load_games(load_manifest(path).entry_path)
            except PackageError as exc:
                raise CatalogError(f"{path}: {exc}") from None
        games: list[Game] = []
        for child in sorted(path.iterdir()):
            if child.name in SKIPPED_DIRS or child.name.startswith("."):
                continue
            if child.is_dir() or child.suffix == ".game" or child.name.endswith(".ir.json"):
                games += load_games(child)
        return games
    if path.name.endswith(".ir.json"):
        try:
            return [load_game(path)]
        except Exception as exc:
            raise CatalogError(f"{path}: {exc}") from None
    if path.suffix == ".game":
        from gamehub.lang.compiler import compile_file

        result = compile_file(path)
        if not result.ok:
            first = result.diagnostics.errors[0]
            raise CatalogError(f"{path}: error[{first.code}] {first.message}")
        # Un archivo sin juegos es un módulo (p. ej. la base de una familia de variantes).
        return [Game(compiled.ir) for compiled in result.games.values()]
    raise CatalogError(f"{path}: se esperaba un .game, un .ir.json o un directorio")
