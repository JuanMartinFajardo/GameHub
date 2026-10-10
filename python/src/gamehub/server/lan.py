# SPDX-License-Identifier: Apache-2.0
"""Red local: la dirección de este equipo en la LAN y las URL que se comparten."""

from __future__ import annotations

import contextlib
import socket


def lan_ip() -> str:
    """La IP de este equipo en la red local (la de la interfaz con salida a internet; si no hay
    red, 127.0.0.1). No envía ningún paquete: un socket UDP «conectado» solo elige la ruta."""
    with contextlib.suppress(OSError), socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("192.0.2.1", 9))  # TEST-NET-1 (RFC 5737): nunca se usa de verdad
        ip = s.getsockname()[0]
        if ip and not ip.startswith("0."):
            return ip
    return "127.0.0.1"


def base_url(host: str, port: int) -> str:
    """URL del servidor para compartir: si escucha en todas las interfaces, la IP de la LAN."""
    shown = lan_ip() if host in ("0.0.0.0", "::", "") else host
    if ":" in shown:
        shown = f"[{shown}]"
    return f"http://{shown}:{port}"
