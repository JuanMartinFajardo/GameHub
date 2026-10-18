# SPDX-License-Identifier: AGPL-3.0-or-later
"""La cola de trabajos del hub: análisis de versiones, Balance CI de propuestas y arenas.

Un trabajo es una fila en `jobs` (estado `queued` → `running` → `done` o `failed`) con su entrada
en el almacén de objetos. Los ejecuta `JobRunner`: unos hilos que toman trabajos de la cola y
lanzan por cada uno un proceso hijo (`gamehub.hub.worker`) con límites del sistema operativo
(CPU, memoria, sin volcados de memoria) y un plazo de tiempo real; si se pasa, se le mata.

Los trabajos automáticos (el análisis de cada versión publicada, el balance de cada propuesta)
son del sistema; los que pide alguien cuentan para su cuota (`jobs_per_day`, `concurrent_jobs`).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any

from gamehub.bots.sandbox import Limits, _limiter
from gamehub.hub import registry
from gamehub.hub.service import Account, Hub, HubError, Repo, bad, not_found

KINDS = ("analyze", "balance", "balance_ci", "arena")
Job = dict[str, Any]

#: Opciones del balance automático de las propuestas (rápidas: es una señal, no un estudio).
PULL_BALANCE = {"games": 60, "ladder_games": 20, "kingmaking_games": 4}


def enqueue(
    hub: Hub,
    kind: str,
    payload: dict[str, Any],
    *,
    account: Account | None = None,
    repo: Repo | None = None,
    release: dict[str, Any] | None = None,
    pull: dict[str, Any] | None = None,
) -> int:
    if kind not in KINDS:
        raise bad(f"tipo de trabajo desconocido: {kind}")
    if account is not None:
        check_quota(hub, account)
    key = hub.blobs.put_json({"kind": kind, **payload})
    return hub.db.insert(
        "INSERT INTO jobs (kind, status, account, repo, release, pull, input, created)"
        " VALUES (?, 'queued', ?, ?, ?, ?, ?, ?)",
        (
            kind,
            account["id"] if account else None,
            repo["id"] if repo else None,
            release["id"] if release else None,
            pull["id"] if pull else None,
            key,
            hub.now(),
        ),
    )


def check_quota(hub: Hub, account: Account) -> None:
    q = hub.config.quotas
    today = hub.db.value(
        "SELECT count(*) AS n FROM jobs WHERE account = ? AND created > ?",
        (account["id"], hub.now() - 86400),
    )
    if today >= q.jobs_per_day:
        raise HubError(429, "quota", f"ya has lanzado {today} trabajos hoy (el máximo)")
    running = hub.db.value(
        "SELECT count(*) AS n FROM jobs WHERE account = ? AND status IN ('queued', 'running')",
        (account["id"],),
    )
    if running >= q.concurrent_jobs:
        raise HubError(429, "quota", f"tienes {running} trabajos pendientes: espera a que acaben")


def get(hub: Hub, job_id: int) -> Job:
    row = hub.db.one("SELECT * FROM jobs WHERE id = ?", (job_id,))
    if row is None:
        raise not_found("no existe ese trabajo")
    return row


def job_json(hub: Hub, row: Job, *, result: bool = True) -> dict[str, Any]:
    owner = hub.db.one("SELECT name FROM accounts WHERE id = ?", (row["account"],))
    out: dict[str, Any] = {
        "id": row["id"],
        "kind": row["kind"],
        "status": row["status"],
        "account": owner["name"] if owner else None,
        "error": row["error"],
        "seconds": row["seconds"],
        "created": row["created"],
        "started": row["started"],
        "finished": row["finished"],
        "position": None,
    }
    if row["repo"] is not None:
        out["repo"] = hub.full_name(hub.repo_by_id(row["repo"]))
    if row["release"] is not None:
        rel = hub.db.one("SELECT version FROM releases WHERE id = ?", (row["release"],))
        out["version"] = rel["version"] if rel else None
    if row["pull"] is not None:
        pull = hub.db.one("SELECT number FROM pulls WHERE id = ?", (row["pull"],))
        out["pull"] = pull["number"] if pull else None
    if row["status"] == "queued":
        out["position"] = hub.db.value(
            "SELECT count(*) AS n FROM jobs WHERE status = 'queued' AND id < ?", (row["id"],)
        )
    if result and row["result"]:
        out["result"] = json.loads(row["result"])
    return out


def listing(hub: Hub, *, repo: Repo | None = None, limit: int = 50) -> list[Job]:
    if repo is not None:
        return hub.db.all(
            "SELECT * FROM jobs WHERE repo = ? ORDER BY id DESC LIMIT ?", (repo["id"], limit)
        )
    return hub.db.all("SELECT * FROM jobs ORDER BY id DESC LIMIT ?", (limit,))


# --- trabajos automáticos -----------------------------------------------------------------------


def install(hub: Hub) -> None:
    """Engancha los trabajos automáticos a lo que pasa en el hub."""
    hub.on("published", lambda repo, release: _on_published(hub, repo, release))
    hub.on("pull_changed", lambda repo, pull: _on_pull(hub, repo, pull))
    hub.on("job_done", lambda job: _on_done(hub, job))


def _on_published(hub: Hub, repo: Repo, release: dict[str, Any]) -> None:
    if release["ir"]:
        ir = hub.blobs.get_json(release["ir"])
        enqueue(hub, "analyze", {"ir": ir}, repo=repo, release=release)


def _on_pull(hub: Hub, repo: Repo, pull: dict[str, Any]) -> None:
    old = registry.build(hub, repo, pull["base_commit"])
    new = registry.build(hub, repo, pull["head_commit"])
    if old.ir is None or new.ir is None:
        return
    if old.ir == new.ir:
        return
    job_id = enqueue(
        hub,
        "balance_ci",
        {"old": old.ir, "new": new.ir, "options": dict(PULL_BALANCE)},
        repo=repo,
        pull=pull,
    )
    hub.db.execute("UPDATE pulls SET balance_job = ? WHERE id = ?", (job_id, pull["id"]))


def _on_done(hub: Hub, job: Job) -> None:
    """El análisis de una versión rellena sus propiedades de búsqueda (ramificación, duración)."""
    if job["kind"] != "analyze" or job["status"] != "done" or job["release"] is None:
        return
    result = json.loads(job["result"])
    f = result.get("feasibility", {})
    row = hub.db.one("SELECT properties FROM releases WHERE id = ?", (job["release"],))
    if row is None:
        return
    properties = json.loads(row["properties"])
    depth = f.get("depth") or {}
    properties["analysis"] = {
        "tree_log10": f.get("tree_log10"),
        "leaves_log10": f.get("leaves_log10"),
        "branching": f.get("branching"),
        "depth_mean": depth.get("mean"),
        "depth_max": depth.get("max"),
        "exact": f.get("exact"),
    }
    properties["recommendations"] = f.get("recommendations", [])
    hub.db.execute(
        "UPDATE releases SET branching = ?, length = ?, properties = ? WHERE id = ?",
        (
            f.get("branching"),
            depth.get("mean"),
            json.dumps(properties, ensure_ascii=False),
            job["release"],
        ),
    )


# --- ejecutar -----------------------------------------------------------------------------------


def claim(hub: Hub) -> Job | None:
    """Toma el trabajo más antiguo de la cola (o None)."""
    with hub.db.transaction():
        row = hub.db.one("SELECT * FROM jobs WHERE status = 'queued' ORDER BY id LIMIT 1")
        if row is None:
            return None
        hub.db.execute(
            "UPDATE jobs SET status = 'running', started = ? WHERE id = ?", (hub.now(), row["id"])
        )
    return get(hub, row["id"])


def execute(hub: Hub, job: Job) -> Job:
    """Ejecuta un trabajo ya tomado en un proceso hijo con límites y guarda su resultado."""
    q = hub.config.quotas
    start = time.monotonic()
    payload = hub.blobs.get(job["input"])
    error: str | None = None
    result: Any = None
    with tempfile.TemporaryDirectory(dir=hub.tmp_dir) as home:
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": home,
            "LC_ALL": "C.UTF-8",
            "PYTHONHASHSEED": "0",
        }
        limits = Limits(cpu_seconds=q.job_cpu_seconds, memory_mb=q.job_memory_mb)
        try:
            done = subprocess.run(
                [sys.executable, "-m", "gamehub.hub.worker"],
                input=payload,
                capture_output=True,
                cwd=home,
                env=env,
                timeout=q.job_seconds,
                preexec_fn=_limiter(limits) if os.name == "posix" else None,
            )
        except subprocess.TimeoutExpired:
            error = f"se pasó del tiempo máximo ({q.job_seconds:g} s)"
        else:
            try:
                out = json.loads(done.stdout or b"{}")
            except ValueError:
                out = {}
            if out.get("ok"):
                result = out["result"]
            else:
                tail = done.stderr.decode("utf-8", "replace").strip().splitlines()[-3:]
                error = out.get("error") or (
                    f"el proceso terminó con el código {done.returncode}"
                    + (f": {' '.join(tail)}" if tail else "")
                )
    seconds = time.monotonic() - start
    hub.db.execute(
        "UPDATE jobs SET status = ?, result = ?, error = ?, seconds = ?, finished = ? WHERE id = ?",
        (
            "failed" if error else "done",
            json.dumps(result, ensure_ascii=False) if result is not None else None,
            error,
            seconds,
            hub.now(),
            job["id"],
        ),
    )
    row = get(hub, job["id"])
    hub.emit("job_done", row)
    return row


def run_pending(hub: Hub, limit: int | None = None) -> int:
    """Ejecuta trabajos de la cola en este hilo hasta vaciarla (para tests y `hub jobs run`)."""
    count = 0
    while limit is None or count < limit:
        job = claim(hub)
        if job is None:
            break
        execute(hub, job)
        count += 1
    return count


class JobRunner:
    """Hilos que vacían la cola mientras el hub está en marcha."""

    def __init__(self, hub: Hub, workers: int, poll: float = 0.5) -> None:
        self.hub = hub
        self.workers = workers
        self.poll = poll
        self.stop = threading.Event()
        self.threads: list[threading.Thread] = []

    def start(self) -> None:
        # Lo que quedó a medias si el hub se paró: vuelve a la cola.
        self.hub.db.execute("UPDATE jobs SET status = 'queued' WHERE status = 'running'")
        for k in range(self.workers):
            t = threading.Thread(target=self._loop, name=f"hub-jobs-{k}", daemon=True)
            t.start()
            self.threads.append(t)

    def _loop(self) -> None:
        while not self.stop.is_set():
            try:
                job = claim(self.hub)
            except Exception:
                job = None
            if job is None:
                self.stop.wait(self.poll)
                continue
            try:
                execute(self.hub, job)
            except Exception as exc:  # que un fallo del hub no pare los hilos
                self.hub.db.execute(
                    "UPDATE jobs SET status = 'failed', error = ?, finished = ? WHERE id = ?",
                    (f"error del hub: {exc}", self.hub.now(), job["id"]),
                )

    def close(self) -> None:
        self.stop.set()
        for t in self.threads:
            t.join(timeout=2)
