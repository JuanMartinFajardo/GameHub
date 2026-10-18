# SPDX-License-Identifier: AGPL-3.0-or-later
"""Propuestas de cambio (PRs): una rama de un fork (o del mismo repositorio) que se propone
fusionar en una rama del repositorio original.

Al abrirla, el hub trae la rama al repositorio de destino (`refs/pull/N/head`) y desde entonces la
revisa en cuatro capas (ADR-094):

1. **Texto**: el diff de git desde la base común.
2. **Semántica**: el diff de la IR de los dos lados (`gamehub.render.diff`), los cambios de
   interfaz y el nivel de semver que exigiría publicarla.
3. **Visual**: el modelo del diagrama de cada lado; la web pinta lo añadido, quitado y cambiado.
4. **Comportamiento** (Balance CI): un trabajo que juega las dos versiones con los mismos bots y
   semillas y compara las métricas (`gamehub.bots.balance.compare`).

Si la rama del fork avanza, la propuesta se actualiza al verla (y se vuelve a medir el balance).
Fusionar es avance rápido si se puede y, si no, un commit de fusión; un conflicto se resuelve en
el fork (fusionando la rama de destino en él) y se vuelve a intentar.
"""

from __future__ import annotations

from typing import Any

from gamehub.hub import registry
from gamehub.hub.gitrepo import GitError
from gamehub.hub.service import Account, Hub, HubError, Repo, bad, forbidden, not_found
from gamehub.ir.hashing import rules_hash
from gamehub.ir.interface import change_level, compare

Pull = dict[str, Any]


def network_root(hub: Hub, repo: Repo) -> int:
    """El repositorio original de una familia de forks."""
    seen = {repo["id"]}
    while repo["parent"] is not None and repo["parent"] not in seen:
        seen.add(repo["parent"])
        repo = hub.repo_by_id(repo["parent"])
    return int(repo["id"])


def create(
    hub: Hub,
    target: Repo,
    by: Account,
    *,
    source: Repo,
    head: str,
    base: str | None = None,
    title: str,
    body: str = "",
) -> Pull:
    if not hub.can_write(source, by):
        raise forbidden("solo puedes proponer ramas de repositorios en los que escribes")
    if source["id"] != target["id"] and network_root(hub, source) != network_root(hub, target):
        raise bad("solo se proponen cambios entre repositorios de la misma familia de forks")
    if not title.strip():
        raise bad("la propuesta necesita un título")
    base = base or target["default_branch"]
    target_git, source_git = hub.git(target), hub.git(source)
    base_tip = target_git.resolve(f"refs/heads/{base}")
    if base_tip is None:
        raise not_found(f"{hub.full_name(target)} no tiene la rama {base}")
    if source_git.resolve(f"refs/heads/{head}") is None:
        raise not_found(f"{hub.full_name(source)} no tiene la rama {head}")
    if source["id"] == target["id"] and head == base:
        raise bad("la rama propuesta y la de destino son la misma")
    with hub.db.transaction():
        number = (
            hub.db.value("SELECT max(number) AS n FROM pulls WHERE repo = ?", (target["id"],)) or 0
        ) + 1
        ref = f"refs/pull/{number}/head"
        head_commit = target_git.fetch(source_git, f"refs/heads/{head}", ref)
        if target_git.is_ancestor(head_commit, base_tip):
            target_git.delete_ref(ref)
            raise bad(f"{base} ya contiene todo lo de {head}: no hay nada que proponer")
        base_commit = target_git.merge_base(base_tip, head_commit) or base_tip
        now = hub.now()
        pull_id = hub.db.insert(
            "INSERT INTO pulls (repo, number, base, source, head, title, body, author, state,"
            " head_commit, base_commit, created, updated)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?)",
            (
                target["id"],
                number,
                base,
                source["id"],
                head,
                title.strip()[:200],
                body[:20000],
                by["id"],
                head_commit,
                base_commit,
                now,
                now,
            ),
        )
    pull = get_by_id(hub, pull_id)
    hub.event(target, by, "pull_opened", {"number": number, "title": pull["title"]})
    hub.emit("pull_changed", target, pull)
    return get_by_id(hub, pull_id)


