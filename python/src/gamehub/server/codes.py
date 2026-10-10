# SPDX-License-Identifier: Apache-2.0
"""Códigos de sala: 6 caracteres de Crockford base32 (sin I, L, O ni U), p. ej. `K7F-Q2P`.

Al leerlos se admiten minúsculas, guiones y espacios, y las letras que se confunden con cifras
valen como ellas (O → 0; I, L → 1), como en Crockford.
"""

from __future__ import annotations

import secrets
from collections.abc import Container

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
LENGTH = 6
_CONFUSABLE = str.maketrans({"O": "0", "I": "1", "L": "1"})


def new_code(taken: Container[str] = ()) -> str:
    while True:
        code = "".join(secrets.choice(ALPHABET) for _ in range(LENGTH))
        if code not in taken:
            return code


def normalize(text: str) -> str | None:
    """El código canónico (mayúsculas, sin separadores) o `None` si no es un código válido."""
    code = "".join(text.split()).replace("-", "").upper().translate(_CONFUSABLE)
    if len(code) != LENGTH or any(c not in ALPHABET for c in code):
        return None
    return code


def display(code: str) -> str:
    half = LENGTH // 2
    return f"{code[:half]}-{code[half:]}"
