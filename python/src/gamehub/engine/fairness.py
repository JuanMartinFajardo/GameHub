# SPDX-License-Identifier: Apache-2.0
"""Azar verificable ("provably fair"): compromiso y revelación, esquema `gamehub-fair/1`.

1. Antes de la partida, el servidor elige en secreto `server_seed` (64 cifras hexadecimales) y
   publica su compromiso: `commitment = SHA-256("gamehub-fair/1:commit:" + server_seed)`.
2. Cada jugador puede aportar su propia semilla (un texto corto) al declararse listo. Como no
   conoce `server_seed`, no puede predecir el resultado; como el servidor ya se comprometió, no
   puede elegir una semilla a la vista de las de los jugadores.
3. La semilla de la partida sale de las dos partes:
   `SHA-256(JSON canónico {"scheme", "server_seed", "client_seeds"})`, primeros 8 bytes como
   entero sin signo y desplazados 11 bits: 53 bits, representables sin pérdida en cualquier JSON.
   El azar de la partida es PCG32(semilla, flujo 1), muestreado punto de azar a punto de azar.
4. Al terminar se revela `server_seed`: cualquiera puede comprobar el compromiso, recalcular la
   semilla y re-simular el replay comprobando que cada resultado de azar es el que da PCG32.

`verify` hace las tres comprobaciones sobre un replay que lleva el bloque `fairness`.
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Sequence
from typing import Any

from gamehub.engine.errors import EngineError
from gamehub.engine.game import Game
from gamehub.engine.rng import STREAM_CHANCE, Pcg32
from gamehub.engine.state import State
from gamehub.ir.hashing import canonical_json

SCHEME = "gamehub-fair/1"
SEED_BITS = 53
#: Longitud máxima de la semilla que aporta un jugador.
CLIENT_SEED_MAX = 64


class FairnessError(EngineError):
    """El azar de la partida no cuadra con el compromiso publicado."""


def new_server_seed() -> str:
    return secrets.token_hex(32)


def commitment(server_seed: str) -> str:
    return hashlib.sha256(f"{SCHEME}:commit:{server_seed}".encode()).hexdigest()


def derive_seed(server_seed: str, client_seeds: Sequence[str]) -> int:
    """Semilla de la partida (53 bits) a partir de la del servidor y las de los jugadores (una
    por asiento, `""` si no aportó ninguna)."""
    material = {"scheme": SCHEME, "server_seed": server_seed, "client_seeds": list(client_seeds)}
    digest = hashlib.sha256(canonical_json(material).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") >> (64 - SEED_BITS)


def valid_client_seed(text: str) -> bool:
    return len(text) <= CLIENT_SEED_MAX and text.isprintable()


def block(server_seed: str, client_seeds: Sequence[str], *, reveal: bool) -> dict[str, Any]:
    """El bloque `fairness` de un replay (sin `server_seed` mientras la partida sigue)."""
    data: dict[str, Any] = {
        "scheme": SCHEME,
        "commitment": commitment(server_seed),
        "client_seeds": list(client_seeds),
    }
    if reveal:
        data["server_seed"] = server_seed
    return data


def verify(game: Game, data: dict[str, Any]) -> State:
    """Comprueba el azar de un replay con bloque `fairness` revelado y devuelve el estado final.

    Errores: `FairnessError` si el compromiso o la semilla no cuadran, o si un resultado de azar
    no es el que da PCG32 con esa semilla; `ReplayMismatch` si el replay no se reproduce.
    """
    from gamehub.engine.replay import replay

    fair = data.get("fairness")
    if not isinstance(fair, dict):
        raise FairnessError("el replay no lleva el bloque 'fairness'")
    if fair.get("scheme") != SCHEME:
        raise FairnessError(f"esquema desconocido: {fair.get('scheme')!r}")
    server_seed = fair.get("server_seed")
    if not isinstance(server_seed, str):
        raise FairnessError("la semilla del servidor aún no se ha revelado")
    if commitment(server_seed) != fair.get("commitment"):
        raise FairnessError("la semilla revelada no corresponde al compromiso publicado")
    seed = derive_seed(server_seed, fair.get("client_seeds") or [])
    if seed != data.get("seed"):
        raise FairnessError(f"la semilla de la partida debía ser {seed}, no {data.get('seed')}")
    return replay(game, data, rng=Pcg32(seed, STREAM_CHANCE))
