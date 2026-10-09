# SPDX-License-Identifier: Apache-2.0
"""Contexto de evaluación de expresiones y sentencias."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gamehub.engine.events import Event
    from gamehub.engine.game import GameDef
    from gamehub.engine.rng import Draws


class Ctx:
    """Compartido durante una evaluación: almacén de trabajo, parámetros, azar y eventos.

    `store` es la lista de valores de las variables de estado (índice = orden de declaración).
    Durante la ejecución de efectos se modifica en sitio; el `State` resultante la congela.
    """

    __slots__ = ("draws", "events", "game", "n", "params", "path", "store")

    def __init__(
        self,
        game: GameDef,
        store: list[Any],
        params: dict[str, Any],
        n: int,
        path: tuple[str, ...] = (),
        draws: Draws | None = None,
    ) -> None:
        self.game = game
        self.store = store
        self.params = params
        self.n = n
        self.path = path
        self.draws = draws
        self.events: list[Event] = []


class Env:
    """Ámbito léxico: argumentos, locales y los asientos de contexto (actor, viewer, owner)."""

    __slots__ = ("actor", "args", "ctx", "face_up", "locals", "owner", "viewer")

    def __init__(
        self,
        ctx: Ctx,
        *,
        args: dict[str, Any] | None = None,
        locals_: dict[str, Any] | None = None,
        actor: int | None = None,
        viewer: int | None = None,
        owner: int | None = None,
        face_up: bool | None = None,
    ) -> None:
        self.ctx = ctx
        self.args = args if args is not None else {}
        self.locals = locals_ if locals_ is not None else {}
        self.actor = actor
        self.viewer = viewer
        self.owner = owner
        self.face_up = face_up

    def replace(self, **changes: Any) -> Env:
        env = Env(
            self.ctx,
            args=self.args,
            locals_=self.locals,
            actor=self.actor,
            viewer=self.viewer,
            owner=self.owner,
            face_up=self.face_up,
        )
        for key, value in changes.items():
            setattr(env, key, value)
        return env

    def bind(self, name: str, value: Any) -> Env:
        return self.replace(locals={**self.locals, name: value})

    def child(self) -> Env:
        """Copia con locales propios (un bloque de sentencias puede añadir `let`)."""
        return self.replace(locals=dict(self.locals))

    def with_args(self, args: dict[str, Any]) -> Env:
        return self.replace(args=args)
