# SPDX-License-Identifier: Apache-2.0
"""Salas del servidor de partidas, sin red: lobby, partidas, turnos y `seq`, espectadores, bots,
plazos, abandonos, reconexión y revancha. Todos los mensajes se validan contra el esquema."""

from __future__ import annotations

import pytest

from gamehub.engine.fairness import verify
from gamehub.server.room import RoomError
from server_harness import Harness, game

# --- Lobby -------------------------------------------------------------------------------------


def test_join_fills_seats_and_ready_starts_the_match() -> None:
    h = Harness("tictactoe")
    ana = h.join("Ana", host=True)
    assert h.last(ana, "joined")["session"] == {
        "room": "K7FQ2P",
        "participant": ana.id,
        "name": "Ana",
        "role": "player",
        "seat": 0,
        "host": True,
    }
    room = h.last(ana, "room")
    assert room["status"] == "lobby"
    assert [s["kind"] for s in room["seats"]] == ["human", "open"]
    luis = h.join("Luis")
    assert luis.seat == 1
    h.ready(ana)
    assert h.room.status == "lobby"
    h.ready(luis)
    assert h.room.status == "running"
    start = h.last(ana, "match_start")
    assert start["seat"] == 0 and start["match"]["number"] == 1
    assert start["fairness"]["commitment"] == room["commitment"]
    update = h.last(ana, "update")
    assert update["seq"] == 0 and update["view"]["active"] == [0]
    assert len(h.legal(ana)) == 9
    assert "legal" not in h.last(luis, "update")


def test_names_are_cleaned_and_unique() -> None:
    h = Harness("nim")
    a = h.join("  Ana\u0007  Pérez ")
    b = h.join("Ana Pérez")
    assert a.name == "Ana Pérez" and b.name == "Ana Pérez (2)"


def test_room_full_and_seat_taken() -> None:
    h = Harness("tictactoe")
    h.join("Ana")
    with pytest.raises(RoomError) as info:
        h.join("Luis", seat=0)
    assert info.value.code == "seat_taken"
    h.join("Luis")
    with pytest.raises(RoomError) as info:
        h.join("Eva")
    assert info.value.code == "room_full"
    eva = h.join("Eva", role="spectator")
    assert eva.seat is None


def test_reserved_seat_is_kept_for_its_name() -> None:
    h = Harness("tictactoe")
    host = h.join("Ana", host=True)
    h.room.set_seat(host.id, 1, "reserved", h.now, name="Luis")
    h.deliver()
    with pytest.raises(RoomError):
        h.join("Eva")
    assert h.join("luis").seat == 1


def test_sit_stand_and_configure() -> None:
    h = Harness("dudo", 2)
    host = h.join("Ana", host=True)
    h.room.stand(host.id, h.now)
    assert host.seat is None and h.room.seats[0].participant is None
    h.room.sit(host.id, 1, h.now)
    assert host.seat == 1
    h.room.configure(host.id, h.now, players=4, params={"dice": 2})
    h.deliver()
    room = h.last(host, "room")
    assert len(room["seats"]) == 4 and room["params"] == {"dice": 2}
    with pytest.raises(RoomError) as info:
        h.room.configure(host.id, h.now, players=5)
    assert info.value.code == "invalid_params"
    with pytest.raises(RoomError) as info:
        h.room.configure(host.id, h.now, params={"dice": 9})
    assert info.value.code == "invalid_params"
    other = h.join("Luis")
    with pytest.raises(RoomError) as info:
        h.room.configure(other.id, h.now, players=2)
    assert info.value.code == "not_host"


def test_host_passes_on_and_kick() -> None:
    h = Harness("tictactoe")
    ana = h.join("Ana", host=True)
    luis = h.join("Luis")
    eva = h.join("Eva", role="spectator")
    h.room.kick(ana.id, eva.id, h.now)
    h.deliver()
    assert eva.id in h.closed and eva.id not in h.room.participants
    h.room.leave(ana.id, h.now)
    h.deliver()
    assert luis.host and h.room.seats[0].empty
    h.room.leave(luis.id, h.now)
    assert h.room.status == "closed"


