# SPDX-License-Identifier: Apache-2.0
"""Construcción de la rueda: la app web compilada (`web/apps/play/dist`, tras `pnpm build`), si
existe, viaja dentro del paquete como `gamehub/webapp`, donde la busca `gamehub serve`."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):  # type: ignore[type-arg]
    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        if self.target_name != "wheel":
            return
        dist = Path(self.root).parent / "web" / "apps" / "play" / "dist"
        if (dist / "index.html").is_file():
            build_data["force_include"][str(dist)] = "gamehub/webapp"
        else:
            self.app.display_warning(
                "La rueda no lleva la app web: compílala antes con `pnpm build` en la raíz."
            )
