# SPDX-License-Identifier: Apache-2.0
"""Contexto de evaluación de expresiones y sentencias."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gamehub.engine.events import Event
    from gamehub.engine.game import GameDef
    from gamehub.engine.rng import Draws


#: Observador público (un espectador): no ocupa ningún asiento. Como `viewer`, no coincide con
#: ningún `owner`; un predicado de visibilidad que no se puede evaluar para él (por ejemplo, porque
#: usa `viewer` como índice de un asiento) cuenta como falso: no ve ese dato.
PUBLIC = -1


class Ctx:
    """Compartido durante una evaluación: almacén de trabajo, parámetros, azar y eventos.

    `store` es la lista de valores de las variables de estado (índice = orden de declaración).
    Durante la ejecución de efectos se modifica en sitio; el `State` resultante la congela.

    `memo` guarda los resultados de las funciones puras de la IR (las que no dependen del nodo ni
    de `actor`, `viewer` u `owner`) mientras `store` no cambia: cada escritura en el estado lo
    vacía. `None` lo desactiva. Es una caché: no cambia ningún resultado.
    """

    __slots__ = ("draws", "events", "game", "memo", "n", "params", "path", "store")

    def __init__(
        self,
        game: GameDef,
        store: list[Any] | tuple[Any, ...],
        params: dict[str, Any],
        n: int,
        path: tuple[str, ...] = (),
        draws: Draws | None = None,
        memo: dict[Any, Any] | None = None,
    ) -> None:
        self.game = game
        self.memo = memo
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
        """Copia con algunos campos cambiados (para los casos poco frecuentes: `bind` y
        `with_args` son los rápidos)."""
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

    def _copy(self, args: dict[str, Any], locals_: dict[str, Any]) -> Env:
        env = Env.__new__(Env)
        env.ctx = self.ctx
        env.args = args
        env.locals = locals_
        env.actor = self.actor
        env.viewer = self.viewer
        env.owner = self.owner
        env.face_up = self.face_up
        return env

    def bind(self, name: str, value: Any) -> Env:
        locals_ = dict(self.locals)
        locals_[name] = value
        return self._copy(self.args, locals_)

    def child(self) -> Env:
        """Copia con locales propios (un bloque de sentencias puede añadir `let`)."""
        return self._copy(self.args, dict(self.locals))

    def with_args(self, args: dict[str, Any]) -> Env:
        return self._copy(args, self.locals)
