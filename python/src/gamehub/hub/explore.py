# SPDX-License-Identifier: AGPL-3.0-or-later
"""Explorar el hub: búsqueda por propiedades matemáticas y el árbol genealógico de un juego.

Cada versión publicada se clasifica sola (jugadores, azar, información, simultaneidad, suma cero)
y su análisis le añade la ramificación y la duración medias; así se puede buscar "2 jugadores,
suma cero, información perfecta, ramificación < 10" o "juegos con información oculta para 4". La
búsqueda mira la última versión de cada repositorio.

La consulta de texto entiende esas propiedades escritas en inglés o en español (`parse_query`);
lo que no reconoce se busca en el nombre, la descripción, el título y el dueño.
"""

from __future__ import annotations

import re
from typing import Any

from gamehub.hub import registry
from gamehub.hub.service import Account, Hub, Repo

_LATEST = (
    "(SELECT v2.id FROM releases v2 WHERE v2.repo = r.id AND v2.yanked = 0"
    " ORDER BY v2.major DESC, v2.minor DESC, v2.patch DESC, v2.pre = '' DESC, v2.pre DESC LIMIT 1)"
)

#: Palabras de la consulta que son propiedades (inglés y español): patrón -> (filtro, valor).
_PHRASES: list[tuple[str, str, Any]] = [
    # En orden: lo más concreto antes ("suma no nula" antes que "suma", "sin azar" antes que
    # "azar").
    (r"non[- ]zero[- ]sum|general[- ]sum|suma no nula|suma general", "zero_sum", False),
    (r"zero[- ]sum|suma cero", "zero_sum", True),
    (
        r"(?:imperfect|hidden) information|informaci[oó]n (?:imperfecta|oculta)",
        "perfect_information",
        False,
    ),
    (r"perfect information|informaci[oó]n perfecta", "perfect_information", True),
    (r"deterministic|determinista|sin azar|no chance", "chance", False),
    (r"(?:with )?chance|(?:con )?azar|dice|dados|random", "chance", True),
    (r"turn[- ]based|por turnos|sequential|secuencial", "simultaneous", False),
    (r"simultaneous|simult[aá]ne[oa]s?", "simultaneous", True),
]


def parse_query(text: str) -> tuple[dict[str, Any], str]:
    """Las propiedades que nombra una consulta y lo que queda como texto libre."""
    filters: dict[str, Any] = {}
    rest = " " + text.lower() + " "
    m = re.search(r"\b(\d+)\s*(?:players?|jugador(?:es)?|p\b)", rest)
    if m:
        filters["players"] = int(m[1])
        rest = rest.replace(m[0], " ")
    m = re.search(
        r"(?:branching|ramificaci[oó]n)\s*(?:<=?|under|menor que|de menos de)\s*(\d+(?:\.\d+)?)",
        rest,
    )
    if m:
        filters["max_branching"] = float(m[1])
        rest = rest.replace(m[0], " ")
    for pattern, key, value in _PHRASES:
        m = re.search(rf"(?<![\w-])(?:{pattern})(?![\w-])", rest)
        if m and key not in filters:
            filters[key] = value
            rest = rest.replace(m[0], " ")
    for tag in re.findall(r"#([a-z0-9-]+)", rest):
        filters.setdefault("tags", []).append(tag)
        rest = rest.replace("#" + tag, " ")
    words = [w for w in re.split(r"[\s,;]+", rest) if w and w not in _STOP]
    return filters, " ".join(words)


_STOP = frozenset(
    {"and", "with", "for", "games", "game", "y", "con", "para", "juegos", "juego", "de", "a", "the"}
)


