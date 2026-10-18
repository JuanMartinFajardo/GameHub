# SPDX-License-Identifier: Apache-2.0
"""Construcción de la rueda: las apps web compiladas (tras `pnpm build`), si existen, viajan dentro
del paquete: la de jugar (`web/apps/play/dist`) como `gamehub/webapp`, donde la busca
`gamehub serve`, la del Studio (`web/apps/studio/dist`) como `gamehub/studioapp`, donde la busca
`gamehub studio`, y la del hub (`web/apps/hub/dist`) como `gamehub/hubapp`, donde la busca
`gamehub hub serve`."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):  # type: ignore[type-arg]
    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        if self.target_name != "wheel":
            return
        apps = Path(self.root).parent / "web" / "apps"
        for app, target, what in (
            ("play", "gamehub/webapp", "la app web"),
            ("studio", "gamehub/studioapp", "el Studio"),
            ("hub", "gamehub/hubapp", "la app del hub"),
        ):
            dist = apps / app / "dist"
            if (dist / "index.html").is_file():
                build_data["force_include"][str(dist)] = target
            else:
                self.app.display_warning(
                    f"La rueda no lleva {what}: compílalo antes con `pnpm build` en la raíz."
                )
