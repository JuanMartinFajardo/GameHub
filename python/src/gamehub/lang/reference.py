# SPDX-License-Identifier: Apache-2.0
"""Referencia breve de lo predefinido en Nomos (funciones, nombres de contexto, palabras clave y
tipos) para el autocompletado, el hover y la ayuda de firmas del servidor de lenguaje.

Cada función lleva su firma en Nomos y una frase. Las que tienen forma con variable
(`all(x in xs : p)`) llevan las dos firmas.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Entry:
    name: str
    signatures: tuple[str, ...]
    doc: str


def _fn(name: str, doc: str, *signatures: str) -> Entry:
    return Entry(name, signatures, doc)


FUNCTIONS: dict[str, Entry] = {
    e.name: e
    for e in (
        _fn("len", "Número de elementos de una lista, conjunto o texto.", "len(xs) -> Int"),
        _fn(
            "size",
            "Número de elementos de una zona o bolsa (también de una lista).",
            "size(z) -> Int",
        ),
        _fn("items", "Los elementos de una zona o bolsa, como lista.", "items(z) -> List<T>"),
        _fn("top", "El elemento de arriba de una zona (el último).", "top(z) -> T"),
        _fn("first", "El primer elemento de una lista.", "first(xs) -> T"),
        _fn("last", "El último elemento de una lista.", "last(xs) -> T"),
        _fn("only", "El único elemento de una colección de tamaño 1.", "only(xs) -> T"),
        _fn("reverse", "La lista al revés.", "reverse(xs) -> List<T>"),
        _fn("distinct", "La lista sin repetidos, en el orden original.", "distinct(xs) -> List<T>"),
        _fn("append", "La lista con un elemento más al final.", "append(xs, x) -> List<T>"),
        _fn("concat", "Una lista detrás de otra (también `xs + ys`).", "concat(xs, ys) -> List<T>"),
        _fn("union", "Unión de dos conjuntos.", "union(a, b) -> Set<T>"),
        _fn("intersection", "Intersección de dos conjuntos.", "intersection(a, b) -> Set<T>"),
        _fn(
            "difference",
            "Los elementos de la primera que no están en la segunda (también `xs - ys`).",
            "difference(xs, ys) -> List<T>",
        ),
        _fn(
            "subsets",
            "Los subconjuntos de una colección con entre `lo` y `hi` elementos (dominio de las "
            "acciones que eligen varias cartas).",
            "subsets(xs, lo, hi) -> List<List<T>>",
        ),
        _fn("range", "Los enteros de `a` a `b`, ambos incluidos (también `a..b`).", "range(a, b)"),
        _fn("slice", "El trozo [a, b) de una lista (también `xs[a:b]`).", "slice(xs, a, b)"),
        _fn(
            "contains", "Si la colección contiene el valor (también `x in xs`).", "contains(xs, x)"
        ),
        _fn("set", "Un conjunto con los valores dados.", "set(a, b, …) -> Set<T>"),
        _fn("abs", "Valor absoluto.", "abs(x) -> Int | Real"),
        _fn(
            "min",
            "El menor de varios valores o de una lista; con variable, el menor de una expresión.",
            "min(a, b, …)",
            "min(xs)",
            "min(x in xs : e)",
        ),
        _fn(
            "max",
            "El mayor de varios valores o de una lista; con variable, el mayor de una expresión.",
            "max(a, b, …)",
            "max(xs)",
            "max(x in xs : e)",
        ),
        _fn(
            "sum",
            "La suma de una lista de números o de una expresión para cada elemento.",
            "sum(xs) -> Int | Real",
            "sum(x in xs : e) -> Int | Real",
        ),
        _fn("rat", "El racional exacto a/b.", "rat(a, b) -> Real"),
        _fn("is_none", "Si un opcional no tiene valor.", "is_none(x) -> Bool"),
        _fn("unwrap", "El valor de un opcional (error de reglas si es none).", "unwrap(x) -> T"),
        _fn("ord", "La posición de un valor en su enumerado (desde 0).", "ord(v) -> Int"),
        _fn("next", "El asiento siguiente (vuelve al 0 tras el último).", "next(s) -> Seat"),
        _fn("prev", "El asiento anterior.", "prev(s) -> Seat"),
        _fn("other", "El otro asiento (juegos de 2 jugadores).", "other(s) -> Seat"),
        _fn(
            "seats_from",
            "Todos los asientos en orden empezando por `s`.",
            "seats_from(s) -> List<Seat>",
        ),
        _fn("cells", "Todas las casillas de una rejilla.", "cells(g) -> List<Cell>"),
        _fn(
            "lines",
            "Todas las líneas de k casillas seguidas de una rejilla (filas, columnas y "
            "diagonales).",
            "lines(g, k) -> List<List<Cell>>",
        ),
        _fn(
            "neighbors",
            "Las casillas vecinas de una casilla (las 8 de alrededor dentro de la rejilla).",
            "neighbors(g, c) -> List<Cell>",
        ),
        _fn("in_bounds", "Si una casilla está dentro de la rejilla.", "in_bounds(g, c) -> Bool"),
        _fn("cell", "La casilla (fila, columna).", "cell(f, c) -> Cell"),
        _fn(
            "win_loss",
            "Pagos: `gana` para el ganador y `pierde` para los demás.",
            "win_loss(ganador, gana, pierde) -> List<Real>",
        ),
        _fn("fill", "Pagos: el mismo valor para todos los asientos.", "fill(v) -> List<Real>"),
        _fn(
            "all",
            "Si la condición se cumple para todos los elementos.",
            "all(x in xs : cond) -> Bool",
        ),
        _fn(
            "any",
            "Si la condición se cumple para alguno de los elementos.",
            "any(x in xs : cond) -> Bool",
        ),
        _fn(
            "count",
            "Cuántos elementos cumplen la condición.",
            "count(x in xs : cond) -> Int",
        ),
        _fn(
            "argmax",
            "El elemento con el mayor valor de la expresión.",
            "argmax(x in xs : e) -> T",
        ),
        _fn(
            "argmin",
            "El elemento con el menor valor de la expresión.",
            "argmin(x in xs : e) -> T",
        ),
        _fn(
            "sort_by",
            "Los elementos ordenados por la expresión.",
            "sort_by(x in xs : e) -> List<T>",
        ),
        _fn("map", "La expresión para cada elemento.", "map(x in xs : e) -> List<U>"),
        _fn("filter", "Los elementos que cumplen la condición.", "filter(x in xs : cond)"),
        _fn(
            "flat_map",
            "Las listas de cada elemento, una detrás de otra.",
            "flat_map(x in xs : e) -> List<U>",
        ),
        _fn("at", "Si la partida está en ese nodo (o dentro de esa fase).", "at(Nodo) -> Bool"),
        _fn(
            "roll",
            "Azar: un dado de n caras (de 1 a n). Solo como `x = roll(n)` en un nodo chance.",
            "roll(n) -> Int",
        ),
        _fn(
            "random",
            "Azar: un elemento al azar. Solo como `x = random(xs)` en un nodo chance.",
            "random(xs) -> T",
        ),
        _fn(
            "sample",
            "Azar: un valor según sus probabilidades. Solo como `x = sample(…)` en un nodo chance.",
            "sample([(valor, prob), …]) -> T",
        ),
    )
}

#: Nombres de contexto: tipo y significado.
CONTEXT: dict[str, tuple[str, str]] = {
    "actor": ("Seat", "El asiento que juega la acción (en acciones y transiciones de decision)."),
    "seats": ("List<Seat>", "Todos los asientos, del 0 al último."),
    "num_players": ("Int", "El número de jugadores de la partida."),
    "viewer": ("Seat", "Quien mira (en las políticas de visibilidad)."),
    "owner": ("Seat", "El dueño de la parte per_player (en la visibilidad y al inicializar)."),
    "face_up": ("Bool", "Si el elemento está boca arriba (en la visibilidad de una zona)."),
    "payoff": ("List<Real>", "Los pagos de la partida (en los tests, al final)."),
    "active": ("List<Seat>", "Los asientos que pueden jugar ahora (en los tests)."),
}

TYPES: dict[str, str] = {
    "Bool": "true o false.",
    "Int": "Entero.",
    "Real": "Racional exacto (0.5 es 1/2).",
    "Text": "Texto.",
    "Seat": "Un asiento: de 0 a num_players - 1.",
    "Cell": "Una casilla de rejilla: (fila, columna).",
    "List": "Lista ordenada: List<T>.",
    "Set": "Conjunto: Set<T>.",
    "Map": "Diccionario: Map<K, V>.",
    "Zone": "Zona ordenada de elementos con cara (mazo, montón): Zone<T>.",
    "Bag": "Bolsa sin orden (una mano): Bag<T>.",
    "Grid": "Rejilla: Grid[ancho, alto] of T.",
    "per_player": "Un valor por asiento: per_player T.",
}

#: Miembros de cada clase de nodo (lo que va con `clave:`).
NODE_MEMBERS: dict[str, tuple[str, ...]] = {
    "decision": ("actor",),
    "simultaneous": ("actors",),
    "window": ("eligible", "mode", "order"),
    "chance": (),
    "auto": (),
    "phase": (),
    "terminal": ("payoff", "rank"),
}

NODE_KINDS: dict[str, str] = {
    "decision": "Un asiento elige una acción (actor: …).",
    "simultaneous": "Varios asientos eligen a la vez y en secreto (actors: …; resolve { … }).",
    "window": "Ventana de reacción: pueden responder o pasar (eligible, mode, order).",
    "chance": "Azar: sus efectos sortean (roll, random, sample, shuffle).",
    "auto": "Efectos sin esperar a nadie.",
    "phase": "Fase: un subdiagrama con su start, on_enter y on_exit.",
    "terminal": "Final de la partida: payoff (un número por asiento) y, si se quiere, rank.",
}

#: Sentencias (en efectos) con un ejemplo.
STATEMENTS: dict[str, str] = {
    "let": "let x = expresión",
    "if": "if cond { … } else { … }",
    "for": "for x in xs { … }",
    "move": "move top 1 from deck to hand[actor]",
    "flip": "flip top 1 of pile face_up",
    "shuffle": "shuffle deck",
    "deal": "deal 5 from deck to each hand",
    "reveal": "reveal hand[actor] to all",
    "emit": "emit nombre { campo: valor }",
    "reward": "reward 1 to actor",
    "fail": 'fail "caso imposible"',
}

#: Secciones de un juego.
GAME_SECTIONS: dict[str, str] = {
    "meta": 'meta { title: "…", version: "1.0.0" }',
    "players": "players 2  ·  players 2..4",
    "params": "params { nombre: Tipo = valor }",
    "enum": "enum Nombre { A, B }",
    "struct": "struct Nombre { campo: Tipo }",
    "state": "state { nombre: Tipo = valor }",
    "fn": "fn nombre(x: Tipo) -> Tipo = expresión",
    "flow": "flow { start -> Nodo … }",
    "ui": "ui { destino: pista }",
    "test": 'test "nombre" { play …  expect … }',
    "invariant": "invariant condición",
}

EXPRESSION_KEYWORDS = ("if", "else", "and", "or", "not", "in", "true", "false", "none", "case")