def search(
    hub: Hub,
    *,
    q: str = "",
    players: int | None = None,
    chance: bool | None = None,
    perfect_information: bool | None = None,
    simultaneous: bool | None = None,
    zero_sum: bool | None = None,
    max_branching: float | None = None,
    max_length: float | None = None,
    tags: list[str] | None = None,
    kind: str | None = None,
    owner: str | None = None,
    sort: str = "stars",
    limit: int = 30,
    offset: int = 0,
    viewer: Account | None = None,
) -> dict[str, Any]:
    parsed, text = parse_query(q) if q else ({}, "")
    filters = {
        "players": players,
        "chance": chance,
        "perfect_information": perfect_information,
        "simultaneous": simultaneous,
        "zero_sum": zero_sum,
        "max_branching": max_branching,
        "tags": tags,
    }
    for key, value in parsed.items():
        if filters.get(key) in (None, []):
            filters[key] = value
    where = ["r.hidden = 0"]
    params: list[Any] = []
    if text:
        for word in text.split():
            like = f"%{word}%"
            where.append(
                "(lower(r.name) LIKE ? OR lower(r.description) LIKE ? OR lower(a.name) LIKE ?"
                " OR lower(coalesce(v.title, '')) LIKE ? OR lower(coalesce(v.tags, '')) LIKE ?)"
            )
            params += [like] * 5
    if filters["players"] is not None:
        where.append("v.min_players <= ? AND v.max_players >= ?")
        params += [filters["players"], filters["players"]]
    for key in ("chance", "perfect_information", "simultaneous", "zero_sum"):
        if filters[key] is not None:
            where.append(f"v.{key} = ?")
            params.append(int(bool(filters[key])))
    if filters["max_branching"] is not None:
        where.append("v.branching IS NOT NULL AND v.branching <= ?")
        params.append(filters["max_branching"])
    if max_length is not None:
        where.append("v.length IS NOT NULL AND v.length <= ?")
        params.append(max_length)
    for tag in filters["tags"] or []:
        where.append("v.tags LIKE ?")
        params.append(f"%,{tag},%")
    if kind:
        where.append("r.kind = ?")
        params.append(kind)
    if owner:
        where.append("a.name = ?")
        params.append(owner)
    order = {
        "stars": "r.stars DESC, r.updated DESC",
        "recent": "r.updated DESC",
        "name": "a.name, r.name",
        "players": "v.min_players, v.max_players",
    }.get(sort, "r.stars DESC, r.updated DESC")
    sql = (
        f"FROM repos r JOIN accounts a ON a.id = r.owner LEFT JOIN releases v ON v.id = {_LATEST}"
        f" WHERE {' AND '.join(where)}"
    )
    total = hub.db.value(f"SELECT count(*) AS n {sql}", params)
    rows = hub.db.all(
        f"SELECT r.id AS repo_id, v.id AS release_id {sql} ORDER BY {order} LIMIT ? OFFSET ?",
        (*params, min(limit, 100), offset),
    )
    results = []
    for row in rows:
        repo = hub.repo_by_id(row["repo_id"])
        item = hub.repo_json(repo, viewer)
        if row["release_id"] is not None:
            release = hub.db.one("SELECT * FROM releases WHERE id = ?", (row["release_id"],))
            assert release is not None
            item["release"] = registry.release_json(hub, repo, release)
        results.append(item)
    used = {k: v for k, v in filters.items() if v not in (None, [])}
    return {"total": total, "filters": used, "text": text, "results": results}


# --- árbol genealógico --------------------------------------------------------------------------


def family(hub: Hub, repo: Repo, viewer: Account | None = None) -> dict[str, Any]:
    """La familia de forks de un repositorio (desde el original), su línea de ancestros y sus
    dependencias y dependientes del hub."""
    line = [repo]
    seen = {repo["id"]}
    while line[0]["parent"] is not None and line[0]["parent"] not in seen:
        parent = hub.repo_by_id(line[0]["parent"])
        seen.add(parent["id"])
        line.insert(0, parent)

    def node(r: Repo, depth: int) -> dict[str, Any]:
        latest = hub.db.one(
            "SELECT version, rules_hash FROM releases WHERE repo = ? AND yanked = 0"
            " ORDER BY major DESC, minor DESC, patch DESC LIMIT 1",
            (r["id"],),
        )
        children = hub.db.all("SELECT * FROM repos WHERE parent = ? ORDER BY created", (r["id"],))
        return {
            "repo": hub.full_name(r),
            "description": r["description"],
            "stars": r["stars"],
            "version": latest["version"] if latest else None,
            "rules_hash": latest["rules_hash"] if latest else None,
            "current": r["id"] == repo["id"],
            "children": [node(c, depth + 1) for c in children if hub.can_see(c, viewer)]
            if depth < 20
            else [],
        }

    deps: list[dict[str, Any]] = []
    latest = registry.releases(hub, repo, include_yanked=False)
    if latest:
        deps = registry.release_json(hub, repo, latest[0])["dependencies"]
    return {
        "root": node(line[0], 0),
        "ancestors": [hub.full_name(r) for r in line[:-1]],
        "dependencies": deps,
        "dependents": registry.dependents(hub, repo),
    }
