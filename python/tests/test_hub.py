# SPDX-License-Identifier: AGPL-3.0-or-later
"""El hub (fase 10): semver e interfaz, dependencias del hub, el servicio, git por HTTP, la CLI,
propuestas con sus diffs, el juego en línea con valoraciones, Pages, OAuth y moderación; y la
aceptación de la fase: A publica, B hace un fork, crea una variante y la propone, A la fusiona y
cualquiera juega la versión nueva en línea."""

from __future__ import annotations

import asyncio
import base64
import copy
import io
import json
import os
import re
import subprocess
import tarfile
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from gamehub.cli import main
from gamehub.client import AgentRunner, Client, load_agent
from gamehub.engine import Game
from gamehub.hub import explore
from gamehub.hub.config import HubConfig, OAuthProvider, Quotas
from gamehub.hub.db import Database
from gamehub.hub.service import Hub, HubError
from gamehub.ir.interface import change_level, compare, interface, interface_hash
from gamehub.lang.compiler import load_nomos
from gamehub.packages import PackageError, load_lock, load_manifest, save_lock
from gamehub.semver import Requirement, Version, VersionError, allowed
from hub_harness import ROOT, ApiError, HubThread, User, package_files


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Credenciales de la CLI y caché de git propias de cada test."""
    monkeypatch.setenv("GAMEHUB_CONFIG", str(tmp_path / "config"))
    monkeypatch.setenv("GAMEHUB_CACHE", str(tmp_path / "cache"))
    monkeypatch.delenv("GAMEHUB_HUB", raising=False)
    for key in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        monkeypatch.setenv(key, "Tests")
    for key in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        monkeypatch.setenv(key, "tests@example.invalid")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


@pytest.fixture
def hub(tmp_path: Path) -> Iterator[HubThread]:
    with HubThread(tmp_path / "hub") as running:
        yield running


def nim_text() -> str:
    return (ROOT / "games" / "nim" / "nim.game").read_text(encoding="utf-8")


# --- semver -------------------------------------------------------------------------------------


def test_semver_order_and_requirements() -> None:
    order = ["1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta", "1.0.0-beta", "1.0.0-beta.2"]
    order += ["1.0.0-beta.11", "1.0.0-rc.1", "1.0.0", "1.0.1", "1.1.0", "2.0.0"]
    shuffled = sorted(order, key=lambda v: v[::-1])
    assert [str(v) for v in sorted(map(Version.parse, shuffled), key=Version.key)] == order
    cases = {
        "^1.2.3": (["1.2.3", "1.9.0"], ["2.0.0", "1.2.2", "1.5.0-beta"]),
        "^0.2.3": (["0.2.9"], ["0.3.0"]),
        "^0.0.3": (["0.0.3"], ["0.0.4"]),
        "~1.2": (["1.2.0", "1.2.9"], ["1.3.0"]),
        ">=0.3, <0.4": (["0.3.5"], ["0.4.0", "0.2.9"]),
        "1.*": (["1.0.0", "1.99.0"], ["2.0.0"]),
        "*": (["0.0.1", "9.0.0"], ["1.0.0-alpha"]),
        ">=1.0.0-beta": (["1.0.0-beta.2", "1.0.0"], ["1.0.1-beta"]),
        "=1.2": (["1.2.5"], ["1.3.0"]),
        "1.2.3": (["1.4.0"], ["2.0.0"]),
    }
    for text, (yes, no) in cases.items():
        req = Requirement.parse(text)
        assert all(req.matches(Version.parse(v)) for v in yes), text
        assert not any(req.matches(Version.parse(v)) for v in no), text
    assert (
        str(Requirement.parse("^1").best([Version.parse(v) for v in ("1.0.0", "1.4.2", "2.0.0")]))
        == "1.4.2"
    )
    for bad_text in ("", "1.2.3.4", "^x", ">=1.*", "1.2.3,"):
        with pytest.raises(VersionError):
            Requirement.parse(bad_text)
    with pytest.raises(VersionError):
        Version.parse("01.2.3")


def test_semver_bumps_follow_cargo_for_zero_versions() -> None:
    v = Version.parse
    assert str(v("1.2.3").bump("major")) == "2.0.0"
    assert str(v("1.2.3").bump("minor")) == "1.3.0"
    assert str(v("0.2.3").bump("major")) == "0.3.0"
    assert str(v("0.2.3").bump("minor")) == "0.2.4"
    assert allowed(v("1.2.3"), v("2.0.0"), "major")
    assert not allowed(v("1.2.3"), v("1.9.0"), "major")
    assert not allowed(v("1.2.3"), v("1.2.4"), "minor")
    assert allowed(v("0.2.3"), v("0.2.4"), "minor")
    assert not allowed(v("0.2.3"), v("0.2.4"), "major")
    assert allowed(v("1.0.0-beta"), v("1.0.0"), "major")
    assert not allowed(v("1.2.3"), v("1.2.3"), "patch")


# --- interfaz -----------------------------------------------------------------------------------


def test_interface_hash_and_change_levels() -> None:
    ir = load_nomos(ROOT / "games" / "connect-four" / "connect-four.game").ir
    face = interface(ir)
    assert set(face) == {"params", "view", "actions", "events", "types"}
    assert face["actions"] == {"drop": [[{"name": "c", "type": "Int", "visibility": "all"}]]}
    assert list(face["types"]) == ["Disc"]

    cosmetic = copy.deepcopy(ir)
    cosmetic["meta"]["title"] = {"en": "Four in a row"}
    cosmetic["heuristics"] = []
    assert interface_hash(cosmetic) == interface_hash(ir)
    assert change_level(ir, cosmetic) == "patch"
    assert change_level(ir, copy.deepcopy(ir)) is None

    rules = copy.deepcopy(ir)
    rules["params"][2]["default"] = ["const", 5]
    assert compare(ir, rules) == [] and change_level(ir, rules) == "minor"

    wider = copy.deepcopy(ir)
    wider["types"][0]["values"].append("Green")
    assert [str(c) for c in compare(ir, wider)] == ["~ types.Disc (incompatible)"]
    assert change_level(ir, wider) == "major"

    more = copy.deepcopy(ir)
    more["state"].append({"name": "moves", "type": "Int", "init": ["const", 0]})
    assert [c.to_json() for c in compare(ir, more)] == [
        {"op": "+", "path": "view.moves", "breaking": False}
    ]
    assert change_level(ir, more) == "minor"
    hidden = copy.deepcopy(ir)
    hidden["state"][1]["visibility"] = "none"
    hidden["state"][1]["size_visibility"] = "none"
    assert change_level(ir, hidden) == "major"


def test_every_catalog_game_has_an_interface() -> None:
    hashes = set()
    for path in sorted((ROOT / "games").glob("*/*.game")):
        if path.parent.name == "iterated-pd" and path.name == "tests.game":
            continue
        g = load_nomos(path)
        assert interface(g.ir)["actions"], path
        hashes.add(interface_hash(g.ir))
    assert len(hashes) >= 15  # juegos distintos, interfaces distintas


# --- dependencias del hub en game.toml ----------------------------------------------------------


def test_hub_dependencies_in_manifest_and_lock(tmp_path: Path) -> None:
    (tmp_path / "game.toml").write_text(
        '[game]\nname = "mi-wizard"\n\n[dependencies]\n"juanma/bazas" = "^1.2"\n'
        'pujas = { hub = "juanma/pujas", version = "~0.3", registry = "http://h:7430" }\n'
        'local = { path = "../local" }\n',
        encoding="utf-8",
    )
    m = load_manifest(tmp_path)
    assert m.dependencies["bazas"].hub == "juanma/bazas"
    assert m.dependencies["bazas"].version == "^1.2"
    assert m.dependencies["pujas"].registry == "http://h:7430"
    from gamehub.packages import Locked, manifest_toml

    again = tmp_path / "again"
    again.mkdir()
    (again / "game.toml").write_text(manifest_toml(m), encoding="utf-8")
    assert load_manifest(again).dependencies == m.dependencies
    save_lock(
        tmp_path,
        {
            "bazas": Locked(
                "bazas", "http://h/juanma/bazas.git", "v1.4.0", "a" * 40, "1.4.0", "juanma/bazas"
            )
        },
    )
    assert load_lock(tmp_path)["bazas"].version == "1.4.0"
    for bad_dep in (
        'bazas = "^1.2"',
        'x = { hub = "sin-barra" }',
        'x = { hub = "a/b", version = "^x" }',
    ):
        (tmp_path / "game.toml").write_text(f'[game]\nname = "g"\n\n[dependencies]\n{bad_dep}\n')
        with pytest.raises(PackageError):
            load_manifest(tmp_path)


# --- base de datos y servicio -------------------------------------------------------------------


def test_database_migrations_are_idempotent(tmp_path: Path) -> None:
    url = f"sqlite://{tmp_path / 'hub.db'}"
    db = Database.open(url)
    db.execute("INSERT INTO accounts (name, kind, created) VALUES (?, ?, ?)", ("ana", "user", 1.0))
    db.close()
    db = Database.open(url)
    assert db.value("SELECT count(*) AS n FROM accounts") == 1
    assert db.value("SELECT max(version) AS v FROM schema_version") == 1
    with pytest.raises(ValueError), db.transaction():
        db.execute(
            "INSERT INTO accounts (name, kind, created) VALUES (?, ?, ?)", ("beto", "user", 1.0)
        )
        raise ValueError("deshacer")
    assert db.value("SELECT count(*) AS n FROM accounts") == 1
    db.close()


@pytest.mark.skipif(not os.environ.get("GAMEHUB_TEST_POSTGRES"), reason="sin PostgreSQL de pruebas")
def test_postgresql_backend() -> None:
    db = Database.open(os.environ["GAMEHUB_TEST_POSTGRES"])
    try:
        for table in ("comments", "dependencies", "stars", "members", "identities", "sessions"):
            db.execute(f"DELETE FROM {table}")
        account = db.insert(
            "INSERT INTO accounts (name, kind, created) VALUES (?, ?, ?)", ("pg-ana", "user", 1.5)
        )
        assert db.one("SELECT name, created FROM accounts WHERE id = ?", (account,)) == {
            "name": "pg-ana",
            "created": 1.5,
        }
    finally:
        db.execute("DELETE FROM accounts WHERE name = 'pg-ana'")
        db.close()


def test_service_accounts_orgs_and_permissions(tmp_path: Path) -> None:
    h = Hub(HubConfig(data=tmp_path, admins=("mod",)))
    terms = h.config.terms_version
    ana = h.signup("ana", "contraseña-segura", terms=terms)
    beto = h.signup("beto", "contraseña-segura", terms=terms)
    admin = h.signup("mod", "contraseña-segura", terms=terms)
    assert admin["admin"] and not ana["admin"]
    for name, problem in (("api", "reservado"), ("Ana", "no válido"), ("x", "no válido")):
        with pytest.raises(HubError, match=problem):
            h.signup(name, "contraseña-segura", terms=terms)
    with pytest.raises(HubError, match="condiciones"):
        h.signup("carla", "contraseña-segura")
    with pytest.raises(HubError, match="8 caracteres"):
        h.signup("carla", "corta", terms=terms)
    with pytest.raises(HubError, match="incorrectos"):
        h.login("ana", "otra-contraseña")
    assert h.login("ana", "contraseña-segura")["name"] == "ana"

    club = h.create_org("club", ana)
    h.set_member(club, ana, "beto", "member")
    repo = h.create_repo("club", "nim", beto, files={"nim.game": b"// vacio\n"})
    assert h.can_write(repo, ana) and h.can_write(repo, beto)
    assert h.can_admin(repo, ana) and not h.can_admin(repo, beto)
    with pytest.raises(HubError, match="no puedes crear"):
        h.create_repo("ana", "otro", beto)
    with pytest.raises(HubError, match="un dueño"):
        h.set_member(club, ana, "ana", None)

    fork = h.fork(repo, beto)
    assert fork["parent"] == repo["id"] and h.git(fork).branches().keys() == {"main"}
    commit = h.commit_files(fork, beto, "main", {"README.md": b"hola\n"}, "Léeme")
    assert h.git(fork).read(commit, "README.md") == b"hola\n"
    with pytest.raises(HubError, match="no hay cambios"):
        h.commit_files(fork, beto, "main", {"README.md": b"hola\n"}, "otra vez")
    with pytest.raises(HubError, match="ruta no válida"):
        h.commit_files(fork, beto, "main", {"../fuera": b"x"}, "fuera")
    assert h.star(repo, ana, True) == 1 and h.star(repo, beto, True) == 2
    assert h.star(repo, ana, False) == 1

    # Moderación: ocultar y suspender.
    h.moderate_repo(admin, repo, True)
    with pytest.raises(HubError):
        h.repo("club", "nim", None)
    assert h.repo("club", "nim", beto)["id"] == repo["id"]
    with pytest.raises(HubError, match="moderación"):
        h.moderate_repo(ana, repo, False)
    secret = h.new_session(beto)
    h.suspend(admin, beto, True)
    assert h.session_account(secret) is None
    with pytest.raises(HubError, match="suspendida"):
        h.login("beto", "contraseña-segura")
    h.close()


# --- la aceptación de la fase -------------------------------------------------------------------


async def play_seat(url: str, token: str | None, code: str, seed: int) -> list[dict[str, Any]]:
    async with Client(url, name=f"jugador{seed}", token=token) as client:
        if token is None:
            await client.join(code)
        game = Game(await client.room_ir())
        runner = AgentRunner(client, load_agent("random", seed=seed), game, matches=1)
        return await runner.run()


def test_acceptance_publish_fork_variant_pull_merge_play(hub: HubThread) -> None:
    ana, beto = hub.user("ana"), hub.user("beto")
    anon = User(hub.url, None)

    # A publica su juego.
    ana.post(
        "/repos", {"name": "nim", "description": "Nim de Bouton", "files": package_files("nim")}
    )
    first = ana.post("/repos/ana/nim/releases", {})
    assert first["ref"] == "ana/nim@1.0.0" and first["level"] is None
    assert "información perfecta" in first["properties"]["labels"]
    assert hub.run_jobs() == 1  # el análisis de la versión
    analysis = anon.get("/repos/ana/nim/releases/1.0.0")["properties"]["analysis"]
    assert analysis["exact"]["positions"] == 376 and analysis["branching"] > 1
    view = anon.get("/repos/ana/nim/releases/1.0.0/view")
    assert view["rules"].startswith("# Nim") and view["model"]["game"]["name"] == "Nim"

    # B hace un fork y crea una variante (desde la web: un commit en una rama nueva).
    fork = beto.post("/repos/ana/nim/forks", {"name": "nim-misere"})
    assert fork["parent"] == "ana/nim"
    text = nim_text().replace("misere: Bool = false", "misere: Bool = true")
    beto.post(
        "/repos/beto/nim-misere/files",
        {"branch": "misere", "base": "main", "message": "Misère", "changes": {"nim.game": text}},
    )

    # B la propone: diffs de texto, semántico (con el nivel de semver) y visual, y el balance.
    pull = beto.post(
        "/repos/ana/nim/pulls",
        {"source": "beto/nim-misere", "head": "misere", "title": "Nim misère por defecto"},
    )
    assert pull["number"] == 1 and pull["mergeable"] and pull["balance_job"] is not None
    assert not pull["can_merge"]
    diff = anon.get("/repos/ana/nim/pulls/1/diff")
    assert diff["text"]["files"] == [{"path": "nim.game", "added": 1, "removed": 1}]
    assert "+    misere: Bool = true" in diff["text"]["patch"]
    semantic = diff["semantic"]
    assert not semantic["same_rules"] and semantic["level"] == "minor"
    assert semantic["changes"] == [
        {
            "op": "~",
            "path": "opción misere",
            "old": "misere: Bool = false",
            "new": "misere: Bool = true",
        }
    ]
    assert diff["visual"]["base"]["game"]["name"] == diff["visual"]["head"]["game"]["name"] == "Nim"
    assert hub.run_jobs() == 1
    balance = ana.get("/repos/ana/nim/pulls/1")["balance"]
    assert balance["status"] == "done" and balance["kind"] == "balance_ci"
    assert balance["result"]["markdown"].startswith("# Balance CI: nim")
    beto.post("/repos/ana/nim/pulls/1/comments", {"body": "La misère es más traicionera."})

    # A la fusiona y publica: el hub elige la versión (cambio de reglas: menor).
    with pytest.raises(ApiError) as denied:
        beto.post("/repos/ana/nim/pulls/1/merge")
    assert denied.value.status == 403
    merged = ana.post("/repos/ana/nim/pulls/1/merge")
    assert merged["state"] == "merged" and merged["comments"][0]["author"] == "beto"
    second = ana.post("/repos/ana/nim/releases", {})
    assert second["ref"] == "ana/nim@1.1.0" and second["level"] == "minor"
    assert second["rules_hash"] != first["rules_hash"]

    # Cualquiera juega la versión nueva en línea (sin cuenta).
    async def scenario() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        req = urllib.request.Request(
            hub.url + "/api/v1/rooms",
            data=json.dumps({"game": "ana/nim@1.1.0"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        created = json.loads(await asyncio.to_thread(lambda: urllib.request.urlopen(req).read()))
        code = created["code"]
        return await asyncio.gather(
            play_seat(hub.url, None, code, 1), play_seat(hub.url, None, code, 2)
        )

    results = asyncio.run(asyncio.wait_for(scenario(), 60))
    assert all(r[0]["reason"] == "terminal" for r in results)
    assert anon.get("/api/v1/info".removeprefix("/api/v1"))["name"] == "GameHub"
    stored = anon.get("/repos/ana/nim/ratings?version=1.1.0")["matches"]
    assert stored and stored[0]["game"] == "ana/nim@1.1.0" and not stored[0]["rated"]

    # La familia y la búsqueda.
    family = anon.get("/repos/beto/nim-misere/family")
    assert family["ancestors"] == ["ana/nim"] and family["root"]["children"][0]["current"]
    found = anon.get(
        "/search?q=" + urllib.parse.quote("2 jugadores suma cero información perfecta")
    )
    assert [r["full_name"] for r in found["results"]] == ["ana/nim"]
    assert found["filters"] == {"players": 2, "zero_sum": True, "perfect_information": True}


def test_semver_is_enforced_on_publish(hub: HubThread) -> None:
    ana = hub.user("ana")
    ana.post("/repos", {"name": "nim", "files": package_files("nim")})
    ana.post("/repos/ana/nim/releases", {"version": "1.0.0"})
    with pytest.raises(ApiError, match="nada que publicar"):
        ana.post("/repos/ana/nim/releases", {})
    # Una acción nueva amplía la interfaz (menor); quitar la que había la rompe (mayor).
    text = nim_text().replace("action take(", "action pasar() {}\n      action take(")
    ana.post("/repos/ana/nim/files", {"message": "Pasar", "changes": {"nim.game": text}})
    plan = ana.post("/repos/ana/nim/releases", {"dry_run": True})
    assert plan["level"] == "minor" and plan["version"] == "1.1.0"
    assert plan["interface_changes"] == [{"op": "+", "path": "actions.pasar", "breaking": False}]
    ana.post("/repos/ana/nim/releases", {})
    renamed = re.sub(r"\btake\b", "quitar", text).replace("action pasar() {}\n      ", "")
    ana.post("/repos/ana/nim/files", {"message": "Renombra", "changes": {"nim.game": renamed}})
    with pytest.raises(ApiError) as low:
        ana.post("/repos/ana/nim/releases", {"version": "1.2.0"})
    assert low.value.status == 422 and "al menos 2.0.0" in low.value.body["error"]["message"]
    assert ana.post("/repos/ana/nim/releases", {})["version"] == "2.0.0"
    # Un error de compilación no se publica, y lo dice.
    ana.post("/repos/ana/nim/files", {"message": "Rompe", "changes": {"nim.game": "game {"}})
    with pytest.raises(ApiError, match=r"error\["):
        ana.post("/repos/ana/nim/releases", {})
    versions = [r["version"] for r in ana.get("/repos/ana/nim/releases")["releases"]]
    assert versions == ["2.0.0", "1.1.0", "1.0.0"]
    ana.post("/repos/ana/nim/releases/1.1.0/yank", {})
    assert User(hub.url, None).get("/repos/ana/nim/resolve?requirement=%5E1")["version"] == "1.0.0"


def test_library_dependency_resolved_by_the_registry(hub: HubThread, tmp_path: Path) -> None:
    ana = hub.user("ana")
    ana.post(
        "/repos",
        {
            "name": "dilemas",
            "kind": "library",
            "files": {
                "game.toml": '[game]\nname = "dilemas"\nversion = "1.0.0"\n',
                "dilemas.game": "fn premio(a: Int, b: Int) -> Int = a * 2 + b\n",
            },
        },
    )
    ana.post("/repos/ana/dilemas/releases", {})
    game = (
        nim_text()
        .replace("game Nim {", "import dilemas.{premio}\n\ngame Nim {", 1)
        .replace(
            "win_loss(other(turn) if misere else turn, 1, -1)",
            "win_loss(other(turn) if misere else turn, premio(0, 1), -1)",
        )
    )
    files = {
        "game.toml": '[game]\nname = "nim-premio"\n\n[dependencies]\n"ana/dilemas" = "^1.0"\n',
        "nim-premio.game": game,
    }
    ana.post("/repos", {"name": "nim-premio", "files": files})
    rel = ana.post("/repos/ana/nim-premio/releases", {})
    assert rel["dependencies"] == [{"repo": "ana/dilemas", "requirement": "^1.0"}]
    assert User(hub.url, None).get("/repos/ana/dilemas/family")["dependents"] == [
        {"repo": "ana/nim-premio"}
    ]

    # En local, `gamehub fetch` pregunta al registro y fija la versión en el lock.
    local = tmp_path / "local"
    local.mkdir()
    for name, text in files.items():
        (local / name).write_text(text, encoding="utf-8")
    os.environ["GAMEHUB_HUB"] = hub.url
    try:
        assert main(["fetch", str(local)]) == 0
    finally:
        del os.environ["GAMEHUB_HUB"]
    locked = load_lock(local)["dilemas"]
    assert (locked.hub, locked.version, locked.rev) == ("ana/dilemas", "1.0.0", "v1.0.0")
    assert load_nomos(local / "nim-premio.game").rules_hash == rel["rules_hash"]


# --- git por HTTP y la CLI ----------------------------------------------------------------------


def git(
    *args: str, cwd: Path | None = None, check: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=check)


def test_git_over_http_clone_and_authenticated_push(hub: HubThread, tmp_path: Path) -> None:
    ana = hub.user("ana")
    ana.post("/repos", {"name": "nim", "files": package_files("nim")})
    work = tmp_path / "nim"
    git("clone", "--quiet", f"{hub.url}/ana/nim.git", str(work))
    assert (work / "nim.game").is_file()
    (work / "README.md").write_text("Nim\n")
    git("add", "-A", cwd=work)
    git("commit", "--quiet", "-m", "Léeme", cwd=work)
    anonymous = git("push", "origin", "HEAD:main", cwd=work, check=False)
    assert anonymous.returncode != 0
    auth = base64.b64encode(f"ana:{ana.token}".encode()).decode()
    git(
        "-c",
        f"http.extraHeader=Authorization: Basic {auth}",
        "push",
        "--quiet",
        "origin",
        "HEAD:main",
        cwd=work,
    )
    events = ana.get("/repos/ana/nim/events")["events"]
    assert events[0]["kind"] == "pushed" and "heads/main" in events[0]["data"]["refs"]
    assert ana.get("/repos/ana/nim/file?path=README.md")["text"] == "Nim\n"
    beto = hub.user("beto")
    other = base64.b64encode(f"beto:{beto.token}".encode()).decode()
    denied = git(
        "-c",
        f"http.extraHeader=Authorization: Basic {other}",
        "push",
        "origin",
        "HEAD:main",
        cwd=work,
        check=False,
    )
    assert denied.returncode != 0 and "403" in denied.stderr
    # Las etiquetas de versión y las referencias de propuestas son del hub.
    git("tag", "v9.9.9", cwd=work)
    tagged = git(
        "-c",
        f"http.extraHeader=Authorization: Basic {auth}",
        "push",
        "origin",
        "v9.9.9",
        cwd=work,
        check=False,
    )
    assert tagged.returncode != 0


def test_cli_login_publish_fork_and_pull_request(hub: HubThread, tmp_path: Path) -> None:
    ana, beto = hub.user("ana"), hub.user("beto")
    work = tmp_path / "nim"
    work.mkdir()
    for name, text in package_files("nim").items():
        (work / name).write_text(text, encoding="utf-8")
    git("init", "--quiet", "--initial-branch=main", cwd=work)
    git("add", "-A", cwd=work)
    git("commit", "--quiet", "-m", "Nim", cwd=work)
    assert main(["login", "--hub", hub.url, "--token", str(ana.token)]) == 0
    assert main(["publish", str(work), "--dry-run"]) == 0
    assert main(["publish", str(work)]) == 0
    assert ana.get("/repos/ana/nim/releases/latest")["version"] == "1.0.0"

    assert main(["login", "--hub", hub.url, "--token", str(beto.token)]) == 0
    fork_dir = tmp_path / "variante"
    assert main(["fork", "ana/nim", str(fork_dir), "--as", "nim-grande"]) == 0
    game = fork_dir / "nim.game"
    game.write_text(game.read_text().replace("[3, 5, 7]", "[3, 5, 7, 9]"), encoding="utf-8")
    git("checkout", "--quiet", "-b", "grande", cwd=fork_dir)
    git("commit", "--quiet", "-am", "Cuatro montones", cwd=fork_dir)
    assert main(["hub", "pr", "create", "--dir", str(fork_dir), "--title", "Cuatro montones"]) == 0
    assert main(["hub", "pr", "list", "--repo", "ana/nim"]) == 0
    assert main(["hub", "pr", "show", "1", "--repo", "ana/nim"]) == 0
    assert main(["hub", "pr", "merge", "1", "--repo", "ana/nim"]) == 1  # beto no puede

    assert main(["login", "--hub", hub.url, "--token", str(ana.token)]) == 0
    assert main(["hub", "pr", "merge", "1", "--repo", "ana/nim"]) == 0
    assert main(["clone", "ana/nim", str(tmp_path / "clon")]) == 0
    assert "[3, 5, 7, 9]" in (tmp_path / "clon" / "nim.game").read_text()
    assert main(["hub", "search", "nim"]) == 0
    assert main(["hub", "whoami"]) == 0


# --- jugar: emparejamiento y valoraciones -------------------------------------------------------


def test_matchmaking_and_human_ratings(hub: HubThread) -> None:
    ana, beto = hub.user("ana"), hub.user("beto")
    ana.post("/repos", {"name": "tictactoe", "files": package_files("tictactoe")})
    ana.post("/repos/ana/tictactoe/releases", {})

    async def wait(user: User, ticket: str) -> dict[str, Any]:
        for _ in range(100):
            t = await asyncio.to_thread(user.get, f"/matchmaking/{ticket}")
            if t["status"] == "matched":
                return t
            await asyncio.sleep(0.1)
        raise AssertionError("sin emparejar")

    async def one_match() -> None:
        ta = await asyncio.to_thread(ana.post, "/matchmaking", {"game": "ana/tictactoe"})
        tb = await asyncio.to_thread(beto.post, "/matchmaking", {"game": "ana/tictactoe"})
        assert ta["game"] == "ana/tictactoe@1.0.0" and ta["status"] == "waiting"
        ma, mb = await asyncio.gather(wait(ana, ta["id"]), wait(beto, tb["id"]))
        assert ma["room"] == mb["room"] and {ma["seat"], mb["seat"]} == {0, 1}
        await asyncio.gather(
            play_seat(hub.url, ma["token"], ma["room"], 1),
            play_seat(hub.url, mb["token"], mb["room"], 2),
        )

    for _ in range(3):
        asyncio.run(asyncio.wait_for(one_match(), 60))
    board = User(hub.url, None).get("/repos/ana/tictactoe/ratings")
    assert {r["account"] for r in board["ratings"]} == {"ana", "beto"}
    assert all(r["games"] == 3 for r in board["ratings"])
    assert all(m["rated"] and m["humans_only"] for m in board["matches"])
    with pytest.raises(ApiError, match="jugadores"):
        ana.post("/matchmaking", {"game": "ana/tictactoe", "players": 3})


# --- trabajos -----------------------------------------------------------------------------------


def test_jobs_arena_and_quotas(tmp_path: Path) -> None:
    with HubThread(tmp_path / "hub", quotas=Quotas(jobs_per_day=2, concurrent_jobs=1)) as hub:
        ana = hub.user("ana")
        ana.post("/repos", {"name": "tictactoe", "files": package_files("tictactoe")})
        ana.post("/repos/ana/tictactoe/releases", {})
        hub.run_jobs()
        job = ana.post(
            "/repos/ana/tictactoe/jobs",
            {"kind": "arena", "entrants": ["greedy", "random"], "options": {"games": 4}},
        )
        assert job["status"] == "queued" and job["position"] == 0
        with pytest.raises(ApiError) as busy:
            ana.post("/repos/ana/tictactoe/jobs", {"kind": "analyze"})
        assert busy.value.status == 429
        hub.run_jobs()
        done = ana.get(f"/jobs/{job['id']}")
        assert done["status"] == "done", done
        assert "greedy" in done["result"]["table"]
        bad_job = ana.post(
            "/repos/ana/tictactoe/jobs",
            {"kind": "arena", "entrants": ["random", "/tmp/malo.py"]},
        )
        hub.run_jobs()
        failed = ana.get(f"/jobs/{bad_job['id']}")
        assert failed["status"] == "failed" and "núcleo" in failed["error"]
        with pytest.raises(ApiError, match="hoy"):
            ana.post("/repos/ana/tictactoe/jobs", {"kind": "analyze"})


# --- Pages, OAuth, moderación y seguridad -------------------------------------------------------


def test_pages_are_served_sandboxed(hub: HubThread) -> None:
    ana = hub.user("ana")
    ana.post("/repos", {"name": "nim", "files": package_files("nim")})
    rel = ana.post("/repos/ana/nim/releases", {})
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in (("dist/index.html", b"<h1>Nim</h1>"), ("dist/app.js", b"1;")):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    page = ana.call(
        "POST",
        "/repos/ana/nim/pages?name=tablero",
        raw=buf.getvalue(),
        headers={"Content-Type": "application/gzip"},
    )
    assert page["interface_hash"] == rel["interface_hash"] and page["versions"] == ["1.0.0"]
    assert page["files"] == 2
    with urllib.request.urlopen(hub.url + "/pages/ana/nim/tablero/") as response:
        assert response.read() == b"<h1>Nim</h1>"
        assert response.headers["Content-Security-Policy"].startswith("sandbox")
    with urllib.request.urlopen(hub.url + "/pages/ana/nim/tablero/otra/ruta") as response:
        assert response.read() == b"<h1>Nim</h1>"  # una app de una página
    assert User(hub.url, None).get("/repos/ana/nim/releases/1.0.0")["pages"][0]["name"] == "tablero"
    evil = io.BytesIO()
    with tarfile.open(fileobj=evil, mode="w:gz") as tar:
        info = tarfile.TarInfo("../fuera.html")
        info.size = 1
        tar.addfile(info, io.BytesIO(b"x"))
    with pytest.raises(ApiError, match="ruta no válida"):
        ana.call("POST", "/repos/ana/nim/pages?name=malo", raw=evil.getvalue())


def test_oauth_login_with_a_provider(tmp_path: Path) -> None:
    provider = OAuthProvider(
        "prueba",
        "Prueba",
        "https://sso.invalid/authorize",
        "https://sso.invalid/token",
        "https://sso.invalid/userinfo",
        "cliente",
        "secreto",
    )
    calls: list[tuple[str, str]] = []

    def fake_fetch(method: str, url: str, headers: dict[str, str], body: bytes | None) -> Any:
        calls.append((method, url))
        if url.endswith("/token"):
            assert b"code=abc" in (body or b"") and b"client_secret=secreto" in (body or b"")
            return {"access_token": "t0k3n"}
        assert headers["Authorization"] == "Bearer t0k3n"
        return {
            "id": 42,
            "login": "Juan_Martín",
            "name": "Juan Martín",
            "email": "j@example.invalid",
        }

    with HubThread(tmp_path / "hub", oauth={"prueba": provider}) as hub:
        hub.app.fetch = fake_fetch  # type: ignore[method-assign]

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(  # pyright: ignore[reportIncompatibleMethodOverride]
                self, *args: Any
            ) -> None:
                return None

        opener = urllib.request.build_opener(NoRedirect)
        with pytest.raises(urllib.error.HTTPError) as start:
            opener.open(hub.url + "/auth/prueba/login?next=/explore")
        location = start.value.headers["Location"]
        cookie = start.value.headers["Set-Cookie"].split(";")[0]
        state = urllib.parse.parse_qs(urllib.parse.urlsplit(location).query)["state"][0]
        assert (
            location.startswith("https://sso.invalid/authorize?")
            and "client_id=cliente" in location
        )
        bad_state = urllib.request.Request(
            hub.url + "/auth/prueba/callback?code=abc&state=otro", headers={"Cookie": cookie}
        )
        with pytest.raises(urllib.error.HTTPError) as rejected:
            opener.open(bad_state)
        assert rejected.value.code == 400
        req = urllib.request.Request(
            hub.url + f"/auth/prueba/callback?code=abc&state={state}", headers={"Cookie": cookie}
        )
        with pytest.raises(urllib.error.HTTPError) as done:
            opener.open(req)
        assert done.value.code == 302 and done.value.headers["Location"] == "/explore"
        session = [
            c for c in done.value.headers.get_all("Set-Cookie") or [] if c.startswith("gh_session=")
        ]
        me = urllib.request.Request(
            hub.url + "/api/v1/me", headers={"Cookie": session[0].split(";")[0]}
        )
        with urllib.request.urlopen(me) as response:
            user = json.loads(response.read())["user"]
        assert user["name"] == "juan-mart-n" and user["display"] == "Juan Martín"
        assert calls == [
            ("POST", "https://sso.invalid/token"),
            ("GET", "https://sso.invalid/userinfo"),
        ]


def test_moderation_reports_and_cross_site_requests(hub: HubThread) -> None:
    ana, beto, admin = hub.user("ana"), hub.user("beto"), hub.user("mod")
    ana.post("/repos", {"name": "nim", "files": package_files("nim")})
    report = beto.post("/reports", {"target": "repo:ana/nim", "reason": "Copia un reglamento"})
    with pytest.raises(ApiError) as denied:
        beto.get("/admin/reports")
    assert denied.value.status == 403
    listed = admin.get("/admin/reports")["reports"]
    assert listed[0]["id"] == report["id"] and listed[0]["label"] == "ana/nim"
    admin.post("/admin/repos/ana/nim", {"hidden": True})
    with pytest.raises(ApiError) as hidden:
        User(hub.url, None).get("/repos/ana/nim")
    assert hidden.value.status == 404
    assert ana.get("/repos/ana/nim")["hidden"]
    admin.post(f"/admin/reports/{report['id']}", {"status": "resolved", "resolution": "Oculto"})
    assert admin.get("/admin/reports")["reports"] == []

    # Con la cookie del navegador, una petición que cambia algo desde otro sitio se rechaza.
    login = urllib.request.Request(
        hub.url + "/api/v1/auth/login",
        data=json.dumps({"name": "beto", "password": "contraseña-segura"}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(login) as response:
        cookie = response.headers["Set-Cookie"].split(";")[0]
    forged = urllib.request.Request(
        hub.url + "/api/v1/repos",
        data=json.dumps({"name": "robado"}).encode(),
        headers={
            "Content-Type": "application/json",
            "Cookie": cookie,
            "Origin": "https://malo.example",
        },
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as csrf:
        urllib.request.urlopen(forged)
    assert csrf.value.code == 403
    same = urllib.request.Request(
        hub.url + "/api/v1/repos",
        data=json.dumps({"name": "propio"}).encode(),
        headers={"Content-Type": "application/json", "Cookie": cookie, "Origin": hub.url},
        method="POST",
    )
    with urllib.request.urlopen(same) as response:
        assert response.status == 201


def test_query_parser() -> None:
    filters, rest = explore.parse_query(
        "juegos de cartas con información oculta para 4 jugadores #bazas"
    )
    assert filters == {"players": 4, "perfect_information": False, "tags": ["bazas"]}
    assert rest == "cartas"
    assert explore.parse_query("non-zero-sum deterministic branching < 12")[0] == {
        "max_branching": 12.0,
        "zero_sum": False,
        "chance": False,
    }
