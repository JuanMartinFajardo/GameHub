# SPDX-License-Identifier: Apache-2.0
"""Análisis de juegos.

- Sobre la GameIR, sin jugar: avisos estáticos (`lint`) y clasificación (`classify`).
- Teoría de juegos (fase 7, docs/wiki/game-theory.md), en submódulos: `feasibility` (asesor de
  viabilidad), `tree` (forma extensiva y grafo de estados), `normal_form`, `nash` (equilibrios,
  dominancia, correlado, Pareto), `lp` (programación lineal exacta o con HiGHS), `search`
  (alfa-beta e inducción hacia atrás), `policy`, `cfr` y `sequence_form` (información
  imperfecta), `cgt` (Sprague–Grundy), `coop` (juegos cooperativos), `repeated` (torneos de
  Axelrod), `export` (Gambit), `openspiel`, `widgets` (notebooks) y `report` (`gamehub analyze`).
"""

from gamehub.analysis.classify import Classification, classify
from gamehub.analysis.lint import Finding, lint

__all__ = ["Classification", "Finding", "classify", "lint"]