# --- Partidas ------------------------------------------------------------------------------------


def play_tictactoe(h: Harness) -> tuple:
    x, o = h.seat("Ana"), h.seat("Luis")
    for p, cell in [(x, [0, 0]), (o, [1, 1]), (x, [0, 1]), (o, [2, 2]), (x, [0, 2])]:
        h.act(p, "place", c=cell)
    return x, o


def test_full_match_end_and_fair_replay() -> None:
    h = Harness("tictactoe")
    x, o = play_tictactoe(h)
    end = h.last(x, "match_end")
    assert end["reason"] == "terminal" and end["payoffs"] == [1, -1] and end["ranking"] == [1, 2]
    assert end["fairness"]["server_seed"] and end["view"]["status"] == "terminal"
    assert h.room.status == "lobby" and h.last(o, "room")["last"]["payoffs"] == [1, -1]
    match = h.room.match
    assert match is not None
    data = match.replay(h.room.match_players)
    assert data["players"] == [{"name": "Ana", "kind": "human"}, {"name": "Luis", "kind": "human"}]
    assert verify(game("tictactoe"), data).payoffs == (1, -1)


def test_rejections() -> None:
    h = Harness("tictactoe")
    x, o = h.seat("Ana"), h.seat("Luis")
    h.act(o, "place", c=[0, 0])
    assert h.last(o, "rejected")["reason"] == "not_your_turn"
    h.act(x, "place", c=[3, 3])
    assert h.last(x, "rejected")["reason"] == "illegal_action"
    h.act_json(x, {"name": "fly", "args": {}})
    assert "desconocida" in h.last(x, "rejected")["detail"]
    h.act(x, "place", seq=7, c=[0, 0])
    assert h.last(x, "rejected")["reason"] == "stale_seq"
    h.act(x, "place", c=[0, 0])
    h.act(o, "place", c=[1, 1])
    # X decide con lo que veía antes de que O jugara: su turno empezó en la actualización 2.
    h.act(x, "place", seq=1, c=[2, 2])
    rejected = h.last(x, "rejected")
    assert rejected["reason"] == "stale_seq"
    assert "empezó en la actualización 2" in rejected["detail"]


def test_repeated_message_ids_are_ignored() -> None:
    h = Harness("nim")
    a, b = h.seat("Ana"), h.seat("Luis")
    h.act(a, "take", re="m1", heap=0, count=1)
    seq = h.room.match.seq  # type: ignore[union-attr]
    h.act(a, "take", seq=0, re="m1", heap=0, count=1)
    assert h.room.match.seq == seq and not h.messages(a, "rejected")  # type: ignore[union-attr]
    assert b.seat == 1


def test_simultaneous_moves_do_not_go_stale() -> None:
    h = Harness("rock-paper-scissors")
    a, b = h.seat("Ana"), h.seat("Luis")
    assert h.last(a, "update")["view"]["active"] == [0, 1]
    h.act(a, "show", seq=0, h="Rock")
    seen = h.last(b, "update")
    assert seen["seq"] == 1 and seen["events"] == [{"type": "submitted", "seat": 0}]
    # Luis decidió con la actualización 0: su turno no ha cambiado, así que vale.
    h.act(b, "show", seq=0, h="Paper")
    end = h.last(a, "match_end")
    assert end["payoffs"] == [-1, 1]


def test_window_collect_in_mentiroso() -> None:
    h = Harness("mentiroso", 3, params={})
    players = [h.seat(n, legal_limit=0) for n in ("Ana", "Luis", "Eva")]
    first = next(p for p in players if p.seat == h.last(p, "update")["view"]["active"][0])
    legal = h.last(first, "update")["legal"]
    assert legal["kind"] == "progressive" and legal["names"] == ["play"]
    h.room.query_actions(first.id, h.seq(first), "play", {}, h.now, re="q")
    h.deliver()
    options = h.last(first, "actions")
    assert options["name"] == "play" and options["options"]
    cards = options["options"][0][:1]
    h.act(first, "play", cards=cards)
    others = [p for p in players if p is not first]
    assert all(h.last(p, "update")["view"]["active"] for p in others)
    h.act(others[0], "pass")
    h.act(others[1], "pass", seq=h.seq(others[1]) - 1)
    assert not h.messages(others[1], "rejected")
    assert h.last(first, "update")["view"]["node"] == "Play"


