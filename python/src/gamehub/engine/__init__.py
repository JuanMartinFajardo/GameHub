# SPDX-License-Identifier: Apache-2.0
"""Motor de referencia de GameHub: ejecuta juegos descritos en GameIR.

from gamehub.engine import load_game
game = load_game("spec/ir/examples/tictactoe.ir.json")
state = game.new_state()
state = state.apply_action(0, state.legal_actions(0)[4])
"""

from gamehub.engine.env import PUBLIC
from gamehub.engine.errors import (
    EngineError,
    IllegalAction,
    InvalidParams,
    NotEnumerable,
    RuleError,
)
from gamehub.engine.game import Game, load_game
from gamehub.engine.rng import Pcg32
from gamehub.engine.state import PASS, Action, State, Status, Step

__all__ = [
    "PASS",
    "PUBLIC",
    "Action",
    "EngineError",
    "Game",
    "IllegalAction",
    "InvalidParams",
    "NotEnumerable",
    "Pcg32",
    "RuleError",
    "State",
    "Status",
    "Step",
    "load_game",
]
