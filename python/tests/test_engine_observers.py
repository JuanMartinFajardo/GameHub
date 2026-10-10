# SPDX-License-Identifier: Apache-2.0
"""Motor, Fase 3: el observador público (espectadores), el puesto final, las acciones legales
pedidas de una en una, la decodificación sin estado y el azar verificable de los replays."""

from __future__ import annotations

import itertools
from pathlib import Path

import pytest

from gamehub.engine import PUBLIC, Action, Game, IllegalAction, Status, load_game
from gamehub.engine.fairness import (
    FairnessError,
    block,
    commitment,
    derive_seed,
    new_server_seed,
    valid_client_seed,
    verify,
)
from gamehub.engine.match import RandomAgent, play_match
from gamehub.engine.replay import record, replay
from gamehub.engine.rng import STREAM_CHANCE, Pcg32
from gamehub.engine.values import HIDDEN
from gamehub.ir.spec import examples_dir
from gamehub.lang.compiler import compile_text, load_nomos

ROOT = Path(__file__).resolve().parents[2]

WATCH = """
game Watch {
  players 3
  state {
    /// Como en Hanabi: cada uno ve lo de los demás, no lo suyo.
    @visible(viewer != owner)
    forehead: per_player Int = owner + 1
    team: per_player Int = owner % 2
    /// Visible para el propio equipo: usa `viewer` como asiento.
    @visible(team[viewer] == team[owner])
    plan: per_player Int = 10 + owner
    @visible(owner)
    hand: per_player List<Int> = [owner]
  }
  flow {
    start -> Pick
    decision Pick {
      actor: 0
      action pick(@visible(none) n in 1..3) {
        reveal forehead[0] to all
        reveal plan[1] to 1
        @visible(owner) emit mine { value: n }
        emit shared { value: n }
        -> End
      }
    }
    terminal End {
      payoff: [1, 0, 0]
      rank: [1, 3, 2]
    }
  }
}
"""


def watch() -> Game:
    result = compile_text(WATCH, "watch.game")
    assert result.ok, [str(d) for d in result.diagnostics]
    return load_game(result.game().ir)


def test_public_view_sees_what_belongs_to_nobody() -> None:
    state = watch().new_state()
    public = state.view(PUBLIC)["state"]
    # `viewer != owner`: un espectador no es dueño de nada, así que lo ve todo.
    assert public["forehead"] == [1, 2, 3]
    # `team[viewer]` no se puede evaluar sin asiento: oculto, sin error.
    assert public["plan"] == [HIDDEN, HIDDEN, HIDDEN]
    assert public["hand"] == [HIDDEN, HIDDEN, HIDDEN]
    # Los asientos siguen viendo lo suyo.
    seat0 = state.view(0)["state"]
    assert seat0["forehead"] == [HIDDEN, 2, 3]
    assert seat0["plan"] == [10, HIDDEN, 12]
    assert seat0["hand"] == [[0], HIDDEN, HIDDEN]


def test_public_events() -> None:
    state = watch().new_state()
    after = state.apply_action(0, Action.of("pick", n=2))
    public = after.events(PUBLIC)
    kinds = [e["type"] for e in public]
    # La acción se ve sin su argumento oculto; la revelación a todos sí, la privada no; el
    # evento `@visible(owner)` no, el público sí.
    action = next(e for e in public if e["type"] == "action")
    assert action == {"type": "action", "seat": 0, "name": "pick", "args": {"n": HIDDEN}}
    reveals = [e for e in public if e["type"] == "reveal"]
    assert [r["value"] for r in reveals] == [1]
    emits = [e["name"] for e in public if e["type"] == "emit"]
    assert emits == ["shared"]
    assert "end" in kinds
    # El asiento 1 ve las dos revelaciones; el actor ve su `emit` privado.
    assert [e["value"] for e in after.events(1) if e["type"] == "reveal"] == [1, 11]
    assert [e["name"] for e in after.events(0) if e["type"] == "emit"] == ["mine", "shared"]


def test_public_move_events_hide_private_cards() -> None:
    game = load_game(examples_dir() / "kuhn-poker.ir.json")
    state = game.new_state()
    dealt = state.apply_chance(state.chance_outcomes()[0][0])
    moves = [e for e in dealt.events(PUBLIC) if e["type"] == "move"]
    assert moves, "el reparto mueve cartas"
    assert all(item == HIDDEN for e in moves for item in e["items"])
    hands = dealt.view(PUBLIC)["state"]["hand"]
    assert [h["size"] for h in hands] == [1, 1]
    # La mano es una bolsa: de la ajena solo se ve cuántas cartas tiene.
    assert all(h["items"] == [] for h in hands)


def test_dudo_reveal_to_all_reaches_spectators() -> None:
    game = load_nomos(ROOT / "games" / "dudo" / "dudo.game")
    state = game.new_state(2)
    state = state.apply_chance(state.sample_chance(_rng(3)))
    assert state.view(PUBLIC)["state"]["cup"] == [HIDDEN, HIDDEN]
    state = state.apply_action(0, Action.of("bid", q=1, f=2))
    state = state.apply_action(1, Action.of("dudo"))
    [reveal] = [e for e in state.events(PUBLIC) if e["type"] == "reveal"]
    assert len(reveal["value"]) == 2


