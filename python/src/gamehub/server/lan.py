# SPDX-License-Identifier: Apache-2.0
"""Red local: la dirección de este equipo en la LAN, el QR del enlace de una sala y el anuncio y
descubrimiento de servidores por mDNS (`_gamehub._tcp`, como las impresoras o los altavoces).

mDNS es un extra: si la red no lo permite (multidifusión bloqueada, sin interfaces), el servidor
funciona igual y los demás se unen con el enlace o la IP.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import socket
from dataclasses import dataclass
from typing import Any

from gamehub import __version__

SERVICE = "_gamehub._tcp.local."


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


def qr_text(url: str) -> str:
    """El enlace como código QR para la terminal (medio bloque por módulo)."""
    import segno

    out = io.StringIO()
    segno.make(url, error="m").terminal(out=out, compact=True)
    return out.getvalue()


# --- mDNS -----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Found:
    """Un servidor de partidas descubierto en la LAN."""

    name: str
    url: str
    version: str


class Advertiser:
    """Anuncia por mDNS un servidor de partidas mientras está abierto."""

    def __init__(self, name: str, port: int, *, ip: str | None = None) -> None:
        self.name = name
        self.port = port
        self.ip = ip or lan_ip()
        self._zc: Any = None
        self._info: Any = None

    async def start(self) -> bool:
        """Empieza a anunciar. Devuelve si ha sido posible."""
        try:
            from zeroconf import ServiceInfo
            from zeroconf.asyncio import AsyncZeroconf

            instance = f"{self.name} ({socket.gethostname()}:{self.port})"[:60]
            self._info = ServiceInfo(
                SERVICE,
                f"{instance}.{SERVICE}",
                port=self.port,
                parsed_addresses=[self.ip],
                properties={"v": "1", "name": self.name, "version": __version__},
            )
            self._zc = AsyncZeroconf()
            await (await self._zc.async_register_service(self._info, allow_name_change=True))
        except Exception:  # sin red, multidifusión bloqueada… el servidor sigue sin mDNS
            await self.stop()
            return False
        return True

    async def stop(self) -> None:
        zc, info = self._zc, self._info
        self._zc = self._info = None
        if zc is None:
            return
        with contextlib.suppress(Exception):
            if info is not None:
                await zc.async_unregister_service(info)
            await zc.async_close()


async def discover(timeout: float = 2.0) -> list[Found]:
    """Servidores de partidas anunciados en la LAN (los que responden en `timeout` segundos)."""
    try:
        from zeroconf import ServiceStateChange
        from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo, AsyncZeroconf
    except ImportError:
        return []
    names: list[str] = []

    def on_change(**kw: Any) -> None:
        if kw["state_change"] is ServiceStateChange.Added and kw["name"] not in names:
            names.append(kw["name"])

    try:
        zc = AsyncZeroconf()
    except Exception:
        return []
    found: list[Found] = []
    try:
        browser = AsyncServiceBrowser(zc.zeroconf, SERVICE, handlers=[on_change])
        await asyncio.sleep(timeout)
        for name in names:
            info = AsyncServiceInfo(SERVICE, name)
            if not await info.async_request(zc.zeroconf, 1500):
                continue
            addresses = [a for a in info.parsed_addresses() if ":" not in a] or [
                f"[{a}]" for a in info.parsed_addresses()
            ]
            if not addresses or info.port is None:
                continue
            props = {
                (k.decode() if isinstance(k, bytes) else str(k)): (
                    v.decode() if isinstance(v, bytes) else ""
                )
                for k, v in (info.properties or {}).items()
            }
            label = props.get("name") or name.removesuffix(f".{SERVICE}")
            url = f"http://{addresses[0]}:{info.port}"
            if all(f.url != url for f in found):
                found.append(Found(label, url, props.get("version", "")))
        await browser.async_cancel()
    except Exception:
        return found
    finally:
        with contextlib.suppress(Exception):
            await zc.async_close()
    return found
