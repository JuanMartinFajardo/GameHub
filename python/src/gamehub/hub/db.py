# SPDX-License-Identifier: AGPL-3.0-or-later
"""La base de datos del hub: SQLite (por defecto, sin configurar nada) o PostgreSQL.

El SQL se escribe una vez, con `?` como marcador y en el subconjunto común a los dos (`RETURNING`
incluido); `{id}` y `{real}` en las tablas se traducen al tipo de cada uno. Una sola conexión
protegida por un cerrojo: las consultas del hub son cortas y lo lento (compilar, git, trabajos)
va fuera de ellas.

    db = Database.open("sqlite:///ruta/hub.db")     # o "postgresql://usuario@host/base"
    with db.transaction():
        uid = db.insert("INSERT INTO accounts (name, …) VALUES (?, …)", (name, …))
    row = db.one("SELECT * FROM accounts WHERE name = ?", (name,))   # dict o None
"""

from __future__ import annotations

import contextlib
import re
import sqlite3
import threading
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

Row = dict[str, Any]

SCHEMA: list[str] = [
    # --- 1: cuentas, repositorios, versiones, propuestas, trabajos, partidas, moderación --------
    """
    CREATE TABLE accounts (
      id {id},
      name TEXT NOT NULL UNIQUE,
      kind TEXT NOT NULL,                 -- user | org
      display TEXT NOT NULL DEFAULT '',
      email TEXT,
      password TEXT,                      -- scrypt; NULL si solo entra con OAuth
      admin INTEGER NOT NULL DEFAULT 0,
      suspended INTEGER NOT NULL DEFAULT 0,
      terms TEXT,                         -- versión de las condiciones de uso aceptada
      bio TEXT NOT NULL DEFAULT '',
      created {real} NOT NULL
    );
    CREATE TABLE members (
      org INTEGER NOT NULL REFERENCES accounts(id),
      account INTEGER NOT NULL REFERENCES accounts(id),
      role TEXT NOT NULL,                 -- owner | member
      PRIMARY KEY (org, account)
    );
    CREATE TABLE identities (
      provider TEXT NOT NULL,
      subject TEXT NOT NULL,
      account INTEGER NOT NULL REFERENCES accounts(id),
      PRIMARY KEY (provider, subject)
    );
    CREATE TABLE sessions (
      hash TEXT PRIMARY KEY,
      account INTEGER NOT NULL REFERENCES accounts(id),
      created {real} NOT NULL,
      expires {real} NOT NULL
    );
    CREATE TABLE tokens (
      id {id},
      account INTEGER NOT NULL REFERENCES accounts(id),
      name TEXT NOT NULL,
      hash TEXT NOT NULL UNIQUE,
      created {real} NOT NULL,
      used {real}
    );
    CREATE TABLE repos (
      id {id},
      owner INTEGER NOT NULL REFERENCES accounts(id),
      name TEXT NOT NULL,
      kind TEXT NOT NULL,                 -- game | library
      description TEXT NOT NULL DEFAULT '',
      parent INTEGER REFERENCES repos(id),
      default_branch TEXT NOT NULL DEFAULT 'main',
      hidden INTEGER NOT NULL DEFAULT 0,
      stars INTEGER NOT NULL DEFAULT 0,
      size INTEGER NOT NULL DEFAULT 0,
      created {real} NOT NULL,
      updated {real} NOT NULL,
      UNIQUE (owner, name)
    );
    CREATE TABLE stars (
      account INTEGER NOT NULL REFERENCES accounts(id),
      repo INTEGER NOT NULL REFERENCES repos(id),
      PRIMARY KEY (account, repo)
    );
    CREATE TABLE releases (
      id {id},
      repo INTEGER NOT NULL REFERENCES repos(id),
      version TEXT NOT NULL,
      major INTEGER NOT NULL,
      minor INTEGER NOT NULL,
      patch INTEGER NOT NULL,
      pre TEXT NOT NULL DEFAULT '',
      commit_id TEXT NOT NULL,
      level TEXT,                         -- major | minor | patch respecto a la anterior
      game TEXT,                          -- id del juego principal (NULL en una librería)
      title TEXT NOT NULL DEFAULT '',
      rules_hash TEXT,
      interface_hash TEXT,
      ir TEXT,                            -- clave de la IR en el almacén de objetos
      manifest TEXT NOT NULL,             -- game.toml como JSON
      properties TEXT NOT NULL,           -- clasificación y medidas (JSON)
      tags TEXT NOT NULL DEFAULT '',      -- ",tag1,tag2,"
      min_players INTEGER,
      max_players INTEGER,
      chance INTEGER,
      perfect_information INTEGER,
      simultaneous INTEGER,
      zero_sum INTEGER,
      branching {real},
      length {real},
      notes TEXT NOT NULL DEFAULT '',
      publisher INTEGER REFERENCES accounts(id),
      yanked INTEGER NOT NULL DEFAULT 0,
      created {real} NOT NULL,
      UNIQUE (repo, version)
    );
    CREATE TABLE dependencies (
      release INTEGER NOT NULL REFERENCES releases(id),
      repo INTEGER NOT NULL REFERENCES repos(id),
      requirement TEXT NOT NULL,
      PRIMARY KEY (release, repo)
    );
    CREATE TABLE pulls (
      id {id},
      repo INTEGER NOT NULL REFERENCES repos(id),
      number INTEGER NOT NULL,
      base TEXT NOT NULL,
      source INTEGER NOT NULL REFERENCES repos(id),
      head TEXT NOT NULL,
      title TEXT NOT NULL,
      body TEXT NOT NULL DEFAULT '',
      author INTEGER NOT NULL REFERENCES accounts(id),
      state TEXT NOT NULL,                -- open | merged | closed
      head_commit TEXT NOT NULL,
      base_commit TEXT NOT NULL,
      merge_commit TEXT,
      balance_job INTEGER,
      created {real} NOT NULL,
      updated {real} NOT NULL,
      UNIQUE (repo, number)
    );
    CREATE TABLE comments (
      id {id},
      pull INTEGER NOT NULL REFERENCES pulls(id),
      author INTEGER NOT NULL REFERENCES accounts(id),
      body TEXT NOT NULL,
      created {real} NOT NULL
    );
    CREATE TABLE jobs (
      id {id},
      kind TEXT NOT NULL,                 -- analyze | balance | arena
      status TEXT NOT NULL,               -- queued | running | done | failed
      account INTEGER REFERENCES accounts(id),
      repo INTEGER REFERENCES repos(id),
      release INTEGER REFERENCES releases(id),
      pull INTEGER REFERENCES pulls(id),
      input TEXT NOT NULL,                -- clave del almacén de objetos
      result TEXT,                        -- JSON
      error TEXT,
      seconds {real},
      created {real} NOT NULL,
      started {real},
      finished {real}
    );
    CREATE TABLE matches (
      id TEXT PRIMARY KEY,
      rules_hash TEXT NOT NULL,
      game TEXT NOT NULL,                 -- dueño/nombre@versión
      room TEXT NOT NULL,
      players TEXT NOT NULL,              -- JSON: [{name, kind, account}]
      result TEXT NOT NULL,               -- JSON: {payoffs, ranking, outcome}
      rated INTEGER NOT NULL,
      humans_only INTEGER NOT NULL,
      created {real} NOT NULL
    );
    CREATE TABLE ratings (
      rules_hash TEXT NOT NULL,
      account INTEGER NOT NULL REFERENCES accounts(id),
      elo {real} NOT NULL,
      glicko {real} NOT NULL,
      glicko_rd {real} NOT NULL,
      trueskill {real} NOT NULL,
      games INTEGER NOT NULL,
      PRIMARY KEY (rules_hash, account)
    );
    CREATE TABLE pages (
      id {id},
      repo INTEGER NOT NULL REFERENCES repos(id),
      name TEXT NOT NULL,
      interface_hash TEXT NOT NULL,
      archive TEXT NOT NULL,              -- clave del .tar.gz en el almacén de objetos
      files INTEGER NOT NULL,
      size INTEGER NOT NULL,
      publisher INTEGER REFERENCES accounts(id),
      created {real} NOT NULL,
      UNIQUE (repo, name)
    );
    CREATE TABLE reports (
      id {id},
      reporter INTEGER REFERENCES accounts(id),
      target TEXT NOT NULL,               -- repo:ID | account:ID | pull:ID
      reason TEXT NOT NULL,
      status TEXT NOT NULL,               -- open | resolved | dismissed
      resolution TEXT NOT NULL DEFAULT '',
      resolver INTEGER REFERENCES accounts(id),
      created {real} NOT NULL
    );
    CREATE TABLE events (
      id {id},
      repo INTEGER REFERENCES repos(id),
      account INTEGER REFERENCES accounts(id),
      kind TEXT NOT NULL,
      data TEXT NOT NULL,
      created {real} NOT NULL
    );
    CREATE INDEX releases_repo ON releases (repo);
    CREATE INDEX releases_rules ON releases (rules_hash);
    CREATE INDEX repos_parent ON repos (parent);
    CREATE INDEX jobs_status ON jobs (status, created);
    CREATE INDEX matches_rules ON matches (rules_hash);
    CREATE INDEX events_repo ON events (repo, created);
    """,
]


