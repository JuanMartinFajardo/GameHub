# SPDX-License-Identifier: Apache-2.0
"""Análisis de juegos sobre la GameIR: avisos estáticos (`lint`) y clasificación (`classify`).
Más adelante: viabilidad, árbol, forma normal, solvers (ver docs/wiki/architecture.md)."""

from gamehub.analysis.classify import Classification, classify
from gamehub.analysis.lint import Finding, lint

__all__ = ["Classification", "Finding", "classify", "lint"]
