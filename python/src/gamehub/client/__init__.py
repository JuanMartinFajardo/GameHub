# SPDX-License-Identifier: Apache-2.0
"""SDK cliente de Python para el servidor de partidas (Fase 3).

- `Client`: conexión asíncrona que sigue el estado de la sala y se reconecta sola.
- `AgentRunner` / `load_agent`: bots por la red con la misma interfaz `Agent` que en proceso.
- `create_room`, `fetch_json`: la API REST.
"""

from gamehub.client.agent import AgentLoadError, AgentRunner, RemoteObservation, load_agent
from gamehub.client.connection import (
    Client,
    ClientError,
    create_room,
    endpoints,
    fetch_json,
    target,
)

__all__ = [
    "AgentLoadError",
    "AgentRunner",
    "Client",
    "ClientError",
    "RemoteObservation",
    "create_room",
    "endpoints",
    "fetch_json",
    "load_agent",
    "target",
]