def test_ranking_from_rank_expression_and_from_payoffs() -> None:
    state = watch().new_state().apply_action(0, Action.of("pick", n=1))
    assert state.ranking() == (1, 3, 2)
    game = load_nomos(ROOT / "games" / "dudo" / "dudo.game")
    result = play_match(
        game, [RandomAgent(5, s) for s in range(3)], seed=5, num_players=3, params={"dice": 1}
    )
    payoffs = result.state.payoffs
    assert payoffs is not None
    winner = payoffs.index(max(payoffs))
    ranks = result.state.ranking()
    assert ranks is not None
    assert ranks[winner] == 1 and sorted(ranks) == [1, 2, 2]
    assert game.new_state(2).ranking() is None


def test_iter_legal_actions_is_lazy_and_matches_the_list() -> None:
    game = load_nomos(ROOT / "games" / "mentiroso" / "mentiroso.game")
    state = game.new_state(3)
    while state.status is Status.CHANCE:
        state = state.apply_chance(state.sample_chance(_rng(1)))
    seat = state.active_seats[0]
    first_ten = list(itertools.islice(state.iter_legal_actions(seat), 10))
    assert first_ten == state.legal_actions(seat)[:10]
    assert list(state.iter_legal_actions(1 - seat if seat < 2 else 0)) == []


def test_decode_action_without_a_state() -> None:
    game = load_nomos(ROOT / "games" / "dudo" / "dudo.game")
    state = game.new_state(2)
    state = state.apply_chance(state.sample_chance(_rng(2)))
    data = {"name": "bid", "args": {"q": 2, "f": 5}}
    assert game.decode_action(state.node, data) == state.decode_action(0, data)
    with pytest.raises(IllegalAction):
        game.decode_action(state.node, {"name": "bid", "args": {"q": "dos", "f": 5}})
    with pytest.raises(IllegalAction):
        game.decode_action(state.node, {"name": "bid", "args": [2, 5]})


# --- Azar verificable ----------------------------------------------------------------------------


def _rng(seed: int) -> Pcg32:
    return Pcg32(seed, STREAM_CHANCE)


def fair_replay(server_seed: str, client_seeds: list[str]) -> tuple[Game, dict]:
    game = load_game(examples_dir() / "kuhn-poker.ir.json")
    seed = derive_seed(server_seed, client_seeds)
    result = play_match(game, [RandomAgent(seed, s) for s in range(2)], seed=seed)
    data = record(result.state, seed, game=game)
    data["fairness"] = block(server_seed, client_seeds, reveal=True)
    return game, data


def test_commitment_and_seed_derivation() -> None:
    server_seed = new_server_seed()
    assert len(server_seed) == 64 and int(server_seed, 16) >= 0
    assert commitment(server_seed) == commitment(server_seed) != commitment(new_server_seed())
    seed = derive_seed(server_seed, ["", "hola"])
    assert 0 <= seed < 2**53
    assert seed == derive_seed(server_seed, ["", "hola"])
    assert seed != derive_seed(server_seed, ["hola", ""])
    assert valid_client_seed("dados de la suerte") and not valid_client_seed("x" * 65)
    assert not valid_client_seed("línea\nnueva")
    hidden = block(server_seed, ["a", "b"], reveal=False)
    assert "server_seed" not in hidden and hidden["commitment"] == commitment(server_seed)


def test_verify_a_fair_replay() -> None:
    game, data = fair_replay("ab" * 32, ["", "mi semilla"])
    final = verify(game, data)
    assert final.is_terminal
    assert replay(game, data).digest() == final.digest()


@pytest.mark.parametrize("tamper", ["server_seed", "client_seed", "seed", "chance"])
def test_verify_detects_tampering(tamper: str) -> None:
    game, data = fair_replay("cd" * 32, ["x", "y"])
    fair = data["fairness"]
    if tamper == "server_seed":
        fair["server_seed"] = "ef" * 32
    elif tamper == "client_seed":
        fair["client_seeds"] = ["x", "z"]
    elif tamper == "seed":
        data["seed"] += 1
    else:
        # Otro reparto igual de válido para las reglas, pero que no sale de la semilla.
        state = game.new_state()
        current = tuple(data["steps"][0]["chance"])
        other = next(o for o, _ in state.chance_outcomes() if o != current)
        data["steps"][0]["chance"] = list(other)
        data.pop("digests")
        data.pop("result")
    with pytest.raises(FairnessError):
        verify(game, data)


def test_verify_requires_the_revealed_seed() -> None:
    game, data = fair_replay("01" * 32, ["", ""])
    data["fairness"].pop("server_seed")
    with pytest.raises(FairnessError, match="revelado"):
        verify(game, data)
    data.pop("fairness")
    with pytest.raises(FairnessError):
        verify(game, data)
