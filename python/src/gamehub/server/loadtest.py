# SPDX-License-Identifier: Apache-2.0
"""Prueba de carga del servidor de partidas: muchas salas a la vez, cada una con bots que juegan
por WebSocket, midiendo la latencia de cada jugada (del `act` a la actualización que la refleja).

    gamehub loadtest --rooms 100 --game nim.game         # servidor propio, en un hilo
    gamehub loadtest --rooms 100 --server http://…:7420 --game-id nim   # un servidor ya en marcha
"""

from __future__ import annotations

import asyncio
import random
import statistics
import time
from dataclasses import dataclass, field

from gamehub.client.connection import Client, ClientError, create_room


@dataclass
class LoadReport:
    rooms: int
    clients: int
    matches: int = 0
    steps: int = 0
    failures: list[str] = field(default_factory=list)
    latencies: list[float] = field(default_factory=list)
    seconds: float = 0.0

    def percentile(self, q: float) -> float:
        if not self.latencies:
            return 0.0
        ordered = sorted(self.latencies)
        return ordered[min(len(ordered) - 1, int(q * len(ordered)))]

    def summary(self) -> str:
        lat = [x * 1000 for x in self.latencies]
        mean = statistics.fmean(lat) if lat else 0.0
        rate = f" ({self.steps / self.seconds:.0f}/s)" if self.seconds else ""
        first = f" ({self.failures[0]})" if self.failures else ""
        p50, p95 = self.percentile(0.5) * 1000, self.percentile(0.95) * 1000
        return "\n".join(
            [
                f"{self.rooms} salas · {self.clients} conexiones · {self.matches} partidas "
                f"terminadas en {self.seconds:.1f} s",
                f"  jugadas: {self.steps}{rate}",
                f"  latencia por jugada: media {mean:.1f} ms · p50 {p50:.1f} ms · "
                f"p95 {p95:.1f} ms · máx {max(lat, default=0):.1f} ms",
                f"  fallos: {len(self.failures)}{first}",
            ]
        )


async def run_load(
    server: str,
    game_id: str,
    *,
    rooms: int = 100,
    players: int = 2,
    matches: int = 1,
    seed: int = 0,
    timeout: float = 300.0,
) -> LoadReport:
    """Crea `rooms` salas de `game_id` y llena cada una con `players` bots aleatorios que juegan
    `matches` partidas seguidas."""
    report = LoadReport(rooms, rooms * players)
    started = time.perf_counter()
    created = await asyncio.gather(
        *(create_room(server, game=game_id, players=players) for _ in range(rooms))
    )
    tasks = [
        _player(server, room["code"], seed * 1_000_003 + i * players + s, report, matches, s == 0)
        for i, room in enumerate(created)
        for s in range(players)
    ]
    try:
        await asyncio.wait_for(asyncio.gather(*tasks), timeout)
    except TimeoutError:
        report.failures.append(f"no han terminado en {timeout:.0f} s")
    report.seconds = time.perf_counter() - started
    return report


async def _player(
    server: str, code: str, seed: int, report: LoadReport, matches: int, counts: bool
) -> None:
    rng = random.Random(seed)
    loop = asyncio.get_running_loop()
    try:
        async with Client(
            server, name=f"carga {seed % 10_000}", kind="bot", legal_limit=20_000
        ) as c:
            await c.join(code)
            played = 0
            sent_at: float | None = None
            ready_for = 0
            async for msg in c:
                kind, data = msg["type"], msg["data"]
                if kind == "room" and data["status"] == "lobby" and ready_for == played:
                    ready_for += 1
                    await c.ready()
                elif kind == "update":
                    if sent_at is not None:
                        report.latencies.append(loop.time() - sent_at)
                        sent_at = None
                    legal = c.legal
                    if legal:
                        sent_at = loop.time()
                        report.steps += 1
                        await c.act(rng.choice(legal))
                elif kind == "match_end":
                    played += 1
                    if counts:
                        report.matches += 1
                    if played >= matches:
                        await c.leave()
                        return
                elif kind in ("rejected", "error"):
                    report.failures.append(f"{kind}: {data.get('detail') or data.get('message')}")
    except ClientError as exc:
        report.failures.append(f"{exc.code}: {exc.message}")