class DatabaseError(Exception):
    """La base de datos no está disponible o una URL no se entiende."""


class Database:
    def __init__(self, conn: Any, dialect: str) -> None:
        self.conn = conn
        self.dialect = dialect  # sqlite | postgresql
        self.lock = threading.RLock()
        self._depth = 0

    @classmethod
    def open(cls, url: str) -> Database:
        if url.startswith("sqlite://"):
            path = url.removeprefix("sqlite://")
            target = ":memory:" if path in ("", ":memory:", "/:memory:") else path
            if target != ":memory:":
                Path(target).parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(target, check_same_thread=False, isolation_level=None)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            if target != ":memory:":
                conn.execute("PRAGMA journal_mode = WAL")
            db = cls(conn, "sqlite")
        elif url.startswith(("postgresql://", "postgres://")):
            try:
                import psycopg
                from psycopg.rows import dict_row
            except ImportError:
                raise DatabaseError(
                    "PostgreSQL necesita psycopg: instala el extra `gamehub[hub-postgres]`"
                ) from None
            try:
                conn = psycopg.connect(
                    url,
                    autocommit=True,
                    row_factory=dict_row,  # pyright: ignore[reportArgumentType]
                )
            except Exception as exc:
                raise DatabaseError(f"no se puede conectar a PostgreSQL: {exc}") from None
            db = cls(conn, "postgresql")
        else:
            raise DatabaseError(
                f"URL de base de datos no válida: {url} (sqlite:// o postgresql://)"
            )
        db.migrate()
        return db

    # --- SQL ------------------------------------------------------------------------------------

    def _sql(self, sql: str) -> str:
        if self.dialect == "postgresql":
            return re.sub(r"\?", "%s", sql)
        return sql

    def execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        """Ejecuta y devuelve las filas afectadas."""
        with self.lock:
            cur = self.conn.execute(self._sql(sql), tuple(params))
            return cur.rowcount

    def all(self, sql: str, params: Sequence[Any] = ()) -> list[Row]:
        with self.lock:
            cur = self.conn.execute(self._sql(sql), tuple(params))
            return [dict(r) for r in cur.fetchall()]

    def one(self, sql: str, params: Sequence[Any] = ()) -> Row | None:
        rows = self.all(sql, params)
        return rows[0] if rows else None

    def value(self, sql: str, params: Sequence[Any] = ()) -> Any:
        row = self.one(sql, params)
        return next(iter(row.values())) if row else None

    def insert(self, sql: str, params: Sequence[Any] = ()) -> int:
        """Un `INSERT` que devuelve el id de la fila nueva."""
        row = self.one(sql + " RETURNING id", params)
        assert row is not None
        return int(row["id"])

    @contextlib.contextmanager
    def transaction(self) -> Iterator[None]:
        """Un bloque atómico (anidable: solo el más externo confirma)."""
        with self.lock:
            outer = self._depth == 0
            if outer:
                self.conn.execute("BEGIN IMMEDIATE" if self.dialect == "sqlite" else "BEGIN")
            self._depth += 1
            try:
                yield
            except BaseException:
                self._depth -= 1
                if outer:
                    self.conn.execute("ROLLBACK")
                raise
            self._depth -= 1
            if outer:
                self.conn.execute("COMMIT")

    # --- esquema --------------------------------------------------------------------------------

    def ddl(self, script: str) -> list[str]:
        if self.dialect == "sqlite":
            types = {"id": "INTEGER PRIMARY KEY AUTOINCREMENT", "real": "REAL"}
        else:
            types = {
                "id": "BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY",
                "real": "DOUBLE PRECISION",
            }
        text = re.sub(r"--[^\n]*", "", script).format(**types)
        return [s.strip() for s in text.split(";") if s.strip()]

    def migrate(self) -> None:
        with self.lock:
            self.conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)"
            )
            current = self.value("SELECT max(version) AS v FROM schema_version") or 0
            for number, script in enumerate(SCHEMA, start=1):
                if number <= current:
                    continue
                with self.transaction():
                    for statement in self.ddl(script):
                        self.conn.execute(statement)
                    self.execute("INSERT INTO schema_version (version) VALUES (?)", (number,))

    def close(self) -> None:
        with self.lock:
            self.conn.close()