# --- Espectadores -----------------------------------------------------------------------------


def test_spectators_see_the_public_view() -> None:
    h = Harness("kuhn-poker")
    a, b = h.seat("Ana"), h.seat("Luis")
    eva = h.join("Eva", role="spectator")
    update = h.last(eva, "update")
    hands = update["view"]["state"]["hand"]
    assert all(hand["items"] == [] for hand in hands)
    assert h.last(a, "update")["view"]["state"]["hand"][0]["items"] != []
    assert b.seat == 1


def test_omniscient_spectators_with_delay() -> None:
    h = Harness("kuhn-poker", spectator_view="omniscient", spectator_delay=5)
    eva = h.join("Eva", role="spectator")
    a, b = h.seat("Ana"), h.seat("Luis")
    assert not h.messages(eva, "match_start")
    h.advance(4.9)
    assert not h.messages(eva, "match_start")
    h.advance(0.2)
    assert h.messages(eva, "match_start")
    hands = h.last(eva, "update")["view"]["state"]["hand"]
    assert all(len(hand["items"]) == 1 for hand in hands)
    # Quien llega ahora ve la partida como estaba hace 5 segundos.
    h.act(a, "bet")
    late = h.join("Leo", role="spectator")
    assert h.last(late, "update")["seq"] == 0
    h.advance(5.0)
    assert h.last(late, "update")["seq"] == 1
    assert b.seat == 1


def test_spectators_can_be_disabled() -> None:
    h = Harness("nim", spectators=False)
    with pytest.raises(RoomError) as info:
        h.join("Eva", role="spectator")
    assert info.value.code == "not_allowed"


# --- Bots ---------------------------------------------------------------------------------------


def test_server_bot_plays_its_seat() -> None:
    h = Harness("tictactoe")
    ana = h.join("Ana", host=True)
    h.room.set_seat(ana.id, 1, "bot", h.now, bot="first")
    h.ready(ana)
    assert h.room.status == "running"
    h.act(ana, "place", c=[1, 1])
    # El bot (la primera acción legal) ya ha respondido.
    assert h.last(ana, "update")["view"]["active"] == [0]
    assert h.room.match.seq == 2  # type: ignore[union-attr]


def test_bot_delay() -> None:
    h = Harness("tictactoe", bot_delay=1.0)
    ana = h.join("Ana", host=True)
    h.room.set_seat(ana.id, 1, "bot", h.now)
    h.ready(ana)
    h.act(ana, "place", c=[1, 1])
    assert h.room.match.seq == 1  # type: ignore[union-attr]
    assert h.room.next_wakeup() == pytest.approx(h.now + 1.0)
    h.advance(1.0)
    assert h.room.match.seq == 2  # type: ignore[union-attr]


def test_bots_only_room_plays_to_the_end() -> None:
    h = Harness("dudo", 3, params={"dice": 1})
    host = h.join("Ana", role="spectator", host=True)
    for seat in range(3):
        h.room.set_seat(host.id, seat, "bot", h.now)
    h.deliver()
    end = h.last(host, "match_end")
    assert end["reason"] == "terminal" and sorted(end["ranking"]) == [1, 2, 2]


# --- Plazos -------------------------------------------------------------------------------------


def test_move_clock_timeout_plays_at_random() -> None:
    h = Harness("tictactoe", clock={"kind": "move", "seconds": 10})
    a, b = h.seat("Ana"), h.seat("Luis")
    clocks = h.last(a, "update")["clocks"]
    assert clocks == {"kind": "move", "remaining_ms": [10_000, None], "running": [0]}
    h.advance(9.9)
    assert h.room.match.seq == 0  # type: ignore[union-attr]
    h.advance(0.2)
    assert h.room.match.seq == 1  # type: ignore[union-attr]
    assert h.last(b, "update")["view"]["active"] == [1]
    assert h.last(b, "update")["clocks"]["running"] == [1]


