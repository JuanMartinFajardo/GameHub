# SPDX-License-Identifier: Apache-2.0
"""Paquetes: game.toml, dependencias (path y git), game.lock, new, fetch, clone y fork. Las
dependencias git se prueban con repositorios locales (sin red)."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from gamehub.cli import main
from gamehub.lang.compiler import compile_file
from gamehub.lang.testing import GameTester
from gamehub.packages import (
    PackageError,
    clone,
    fetch,
    find_files,
    fork,
    load_lock,
    load_manifest,
    new_package,
)

GAMES = Path(__file__).resolve().parents[2] / "games"
IPD = """import prisoners_dilemma.{PrisonersDilemma}

game IteratedPD = repeat(PrisonersDilemma, rounds: 2)
"""


@pytest.fixture(autouse=True)
def cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "cache"
    monkeypatch.setenv("GAMEHUB_CACHE", str(path))
    return path


def git(*args: str, cwd: Path) -> str:
    done = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return done.stdout.strip()


def pd_package(root: Path, *, repo: bool = False) -> Path:
    root.mkdir(parents=True)
    shutil.copy(GAMES / "prisoners-dilemma" / "prisoners-dilemma.game", root)
    (root / "game.toml").write_text('[game]\nname = "prisoners-dilemma"\n', encoding="utf-8")
    if repo:
        git("init", "--quiet", "--initial-branch=main", cwd=root)
        git("add", ".", cwd=root)
        git("commit", "--quiet", "-m", "PD", cwd=root)
        git("tag", "v1", cwd=root)
    return root


def ipd_package(root: Path, dependency: str) -> Path:
    root.mkdir(parents=True)
    (root / "game.toml").write_text(
        f'[game]\nname = "iterated-pd"\n\n[dependencies]\nprisoners-dilemma = {dependency}\n',
        encoding="utf-8",
    )
    (root / "iterated-pd.game").write_text(IPD, encoding="utf-8")
    return root


def test_new_package_compiles_and_passes_its_test(tmp_path: Path) -> None:
    manifest = new_package(tmp_path / "carrera", "carrera", authors=["Ana"])
    assert load_manifest(tmp_path / "carrera") == manifest
    result = compile_file(manifest.entry_path)
    assert result.ok and not result.diagnostics.warnings
    report = GameTester(result.game()).run_all(playouts=3)
    assert all(t.ok for t in report.tests) and report.playouts.failure is None
    with pytest.raises(PackageError, match="no está vacío"):
        new_package(tmp_path / "carrera", "carrera")
    with pytest.raises(PackageError, match="nombre no válido"):
        new_package(tmp_path / "x", "Mal_Nombre")


def test_path_dependencies(tmp_path: Path) -> None:
    pd_package(tmp_path / "pd")
    (tmp_path / "pd" / "extra.game").write_text("fn bonus() -> Int = 1\n", encoding="utf-8")
    ipd = ipd_package(tmp_path / "ipd", '{ path = "../pd" }')
    (ipd / "iterated-pd.game").write_text(
        IPD.replace(
            "import prisoners_dilemma.{PrisonersDilemma}",
            "import prisoners_dilemma.{PrisonersDilemma}\nimport prisoners_dilemma.extra.{bonus}",
        ),
        encoding="utf-8",
    )
    result = compile_file(ipd / "iterated-pd.game")
    assert result.ok, [str(d) for d in result.diagnostics]
    assert result.game().ir["meta"]["title"]["es"] == "Dilema del prisionero (2 rondas)"


def test_git_dependencies_lock_and_update(tmp_path: Path) -> None:
    repo = pd_package(tmp_path / "pd", repo=True)
    ipd = ipd_package(tmp_path / "ipd", f'{{ git = "{repo.as_uri()}", rev = "main" }}')
    before = compile_file(ipd / "iterated-pd.game")
    assert [d.code for d in before.diagnostics.errors] == ["E507"]
    assert "gamehub fetch" in before.diagnostics.errors[0].message

    first = fetch(load_manifest(ipd))["prisoners-dilemma"]
    assert first.commit == git("rev-parse", "HEAD", cwd=repo)
    assert load_lock(ipd) == {"prisoners-dilemma": first}
    assert compile_file(ipd / "iterated-pd.game").ok

    (repo / "README.md").write_text("cambio\n", encoding="utf-8")
    git("add", ".", cwd=repo)
    git("commit", "--quiet", "-m", "otro", cwd=repo)
    assert fetch(load_manifest(ipd))["prisoners-dilemma"] == first  # el lock manda
    updated = fetch(load_manifest(ipd), update=True)["prisoners-dilemma"]
    assert updated.commit == git("rev-parse", "HEAD", cwd=repo) != first.commit


def test_clone_and_fork(tmp_path: Path) -> None:
    repo = pd_package(tmp_path / "pd", repo=True)
    cloned = clone(str(repo), tmp_path / "copy")
    assert cloned is not None and cloned.name == "prisoners-dilemma"
    forked = fork(str(repo), tmp_path / "mine")
    commit = git("rev-parse", "HEAD", cwd=repo)
    assert forked.forked_from == f"{repo}@{commit}"
    assert git("remote", cwd=tmp_path / "mine") == "upstream"
    assert load_manifest(tmp_path / "mine").forked_from == forked.forked_from

    plain = pd_package(tmp_path / "plain")
    copied = fork(str(plain), tmp_path / "plain-fork")
    assert copied.forked_from == str(plain.resolve())
    assert compile_file(copied.entry_path).ok


@pytest.mark.parametrize(
    ("toml", "message"),
    [
        ("[game]\n", "falta [game]"),
        ('[game]\nname = "Mal"\n', "nombre de paquete no válido"),
        (
            '[game]\nname = "ok"\n[dependencies]\nx = { rev = "v1" }\n',
            'path = "…", git = "…" o hub = "dueño/nombre"',
        ),
        ("[game\n", "TOML no válido"),
    ],
)
def test_manifest_errors(tmp_path: Path, toml: str, message: str) -> None:
    (tmp_path / "game.toml").write_text(toml, encoding="utf-8")
    with pytest.raises(PackageError, match=re.escape(message)):
        load_manifest(tmp_path)


def test_package_commands(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["new", "carrera", "--dir", str(tmp_path / "carrera")]) == 0
    assert main(["test", str(tmp_path / "carrera"), "--playouts", "2"]) == 0
    repo = pd_package(tmp_path / "pd", repo=True)
    ipd = ipd_package(tmp_path / "ipd", f'{{ git = "{repo.as_uri()}", rev = "v1" }}')
    assert main(["fetch", str(ipd)]) == 0
    assert "✓ prisoners-dilemma v1 →" in capsys.readouterr().out
    assert main(["check", str(ipd)]) == 0
    assert main(["fork", str(repo), str(tmp_path / "fork")]) == 0
    assert main(["new", "carrera", "--dir", str(tmp_path / "carrera")]) == 1


def test_find_files_skips_ui_dependencies_and_hidden_folders(tmp_path: Path) -> None:
    (tmp_path / "a.game").write_text("", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.game").write_text("", encoding="utf-8")
    for skipped in ("ui/node_modules/x", "ui/dist", ".git", "node_modules"):
        folder = tmp_path / skipped
        folder.mkdir(parents=True)
        (folder / "z.game").write_text("", encoding="utf-8")
    found = [p.relative_to(tmp_path).as_posix() for p in find_files(tmp_path, ".game")]
    assert found == ["a.game", "sub/b.game"]
