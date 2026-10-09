# SPDX-License-Identifier: Apache-2.0
"""Errores del motor."""

from __future__ import annotations


class EngineError(Exception):
    """Base de los errores del motor."""


class RuleError(EngineError):
    """Las reglas del juego llevan a una situación imposible (un fallo de diseño del juego):
    índice fuera de rango, ninguna transición aplicable, decisión sin acciones legales…"""

    def __init__(self, message: str, where: str | None = None) -> None:
        super().__init__(f"{where}: {message}" if where else message)
        self.where = where


class IllegalAction(EngineError):
    """Se intentó aplicar una acción que no es legal en el estado actual."""


class InvalidParams(EngineError):
    """Parámetros de partida inválidos (tipo, rango de jugadores o restricciones)."""


class NotEnumerable(EngineError):
    """Un nodo de azar tiene demasiados resultados para enumerarlos: hay que muestrearlo."""