def test_match_clock_counts_time_and_increment() -> None:
    h = Harness("nim", clock={"kind": "match", "initial": 60, "increment": 2})
    a, b = h.seat("Ana"), h.seat("Luis")
    h.advance(10)
    h.act(a, "take", heap=0, count=1)
    clocks = h.last(b, "update")["clocks"]
    assert clocks["remaining_ms"] == [52_000, 60_000] and clocks["running"] == [1]


def test_timeout_forfeit_ends_a_two_player_match() -> None:
    h = Harness("nim", clock={"kind": "move", "seconds": 5}, on_timeout="forfeit")
    a, b = h.seat("Ana"), h.seat("Luis")
    h.advance(6)
    end = h.last(b, "match_end")
    assert end["reason"] == "forfeit" and end["ranking"] == [2, 1] and end["forfeited"] == [0]
    assert end["payoffs"] is None and a.seat == 0


def test_timeout_bot_takes_over() -> None:
    h = Harness("tictactoe", clock={"kind": "move", "seconds": 5}, on_timeout="bot")
    a, b = h.seat("Ana"), h.seat("Luis")
    h.advance(6)
    assert h.room.seats[0].takeover == "random"
    h.act(b, "place", c=h.legal(b)[0]["args"]["c"])
    assert h.last(b, "update")["view"]["active"] == [1]  # el bot ya ha jugado por Ana
    assert "legal" not in h.last(a, "update")


# --- Abandonos ----------------------------------------------------------------------------------


def test_resign_two_players() -> None:
    h = Harness("tictactoe")
    a, b = h.seat("Ana"), h.seat("Luis")
    h.room.resign(b.id, h.now)
    h.deliver()
    end = h.last(a, "match_end")
    assert end["reason"] == "forfeit" and end["ranking"] == [1, 2]


def test_leaving_a_three_player_match_lets_a_bot_finish_it() -> None:
    h = Harness("dudo", 3, params={"dice": 1})
    a, b, c = h.seat("Ana"), h.seat("Luis"), h.seat("Eva")
    h.room.leave(c.id, h.now)
    h.deliver()
    assert h.room.status == "running" and h.room.seats[2].takeover == "random"
    room = h.last(a, "room")
    assert room["seats"][2]["kind"] == "bot"
    for _ in range(100):
        if h.room.status != "running":
            break
        active = h.last(a, "update")["view"]["active"]
        p = a if active == [0] else b
        h.act_json(p, h.legal(p)[-1])
    end = h.last(a, "match_end")
    assert end["ranking"][2] == 3 and end["forfeited"] == [2]
    assert h.room.seats[2].empty


# --- Reconexión ---------------------------------------------------------------------------------


def test_reconnect_with_resume_gets_only_missed_updates() -> None:
    h = Harness("nim")
    a, b = h.seat("Ana"), h.seat("Luis")
    match_id = h.last(b, "match_start")["match"]["id"]
    h.room.disconnect(b.id, h.now)
    h.deliver()
    assert h.last(a, "room")["seats"][1]["connected"] is False
    h.act(a, "take", heap=0, count=1)
    h.clear()
    h.room.resume(b.id, h.now, {"match": match_id, "seq": 0})
    h.deliver()
    kinds = [m["type"] for m in h.messages(b)]
    assert kinds == ["welcome", "room", "update"]
    assert h.last(b, "update")["seq"] == 1 and h.last(b, "update")["events"]
    assert h.legal(b)
    h.act(b, "take", heap=1, count=1)
    assert not h.messages(b, "rejected")