def get_by_id(hub: Hub, pull_id: int) -> Pull:
    row = hub.db.one("SELECT * FROM pulls WHERE id = ?", (pull_id,))
    if row is None:
        raise not_found("no existe esa propuesta")
    return row


def get(hub: Hub, repo: Repo, number: int) -> Pull:
    row = hub.db.one("SELECT * FROM pulls WHERE repo = ? AND number = ?", (repo["id"], number))
    if row is None:
        raise not_found(f"{hub.full_name(repo)} no tiene la propuesta #{number}")
    return row


def refresh(hub: Hub, pull: Pull) -> Pull:
    """Si la rama propuesta avanzó, la vuelve a traer (y se vuelve a medir el balance)."""
    if pull["state"] != "open":
        return pull
    target, source = hub.repo_by_id(pull["repo"]), hub.repo_by_id(pull["source"])
    target_git, source_git = hub.git(target), hub.git(source)
    tip = source_git.resolve(f"refs/heads/{pull['head']}")
    base_tip = target_git.resolve(f"refs/heads/{pull['base']}")
    if tip is None or base_tip is None:
        return pull
    if tip == pull["head_commit"] and target_git.is_ancestor(pull["base_commit"], base_tip):
        return pull
    head_commit = target_git.fetch(source_git, f"refs/heads/{pull['head']}", _ref(pull))
    base_commit = target_git.merge_base(base_tip, head_commit) or base_tip
    if head_commit == pull["head_commit"] and base_commit == pull["base_commit"]:
        return pull
    hub.db.execute(
        "UPDATE pulls SET head_commit = ?, base_commit = ?, updated = ? WHERE id = ?",
        (head_commit, base_commit, hub.now(), pull["id"]),
    )
    pull = get_by_id(hub, pull["id"])
    hub.emit("pull_changed", target, pull)
    return pull


def _ref(pull: Pull) -> str:
    return f"refs/pull/{pull['number']}/head"


def listing(hub: Hub, repo: Repo, state: str | None = "open") -> list[Pull]:
    if state in (None, "all"):
        return hub.db.all("SELECT * FROM pulls WHERE repo = ? ORDER BY number DESC", (repo["id"],))
    return hub.db.all(
        "SELECT * FROM pulls WHERE repo = ? AND state = ? ORDER BY number DESC",
        (repo["id"], state),
    )


def pull_json(hub: Hub, pull: Pull, viewer: Account | None = None) -> dict[str, Any]:
    target, source = hub.repo_by_id(pull["repo"]), hub.repo_by_id(pull["source"])
    author = hub.account_by_id(pull["author"])
    comments = hub.db.all(
        "SELECT c.body, c.created, a.name AS author FROM comments c"
        " JOIN accounts a ON a.id = c.author WHERE c.pull = ? ORDER BY c.id",
        (pull["id"],),
    )
    mergeable = None
    if pull["state"] == "open":
        git = hub.git(target)
        tip = git.resolve(f"refs/heads/{pull['base']}")
        if tip is not None:
            mergeable = git.is_ancestor(tip, pull["head_commit"]) or _merges_cleanly(
                hub, target, tip, pull["head_commit"]
            )
    return {
        "number": pull["number"],
        "repo": hub.full_name(target),
        "source": hub.full_name(source),
        "head": pull["head"],
        "base": pull["base"],
        "title": pull["title"],
        "body": pull["body"],
        "author": author["name"],
        "state": pull["state"],
        "head_commit": pull["head_commit"],
        "base_commit": pull["base_commit"],
        "merge_commit": pull["merge_commit"],
        "mergeable": mergeable,
        "balance_job": pull["balance_job"],
        "comments": comments,
        "created": pull["created"],
        "updated": pull["updated"],
        "can_merge": pull["state"] == "open" and hub.can_write(target, viewer),
        "can_close": pull["state"] == "open"
        and viewer is not None
        and (viewer["id"] == pull["author"] or hub.can_write(target, viewer)),
    }


