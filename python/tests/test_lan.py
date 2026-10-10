# SPDX-License-Identifier: Apache-2.0
"""LAN: dirección local, QR del enlace, anuncio y descubrimiento por mDNS, y los comandos
`gamehub host`, `gamehub rooms` y `gamehub join` de punta a punta en subprocesos.

Las pruebas de mDNS usan la multidifusión de la red real: solo se ejecutan con
`GAMEHUB_LAN_TESTS=1` (en CI no suele estar disponible)."""

from __future__ import annotations

import asyncio
import ipaddress
import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from gamehub.client import create_room
from gamehub.client.play import find_room
from gamehub.server.catalog import Catalog
from gamehub.server.lan import Advertiser, base_url, discover, lan_ip, qr_text
from gamehub.server.rooms import Rooms
from gamehub.server.run import ServerThread
from server_harness import game

ROOT = Path(__file__).resolve().parents[2]
lan = pytest.mark.skipif(
    os.environ.get("GAMEHUB_LAN_TESTS") != "1", reason="mDNS: define GAMEHUB_LAN_TESTS=1"
)


def test_lan_ip_and_urls() -> None:
    ip = ipaddress.ip_address(lan_ip())
    assert ip.version == 4
    assert base_url("127.0.0.1", 7420) == "http://127.0.0.1:7420"
    assert base_url("0.0.0.0", 7420) == f"http://{lan_ip()}:7420"
    assert base_url("::1", 80) == "http://[::1]:80"


def test_qr_text() -> None:
    text = qr_text("http://192.168.1.20:7420/r/K7FQ2P")
    lines = text.rstrip("\n").splitlines()
    assert len(lines) > 10 and len({len(line) for line in lines}) == 1
    assert set("".join(lines)) <= {"█", "▀", "▄", " "}
    assert text == qr_text("http://192.168.1.20:7420/r/K7FQ2P")


@lan
def test_mdns_advertise_discover_and_find_room() -> None:
    rooms = Rooms(Catalog([game("nim")]))
    with ServerThread(rooms) as server:

        async def scenario() -> tuple[list[str], str | None, str]:
            created = await create_room(server.url, game="nim")
            advertiser = Advertiser("Prueba de GameHub", server.port, ip="127.0.0.1")
            assert await advertiser.start()
            try:
                found = await discover(2.0)
                where = await find_room(created["code"], timeout=2.0)
            finally:
                await advertiser.stop()
            return [f.url for f in found], where, created["code"]

        urls, where, _ = asyncio.run(scenario())
        assert server.url in urls
        assert where == server.url


def _gamehub(*argv: str, **kw: object) -> subprocess.Popen[str]:
    code = f"import sys; from gamehub.cli import main; sys.exit(main({list(argv)!r}))"
    return subprocess.Popen(
        [sys.executable, "-c", code],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        **kw,  # type: ignore[arg-type]
    )


def test_host_rooms_and_join_commands() -> None:
    nim = str(ROOT / "games" / "nim" / "nim.game")
    host = _gamehub(
        "host",
        nim,
        "--no-play",
        "--no-mdns",
        "--no-qr",
        "--host",
        "127.0.0.1",
        "--port",
        "0",
        "--db",
        ":memory:",
        "--player",
        "Ana",
    )
    try:
        assert host.stdout is not None
        lines = [host.stdout.readline() for _ in range(3)]
        assert lines[0].startswith("GameHub · Nim"), lines
        link = lines[2].split()[-1]
        server = link.rsplit("/r/", 1)[0]
        listing = _gamehub("rooms", "--server", server)
        listed, _ = listing.communicate(timeout=30)
        assert listing.returncode == 0 and "Nim" in listed, listed
        joiner = _gamehub("join", link, "--player", "Luis", stdin=subprocess.PIPE)
        out, _ = joiner.communicate("/salir\n", timeout=30)
        assert joiner.returncode == 0 and "Has salido de la sala." in out, out
    finally:
        host.send_signal(signal.SIGINT)
        rest, _ = host.communicate(timeout=15)
    assert host.returncode == 0, rest