def test_reconnect_without_resume_gets_a_snapshot() -> None:
    h = Harness("nim")
    a, b = h.seat("Ana"), h.seat("Luis")
    h.room.disconnect(a.id, h.now)
    h.clear()
    h.room.resume(a.id, h.now)
    h.deliver()
    kinds = [m["type"] for m in h.messages(a)]
    assert kinds == ["welcome", "room", "match_start", "update"]
    assert h.last(a, "update")["events"] == [] and h.legal(a)
    assert b.seat == 1


# --- Revancha y chat ------------------------------------------------------------------------------


def test_rematch_starts_a_new_match_with_a_new_commitment() -> None:
    h = Harness("tictactoe")
    x, o = play_tictactoe(h)
    first = h.last(x, "match_end")["fairness"]["commitment"]
    room = h.last(x, "room")
    assert room["status"] == "lobby" and room["commitment"] != first
    h.ready(x, seed="suerte")
    h.ready(o)
    start = h.last(x, "match_start")
    assert start["match"]["number"] == 2 and start["fairness"]["client_seeds"] == ["suerte", ""]


def test_chat_is_cleaned() -> None:
    h = Harness("nim")
    a = h.join("Ana")
    b = h.join("Luis", role="spectator")
    h.room.chat(a.id, "hola\n\n  a todos\u0000", h.now)
    h.deliver()
    assert h.last(b, "chat") == {
        "sender": {"participant": a.id, "name": "Ana", "seat": 0},
        "text": "hola a todos",
    }


def test_closing_a_room_aborts_the_match() -> None:
    h = Harness("nim")
    a, b = h.seat("Ana"), h.seat("Luis")
    h.room.close(h.now)
    h.deliver()
    assert h.last(a, "match_end")["reason"] == "aborted"
    assert h.last(b, "room")["status"] == "closed"
    with pytest.raises(RoomError):
        h.join("Eva")


# --- Registro de salas ----------------------------------------------------------------------------


def test_rooms_registry_tokens_and_sweep() -> None:
    from gamehub.server.rooms import Limits, Rooms

    rooms = Rooms(limits=Limits(max_rooms=2, idle_lobby=60, idle_running=600))
    room, token = rooms.create(game("nim"), now=0, host_name="Ana")
    found = rooms.session(token)
    assert found is not None and found[0] is room and room.participants[found[1]].host
    assert rooms.get(room.display_code.lower()) is room
    assert rooms.session("otro") is None
    p, other = rooms.join(room, now=0, name="Luis", role="player")
    assert rooms.session(other) == (room, p.id)
    rooms.create(game("nim"), now=0)
    with pytest.raises(RoomError) as info:
        rooms.create(game("nim"), now=0)
    assert info.value.code == "not_allowed"
    # Luis se desconecta: la sala sigue hasta que pasa el plazo sin nadie conectado.
    room.disconnect(p.id, 10)
    assert rooms.sweep(30) == []
    removed = rooms.sweep(71)
    assert room in removed and room.status == "closed"
    assert rooms.session(token) is None and len(rooms.rooms) == 0


def test_settings_patch_from_rest() -> None:
    from gamehub.server.rooms import Rooms

    rooms = Rooms()
    room, _ = rooms.create(
        game("dudo"),
        now=0,
        players=3,
        params={"dice": 2},
        settings={"clock": {"kind": "move", "seconds": 30}, "private": True},
    )
    info = room.info()
    assert info["settings"]["players"] == 3 and info["settings"]["clock"]["seconds"] == 30
    assert info["params"] == {"dice": 2} and rooms.listed() == []


def test_resume_with_nothing_missed_refreshes_the_state() -> None:
    h = Harness("nim")
    a, b = h.seat("Ana"), h.seat("Luis")
    match_id = h.last(a, "match_start")["match"]["id"]
    h.room.disconnect(a.id, h.now)
    h.clear()
    h.room.resume(a.id, h.now, {"match": match_id, "seq": 0})
    h.deliver()
    update = h.last(a, "update")
    assert [m["type"] for m in h.messages(a)] == ["welcome", "room", "update"]
    assert update["seq"] == 0 and update["events"] == [] and h.legal(a)
    assert b.seat == 1