def _merges_cleanly(hub: Hub, repo: Repo, tip: str, head: str) -> bool:
    done = hub.git(repo).git("merge-tree", "--write-tree", "--name-only", tip, head, check=False)
    return done.returncode == 0


# --- las cuatro capas ---------------------------------------------------------------------------


def diffs(hub: Hub, pull: Pull) -> dict[str, Any]:
    """Texto, semántica e interfaz, y los modelos para el diff visual (el balance va aparte:
    es un trabajo)."""
    target = hub.repo_by_id(pull["repo"])
    git = hub.git(target)
    patch, stats = git.diff(pull["base_commit"], pull["head_commit"])
    old = registry.build(hub, target, pull["base_commit"], model=True)
    new = registry.build(hub, target, pull["head_commit"], model=True)
    out: dict[str, Any] = {
        "text": {"patch": patch[:2_000_000], "files": stats, "truncated": len(patch) > 2_000_000},
        "base_problems": old.problems,
        "head_problems": new.problems,
        "semantic": None,
        "visual": {"base": old.model, "head": new.model},
    }
    if old.ir is not None and new.ir is not None:
        from gamehub.render.diff import diff as semantic_diff

        result = semantic_diff(old.ir, new.ir)
        out["semantic"] = {
            "same_rules": result.same_rules,
            "old_hash": result.old_hash,
            "new_hash": result.new_hash,
            "changes": [c.to_json() for c in result.changes],
            "interface": [c.to_json() for c in compare(old.ir, new.ir)],
            "level": change_level(old.ir, new.ir),
        }
    elif new.ir is not None:
        out["semantic"] = {"new_hash": rules_hash(new.ir), "changes": [], "interface": []}
    return out


# --- fusionar, cerrar, comentar -----------------------------------------------------------------


def merge(hub: Hub, pull: Pull, by: Account, message: str | None = None) -> Pull:
    target = hub.repo_by_id(pull["repo"])
    if not hub.can_write(target, by):
        raise forbidden("solo quien escribe en el repositorio puede fusionar propuestas")
    if pull["state"] != "open":
        raise HubError(409, "closed", "la propuesta ya no está abierta")
    pull = refresh(hub, pull)
    head_built = registry.build(hub, target, pull["head_commit"])
    text = message or f"Fusiona la propuesta #{pull['number']}: {pull['title']}"
    try:
        commit = hub.git(target).merge(pull["base"], pull["head_commit"], text, hub.author(by))
    except GitError as exc:
        raise HubError(
            409 if exc.conflict else 400, "conflict" if exc.conflict else "git", str(exc)
        ) from None
    hub.db.execute(
        "UPDATE pulls SET state = 'merged', merge_commit = ?, updated = ? WHERE id = ?",
        (commit, hub.now(), pull["id"]),
    )
    hub._refresh_size(target)
    hub.event(
        target,
        by,
        "pull_merged",
        {"number": pull["number"], "commit": commit, "compiles": head_built.ok},
    )
    return get_by_id(hub, pull["id"])


def close(hub: Hub, pull: Pull, by: Account) -> Pull:
    target = hub.repo_by_id(pull["repo"])
    if pull["state"] != "open":
        raise HubError(409, "closed", "la propuesta ya no está abierta")
    if by["id"] != pull["author"] and not hub.can_write(target, by):
        raise forbidden("solo su autor o quien escribe en el repositorio puede cerrarla")
    hub.db.execute(
        "UPDATE pulls SET state = 'closed', updated = ? WHERE id = ?", (hub.now(), pull["id"])
    )
    hub.event(target, by, "pull_closed", {"number": pull["number"]})
    return get_by_id(hub, pull["id"])


def comment(hub: Hub, pull: Pull, by: Account, body: str) -> None:
    if not body.strip():
        raise bad("el comentario está vacío")
    hub.db.execute(
        "INSERT INTO comments (pull, author, body, created) VALUES (?, ?, ?, ?)",
        (pull["id"], by["id"], body.strip()[:20000], hub.now()),
    )
    hub.db.execute("UPDATE pulls SET updated = ? WHERE id = ?", (hub.now(), pull["id"]))
