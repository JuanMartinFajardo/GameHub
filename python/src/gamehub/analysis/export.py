# SPDX-License-Identifier: Apache-2.0
"""Exportación a los formatos de Gambit (https://gambitproject.org): `.efg` (forma extensiva) y
`.nfg` (forma normal, versión de pagos). Así se pueden usar sus solvers de n jugadores, que son
maduros, y su interfaz gráfica.

- `.efg`: los nodos en preorden; los de azar con la probabilidad exacta de cada resultado
  (racionales `1/6`), los de decisión con el jugador (desde 1) y el número de su conjunto de
  información, y los terminales con un resultado propio y los pagos.
- `.nfg`: las estrategias con nombre y los pagos de cada perfil, con la estrategia del primer
  jugador variando más deprisa.
"""

from __future__ import annotations

import itertools
import re
import unicodedata
from fractions import Fraction
from typing import Any

from gamehub.analysis.normal_form import NormalForm
from gamehub.analysis.tree import GameTree

_ASCII = str.maketrans({"·": "|", "→": "->", "–": "-", "—": "-", "∅": "{}", "×": "x", "▒": "?"})


def _q(text: str) -> str:
    """Una etiqueta entre comillas. Gambit solo admite ASCII imprimible, sin espacios al principio
    o al final ni dos seguidos: se translitera («Póker» → «Poker») y se compactan los espacios."""
    text = unicodedata.normalize("NFKD", text.translate(_ASCII))
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"\s+", " ", text).strip()
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _n(x: Any) -> str:
    x = Fraction(x)
    return str(x.numerator) if x.denominator == 1 else f"{x.numerator}/{x.denominator}"


def _player_names(n: int) -> str:
    return "{ " + " ".join(_q(f"Player {i + 1}") for i in range(n)) + " }"


def to_efg(tree: GameTree, title: str | None = None) -> str:
    lines = [f"EFG 2 R {_q(title or tree.title)} {_player_names(tree.num_players)}", _q(""), ""]
    # Los conjuntos de información se numeran desde 1 dentro de cada jugador.
    numbers: dict[int, int] = {}
    per_player = [0] * tree.num_players
    for s in tree.infosets:
        per_player[s.player] += 1
        numbers[s.id] = per_player[s.player]
    chance_sets = 0
    outcomes = 0
    stack = [0]
    while stack:
        h = stack.pop()
        node = tree.nodes[h]
        if node.kind == "terminal":
            outcomes += 1
            payoffs = ", ".join(_n(u) for u in node.payoffs)
            lines.append(f't "" {outcomes} "" {{ {payoffs} }}')
        elif node.kind == "chance":
            chance_sets += 1
            branches = " ".join(
                f"{_q(label)} {_n(p)}" for label, p in zip(node.labels, node.probs, strict=True)
            )
            lines.append(f'c "" {chance_sets} "" {{ {branches} }} 0')
        else:
            info = tree.infosets[node.infoset]
            actions = " ".join(_q(label) for label in info.labels)
            lines.append(
                f'p "" {node.player + 1} {numbers[node.infoset]} {_q(info.description)} '
                f"{{ {actions} }} 0"
            )
        stack.extend(reversed(node.children))
    return "\n".join(lines) + "\n"


def to_nfg(nf: NormalForm, title: str | None = None) -> str:
    strategies = " ".join("{ " + " ".join(_q(s) for s in names) + " }" for names in nf.strategies)
    lines = [
        f"NFG 1 R {_q(title or nf.title)} {_player_names(nf.num_players)} {{ {strategies} }}",
        _q(""),
        "",
    ]
    values: list[str] = []
    # El primer jugador varía más deprisa: se recorre con el orden de los jugadores invertido.
    for reversed_profile in itertools.product(*(range(k) for k in reversed(nf.shape))):
        profile = tuple(reversed(reversed_profile))
        values.extend(_n(u) for u in nf.payoffs[profile])
    lines.append(" ".join(values))
    return "\n".join(lines) + "\n"
