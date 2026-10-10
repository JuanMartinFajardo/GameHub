# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture(autouse=True)
def _private_data_dir(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Los datos del usuario (sesiones del cliente, base de datos del servidor) de los tests van a
    un directorio temporal, también en los subprocesos: nunca a ~/.local/share/gamehub."""
    monkeypatch.setenv("GAMEHUB_DATA", str(tmp_path_factory.mktemp("gamehub-data")))


@pytest.fixture
def coin_game() -> dict[str, Any]:
    """Juego mínimo válido: adivinar una moneda. Los tests lo mutan para provocar errores."""
    return {
        "ir_version": "0.1.0",
        "game": {"id": "coin-guess", "version": "0.1.0"},
        "players": {"min": 1, "max": 1},
        "types": [{"kind": "enum", "name": "Side", "values": ["Heads", "Tails"]}],
        "state": [
            {"name": "guess", "type": ["option", "Side"], "init": ["const", None]},
            {"name": "coin", "type": ["option", "Side"], "init": ["const", None]},
        ],
        "functions": [
            {
                "name": "hit",
                "params": [],
                "returns": "Bool",
                "body": ["eq", ["var", "guess"], ["var", "coin"]],
            }
        ],
        "flow": {
            "start": "Guess",
            "nodes": [
                {
                    "id": "Guess",
                    "kind": "decision",
                    "actor": ["const", 0],
                    "actions": [
                        {
                            "name": "call",
                            "params": [
                                {"name": "s", "type": "Side", "domain": ["enum_values", "Side"]}
                            ],
                            "effects": [["assign", ["var", "guess"], ["arg", "s"]]],
                        }
                    ],
                    "transitions": [{"to": "Flip"}],
                },
                {
                    "id": "Flip",
                    "kind": "chance",
                    "effects": [["random_choice", ["var", "coin"], ["enum_values", "Side"]]],
                    "transitions": [{"to": "End"}],
                },
                {
                    "id": "End",
                    "kind": "terminal",
                    "payoff": ["fill", ["if", ["call", "hit"], ["const", 1], ["const", 0]]],
                },
            ],
        },
    }
